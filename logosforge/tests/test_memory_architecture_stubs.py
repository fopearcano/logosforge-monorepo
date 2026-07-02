"""Phase 2 — assistant memory + model gateway interfaces/stubs.

Proves the new isolated packages (`logosforge.memory_arch`,
`logosforge.assistant_arch`) are safe, non-destructive interface stubs:
explicit scopes, candidates-not-active, forbidden-content rejection, no
persistence/network, disabled cloud/GitHub sync, and import safety. No
production UI/provider behavior is touched.
"""

from __future__ import annotations

import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge.memory_arch.schema import (
    EventLogEntry,
    MemoryObject,
    MemoryScope,
    MemoryStatus,
    MemoryType,
)
from logosforge.memory_arch.store import InMemoryMemoryStore
from logosforge.memory_arch.policy import MemoryWriterPolicy
from logosforge.assistant_arch.context_builder import (
    AssistantContextBuilder,
    ContextBundle,
    MemoryCandidateExtractor,
)
from logosforge.assistant_arch.model_gateway import (
    DummyModelProvider,
    ModelGateway,
    ModelRequest,
    ProviderType,
)
from logosforge.assistant_arch.tools import AssistantTools


# 1. MemoryObject requires explicit scope (no default).
def test_memory_object_requires_explicit_scope():
    import inspect
    sig = inspect.signature(MemoryObject.__init__)
    assert sig.parameters["scope"].default is inspect.Parameter.empty


# 2. Project Memory requires project_id.
def test_project_memory_requires_project_id():
    with pytest.raises(ValueError):
        MemoryObject(scope=MemoryScope.PROJECT,
                     type=MemoryType.PROJECT_DECISION, content="x")
    ok = MemoryObject(scope=MemoryScope.PROJECT,
                      type=MemoryType.PROJECT_DECISION, content="x",
                      project_id="p1")
    assert ok.project_id == "p1"


# 3. User Memory accepts user scope (with user_id).
def test_user_memory_accepts_user_scope():
    mem = MemoryObject(scope=MemoryScope.USER, type=MemoryType.PREFERENCE,
                       content="prefers dark theme", user_id="u1")
    assert mem.scope is MemoryScope.USER
    with pytest.raises(ValueError):
        MemoryObject(scope=MemoryScope.USER, type=MemoryType.PREFERENCE,
                     content="x")            # user scope needs user_id


# 4. Assistant Meta-Memory can store an assistant_rule.
def test_assistant_meta_memory_stores_rule():
    mem = MemoryObject(scope=MemoryScope.ASSISTANT,
                       type=MemoryType.ASSISTANT_RULE,
                       content="propose memory before making it durable")
    assert mem.type is MemoryType.ASSISTANT_RULE


# 5. Proposed candidate defaults to proposed (never active).
def test_candidate_defaults_to_proposed_not_active():
    mem = MemoryObject(scope=MemoryScope.ASSISTANT,
                       type=MemoryType.WORKFLOW_RULE, content="x")
    assert mem.status is MemoryStatus.PROPOSED
    spec = MemoryObject(scope=MemoryScope.ASSISTANT,
                        type=MemoryType.SPECULATIVE_IDEA, content="maybe",
                        status=MemoryStatus.SPECULATIVE)
    assert spec.status is MemoryStatus.SPECULATIVE


# 6. Policy rejects obvious API keys/secrets.
def test_policy_rejects_secrets():
    p = MemoryWriterPolicy()
    assert p.check_forbidden_content_text("key is sk-abcd1234efgh5678")
    assert p.check_forbidden_content_text("api_key: hunter2")
    assert p.should_save_candidate("sk-abcd1234efgh5678") is False


# 7. Policy rejects raw audio paths.
def test_policy_rejects_raw_audio_paths():
    p = MemoryWriterPolicy()
    assert p.check_forbidden_content_text("buffer saved to clip_01.wav")
    assert p.should_save_candidate("recording.mp3 captured") is False


# 8. InMemoryMemoryStore.write_candidate works (and refuses active).
def test_store_write_candidate():
    store = InMemoryMemoryStore()
    mem = MemoryObject(scope=MemoryScope.USER, type=MemoryType.PREFERENCE,
                       content="likes em dashes", user_id="u1")
    saved = store.write_candidate(mem)
    assert store.get(saved.id) is saved
    bad = MemoryObject(scope=MemoryScope.USER, type=MemoryType.PREFERENCE,
                       content="active!", user_id="u1",
                       status=MemoryStatus.ACTIVE)
    with pytest.raises(ValueError):
        store.write_candidate(bad)           # active not allowed via candidate


# 9. approve_candidate changes status to active.
def test_approve_candidate_activates():
    store = InMemoryMemoryStore()
    mem = store.write_candidate(MemoryObject(
        scope=MemoryScope.ASSISTANT, type=MemoryType.WORKFLOW_RULE,
        content="dual-push both refs"))
    out = store.approve_candidate(mem.id)
    assert out.status is MemoryStatus.ACTIVE and out.version == 2


# 10. supersede preserves old object and marks it superseded.
def test_supersede_preserves_old():
    store = InMemoryMemoryStore()
    old = store.write_candidate(MemoryObject(
        scope=MemoryScope.ASSISTANT, type=MemoryType.ARCHITECTURE_DECISION,
        content="use tree outline"))
    new = store.write_candidate(MemoryObject(
        scope=MemoryScope.ASSISTANT, type=MemoryType.ARCHITECTURE_DECISION,
        content="use block/card outline"))
    o, n = store.supersede(old.id, new.id, reason="block UX replaces tree")
    assert o.status is MemoryStatus.SUPERSEDED       # preserved, not deleted
    assert store.get(old.id) is not None
    assert n.supersedes == old.id
    with pytest.raises(ValueError):
        store.update(new.id, {"content": "x"}, reason="")   # reason required


