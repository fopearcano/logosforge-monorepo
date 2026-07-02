"""Voice MVP — backend modes + trusted Local-LAN Whisper server backend.

Covers the backend selector (disabled default, mode resolution), the strict
private-host URL validation (public/ngrok/cloud endpoints blocked, redirects
refused), the LAN transcriber (health check, transcription, timeout, invalid
response, payload caps, auth header hygiene) — all offline via an injected
transport — plus the panel's backend selector UI and LAN warnings.
"""

from __future__ import annotations

import array
import json
import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.voice.editor_commit import EditorCommitTarget
from logosforge.voice.lan_server import (
    LanWhisperTranscriber,
    _NoRedirect,
    is_private_host,
    validate_lan_url,
)
from logosforge.voice.recorder import MockRecorder
from logosforge.voice.session import VoiceSessionController
from logosforge.voice.transcriber import (
    DisabledTranscriber,
    MockTranscriber,
    build_transcriber,
)
from logosforge.voice.types import (
    BACKEND_DISABLED_MESSAGE,
    LAN_PUBLIC_URL_MESSAGE,
    LAN_SETUP_MESSAGE,
    VoiceSettings,
    VoiceStatus,
)

_SR = 16000


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    import logosforge.gomckee_bridge as gb
    monkeypatch.setattr(gb, "is_gomckee_enabled", lambda: False, raising=False)
    yield
    settings._instance = None


def _pcm(seconds: float) -> bytes:
    return array.array("h", [4000] * int(_SR * seconds)).tobytes()


def _lan_settings(**over) -> VoiceSettings:
    base = dict(enabled=True, backend_mode="lan_server",
                lan_base_url="http://192.168.1.50:8000")
    base.update(over)
    return VoiceSettings(**base)


def _get(d: dict):
    from logosforge.settings import DEFAULTS
    merged = {**DEFAULTS, **d}
    return merged.get


# ==========================================================================
# 1-2  Backend mode defaults + resolution
# ==========================================================================


def test_backend_mode_defaults_to_disabled_in_store():
    from logosforge.settings import DEFAULTS
    assert DEFAULTS["voice_backend_mode"] == "disabled"
    vs = VoiceSettings.from_store(_get({}))
    assert vs.backend_mode == "disabled"
    assert isinstance(build_transcriber(vs), DisabledTranscriber)


def test_disabled_mode_reports_clear_message():
    vs = VoiceSettings(enabled=True, backend_mode="disabled")
    t = build_transcriber(vs)
    ok, msg = t.availability()
    assert ok is False and msg == BACKEND_DISABLED_MESSAGE
    ctl = VoiceSessionController(vs, MockRecorder(), t)
    assert ctl.start_voice_session() is False
    assert ctl.status == VoiceStatus.DISABLED


def test_mode_resolution_and_builders():
    assert isinstance(build_transcriber(
        VoiceSettings(enabled=True, backend_mode="mock")), MockTranscriber)
    assert isinstance(build_transcriber(_lan_settings()), LanWhisperTranscriber)
    # Legacy back-compat: no backend_mode + backend="mock" -> mock.
    assert isinstance(build_transcriber(
        VoiceSettings(enabled=True, backend="mock")), MockTranscriber)


# ==========================================================================
# 5-7  Private-host URL validation (public blocked; redirects refused)
# ==========================================================================


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8080", "http://localhost:9000",
    "http://192.168.1.50:8000", "http://10.0.0.7:5000",
    "http://172.20.3.4", "http://my-gpu.local:8000",
    "http://169.254.10.10", "http://[::1]:8000",
])
def test_private_urls_accepted(url):
    assert validate_lan_url(url) == (True, "")


@pytest.mark.parametrize("url", [
    "https://api.openai.com/v1", "https://abc123.ngrok.io",
    "https://my-tunnel.trycloudflare.com", "https://example.com",
    "http://8.8.8.8:9000", "ftp://192.168.1.2", "",
])
def test_public_or_invalid_urls_rejected(url):
    ok, msg = validate_lan_url(url)
    assert ok is False and msg


def test_public_url_message_is_exact():
    assert validate_lan_url("https://example.com")[1] == LAN_PUBLIC_URL_MESSAGE


def test_public_hostnames_never_resolved():
    # Hostnames are not DNS-resolved, so a public domain can't smuggle in.
    assert is_private_host("evil-but-resolves-to-10.0.0.1.example.com") is False
    assert is_private_host("localhost") is True
    assert is_private_host("workstation.local") is True


def test_redirects_are_refused():
    import urllib.error
    handler = _NoRedirect()
    with pytest.raises(urllib.error.HTTPError):
        handler.redirect_request(
            type("R", (), {"full_url": "http://192.168.1.50:8000/x"})(),
            None, 302, "Found", {}, "https://evil.example.com/upload")


def test_private_only_can_be_relaxed_flag_exists_but_defaults_true():
    vs = VoiceSettings.from_store(_get({}))
    assert vs.lan_allow_only_private_hosts is True


