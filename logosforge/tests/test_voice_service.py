"""Tests for the headless VoiceRoomService — the canonical Dexter's Room API.

Pure Python, no Qt: a frontend (or the FastAPI layer) drives the service and
gets JSON-safe dicts back. Audio capture and the editor live in the frontend;
cursor commits come back as ``inserted_text`` and DB targets commit server-side.
"""

from __future__ import annotations

import json
import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.voice import glossary as vg
from logosforge.voice.service import VoiceRoomService
from logosforge.voice.types import VoiceSettings


def _mock_settings():
    # The "mock" backend transcribes without a model and never touches audio
    # hardware — ideal for headless API tests.
    return VoiceSettings(enabled=True, backend_mode="mock")


def _service(ai_complete=None, writing_mode="novel"):
    db = Database()
    proj = db.create_project("Voice API", narrative_engine=writing_mode)
    svc = VoiceRoomService(db, proj.id, writing_mode=writing_mode,
                           settings=_mock_settings(), ai_complete=ai_complete)
    return db, proj, svc


# 16-bit mono PCM helpers (silence threshold is int16 RMS 500).
_LOUD = b"\x00\x40" * 1600     # ~0.1s of amplitude 0x4000
_QUIET = b"\x10\x00" * 1600    # ~0.1s near-silence


def _is_json_safe(obj) -> bool:
    json.dumps(obj)            # raises if anything is not serializable
    return True


# ---------------------------------------------------------------------------
# Status + transcription
# ---------------------------------------------------------------------------

def test_backend_status_is_serializable_and_ready_for_mock():
    _db, _p, svc = _service()
    status = svc.backend_status()
    assert _is_json_safe(status)
    assert status["ready"] is True and "test" in status["message"].lower()


def test_transcribe_is_stateless_and_serializable():
    _db, _p, svc = _service()
    seg = svc.transcribe(_LOUD * 3)
    assert _is_json_safe(seg)
    assert "mock transcript" in seg["text"].lower()
    assert "audio_bytes" not in seg          # never on the wire
    assert svc.history() == []               # stateless: nothing recorded


def test_transcribe_segment_records_history():
    _db, _p, svc = _service()
    entry = svc.transcribe_segment(_LOUD * 3)
    assert entry is not None and "mock transcript" in entry["text"].lower()
    assert "audio_bytes" not in entry and entry["has_audio"] is True
    hist = svc.history()
    assert len(hist) == 1 and hist[0]["id"] == entry["id"]


def test_feed_chunk_segments_server_side():
    _db, _p, svc = _service()
    # Speech then >=900ms silence finalizes one segment via the core segmenter.
    finalized = None
    for c in [_LOUD] * 5 + [_QUIET] * 12:
        out = svc.feed_chunk(c)
        if out:
            finalized = out
    finalized = finalized or svc.flush()
    assert finalized is not None
    assert len(svc.history()) == 1


# ---------------------------------------------------------------------------
# History lifecycle
# ---------------------------------------------------------------------------

def test_history_edit_and_discard():
    _db, _p, svc = _service()
    entry = svc.transcribe_segment(_LOUD * 3)
    edited = svc.edit_segment(entry["id"], "edited text")
    assert edited["text"] == "edited text" and edited["status"] == "edited"
    assert svc.discard_segment(entry["id"]) is True


def test_retry_segment_returns_result():
    _db, _p, svc = _service()
    entry = svc.transcribe_segment(_LOUD * 3)
    res = svc.retry_segment(entry["id"])
    assert "ok" in res and "message" in res and _is_json_safe(res)


# ---------------------------------------------------------------------------
# Glossary
# ---------------------------------------------------------------------------

def test_glossary_suggest_and_apply():
    db, proj, svc = _service()
    vg.learn_correction(db, proj.id, "alise", "Alice")
    suggestions = svc.suggest_corrections("i saw alise today")
    assert _is_json_safe(suggestions)
    assert any(s["replacement_text"] == "Alice" for s in suggestions)
    ids = [s["id"] for s in suggestions]
    applied = svc.apply_corrections("i saw alise today", ids)
    assert "Alice" in applied["text"] and applied["applied_count"] >= 1


# ---------------------------------------------------------------------------
# Intents
# ---------------------------------------------------------------------------

