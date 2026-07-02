"""Logos Phase 3 — section-aware adaptive Logos for PSYKE/Plot/Timeline/Graph.

Covers: per-section context capture, adaptive action registry, PSYKE
apply-capable operations (notes/progression/relation) with validation, the
suggestion-only contract for Plot/Timeline/Graph, no provider duplication, and
that mutations require confirmation (no apply before confirm). AssistantPanel /
Dock and Manuscript/Outline Logos are exercised separately and must stay green.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.logos import (
    build_logos_context,
    list_actions_for_section,
    operations as ops,
)
from logosforge.logos.actions import get_action
from logosforge.logos.result import LogosResult


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
    alice = db.create_psyke_entry(pid, "Alice", "character", notes="hero").id
    theme = db.create_psyke_entry(pid, "Justice", "theme").id
    sid = db.create_scene(pid, "Opening", act="Act I", plotline="Main").id
    return db, pid, alice, theme, sid


# -- Action registry adapts per section --------------------------------------


@pytest.mark.parametrize("section,expected", [
    ("PSYKE", {"explain_entry_role", "suggest_details", "suggest_progression",
               "suggest_relations", "counterpart_critique"}),
    ("Plot", {"explain_plot_function", "identify_weak_conflict",
              "suggest_setup_payoff_link", "counterpart_critique"}),
    ("Timeline", {"check_chronology", "check_pacing", "suggest_next_event",
                  "counterpart_critique"}),
    ("Graph", {"explain_node", "identify_missing_links", "suggest_psyke_relation",
               "counterpart_critique"}),
])
def test_section_actions_registered(section, expected):
    names = {a.name for a in list_actions_for_section(section)}
    assert expected <= names


def test_actions_do_not_bleed_across_sections():
    psyke = {a.name for a in list_actions_for_section("PSYKE")}
    plot = {a.name for a in list_actions_for_section("Plot")}
    assert "explain_entry_role" in psyke and "explain_entry_role" not in plot
    assert "explain_plot_function" in plot and "explain_plot_function" not in psyke


def test_all_phase3_actions_non_destructive():
    for section in ("PSYKE", "Plot", "Timeline", "Graph"):
        for action in list_actions_for_section(section):
            assert not action.destructive


# -- Context capture per section ---------------------------------------------


def test_psyke_context():
    db, pid, alice, _, _ = _project()
    ctx = build_logos_context(db, pid, section_name="PSYKE",
                              selected_psyke_entry_id=alice)
    assert ctx.section_name == "PSYKE"
    assert ctx.selected_psyke_entry_id == alice
    assert isinstance(ctx.to_dict(), dict)


def test_plot_context():
    db, pid, *_ = _project()
    ctx = build_logos_context(db, pid, section_name="Plot",
                              current_plot_block_id="Main")
    assert ctx.current_plot_block_id == "Main"


def test_timeline_context():
    db, pid, _, _, sid = _project()
    ctx = build_logos_context(db, pid, section_name="Timeline",
                              current_timeline_event_id=sid)
    assert ctx.current_timeline_event_id == sid


def test_graph_context():
    db, pid, alice, _, _ = _project()
    ctx = build_logos_context(
        db, pid, section_name="Graph",
        current_graph_node_id=f"PSYKE:{alice}", current_graph_node_type="PSYKE",
        current_graph_neighbors=["Scene:1"], linked_psyke_entry_ids=[alice],
    )
    assert ctx.current_graph_node_id == f"PSYKE:{alice}"
    assert ctx.current_graph_neighbors == ["Scene:1"]
    assert ctx.linked_psyke_entry_ids == [alice]


def test_context_has_no_secrets():
    db, pid, alice, _, _ = _project()
    ctx = build_logos_context(db, pid, section_name="PSYKE",
                              selected_psyke_entry_id=alice)
    blob = str(ctx.to_dict()).lower()
    assert "api_key" not in blob


# -- PSYKE proposed operations (apply-capable) -------------------------------


def test_psyke_generative_proposes_append_notes():
    db, pid, alice, _, _ = _project()
    ctx = build_logos_context(db, pid, section_name="PSYKE",
                              selected_psyke_entry_id=alice)
    proposed = ops.build_proposed_operations(db, ctx, get_action("suggest_details"), "Detail.")
    assert [o["operation"] for o in proposed] == [ops.OP_APPEND_PSYKE_NOTES]


def test_psyke_suggest_progression_proposes_progression():
    db, pid, alice, _, _ = _project()
    ctx = build_logos_context(db, pid, section_name="PSYKE",
                              selected_psyke_entry_id=alice)
    proposed = ops.build_proposed_operations(db, ctx, get_action("suggest_progression"), "Grows.")
    assert [o["operation"] for o in proposed] == [ops.OP_CREATE_PSYKE_PROGRESSION]


def test_psyke_diagnostic_is_suggestion_only():
    db, pid, alice, _, _ = _project()
    ctx = build_logos_context(db, pid, section_name="PSYKE",
                              selected_psyke_entry_id=alice)
    assert ops.build_proposed_operations(db, ctx, get_action("explain_entry_role"), "role") == []


def test_psyke_without_selected_entry_is_suggestion_only():
    db, pid, *_ = _project()
    ctx = build_logos_context(db, pid, section_name="PSYKE")
    assert ops.build_proposed_operations(db, ctx, get_action("suggest_details"), "x") == []


# -- Plot/Timeline/Graph remain suggestion-only ------------------------------


@pytest.mark.parametrize("section,kwargs,action", [
    ("Plot", {"current_plot_block_id": "Main"}, "suggest_scene_purpose"),
    ("Timeline", {"current_timeline_event_id": 1}, "suggest_event_summary"),
    ("Graph", {"current_graph_node_id": "Character:1"}, "suggest_relationship"),
])
def test_non_psyke_sections_suggestion_only(section, kwargs, action):
    db, pid, *_ = _project()
    ctx = build_logos_context(db, pid, section_name=section, **kwargs)
    assert ops.build_proposed_operations(db, ctx, get_action(action), "text") == []


# -- PSYKE apply (only via operations layer, after confirmation) -------------


def test_apply_append_notes_preserves_existing():
    db, pid, alice, _, _ = _project()
    out = ops.apply_logos_operation(
        db, pid, {"operation": ops.OP_APPEND_PSYKE_NOTES, "target": "psyke",
                  "payload": {"entry_id": alice, "note": "brave"}},
    )
    notes = db.get_psyke_entry_by_id(alice).notes
    assert out["ok"] and "brave" in notes and "hero" in notes  # appended, not replaced
    assert out["events"] == ["psyke_changed", "project_data_changed"]


def test_apply_create_progression():
    db, pid, alice, _, sid = _project()
    out = ops.apply_logos_operation(
        db, pid, {"operation": ops.OP_CREATE_PSYKE_PROGRESSION, "target": "psyke",
                  "payload": {"entry_id": alice, "text": "turns", "scene_id": sid}},
    )
    assert out["ok"] and len(db.get_psyke_progressions(alice)) == 1


def test_apply_create_relation_targets_psyke_source_of_truth():
    db, pid, alice, theme, _ = _project()
    out = ops.apply_logos_operation(
        db, pid, {"operation": ops.OP_CREATE_PSYKE_RELATION, "target": "psyke",
                  "payload": {"entry_id": alice, "related_entry_id": theme,
                              "relation_type": "thematic_echo"}},
    )
    # Relation persists in PSYKE (not a graph-only cache).
    assert out["ok"]
    related = db.get_typed_related_psyke_entries(alice)
    assert any(e.id == theme for e, _ in related)


# -- Operation validation ----------------------------------------------------


def test_psyke_relation_rejects_self_and_missing():
    assert ops.validate_operation(
        {"operation": ops.OP_CREATE_PSYKE_RELATION, "target": "psyke",
         "payload": {"entry_id": 1, "related_entry_id": 1}}
    )
    assert ops.validate_operation(
        {"operation": ops.OP_CREATE_PSYKE_RELATION, "target": "psyke",
         "payload": {"entry_id": 1}}
    )


def test_psyke_op_wrong_target_rejected():
    assert ops.validate_operation(
        {"operation": ops.OP_APPEND_PSYKE_NOTES, "target": "outline",
         "payload": {"entry_id": 1, "note": "x"}}
    )


def test_apply_validates_entry_exists():
    db, pid, *_ = _project()
    out = ops.apply_logos_operation(
        db, pid, {"operation": ops.OP_APPEND_PSYKE_NOTES, "target": "psyke",
                  "payload": {"entry_id": 99999, "note": "x"}},
    )
    assert out["ok"] is False


# -- Preview: no apply before confirmation -----------------------------------


def test_psyke_preview_returns_op_only_on_confirm():
    db, pid, alice, _, _ = _project()
    from logosforge.ui.logos.logos_apply_preview import LogosApplyPreview
    ctx = build_logos_context(db, pid, section_name="PSYKE", selected_psyke_entry_id=alice)
    result = LogosResult(
        ok=True, action="suggest_details", title="Suggest Details", message="A trait.",
        proposed_operations=[{"operation": ops.OP_APPEND_PSYKE_NOTES, "target": "psyke",
                              "payload": {"entry_id": alice, "note": "A trait."}}],
    )
    dlg = LogosApplyPreview(result, ctx)
    assert dlg.operation() is None             # nothing applied yet
    before = db.get_psyke_entry_by_id(alice).notes
    dlg._confirm_psyke_notes()                 # user confirms
    op = dlg.operation()
    assert op["operation"] == ops.OP_APPEND_PSYKE_NOTES
    # The dialog itself never mutated the DB.
    assert db.get_psyke_entry_by_id(alice).notes == before


# -- MainWindow apply orchestration ------------------------------------------


def _window():
    db = Database()
    pid = db.create_project("P", narrative_engine="novel").id
    alice = db.create_psyke_entry(pid, "Alice", "character", notes="hero").id
    from logosforge.ui.main_window import MainWindow
    win = MainWindow(db, pid)
    win.resize(1400, 900)
    return win, db, pid, alice


def test_mainwindow_psyke_apply_emits_psyke_changed(monkeypatch):
    win, db, pid, alice = _window()
    import logosforge.ui.logos.logos_apply_preview as prev
    from logosforge.project_events import get_event_bus
    fired = {"psyke": [], "data": 0}
    bus = get_event_bus()
    bus.psyke_changed.connect(lambda eid: fired["psyke"].append(eid))
    bus.project_data_changed.connect(lambda: fired.__setitem__("data", fired["data"] + 1))

    op = {"operation": ops.OP_APPEND_PSYKE_NOTES, "target": "psyke",
          "payload": {"entry_id": alice, "note": "confirmed note"}}
    monkeypatch.setattr(prev.LogosApplyPreview, "get_operation",
                        staticmethod(lambda r, c, parent=None: op))
    ctx = build_logos_context(db, pid, section_name="PSYKE", selected_psyke_entry_id=alice)
    result = LogosResult(ok=True, action="suggest_details", title="x", message="y",
                         proposed_operations=[op])
    win._logos_request_apply(result, ctx)
    assert "confirmed note" in db.get_psyke_entry_by_id(alice).notes
    assert fired["psyke"] == [alice] and fired["data"] >= 1


def test_mainwindow_cancel_no_mutation(monkeypatch):
    win, db, pid, alice = _window()
    import logosforge.ui.logos.logos_apply_preview as prev
    monkeypatch.setattr(prev.LogosApplyPreview, "get_operation",
                        staticmethod(lambda r, c, parent=None: None))  # Cancel
    ctx = build_logos_context(db, pid, section_name="PSYKE", selected_psyke_entry_id=alice)
    result = LogosResult(ok=True, action="suggest_details", title="x", message="y",
                         proposed_operations=[{"operation": ops.OP_APPEND_PSYKE_NOTES,
                                               "target": "psyke",
                                               "payload": {"entry_id": alice, "note": "z"}}])
    win._logos_request_apply(result, ctx)
    assert db.get_psyke_entry_by_id(alice).notes == "hero"  # unchanged


def test_assistant_unchanged_by_phase3():
    win, *_ = _window()
    assert hasattr(win, "_assistant_panel") and hasattr(win, "_assistant_dock")
    assert win._assistant_dock.panel is win._assistant_panel


# -- No provider/backend duplication -----------------------------------------


def test_logos_logic_package_has_no_second_provider_system():
    import pathlib
    import logosforge.logos as logos_pkg
    root = pathlib.Path(logos_pkg.__file__).parent
    forbidden = ("ProviderConfig(", "QComboBox", "ai_api_key", "get_manager(")
    for py in root.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{py.name} should not contain {token!r}"
