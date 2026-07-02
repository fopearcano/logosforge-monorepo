"""Logos Phase 0 — foundation tests.

Verifies the inline Logos layer: context serialization, action registry,
controller returning structured results, that Logos rides the *shared* Assistant
backend (no own provider/client), Manuscript/Outline context capture, and that
Phase 0 performs no database mutation. Existing AssistantPanel tests are run
separately and must remain green.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.logos import (
    FUTURE_ACTIONS,
    LogosContext,
    LogosController,
    LogosResult,
    build_logos_context,
    describe_all_actions,
    list_actions,
    list_actions_for_section,
)


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path, raising=False)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json", raising=False)
    yield
    settings._instance = None


def _project():
    db = Database()
    pid = db.create_project("Saga", narrative_engine="novel").id
    sid = db.create_scene(
        pid, "Opening", act="Act I", content="The hero walks into the rain.",
        summary="intro",
    ).id
    return db, pid, sid


# -- Context -----------------------------------------------------------------


def test_context_is_serializable_and_secret_free():
    db, pid, sid = _project()
    ctx = build_logos_context(
        db, pid, section_name="Manuscript", current_scene_id=sid,
        selected_text="hello world",
    )
    d = ctx.to_dict()
    assert isinstance(d, dict)
    assert d["project_id"] == pid
    assert d["narrative_engine"] == "novel"
    # No secret/provider keys ever leak into the context.
    blob = str(d).lower()
    assert "api_key" not in blob and "ai_api_key" not in blob


def test_context_excerpt_is_capped():
    db, pid, _ = _project()
    ctx = build_logos_context(db, pid, cursor_text_excerpt="x" * 5000)
    assert len(ctx.cursor_text_excerpt) <= 600


def test_context_debug_summary_truncates_selection():
    db, pid, sid = _project()
    ctx = build_logos_context(
        db, pid, section_name="Manuscript", current_scene_id=sid,
        selected_text="y" * 200,
    )
    summary = ctx.debug_summary()
    assert "Manuscript" in summary
    assert "api" not in summary.lower()


# -- Action registry ---------------------------------------------------------


def test_registry_lists_phase1_actions():
    names = {a.name for a in list_actions()}
    assert {
        # Manuscript
        "explain_selection", "suggest_revision", "rewrite_options",
        "expand", "compress", "improve_dialogue", "improve_subtext",
        "identify_weakness",
        # Outline
        "summarize_node", "identify_structure_problem", "suggest_next_beat",
        "strengthen_conflict", "check_template_fit",
        # Cross-section
        "counterpart_critique",
    } <= names
    # The binding Phase 1 invariant: everything registered is non-destructive.
    assert all(not a.destructive for a in list_actions())
    assert all(a.category in ("diagnostic", "generative") for a in list_actions())


def test_future_destructive_actions_are_not_registered():
    registered = {a.name for a in list_actions()}
    for future in FUTURE_ACTIONS:
        assert future not in registered


def test_actions_are_section_scoped():
    man = {a.name for a in list_actions_for_section("Manuscript")}
    out = {a.name for a in list_actions_for_section("Outline")}
    assert "explain_selection" in man and "explain_selection" not in out
    assert "identify_structure_problem" in out and "identify_structure_problem" not in man
    assert "summarize_node" in out and "summarize_node" not in man
    # Counterpart Critique is offered in both sections.
    assert "counterpart_critique" in man and "counterpart_critique" in out


def test_describe_all_actions_shape():
    described = describe_all_actions()
    assert described and all("name" in d and "category" in d for d in described)


# -- Controller --------------------------------------------------------------


def test_controller_returns_structured_result_with_injected_chat():
    db, pid, sid = _project()
    ctrl = LogosController(
        db,
        provider_resolver=lambda: object(),
        chat_fn=lambda messages, provider: "Reads well.\n- Tighten verb\n- Add sensory beat",
    )
    ctx = build_logos_context(
        db, pid, section_name="Manuscript", current_scene_id=sid,
        selected_text="The hero walks into the rain.",
    )
    res = ctrl.run(ctx, "explain_selection")
    assert isinstance(res, LogosResult)
    assert res.ok and res.action == "explain_selection"
    assert res.suggestions == ["Tighten verb", "Add sensory beat"]
    assert res.proposed_operations == []  # Phase 0: never auto-apply


def test_controller_uses_shared_backend_not_own_client():
    """Logos must call the injected (shared) resolver + chat fn, proving it
    does not instantiate its own provider/client."""
    db, pid, sid = _project()
    used = {"resolver": 0, "chat": 0}

    def resolver():
        used["resolver"] += 1
        return object()

    def chat(messages, provider):
        used["chat"] += 1
        assert isinstance(messages, list)  # built via shared build_messages
        return "ok"

    ctrl = LogosController(db, provider_resolver=resolver, chat_fn=chat)
    ctx = build_logos_context(
        db, pid, section_name="Manuscript", current_scene_id=sid,
        selected_text="x",
    )
    ctrl.run(ctx, "explain_selection")
    assert used["resolver"] == 1 and used["chat"] == 1


def test_controller_offline_returns_safe_preview():
    db, pid, sid = _project()
    ctrl = LogosController(db, provider_resolver=lambda: None)  # no provider
    ctx = build_logos_context(
        db, pid, section_name="Manuscript", current_scene_id=sid,
        selected_text="x",
    )
    res = ctrl.run(ctx, "explain_selection")
    assert res.ok and res.proposed_operations == []
    assert res.suggestions  # local preview bits


def test_controller_blocks_future_and_unknown_actions():
    db, pid, _ = _project()
    ctrl = LogosController(db, provider_resolver=lambda: object(),
                           chat_fn=lambda m, p: "x")
    ctx = build_logos_context(db, pid, section_name="Manuscript")
    for name in ("rewrite_selection", "does_not_exist"):
        res = ctrl.run(ctx, name)
        assert not res.ok and res.error


def test_controller_requires_selection_where_needed():
    db, pid, sid = _project()
    ctrl = LogosController(db, provider_resolver=lambda: object(),
                           chat_fn=lambda m, p: "x")
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctrl.run(ctx, "explain_selection")  # no selection
    assert not res.ok and "select" in res.error.lower()


def test_controller_enforces_section_applicability():
    db, pid, sid = _project()
    ctrl = LogosController(db, provider_resolver=lambda: object(),
                           chat_fn=lambda m, p: "x")
    ctx = build_logos_context(db, pid, section_name="Outline", current_scene_id=sid)
    res = ctrl.run(ctx, "explain_selection")  # manuscript-only action
    assert not res.ok


def test_phase0_does_not_mutate_database():
    db, pid, sid = _project()
    before_scenes = len(db.get_all_scenes(pid))
    before_psyke = len(db.get_all_psyke_entries(pid))
    before_outline = len(db.get_outline_nodes(pid))
    ctrl = LogosController(
        db, provider_resolver=lambda: object(),
        chat_fn=lambda m, p: "diagnostics\n- one\n- two",
    )
    for section, action in (
        ("Manuscript", "identify_weakness"),
        ("Manuscript", "counterpart_critique"),
        ("Outline", "identify_structure_problem"),
        ("Outline", "summarize_node"),
    ):
        ctx = build_logos_context(db, pid, section_name=section, current_scene_id=sid)
        ctrl.run(ctx, action)
    assert len(db.get_all_scenes(pid)) == before_scenes
    assert len(db.get_all_psyke_entries(pid)) == before_psyke
    assert len(db.get_outline_nodes(pid)) == before_outline


def test_logos_logic_package_defines_no_provider_system():
    """The pure-logic logos package must not build a second provider system."""
    import pathlib
    import logosforge.logos as logos_pkg
    root = pathlib.Path(logos_pkg.__file__).parent
    forbidden = ("ProviderConfig(", "QComboBox", "ai_api_key", "get_manager(")
    for py in root.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{py.name} should not contain {token!r}"
