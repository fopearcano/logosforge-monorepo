"""Dexter's Room voice — headless STT over the API.

Wraps the proven ``logosforge.voice`` faster-whisper transcriber so a frontend
(the Pro Electron app) can POST captured PCM and get text back. The model +
device are configured via environment so the host app points the core at the
user's local model (nothing is bundled): ``LOGOSFORGE_VOICE_MODEL`` (a
faster-whisper model directory), ``LOGOSFORGE_VOICE_DEVICE`` (cpu|cuda),
``LOGOSFORGE_VOICE_COMPUTE`` (int8|float16|…), ``LOGOSFORGE_VOICE_CUDA_DIRS``
(os.pathsep-joined dirs added to the DLL path for GPU). Audio never leaves the
machine — this is a local endpoint.
"""

from __future__ import annotations

import base64
import os

from typing import Any

from fastapi import APIRouter, Depends

from logosforge.api import schemas
from logosforge.api.deps import get_db, get_project

router = APIRouter(tags=["voice"])

_TRANSCRIBER = None
_TRANSCRIBER_KEY: tuple[str, str, str, str] | None = None


def _config() -> tuple[str, str, str, str]:
    return (
        os.environ.get("LOGOSFORGE_VOICE_MODEL", ""),
        os.environ.get("LOGOSFORGE_VOICE_DEVICE", "cpu"),
        os.environ.get("LOGOSFORGE_VOICE_COMPUTE", "int8"),
        os.environ.get("LOGOSFORGE_VOICE_CUDA_DIRS", ""),
    )


def _get_transcriber():
    """Lazily build + cache a transcriber from the env config (model loads once)."""
    global _TRANSCRIBER, _TRANSCRIBER_KEY
    key = _config()
    if _TRANSCRIBER is not None and _TRANSCRIBER_KEY == key:
        return _TRANSCRIBER
    model, device, compute, cuda = key
    if not model:
        from logosforge.voice.transcriber import DisabledTranscriber
        _TRANSCRIBER = DisabledTranscriber()
        _TRANSCRIBER_KEY = key
        return _TRANSCRIBER
    if cuda:
        try:
            from logosforge.voice.cuda_paths import ensure_cuda_dll_path
            ensure_cuda_dll_path([d for d in cuda.split(os.pathsep) if d])
        except Exception:
            pass
    from logosforge.voice.transcriber import FasterWhisperTranscriber
    _TRANSCRIBER = FasterWhisperTranscriber(model_path=model, device=device, compute_type=compute)
    _TRANSCRIBER_KEY = key
    return _TRANSCRIBER


@router.get("/voice/status", response_model=schemas.VoiceStatusDTO)
def voice_status():
    """Is local voice available (faster-whisper installed + a model configured)?"""
    model, device, _compute, _cuda = _config()
    try:
        ok, msg = _get_transcriber().availability()
    except Exception as exc:  # a bad model path / missing CUDA shouldn't 500 the poll
        ok, msg = False, str(exc)
    return schemas.VoiceStatusDTO(available=ok, message=msg, model_configured=bool(model), device=device)


@router.post(
    "/projects/{project_id}/voice/transcribe",
    response_model=schemas.VoiceTranscriptDTO,
)
def voice_transcribe(body: schemas.VoiceTranscribeDTO, project=Depends(get_project)):
    """Stateless STT of one PCM segment (int16 mono LE, base64). Local only."""
    try:
        pcm = base64.b64decode(body.audio_base64)
    except Exception:
        return schemas.VoiceTranscriptDTO(error="invalid audio payload")
    try:
        seg = _get_transcriber().transcribe(pcm, sample_rate=body.sample_rate or 16000, language=body.language)
    except Exception as exc:
        return schemas.VoiceTranscriptDTO(error=str(exc))
    return schemas.VoiceTranscriptDTO(
        text=(seg.text or "").strip(),
        language=getattr(seg, "language", "") or "",
        error=seg.error or "",
    )


# ---------------------------------------------------------------------------
# Full Dexter's Room facade — the stateful VoiceRoomService over HTTP.
#
# The stateless /transcribe above is the raw STT capability. The endpoints below
# wrap the *whole* headless facade (history, Intent cleanup, ask/edit-with-Billy,
# commit targets incl. Note/PSYKE, and undo) so the Pro app is a faithful desktop
# of the Python Dexter's Room — not a reduced transcribe-only panel. One
# VoiceRoomService instance is cached per project (it owns the session
# transcript history + pending previews/proposals).
# ---------------------------------------------------------------------------

_SESSIONS: dict[int, Any] = {}


