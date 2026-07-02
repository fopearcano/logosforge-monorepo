"""Voice Setup & Diagnostics — local backend profiles and guardrails (Phase 8).

Makes local voice usable on real desktops: backend profile validation
(faster-whisper / whisper.cpp / mock / LAN), conservative performance
profiles, microphone diagnostics, a file-based local test transcription and
a copyable diagnostics summary. Everything is **local and explicit**:
nothing is installed or downloaded, no GPU is required (CPU-safe defaults),
invalid paths degrade to clear setup messages instead of crashes, and the
summary never contains API keys, provider secrets, transcript history or
raw audio.
"""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field

SETUP_REQUIRED_MESSAGE = ("Local Whisper is not configured. Open Voice "
                          "Setup to enable Voice Mode.")
LOCAL_ONLY_STATEMENT = ("Audio is processed locally. No cloud speech API is "
                        "used. Raw audio is never sent to Billy or AI "
                        "providers.")

# Backend ids selectable in Voice Setup (one active backend at a time).
BACKENDS = (
    ("local_process", "faster-whisper (local PC)"),
    ("whisper_cpp", "whisper.cpp (local executable)"),
    ("lan_server", "Local LAN Whisper server"),
    ("mock", "Mock / Test (no audio — testing only)"),
)

# Status ids (§2.B).
ST_NOT_CONFIGURED = "not_configured"
ST_READY = "ready"
ST_MISSING_DEPENDENCY = "missing_dependency"
ST_MISSING_EXECUTABLE = "missing_executable"
ST_MISSING_MODEL = "missing_model"
ST_ERROR = "error"
ST_DISABLED = "disabled"

# Conservative performance profiles (§4): map to settings the pipeline
# actually consumes (segmentation pace + beam size where the backend
# supports it). CPU-safe; no GPU assumed; no model downloads.
PERFORMANCE_PROFILES = {
    "fast_draft": {
        "label": "Fast draft",
        "voice_silence_ms": 600,
        "voice_max_segment_seconds": 12,
        "voice_beam_size": 1,
        "note": "Shorter segments, quickest feedback, lower accuracy.",
    },
    "balanced": {
        "label": "Balanced",
        "voice_silence_ms": 900,
        "voice_max_segment_seconds": 25,
        "voice_beam_size": 0,            # backend default
        "note": "The Alpha recommendation.",
    },
    "accurate": {
        "label": "Accurate",
        "voice_silence_ms": 1200,
        "voice_max_segment_seconds": 40,
        "voice_beam_size": 5,
        "note": "Longer segments and wider beam — latency may increase.",
    },
    "custom": {
        "label": "Custom",
        "note": "Your own silence/segment/beam values (edited in Setup).",
    },
}

def _language_choices() -> tuple:
    """("auto", "Auto detect") first, then every Whisper language sorted by
    display name. Stored by CODE; shown as "Name (code)"."""
    from logosforge.voice.types import WHISPER_LANGUAGES
    rest = sorted(((code, name) for code, name in WHISPER_LANGUAGES.items()
                   if code != "auto"), key=lambda cn: cn[1])
    return (("auto", WHISPER_LANGUAGES["auto"]),) + tuple(rest)


LANGUAGES = _language_choices()


@dataclass
class VoiceBackendProfile:
    """The validated state of the selected backend (read-only check)."""

    backend_id: str = ""
    label: str = ""
    enabled: bool = False
    status: str = ST_NOT_CONFIGURED
    message: str = ""
    model_path: str = ""
    executable_path: str = ""
    language: str = "auto"
    device: str = "auto"
    compute_type: str = ""
    sample_rate: int = 16000
    beam_size: int = 0
    performance_profile: str = "balanced"
    notes: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.status == ST_READY


def apply_performance_profile(settings_set, profile_id: str) -> bool:
    """Write a profile's concrete values into the settings store. ``custom``
    leaves the current values untouched (they are edited directly)."""
    profile = PERFORMANCE_PROFILES.get(profile_id)
    if profile is None:
        return False
    settings_set("voice_performance_profile", profile_id)
    if profile_id == "custom":
        return True
    for key in ("voice_silence_ms", "voice_max_segment_seconds",
                "voice_beam_size"):
        settings_set(key, profile[key])
    return True


