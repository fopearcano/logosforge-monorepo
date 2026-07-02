"""Outline content must never appear as Manuscript body.

Covers: (A) outline generation/apply writes structure fields only, never
scene.content; the parser drops the model's "A Complete Outline…" preamble so
it isn't added as an item; (B) the Manuscript renderer shows scene.content only
(neutral placeholder when empty), never summary/synopsis; (C) a conservative
repair that clears obvious historical contamination but keeps real prose;
(D) project-switch keeps manuscript/outline isolated.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.manuscript_repair import (
    repair_manuscript_contamination,
    scan_manuscript_contamination,
)
from logosforge.outline_actions import (
    apply_outline_as_scenes,
    outline_scene_rows,
    parse_outline_response,
    repair_outline_ops,
    validate_outline_ops,
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


_RESPONSE_WITH_PREAMBLE = """A Complete Outline for Your Novel

# Act 1: The Beginning
## Chapter 1: Dawn
- Scene: Hero wakes — establishes the ordinary world
- Scene: The summons — the call to adventure
"""


# ==========================================================================
# A. Generation writes structure only; preamble is dropped
# ==========================================================================


def test_repair_drops_outline_preamble_node():
    ops = parse_outline_response(_RESPONSE_WITH_PREAMBLE)
    assert ops[0].title == "A Complete Outline for Your Novel"  # parsed as node
    ops, warns = repair_outline_ops(ops)
    titles = [o.title for o in ops]
    assert "A Complete Outline for Your Novel" not in titles
    assert titles == ["Act 1"]
    # Warning now covers all non-structural drops (intros + meta-sections).
    assert any("non-structural" in w for w in warns)


def test_apply_outline_does_not_write_manuscript_body():
    db = Database()
    pid = db.create_project("P").id
    ops, _ = repair_outline_ops(parse_outline_response(_RESPONSE_WITH_PREAMBLE))
    assert validate_outline_ops(ops)[0]
    created = apply_outline_as_scenes(db, pid, ops)
    assert created
    # No created scene carries manuscript prose; planning lands in summary.
    for sid in created:
        s = db.get_scene_by_id(sid)
        assert (s.content or "") == ""
    # And no scene/title is the dropped preamble.
    titles = {s.title for s in db.get_all_scenes(pid)}
    assert "A Complete Outline for Your Novel" not in titles


def test_preamble_never_becomes_a_scene_row():
    ops, _ = repair_outline_ops(parse_outline_response(_RESPONSE_WITH_PREAMBLE))
    rows = outline_scene_rows(ops)
    assert all("complete outline" not in r["title"].lower() for r in rows)
    assert all("complete outline" not in r["act"].lower() for r in rows)


def test_real_top_level_scene_is_not_dropped_as_preamble():
    # A legitimate kind-less node that doesn't mention "outline" survives.
    ops = parse_outline_response("Opening Image\n- Scene: a")
    ops, _ = repair_outline_ops(ops)
    assert any(o.title == "Opening Image" for o in ops)


# ==========================================================================
# B. Manuscript renderer shows content only; placeholder when empty
# ==========================================================================


def test_manuscript_body_is_scene_content_only_not_summary():
    db = Database()
    pid = db.create_project("P").id
    # A scene with planning summary but EMPTY body.
    sid = db.create_scene(pid, "Opening", summary="hero wakes; ordinary world").id
    from logosforge.ui.writing_core_view import WritingCoreView
    view = WritingCoreView(db, pid)
    # Locate the editor for this scene; its body must be empty (not the summary).
    editor = None
    for sceneid, ed in getattr(view, "_editors", {}).items():
        if sceneid == sid:
            editor = ed
    # Fallback: search child _SceneEditors for one bound to sid.
    if editor is None:
        from logosforge.ui.writing_core_view import _SceneEditor
        for ed in view.findChildren(_SceneEditor):
            if getattr(ed, "_scene_id", None) == sid:
                editor = ed
                break
    assert editor is not None
    assert editor.toPlainText().strip() == ""             # not the summary
    assert "hero wakes" not in editor.toPlainText()
    assert editor.placeholderText() == "Start writing, or type '/' for commands…"


def test_manuscript_displays_real_body_text():
    db = Database()
    pid = db.create_project("P").id
    sid = db.create_scene(pid, "Opening", content="Alice opened the door.",
                          summary="planning note").id
    from logosforge.ui.writing_core_view import WritingCoreView, _SceneEditor
    view = WritingCoreView(db, pid)
    editor = next(ed for ed in view.findChildren(_SceneEditor)
                  if getattr(ed, "_scene_id", None) == sid)
    assert "Alice opened the door." in editor.toPlainText()


# ==========================================================================
# C. Conservative repair of historical contamination
# ==========================================================================


def test_repair_detects_complete_outline_preamble_in_body():
    db = Database()
    pid = db.create_project("P").id
    sid = db.create_scene(
        pid, "Ch1",
        content="A Complete Outline for Your Novel\n\n# Act 1\n- Scene: x",
    ).id
    findings = scan_manuscript_contamination(db, pid)
    assert [f.scene_id for f in findings] == [sid]
    report = repair_manuscript_contamination(db, pid, apply=True)
    assert report["cleared"] == 1
    assert (db.get_scene_by_id(sid).content or "") == ""


def test_repair_detects_body_equals_summary():
    db = Database()
    pid = db.create_project("P").id
    sid = db.create_scene(pid, "S", summary="the betrayal", content="the betrayal").id
    report = repair_manuscript_contamination(db, pid, apply=True)
    assert report["cleared"] == 1
    assert (db.get_scene_by_id(sid).content or "") == ""


def test_repair_detects_pure_outline_markup_body():
    db = Database()
    pid = db.create_project("P").id
    markup = "# Act 1\n## Chapter 1\n- Scene: a\n- Scene: b\n## Chapter 2"
    sid = db.create_scene(pid, "S", content=markup).id
    findings = scan_manuscript_contamination(db, pid)
    assert sid in [f.scene_id for f in findings]


def test_repair_keeps_real_prose():
    db = Database()
    pid = db.create_project("P").id
    prose = ("Alice walked into the dim kitchen and paused. The kettle was "
             "still warm. She wondered who had been there before her, and why "
             "they had left in such a hurry.")
    sid = db.create_scene(pid, "S", content=prose, summary="kitchen scene").id
    findings = scan_manuscript_contamination(db, pid)
    assert findings == []
    report = repair_manuscript_contamination(db, pid, apply=True)
    assert report["cleared"] == 0
    assert db.get_scene_by_id(sid).content == prose   # untouched


def test_repair_dry_run_does_not_write():
    db = Database()
    pid = db.create_project("P").id
    sid = db.create_scene(pid, "S", content="A Complete Outline for Your Novel").id
    report = repair_manuscript_contamination(db, pid)  # apply defaults to False
    assert report["cleared"] == 0
    assert len(report["findings"]) == 1
    assert db.get_scene_by_id(sid).content == "A Complete Outline for Your Novel"


def test_repair_is_project_scoped():
    db = Database()
    a = db.create_project("A").id
    b = db.create_project("B").id
    db.create_scene(a, "S", content="A Complete Outline for Your Novel")
    db.create_scene(b, "S", content="Real prose here, nothing structural at all.")
    report_b = repair_manuscript_contamination(db, b, apply=True)
    assert report_b["cleared"] == 0   # B is clean; A's contamination not touched here


# ==========================================================================
# D. Project switch keeps Manuscript / Outline isolated (regression guard)
# ==========================================================================


def test_switch_manuscript_isolated_between_projects():
    # Scene-based manuscript (screenplay) — Novel now uses the chapter view, so
    # this exercises the scene-editor isolation path explicitly.
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.writing_core_view import WritingCoreView, _SceneEditor
    db = Database()
    a = db.create_project("A", narrative_engine="screenplay",
                          default_writing_format="screenplay").id
    db.create_scene(a, "A-scene", content="ALICE PROSE ALPHA")
    b = db.create_project("B", narrative_engine="screenplay",
                          default_writing_format="screenplay").id
    win = MainWindow(db, a)
    win.sidebar_buttons["Manuscript"].click()
    bodies_a = " ".join(ed.toPlainText()
                        for ed in win.content_area.findChildren(_SceneEditor))
    assert "ALICE PROSE ALPHA" in bodies_a
    win._switch_project(b)
    assert isinstance(win.content_area, WritingCoreView)
    bodies_b = " ".join(ed.toPlainText()
                        for ed in win.content_area.findChildren(_SceneEditor))
    assert "ALICE PROSE ALPHA" not in bodies_b