# 11. search returns a matching memory object.
def test_search_substring():
    store = InMemoryMemoryStore()
    store.write_candidate(MemoryObject(
        scope=MemoryScope.PROJECT, type=MemoryType.CHARACTER_FACT,
        content="Ada North is methodical", project_id="p1"))
    assert store.search("methodical", project_id="p1")
    assert store.search("methodical", project_id="other") == []


# 12. find_contradictions stub returns a safe empty list.
def test_find_contradictions_stub_empty():
    store = InMemoryMemoryStore()
    assert store.find_contradictions("anything") == []
    from logosforge.memory_arch.contradictions import ContradictionChecker
    cand = MemoryObject(scope=MemoryScope.USER, type=MemoryType.PREFERENCE,
                        content="x", user_id="u1")
    assert ContradictionChecker().find_contradictions(cand, []) == []


# 13. ModelGateway registers a dummy provider.
def test_gateway_registers_dummy():
    gw = ModelGateway()
    gw.register_provider(DummyModelProvider("dummy"))
    caps = gw.list_providers()
    assert [c.provider_id for c in caps] == ["dummy"]
    assert gw.select_provider() == "dummy"


# 14. Dummy provider generate returns a deterministic response.
def test_dummy_generate_deterministic():
    gw = ModelGateway()
    gw.register_provider(DummyModelProvider("dummy"))
    req = ModelRequest(provider_id="dummy", model="dummy-1",
                       messages=[{"role": "user", "content": "hello"}])
    r1 = gw.generate(req)
    r2 = gw.generate(req)
    assert r1.content == r2.content == "[dummy:dummy] hello"


# 15. Provider capabilities distinguish local/cloud.
def test_capabilities_local_vs_cloud():
    local = DummyModelProvider("lm", ProviderType.LOCAL).get_capabilities()
    cloud = DummyModelProvider("oa", ProviderType.CLOUD).get_capabilities()
    assert local.provider_type is ProviderType.LOCAL and local.offline_capable
    assert cloud.provider_type is ProviderType.CLOUD
    assert cloud.privacy_mode == "cloud" and not cloud.offline_capable


# 16. AssistantContextBuilder returns a ContextBundle without mutation.
def test_context_builder_no_mutation():
    store = InMemoryMemoryStore()
    mem = store.write_candidate(MemoryObject(
        scope=MemoryScope.PROJECT, type=MemoryType.CONTINUITY_FACT,
        content="door is unlocked", project_id="p1"))
    store.approve_candidate(mem.id)     # Phase 5 retrieves active memory by default
    before = len(store.search(""))
    cb = AssistantContextBuilder(store)
    # Deterministic substring ranking (Phase 5) — query a term.
    bundle = cb.build_context("door", project_id="p1")
    assert isinstance(bundle, ContextBundle)
    assert any("door" in m.content for m in bundle.project_memory)
    assert len(store.search("")) == before          # nothing written
    # No store → safe empty bundle, no raise.
    empty = AssistantContextBuilder(None).build_context("x", project_id="p1")
    assert empty.project_memory == [] and empty.warnings


# 17. MemoryCandidateExtractor returns empty list by default.
def test_candidate_extractor_empty():
    assert MemoryCandidateExtractor().extract_candidates("a session") == []


# 18. sync_memory_to_cloud returns disabled/not_configured.
def test_sync_disabled():
    tools = AssistantTools()
    out = tools.sync_memory_to_cloud()
    assert out["status"] == "disabled"


# 19. optional_sync_memory_to_github returns disabled/not_configured.
def test_github_sync_disabled():
    tools = AssistantTools()
    out = tools.optional_sync_memory_to_github()
    assert out["status"] == "disabled" and out.get("reason")


# 20. Importing memory modules requires no external services.
def test_imports_have_no_external_deps():
    import importlib
    for mod in ("logosforge.memory_arch",
                "logosforge.memory_arch.schema",
                "logosforge.memory_arch.store",
                "logosforge.memory_arch.policy",
                "logosforge.memory_arch.retrieval",
                "logosforge.memory_arch.contradictions",
                "logosforge.memory_arch.sync",
                "logosforge.memory_arch.github_export",
                "logosforge.assistant_arch",
                "logosforge.assistant_arch.model_gateway",
                "logosforge.assistant_arch.context_builder",
                "logosforge.assistant_arch.orchestration",
                "logosforge.assistant_arch.tools"):
        importlib.import_module(mod)        # no network/provider/DB on import


# Extra: tools write_candidate creates a proposed candidate and refuses
# forbidden content; event log + project/assistant separation hold.
def test_tools_candidate_and_separation():
    tools = AssistantTools()
    mem = tools.write_memory_candidate(
        "user prefers GitHub-first workflow", MemoryType.WORKFLOW_RULE,
        MemoryScope.ASSISTANT, confidence=0.8)
    assert mem.status is MemoryStatus.PROPOSED
    with pytest.raises(ValueError):
        tools.write_memory_candidate("token: sk-deadbeef12345678",
                                     MemoryType.OTHER, MemoryScope.USER,
                                     user_id="u1")
    # assistant scope must not hold project fiction facts.
    p = MemoryWriterPolicy()
    bad = MemoryObject(scope=MemoryScope.ASSISTANT,
                       type=MemoryType.CHARACTER_FACT, content="Ada is tall")
    with pytest.raises(ValueError):
        p.validate_scope(bad)
    # event log entry schema works.
    store = InMemoryMemoryStore()
    ev = store.add_event(EventLogEntry(event_type="edit", content="typed"))
    assert store._events[ev.id] is ev