# --------------------------------------------------------------------------
# Backend checks (read-only; never install, never download, never mutate)
# --------------------------------------------------------------------------

def check_faster_whisper(settings) -> tuple[str, str]:
    try:
        import faster_whisper  # noqa: F401 — availability probe only
    except Exception:
        return (ST_MISSING_DEPENDENCY,
                "faster-whisper is not installed "
                "(pip install faster-whisper).")
    model = (settings.model_path or "").strip()
    if not model:
        return ST_MISSING_MODEL, "Local Whisper model path is not set."
    if not os.path.exists(model):
        return ST_MISSING_MODEL, "Model not found at the configured path."
    return ST_READY, "faster-whisper ready."


def check_whisper_cpp(settings) -> tuple[str, str]:
    exe = (settings.executable_path or "").strip()
    if not exe:
        return (ST_MISSING_EXECUTABLE,
                "whisper.cpp executable path is not set.")
    if not os.path.isfile(exe):
        return (ST_MISSING_EXECUTABLE,
                "whisper.cpp executable not found at the set path.")
    if not os.access(exe, os.X_OK):
        return ST_ERROR, "whisper.cpp executable is not runnable."
    model = (settings.model_path or "").strip()
    if not model:
        return ST_MISSING_MODEL, "whisper.cpp model path is not set."
    if not os.path.exists(model):
        return ST_MISSING_MODEL, "Model not found at the configured path."
    return ST_READY, "whisper.cpp ready."


def probe_whisper_cpp(executable_path: str) -> tuple[bool, str]:
    """Optional safe probe: run ``<exe> --help`` with a short timeout."""
    import subprocess
    try:
        result = subprocess.run([executable_path, "--help"],
                                capture_output=True, text=True, timeout=5)
        return True, f"executable responded (exit {result.returncode})"
    except Exception as exc:
        return False, f"executable probe failed: {exc}"


def check_lan_server(settings) -> tuple[str, str]:
    if not (settings.lan_base_url or "").strip():
        return ST_NOT_CONFIGURED, "LAN Whisper server URL is not set."
    from logosforge.voice.lan_server import LanWhisperTranscriber
    ok, msg = LanWhisperTranscriber(settings).availability()
    return (ST_READY, msg) if ok else (ST_ERROR, msg)


def build_backend_profile(settings) -> VoiceBackendProfile:
    """Validate the SELECTED backend. Read-only; never mutates anything."""
    mode = settings.resolved_backend_mode()
    labels = dict(BACKENDS)
    profile = VoiceBackendProfile(
        backend_id=mode, label=labels.get(mode, mode),
        enabled=bool(settings.enabled),
        model_path=settings.model_path or "",
        executable_path=settings.executable_path or "",
        language=(settings.effective_language()
                  if hasattr(settings, "effective_language")
                  else settings.language) or "auto",
        device=getattr(settings, "local_device", "auto") or "auto",
        compute_type=getattr(settings, "local_compute_type", "") or "",
        sample_rate=int(settings.sample_rate or 16000),
        beam_size=int(getattr(settings, "beam_size", 0) or 0),
        performance_profile=getattr(settings, "performance_profile",
                                    "balanced") or "balanced",
    )
    if not settings.enabled:
        profile.status, profile.message = (
            ST_DISABLED, "Voice Mode is off — enable it in Voice Setup.")
        return profile
    if mode == "disabled":
        profile.status, profile.message = (
            ST_NOT_CONFIGURED,
            "Voice backend is set to Disabled. Pick a backend in Voice "
            "Setup.")
    elif mode == "mock":
        profile.status, profile.message = (
            ST_READY, "Mock/Test backend (no audio — testing only).")
        profile.notes.append("Not a production backend.")
    elif mode == "local_process":
        profile.status, profile.message = check_faster_whisper(settings)
    elif mode == "whisper_cpp":
        profile.status, profile.message = check_whisper_cpp(settings)
    elif mode == "lan_server":
        profile.status, profile.message = check_lan_server(settings)
    else:
        profile.status, profile.message = (ST_ERROR,
                                           f"Unknown backend “{mode}”.")
    return profile


# --------------------------------------------------------------------------
# Microphone diagnostics (§5) — safe, nothing saved, nothing sent
# --------------------------------------------------------------------------

