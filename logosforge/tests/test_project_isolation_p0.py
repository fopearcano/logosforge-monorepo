"""P0 — project data isolation across New / Open / Refresh / switch.

Reproduction-style tests using unique sentinels. These fail if any project's
data leaks into another, if "Create New Project" doesn't create a clean
project, or if opening a file duplicates it.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import (
    QApplication, QLabel, QListWidget, QPlainTextEdit, QTextEdit, QTreeWidget,
)

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.export import export_json
from logosforge.ui.main_window import MainWindow

PROJECT_A_SENTINEL = "PROJECT_A_SENTINEL"
MANUSCRIPT_A_SENTINEL = "MANUSCRIPT_A_SENTINEL"
PSYKE_A_SENTINEL = "PSYKE_A_SENTINEL"
NOTE_A_SENTINEL = "NOTE_A_SENTINEL"
_A_LEAK_TOKENS = (MANUSCRIPT_A_SENTINEL, PSYKE_A_SENTINEL, NOTE_A_SENTINEL)


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


def _seed_project_a(db) -> int:
    # Screenplay (scene-based manuscript) so the manuscript sentinel — stored as
    # scene content — is visible in the Manuscript section. (Novel manuscript now
    # shows chapters; isolation is identical either way.)
    pid = db.create_project(PROJECT_A_SENTINEL, narrative_engine="screenplay",
                            default_writing_format="screenplay").id
    db.create_scene(pid, "A-scene", content=MANUSCRIPT_A_SENTINEL)
    db.create_psyke_entry(pid, PSYKE_A_SENTINEL, "character")
    db.create_note(pid, NOTE_A_SENTINEL, "body")
    return pid


def _scan_sections(win, sections) -> str:
    """Return the concatenated visible text of the given sections' widgets."""
    blobs = []
    for sec in sections:
        win.sidebar_buttons[sec].click()
        view = win.content_area
        for w in view.findChildren(QPlainTextEdit):
            blobs.append(w.toPlainText())
        for w in view.findChildren(QTextEdit):
            blobs.append(w.toPlainText())
        for lbl in view.findChildren(QLabel):
            blobs.append(lbl.text())
        for lw in view.findChildren(QListWidget):
            blobs.append(" ".join(lw.item(i).text() for i in range(lw.count())))
        for tw in view.findChildren(QTreeWidget):
            def _walk(it):
                out = []
                for i in range(it.childCount()):
                    c = it.child(i)
                    out.append(c.text(0))
                    out += _walk(c)
                return out
            blobs.append(" ".join(_walk(tw.invisibleRootItem())))
    return " ".join(blobs)


def _fake_new_dialog(monkeypatch, title):
    import logosforge.ui.new_project_dialog as npd

    class _FD:
        def __init__(self, *a, **k): ...
        def exec(self): return True
        def get_title(self): return title
        def get_engine(self): return "novel"
        def get_format(self): return "novel"

    monkeypatch.setattr(npd, "NewProjectDialog", _FD)


# ==========================================================================
# New project is clean
# ==========================================================================


def test_new_project_is_clean_workspace(monkeypatch):
    db = Database()
    a = _seed_project_a(db)
    win = MainWindow(db, a)
    _fake_new_dialog(monkeypatch, "PROJECT_C_SENTINEL")
    win._on_new_project()
    c = win._project_id
    assert c != a
    assert db.get_all_scenes(c) == []
    assert db.get_all_psyke_entries(c) == []
    assert db.get_all_notes(c) == []
    # No A sentinels anywhere in the new project's sections.
    blob = _scan_sections(win, ["Manuscript", "PSYKE", "Notes"])
    assert not any(tok in blob for tok in _A_LEAK_TOKENS)


def test_projects_view_create_new_calls_new_project_not_export():
    from logosforge.ui.projects_view import ProjectsView
    calls = {"new": 0, "save": 0}
    view = ProjectsView(
        on_open_file=lambda p: None,
        on_save_as=lambda: calls.__setitem__("save", calls["save"] + 1),
        on_new_project=lambda: calls.__setitem__("new", calls["new"] + 1),
    )
    view._create_new_project()
    assert calls == {"new": 1, "save": 0}


# ==========================================================================
# Switch isolation (section-level sentinel scan)
# ==========================================================================


