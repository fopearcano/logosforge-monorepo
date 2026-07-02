#!/usr/bin/env python3
"""Optional companion: a local LAN Whisper server for LogosForge voice mode.

Run this **manually** on the machine that has the GPU/model — it is never
started, imported, or required by the LogosForge app. Stdlib HTTP server (no
framework needed for three endpoints); the only runtime dependency is the
optional ``faster-whisper`` package.

Endpoints
---------
* ``GET  /health`` ->
  ``{"ok": true, "backend": "faster-whisper", "model_loaded": true,
     "device": "...", "language_default": "auto"}``
* ``POST /v1/audio/transcriptions`` — OpenAI-compatible local shape:
  multipart/form-data with a required ``file`` field (WAV), optional
  ``language`` / ``response_format`` (``json`` default, ``text`` supported) /
  ``temperature`` (accepted, unused). Returns ``{"text": "..."}``.
* ``POST /inference`` — whisper.cpp-style compatibility alias (same handler).

Local-first rules
-----------------
* Binds **127.0.0.1 by default** (same-machine testing). Passing ``--host``
  with a LAN IP or ``0.0.0.0`` is an **explicit** choice and prints a strong
  warning — keep the port inside your trusted LAN / firewall; never expose it
  to the public internet. No tunnels, no public URLs, no firewall changes,
  no admin rights.
* ``--model`` should be a **local** model directory for Alpha (the server
  never downloads on your behalf beyond what faster-whisper does for an
  explicit *named* model — prefer a path).
* Optional static token: ``--auth-token SECRET`` -> clients must send
  ``Authorization: Bearer SECRET`` (the LogosForge custom header
  ``X-Voice-Token: SECRET`` is also accepted). **Basic LAN protection only —
  not internet-grade security.** The token is never logged.
* Never logs audio bytes or transcripts (``--debug`` adds sizes/timings only).

Example
-------
    pip install faster-whisper
    python scripts/local_whisper_server.py --model /models/faster-whisper-small
    # LAN (explicit):
    python scripts/local_whisper_server.py --model /models/faster-whisper-small \\
        --host 0.0.0.0 --port 8765
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN_HEADER = "X-Voice-Token"          # LogosForge custom-header alternative
TRANSCRIBE_PATHS = ("/v1/audio/transcriptions", "/inference")

LAN_WARNING = (
    "WARNING: LAN mode exposes transcription on the local network. "
    "Do not expose this port to the public internet."
)


class ServerConfig:
    def __init__(self, *, model: str = "", device: str = "auto",
                 compute_type: str = "auto", language: str = "auto",
                 auth_token: str = "", max_audio_seconds: int = 60,
                 max_payload_mb: int = 25, debug: bool = False) -> None:
        self.model = model
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.auth_token = auth_token
        self.max_audio_seconds = max_audio_seconds
        self.max_payload_mb = max_payload_mb
        self.debug = debug
        # transcribe_fn(wav_bytes, language) -> text. Injected for tests; set to
        # a faster-whisper call by load_model().
        self.transcribe_fn = None
        self.model_loaded = False


def load_model(cfg: ServerConfig) -> None:
    """Load faster-whisper up front so misconfiguration exits with a clear
    message instead of failing on the first request. Never falls back to any
    cloud service."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("Setup error: faster-whisper is not installed. "
              "Run: pip install faster-whisper", file=sys.stderr)
        raise SystemExit(2)
    try:
        model = WhisperModel(cfg.model, device=cfg.device,
                             compute_type=cfg.compute_type)
    except Exception as exc:
        print(f"Setup error: could not load Whisper model {cfg.model!r}: {exc}",
              file=sys.stderr)
        raise SystemExit(2)

    def _transcribe(wav_bytes: bytes, language: str) -> str:
        segments, _info = model.transcribe(
            io.BytesIO(wav_bytes), language=(language or None))
        return " ".join(s.text.strip() for s in segments).strip()

    cfg.transcribe_fn = _transcribe
    cfg.model_loaded = True


# ---------------------------------------------------------------------------
# Pure request helpers (unit-testable without sockets)
# ---------------------------------------------------------------------------


def check_auth(cfg: ServerConfig, headers) -> bool:
    """True when no token is configured, or the request carries it via
    ``Authorization: Bearer <token>`` or ``X-Voice-Token: <token>``."""
    if not cfg.auth_token:
        return True
    bearer = (headers.get("Authorization", "") or "").strip()
    if bearer == f"Bearer {cfg.auth_token}":
        return True
    return (headers.get(TOKEN_HEADER, "") or "") == cfg.auth_token


def extract_multipart(body: bytes, content_type: str) -> dict:
    """Fields from a multipart body: ``file`` (bytes) + text fields. Raw,
    non-multipart bodies fall back to ``{"file": body}`` (curl-friendly)."""
    match = re.search(r'boundary="?([^";,]+)"?', content_type or "")
    if not match:
        return {"file": body} if body else {}
    boundary = ("--" + match.group(1)).encode()
    out: dict = {}
    for part in body.split(boundary):
        header, _, payload = part.partition(b"\r\n\r\n")
        if not payload:
            continue
        payload = payload.rstrip(b"\r\n-")
        name_m = re.search(rb'name="([^"]+)"', header)
        if not name_m:
            continue
        name = name_m.group(1).decode("utf-8", "replace")
        if name == "file":
            out["file"] = payload
        else:
            out[name] = payload.decode("utf-8", "replace").strip()
    return out


def wav_duration_seconds(data: bytes) -> float | None:
    """Duration of a WAV payload, or None if it isn't parseable WAV."""
    try:
        with wave.open(io.BytesIO(data), "rb") as wf:
            rate = wf.getframerate()
            return (wf.getnframes() / float(rate)) if rate else None
    except Exception:
        return None