def microphone_diagnostics(settings) -> tuple[bool, str]:
    """Availability check via the recorder abstraction. No audio is kept."""
    try:
        from logosforge.voice.recorder import build_recorder
        recorder = build_recorder(settings)
        ok, msg = recorder.availability()
        return bool(ok), msg or ("Microphone available." if ok
                                 else "Microphone unavailable.")
    except Exception as exc:
        return False, f"Microphone check failed: {exc}"


# --------------------------------------------------------------------------
# Test transcription (§6) — local only; never committed; never retained
# --------------------------------------------------------------------------

def load_wav_pcm(wav_path: str) -> tuple[bytes, int]:
    """Read a mono/stereo 16-bit WAV into mono PCM + sample rate."""
    import wave
    with wave.open(wav_path, "rb") as wav:
        rate = wav.getframerate()
        channels = wav.getnchannels()
        frames = wav.readframes(wav.getnframes())
    if channels == 2:                     # cheap downmix: take left channel
        frames = b"".join(frames[i:i + 2]
                          for i in range(0, len(frames), 4))
    return frames, rate


def run_test_transcription(settings, *, wav_path: str = "",
                           pcm: bytes | None = None,
                           sample_rate: int = 16000) -> tuple[bool, str]:
    """One local test transcription for Voice Setup. The result is shown in
    the setup panel only — never committed, never sent to Billy/AI; any
    file audio is read locally and not retained."""
    profile = build_backend_profile(settings)
    if not profile.ready:
        return False, profile.message or SETUP_REQUIRED_MESSAGE
    if profile.backend_id == "mock":
        from logosforge.voice.transcriber import MockTranscriber
        seg = MockTranscriber().transcribe(b"\x00\x00" * sample_rate,
                                           sample_rate=sample_rate)
        return True, seg.text
    if pcm is None:
        if not wav_path:
            return False, ("Pick a short local WAV file to test "
                           "transcription (no audio is kept).")
        try:
            pcm, sample_rate = load_wav_pcm(wav_path)
        except Exception as exc:
            return False, f"Could not read WAV file: {exc}"
    from logosforge.voice.transcriber import build_transcriber
    transcriber = build_transcriber(settings)
    seg = transcriber.transcribe(pcm, sample_rate=sample_rate,
                                 language=(settings.effective_language()
                                           if hasattr(settings, "effective_language")
                                           else settings.language) or None)
    if seg.error:
        return False, seg.error
    if seg.is_empty():
        return False, "Transcription produced no text."
    return True, seg.text


# --------------------------------------------------------------------------
# Diagnostics summary (§7) — copyable; no secrets, no transcripts
# --------------------------------------------------------------------------

def diagnostics_summary(settings, *, last_error: str = "") -> str:
    profile = build_backend_profile(settings)
    mic_ok, mic_msg = microphone_diagnostics(settings)
    try:
        from logosforge import __version__ as app_version
    except Exception:
        app_version = "unknown"
    lines = [
        "LogosForge Voice diagnostics",
        f"app version: {app_version}",
        f"platform: {platform.system()} {platform.release()}",
        f"voice enabled: {bool(settings.enabled)}",
        f"backend: {profile.label} ({profile.backend_id})",
        f"backend status: {profile.status} — {profile.message}",
        f"model path configured: "
        f"{'yes' if (settings.model_path or '').strip() else 'no'}",
        f"executable path configured: "
        f"{'yes' if (settings.executable_path or '').strip() else 'no'}",
        f"microphone: {'available' if mic_ok else 'unavailable'} "
        f"— {mic_msg}",
        f"language: "
        f"{(settings.effective_language() if hasattr(settings, 'effective_language') else settings.language) or 'auto'}"
        f" (mode: {settings.resolved_language_mode() if hasattr(settings, 'resolved_language_mode') else 'explicit'})",
        f"performance profile: {profile.performance_profile}",
        f"segmentation: silence {settings.silence_ms} ms / max "
        f"{settings.max_segment_seconds} s / beam "
        f"{getattr(settings, 'beam_size', 0) or 'default'}",
        f"last error: {last_error or 'none'}",
        LOCAL_ONLY_STATEMENT,
    ]
    return "\n".join(lines)
