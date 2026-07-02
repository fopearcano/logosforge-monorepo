"""Local voice-to-script MVP (buffered dictation; local Whisper; manual commit).

Local-first and isolated: no cloud speech API, no audio leaves the machine. The
microphone and Whisper backends are optional + lazy-imported, so importing this
package is always safe even when voice is disabled or the backends are absent.
Feature-flagged OFF by default (``enable_voice_mode``). See ``docs/VOICE_MVP.md``.
"""

from __future__ import annotations

from logosforge.voice.audio_buffer import AudioBuffer
from logosforge.voice.editor_commit import EditorCommitTarget
from logosforge.voice.recorder import (
    MockRecorder,
    SoundDeviceRecorder,
    VoiceRecorder,
    build_recorder,
)
from logosforge.voice.lan_server import (
    LanWhisperTranscriber,
    is_private_host,
    validate_lan_url,
)
from logosforge.voice.session import VoiceSessionController
from logosforge.voice.silence_detector import SimpleSilenceDetector
from logosforge.voice.transcriber import (
    DisabledTranscriber,
    FasterWhisperTranscriber,
    MockTranscriber,
    Transcriber,
    build_transcriber,
)
from logosforge.voice.types import (
    BACKEND_DISABLED_MESSAGE,
    LAN_PUBLIC_URL_MESSAGE,
    LAN_SETUP_MESSAGE,
    PRIVACY_NOTE,
    SETUP_MESSAGE,
    TranscriptSegment,
    VoiceSettings,
    VoiceStatus,
)

__all__ = [
    "AudioBuffer", "SimpleSilenceDetector",
    "VoiceRecorder", "MockRecorder", "SoundDeviceRecorder", "build_recorder",
    "Transcriber", "MockTranscriber", "FasterWhisperTranscriber",
    "DisabledTranscriber", "LanWhisperTranscriber", "build_transcriber",
    "is_private_host", "validate_lan_url",
    "VoiceSessionController", "EditorCommitTarget",
    "VoiceStatus", "TranscriptSegment", "VoiceSettings",
    "SETUP_MESSAGE", "LAN_SETUP_MESSAGE", "LAN_PUBLIC_URL_MESSAGE",
    "BACKEND_DISABLED_MESSAGE", "PRIVACY_NOTE",
]


def load_voice_settings() -> VoiceSettings:
    """Load :class:`VoiceSettings` from the app settings store."""
    from logosforge.settings import get_manager
    return VoiceSettings.from_store(get_manager().get)
