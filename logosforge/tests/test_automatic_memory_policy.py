"""Automatic policy-governed memory pipeline (RAG-first).

Exercises the rich policy engine (`MemoryWriterPolicy.evaluate` → `PolicyResult`)
and the event→memory pipeline / tools: safe high-confidence durable memory
auto-saves as ACTIVE; uncertain/sensitive/conflicting/scope-ambiguous memory is
flagged for review; secrets/raw-audio are rejected; transient noise is ignored.
No provider calls, no cloud sync, no GitHub writes.
"""

from __future__ import annotations

import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge.assistant_arch.context_builder import AssistantContextBuilder
from logosforge.assistant_arch.tools import AssistantTools
from logosforge.memory_arch.candidates import (
    process_event_for_memory_candidates as run_pipeline,
)
from logosforge.memory_arch.policy import (
    MemoryWriterPolicy,
    PolicyDecision,
    PolicyResult,
)
from logosforge.memory_arch.review import MemoryCandidateReviewService
from logosforge.memory_arch.schema import (
    EventLogEntry,
    MemoryObject,
    MemoryScope,
    MemoryStatus,
    MemoryType,
)
from logosforge.memory_arch.store import InMemoryMemoryStore

P = MemoryWriterPolicy()


def c(scope, mtype, content, conf, status=MemoryStatus.PROPOSED, **kw):
    return MemoryObject(scope=scope, type=mtype, content=content,
                        confidence=conf, status=status, **kw)


def ev(content, **kw):
    return EventLogEntry(event_type="chat", content=content, **kw)


# 0. evaluate() returns a rich, auditable PolicyResult.
def test_evaluate_returns_rich_result():
    r = P.evaluate(c(MemoryScope.USER, MemoryType.PREFERENCE,
                     "prefers em dashes", 0.9, user_id="u1"))
    assert isinstance(r, PolicyResult)
    assert r.decision is PolicyDecision.AUTO_SAVE_ACTIVE
    assert r.auto_saved is True and r.requires_review is False
    assert r.suggested_status is MemoryStatus.ACTIVE
    assert r.confidence == 0.9 and r.risk_level == "low"


# 1-6. High-confidence durable safe memory of various types auto-saves active.
@pytest.mark.parametrize("scope,mtype,text,kw", [
    (MemoryScope.USER, MemoryType.PREFERENCE, "prefers em dashes", {"user_id": "u1"}),
    (MemoryScope.PROJECT, MemoryType.PROJECT_DECISION,
     "GN uses Act -> Page -> Scene -> Panel", {"project_id": "p1"}),
    (MemoryScope.ASSISTANT, MemoryType.WORKFLOW_RULE, "dual-push both refs", {}),
    (MemoryScope.ASSISTANT, MemoryType.ARCHITECTURE_DECISION,
     "desktop alpha first, cloud later", {}),
    (MemoryScope.ASSISTANT, MemoryType.RELEASE_BLOCKER_RULE,
     "GitHub is optional export, not the default backend", {}),
    (MemoryScope.USER, MemoryType.MODEL_PREFERENCE,
     "prefers local LM Studio backend", {"user_id": "u1"}),
])
def test_high_conf_auto_saves_active(scope, mtype, text, kw):
    assert P.decide(c(scope, mtype, text, 0.9, **kw)) \
        is PolicyDecision.AUTO_SAVE_ACTIVE


# 7. Speculative idea → speculative, never active.
def test_speculative_not_active():
    r = P.evaluate(c(MemoryScope.PROJECT, MemoryType.SPECULATIVE_IDEA,
                     "maybe a flashback", 0.3,
                     status=MemoryStatus.SPECULATIVE, project_id="p1"))
    assert r.decision is PolicyDecision.SAVE_SPECULATIVE
    assert r.suggested_status is MemoryStatus.SPECULATIVE and not r.auto_saved


# 8. Ambiguous/collaborative scope → review.
def test_workspace_scope_review():
    r = P.evaluate(c(MemoryScope.WORKSPACE, MemoryType.REPO_DECISION,
                     "team uses trunk-based dev", 0.9, workspace_id="ws1"))
    assert r.decision is PolicyDecision.REQUIRE_REVIEW and r.requires_review