def _ai_complete():
    """A ``(prompt) -> text`` callable backed by the app's active provider — the
    same LM Studio / provider Billy uses (respects the ``ai_base_url`` setting)."""
    def _fn(prompt: str) -> str:
        try:
            from logosforge.assistant import chat_completion
            from logosforge.providers import build_active_provider
            text, _ = chat_completion(
                [{"role": "user", "content": prompt}],
                provider=build_active_provider(), use_cache=False)
            return text or ""
        except Exception:
            return ""
    return _fn


def _session(db, project):
    """Get-or-build the per-project VoiceRoomService (shared transcriber + LLM)."""
    pid = int(project.id)
    svc = _SESSIONS.get(pid)
    if svc is None:
        from logosforge.voice.service import VoiceRoomService
        mode = (getattr(project, "narrative_engine", "")
                or getattr(project, "writing_mode", "") or "novel")
        svc = VoiceRoomService(
            db=db, project_id=pid, writing_mode=mode,
            transcriber=_get_transcriber(), ai_complete=_ai_complete())
        _SESSIONS[pid] = svc
    return svc


@router.post("/projects/{project_id}/voice/transcribe-segment")
def voice_transcribe_segment(body: schemas.VoiceSegmentReqDTO,
                             db=Depends(get_db), project=Depends(get_project)):
    """Transcribe a finalized PCM segment AND record it in the session history
    (returns the history entry, or ``{empty:true}`` for a no-speech segment)."""
    try:
        pcm = base64.b64decode(body.audio_base64)
    except Exception:
        return {"error": "invalid audio payload"}
    try:
        entry = _session(db, project).transcribe_segment(pcm)
    except Exception as exc:
        return {"error": str(exc)}
    return entry or {"empty": True}


@router.get("/projects/{project_id}/voice/history")
def voice_history(db=Depends(get_db), project=Depends(get_project)):
    return {"entries": _session(db, project).history()}


@router.post("/projects/{project_id}/voice/intents")
def voice_intents(body: schemas.VoiceCtxReqDTO,
                  db=Depends(get_db), project=Depends(get_project)):
    """Available voice Intents (cleanup, etc.) for the current context."""
    return {"intents": _session(db, project).list_intents(body.ctx)}


@router.post("/projects/{project_id}/voice/intents/preview")
def voice_intent_preview(body: schemas.VoiceIntentPreviewReqDTO,
                         db=Depends(get_db), project=Depends(get_project)):
    return _session(db, project).preview_intent(
        body.intent_id, body.source_text, body.ctx,
        commit_target_id=body.commit_target_id,
        source_segment_ids=body.source_segment_ids or None)


@router.post("/projects/{project_id}/voice/intents/apply")
def voice_intent_apply(body: schemas.VoiceIntentApplyReqDTO,
                       db=Depends(get_db), project=Depends(get_project)):
    return _session(db, project).apply_intent(body.preview_id, body.ctx)


@router.post("/projects/{project_id}/voice/billy/operations")
def voice_billy_operations(body: schemas.VoiceCtxReqDTO,
                           db=Depends(get_db), project=Depends(get_project)):
    """Ask/edit-with-Billy operations available for the current context."""
    return {"operations": _session(db, project).billy_operations(body.ctx)}


@router.post("/projects/{project_id}/voice/billy/generate")
def voice_billy_generate(body: schemas.VoiceBillyGenReqDTO,
                         db=Depends(get_db), project=Depends(get_project)):
    return _session(db, project).generate_billy(
        body.operation, body.transcript_text, body.ctx,
        source_segment_ids=body.source_segment_ids or None)


@router.post("/projects/{project_id}/voice/billy/apply")
def voice_billy_apply(body: schemas.VoiceBillyApplyReqDTO,
                      db=Depends(get_db), project=Depends(get_project)):
    return _session(db, project).apply_billy(body.proposal_id, body.ctx)


@router.post("/projects/{project_id}/voice/commit-targets")
def voice_commit_targets(body: schemas.VoiceCtxReqDTO,
                         db=Depends(get_db), project=Depends(get_project)):
    """Where a transcript can be committed (editor / Note / PSYKE / GN field)."""
    return {"targets": _session(db, project).commit_targets(body.ctx)}


@router.post("/projects/{project_id}/voice/commit")
def voice_commit(body: schemas.VoiceCommitReqDTO,
                 db=Depends(get_db), project=Depends(get_project)):
    """Commit transcript text to a target. ``inserted_text`` in the reply means
    the frontend should insert it at the editor cursor; its absence means it was
    committed server-side (Note / PSYKE)."""
    return _session(db, project).commit(body.text, body.target_id, body.ctx)


@router.get("/projects/{project_id}/voice/can-undo")
def voice_can_undo(db=Depends(get_db), project=Depends(get_project)):
    return _session(db, project).can_undo()


@router.post("/projects/{project_id}/voice/undo")
def voice_undo(db=Depends(get_db), project=Depends(get_project)):
    return _session(db, project).undo_last()