# ==========================================================================
# 18-24  LAN transcriber behavior (injected transport — no network)
# ==========================================================================


def test_lan_missing_url_gives_setup_message():
    t = LanWhisperTranscriber(_lan_settings(lan_base_url=""))
    ok, msg = t.availability()
    assert ok is False and msg == LAN_SETUP_MESSAGE


def test_lan_public_url_blocked_in_availability():
    t = LanWhisperTranscriber(_lan_settings(lan_base_url="https://example.com"))
    ok, msg = t.availability()
    assert ok is False and msg == LAN_PUBLIC_URL_MESSAGE


def test_lan_health_check_success_and_failure():
    t = LanWhisperTranscriber(_lan_settings())
    t._http_get = lambda url, timeout: (200, b"ok")
    assert t.health_check()[0] is True
    t._http_get = lambda url, timeout: (_ for _ in ()).throw(OSError("refused"))
    ok, msg = t.health_check()
    assert ok is False and msg == LAN_SETUP_MESSAGE


def test_lan_transcription_round_trip_uses_private_url_only():
    t = LanWhisperTranscriber(_lan_settings())
    captured = {}

    def fake_post(url, body, headers, timeout):
        captured.update(url=url, headers=dict(headers))
        return (200, json.dumps({"text": "lan transcript"}).encode())
    t._http_post = fake_post
    seg = t.transcribe(_pcm(0.5), sample_rate=_SR, language="en")
    assert seg.text == "lan transcript" and not seg.error
    assert captured["url"] == \
        "http://192.168.1.50:8000/v1/audio/transcriptions"
    assert captured["headers"]["Content-Type"].startswith("multipart/form-data")


def test_lan_api_type_endpoints():
    captured = {}

    def fake_post(url, body, headers, timeout):
        captured["url"] = url
        return (200, b'{"text": "x"}')
    cpp = LanWhisperTranscriber(_lan_settings(lan_api_type="whisper_cpp"))
    cpp._http_post = fake_post
    cpp.transcribe(_pcm(0.5), sample_rate=_SR)
    assert captured["url"].endswith("/inference")
    custom = LanWhisperTranscriber(_lan_settings(
        lan_api_type="custom", lan_transcription_endpoint="/api/stt"))
    custom._http_post = fake_post
    custom.transcribe(_pcm(0.5), sample_rate=_SR)
    assert captured["url"].endswith("/api/stt")


def test_lan_custom_without_endpoint_unavailable():
    t = LanWhisperTranscriber(_lan_settings(lan_api_type="custom"))
    ok, msg = t.availability()
    assert ok is False and msg


def test_lan_timeout_returns_error_status():
    t = LanWhisperTranscriber(_lan_settings())

    def boom(*a, **k):
        raise TimeoutError("t")
    t._http_post = boom
    seg = t.transcribe(_pcm(0.5), sample_rate=_SR)
    assert "timed out" in seg.error


def test_lan_server_error_and_invalid_response_handled():
    t = LanWhisperTranscriber(_lan_settings())
    t._http_post = lambda *a, **k: (500, b"oops")
    assert "500" in t.transcribe(_pcm(0.5), sample_rate=_SR).error
    t._http_post = lambda *a, **k: (200, b'{"weird": 1}')
    assert "unrecognized" in t.transcribe(_pcm(0.5), sample_rate=_SR).error
    t._http_post = lambda *a, **k: (200, b"plain text result")
    assert t.transcribe(_pcm(0.5), sample_rate=_SR).text == "plain text result"


def test_lan_audio_and_payload_caps_block_before_sending():
    sent = []
    t = LanWhisperTranscriber(_lan_settings(lan_max_audio_seconds=1))
    t._http_post = lambda *a, **k: sent.append(1) or (200, b'{"text":"x"}')
    seg = t.transcribe(_pcm(3.0), sample_rate=_SR)
    assert "limit" in seg.error and not sent       # refused before any request


def test_lan_auth_header_sent_but_never_logged(caplog):
    t = LanWhisperTranscriber(_lan_settings(
        lan_auth_header_name="X-Token", lan_auth_token="sekrit-token"))
    captured = {}
    t._http_post = lambda url, body, headers, timeout: (
        captured.update(headers=dict(headers)) or (200, b'{"text":"x"}'))
    with caplog.at_level("DEBUG"):
        t.transcribe(_pcm(0.5), sample_rate=_SR)
    assert captured["headers"].get("X-Token") == "sekrit-token"
    assert "sekrit-token" not in caplog.text       # token never logged