# 9. Sensitive-looking content → review with sensitive_flags.
def test_sensitive_flagged():
    r = P.evaluate(c(MemoryScope.USER, MemoryType.PREFERENCE,
                     "remember my salary and medical diagnosis", 0.9,
                     user_id="u1"))
    assert r.decision is PolicyDecision.FLAG_SENSITIVE
    assert r.sensitive_flags and r.risk_level == "high"


# 10-12. Secrets / raw audio path / raw audio reference → reject.
@pytest.mark.parametrize("text", [
    "token sk-abcd1234efgh5678",
    "buffer saved to clip_01.wav",
    "recording at /home/u/audio/take3.mp3",
])
def test_unsafe_rejected(text):
    assert P.decide(c(MemoryScope.USER, MemoryType.OTHER, text, 0.9,
                      user_id="u1")) is PolicyDecision.REJECT


# 13. Contradiction with active memory → review with contradiction ids.
def test_contradiction_metadata():
    active = c(MemoryScope.PROJECT, MemoryType.CONTINUITY_FACT,
               "the gate is locked at night", 0.9, project_id="p1",
               status=MemoryStatus.ACTIVE)
    new = c(MemoryScope.PROJECT, MemoryType.CONTINUITY_FACT,
            "the gate is not locked at night", 0.9, project_id="p1")
    r = P.evaluate(new, existing=[active])
    assert r.decision is PolicyDecision.FLAG_CONTRADICTION
    assert active.id in r.contradiction_ids and r.requires_review


# 14. Low confidence → not auto-active.
def test_low_conf_not_auto():
    assert P.decide(c(MemoryScope.USER, MemoryType.PREFERENCE, "maybe", 0.2,
                      user_id="u1")) is not PolicyDecision.AUTO_SAVE_ACTIVE


# 15-16. Transient mood / random fragment → nothing written (unmarked).
def test_mood_and_fragment_ignored():
    store = InMemoryMemoryStore()
    out = run_pipeline(store, ev("ugh I'm tired. asdf qwerty zzz."))
    assert out.written == [] and store.search("") == []


# 17-18. Scope separation: project fact stays project; workflow stays assistant.
def test_scope_separation():
    store = InMemoryMemoryStore()
    run_pipeline(store, ev("For this project the hero is Ada. "
                           "The workflow is to dual-push.", project_id="p1"))
    proj = store.search("", scope=MemoryScope.PROJECT, project_id="p1")
    asst = store.search("", scope=MemoryScope.ASSISTANT)
    assert any("hero is Ada" in m.content for m in proj)
    assert not any("hero is Ada" in m.content for m in asst)
    assert any("dual-push" in m.content for m in asst)
    assert not any("dual-push" in m.content for m in proj)


# 19-22. Auto-saved active memory: source_event, auto_saved, policy_decision,
# and supersedable (non-destructive).
def test_auto_saved_active_properties():
    store = InMemoryMemoryStore()
    e = ev("Correction: the earlier plan was the wrong approach.",
           session_id="s1")
    m = run_pipeline(store, e).written[0]
    assert m.status is MemoryStatus.ACTIVE
    assert m.auto_saved is True
    assert m.source_event == e.id
    assert m.policy_decision == PolicyDecision.AUTO_SAVE_ACTIVE.value
    # supersedable / reversible (non-destructive).
    new = store.save_active(c(MemoryScope.ASSISTANT,
                              MemoryType.MISTAKE_CORRECTION,
                              "the corrected approach is X", 0.9))
    old, _new = MemoryCandidateReviewService(store).supersede(
        m.id, new.id, reason="revised")
    assert old.status is MemoryStatus.SUPERSEDED and store.get(m.id) is not None


# 23. Normal retrieval includes active auto-saved memory.
def test_retrieval_includes_active():
    store = InMemoryMemoryStore()
    run_pipeline(store, ev("Correction: the plan was the wrong call."))
    bundle = AssistantContextBuilder(store).build_context("plan", project_id="p1")
    assert any("Correction" in m.content for m in bundle.assistant_meta_memory)


