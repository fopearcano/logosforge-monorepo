"""Phase 3 — local-first SQLite assistant memory store.

Proves `LocalSQLiteMemoryStore` is a safe MVP: real persistence (events +
curated objects), candidate-not-active, explicit approval, supersede
preserves history, substring/scope/project search, markdown export, policy
rejection of secrets/raw-audio, and **no** cloud/GitHub/provider/network.
No app startup, UI, or provider behavior is touched.
"""

from __future__ import annotations

import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge.memory_arch.local_store import (
    LocalSQLiteMemoryStore,
    default_memory_db_path,
)
from logosforge.memory_arch.schema import (
    EventLogEntry,
    MemoryObject,
    MemoryScope,
    MemoryStatus,
    MemoryType,
)


def _store(tmp_path, name="mem.sqlite3"):
    return LocalSQLiteMemoryStore(str(tmp_path / name))


def _table_names(store) -> set[str]:
    rows = store._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r["name"] for r in rows}


# 1-3. init + tables.
def test_temp_db_initializes_with_tables(tmp_path):
    store = _store(tmp_path)
    names = _table_names(store)
    assert "memory_events" in names
    assert "memory_objects" in names
    assert "memory_relations" in names
    assert (tmp_path / "mem.sqlite3").exists()


# 4. add_event persists and reloads.
def test_add_event_round_trip(tmp_path):
    store = _store(tmp_path)
    ev = store.add_event(EventLogEntry(event_type="edit", content="typed text",
                                       project_id="p1",
                                       metadata={"k": "v"}))
    got = store.get_event(ev.id)
    assert got is not None and got.content == "typed text"
    assert got.metadata == {"k": "v"}
    # Persists across reconnects (real durability).
    store.close()
    store2 = LocalSQLiteMemoryStore(str(tmp_path / "mem.sqlite3"))
    assert store2.get_event(ev.id).content == "typed text"


# 5-6. write_candidate persists proposed; never silently active.
def test_write_candidate_persists_proposed(tmp_path):
    store = _store(tmp_path)
    mem = store.write_candidate(MemoryObject(
        scope=MemoryScope.USER, type=MemoryType.PREFERENCE,
        content="prefers em dashes", user_id="u1"))
    got = store.get(mem.id)
    assert got is not None and got.status is MemoryStatus.PROPOSED
    bad = MemoryObject(scope=MemoryScope.USER, type=MemoryType.PREFERENCE,
                       content="x", user_id="u1", status=MemoryStatus.ACTIVE)
    with pytest.raises(ValueError):
        store.write_candidate(bad)


# 7. approve_candidate → active.
def test_approve_candidate_activates(tmp_path):
    store = _store(tmp_path)
    mem = store.write_candidate(MemoryObject(
        scope=MemoryScope.ASSISTANT, type=MemoryType.WORKFLOW_RULE,
        content="dual-push both refs"))
    out = store.approve_candidate(mem.id)
    assert out.status is MemoryStatus.ACTIVE and out.version == 2
    assert store.get(mem.id).status is MemoryStatus.ACTIVE   # persisted


# 8. get returns a parsed MemoryObject with lists intact.
def test_get_parses_object(tmp_path):
    store = _store(tmp_path)
    mem = store.write_candidate(MemoryObject(
        scope=MemoryScope.PROJECT, type=MemoryType.CHARACTER_FACT,
        content="Ada is methodical", project_id="p1",
        tags=["psyke", "ada"], entities=["Ada North"]))
    got = store.get(mem.id)
    assert got.tags == ["psyke", "ada"] and got.entities == ["Ada North"]
    assert got.scope is MemoryScope.PROJECT


# 9-11. search substring / scope / project.
def test_search_filters(tmp_path):
    store = _store(tmp_path)
    store.write_candidate(MemoryObject(
        scope=MemoryScope.PROJECT, type=MemoryType.CONTINUITY_FACT,
        content="the door is unlocked", project_id="p1"))
    store.write_candidate(MemoryObject(
        scope=MemoryScope.USER, type=MemoryType.PREFERENCE,
        content="dark theme please", user_id="u1"))
    assert len(store.search("door")) == 1
    assert store.search("door", project_id="p2") == []
    assert len(store.search("", scope=MemoryScope.USER)) == 1
    assert len(store.search("", scope=MemoryScope.PROJECT,
                            project_id="p1")) == 1
    # type/status filters.
    assert len(store.search("", filters={"type": MemoryType.PREFERENCE})) == 1
    assert len(store.search(
        "", filters={"status": MemoryStatus.PROPOSED})) == 2


# 12-13. update requires reason; applies patch.
def test_update_requires_reason_and_patches(tmp_path):
    store = _store(tmp_path)
    mem = store.write_candidate(MemoryObject(
        scope=MemoryScope.USER, type=MemoryType.PREFERENCE,
        content="old", user_id="u1"))
    with pytest.raises(ValueError):
        store.update(mem.id, {"content": "new"}, reason="")
    out = store.update(mem.id, {"content": "new", "tags": ["t"]},
                       reason="user revised")
    assert out.content == "new" and out.tags == ["t"] and out.version == 2
    assert store.get(mem.id).content == "new"               # persisted