def test_lan_session_end_to_end_with_mock_recorder():
    finals = []
    settings = _lan_settings(silence_ms=300)
    t = LanWhisperTranscriber(settings)
    t._http_post = lambda *a, **k: (200, b'{"text": "from lan"}')
    ctl = VoiceSessionController(settings, MockRecorder(), t,
                                 on_final_transcript=lambda s: finals.append(s.text))
    assert ctl.start_voice_session() is True
    speech = array.array("h", [6000 if i % 2 else -6000
                               for i in range(_SR // 2)]).tobytes()
    ctl._recorder.feed_chunk(speech)
    ctl._recorder.feed_chunk(b"\x00\x00" * int(_SR * 0.4))
    ctl.stop_voice_session()
    assert finals == ["from lan"]


# ==========================================================================
# 30-32  Panel UI: backend selector + LAN warnings
# ==========================================================================


def _panel(**settings):
    from logosforge.ui.voice_panel import VoicePanel
    base = dict(enable_voice_mode=True)
    base.update(settings)
    saved = {}
    p = VoicePanel(settings_get=_get(base),
                   settings_set=lambda k, v: saved.__setitem__(k, v),
                   commit_target=EditorCommitTarget())
    p._test_saved = saved
    return p


def test_panel_backend_selector_lists_all_modes():
    p = _panel(voice_backend_mode="disabled")
    values = [p._backend_combo.itemData(i)
              for i in range(p._backend_combo.count())]
    assert values == ["disabled", "local_process", "whisper_cpp",
                      "lan_server", "mock"]
    assert p._backend_combo.currentData() == "disabled"


def test_panel_backend_selector_persists_choice():
    p = _panel(voice_backend_mode="disabled")
    idx = next(i for i in range(p._backend_combo.count())
               if p._backend_combo.itemData(i) == "lan_server")
    p._backend_combo.setCurrentIndex(idx)
    assert p._test_saved.get("voice_backend_mode") == "lan_server"


def test_panel_disabled_mode_start_shows_choose_backend():
    p = _panel(voice_backend_mode="disabled")
    p.start()
    assert BACKEND_DISABLED_MESSAGE in p._status_label.text()


def test_panel_lan_unreachable_message_on_start():
    # LAN mode configured but URL missing -> LAN setup message, no crash.
    p = _panel(voice_backend_mode="lan_server", voice_lan_base_url="")
    p.start()
    assert LAN_SETUP_MESSAGE in p._status_label.text()


def test_panel_lan_public_url_blocked_message():
    p = _panel(voice_backend_mode="lan_server",
               voice_lan_base_url="https://example.com")
    p.start()
    assert LAN_PUBLIC_URL_MESSAGE in p._status_label.text()


def test_panel_lan_row_visible_only_in_lan_mode():
    p = _panel(voice_backend_mode="lan_server",
               voice_lan_base_url="http://192.168.1.50:8000")
    assert p._lan_check_btn.isHidden() is False
    p2 = _panel(voice_backend_mode="local_process")
    assert p2._lan_check_btn.isHidden() is True


def test_switching_backend_mode_while_recording_stops_session():
    # §3: changing backend mode mid-session must stop the active recorder (the
    # old backend must not keep recording after the switch).
    p = _panel(voice_backend_mode="mock")
    p.start()
    rec = p._controller._recorder
    assert rec.is_recording
    idx = next(i for i in range(p._backend_combo.count())
               if p._backend_combo.itemData(i) == "local_process")
    p._backend_combo.setCurrentIndex(idx)
    assert not rec.is_recording                    # old session stopped safely
    assert p._status == VoiceStatus.OFF
    assert p._test_saved.get("voice_backend_mode") == "local_process"


def test_voice_package_uses_no_temp_files():
    # Segments are wrapped as in-memory WAV (BytesIO) — no temp-file litter.
    # Phase 8 exception: transcriber.py's whisper.cpp backend must hand the
    # binary a file; its temp WAV is always deleted (pinned by
    # test_voice_setup.py::test_whisper_cpp_transcriber_deletes_temp_audio).
    import os
    import re
    import logosforge.voice as vp
    pkg_dir = list(vp.__path__)[0]
    tmp_re = re.compile(r"^\s*(import|from)\s+tempfile\b", re.M)
    for name in os.listdir(pkg_dir):
        if name.endswith(".py") and name != "transcriber.py":
            src = open(os.path.join(pkg_dir, name), encoding="utf-8").read()
            assert not tmp_re.search(src), f"tempfile usage in {name}"


def test_no_hardcoded_machine_paths_in_voice_defaults():
    from logosforge.settings import DEFAULTS
    for key in ("voice_whisper_model_path", "voice_whisper_executable_path",
                "voice_lan_base_url", "voice_lan_auth_token"):
        assert DEFAULTS[key] == ""                 # user-configured, never baked in


def test_panel_creates_no_top_level_window():
    before = set(QApplication.topLevelWidgets())
    p = _panel(voice_backend_mode="lan_server",
               voice_lan_base_url="http://10.0.0.5:8000")
    p.toggle_panel()
    new_visible = [w for w in (set(QApplication.topLevelWidgets()) - before)
                   if w.isVisible() and w is not p.window()]
    assert new_visible == []
