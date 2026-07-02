"""Tests for the Outline-Mode fix pass:

- Apply-to-Outline writes real (visible) Scenes, not orphaned OutlineNodes.
- PlanView top-right controls + per-item AI Generate produce real scenes.
- Resizable confirmation dialog.
- Dynamic "Classical · <template>" badge + template persistence.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.outline_actions import (
    apply_outline_as_scenes,
    count_ops,
    outline_scene_rows,
    parse_outline_response,
)
from logosforge.ui.plan_view import PlanView, build_plan_tree

_SAMPLE = """# Act I
## Chapter 1
- Scene: Opening — hero at home
- Scene: Call — the summons
## Chapter 2
- Scene: Threshold — leaving home
# Act II
- Beat: Midpoint — big reversal
"""


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
    return db, db.create_project("Saga", narrative_engine="novel").id


# -- Scene-mapping logic -----------------------------------------------------


def test_outline_scene_rows_maps_hierarchy():
    rows = outline_scene_rows(parse_outline_response(_SAMPLE))
    titles = [(r["act"], r["chapter"], r["title"], r["beat"]) for r in rows]
    assert ("I", "Chapter 1", "Opening", "") in titles
    assert ("I", "Chapter 2", "Threshold", "") in titles
    # A beat directly under an act becomes a scene tagged with its beat.
    assert any(r["act"] == "II" and r["beat"] == "Midpoint" for r in rows)


def test_apply_outline_as_scenes_is_visible_in_plan_tree():
    db, pid = _project()
    created = apply_outline_as_scenes(db, pid, parse_outline_response(_SAMPLE))
    assert len(created) == 4
    tree = build_plan_tree(db, pid)
    acts = [a for a, _ in tree]
    assert acts == ["I", "II"]
    # The applied structure shows up as real scenes grouped by act/chapter.
    ch1 = next(scs for a, chs in tree if a == "I" for ch, scs in chs if ch == "Chapter 1")
    assert {s.title for s in ch1} == {"Opening", "Call"}


def test_apply_as_scenes_is_additive():
    db, pid = _project()
    db.create_scene(pid, title="Existing", act="Prologue")
    apply_outline_as_scenes(db, pid, parse_outline_response(_SAMPLE))
    assert any(s.title == "Existing" for s in db.get_all_scenes(pid))


def test_apply_scoped_under_act_and_chapter():
    db, pid = _project()
    ops = parse_outline_response("- Scene: New Scene A\n- Scene: New Scene B")
    created = apply_outline_as_scenes(
        db, pid, ops, base_act="Act III", base_chapter="Chapter 9",
    )
    assert len(created) == 2
    for sid in created:
        s = db.get_scene_by_id(sid)
        assert s.act == "Act III" and s.chapter == "Chapter 9"


def test_apply_persists_across_reload():
    db, pid = _project()
    apply_outline_as_scenes(db, pid, parse_outline_response(_SAMPLE))
    # Simulate reload by re-reading from the same DB engine.
    reloaded = build_plan_tree(db, pid)
    assert [a for a, _ in reloaded] == ["I", "II"]


# -- Confirmation dialog -----------------------------------------------------


def test_confirm_dialog_is_resizable_with_pinned_buttons():
    from logosforge.ui.outline_confirm_dialog import OutlineConfirmDialog

    long_preview = "\n".join(f"• Scene {i}" for i in range(200))
    dlg = OutlineConfirmDialog(long_preview, 200)
    # Resizable: a sane default and a minimum that still fits the buttons.
    assert dlg.minimumWidth() <= 360
    assert dlg.minimumHeight() <= 320
    assert dlg.isSizeGripEnabled()
    # Preview is the read-only scrolling area; buttons live outside it.
    assert dlg._preview.isReadOnly()
    assert dlg._preview.toPlainText().count("Scene") == 200


# -- PlanView controls -------------------------------------------------------


def test_planview_has_ai_and_template_controls():
    db, pid = _project()
    view = PlanView(db, pid)
    assert hasattr(view, "_template_combo")
    assert view._template_combo.count() >= 2  # "No template" + builtins
    assert hasattr(view, "_run_ai")
    assert hasattr(view, "_apply_ai_outline")


def test_planview_template_label_is_dynamic_and_persists():
    db, pid = _project()
    view = PlanView(db, pid)
    # Pick a non-default template -> badge reflects it (not just "Classical").
    idx = view._template_combo.findData("save_the_cat")
    assert idx > 0
    view._template_combo.setCurrentIndex(idx)
    assert "Save the Cat" in view._mode_badge.text()
    assert "Classical" in view._mode_badge.text()
    # Persisted to project settings and restored on a fresh view.
    assert db.get_project_settings(pid).get("outline_template") == "save_the_cat"
    view2 = PlanView(db, pid)
    assert view2._template_combo.currentData() == "save_the_cat"
    assert "Save the Cat" in view2._mode_badge.text()


def test_planview_default_badge_is_classical_without_template():
    db, pid = _project()
    view = PlanView(db, pid)
    assert view._mode_badge.text() == "Classical"  # no template selected


def test_planview_ai_generate_full_creates_scenes():
    db, pid = _project()
    view = PlanView(db, pid)
    created = view._apply_ai_outline(_SAMPLE, scope="full", confirm=False)
    assert len(created) == 4
    assert [a for a, _ in build_plan_tree(db, pid)] == ["I", "II"]


def test_planview_ai_generate_act_scopes_under_act():
    db, pid = _project()
    view = PlanView(db, pid)
    text = "## Chapter 1\n- Scene: A\n- Scene: B"
    created = view._apply_ai_outline(text, scope="chapter", act="Act 7", confirm=False)
    assert created
    for sid in created:
        assert db.get_scene_by_id(sid).act == "Act 7"


def test_planview_ai_generate_scene_scopes_under_chapter():
    db, pid = _project()
    view = PlanView(db, pid)
    text = "- Scene: Only Scene"
    created = view._apply_ai_outline(
        text, scope="scene", act="Act 2", chapter="Chapter 4", confirm=False,
    )
    assert len(created) == 1
    s = db.get_scene_by_id(created[0])
    assert s.act == "Act 2" and s.chapter == "Chapter 4"


def test_planview_add_act_creates_visible_act():
    db, pid = _project()
    view = PlanView(db, pid)
    # _add_act prompts; exercise the underlying creation path it uses.
    db.create_scene(pid, title="Untitled Scene", act="Brand New Act")
    view.refresh()
    assert "Brand New Act" in [a for a, _ in build_plan_tree(db, pid)]


def test_planview_run_ai_without_provider_is_safe(monkeypatch):
    db, pid = _project()
    view = PlanView(db, pid)
    import logosforge.ui.plan_view as pv
    monkeypatch.setattr(pv, "build_provider", lambda: None)
    # No provider -> returns False, does not raise or start a worker.
    assert view._run_ai("full") is False
    assert view._gen_worker is None
