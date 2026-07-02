"""Phase 6 — passive assistant context integration MVP.

Proves the assistant prompt builder can OPTIONALLY receive a read-only
LogosForge ContextBundle without changing provider behavior or writing memory:

- default-off: when the flag is disabled (or no params/store), the prompt is
  byte-identical to before;
- when enabled, scoped memory + provider capabilities are injected as clearly
  labelled, separate sections;
- archived/proposed memory and wrong-project memory are excluded;
- secrets / raw-audio / raw events never appear;
- **no memory write** and **no sync/GitHub** calls happen during prompt build;
- builder/store failures and missing project_id degrade safely.
"""

from __future__ import annotations

import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge import assistant
from logosforge.assistant_arch import passive_context
from logosforge.assistant_arch.model_gateway import (
    DummyModelProvider,
    ModelGateway,
    ProviderType,
)
from logosforge.memory_arch.schema import (
    EventLogEntry,
    MemoryObject,
    MemoryScope,
    MemoryStatus,
    MemoryType,
)
from logosforge.memory_arch.store import InMemoryMemoryStore


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(passive_context, "is_enabled", lambda: True)
    monkeypatch.setattr(passive_context, "is_diagnostics_enabled", lambda: False)


@pytest.fixture
def enabled_diag(monkeypatch):
    monkeypatch.setattr(passive_context, "is_enabled", lambda: True)
    monkeypatch.setattr(passive_context, "is_diagnostics_enabled", lambda: True)


@pytest.fixture
def disabled(monkeypatch):
    monkeypatch.setattr(passive_context, "is_enabled", lambda: False)


def _active(store, scope, mtype, content, **kw):
    m = store.write_candidate(MemoryObject(scope=scope, type=mtype,
                                           content=content, **kw))
    store.approve_candidate(m.id)
    return store.get(m.id)


def _set_status(store, mem, status):
    return store.update(mem.id, {"status": status}, reason="test")


def _user_text(messages):
    return next(m["content"] for m in messages if m["role"] == "user")


# 1. Flag disabled → prompt identical to the no-params prompt.
def test_disabled_prompt_identical(disabled):
    store = InMemoryMemoryStore()
    _active(store, MemoryScope.PROJECT, MemoryType.PROJECT_DECISION,
            "hero is Ada", project_id="p1")
    base = assistant.build_messages("Do X", "scene text")
    with_params = assistant.build_messages(
        "Do X", "scene text",
        memory_context_params={"store": store, "project_id": "p1"})
    assert base == with_params
    # And passing no params at all is also identical.
    assert assistant.build_messages("Do X", "scene text",
                                    memory_context_params=None) == base


# 2. Flag enabled → context builder runs; block injected.
def test_enabled_injects_block(enabled):
    store = InMemoryMemoryStore()
    _active(store, MemoryScope.PROJECT, MemoryType.PROJECT_DECISION,
            "hero is Ada North", project_id="p1")
    msgs = assistant.build_messages(
        "Who is the hero?", "scene text",
        memory_context_params={"store": store, "project_id": "p1"})
    text = _user_text(msgs)
    assert "LogosForge Memory Context" in text
    assert "hero is Ada North" in text


# 3-6. Scoped sections appear, labelled and separate.
def test_sections_labelled_and_separate(enabled):
    store = InMemoryMemoryStore()
    _active(store, MemoryScope.PROJECT, MemoryType.CHARACTER_FACT,
            "Ada is methodical", project_id="p1")
    _active(store, MemoryScope.USER, MemoryType.PREFERENCE,
            "prefers em dashes", user_id="u1")
    _active(store, MemoryScope.ASSISTANT, MemoryType.MISTAKE_CORRECTION,
            "do not mix scopes")
    _active(store, MemoryScope.ASSISTANT, MemoryType.ASSISTANT_RULE,
            "always dual-push")
    text = _user_text(assistant.build_messages(
        "task", "scene",
        memory_context_params={"store": store, "project_id": "p1",
                               "user_id": "u1"}))
    assert "## Project Memory" in text and "Ada is methodical" in text
    assert "## User Memory" in text and "prefers em dashes" in text
    assert "## Assistant Meta-Memory" in text and "do not mix scopes" in text
    assert "## Assistant Rules" in text and "always dual-push" in text