def validate_audio(cfg: ServerConfig, data: bytes) -> tuple[int, str]:
    """``(0, "")`` when acceptable, else ``(http_status, error message)``."""
    if not data:
        return (400, "no audio file (multipart 'file' field required)")
    if len(data) > cfg.max_payload_mb * 1024 * 1024:
        return (413, f"payload exceeds {cfg.max_payload_mb} MB limit")
    duration = wav_duration_seconds(data)
    if duration is None:
        return (415, "unsupported media type: send 16-bit WAV audio")
    if duration > cfg.max_audio_seconds:
        return (413, f"audio exceeds {cfg.max_audio_seconds} s limit")
    return (0, "")


def health_payload(cfg: ServerConfig) -> dict:
    return {"ok": True, "backend": "faster-whisper",
            "model_loaded": bool(cfg.model_loaded), "device": cfg.device,
            "language_default": cfg.language}


# ---------------------------------------------------------------------------
# HTTP handler / server
# ---------------------------------------------------------------------------


def make_handler(cfg: ServerConfig):
    class Handler(BaseHTTPRequestHandler):
        def _send_json(self, code: int, payload: dict) -> None:
            body = json.dumps(payload).encode()
            self._send_raw(code, body, "application/json")

        def _send_raw(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802 (http.server signature)
            if self.path.rstrip("/") in ("", "/health"):
                self._send_json(200, health_payload(cfg))
            else:
                self._send_json(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            if self.path not in TRANSCRIBE_PATHS:
                self._send_json(404, {"error": "not found"})
                return
            if not check_auth(cfg, self.headers):
                self._send_json(401, {"error": "missing or wrong token"})
                return
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length > cfg.max_payload_mb * 1024 * 1024:
                self._send_json(413, {"error": "payload too large"})
                return
            body = self.rfile.read(length) if length else b""
            fields = extract_multipart(
                body, self.headers.get("Content-Type", ""))
            audio = fields.get("file", b"")
            status, err = validate_audio(cfg, audio)
            if status:
                self._send_json(status, {"error": err})
                return
            language = fields.get("language", "") or \
                ("" if cfg.language == "auto" else cfg.language)
            started = time.monotonic()
            try:
                if cfg.transcribe_fn is None:
                    self._send_json(503, {"error": "model not loaded"})
                    return
                text = cfg.transcribe_fn(audio, language)
            except Exception as exc:   # report, never crash the server loop
                self.log_message("transcription error: %s",
                                 type(exc).__name__)
                self._send_json(500, {"error": "transcription failed"})
                return
            elapsed = time.monotonic() - started
            self.log_message("request ok: %d bytes in, %.2fs", len(audio),
                             elapsed)
            if fields.get("response_format", "json") == "text":
                self._send_raw(200, text.encode("utf-8"),
                               "text/plain; charset=utf-8")
            else:
                self._send_json(200, {"text": text})

        def log_message(self, fmt, *args):
            # Never logs audio bytes, transcripts, or tokens.
            sys.stderr.write("[local-whisper] %s\n" % (fmt % args))

    return Handler


def serve(cfg: ServerConfig, host: str, port: int) -> ThreadingHTTPServer:
    """Build (and return) the server — separated for tests; callers loop."""
    return ThreadingHTTPServer((host, port), make_handler(cfg))


def main() -> int:
    # Windows consoles default to a legacy code page (e.g. cp1252) that cannot
    # encode the Unicode in our help text / status lines (e.g. the arrow "->"),
    # which makes even ``--help`` crash with UnicodeEncodeError. Force UTF-8 on
    # stdout/stderr so the CLI is usable on Windows.
    for _stream in (sys.stdout, sys.stderr):
        _reconfigure = getattr(_stream, "reconfigure", None)
        if callable(_reconfigure):
            try:
                _reconfigure(encoding="utf-8")
            except (ValueError, OSError):  # pragma: no cover - stream not retargetable
                pass

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True,
                        help="LOCAL faster-whisper model directory (preferred) "
                             "or model name")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Bind address (default 127.0.0.1; a LAN IP or "
                             "0.0.0.0 is an explicit trusted-LAN choice)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--device", default="auto",
                        choices=("auto", "cpu", "cuda"))
    parser.add_argument("--compute-type", default="auto",
                        choices=("auto", "int8", "float16", "int8_float16"))
    parser.add_argument("--language", default="auto",
                        help="Default language when the client sends none")
    parser.add_argument("--auth-token", default="",
                        help="Optional static token (Authorization: Bearer …). "
                             "Basic LAN protection only.")
    parser.add_argument("--max-audio-seconds", type=int, default=60)
    parser.add_argument("--max-payload-mb", type=int, default=25)
    parser.add_argument("--debug", action="store_true",
                        help="Verbose sizes/timings (never audio or tokens)")
    args = parser.parse_args()

    cfg = ServerConfig(model=args.model, device=args.device,
                       compute_type=args.compute_type, language=args.language,
                       auth_token=args.auth_token,
                       max_audio_seconds=args.max_audio_seconds,
                       max_payload_mb=args.max_payload_mb, debug=args.debug)
    load_model(cfg)

    print(f"[local-whisper] serving on http://{args.host}:{args.port} "
          f"(backend=faster-whisper, model={args.model}, device={args.device})")
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"[local-whisper] {LAN_WARNING}", file=sys.stderr)
    if args.auth_token:
        print("[local-whisper] auth token required "
              "(Authorization: Bearer …) — value not logged.")
    serve(cfg, args.host, args.port).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
