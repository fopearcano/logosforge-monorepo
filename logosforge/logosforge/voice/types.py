"""Local voice-to-script MVP — shared types and settings.

Pure data types for the local, buffered dictation subsystem. No Qt, no audio or
Whisper dependencies here — those are lazy-imported by the backend modules so the
app (and these types) stay importable everywhere, even when voice is off or the
optional local backends are not installed.

This is *near-live segmented dictation* with **local** transcription and **manual**
commit. It is not cloud realtime, not speech-to-speech, and does not classify or
auto-format transcripts. See ``docs/VOICE_MVP.md``.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class VoiceStatus(str, Enum):
    """Lifecycle of a voice dictation session (UI reflects these directly)."""

    DISABLED = "disabled"            # feature flag off, or backend not configured
    OFF = "off"                      # enabled + ready, not currently listening
    LISTENING = "listening"          # capturing audio
    PROCESSING = "processing"        # transcribing a finalized segment
    TRANSCRIPT_READY = "transcript_ready"
    ERROR = "error"


@dataclass
class TranscriptSegment:
    """One transcribed segment (Alpha: always treated as plain text).

    Commit metadata is filled by the Voice Commit Router when (and only when)
    the user explicitly commits — segments are never auto-committed. Audio is
    never stored on the segment.
    """

    text: str = ""
    is_final: bool = True
    language: str = ""
    duration_s: float = 0.0
    error: str = ""
    # -- identity / provenance (Phase 2) --
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=time.time)
    source: str = "local_whisper"
    confidence: float | None = None
    # -- explicit-commit tracking (Phase 2) --
    committed: bool = False
    committed_target: str = ""
    committed_at: float | None = None
    # -- retry support (Phase 3): the segment's local PCM, session-only.
    # Never written to disk, never sent anywhere; dropped on discard/clear.
    audio_bytes: bytes | None = field(default=None, repr=False)
    sample_rate: int = 16000
    # -- language metadata (Dexter's Room language update) --
    selected_language_code: str = ""     # what the user/setting asked for
    detected_language_code: str = ""     # what the backend reported, if any
    language_source: str = ""    # auto | user_selected | project_language
    #                            # | backend_detected
    # -- project coordination (multi-language infrastructure) --
    project_language_code: str = ""      # the project's writing language
    dexter_language_mode: str = ""       # auto | project | explicit

    def is_empty(self) -> bool:
        return not (self.text or "").strip()


@dataclass
class VoiceSettings:
    """Snapshot of the voice settings (loaded from the app settings store)."""

    enabled: bool = False
    # Backend mode: "disabled" | "mock" | "local_process" | "lan_server".
    # Empty = derive from the legacy ``backend`` field (back-compat for direct
    # construction: "mock" -> mock, anything else -> local_process).
    backend_mode: str = ""
    backend: str = "faster-whisper"     # local PC kind ("faster-whisper"|"mock")
    model_path: str = ""
    executable_path: str = ""
    beam_size: int = 0                # 0 = backend default (profiles may set)
    performance_profile: str = "balanced"
    local_device: str = "auto"
    local_compute_type: str = "int8"
    language: str = "auto"            # the EXPLICIT language selection
    # Transcription language mode: "project" (follow the project's writing
    # language — the default), "auto", or "explicit" (use ``language``).
    # "" infers for pre-existing installs: a concrete saved ``language``
    # means the user chose it (explicit); auto/empty follows the project.
    language_mode: str = ""
    # The active project's writing language, filled by the caller that
    # knows the project (the voice panel). "auto" when unknown.
    project_language_code: str = "auto"
    auto_commit: bool = False
    silence_ms: int = 900
    max_segment_seconds: int = 25
    overlap_ms: int = 0
    sample_rate: int = 16000          # Whisper-style mono 16 kHz
    channels: int = 1
    # LAN backend (trusted local-network Whisper server only).
    lan_base_url: str = ""
    lan_api_type: str = "openai_compatible"   # | "whisper_cpp" | "custom"
    lan_transcription_endpoint: str = ""
    lan_health_endpoint: str = ""
    lan_timeout_seconds: int = 60
    lan_auth_header_name: str = ""
    lan_auth_token: str = ""                  # never logged
    lan_allow_only_private_hosts: bool = True
    lan_max_audio_seconds: int = 60
    lan_max_payload_mb: int = 25

    def resolved_backend_mode(self) -> str:
        """The effective backend mode, with legacy-field back-compat."""
        mode = (self.backend_mode or "").strip().lower()
        if mode:
            return mode
        return "mock" if (self.backend or "").lower() == "mock" else "local_process"

    def resolved_language_mode(self) -> str:
        """auto | project | explicit — with back-compat inference: installs
        that saved a concrete language before the mode existed keep it."""
        mode = (self.language_mode or "").strip().lower()
        if mode in ("auto", "project", "explicit"):
            return mode
        return "explicit" if self.language not in ("", "auto") else "project"

    def effective_language(self) -> str:
        """The transcription language code the backend should receive.
        Invalid values fall back to auto (never crash, never leave the
        Whisper code domain)."""
        mode = self.resolved_language_mode()
        if mode == "auto":
            return "auto"
        if mode == "project":
            return normalize_language(self.project_language_code)
        return normalize_language(self.language)

    @classmethod
    def from_store(cls, get) -> "VoiceSettings":
        """Build from a ``get(key)`` accessor (e.g. ``settings.get_manager().get``)."""
        def _int(key, default):
            try:
                return int(get(key))
            except (TypeError, ValueError):
                return default
        return cls(
            enabled=bool(get("enable_voice_mode")),
            backend_mode=str(get("voice_backend_mode") or "disabled"),
            backend=str(get("voice_whisper_backend") or "faster-whisper"),
            model_path=str(get("voice_whisper_model_path") or ""),
            executable_path=str(get("voice_whisper_executable_path") or ""),
            beam_size=_int("voice_beam_size", 0),
            performance_profile=str(get("voice_performance_profile")
                                    or "balanced"),
            local_device=str(get("voice_local_device") or "auto"),
            local_compute_type=str(get("voice_local_compute_type") or "int8"),
            language=normalize_language(get("voice_language")),
            language_mode=str(get("voice_language_mode") or ""),
            auto_commit=bool(get("voice_auto_commit")),
            silence_ms=_int("voice_silence_ms", 900),
            max_segment_seconds=_int("voice_max_segment_seconds", 25),
            overlap_ms=_int("voice_overlap_ms", 0),
            lan_base_url=str(get("voice_lan_base_url") or ""),
            lan_api_type=str(get("voice_lan_api_type") or "openai_compatible"),
            lan_transcription_endpoint=str(
                get("voice_lan_transcription_endpoint") or ""),
            lan_health_endpoint=str(get("voice_lan_health_endpoint") or ""),
            lan_timeout_seconds=_int("voice_lan_timeout_seconds", 60),
            lan_auth_header_name=str(get("voice_lan_auth_header_name") or ""),
            lan_auth_token=str(get("voice_lan_auth_token") or ""),
            lan_allow_only_private_hosts=bool(
                get("voice_lan_allow_only_private_hosts")
                if get("voice_lan_allow_only_private_hosts") is not None else True),
            lan_max_audio_seconds=_int("voice_lan_max_audio_seconds", 60),
            lan_max_payload_mb=_int("voice_lan_max_payload_mb", 25),
        )



# Full OpenAI Whisper language list (code -> display name). "auto" first;
# stored BY CODE; display names are user-friendly. The single source of
# truth now lives in the central registry (logosforge.languages) shared
# with the Project Writing Language and grammar systems; these re-exports
# keep every existing voice import working unchanged.
from logosforge.languages import (  # noqa: E402  (re-export)
    LANGUAGE_ALIASES,
    WHISPER_LANGUAGES,
    normalize_language,
)


# Non-blocking setup messages (shown in the panel; the app stays usable).
SETUP_MESSAGE = (
    "Local Whisper is not configured. Voice mode is disabled until setup is "
    "complete."
)
LAN_SETUP_MESSAGE = (
    "Local LAN Whisper server is not reachable. Voice mode is disabled until "
    "setup is complete."
)
LAN_PUBLIC_URL_MESSAGE = (
    "LAN Whisper server must be a trusted local network address for this "
    "Alpha build."
)
BACKEND_DISABLED_MESSAGE = (
    "Voice backend is set to Disabled. Choose Local PC or Local LAN Server "
    "in the voice settings."
)
PRIVACY_NOTE = (
    "Dexter's Room uses local transcription. Audio is processed on this "
    "device. In LAN mode, audio is sent only to the configured local "
    "network Whisper server."
)