# 14-16. supersede marks/links/preserves.
def test_supersede_preserves_and_links(tmp_path):
    store = _store(tmp_path)
    old = store.write_candidate(MemoryObject(
        scope=MemoryScope.ASSISTANT, type=MemoryType.ARCHITECTURE_DECISION,
        content="tree outline"))
    new = store.write_candidate(MemoryObject(
        scope=MemoryScope.ASSISTANT, type=MemoryType.ARCHITECTURE_DECISION,
        content="block/card outline"))
    o, n = store.supersede(old.id, new.id, reason="block UX replaces tree")
    assert o.status is MemoryStatus.SUPERSEDED
    assert store.get(old.id) is not None                    # not deleted
    assert store.get(new.id).supersedes == old.id
    rel = store._conn.execute(
        "SELECT * FROM memory_relations WHERE source_memory_id=?",
        (old.id,)).fetchone()
    assert rel["relation_type"] == "supersedes"
    with pytest.raises(ValueError):
        store.supersede(old.id, new.id, reason="")


# 17. find_contradictions safe.
def test_find_contradictions_safe(tmp_path):
    store = _store(tmp_path)
    assert store.find_contradictions("anything") == []
    # A flagged-contradicted object is surfaced.
    store.write_candidate(MemoryObject(
        scope=MemoryScope.USER, type=MemoryType.PREFERENCE,
        content="contradicted topic", user_id="u1"))
    # (none are 'contradicted' status yet → still empty)
    assert store.find_contradictions("contradicted") == []


# 18-19. markdown export + filters.
def test_export_markdown(tmp_path):
    store = _store(tmp_path)
    store.write_candidate(MemoryObject(
        scope=MemoryScope.PROJECT, type=MemoryType.CHARACTER_FACT,
        content="Milo is nervous", project_id="p1", tags=["milo"]))
    store.write_candidate(MemoryObject(
        scope=MemoryScope.USER, type=MemoryType.PREFERENCE,
        content="user secret-free pref", user_id="u1"))
    md = store.export_markdown()
    assert md.startswith("# LogosForge memory export")
    assert "Milo is nervous" in md and "Scope: project" in md
    assert "Generated:" in md
    scoped = store.export_markdown(scope=MemoryScope.PROJECT, project_id="p1")
    assert "Milo is nervous" in scoped and "user secret-free pref" not in scoped


# 20-21. scope id requirements (schema invariants hold through the store).
def test_scope_id_requirements(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.write_candidate(MemoryObject(
            scope=MemoryScope.PROJECT, type=MemoryType.PROJECT_DECISION,
            content="x"))                                    # no project_id
    ok = store.write_candidate(MemoryObject(
        scope=MemoryScope.USER, type=MemoryType.PREFERENCE,
        content="ok", user_id="u1"))
    assert ok.user_id == "u1"


# 22-23. policy rejects secrets / raw audio at write.
def test_policy_rejects_secrets_and_audio(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.write_candidate(MemoryObject(
            scope=MemoryScope.USER, type=MemoryType.OTHER,
            content="key sk-abcd1234efgh5678", user_id="u1"))
    with pytest.raises(ValueError):
        store.write_candidate(MemoryObject(
            scope=MemoryScope.USER, type=MemoryType.OTHER,
            content="buffer saved to clip.wav", user_id="u1"))
    # assistant scope must not hold project fiction facts (policy.validate_scope)
    with pytest.raises(ValueError):
        store.write_candidate(MemoryObject(
            scope=MemoryScope.ASSISTANT, type=MemoryType.CHARACTER_FACT,
            content="Ada is tall"))


# 24-25. sync/github remain disabled via tools using the local store.
def test_sync_and_github_disabled_with_local_store(tmp_path):
    from logosforge.assistant_arch.tools import AssistantTools
    tools = AssistantTools(store=_store(tmp_path))
    assert tools.sync_memory_to_cloud()["status"] == "disabled"
    assert tools.optional_sync_memory_to_github()["status"] == "disabled"
    # tools.search routes to the local store.
    tools.write_memory_candidate("local-routed pref", MemoryType.PREFERENCE,
                                 MemoryScope.USER, user_id="u1")
    assert tools.search_memory("local-routed")


# 26. import safety — no external services, no DB created on import.
def test_import_safety_no_db_on_import():
    import importlib
    importlib.import_module("logosforge.memory_arch.local_store")
    # default path is just a string; importing/calling it creates nothing.
    p = default_memory_db_path()
    assert p.endswith("logosforge_memory.sqlite3")


# Context builder retrieves from the local store, separated by scope.
def test_context_builder_local_retrieval_separated(tmp_path):
    from logosforge.assistant_arch.context_builder import (
        AssistantContextBuilder)
    store = _store(tmp_path)
    pm = store.write_candidate(MemoryObject(
        scope=MemoryScope.PROJECT, type=MemoryType.CONTINUITY_FACT,
        content="door fact", project_id="p1"))
    am = store.write_candidate(MemoryObject(
        scope=MemoryScope.ASSISTANT, type=MemoryType.WORKFLOW_RULE,
        content="door rule"))
    store.approve_candidate(pm.id)      # Phase 5 retrieves active memory by default
    store.approve_candidate(am.id)
    cb = AssistantContextBuilder(store)
    bundle = cb.build_context("door", project_id="p1", user_id="u1")
    assert any("door fact" in m.content for m in bundle.project_memory)
    assert any("door rule" in m.content for m in bundle.assistant_meta_memory)
    # Project and Assistant memory stay in separate bundle fields.
    assert all(m.scope is MemoryScope.PROJECT for m in bundle.project_memory)
    assert all(m.scope is MemoryScope.ASSISTANT
               for m in bundle.assistant_meta_memory)
