"""Logos Phase 2 — controlled apply/replace operations.

Covers the structured operation schema, validation, proposed-operation building,
apply via the existing write paths (manuscript editor + scene service), the
preview dialog (no execution before confirmation), and the MainWindow apply
orchestration (events + dirty + no mutation on cancel). AssistantPanel/Dock are
exercised separately and must stay green.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QTextEdit

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.logos import build_logos_context, operations as ops
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
    sid = db.create_scene(
        pid, "Opening", act="Act I", chapter="Ch1",
        content="He said nothing.", summary="intro",
    ).id
    return db, pid, sid


def _editor_with_selection(text: str, start: int, end: int) -> QTextEdit:
    ed = QTextEdit()
    ed.setPlainText(text)
    c = ed.textCursor()
    c.setPosition(start)
    c.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    ed.setTextCursor(c)
    return ed


# -- Validation --------------------------------------------------------------


def test_unknown_operation_rejected():
    assert ops.validate_operation({"operation": "danger", "target": "x", "payload": {}})


def test_wrong_target_rejected():
    assert ops.validate_operation(
        {"operation": ops.OP_REPLACE_SELECTION, "target": "outline", "payload": {"replacement_text": "x"}}
    )


def test_replace_requires_nonempty_text():
    assert ops.validate_operation(
        {"operation": ops.OP_REPLACE_SELECTION, "target": "manuscript", "payload": {"replacement_text": "  "}}
    )
    assert ops.validate_operation(
        {"operation": ops.OP_REPLACE_SELECTION, "target": "manuscript", "payload": {"replacement_text": "ok"}}
    ) is None


def test_insert_requires_nonempty_text():
    assert ops.validate_operation(
        {"operation": ops.OP_INSERT_AFTER, "target": "manuscript", "payload": {"text": ""}}
    )


def test_create_requires_title():
    assert ops.validate_operation(
        {"operation": ops.OP_CREATE_OUTLINE_NODE, "target": "outline", "payload": {"title": ""}}
    )
    assert ops.validate_operation(
        {"operation": ops.OP_CREATE_OUTLINE_NODE, "target": "outline", "payload": {"title": "Beat"}}
    ) is None


def test_update_summary_requires_scene_id_and_text():
    assert ops.validate_operation(
        {"operation": ops.OP_UPDATE_OUTLINE_SUMMARY, "target": "outline", "payload": {"summary": "x"}}
    )
    assert ops.validate_operation(
        {"operation": ops.OP_UPDATE_OUTLINE_SUMMARY, "target": "outline", "payload": {"scene_id": 1, "summary": ""}}
    )


def test_update_validates_node_exists():
    db, pid, _ = _project()
    op = {"operation": ops.OP_UPDATE_OUTLINE_SUMMARY, "target": "outline",
          "payload": {"scene_id": 99999, "summary": "x"}}
    assert ops.validate_operation_against_db(db, pid, op)  # missing node -> error


# -- Build proposed operations -----------------------------------------------


def test_manuscript_generative_proposes_replace_and_insert():
    db, pid, sid = _project()
    ctx = build_logos_context(db, pid, section_name="Manuscript",
                              current_scene_id=sid, selected_text="He said nothing.")
    proposed = ops.build_proposed_operations(db, ctx, get_action("rewrite_options"), "New.")
    names = {o["operation"] for o in proposed}
    assert names == {ops.OP_REPLACE_SELECTION, ops.OP_INSERT_AFTER}


def test_manuscript_diagnostic_proposes_nothing():
    db, pid, sid = _project()
    ctx = build_logos_context(db, pid, section_name="Manuscript",
                              current_scene_id=sid, selected_text="x")
    assert ops.build_proposed_operations(db, ctx, get_action("explain_selection"), "analysis") == []


def test_manuscript_without_selection_proposes_nothing():
    db, pid, sid = _project()
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    assert ops.build_proposed_operations(db, ctx, get_action("rewrite_options"), "x") == []


def test_outline_proposes_create_and_update():
    db, pid, sid = _project()
    ctx = build_logos_context(db, pid, section_name="Outline", current_scene_id=sid,
                              outline_node_label="Opening", outline_node_kind="scene")
    proposed = ops.build_proposed_operations(db, ctx, get_action("summarize_node"), "Summary.")
    names = {o["operation"] for o in proposed}
    assert ops.OP_CREATE_OUTLINE_NODE in names
    assert ops.OP_UPDATE_OUTLINE_SUMMARY in names


# -- Apply: manuscript -------------------------------------------------------


def test_apply_replace_requires_selection():
    ed = QTextEdit(); ed.setPlainText("abc")  # no selection
    out = ops.apply_logos_operation(
        None, 1, {"operation": ops.OP_REPLACE_SELECTION, "target": "manuscript",
                  "payload": {"replacement_text": "x"}}, editor=ed,
    )
    assert out["ok"] is False


def test_apply_replace_replaces_selection_undo_safe():
    ed = _editor_with_selection("Hello world here", 6, 11)
    out = ops.apply_logos_operation(
        None, 1, {"operation": ops.OP_REPLACE_SELECTION, "target": "manuscript",
                  "payload": {"replacement_text": "PLANET"}}, editor=ed,
    )
    assert out["ok"] and ed.toPlainText() == "Hello PLANET here"
    assert "scene_changed" in out["events"]
    ed.undo()
    assert ed.toPlainText() == "Hello world here"  # undo intact


def test_apply_insert_after_selection():
    ed = _editor_with_selection("Line one", 0, 8)
    out = ops.apply_logos_operation(
        None, 1, {"operation": ops.OP_INSERT_AFTER, "target": "manuscript",
                  "payload": {"text": "Added"}}, editor=ed,
    )
    assert out["ok"] and "Added" in ed.toPlainText()
    assert ed.toPlainText().startswith("Line one")  # original preserved


def test_apply_manuscript_without_editor_fails_cleanly():
    out = ops.apply_logos_operation(
        None, 1, {"operation": ops.OP_INSERT_AFTER, "target": "manuscript",
                  "payload": {"text": "x"}}, editor=None,
    )
    assert out["ok"] is False


# -- Apply: outline ----------------------------------------------------------


def test_apply_create_outline_node():
    db, pid, _ = _project()
    before = len(db.get_all_scenes(pid))
    out = ops.apply_logos_operation(
        db, pid, {"operation": ops.OP_CREATE_OUTLINE_NODE, "target": "outline",
                  "payload": {"act": "Act I", "chapter": "Ch1", "title": "New Beat", "summary": "s"}},
    )
    assert out["ok"] and len(db.get_all_scenes(pid)) == before + 1
    assert "outline_changed" in out["events"]


def test_apply_update_summary_persists():
    db, pid, sid = _project()
    out = ops.apply_logos_operation(
        db, pid, {"operation": ops.OP_UPDATE_OUTLINE_SUMMARY, "target": "outline",
                  "payload": {"scene_id": sid, "summary": "Updated summary"}},
    )
    assert out["ok"] and db.get_scene_by_id(sid).summary == "Updated summary"


def test_apply_update_title_preserves_other_fields():
    db, pid, sid = _project()
    out = ops.apply_logos_operation(
        db, pid, {"operation": ops.OP_UPDATE_OUTLINE_TITLE, "target": "outline",
                  "payload": {"scene_id": sid, "title": "Renamed"}},
    )
    scene = db.get_scene_by_id(sid)
    assert out["ok"] and scene.title == "Renamed"
    assert scene.summary == "intro" and scene.act == "Act I"  # untouched


def test_apply_rejects_invalid_target_node():
    db, pid, _ = _project()
    out = ops.apply_logos_operation(
        db, pid, {"operation": ops.OP_UPDATE_OUTLINE_SUMMARY, "target": "outline",
                  "payload": {"scene_id": 99999, "summary": "x"}},
    )
    assert out["ok"] is False


# -- Preview dialog ----------------------------------------------------------


def test_preview_no_operation_before_confirmation():
    db, pid, sid = _project()
    from logosforge.ui.logos.logos_apply_preview import LogosApplyPreview
    ctx = build_logos_context(db, pid, section_name="Manuscript",
                              current_scene_id=sid, selected_text="world")
    result = LogosResult(
        ok=True, action="rewrite_options", title="Rewrite Options", message="PLANET",
        proposed_operations=[{"operation": ops.OP_REPLACE_SELECTION, "target": "manuscript",
                              "payload": {"replacement_text": "PLANET"}}],
    )
    dlg = LogosApplyPreview(result, ctx)
    assert dlg.operation() is None  # nothing chosen yet
    dlg._confirm_replace()          # user clicks Apply Replace
    op = dlg.operation()
    assert op is not None and op["operation"] == ops.OP_REPLACE_SELECTION
    assert op["payload"]["replacement_text"] == "PLANET"


def test_preview_outline_create_and_update_buttons():
    db, pid, sid = _project()
    from logosforge.ui.logos.logos_apply_preview import LogosApplyPreview
    ctx = build_logos_context(db, pid, section_name="Outline", current_scene_id=sid,
                              outline_node_label="Opening", outline_node_kind="scene")
    result = LogosResult(
        ok=True, action="summarize_node", title="Summarize Node", message="A summary.",
        proposed_operations=ops.build_proposed_operations(db, ctx, get_action("summarize_node"), "A summary."),
    )
    dlg = LogosApplyPreview(result, ctx)
    dlg._confirm_update_summary()
    op = dlg.operation()
    assert op["operation"] == ops.OP_UPDATE_OUTLINE_SUMMARY
    assert op["payload"]["scene_id"] == sid


# -- MainWindow apply orchestration ------------------------------------------


def _window():
    db = Database()
    pid = db.create_project("P", narrative_engine="novel").id
    sid = db.create_scene(pid, "Opening", act="Act I", chapter="Ch1",
                          content="Hello world here", summary="old").id
    from logosforge.ui.main_window import MainWindow
    win = MainWindow(db, pid)
    win.resize(1400, 900)
    return win, db, pid, sid


def test_mainwindow_apply_outline_emits_events_and_persists(monkeypatch):
    win, db, pid, sid = _window()
    import logosforge.ui.logos.logos_apply_preview as prev
    from logosforge.project_events import get_event_bus
    fired = {"outline": 0, "data": 0}
    bus = get_event_bus()
    bus.outline_changed.connect(lambda: fired.__setitem__("outline", fired["outline"] + 1))
    bus.project_data_changed.connect(lambda: fired.__setitem__("data", fired["data"] + 1))

    op = {"operation": ops.OP_UPDATE_OUTLINE_SUMMARY, "target": "outline",
          "payload": {"scene_id": sid, "summary": "Confirmed summary"}}
    monkeypatch.setattr(prev.LogosApplyPreview, "get_operation",
                        staticmethod(lambda r, c, parent=None: op))
    ctx = build_logos_context(db, pid, section_name="Outline", current_scene_id=sid)
    result = LogosResult(ok=True, action="summarize_node", title="x", message="y",
                         proposed_operations=[op])
    win._logos_request_apply(result, ctx)
    assert db.get_scene_by_id(sid).summary == "Confirmed summary"
    assert fired["outline"] >= 1 and fired["data"] >= 1


def test_mainwindow_apply_cancel_no_mutation(monkeypatch):
    win, db, pid, sid = _window()
    import logosforge.ui.logos.logos_apply_preview as prev
    monkeypatch.setattr(prev.LogosApplyPreview, "get_operation",
                        staticmethod(lambda r, c, parent=None: None))  # Cancel
    ctx = build_logos_context(db, pid, section_name="Outline", current_scene_id=sid)
    result = LogosResult(ok=True, action="summarize_node", title="x", message="y",
                         proposed_operations=[{"operation": ops.OP_UPDATE_OUTLINE_SUMMARY,
                                               "target": "outline",
                                               "payload": {"scene_id": sid, "summary": "z"}}])
    win._logos_request_apply(result, ctx)
    assert db.get_scene_by_id(sid).summary == "old"  # unchanged


def test_mainwindow_apply_manuscript_replace(monkeypatch):
    win, db, pid, sid = _window()
    import logosforge.ui.logos.logos_apply_preview as prev
    ed = _editor_with_selection("Hello world here", 6, 11)
    win._detect_active_editor = lambda: ed
    op = {"operation": ops.OP_REPLACE_SELECTION, "target": "manuscript",
          "payload": {"replacement_text": "PLANET"}}
    monkeypatch.setattr(prev.LogosApplyPreview, "get_operation",
                        staticmethod(lambda r, c, parent=None: op))
    ctx = build_logos_context(db, pid, section_name="Manuscript",
                              current_scene_id=sid, selected_text="world")
    result = LogosResult(ok=True, action="rewrite_options", title="x", message="PLANET",
                         proposed_operations=[op])
    win._logos_request_apply(result, ctx)
    assert ed.toPlainText() == "Hello PLANET here"


def test_assistant_panel_and_dock_unchanged():
    win, *_ = _window()
    assert hasattr(win, "_assistant_panel") and hasattr(win, "_assistant_dock")
    assert win._assistant_dock.panel is win._assistant_panel


# -- Toolbar apply affordance ------------------------------------------------


def test_toolbar_apply_button_enabled_only_with_operations():
    from logosforge.ui.logos.logos_toolbar import LogosToolbar
    from logosforge.logos.controller import LogosController
    db, pid, sid = _project()
    captured = []
    tb = LogosToolbar(
        LogosController(db), lambda: build_logos_context(db, pid, section_name="Manuscript"),
        on_request_apply=lambda res, ctx: captured.append(res),
    )
    # Diagnostic result -> no ops -> Apply disabled.
    tb._render(LogosResult(ok=True, action="explain_selection", title="x", message="m"))
    assert not tb._apply_btn.isEnabled()
    # Result with ops -> Apply enabled, click forwards to handler.
    tb._last_context = object()
    tb._render(LogosResult(ok=True, action="rewrite_options", title="x", message="m",
                           proposed_operations=[{"operation": ops.OP_REPLACE_SELECTION,
                                                 "target": "manuscript",
                                                 "payload": {"replacement_text": "m"}}]))
    assert tb._apply_btn.isEnabled()
    tb._request_apply()
    assert len(captured) == 1
