"""Part 1 — Outline delete / clear.

Per-node delete (Scene deletes the node; Act/Chapter detach their children,
preserving written text) and a whole-Outline clear that never deletes prose.
All destructive actions confirm; cancel leaves data unchanged.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.ui.plan_view import (
    PlanView,
    _is_placeholder_scene,
    _save_act_summary,
    _save_chapter_summary,
    build_plan_tree,
    clear_outline_structure,
)


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    import logosforge.gomckee_bridge as gb
    monkeypatch.setattr(gb, "is_gomckee_enabled", lambda: False, raising=False)
    yield
    settings._instance = None


def _proj(db):
    return db.create_project("P", narrative_engine="novel").id


def _yes(monkeypatch):
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)


def _cancel(monkeypatch):
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.No)
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: QMessageBox.StandardButton.Cancel)


# ==========================================================================
# Per-node delete
# ==========================================================================


def test_delete_selected_scene(monkeypatch):
    db = Database()
    pid = _proj(db)
    sid = db.create_scene(pid, "Scene", act="Act I", chapter="Ch1",
                          content="PROSE").id
    view = PlanView(db, pid)
    _yes(monkeypatch)
    view._delete_scene_dialog(sid)
    assert db.get_scene_by_id(sid) is None


def test_delete_chapter_detaches_children_preserving_text(monkeypatch):
    db = Database()
    pid = _proj(db)
    keep = db.create_scene(pid, "Real", act="Act I", chapter="Ch1",
                           content="KEEP ME").id
    view = PlanView(db, pid)
    _yes(monkeypatch)
    view._delete_chapter_dialog("Ch1")
    s = db.get_scene_by_id(keep)
    assert s is not None                      # scene survives
    assert s.content == "KEEP ME"             # body preserved
    assert (s.chapter or "") == ""            # detached from chapter


def test_delete_act_detaches_children_preserving_text(monkeypatch):
    db = Database()
    pid = _proj(db)
    keep = db.create_scene(pid, "Real", act="Act I", chapter="Ch1",
                           content="KEEP ME").id
    view = PlanView(db, pid)
    _yes(monkeypatch)
    view._delete_act_dialog("Act I")
    s = db.get_scene_by_id(keep)
    assert s is not None and s.content == "KEEP ME"
    assert (s.act or "") == ""


def test_cancel_delete_leaves_data_unchanged(monkeypatch):
    db = Database()
    pid = _proj(db)
    sid = db.create_scene(pid, "Scene", act="Act I", chapter="Ch1",
                          content="PROSE").id
    view = PlanView(db, pid)
    _cancel(monkeypatch)
    view._delete_scene_dialog(sid)
    view._delete_chapter_dialog("Ch1")
    view._delete_act_dialog("Act I")
    s = db.get_scene_by_id(sid)
    assert s is not None and s.content == "PROSE"
    assert s.act == "Act I" and s.chapter == "Ch1"


# ==========================================================================
# Clear whole Outline (safe)
# ==========================================================================


def test_placeholder_detection():
    db = Database()
    pid = _proj(db)
    ph = db.get_scene_by_id(
        db.create_scene(pid, "Untitled Scene", act="Act I", chapter="Ch1").id
    )
    real = db.get_scene_by_id(
        db.create_scene(pid, "Untitled Scene", content="prose").id
    )
    named = db.get_scene_by_id(db.create_scene(pid, "Important").id)
    assert _is_placeholder_scene(ph) is True
    assert _is_placeholder_scene(real) is False     # has body
    assert _is_placeholder_scene(named) is False     # has a real title


def test_clear_outline_structure_safe():
    db = Database()
    pid = _proj(db)
    ph = db.create_scene(pid, "Untitled Scene", act="Act I", chapter="Ch1").id
    body = db.create_scene(pid, "Real", act="Act I", chapter="Ch1",
                           content="PROSE").id
    _save_act_summary(db, pid, "Act I", "act sum")
    _save_chapter_summary(db, pid, "Ch1", "ch sum")

    res = clear_outline_structure(db, pid)

    assert res == {"deleted": 1, "detached": 1}
    assert db.get_scene_by_id(ph) is None              # placeholder removed
    kept = db.get_scene_by_id(body)
    assert kept is not None and kept.content == "PROSE"  # text preserved
    assert (kept.act or "") == "" and (kept.chapter or "") == ""
    settings = db.get_project_settings(pid)
    assert settings.get("act_summaries") == {}
    assert settings.get("chapter_summaries") == {}
    # "Act I" / "Ch1" structure is gone (scene only reachable under Unsorted).
    acts = [a for a, _ in build_plan_tree(db, pid)]
    assert "Act I" not in acts


def test_clear_outline_via_dialog_confirmed(monkeypatch):
    db = Database()
    pid = _proj(db)
    db.create_scene(pid, "Untitled Scene", act="Act I", chapter="Ch1")
    view = PlanView(db, pid)
    _yes(monkeypatch)
    view._clear_outline_dialog()
    assert "Act I" not in [a for a, _ in build_plan_tree(db, pid)]


def test_clear_outline_cancel_keeps_structure(monkeypatch):
    db = Database()
    pid = _proj(db)
    db.create_scene(pid, "Real", act="Act I", chapter="Ch1", content="PROSE")
    view = PlanView(db, pid)
    _cancel(monkeypatch)
    view._clear_outline_dialog()
    assert "Act I" in [a for a, _ in build_plan_tree(db, pid)]


def test_outline_refreshes_after_delete(monkeypatch):
    db = Database()
    pid = _proj(db)
    db.create_scene(pid, "Real", act="Act I", chapter="Ch1", content="PROSE")
    view = PlanView(db, pid)
    assert "Act I" in [a for a, _ in build_plan_tree(db, pid)]
    _yes(monkeypatch)
    view._clear_outline_dialog()
    # PlanView.refresh() was invoked; tree no longer has the named act.
    assert "Act I" not in [a for a, _ in build_plan_tree(db, pid)]
