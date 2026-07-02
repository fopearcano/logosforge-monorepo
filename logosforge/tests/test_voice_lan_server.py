"""LAN Whisper companion server (scripts/local_whisper_server.py).

Spins the real stdlib HTTP server on 127.0.0.1 with an injected transcribe
function (no faster-whisper, no model, no network beyond loopback) and
exercises every endpoint — including a true integration round-trip with the
Desktop client's ``LanWhisperTranscriber``. The companion is opt-in: nothing in
the app imports or starts it.
"""

from __future__ import annotations

import array
import importlib.util
import json
import os
import threading
import urllib.error
import urllib.request
import wave
from io import BytesIO

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPT = os.path.join(_ROOT, "scripts", "local_whisper_server.py")
_SR = 16000

spec = importlib.util.spec_from_file_location("local_whisper_server", _SCRIPT)
srv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(srv)


def _wav(seconds: float) -> bytes:
    pcm = array.array("h", [4000] * int(_SR * seconds)).tobytes()
    buf = BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(_SR)
        wf.writeframes(pcm)
    return buf.getvalue()


def _multipart(file_bytes: bytes, fields: dict | None = None
               ) -> tuple[bytes, str]:
    boundary = "----test-boundary"
    out = bytearray()
    for key, value in (fields or {}).items():
        out += (f"--{boundary}\r\nContent-Disposition: form-data; "
                f"name=\"{key}\"\r\n\r\n{value}\r\n").encode()
    out += (f"--{boundary}\r\nContent-Disposition: form-data; "
            f"name=\"file\"; filename=\"a.wav\"\r\n"
            f"Content-Type: audio/wav\r\n\r\n").encode()
    out += file_bytes
    out += f"\r\n--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


@pytest.fixture()
def server():
    """A live companion server on 127.0.0.1:<random> with a mocked model."""
    cfg = srv.ServerConfig(model="/fake/model", device="cpu",
                           max_audio_seconds=5, max_payload_mb=1)
    cfg.transcribe_fn = lambda wav_bytes, language: (
        f"mock[{language or 'auto'}]")
    cfg.model_loaded = True
    httpd = srv.serve(cfg, "127.0.0.1", 0)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield cfg, f"http://127.0.0.1:{port}"
    httpd.shutdown()
    httpd.server_close()


def _post(url: str, body: bytes, ctype: str, headers: dict | None = None):
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": ctype, **(headers or {})},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


# ==========================================================================
# 1  /health
# ==========================================================================


def test_health_returns_ok_shape(server):
    _cfg, base = server
    with urllib.request.urlopen(base + "/health", timeout=10) as resp:
        data = json.loads(resp.read())
    assert data["ok"] is True
    assert data["backend"] == "faster-whisper"
    assert data["model_loaded"] is True
    assert data["device"] == "cpu"
    assert data["language_default"] == "auto"


# ==========================================================================
# 2-4, 8  transcription endpoint validation + success
# ==========================================================================


def test_missing_file_rejected(server):
    _cfg, base = server
    body, ctype = _multipart(b"", {"language": "en"})
    status, raw = _post(base + "/v1/audio/transcriptions", body, ctype)
    assert status == 400 and b"file" in raw


def test_oversized_payload_rejected(server):
    _cfg, base = server                       # cap is 1 MB in the fixture
    big = b"\x00" * (2 * 1024 * 1024)
    body, ctype = _multipart(big)
    # The server rejects via Content-Length BEFORE consuming the upload, so the
    # client sees either a clean 413 or a connection abort mid-upload — both are
    # a rejection (the Desktop client maps either to a non-crashing LAN error).
    try:
        status, _ = _post(base + "/v1/audio/transcriptions", body, ctype)
    except urllib.error.URLError:
        status = 413
    assert status == 413