def test_switch_a_to_b_to_a_no_leak():
    db = Database()
    a = _seed_project_a(db)
    b = db.create_project("PROJECT_B_SENTINEL").id
    win = MainWindow(db, a)
    on_a = _scan_sections(win, ["Manuscript", "PSYKE", "Notes"])
    assert MANUSCRIPT_A_SENTINEL in on_a and PSYKE_A_SENTINEL in on_a

    win._switch_project(b)
    on_b = _scan_sections(win, ["Manuscript", "PSYKE", "Notes"])
    assert not any(tok in on_b for tok in _A_LEAK_TOKENS)

    win._switch_project(a)
    on_a2 = _scan_sections(win, ["Manuscript", "PSYKE", "Notes"])
    assert MANUSCRIPT_A_SENTINEL in on_a2 and PSYKE_A_SENTINEL in on_a2


def test_assistant_context_has_no_other_project_terms():
    from logosforge.context_builder import gather_psyke_context
    db = Database()
    a = _seed_project_a(db)
    b = db.create_project("PROJECT_B_SENTINEL").id
    win = MainWindow(db, a)
    win._switch_project(b)
    assert win._assistant_panel._project_id == b
    ctx_b = gather_psyke_context(db, b)
    assert PSYKE_A_SENTINEL not in ctx_b


# ==========================================================================
# Open file: isolation + de-duplication
# ==========================================================================


def test_open_two_distinct_files_isolated(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    a = _seed_project_a(db)
    b = db.create_project("PROJECT_B_SENTINEL").id  # genuinely empty
    afile = tmp_path / "A.json"; afile.write_text(export_json(db, a), encoding="utf-8")
    bfile = tmp_path / "B.json"; bfile.write_text(export_json(db, b), encoding="utf-8")

    win = MainWindow(db, a)
    win._open_file(str(bfile))
    blob_b = _scan_sections(win, ["Manuscript", "PSYKE", "Notes"])
    assert not any(tok in blob_b for tok in _A_LEAK_TOKENS)

    win._open_file(str(afile))
    blob_a = _scan_sections(win, ["Manuscript", "PSYKE"])
    assert MANUSCRIPT_A_SENTINEL in blob_a or PSYKE_A_SENTINEL in blob_a


def test_opening_same_file_does_not_duplicate(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    a = _seed_project_a(db)
    afile = tmp_path / "A.json"; afile.write_text(export_json(db, a), encoding="utf-8")
    win = MainWindow(db, a)
    before = len(db.get_all_projects())
    win._open_file(str(afile))            # first open imports once
    after_first = len(db.get_all_projects())
    win._open_file(str(afile))            # second open must de-dup
    after_second = len(db.get_all_projects())
    assert after_first == before + 1
    assert after_second == after_first    # no duplicate


def test_startup_reimport_does_not_duplicate(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    a = _seed_project_a(db)
    afile = tmp_path / "A.json"; afile.write_text(export_json(db, a), encoding="utf-8")
    win = MainWindow(db, a)
    win._open_file(str(afile))
    n = len(db.get_all_projects())
    # Simulate a subsequent launch loading the same last project file.
    win.load_file_quiet(str(afile))
    assert len(db.get_all_projects()) == n      # activated, not re-imported


def test_source_path_tagging(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    a = _seed_project_a(db)
    afile = tmp_path / "A.json"; afile.write_text(export_json(db, a), encoding="utf-8")
    win = MainWindow(db, a)
    win._open_file(str(afile))
    resolved = str(afile.resolve())
    assert db.get_project_by_source_path(resolved) == win._project_id


# ==========================================================================
# Refresh / missing active project safety
# ==========================================================================


def test_refresh_projects_drops_deleted_file(tmp_path, monkeypatch):
    from logosforge.ui.projects_view import ProjectsView
    from logosforge import recent_projects
    p1 = tmp_path / "gone.json"; p1.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(recent_projects, "clean",
                        lambda: [str(p1)] if p1.exists() else [])
    view = ProjectsView(on_open_file=lambda p: None, on_save_as=lambda: None,
                        on_new_project=lambda: None)
    p1.unlink()
    view.refresh()
    from PySide6.QtCore import QEvent
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.instance().processEvents()
    names = {lbl.text() for lbl in view.findChildren(QLabel)}
    assert "gone.json" not in names
