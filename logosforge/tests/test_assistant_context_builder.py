"""Phase 5 — assistant context builder retrieval + composition MVP.

Proves the context builder retrieves **scoped** memory from a local store and
composes a provider-agnostic `ContextBundle` with the sections kept separate,
deterministic ranking/selection, a character-budget placeholder, optional
provider capabilities, and safe prompt serialization. Invariants:

- active memory by default; proposed/speculative/archived excluded with reasons;
- Project / User / Workspace / Assistant memory never mixed;
- **no provider call** and **no memory write** during context build;
- secrets / raw-audio paths never reach a prompt section.
"""

from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

from logosforge.assistant_arch.context_builder import (
    AssistantContextBuilder,
    ContextBundle,
    DocumentContext,
)
from logosforge.assistant_arch.model_gateway import (
    DummyModelProvider,
    ModelGateway,
    ProviderType,
)
from logosforge.memory_arch.schema import (
    MemoryObject,
    MemoryScope,
    MemoryStatus,
    MemoryType,
)
from logosforge.memory_arch.store import InMemoryMemoryStore


def _store():
    return InMemoryMemoryStore()


def _active(store, scope, mtype, content, **kw):
    m = store.write_candidate(MemoryObject(scope=scope, type=mtype,
                                           content=content, **kw))
    store.approve_candidate(m.id)
    return store.get(m.id)


def _set_status(store, mem, status):
    return store.update(mem.id, {"status": status}, reason="test transition")


# 1. Empty store → valid, empty ContextBundle (no crash).
def test_empty_store_valid_bundle():
    cb = AssistantContextBuilder(_store())
    b = cb.build_context("hello", project_id="p1", user_id="u1")
    assert isinstance(b, ContextBundle)
    assert b.project_memory == [] and b.user_memory == []
    assert b.assistant_meta_memory == [] and b.assistant_rules == []
    assert b.request_id and b.user_request == "hello"


# 2. Project memory retrieved for matching project_id.
def test_project_memory_matching():
    store = _store()
    _active(store, MemoryScope.PROJECT, MemoryType.CHARACTER_FACT,
            "Ada is methodical", project_id="p1")
    b = AssistantContextBuilder(store).build_context("Ada", project_id="p1")
    assert any("Ada is methodical" in m.content for m in b.project_memory)


# 3. Wrong-project memory excluded (with reason).
def test_wrong_project_excluded():
    store = _store()
    _active(store, MemoryScope.PROJECT, MemoryType.PROJECT_DECISION,
            "p1 canon", project_id="p1")
    _active(store, MemoryScope.PROJECT, MemoryType.PROJECT_DECISION,
            "p2 canon", project_id="p2")
    b = AssistantContextBuilder(store).build_context("canon", project_id="p1")
    assert any("p1 canon" in m.content for m in b.project_memory)
    assert not any("p2 canon" in m.content for m in b.project_memory)
    assert any(e["reason"] == "wrong project" for e in b.excluded_memory)


# 4. User memory is separate from project memory.
def test_user_memory_separate():
    store = _store()
    _active(store, MemoryScope.PROJECT, MemoryType.CONTINUITY_FACT,
            "the gate is open", project_id="p1")
    _active(store, MemoryScope.USER, MemoryType.PREFERENCE,
            "prefers em dashes", user_id="u1")
    b = AssistantContextBuilder(store).build_context(
        "", project_id="p1", user_id="u1")
    assert any("prefers em dashes" in m.content for m in b.user_memory)
    assert not any("prefers em dashes" in m.content for m in b.project_memory)
    assert not any("gate is open" in m.content for m in b.user_memory)


# 5. Assistant Meta-Memory retrieved separately.
def test_assistant_meta_separate():
    store = _store()
    _active(store, MemoryScope.ASSISTANT, MemoryType.MISTAKE_CORRECTION,
            "do not mix scopes")
    b = AssistantContextBuilder(store).build_context("scopes", project_id="p1")
    assert any("do not mix scopes" in m.content
               for m in b.assistant_meta_memory)
    assert not any("do not mix scopes" in m.content for m in b.project_memory)


