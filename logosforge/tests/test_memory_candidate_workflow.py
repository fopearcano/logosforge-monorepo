"""Phase 4 — memory candidate workflow MVP.

Proves the candidate workflow is a safe, deterministic, local-only MVP:
extract → classify → propose → review (approve / reject / edit / supersede /
mark speculative / mark contradicted), a deterministic session summary, and a
heuristic contradiction surface. Invariants enforced throughout:

- only *marked* spans become candidates (raw chat is never auto-saved);
- candidates are written **proposed/speculative** only — never active;
- Project Memory and Assistant Meta-Memory stay separate by scope;
- secrets / raw-audio spans are dropped; scope/id integrity is honored;
- **no destructive delete** — rejected/superseded objects are preserved;
- no model call, no embeddings, no network, no DB created on import.
"""

from __future__ import annotations

import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge.memory_arch.candidates import (
    classify_span,
    extract_candidates,
    process_event_for_memory_candidates,
    summarize_session,
)
from logosforge.memory_arch.contradictions import contradicts
from logosforge.memory_arch.review import MemoryCandidateReviewService
from logosforge.memory_arch.schema import (
    EventLogEntry,
    MemoryObject,
    MemoryScope,
    MemoryStatus,
    MemoryType,
)
from logosforge.memory_arch.store import InMemoryMemoryStore


def _store():
    return InMemoryMemoryStore()


def _event(content, **kw):
    return EventLogEntry(event_type="chat", content=content, **kw)


# 1. The Phase-4 status exists and is additive (round-trips by value).
def test_rejected_status_exists():
    assert MemoryStatus.REJECTED.value == "rejected"
    assert MemoryStatus("rejected") is MemoryStatus.REJECTED


# 2-4. classify_span maps markers → (type, scope, confidence) per spec.
def test_classify_preference_marker():
    c = classify_span("I prefer em dashes over semicolons.")
    assert c.type is MemoryType.PREFERENCE
    assert c.scope is MemoryScope.USER and c.confidence == 0.6


def test_classify_project_decision_marker():
    c = classify_span("For this project, the protagonist is Ada.",
                      project_id="p1")
    assert c.type is MemoryType.PROJECT_DECISION
    assert c.scope is MemoryScope.PROJECT


def test_classify_correction_is_high_confidence_assistant():
    c = classify_span("Correction: the deadline is Friday.")
    assert c.type is MemoryType.MISTAKE_CORRECTION
    assert c.scope is MemoryScope.ASSISTANT and c.confidence == 0.9


# 5. Assistant-scope markers: workflow / architecture / deferred / blocker.
def test_classify_assistant_scope_markers():
    assert classify_span("The workflow is to dual-push.").type \
        is MemoryType.WORKFLOW_RULE
    assert classify_span("This is an architecture decision: use SQLite.").type \
        is MemoryType.ARCHITECTURE_DECISION
    assert classify_span("Defer that to a later phase.").type \
        is MemoryType.DEFERRED_FEATURE
    blocker = classify_span("This is a release blocker.")
    assert blocker.type is MemoryType.RELEASE_BLOCKER_RULE
    assert blocker.scope is MemoryScope.ASSISTANT and blocker.confidence == 0.9


# 6. Speculative → SPECULATIVE status; project scope iff project_id present.
def test_classify_speculative_status_and_scope():
    with_proj = classify_span("Maybe the rival is her mentor.", project_id="p1")
    assert with_proj.type is MemoryType.SPECULATIVE_IDEA
    assert with_proj.status is MemoryStatus.SPECULATIVE
    assert with_proj.scope is MemoryScope.PROJECT and with_proj.confidence == 0.3
    no_proj = classify_span("Maybe the rival is her mentor.")
    assert no_proj.scope is MemoryScope.ASSISTANT          # never silently dropped


# 7. Priority order: correction beats project_decision/preference in one span.
def test_classify_priority_order():
    c = classify_span("Correction: for this project we always use em dashes.",
                      project_id="p1")
    assert c.type is MemoryType.MISTAKE_CORRECTION         # highest priority wins


# 8. Unmarked text yields no classification — raw chat is not memory.
def test_classify_unmarked_returns_none():
    assert classify_span("Let's keep writing the next chapter.") is None
    assert classify_span("The weather is nice today.") is None