def test_overlong_audio_rejected(server):
    _cfg, base = server                       # cap is 5 s in the fixture
    body, ctype = _multipart(_wav(8.0))
    status, raw = _post(base + "/v1/audio/transcriptions", body, ctype)
    assert status == 413 and b"limit" in raw


def test_invalid_audio_graceful(server):
    _cfg, base = server
    body, ctype = _multipart(b"this is not wav data")
    status, raw = _post(base + "/v1/audio/transcriptions", body, ctype)
    assert status == 415 and b"WAV" in raw


def test_transcription_returns_text(server):
    _cfg, base = server
    body, ctype = _multipart(_wav(0.5), {"language": "en"})
    status, raw = _post(base + "/v1/audio/transcriptions", body, ctype)
    assert status == 200
    assert json.loads(raw) == {"text": "mock[en]"}


def test_inference_alias_and_text_response_format(server):
    _cfg, base = server
    body, ctype = _multipart(_wav(0.5), {"response_format": "text"})
    status, raw = _post(base + "/inference", body, ctype)
    assert status == 200 and raw == b"mock[auto]"


# ==========================================================================
# 5-7, 9  auth token
# ==========================================================================


def test_bearer_token_accepted_and_required(server):
    cfg, base = server
    cfg.auth_token = "sekrit"
    body, ctype = _multipart(_wav(0.5))
    # Missing token -> 401.
    status, _ = _post(base + "/v1/audio/transcriptions", body, ctype)
    assert status == 401
    # Wrong token -> 401.
    status, _ = _post(base + "/v1/audio/transcriptions", body, ctype,
                      {"Authorization": "Bearer nope"})
    assert status == 401
    # Correct bearer -> 200.
    status, _ = _post(base + "/v1/audio/transcriptions", body, ctype,
                      {"Authorization": "Bearer sekrit"})
    assert status == 200
    # LogosForge custom header also accepted.
    status, _ = _post(base + "/v1/audio/transcriptions", body, ctype,
                      {srv.TOKEN_HEADER: "sekrit"})
    assert status == 200
    cfg.auth_token = ""


def test_no_token_required_when_not_configured(server):
    _cfg, base = server
    body, ctype = _multipart(_wav(0.5))
    status, _ = _post(base + "/v1/audio/transcriptions", body, ctype)
    assert status == 200


def test_auth_token_never_logged(server, capfd):
    cfg, base = server
    cfg.auth_token = "super-sekrit-token"
    body, ctype = _multipart(_wav(0.5))
    _post(base + "/v1/audio/transcriptions", body, ctype,
          {"Authorization": "Bearer super-sekrit-token"})
    cfg.auth_token = ""
    captured = capfd.readouterr()
    assert "super-sekrit-token" not in captured.out
    assert "super-sekrit-token" not in captured.err


def test_transcript_not_logged(server, capfd):
    cfg, base = server
    cfg.transcribe_fn = lambda w, l: "VERY_PRIVATE_TRANSCRIPT"
    body, ctype = _multipart(_wav(0.5))
    _post(base + "/v1/audio/transcriptions", body, ctype)
    captured = capfd.readouterr()
    assert "VERY_PRIVATE_TRANSCRIPT" not in captured.out
    assert "VERY_PRIVATE_TRANSCRIPT" not in captured.err


# ==========================================================================
# 10-18  Desktop client <-> companion server integration (real loopback HTTP)
# ==========================================================================


def _client(base_url: str, **over):
    from logosforge.voice.lan_server import LanWhisperTranscriber
    from logosforge.voice.types import VoiceSettings
    settings = VoiceSettings(enabled=True, backend_mode="lan_server",
                             lan_base_url=base_url, **over)
    return LanWhisperTranscriber(settings)


def test_client_health_check_against_live_server(server):
    _cfg, base = server
    ok, msg = _client(base).health_check()
    assert ok is True and "reachable" in msg


