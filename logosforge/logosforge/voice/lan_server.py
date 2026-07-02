"""Trusted Local-LAN Whisper server backend for the voice MVP.

LogosForge still captures and buffers microphone audio **locally**; only a
*finalized* audio segment is sent — as a WAV upload — to a Whisper server that
the user explicitly configured on the **local network**. This is local-first,
not cloud:

* **Private/loopback hosts only by default.** The URL validator accepts
  localhost / 127.0.0.0/8 / ::1, RFC1918 ranges (10/8, 172.16/12, 192.168/16),
  IPv4 link-local (169.254/16) and ``.local`` mDNS names. Hostnames are **never
  DNS-resolved** — a public domain (or an ngrok / tunnel URL) is rejected
  outright, so audio cannot be routed to the public internet.
* **Redirects are refused** (a local server cannot bounce the upload to a
  public host).
* **No discovery / scanning** — the user types the address.
* Optional static auth header for the local server; the token is **never
  logged** and never leaves the settings store.
* Payload guards: segments longer than ``lan_max_audio_seconds`` or larger than
  ``lan_max_payload_mb`` are refused before any request is made.

Implementation uses **stdlib urllib** (the repo's HTTP idiom — no new
dependency). The HTTP calls are wrapped in ``_http_post`` / ``_http_get`` so
tests can inject a fake transport (no network in CI).

Supported ``lan_api_type`` adapters (endpoint mapping; one request shape —
multipart/form-data with a ``file`` field):

* ``openai_compatible`` → ``POST {base}/v1/audio/transcriptions``
* ``whisper_cpp``       → ``POST {base}/inference``
* ``custom``            → ``POST {base}{lan_transcription_endpoint}``

Responses: JSON ``{"text": ...}`` (OpenAI-compatible and whisper.cpp server
style) or a plain-text body.
"""

from __future__ import annotations

import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request
import uuid

from logosforge.voice.transcriber import Transcriber, pcm_to_wav_bytes
from logosforge.voice.types import (
    LAN_PUBLIC_URL_MESSAGE,
    LAN_SETUP_MESSAGE,
    TranscriptSegment,
)

_DEFAULT_ENDPOINTS = {
    "openai_compatible": "/v1/audio/transcriptions",
    "whisper_cpp": "/inference",
}
_DEFAULT_HEALTH = "/health"


# ---------------------------------------------------------------------------
# Private/local URL validation (no DNS resolution — strict by construction)
# ---------------------------------------------------------------------------


def is_private_host(host: str) -> bool:
    """True only for clearly local/trusted hosts.

    Accepts: ``localhost``, ``*.local`` mDNS names, loopback / RFC1918 /
    link-local / unique-local IP literals. Everything else — including any
    public domain (ngrok, cloudflare tunnels, SaaS hosts) — is rejected;
    hostnames are never resolved, so a DNS name cannot smuggle a public IP.
    """
    host = (host or "").strip().lower().rstrip(".")
    if not host:
        return False
    if host == "localhost" or host.endswith(".localhost"):
        return True
    if host.endswith(".local"):
        return True
    # IPv6 literals arrive bracket-less from urlsplit().hostname.
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False                      # non-IP hostname: not provably local
    return bool(ip.is_loopback or ip.is_private or ip.is_link_local)


def validate_lan_url(url: str, *, allow_only_private: bool = True
                     ) -> tuple[bool, str]:
    """``(ok, message)`` for a configured LAN base URL."""
    url = (url or "").strip()
    if not url:
        return (False, LAN_SETUP_MESSAGE)
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return (False, LAN_SETUP_MESSAGE)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return (False, LAN_SETUP_MESSAGE)
    if allow_only_private and not is_private_host(parts.hostname):
        return (False, LAN_PUBLIC_URL_MESSAGE)
    return (True, "")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect — a LAN server must answer directly (it must not
    be able to bounce an audio upload toward a public host)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        raise urllib.error.HTTPError(
            req.full_url, code, "Redirects are not allowed for the LAN "
            "Whisper server.", headers, fp)


_OPENER = urllib.request.build_opener(_NoRedirect)


# ---------------------------------------------------------------------------
# Transcriber
# ---------------------------------------------------------------------------


