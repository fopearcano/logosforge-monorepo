"""Controlled passive runtime integration of the automatic memory pipeline.

Proves the post-exchange capture path is safe and default-off: disabled → pure
no-op; enabled → a sanitized event runs the policy pipeline (safe memory
auto-saves active, risky goes to review); secrets/raw-audio are redacted and
never stored; scopes stay separate; no provider/cloud/GitHub calls; failures
degrade safely; default app behavior is unchanged.
"""

from __future__ import annotations

import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge import assistant
from logosforge.assistant_arch import auto_memory, passive_context
from logosforge.assistant_arch.tools import AssistantTools
from logosforge.memory_arch.schema import (
    MemoryObject,
    MemoryScope,
    MemoryStatus,
    MemoryType,
)
from logosforge.memory_arch.store import InMemoryMemoryStore


@pytest.fixture
def auto_on(monkeypatch):
    monkeypatch.setattr(auto_memory, "is_auto_memory_enabled", lambda: True)
    monkeypatch.setattr(auto_memory, "is_auto_memory_diagnostics_enabled",
                        lambda: False)


@pytest.fixture
def auto_on_diag(monkeypatch):
    monkeypatch.setattr(auto_memory, "is_auto_memory_enabled", lambda: True)
    monkeypatch.setattr(auto_memory, "is_auto_memory_diagnostics_enabled",
                        lambda: True)


@pytest.fixture
def auto_off(monkeypatch):
    monkeypatch.setattr(auto_memory, "is_auto_memory_enabled", lambda: False)


def _tools():
    return AssistantTools(store=InMemoryMemoryStore())


def _active(store, scope, mtype, content, **kw):
    return store.save_active(MemoryObject(scope=scope, type=mtype,
                                          content=content, **kw))


# 1. Flags disabled → no event, no memory.
def test_disabled_no_capture(auto_off):
    t = _tools()
    out = t.capture_interaction(
        assistant_response="Correction: the plan was the wrong call.")
    assert out["status"] == "disabled"
    assert t.store.list_events() == [] and t.store.search("") == []


# 2. Context flag on but auto-memory off → still no memory write.
def test_context_on_auto_off_no_write(monkeypatch):
    monkeypatch.setattr(passive_context, "is_enabled", lambda: True)
    monkeypatch.setattr(auto_memory, "is_auto_memory_enabled", lambda: False)
    t = _tools()
    out = t.capture_interaction(
        assistant_response="Correction: the plan was the wrong call.")
    assert out["status"] == "disabled" and t.store.search("") == []


# 3. Auto enabled → a (sanitized) event is created.
def test_enabled_creates_event(auto_on):
    t = _tools()
    t.capture_interaction(user_message="I prefer em dashes.",
                          user_id="u1", session_id="s1")
    events = t.store.list_events(session_id="s1")
    assert len(events) == 1
    assert events[0].event_type == "assistant_interaction"


# 4. Auto enabled → pipeline runs; a correction auto-saves active.
def test_enabled_correction_auto_saves_active(auto_on_diag):
    t = _tools()
    out = t.capture_interaction(
        assistant_response="Correction: the earlier plan was the wrong approach.")
    assert out["status"] == "ok" and out["auto_saved_count"] >= 1
    assert any(m.status is MemoryStatus.ACTIVE and m.auto_saved
               for m in t.store.search(""))


# 5-7. High-confidence safe memory auto-saves active at the correct scope
# (the explicit-confidence tool path used by the runtime).
def test_high_conf_preference_auto_saves(auto_on):
    t = _tools()
    m = t.write_memory_candidate("prefers em dashes", MemoryType.PREFERENCE,
                                 MemoryScope.USER, confidence=0.9, user_id="u1")
    assert m.status is MemoryStatus.ACTIVE and m.scope is MemoryScope.USER


def test_high_conf_workflow_auto_saves(auto_on):
    t = _tools()
    m = t.write_memory_candidate("dual-push both refs", MemoryType.WORKFLOW_RULE,
                                 MemoryScope.ASSISTANT, confidence=0.9)
    assert m.status is MemoryStatus.ACTIVE and m.scope is MemoryScope.ASSISTANT


def test_high_conf_project_decision_auto_saves(auto_on):
    t = _tools()
    m = t.write_memory_candidate("GN uses Act -> Page -> Scene -> Panel",
                                 MemoryType.PROJECT_DECISION,
                                 MemoryScope.PROJECT, confidence=0.9,
                                 project_id="p1")
    assert m.status is MemoryStatus.ACTIVE and m.project_id == "p1"


# 8. Speculative idea via capture → speculative, not active.
def test_capture_speculative(auto_on_diag):
    t = _tools()
    out = t.capture_interaction(
        user_message="Maybe the rival could secretly be her mentor.",
        project_id="p1")
    assert out["speculative_count"] >= 1
    assert not any(m.status is MemoryStatus.ACTIVE for m in t.store.search(""))


# 9. Ambiguous/collaborative scope → review_required (not active).
def test_workspace_scope_review(auto_on):
    t = _tools()
    m = t.write_memory_candidate("team uses trunk-based dev",
                                 MemoryType.REPO_DECISION,
                                 MemoryScope.WORKSPACE, confidence=0.9,
                                 user_id=None)
    # workspace candidate constructed with workspace_id via context not given →
    # policy flags it for review; never auto-active.
    assert m.status is not MemoryStatus.ACTIVE