# 6. Workspace memory retrieved only when workspace_id is given.
def test_workspace_memory_conditional():
    store = _store()
    _active(store, MemoryScope.WORKSPACE, MemoryType.REPO_DECISION,
            "team uses trunk-based dev", workspace_id="ws1")
    with_ws = AssistantContextBuilder(store).build_context(
        "dev", project_id="p1", workspace_id="ws1")
    without_ws = AssistantContextBuilder(store).build_context(
        "dev", project_id="p1")
    assert any("trunk-based" in m.content for m in with_ws.workspace_memory)
    assert without_ws.workspace_memory == []


# 7. Assistant rules retrieved as a separate focused view.
def test_assistant_rules_separate():
    store = _store()
    _active(store, MemoryScope.ASSISTANT, MemoryType.ASSISTANT_RULE,
            "always dual-push both refs")
    b = AssistantContextBuilder(store).build_context("push", project_id="p1")
    assert any("dual-push" in m.content for m in b.assistant_rules)
    assert any("dual-push" in m.content for m in b.assistant_meta_memory)


# 8-10. Deprecated / superseded / contradicted excluded by default (with reason).
def test_deprecated_excluded():
    store = _store()
    m = _active(store, MemoryScope.PROJECT, MemoryType.CONTINUITY_FACT,
                "old fact", project_id="p1")
    _set_status(store, m, MemoryStatus.DEPRECATED)
    b = AssistantContextBuilder(store).build_context("fact", project_id="p1")
    assert b.project_memory == []
    assert any(e["reason"] == "deprecated" for e in b.excluded_memory)


def test_superseded_excluded():
    store = _store()
    m = _active(store, MemoryScope.PROJECT, MemoryType.CONTINUITY_FACT,
                "stale fact", project_id="p1")
    _set_status(store, m, MemoryStatus.SUPERSEDED)
    b = AssistantContextBuilder(store).build_context("fact", project_id="p1")
    assert b.project_memory == []
    assert any(e["reason"] == "superseded" for e in b.excluded_memory)


def test_contradicted_excluded():
    store = _store()
    m = _active(store, MemoryScope.PROJECT, MemoryType.CONTINUITY_FACT,
                "conflicting fact", project_id="p1")
    _set_status(store, m, MemoryStatus.CONTRADICTED)
    b = AssistantContextBuilder(store).build_context("fact", project_id="p1")
    assert b.project_memory == []
    assert any(e["reason"] == "contradicted" for e in b.excluded_memory)


# 11. Proposed/speculative excluded by default (with reason).
def test_proposed_excluded_by_default():
    store = _store()
    store.write_candidate(MemoryObject(            # proposed, not approved
        scope=MemoryScope.PROJECT, type=MemoryType.PROJECT_DECISION,
        content="tentative decision", project_id="p1"))
    b = AssistantContextBuilder(store).build_context(
        "decision", project_id="p1")
    assert b.project_memory == []
    assert any("not active" in e["reason"] for e in b.excluded_memory)
    # review/include_proposed surfaces it.
    b2 = AssistantContextBuilder(store).build_context(
        "decision", project_id="p1", include_proposed=True)
    assert any("tentative decision" in m.content for m in b2.project_memory)


# 12. Diagnostic mode includes non-active statuses with visible labels.
def test_diagnostic_includes_labeled():
    store = _store()
    m = _active(store, MemoryScope.PROJECT, MemoryType.CONTINUITY_FACT,
                "deprecated detail", project_id="p1")
    _set_status(store, m, MemoryStatus.DEPRECATED)
    b = AssistantContextBuilder(store).build_context(
        "detail", project_id="p1", diagnostic=True)
    assert any("deprecated detail" in mm.content for mm in b.project_memory)
    text = b.to_prompt_text(diagnostic=True)
    assert "status: deprecated" in text


