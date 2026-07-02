"""Direction correction — automatic policy-governed memory (RAG-first).

Enforces the corrected principle: **LogosForge remembers automatically when
confidence and policy allow it, and asks the user only when memory is uncertain,
sensitive, contradictory, or scope-ambiguous.** Safe high-confidence durable
memory auto-saves as ACTIVE; everything else is proposed / review_required /
speculative; secrets are rejected. No provider calls, no cloud sync, no GitHub.
"""

from __future__ import annotations

import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge.memory_arch.candidates import (
    process_event_for_memory_candidates as run_pipeline,
)
from logosforge.memory_arch.policy import MemoryWriterPolicy, PolicyDecision
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


def cand(scope, mtype, content, conf, status=MemoryStatus.PROPOSED, **kw):
    return MemoryObject(scope=scope, type=mtype, content=content,
                        confidence=conf, status=status, **kw)


def _event(content, **kw):
    return EventLogEntry(event_type="chat", content=content, **kw)


# 1-5. High-confidence durable memory of safe types → AUTO_SAVE_ACTIVE.
def test_decide_high_conf_preference_auto_saves():
    c = cand(MemoryScope.USER, MemoryType.PREFERENCE, "prefers em dashes",
             0.9, user_id="u1")
    assert P.decide(c) is PolicyDecision.AUTO_SAVE_ACTIVE


def test_decide_high_conf_project_decision_auto_saves():
    c = cand(MemoryScope.PROJECT, MemoryType.PROJECT_DECISION,
             "GN uses Act -> Page -> Scene -> Panel", 0.9, project_id="p1")
    assert P.decide(c) is PolicyDecision.AUTO_SAVE_ACTIVE


def test_decide_high_conf_workflow_rule_auto_saves():
    c = cand(MemoryScope.ASSISTANT, MemoryType.WORKFLOW_RULE,
             "dual-push both refs", 0.9)
    assert P.decide(c) is PolicyDecision.AUTO_SAVE_ACTIVE


def test_decide_high_conf_architecture_auto_saves():
    c = cand(MemoryScope.ASSISTANT, MemoryType.ARCHITECTURE_DECISION,
             "desktop alpha first, cloud later", 0.9)
    assert P.decide(c) is PolicyDecision.AUTO_SAVE_ACTIVE


def test_decide_high_conf_release_blocker_auto_saves():
    c = cand(MemoryScope.ASSISTANT, MemoryType.RELEASE_BLOCKER_RULE,
             "GitHub is optional export, not the default backend", 0.9)
    assert P.decide(c) is PolicyDecision.AUTO_SAVE_ACTIVE


# 6. Speculative idea → SAVE_SPECULATIVE (never auto-active).
def test_decide_speculative():
    c = cand(MemoryScope.PROJECT, MemoryType.SPECULATIVE_IDEA,
             "maybe the rival is her mentor", 0.3,
             status=MemoryStatus.SPECULATIVE, project_id="p1")
    assert P.decide(c) is PolicyDecision.SAVE_SPECULATIVE


# 7. Workspace/collaborative scope → review (affects collaborators).
def test_decide_workspace_requires_review():
    c = cand(MemoryScope.WORKSPACE, MemoryType.REPO_DECISION,
             "team uses trunk-based dev", 0.9, workspace_id="ws1")
    assert P.decide(c) is PolicyDecision.REQUIRE_REVIEW


# 8. Sensitive-looking content → FLAG_SENSITIVE (review), not auto-active.
def test_decide_sensitive_flagged():
    c = cand(MemoryScope.USER, MemoryType.PREFERENCE,
             "my password is hunter and my salary matters", 0.9, user_id="u1")
    assert P.decide(c) is PolicyDecision.FLAG_SENSITIVE


# 9-10. Hard secrets / raw audio → REJECT.
def test_decide_rejects_secret():
    c = cand(MemoryScope.USER, MemoryType.OTHER,
             "token sk-abcd1234efgh5678", 0.9, user_id="u1")
    assert P.decide(c) is PolicyDecision.REJECT


def test_decide_rejects_raw_audio():
    c = cand(MemoryScope.USER, MemoryType.OTHER,
             "buffer saved to clip_01.wav", 0.9, user_id="u1")
    assert P.decide(c) is PolicyDecision.REJECT


# 11. Conflict with ACTIVE memory → FLAG_CONTRADICTION.
def test_decide_contradiction_flagged():
    active = cand(MemoryScope.PROJECT, MemoryType.CONTINUITY_FACT,
                  "the gate is locked at night", 0.9, project_id="p1",
                  status=MemoryStatus.ACTIVE)
    new = cand(MemoryScope.PROJECT, MemoryType.CONTINUITY_FACT,
               "the gate is not locked at night", 0.9, project_id="p1")
    assert P.decide(new, existing=[active]) is PolicyDecision.FLAG_CONTRADICTION


# 12. Low confidence → review, never auto-active.
def test_decide_low_confidence_not_auto():
    c = cand(MemoryScope.USER, MemoryType.PREFERENCE, "maybe likes serif", 0.3,
             user_id="u1")
    d = P.decide(c)
    assert d is not PolicyDecision.AUTO_SAVE_ACTIVE
    assert d is PolicyDecision.REQUIRE_REVIEW


# 13. Exact duplicate of active memory → IGNORE.
def test_decide_duplicate_ignored():
    active = cand(MemoryScope.USER, MemoryType.PREFERENCE, "prefers em dashes",
                  0.9, user_id="u1", status=MemoryStatus.ACTIVE)
    dup = cand(MemoryScope.USER, MemoryType.PREFERENCE, "prefers em dashes",
               0.9, user_id="u1")
    assert P.decide(dup, existing=[active]) is PolicyDecision.IGNORE