# 9. extract: only marked spans become candidates; chatter is ignored.
def test_extract_only_marked_spans():
    text = ("Let's keep going. I prefer em dashes. "
            "The weather is nice. For this project the hero is Ada.")
    res = extract_candidates(text, project_id="p1", user_id="u1")
    contents = [m.content for m in res.candidates]
    assert any("em dashes" in c for c in contents)
    assert any("hero is Ada" in c for c in contents)
    assert not any("weather" in c for c in contents)
    assert len(res.candidates) == 2


# 10. extract drops forbidden content (secrets / raw audio) with a reason.
def test_extract_drops_forbidden():
    res = extract_candidates("From now on use api_key: sk-deadbeef12345678.",
                             user_id="u1")
    assert res.candidates == []
    assert res.skipped and "forbidden" in res.skipped[0]["reason"]


# 11. extract skips project-scope span without project_id (warns, never misfiles).
def test_extract_skips_project_without_id():
    res = extract_candidates("For this project the hero is Ada.")  # no project_id
    assert res.candidates == []
    assert res.skipped and "project_id" in res.skipped[0]["reason"]
    assert res.warnings


# 12. extract skips user-scope span without user_id.
def test_extract_skips_user_without_id():
    res = extract_candidates("I prefer dark mode.")               # no user_id
    assert res.candidates == []
    assert res.skipped and "user_id" in res.skipped[0]["reason"]


# 13. extract: candidates carry proposed/speculative status only (never active).
def test_extract_status_is_candidate_only():
    res = extract_candidates(
        "I prefer em dashes. Maybe a flashback could work.",
        project_id="p1", user_id="u1")
    statuses = {m.status for m in res.candidates}
    assert statuses <= {MemoryStatus.PROPOSED, MemoryStatus.SPECULATIVE}
    assert MemoryStatus.ACTIVE not in statuses


# 14. Pipeline writes proposed/speculative candidates and returns their ids.
def test_pipeline_writes_candidates():
    store = _store()
    ev = _event("I prefer em dashes. For this project the hero is Ada.",
                project_id="p1", user_id="u1", session_id="s1")
    out = process_event_for_memory_candidates(store, ev)
    assert len(out.written) == 2
    assert out.written_ids and all(store.get(i) for i in out.written_ids)
    # everything landed as a candidate, nothing active.
    assert all(store.get(i).status in (MemoryStatus.PROPOSED,
                                       MemoryStatus.SPECULATIVE)
               for i in out.written_ids)
    # source_event links back to the event.
    assert all(store.get(i).source_event == ev.id for i in out.written_ids)


# 15. Pipeline honors Project↔Assistant separation by scope.
def test_pipeline_scope_separation():
    store = _store()
    ev = _event("For this project the hero is Ada. "
                "The workflow is to dual-push.",
                project_id="p1", user_id="u1")
    process_event_for_memory_candidates(store, ev)
    proj = store.search("", scope=MemoryScope.PROJECT, project_id="p1")
    asst = store.search("", scope=MemoryScope.ASSISTANT)
    assert any("hero is Ada" in m.content for m in proj)
    assert any("dual-push" in m.content for m in asst)
    # no project fiction fact leaked into assistant scope.
    assert not any("hero is Ada" in m.content for m in asst)


# 16. Pipeline on empty content writes nothing and warns.
def test_pipeline_empty_content():
    store = _store()
    out = process_event_for_memory_candidates(store, _event("   "))
    assert out.written == [] and out.warnings


# 17. Pipeline never auto-saves raw chat as fact (no markers → nothing).
def test_pipeline_ignores_raw_chat():
    store = _store()
    out = process_event_for_memory_candidates(
        store, _event("Hi there. How is the chapter going? Looks good."))
    assert out.written == []
    assert store.search("") == []


# 18. Pipeline surfaces a contradiction as a non-blocking warning (still writes).
def test_pipeline_contradiction_warns_but_writes():
    store = _store()
    store.write_candidate(MemoryObject(
        scope=MemoryScope.PROJECT, type=MemoryType.PROJECT_DECISION,
        content="For this project the gate is locked.", project_id="p1"))
    ev = _event("For this project the gate is not locked.", project_id="p1")
    out = process_event_for_memory_candidates(store, ev)
    assert len(out.written) == 1                       # write not blocked
    assert any("contradiction" in w for w in out.warnings)