# 13. Ranking prefers exact content match.
def test_ranking_prefers_match():
    store = _store()
    _active(store, MemoryScope.PROJECT, MemoryType.CONTINUITY_FACT,
            "unrelated note", project_id="p1")
    _active(store, MemoryScope.PROJECT, MemoryType.CONTINUITY_FACT,
            "the door is locked", project_id="p1")
    b = AssistantContextBuilder(store).build_context("door", project_id="p1")
    assert "door" in b.project_memory[0].content


# 14. Ranking prefers higher-confidence active memory.
def test_ranking_prefers_confidence():
    store = _store()
    _active(store, MemoryScope.PROJECT, MemoryType.CONTINUITY_FACT,
            "door low", project_id="p1", confidence=0.1)
    _active(store, MemoryScope.PROJECT, MemoryType.CONTINUITY_FACT,
            "door high", project_id="p1", confidence=0.9)
    b = AssistantContextBuilder(store).build_context("door", project_id="p1")
    assert b.project_memory[0].confidence == 0.9


# 15. Budget excludes lower-priority memory (over budget).
def test_budget_excludes():
    store = _store()
    for i in range(4):
        _active(store, MemoryScope.PROJECT, MemoryType.CONTINUITY_FACT,
                "x" * 50 + f" fact {i}", project_id="p1")
    b = AssistantContextBuilder(store).build_context(
        "fact", project_id="p1", character_budget=70)
    assert len(b.project_memory) == 1
    assert any(e["reason"] == "over budget" for e in b.excluded_memory)
    assert b.estimated_chars <= 70


# 16. Excluded memory entries always carry a reason.
def test_excluded_has_reasons():
    store = _store()
    _active(store, MemoryScope.PROJECT, MemoryType.PROJECT_DECISION,
            "kept", project_id="p1")
    _active(store, MemoryScope.PROJECT, MemoryType.PROJECT_DECISION,
            "other project", project_id="p2")
    store.write_candidate(MemoryObject(
        scope=MemoryScope.PROJECT, type=MemoryType.PROJECT_DECISION,
        content="proposed one", project_id="p1"))
    b = AssistantContextBuilder(store).build_context("", project_id="p1")
    assert b.excluded_memory
    assert all(e.get("reason") for e in b.excluded_memory)
    reasons = {e["reason"] for e in b.excluded_memory}
    assert "wrong project" in reasons
    assert any("not active" in r for r in reasons)


# 17. Provider capabilities included when a provider is registered.
def test_provider_capabilities_included():
    store = _store()
    gw = ModelGateway()
    gw.register_provider(DummyModelProvider("dummy", ProviderType.LOCAL))
    b = AssistantContextBuilder(store, gw).build_context(
        "x", project_id="p1", provider_id="dummy")
    assert b.provider_capabilities is not None
    assert b.provider_capabilities.provider_id == "dummy"
    assert b.provider_capabilities.context_window == 8192
    assert b.provider_capabilities.offline_capable is True


# 18. Missing/unknown provider → warning, not crash.
def test_missing_provider_warns():
    store = _store()
    no_gw = AssistantContextBuilder(store).build_context(
        "x", project_id="p1", provider_id="anything")
    assert no_gw.provider_capabilities is None
    assert any("provider" in w.lower() for w in no_gw.retrieval_warnings)
    gw = ModelGateway()
    gw.register_provider(DummyModelProvider("dummy"))
    unknown = AssistantContextBuilder(store, gw).build_context(
        "x", project_id="p1", provider_id="nope")
    assert unknown.provider_capabilities is None
    assert any("not registered" in w for w in unknown.retrieval_warnings)


# 19. to_prompt_sections labels every scope clearly.
def test_prompt_sections_labels():
    b = AssistantContextBuilder(_store()).build_context("task", project_id="p1")
    titles = [s["title"] for s in b.to_prompt_sections()]
    for expected in ("Current Task", "Current Document Context",
                     "Project Memory", "User Memory", "Workspace Memory",
                     "Assistant Meta-Memory", "Assistant Rules",
                     "Provider Capabilities", "Warnings / Exclusions"):
        assert expected in titles