# 7. Provider capabilities appear as a separate section when available.
def test_provider_capabilities_section(enabled):
    store = InMemoryMemoryStore()
    _active(store, MemoryScope.PROJECT, MemoryType.PROJECT_DECISION,
            "canon fact", project_id="p1")
    gw = ModelGateway()
    gw.register_provider(DummyModelProvider("dummy", ProviderType.LOCAL))
    text = _user_text(assistant.build_messages(
        "task", "scene",
        memory_context_params={"store": store, "project_id": "p1",
                               "gateway": gw, "provider_id": "dummy"}))
    assert "## Provider Capabilities" in text
    assert "provider_id: dummy" in text and "context_window: 8192" in text


# 8. Wrong-project memory is excluded.
def test_wrong_project_excluded(enabled):
    store = InMemoryMemoryStore()
    _active(store, MemoryScope.PROJECT, MemoryType.PROJECT_DECISION,
            "p1 only fact", project_id="p1")
    _active(store, MemoryScope.PROJECT, MemoryType.PROJECT_DECISION,
            "p2 secret plot", project_id="p2")
    text = _user_text(assistant.build_messages(
        "task", "scene",
        memory_context_params={"store": store, "project_id": "p1"}))
    assert "p1 only fact" in text and "p2 secret plot" not in text


# 9-12. Archived + proposed memory excluded by default.
@pytest.mark.parametrize("status", [MemoryStatus.DEPRECATED,
                                    MemoryStatus.SUPERSEDED,
                                    MemoryStatus.CONTRADICTED])
def test_archived_excluded(enabled, status):
    store = InMemoryMemoryStore()
    m = _active(store, MemoryScope.PROJECT, MemoryType.CONTINUITY_FACT,
                "archived detail", project_id="p1")
    _set_status(store, m, status)
    text = _user_text(assistant.build_messages(
        "detail", "scene",
        memory_context_params={"store": store, "project_id": "p1"}))
    assert "archived detail" not in text


def test_proposed_excluded(enabled):
    store = InMemoryMemoryStore()
    store.write_candidate(MemoryObject(           # proposed, never approved
        scope=MemoryScope.PROJECT, type=MemoryType.PROJECT_DECISION,
        content="tentative idea", project_id="p1"))
    text = _user_text(assistant.build_messages(
        "idea", "scene",
        memory_context_params={"store": store, "project_id": "p1"}))
    assert "tentative idea" not in text


# 13. Diagnostic mode can include warnings; default mode does not.
def test_diagnostic_includes_warnings(enabled_diag):
    store = InMemoryMemoryStore()
    _active(store, MemoryScope.PROJECT, MemoryType.PROJECT_DECISION,
            "canon fact", project_id="p1")
    text = _user_text(assistant.build_messages(
        "task", "scene",
        memory_context_params={"store": store, "project_id": "p1"}))
    # No provider selected → a warning is surfaced in diagnostic mode.
    assert "## Warnings / Exclusions" in text


def test_no_warnings_without_diagnostic(enabled):
    store = InMemoryMemoryStore()
    _active(store, MemoryScope.PROJECT, MemoryType.PROJECT_DECISION,
            "canon fact", project_id="p1")
    text = _user_text(assistant.build_messages(
        "task", "scene",
        memory_context_params={"store": store, "project_id": "p1"}))
    assert "## Warnings / Exclusions" not in text


# 14. Raw source events are never injected.
def test_no_raw_events(enabled):
    store = InMemoryMemoryStore()
    store.add_event(EventLogEntry(event_type="chat",
                                  content="RAW_EVENT_SHOULD_NOT_APPEAR",
                                  project_id="p1"))
    _active(store, MemoryScope.PROJECT, MemoryType.PROJECT_DECISION,
            "canon fact", project_id="p1")
    text = _user_text(assistant.build_messages(
        "task", "scene",
        memory_context_params={"store": store, "project_id": "p1"}))
    assert "RAW_EVENT_SHOULD_NOT_APPEAR" not in text


# 15. Secrets never appear (redacted).
def test_no_secrets(enabled):
    store = InMemoryMemoryStore()
    _active(store, MemoryScope.PROJECT, MemoryType.CONTINUITY_FACT,
            "api_key: sk-deadbeef12345678", project_id="p1")
    text = _user_text(assistant.build_messages(
        "task", "scene",
        memory_context_params={"store": store, "project_id": "p1"}))
    assert "sk-deadbeef" not in text


# 16. Raw audio paths never appear (redacted).
def test_no_audio_paths(enabled):
    store = InMemoryMemoryStore()
    _active(store, MemoryScope.PROJECT, MemoryType.CONTINUITY_FACT,
            "buffer saved to clip_01.wav", project_id="p1")
    text = _user_text(assistant.build_messages(
        "task", "scene",
        memory_context_params={"store": store, "project_id": "p1"}))
    assert "clip_01.wav" not in text