# 19. summarize_session is deterministic and writes ONE proposed summary.
def test_summarize_session_writes_proposed():
    store = _store()
    store.add_event(_event("I prefer em dashes.", session_id="s1"))
    store.add_event(_event("For this project the hero is Ada.", session_id="s1"))
    out = summarize_session(store, "s1")
    assert out["status"] == "proposed"
    summary = store.get(out["candidate_id"])
    assert summary.status is MemoryStatus.PROPOSED
    assert summary.type is MemoryType.SESSION_SUMMARY
    assert summary.scope is MemoryScope.ASSISTANT         # meta-memory, not project
    assert "2 events" in summary.content
    # deterministic: same events → same summary text.
    assert summarize_session(store, "s1")["summary"] == out["summary"]


# 20. summarize_session on an empty session writes nothing.
def test_summarize_empty_session():
    store = _store()
    out = summarize_session(store, "nope")
    assert out["status"] == "empty" and out["candidate_id"] is None
    assert store.search("") == []


# 21. summarize_session redacts forbidden content from excerpts.
def test_summarize_redacts_secrets():
    store = _store()
    store.add_event(_event("api_key: sk-deadbeef12345678", session_id="s1"))
    out = summarize_session(store, "s1")
    assert "sk-deadbeef" not in out["summary"]
    assert "[redacted]" in out["summary"]


# 22. Review list shows proposed + speculative candidates.
def test_review_list_candidates():
    store = _store()
    review = MemoryCandidateReviewService(store)
    store.write_candidate(MemoryObject(
        scope=MemoryScope.USER, type=MemoryType.PREFERENCE,
        content="prefers em dashes", user_id="u1"))
    store.write_candidate(MemoryObject(
        scope=MemoryScope.PROJECT, type=MemoryType.SPECULATIVE_IDEA,
        content="maybe a flashback", project_id="p1",
        status=MemoryStatus.SPECULATIVE))
    assert len(review.list_candidates()) == 2
    assert len(review.list_candidates(scope=MemoryScope.USER)) == 1


# 23. Review approve → active.
def test_review_approve():
    store = _store()
    review = MemoryCandidateReviewService(store)
    mem = store.write_candidate(MemoryObject(
        scope=MemoryScope.ASSISTANT, type=MemoryType.WORKFLOW_RULE,
        content="dual-push both refs"))
    out = review.approve(mem.id)
    assert out.status is MemoryStatus.ACTIVE


# 24. Review reject → rejected, requires a reason, preserves the object.
def test_review_reject_is_non_destructive():
    store = _store()
    review = MemoryCandidateReviewService(store)
    mem = store.write_candidate(MemoryObject(
        scope=MemoryScope.USER, type=MemoryType.PREFERENCE,
        content="prefers tabs", user_id="u1"))
    with pytest.raises(ValueError):
        review.reject(mem.id, reason="")               # reason required
    out = review.reject(mem.id, reason="user changed their mind")
    assert out.status is MemoryStatus.REJECTED
    assert store.get(mem.id) is not None               # kept, not deleted


# 25. Review edit revises content, refuses status changes, requires a reason.
def test_review_edit_guards_status():
    store = _store()
    review = MemoryCandidateReviewService(store)
    mem = store.write_candidate(MemoryObject(
        scope=MemoryScope.USER, type=MemoryType.PREFERENCE,
        content="old", user_id="u1"))
    out = review.edit(mem.id, {"content": "new", "tags": ["t"]},
                      reason="clarified")
    assert out.content == "new" and out.tags == ["t"]
    with pytest.raises(ValueError):
        review.edit(mem.id, {"status": MemoryStatus.ACTIVE}, reason="sneaky")