# 10. Contradiction with active memory → review_required + metadata.
def test_capture_contradiction(auto_on_diag):
    t = _tools()
    _active(t.store, MemoryScope.PROJECT, MemoryType.CONTINUITY_FACT,
            "the gate is locked at night", project_id="p1")
    out = t.capture_interaction(
        user_message="For this project the gate is not locked at night.",
        project_id="p1")
    assert out["contradiction_count"] >= 1
    flagged = [m for m in t.store.search("gate", project_id="p1")
               if m.status is MemoryStatus.REVIEW_REQUIRED]
    assert flagged and flagged[0].contradicted_by


# 11-14. Secrets / raw audio paths are redacted in the event and never stored.
def test_secret_redacted(auto_on):
    t = _tools()
    t.capture_interaction(
        user_message="From now on store api_key: sk-deadbeef12345678.",
        user_id="u1", session_id="s1")
    ev = t.store.list_events(session_id="s1")[0]
    assert "sk-deadbeef" not in ev.content and "[redacted]" in ev.content
    assert not any("sk-deadbeef" in m.content for m in t.store.search(""))


def test_raw_audio_path_redacted(auto_on):
    t = _tools()
    t.capture_interaction(
        user_message="Save the recording to /tmp/take3.wav for me.",
        user_id="u1", session_id="s1")
    ev = t.store.list_events(session_id="s1")[0]
    assert "take3.wav" not in ev.content
    assert not any(".wav" in m.content for m in t.store.search(""))


def test_dexter_text_no_raw_audio(auto_on):
    t = _tools()
    t.capture_interaction(source="dexter_text",
                          user_message="transcript saved at clip_07.mp3",
                          project_id="p1", session_id="s1")
    ev = t.store.list_events(session_id="s1")[0]
    assert ev.source == "dexter_text" and "clip_07.mp3" not in ev.content
    assert not any(".mp3" in m.content for m in t.store.search(""))


# 15. Wrong-project memory is not written.
def test_no_wrong_project(auto_on):
    t = _tools()
    t.capture_interaction(
        user_message="For this project the hero is Ada North.",
        project_id="p1")
    assert all(m.project_id == "p1"
               for m in t.store.search("", scope=MemoryScope.PROJECT))


# 16-17. Scope separation through the capture pipeline.
def test_scope_separation_capture(auto_on):
    t = _tools()
    t.capture_interaction(
        user_message="For this project the hero is Ada. "
                     "The workflow is to dual-push.",
        project_id="p1")
    proj = t.store.search("", scope=MemoryScope.PROJECT, project_id="p1")
    asst = t.store.search("", scope=MemoryScope.ASSISTANT)
    assert any("hero is Ada" in m.content for m in proj)
    assert not any("hero is Ada" in m.content for m in asst)
    assert any("dual-push" in m.content for m in asst)
    assert not any("dual-push" in m.content for m in proj)


# 18. Missing memory store → no crash.
def test_missing_store_no_crash(auto_on, monkeypatch):
    monkeypatch.setattr(passive_context, "get_memory_store", lambda: None)
    out = auto_memory.capture_interaction(
        assistant_response="Correction: x was wrong.", store=None)
    assert out["status"] == "no_store"


# 19. Store failure → no crash.
def test_store_failure_no_crash(auto_on):
    class BadStore(InMemoryMemoryStore):
        def add_event(self, e):
            raise RuntimeError("boom")

    out = auto_memory.capture_interaction(
        assistant_response="Correction: x was wrong.", store=BadStore())
    assert out["status"] == "error"


# 20-21. Diagnostics summary: counts only, no secrets.
def test_diagnostics_counts_no_secrets(auto_on_diag):
    t = _tools()
    out = t.capture_interaction(
        user_message="From now on store api_key: sk-deadbeef12345678. "
                     "Correction: the plan was wrong.")
    for k in ("events_processed", "candidates_extracted", "auto_saved_count",
              "review_required_count", "speculative_count", "ignored_count",
              "rejected_count", "contradiction_count", "warnings"):
        assert k in out
    assert "sk-deadbeef" not in str(out)


# 22-24. No cloud sync / GitHub / provider call during capture.
def test_no_external_calls_on_capture(auto_on, monkeypatch):
    from logosforge.memory_arch import github_export, sync

    def boom(*a, **k):
        raise AssertionError("no external call allowed during capture")

    monkeypatch.setattr(assistant, "chat_completion", boom)
    monkeypatch.setattr(sync.MemorySyncService, "sync_memory_to_cloud", boom)
    monkeypatch.setattr(github_export.GitHubMemoryExportService,
                        "optional_sync_memory_to_github", boom)
    t = _tools()
    t.capture_interaction(
        user_message="Correction: wrong. For this project the hero is Ada.",
        project_id="p1")           # no raise → no provider/cloud/GitHub call


# 25. Default assistant prompt behavior unchanged (deterministic, no injection).
def test_default_prompt_unchanged(auto_off):
    base = assistant.build_messages("Do X", "scene text")
    assert assistant.build_messages("Do X", "scene text") == base
    assert "LogosForge Memory Context" not in base[1]["content"]


# 26. Flags default to False (opt-in).
def test_flags_default_false():
    from logosforge.settings import DEFAULTS
    assert DEFAULTS["assistant_auto_memory_enabled"] is False
    assert DEFAULTS["assistant_auto_memory_diagnostics_enabled"] is False