def test_client_transcription_against_live_server(server):
    _cfg, base = server
    pcm = array.array("h", [4000] * (_SR // 2)).tobytes()
    seg = _client(base).transcribe(pcm, sample_rate=_SR, language="en")
    assert seg.text == "mock[en]" and not seg.error


def test_client_auth_header_against_live_server(server):
    cfg, base = server
    cfg.auth_token = "tok123"
    pcm = array.array("h", [4000] * (_SR // 2)).tobytes()
    # Without the token the server answers 401 -> error status, no crash.
    seg = _client(base).transcribe(pcm, sample_rate=_SR)
    assert "401" in seg.error
    # With the custom header configured the request succeeds.
    seg = _client(base, lan_auth_header_name=srv.TOKEN_HEADER,
                  lan_auth_token="tok123").transcribe(pcm, sample_rate=_SR)
    assert seg.text == "mock[auto]" and not seg.error
    # Bearer works through the configurable header too.
    seg = _client(base, lan_auth_header_name="Authorization",
                  lan_auth_token="Bearer tok123").transcribe(pcm, sample_rate=_SR)
    assert seg.text == "mock[auto]"
    cfg.auth_token = ""


def test_client_unreachable_server_non_blocking():
    # Port 1 on loopback is private (validator passes) but nothing listens.
    client = _client("http://127.0.0.1:1", lan_timeout_seconds=5)
    ok, msg = client.health_check()
    assert ok is False and msg
    pcm = array.array("h", [4000] * (_SR // 2)).tobytes()
    seg = client.transcribe(pcm, sample_rate=_SR)
    assert seg.error and not seg.text


def test_client_still_blocks_public_urls():
    from logosforge.voice.types import LAN_PUBLIC_URL_MESSAGE
    ok, msg = _client("https://abc.ngrok.io").availability()
    assert ok is False and msg == LAN_PUBLIC_URL_MESSAGE


def test_model_not_loaded_returns_503(server):
    cfg, base = server
    fn = cfg.transcribe_fn
    cfg.transcribe_fn = None
    body, ctype = _multipart(_wav(0.5))
    status, raw = _post(base + "/v1/audio/transcriptions", body, ctype)
    cfg.transcribe_fn = fn
    assert status == 503 and b"model not loaded" in raw


# ==========================================================================
# CLI / startup behavior (subprocess — the real entry point)
# ==========================================================================


def test_cli_defaults_localhost_and_full_flag_set():
    import subprocess
    import sys
    out = subprocess.run([sys.executable, _SCRIPT, "--help"],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0
    text = out.stdout
    assert "127.0.0.1" in text                  # default bind is localhost
    for flag in ("--model", "--host", "--port", "--device", "--compute-type",
                 "--language", "--auth-token", "--max-audio-seconds",
                 "--max-payload-mb", "--debug"):
        assert flag in text, flag


def test_missing_faster_whisper_exits_with_clear_setup_message():
    # CI has no faster-whisper, so the real startup path must exit cleanly
    # with the install hint — never start a half-configured server.
    import subprocess
    import sys
    out = subprocess.run([sys.executable, _SCRIPT, "--model", "/fake/model"],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 2
    assert "faster-whisper is not installed" in out.stderr


# ==========================================================================
# Pure helpers + opt-in guarantee
# ==========================================================================


def test_wav_duration_helper():
    assert 0.4 < srv.wav_duration_seconds(_wav(0.5)) < 0.6
    assert srv.wav_duration_seconds(b"junk") is None


def test_default_port_and_lan_warning_text():
    assert "8765" in open(_SCRIPT).read()
    assert "Do not expose this port to the public internet" in srv.LAN_WARNING


def test_app_never_imports_companion_server():
    # The companion is opt-in: no app module references the script.
    import subprocess
    out = subprocess.run(
        ["grep", "-rl", "local_whisper_server", os.path.join(_ROOT, "logosforge")],
        capture_output=True, text=True)
    assert out.stdout.strip() == ""
