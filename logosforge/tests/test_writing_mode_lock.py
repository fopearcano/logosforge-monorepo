"""Writing-mode lock — Alpha blocker fix.

Writing mode is chosen at project creation and LOCKED once the project has
meaningful content, so the Manuscript can never read one mode's body as another's
(e.g. prose parsed as screenplay blocks). Empty/new projects may still change
mode; blocked changes never mutate any data. No automatic conversion.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import writing_modes as wm


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


def _project(db, engine="novel"):
    return db.create_project(engine, narrative_engine=engine,
                             default_writing_format=engine).id


def _empty_default_scene(db, pid):
    # A pure starter scaffold: default title/structure, no body — NOT meaningful.
    return ss.create_scene(db, pid, act=ss.DEFAULT_ACT, chapter=ss.DEFAULT_CHAPTER,
                           title="Untitled", content="", summary="").id


def _body_scene(db, pid, content="INT. X - DAY\n\nMaria runs."):
    return ss.create_scene(db, pid, act=ss.DEFAULT_ACT, chapter=ss.DEFAULT_CHAPTER,
                           title="Untitled", content=content, summary="").id


# ==========================================================================
# 1-3  Mode change allowed on an empty project
# ==========================================================================


def test_empty_project_can_change_mode():
    db = Database()
    pid = _project(db, "novel")
    assert wm.can_change_writing_mode(db, pid) is True


def test_empty_default_scene_still_allows_change():
    db = Database()
    pid = _project(db, "novel")
    _empty_default_scene(db, pid)        # starter scaffold only
    assert wm.can_change_writing_mode(db, pid) is True


def test_empty_project_change_persists():
    db = Database()
    pid = _project(db, "novel")
    changed, mode = wm.change_writing_mode(db, pid, "screenplay")
    assert changed is True and mode == "screenplay"
    assert wm.get_project_writing_mode_by_id(db, pid) == "screenplay"


# ==========================================================================
# 4-13  Mode locks once meaningful content exists
# ==========================================================================


def test_novel_body_locks_mode():
    db = Database()
    pid = _project(db, "novel")
    _body_scene(db, pid, "Once upon a time, prose was written here.")
    assert wm.can_change_writing_mode(db, pid) is False
    changed, mode = wm.change_writing_mode(db, pid, "screenplay")
    assert changed is False and mode == "novel"
    assert wm.get_project_writing_mode_by_id(db, pid) == "novel"


def test_screenplay_blocks_lock_mode():
    db = Database()
    pid = _project(db, "screenplay")
    _body_scene(db, pid, "INT. ROOM - DAY\n\nAction.\n\nMARIA\nHi.")
    assert wm.change_writing_mode(db, pid, "novel") == (False, "screenplay")


def test_graphic_novel_body_locks_mode():
    db = Database()
    pid = _project(db, "graphic_novel")
    _body_scene(db, pid, "PAGE 1\n\nPANEL 1\nMaria at the window.")
    assert wm.change_writing_mode(db, pid, "screenplay") == (False, "graphic_novel")


def test_stage_script_blocks_lock_mode():
    db = Database()
    pid = _project(db, "stage_script")
    _body_scene(db, pid, "STAGE: A bare room.\n\nCHARACTER: MARIA\nHi.")
    assert wm.change_writing_mode(db, pid, "series") == (False, "stage_script")


def test_series_blocks_lock_mode():
    db = Database()
    pid = _project(db, "series")
    _body_scene(db, pid, "INT. X - DAY\n\nMaria escapes.\n\nMARIA\nGo.")
    assert wm.change_writing_mode(db, pid, "stage_script") == (False, "series")


def test_notes_lock_mode():
    db = Database()
    pid = _project(db, "novel")
    db.create_note(pid, "note", "body")
    assert wm.can_change_writing_mode(db, pid) is False


def test_psyke_entries_lock_mode():
    db = Database()
    pid = _project(db, "novel")
    db.create_psyke_entry(pid, "Maria", "character")
    assert wm.can_change_writing_mode(db, pid) is False


def test_timeline_events_lock_mode():
    db = Database()
    pid = _project(db, "novel")
    sid = _empty_default_scene(db, pid)
    assert wm.can_change_writing_mode(db, pid) is True       # scaffold only
    db.add_timeline_event(pid, sid)
    assert wm.can_change_writing_mode(db, pid) is False      # now meaningful


def test_generated_plans_lock_mode():
    db = Database()
    pid = _project(db, "screenplay")
    settings = db.get_project_settings(pid)
    settings["screenplay_beat_plans"] = {"1": {"objective": "win the duel"}}
    db.save_project_settings(pid, settings)
    assert wm.can_change_writing_mode(db, pid) is False


def test_user_created_structure_locks_mode():
    db = Database()
    pid = _project(db, "novel")
    # A non-default Act label = user-created structure, even without body.
    ss.create_scene(db, pid, act="Prologue", chapter="Chapter 1", title="Untitled",
                    content="", summary="")
    assert wm.can_change_writing_mode(db, pid) is False


# ==========================================================================
# 14-20  Blocked change does not mutate anything
# ==========================================================================


def test_blocked_change_mutates_nothing():
    db = Database()
    pid = _project(db, "screenplay")
    sid = ss.create_scene(db, pid, act=ss.DEFAULT_ACT, chapter=ss.DEFAULT_CHAPTER,
                          title="Untitled", content="INT. X - DAY\n\nKeep me.",
                          summary="KEEP_SUMMARY").id
    db.create_note(pid, "n", "note body")
    db.create_psyke_entry(pid, "Maria", "character")
    db.add_timeline_event(pid, sid)

    before = {
        "mode": wm.get_project_writing_mode_by_id(db, pid),
        "body": db.get_scene_by_id(sid).content,
        "summary": db.get_scene_by_id(sid).summary,
        "notes": len(db.get_all_notes(pid)),
        "psyke": len(db.get_all_psyke_entries(pid)),
        "timeline": set(db.get_timeline_event_ids(pid) or set()),
    }
    changed, mode = wm.change_writing_mode(db, pid, "novel")    # locked → refused
    assert changed is False and mode == "screenplay"
    assert wm.get_project_writing_mode_by_id(db, pid) == before["mode"]
    assert db.get_scene_by_id(sid).content == before["body"]
    assert db.get_scene_by_id(sid).summary == before["summary"]
    assert len(db.get_all_notes(pid)) == before["notes"]
    assert len(db.get_all_psyke_entries(pid)) == before["psyke"]
    assert set(db.get_timeline_event_ids(pid) or set()) == before["timeline"]


def test_same_mode_is_noop_not_a_change():
    db = Database()
    pid = _project(db, "series")
    _body_scene(db, pid)
    assert wm.change_writing_mode(db, pid, "series") == (False, "series")


# ==========================================================================
# 21-25  UI: Project Settings dialog enforces the lock
# ==========================================================================


def _dialog(db, pid):
    from logosforge.ui.project_settings_dialog import ProjectSettingsDialog
    return ProjectSettingsDialog(db, pid)


def test_dialog_disables_engine_for_in_progress_project():
    db = Database()
    pid = _project(db, "screenplay")
    _body_scene(db, pid, "INT. X - DAY\n\nAction.")
    dlg = _dialog(db, pid)
    assert dlg._mode_locked is True
    assert dlg._engine_combo.isEnabled() is False


def test_dialog_shows_lock_message():
    db = Database()
    pid = _project(db, "novel")
    _body_scene(db, pid, "Prose body.")
    dlg = _dialog(db, pid)
    assert dlg._lock_label is not None
    assert dlg._lock_label.text() == wm.MODE_LOCK_MESSAGE


def test_dialog_allows_change_on_empty_project():
    db = Database()
    pid = _project(db, "novel")
    dlg = _dialog(db, pid)
    assert dlg._mode_locked is False
    assert dlg._engine_combo.isEnabled() is True


def test_dialog_cannot_bypass_lock_on_save(monkeypatch):
    db = Database()
    pid = _project(db, "screenplay")
    _body_scene(db, pid, "INT. X - DAY\n\nAction.")
    dlg = _dialog(db, pid)
    # Don't pop modal dialogs in the headless test.
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    # Force a bypass attempt: re-enable + select a different engine, then save.
    dlg._engine_combo.setEnabled(True)
    idx = dlg._engine_combo.findData("novel")
    dlg._engine_combo.setCurrentIndex(idx)
    dlg._on_accept()
    assert db.get_project_by_id(pid).narrative_engine == "screenplay"   # unchanged


def test_new_project_dialog_mode_selector_works():
    from logosforge.ui.new_project_dialog import NewProjectDialog
    dlg = NewProjectDialog()
    assert dlg._engine_combo.isEnabled() is True
    idx = dlg._engine_combo.findData("screenplay")
    dlg._engine_combo.setCurrentIndex(idx)
    assert dlg.get_engine() == "screenplay"


# ==========================================================================
# Regression sanity
# ==========================================================================


def test_universal_manuscript_routes_locked_project_by_stored_mode():
    from logosforge.ui.writing_core_view import WritingCoreView
    db = Database()
    pid = _project(db, "series")
    _body_scene(db, pid, "INT. X - DAY\n\nA beat.")
    # Locked; Manuscript opens using the STORED mode (series), not a switched one.
    view = WritingCoreView(db, pid, structured_list=True)
    ed = next(iter(view._editors.values()))
    assert ed._screenplay_mode is False and ed._graphic_novel_mode is False
    assert wm.get_project_writing_mode_by_id(db, pid) == "series"


def test_low_level_setter_remains_permissive():
    # The persistence primitive is unguarded (used at creation / by internals);
    # the guard lives in change_writing_mode + the UI. This must not regress.
    db = Database()
    pid = _project(db, "novel")
    _body_scene(db, pid, "Prose.")
    assert wm.set_project_writing_mode(db, pid, "series") == "series"