# 14-15. Unmarked mood / random fragment → nothing extracted (auto-ignored).
def test_pipeline_ignores_mood_and_fragments():
    store = InMemoryMemoryStore()
    out = run_pipeline(store, _event("I'm so tired today, ugh. asdf qwer."))
    assert out.written == [] and store.search("") == []


# 16. Pipeline auto-saves a correction as ACTIVE, preserving source_event.
def test_pipeline_correction_auto_saves_active():
    store = InMemoryMemoryStore()
    ev = _event("Correction: the earlier plan was the wrong approach.",
                session_id="s1")
    out = run_pipeline(store, ev)
    assert len(out.written) == 1
    m = out.written[0]
    assert m.status is MemoryStatus.ACTIVE and m.auto_saved is True
    assert m.scope is MemoryScope.ASSISTANT
    assert m.source_event == ev.id
    assert m.policy_decision == PolicyDecision.AUTO_SAVE_ACTIVE.value


# 17. Medium-confidence marked decision → proposed (not auto-active).
def test_pipeline_medium_conf_is_proposed():
    store = InMemoryMemoryStore()
    out = run_pipeline(store, _event(
        "For this project the protagonist is Ada.", project_id="p1"))
    assert len(out.written) == 1
    assert out.written[0].status is MemoryStatus.PROPOSED


# 18. Auto-saved active memory is reversible/supersedable (non-destructive).
def test_auto_saved_active_is_reversible():
    store = InMemoryMemoryStore()
    ev = _event("Correction: that earlier assumption was wrong.")
    m = run_pipeline(store, ev).written[0]
    review = MemoryCandidateReviewService(store)
    out = review.reject(m.id, reason="user revised it")
    assert out.status is MemoryStatus.REJECTED
    assert store.get(m.id) is not None              # preserved, not deleted


# 19. Project fact stays project-scoped; assistant rule stays assistant-scoped.
def test_pipeline_scope_separation_preserved():
    store = InMemoryMemoryStore()
    run_pipeline(store, _event(
        "For this project the hero is Ada. The workflow is to dual-push.",
        project_id="p1"))
    proj = store.search("", scope=MemoryScope.PROJECT, project_id="p1")
    asst = store.search("", scope=MemoryScope.ASSISTANT)
    assert any("hero is Ada" in m.content for m in proj)
    assert not any("hero is Ada" in m.content for m in asst)
    assert any("dual-push" in m.content for m in asst)


# 20. Normal retrieval includes active auto-saved memory.
def test_retrieval_includes_auto_saved_active():
    from logosforge.assistant_arch.context_builder import (
        AssistantContextBuilder)
    store = InMemoryMemoryStore()
    run_pipeline(store, _event("Correction: the plan was the wrong call."))
    bundle = AssistantContextBuilder(store).build_context("plan", project_id="p1")
    assert any("Correction" in m.content for m in bundle.assistant_meta_memory)


# 21. Normal retrieval excludes review_required; diagnostic labels it.
def test_retrieval_excludes_review_required():
    from logosforge.assistant_arch.context_builder import (
        AssistantContextBuilder)
    store = InMemoryMemoryStore()
    store.write_candidate(cand(
        MemoryScope.PROJECT, MemoryType.PROJECT_DECISION, "needs a human",
        0.4, project_id="p1", status=MemoryStatus.REVIEW_REQUIRED))
    normal = AssistantContextBuilder(store).build_context("human", project_id="p1")
    assert normal.project_memory == []
    assert any("review_required" in e["reason"] for e in normal.excluded_memory)
    diag = AssistantContextBuilder(store).build_context(
        "human", project_id="p1", diagnostic=True)
    assert any("needs a human" in m.content for m in diag.project_memory)
    assert "status: review_required" in diag.to_prompt_text(diagnostic=True)


# 22. auto_saved + policy metadata persist through the local SQLite store.
def test_auto_saved_persists_local(tmp_path):
    from logosforge.memory_arch.local_store import LocalSQLiteMemoryStore
    path = str(tmp_path / "mem.sqlite3")
    store = LocalSQLiteMemoryStore(path)
    m = store.save_active(cand(
        MemoryScope.ASSISTANT, MemoryType.WORKFLOW_RULE, "dual-push", 0.9))
    store.close()
    store2 = LocalSQLiteMemoryStore(path)
    got = store2.get(m.id)
    assert got.status is MemoryStatus.ACTIVE and got.auto_saved is True


# 23. Docs assert the corrected, automatic-first principle.
def test_docs_state_automatic_first():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1] / "docs" / "architecture"
    arch = (root / "MEMORY_ARCHITECTURE.md").read_text(encoding="utf-8").lower()
    assert "remembers automatically" in arch
    assert "review" in arch and "exception" in arch


# 24. The pipeline calls no provider / cloud sync / GitHub.
def test_pipeline_no_external_calls(monkeypatch):
    from logosforge import assistant
    from logosforge.memory_arch import github_export, sync

    def boom(*a, **k):
        raise AssertionError("no external call allowed during memory pipeline")

    monkeypatch.setattr(assistant, "chat_completion", boom)
    monkeypatch.setattr(sync.MemorySyncService, "sync_memory_to_cloud", boom)
    monkeypatch.setattr(github_export.GitHubMemoryExportService,
                        "optional_sync_memory_to_github", boom)
    store = InMemoryMemoryStore()
    run_pipeline(store, _event(
        "Correction: wrong. For this project the hero is Ada.", project_id="p1"))
    # No raise → no provider/cloud/GitHub call happened.