# 17. No memory write methods are called during prompt build.
def test_no_memory_writes(enabled):
    class SpyStore(InMemoryMemoryStore):
        def __init__(self):
            super().__init__()
            self.wrote = False

        def add_event(self, e):
            self.wrote = True
            return super().add_event(e)

        def write_candidate(self, m):
            self.wrote = True
            return super().write_candidate(m)

        def approve_candidate(self, i):
            self.wrote = True
            return super().approve_candidate(i)

        def update(self, *a, **k):
            self.wrote = True
            return super().update(*a, **k)

        def supersede(self, *a, **k):
            self.wrote = True
            return super().supersede(*a, **k)

    store = SpyStore()
    _active(store, MemoryScope.PROJECT, MemoryType.PROJECT_DECISION,
            "canon fact", project_id="p1")
    store.wrote = False                       # reset after setup
    assistant.build_messages(
        "task", "scene",
        memory_context_params={"store": store, "project_id": "p1"})
    assert store.wrote is False


# 18-19. Sync / GitHub are never invoked during prompt build.
def test_no_sync_or_github(enabled, monkeypatch):
    from logosforge.memory_arch import github_export, sync

    def boom(*a, **k):
        raise AssertionError("sync/github must not be called")

    monkeypatch.setattr(sync.MemorySyncService, "sync_memory_to_cloud", boom)
    monkeypatch.setattr(github_export.GitHubMemoryExportService,
                        "optional_sync_memory_to_github", boom)
    store = InMemoryMemoryStore()
    _active(store, MemoryScope.PROJECT, MemoryType.PROJECT_DECISION,
            "canon fact", project_id="p1")
    # No raise → neither was called.
    assistant.build_messages(
        "task", "scene",
        memory_context_params={"store": store, "project_id": "p1"})


# 20. Provider request shape is unchanged when disabled.
def test_request_shape_unchanged_disabled(disabled):
    msgs = assistant.build_messages(
        "Do X", "scene",
        memory_context_params={"store": InMemoryMemoryStore()})
    assert [m["role"] for m in msgs] == ["system", "user"]
    assert all(isinstance(m["content"], str) for m in msgs)


# 21. Provider request shape stays compatible when enabled.
def test_request_shape_compatible_enabled(enabled):
    store = InMemoryMemoryStore()
    _active(store, MemoryScope.PROJECT, MemoryType.PROJECT_DECISION,
            "canon fact", project_id="p1")
    msgs = assistant.build_messages(
        "task", "scene",
        memory_context_params={"store": store, "project_id": "p1"})
    assert [m["role"] for m in msgs] == ["system", "user"]
    assert all(isinstance(m["content"], str) for m in msgs)


# 22. Context builder failure falls back to no block (assistant not blocked).
def test_builder_failure_falls_back(enabled):
    class BrokenStore(InMemoryMemoryStore):
        def search(self, *a, **k):
            raise RuntimeError("boom")

    base = assistant.build_messages("task", "scene")
    out = assistant.build_messages(
        "task", "scene",
        memory_context_params={"store": BrokenStore(), "project_id": "p1"})
    assert out == base                         # degraded safely


# 23. Missing store falls back safely.
def test_missing_store_falls_back(enabled):
    base = assistant.build_messages("task", "scene")
    out = assistant.build_messages(
        "task", "scene", memory_context_params={"project_id": "p1"})
    assert out == base


# 24. Missing project_id skips project memory but keeps user/assistant.
def test_missing_project_id_skips_project(enabled):
    store = InMemoryMemoryStore()
    _active(store, MemoryScope.PROJECT, MemoryType.PROJECT_DECISION,
            "project canon", project_id="p1")
    _active(store, MemoryScope.USER, MemoryType.PREFERENCE,
            "user pref", user_id="u1")
    _active(store, MemoryScope.ASSISTANT, MemoryType.ASSISTANT_RULE,
            "assistant rule")
    text = _user_text(assistant.build_messages(
        "task", "scene",
        memory_context_params={"store": store, "user_id": "u1"}))  # no project_id
    assert "## Project Memory" not in text and "project canon" not in text
    assert "user pref" in text and "assistant rule" in text


# 25. Helper is_enabled/diagnostics default to False from settings.
def test_flags_default_false():
    # Defaults must be off so the integration is opt-in.
    from logosforge.settings import DEFAULTS
    assert DEFAULTS["assistant_memory_context_enabled"] is False
    assert DEFAULTS["assistant_memory_context_diagnostics_enabled"] is False