# 26. Review supersede preserves + links the old object.
def test_review_supersede_preserves():
    store = _store()
    review = MemoryCandidateReviewService(store)
    old = store.write_candidate(MemoryObject(
        scope=MemoryScope.ASSISTANT, type=MemoryType.ARCHITECTURE_DECISION,
        content="tree outline"))
    new = store.write_candidate(MemoryObject(
        scope=MemoryScope.ASSISTANT, type=MemoryType.ARCHITECTURE_DECISION,
        content="block/card outline"))
    o, n = review.supersede(old.id, new.id, reason="block UX replaces tree")
    assert o.status is MemoryStatus.SUPERSEDED
    assert store.get(old.id) is not None and n.supersedes == old.id


# 27. Review mark_speculative / mark_contradicted are auditable, non-destructive.
def test_review_mark_transitions():
    store = _store()
    review = MemoryCandidateReviewService(store)
    mem = store.write_candidate(MemoryObject(
        scope=MemoryScope.ASSISTANT, type=MemoryType.ASSISTANT_RULE,
        content="some rule"))
    spec = review.mark_speculative(mem.id, reason="not sure yet")
    assert spec.status is MemoryStatus.SPECULATIVE
    contra = review.mark_contradicted(mem.id, reason="conflicts with X",
                                      contradicted_by=["other-id"])
    assert contra.status is MemoryStatus.CONTRADICTED
    assert contra.contradicted_by == ["other-id"]
    assert store.get(mem.id) is not None               # preserved


# 28. contradicts(): opposing polarity + overlap → reason; same polarity → None.
def test_contradicts_heuristic():
    a = MemoryObject(scope=MemoryScope.PROJECT, type=MemoryType.CONTINUITY_FACT,
                     content="The gate is locked at night.", project_id="p1")
    b = MemoryObject(scope=MemoryScope.PROJECT, type=MemoryType.CONTINUITY_FACT,
                     content="The gate is not locked at night.", project_id="p1")
    same = MemoryObject(scope=MemoryScope.PROJECT,
                        type=MemoryType.CONTINUITY_FACT,
                        content="The gate is locked tightly at night.",
                        project_id="p1")
    assert contradicts(a, b) is not None
    assert contradicts(a, same) is None
    # different scope never contradicts.
    c = MemoryObject(scope=MemoryScope.ASSISTANT,
                     type=MemoryType.ASSISTANT_RULE,
                     content="The gate is not locked at night.")
    assert contradicts(a, c) is None


# 29. review.contradictions_for surfaces conflicts; tools return metadata dicts.
def test_contradiction_surface_via_tools():
    from logosforge.assistant_arch.tools import AssistantTools
    tools = AssistantTools()
    tools.write_memory_candidate("The gate is locked at night.",
                                 MemoryType.PROJECT_DECISION,
                                 MemoryScope.PROJECT, project_id="p1")
    tools.write_memory_candidate("The gate is not locked at night.",
                                 MemoryType.PROJECT_DECISION,
                                 MemoryScope.PROJECT, project_id="p1")
    hits = tools.find_contradictions("gate", project_id="p1")
    assert hits and hits[0]["kind"] == "heuristic"
    assert len(hits[0]["memories"]) == 2 and hits[0]["reason"]


# 30. Tools end-to-end: process event → list → reject; nothing becomes active.
def test_tools_candidate_roundtrip():
    from logosforge.assistant_arch.tools import AssistantTools
    tools = AssistantTools()
    ev = tools.log_event("chat", "I prefer em dashes.",
                         user_id="u1", session_id="s1")
    out = tools.process_event_for_memory_candidates(ev)
    assert out.written and out.written[0].status is MemoryStatus.PROPOSED
    listed = tools.list_memory_candidates(scope=MemoryScope.USER)
    assert listed
    rejected = tools.reject_memory_candidate(listed[0].id, reason="dupe")
    assert rejected.status is MemoryStatus.REJECTED


# 31. Import safety: importing the workflow modules creates no DB / no network.
def test_import_safety_no_side_effects():
    import importlib
    for mod in ("logosforge.memory_arch.candidates",
                "logosforge.memory_arch.review",
                "logosforge.memory_arch.contradictions"):
        importlib.import_module(mod)
    # The placeholder extractor is untouched (still returns empty).
    from logosforge.assistant_arch.context_builder import (
        MemoryCandidateExtractor)
    assert MemoryCandidateExtractor().extract_candidates("anything") == []