def test_list_intents_and_cleanup_preview_apply():
    _db, _p, svc = _service()
    intents = svc.list_intents()
    assert _is_json_safe(intents)
    cleanup = next(i for i in intents if i["type"] == "cleanup_transcript")
    assert cleanup["enabled"] is True
    preview = svc.preview_intent(cleanup["id"], "hello world period")
    assert preview["can_apply"] is True and preview["after_text"]
    result = svc.apply_intent(preview["id"])
    assert result["applied"] is True
    assert result["cleaned_text"].endswith(".")    # "period" -> "."


def test_unknown_intent_preview_apply_is_graceful():
    _db, _p, svc = _service()
    res = svc.apply_intent("does-not-exist")
    assert res["applied"] is False and "unknown" in res["message"].lower()


# ---------------------------------------------------------------------------
# Billy (with and without a provider)
# ---------------------------------------------------------------------------

def test_billy_disabled_without_provider():
    _db, _p, svc = _service(ai_complete=None)
    ops = svc.billy_operations()
    assert _is_json_safe(ops)
    assert all(o["enabled"] is False for o in ops)   # no provider -> all blocked


def test_billy_ask_generates_chat_only_proposal_with_provider():
    _db, _p, svc = _service(ai_complete=lambda prompt: "Billy says hello back.")
    ops = {o["id"]: o for o in svc.billy_operations()}
    assert ops["billy_ask"]["enabled"] is True
    proposal = svc.generate_billy("billy_ask", "say hello", source_segment_ids=[])
    assert _is_json_safe(proposal)
    assert "hello" in proposal["response_text"].lower()
    assert proposal["proposal_type"] == "chat_only"


# ---------------------------------------------------------------------------
# Commit — cursor returns text; DB target commits server-side
# ---------------------------------------------------------------------------

def test_commit_targets_listed_and_serializable():
    _db, _p, svc = _service()
    targets = {t["id"]: t for t in svc.commit_targets({"has_active_editor": True})}
    assert _is_json_safe(list(targets.values()))
    assert "active_cursor" in targets and "note" in targets


def test_commit_to_cursor_returns_inserted_text():
    _db, _p, svc = _service()
    res = svc.commit("dictated line", "active_cursor",
                     {"has_active_editor": True})
    assert res["applied"] is True
    assert res["inserted_text"] == "dictated line"   # frontend inserts it


def test_commit_to_note_writes_server_side():
    db, proj, svc = _service()
    before = len(db.get_all_notes(proj.id))
    res = svc.commit("a captured note", "note", {})
    assert res["applied"] is True
    assert "inserted_text" not in res                # committed server-side
    assert len(db.get_all_notes(proj.id)) == before + 1


# ---------------------------------------------------------------------------
# Dependency injection + undo
# ---------------------------------------------------------------------------

def test_injected_history_is_shared():
    from logosforge.voice.history import VoiceTranscriptHistory
    db = Database()
    proj = db.create_project("Shared", narrative_engine="novel")
    hist = VoiceTranscriptHistory()
    svc = VoiceRoomService(db, proj.id, settings=_mock_settings(), history=hist)
    svc.transcribe_segment(_LOUD * 3)
    assert hist.segment_count == 1       # recorded into the injected history


def test_cursor_commit_undo_is_frontend_job():
    _db, _p, svc = _service()
    res = svc.commit("a line", "active_cursor", {"has_active_editor": True})
    assert res["applied"] is True and res["inserted_text"] == "a line"
    # No server-side editor -> the facade cannot undo a cursor insert.
    assert svc.can_undo()["can_undo"] is False


def test_full_loop_dictate_clean_commit_undo():
    """Drive the facade exactly as the React Dexter will: dictate -> clean ->
    commit to a Note (server-side) -> undo."""
    db, proj, svc = _service()
    # 1. dictate
    entry = svc.transcribe_segment(_LOUD * 3)
    assert entry is not None and entry["text"]
    # 2. clean (rule-based intent, no AI)
    cleanup = next(i for i in svc.list_intents()
                   if i["type"] == "cleanup_transcript")
    preview = svc.preview_intent(cleanup["id"], "the end period")
    applied = svc.apply_intent(preview["id"])
    cleaned = applied["cleaned_text"]
    assert cleaned.endswith(".")
    # 3. commit to a Note (server-side)
    before = len(db.get_all_notes(proj.id))
    res = svc.commit(cleaned, "note", {})
    assert res["applied"] is True
    assert len(db.get_all_notes(proj.id)) == before + 1
    # 4. undo (server-side) -> the Note is removed
    assert svc.can_undo()["can_undo"] is True
    undo = svc.undo_last()
    assert undo["undone"] is True
    assert len(db.get_all_notes(proj.id)) == before
    assert svc.can_undo()["can_undo"] is False     # nothing left to undo