# 24. Normal retrieval excludes non-active statuses.
@pytest.mark.parametrize("status", [
    MemoryStatus.REVIEW_REQUIRED, MemoryStatus.PROPOSED,
    MemoryStatus.SPECULATIVE, MemoryStatus.REJECTED,
    MemoryStatus.DEPRECATED, MemoryStatus.SUPERSEDED,
    MemoryStatus.CONTRADICTED,
])
def test_retrieval_excludes_non_active(status):
    store = InMemoryMemoryStore()
    mem = c(MemoryScope.PROJECT, MemoryType.PROJECT_DECISION, "x fact", 0.6,
            project_id="p1")
    mem.status = status
    store._memories[mem.id] = mem               # seed directly with the status
    bundle = AssistantContextBuilder(store).build_context("fact", project_id="p1")
    assert bundle.project_memory == []


# 25. Diagnostic retrieval surfaces excluded memory, labelled.
def test_diagnostic_labels_excluded():
    store = InMemoryMemoryStore()
    mem = c(MemoryScope.PROJECT, MemoryType.PROJECT_DECISION, "flagged fact",
            0.4, project_id="p1")
    mem.status = MemoryStatus.REVIEW_REQUIRED
    store._memories[mem.id] = mem
    diag = AssistantContextBuilder(store).build_context(
        "flagged", project_id="p1", diagnostic=True)
    assert any("flagged fact" in m.content for m in diag.project_memory)
    assert "status: review_required" in diag.to_prompt_text(diagnostic=True)


# 26. Docs reposition Memory Review as optional/exception-based.
def test_docs_reposition_review():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1] / "docs" / "architecture"
    ui = (root / "MEMORY_REVIEW_UI_SPEC.md").read_text(encoding="utf-8").lower()
    assert "optional" in ui and "exception" in ui
    arch = (root / "MEMORY_ARCHITECTURE.md").read_text(encoding="utf-8").lower()
    assert "remembers automatically" in arch


# 27-29. The pipeline + tools call no provider / cloud / GitHub.
def test_no_external_calls(monkeypatch):
    from logosforge import assistant
    from logosforge.memory_arch import github_export, sync

    def boom(*a, **k):
        raise AssertionError("no external call allowed")

    monkeypatch.setattr(assistant, "chat_completion", boom)
    monkeypatch.setattr(sync.MemorySyncService, "sync_memory_to_cloud", boom)
    monkeypatch.setattr(github_export.GitHubMemoryExportService,
                        "optional_sync_memory_to_github", boom)
    tools = AssistantTools()
    e = tools.log_event("chat", "Correction: wrong. I prefer em dashes.",
                        user_id="u1")
    tools.process_event_for_memory_candidates(e)
    tools.write_memory_candidate("dual-push both refs", MemoryType.WORKFLOW_RULE,
                                 MemoryScope.ASSISTANT, confidence=0.9)
    # No raise → the pipeline/write path called no provider / cloud / GitHub.


def test_sync_and_github_remain_disabled():
    tools = AssistantTools()
    assert tools.sync_memory_to_cloud()["status"] == "disabled"
    assert tools.optional_sync_memory_to_github()["status"] == "disabled"


# Extra: tools.write_memory_candidate auto-saves active for safe high-confidence.
def test_tools_write_auto_saves_active():
    tools = AssistantTools()
    m = tools.write_memory_candidate("prefers em dashes", MemoryType.PREFERENCE,
                                     MemoryScope.USER, confidence=0.9,
                                     user_id="u1")
    assert m.status is MemoryStatus.ACTIVE and m.auto_saved is True
    # secrets still rejected.
    with pytest.raises(ValueError):
        tools.write_memory_candidate("api_key: sk-deadbeef12345678",
                                     MemoryType.OTHER, MemoryScope.USER,
                                     user_id="u1")


# Extra: tools.write_memory_candidate flags low-confidence for review.
def test_tools_write_low_conf_review():
    tools = AssistantTools()
    m = tools.write_memory_candidate("vague idea", MemoryType.PREFERENCE,
                                     MemoryScope.USER, confidence=0.2,
                                     user_id="u1")
    assert m.status is MemoryStatus.REVIEW_REQUIRED and m.requires_review is True