class LanWhisperTranscriber(Transcriber):
    """Send finalized segments to a trusted Whisper server on the local LAN."""

    name = "lan_server"

    def __init__(self, settings) -> None:
        self._s = settings

    # -- config --------------------------------------------------------------
    def _base(self) -> str:
        return (self._s.lan_base_url or "").strip().rstrip("/")

    def _endpoint(self) -> str:
        api = (self._s.lan_api_type or "openai_compatible").strip().lower()
        if api == "custom":
            ep = (self._s.lan_transcription_endpoint or "").strip()
        else:
            ep = _DEFAULT_ENDPOINTS.get(api, _DEFAULT_ENDPOINTS["openai_compatible"])
        if ep and not ep.startswith("/"):
            ep = "/" + ep
        return ep

    def _health_url(self) -> str:
        ep = (self._s.lan_health_endpoint or "").strip() or _DEFAULT_HEALTH
        if not ep.startswith("/"):
            ep = "/" + ep
        return self._base() + ep

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        name = (self._s.lan_auth_header_name or "").strip()
        token = (self._s.lan_auth_token or "").strip()
        if name and token:
            headers[name] = token         # static local token; never logged
        return headers

    # -- availability / health (offline config check vs. live probe) ----------
    def availability(self) -> tuple[bool, str]:
        """Offline config validation only (no network — safe to call anywhere)."""
        ok, msg = validate_lan_url(
            self._s.lan_base_url,
            allow_only_private=bool(self._s.lan_allow_only_private_hosts))
        if not ok:
            return (False, msg)
        if (self._s.lan_api_type or "").lower() == "custom" \
                and not (self._s.lan_transcription_endpoint or "").strip():
            return (False, "Set the custom LAN transcription endpoint. "
                           + LAN_SETUP_MESSAGE)
        return (True, "")

    def health_check(self) -> tuple[bool, str]:
        """Live probe of the LAN server's health endpoint (UI button)."""
        ok, msg = self.availability()
        if not ok:
            return (False, msg)
        try:
            status, _body = self._http_get(
                self._health_url(), timeout=min(10, self._s.lan_timeout_seconds))
        except Exception:
            return (False, LAN_SETUP_MESSAGE)
        if 200 <= status < 300:
            return (True, "LAN Whisper server is reachable.")
        return (False, LAN_SETUP_MESSAGE)

    # -- transcription ---------------------------------------------------------
    def transcribe(self, pcm: bytes, *, sample_rate: int = 16000,
                   language: str = "auto") -> TranscriptSegment:
        ok, msg = self.availability()
        if not ok:
            return TranscriptSegment(text="", is_final=True, error=msg)
        if not pcm:
            return TranscriptSegment(text="", is_final=True)

        duration_s = (len(pcm) // 2) / float(sample_rate) if sample_rate else 0.0
        if duration_s > max(1, int(self._s.lan_max_audio_seconds)):
            return TranscriptSegment(text="", is_final=True,
                                     error="Segment exceeds the LAN audio limit.")
        wav = pcm_to_wav_bytes(pcm, sample_rate)
        if len(wav) > max(1, int(self._s.lan_max_payload_mb)) * 1024 * 1024:
            return TranscriptSegment(text="", is_final=True,
                                     error="Segment exceeds the LAN payload limit.")

        fields: dict[str, str] = {"response_format": "json"}
        lang = "" if language in ("", "auto") else language
        if lang:
            fields["language"] = lang
        if (self._s.lan_api_type or "").lower() == "openai_compatible":
            fields.setdefault("model", "whisper-1")   # ignored by local servers

        body, content_type = _encode_multipart(fields, "file", "segment.wav",
                                               "audio/wav", wav)
        headers = {"Content-Type": content_type, **self._headers()}
        url = self._base() + self._endpoint()
        try:
            status, raw = self._http_post(
                url, body, headers, timeout=max(5, int(self._s.lan_timeout_seconds)))
        except TimeoutError:
            return TranscriptSegment(text="", is_final=True,
                                     error="LAN Whisper server timed out.")
        except Exception:
            return TranscriptSegment(text="", is_final=True,
                                     error=LAN_SETUP_MESSAGE)
        if not (200 <= status < 300):
            return TranscriptSegment(
                text="", is_final=True,
                error=f"LAN Whisper server returned HTTP {status}.")
        text = _parse_transcript(raw)
        if text is None:
            return TranscriptSegment(text="", is_final=True,
                                     error="LAN Whisper server returned an "
                                           "unrecognized response.")
        return TranscriptSegment(text=text, is_final=True,
                                 language=lang, duration_s=duration_s)

    # -- transport (wrapped so tests can inject a fake; refuses redirects) -----
    def _http_post(self, url: str, body: bytes, headers: dict[str, str],
                   *, timeout: int) -> tuple[int, bytes]:
        req = urllib.request.Request(url, data=body, headers=headers,
                                     method="POST")
        try:
            with _OPENER.open(req, timeout=timeout) as resp:
                return (resp.status, resp.read())
        except urllib.error.HTTPError as exc:
            return (exc.code, exc.read() if exc.fp else b"")
        except TimeoutError:
            raise
        except OSError as exc:
            if "timed out" in str(exc).lower():
                raise TimeoutError(str(exc)) from exc
            raise

    def _http_get(self, url: str, *, timeout: int) -> tuple[int, bytes]:
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        try:
            with _OPENER.open(req, timeout=timeout) as resp:
                return (resp.status, resp.read())
        except urllib.error.HTTPError as exc:
            return (exc.code, exc.read() if exc.fp else b"")


def _encode_multipart(fields: dict[str, str], file_field: str, filename: str,
                      file_type: str, file_bytes: bytes) -> tuple[bytes, str]:
    boundary = "----logosforge-" + uuid.uuid4().hex
    out = bytearray()
    for key, value in fields.items():
        out += (f"--{boundary}\r\nContent-Disposition: form-data; "
                f"name=\"{key}\"\r\n\r\n{value}\r\n").encode("utf-8")
    out += (f"--{boundary}\r\nContent-Disposition: form-data; "
            f"name=\"{file_field}\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {file_type}\r\n\r\n").encode("utf-8")
    out += file_bytes
    out += f"\r\n--{boundary}--\r\n".encode("utf-8")
    return (bytes(out), f"multipart/form-data; boundary={boundary}")


def _parse_transcript(raw: bytes) -> str | None:
    """Transcript text from a JSON ``{"text": ...}`` or plain-text response."""
    try:
        text = raw.decode("utf-8", errors="replace").strip()
    except Exception:
        return None
    if not text:
        return ""
    if text.startswith("{") or text.startswith("["):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        if isinstance(data, dict) and isinstance(data.get("text"), str):
            return data["text"].strip()
        return None
    return text