# 20. to_prompt_sections never includes secrets.
def test_prompt_sections_no_secrets():
    secret = MemoryObject(
        scope=MemoryScope.PROJECT, type=MemoryType.CONTINUITY_FACT,
        content="api_key: sk-deadbeef12345678", project_id="p1",
        status=MemoryStatus.ACTIVE)
    b = ContextBundle(project_memory=[secret])
    text = b.to_prompt_text()
    assert "sk-deadbeef" not in text and "[redacted]" in text


# 21. to_prompt_sections never includes raw audio paths.
def test_prompt_sections_no_audio_paths():
    audio = MemoryObject(
        scope=MemoryScope.PROJECT, type=MemoryType.CONTINUITY_FACT,
        content="buffer saved to clip_01.wav", project_id="p1",
        status=MemoryStatus.ACTIVE)
    b = ContextBundle(project_memory=[audio])
    text = b.to_prompt_text()
    assert "clip_01.wav" not in text and "[redacted]" in text


# 22. Project Memory and Assistant Meta-Memory are not mixed.
def test_project_and_assistant_not_mixed():
    store = _store()
    _active(store, MemoryScope.PROJECT, MemoryType.CHARACTER_FACT,
            "Ada is tall", project_id="p1")
    _active(store, MemoryScope.ASSISTANT, MemoryType.WORKFLOW_RULE,
            "propose before durable")
    b = AssistantContextBuilder(store).build_context("", project_id="p1")
    assert all(m.scope is MemoryScope.PROJECT for m in b.project_memory)
    assert all(m.scope is MemoryScope.ASSISTANT
               for m in b.assistant_meta_memory)
    assert not any("Ada is tall" in m.content for m in b.assistant_meta_memory)
    assert not any("propose before durable" in m.content
                   for m in b.project_memory)


# 23. No provider generate() call occurs during build_context.
def test_no_provider_generate_call():
    class _NoGen(DummyModelProvider):
        def generate(self, request):
            raise AssertionError("provider.generate must not be called")

    store = _store()
    gw = ModelGateway()
    gw.register_provider(_NoGen("safe", ProviderType.LOCAL))
    b = AssistantContextBuilder(store, gw).build_context(
        "x", project_id="p1", provider_id="safe")
    assert b.provider_capabilities.provider_id == "safe"   # no raise → no call


# 24. No memory write occurs during build_context.
def test_no_memory_write_on_build():
    store = _store()
    _active(store, MemoryScope.PROJECT, MemoryType.CONTINUITY_FACT,
            "stable fact", project_id="p1")
    before_mem = len(store.search(""))
    before_ev = len(store.list_events())
    AssistantContextBuilder(store).build_context("fact", project_id="p1")
    assert len(store.search("")) == before_mem
    assert len(store.list_events()) == before_ev


# 25. DocumentContext adapter populates document fields (no app/UI touch).
def test_document_context_adapter():
    store = _store()
    doc = DocumentContext(
        project_id="p1", current_mode="novel", active_section="Manuscript",
        selected_excerpt="Ada opened the door.", active_entities=["Ada"])
    b = AssistantContextBuilder(store).build_context("continue", document=doc)
    assert b.current_mode == "novel" and b.project_id == "p1"
    assert "Mode: novel" in b.current_document_context
    assert "Ada opened the door" in b.selected_document_excerpt
    # dict form is also accepted.
    b2 = AssistantContextBuilder(store).build_context(
        "x", document={"current_mode": "series", "project_id": "p1"})
    assert b2.current_mode == "series"


# 26. to_dict serializes safely (separate sections; redacted content).
def test_to_dict_serialization_safe():
    secret = MemoryObject(
        scope=MemoryScope.PROJECT, type=MemoryType.CONTINUITY_FACT,
        content="token: sk-deadbeef12345678", project_id="p1",
        status=MemoryStatus.ACTIVE)
    d = ContextBundle(user_request="go", project_memory=[secret]).to_dict()
    assert "project_memory" in d and "assistant_meta_memory" in d
    assert d["project_memory"][0]["content"] == "[redacted]"
    assert "sk-deadbeef" not in str(d)
