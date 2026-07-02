"""Step 18 — export / Fountain / story-elements stabilization."""

import json

import pytest

from logosforge.db import Database
from logosforge.export import (
    export_csv_scenes,
    export_fdx,
    export_formatted_text,
    export_fountain,
    export_html,
    export_json,
    export_markdown,
    export_outline_markdown,
)
from logosforge.data_export import (
    build_full_export,
    build_psyke_data,
    build_story_elements,
    to_json,
)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path, raising=False)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json",
                        raising=False)
    yield
    settings._instance = None


def _novel():
    db = Database()
    pid = db.create_project("My Novel", narrative_engine="novel").id
    db.create_psyke_entry(pid, "Alice", "character", notes="lead")
    db.create_psyke_entry(pid, "The Harbor", "place")
    db.create_note(pid, "Idea", "A note about Alice.")
    db.create_scene(pid, "Opening", content="Alice arrived at the Harbor.",
                    summary="intro", act="Act I", chapter="Ch1")
    return db, pid


def _screenplay():
    db = Database()
    pid = db.create_project("My Script", narrative_engine="screenplay").id
    # Screenplay scenes carry the heading in the content (as the editor writes
    # it); slugline is separate metadata.
    db.create_scene(pid, "Open",
                    content="INT. HOUSE - DAY\n\nALICE\nHello there.\n",
                    slugline="INT. HOUSE - DAY", act="Act I")
    return db, pid


# ==========================================================================
# Manuscript formats export without error
# ==========================================================================


@pytest.mark.parametrize("fn", [
    export_markdown, export_formatted_text, export_json, export_csv_scenes,
    export_html, export_fdx, export_outline_markdown,
])
def test_text_exports_produce_content(fn):
    db, pid = _novel()
    out = fn(db, pid)
    assert isinstance(out, str) and out.strip()


def test_markdown_includes_writing_mode():
    db, pid = _novel()
    md = export_markdown(db, pid)
    assert "Writing Mode" in md


def test_json_export_includes_mode_metadata():
    db, pid = _novel()
    data = json.loads(export_json(db, pid))
    assert data["project"]["writing_mode"] == "novel"
    assert data["project"]["narrative_engine"] == "novel"


# ==========================================================================
# Fountain (screenplay)
# ==========================================================================


def test_fountain_export_screenplay():
    db, pid = _screenplay()
    fountain = export_fountain(db, pid)
    assert fountain.strip()
    # Scene heading preserved (uppercased slugline).
    assert "INT. HOUSE - DAY" in fountain.upper()
    # Character cue present (uppercased) and dialogue retained.
    assert "ALICE" in fountain.upper()
    assert "Hello there" in fountain


def test_fountain_no_text_loss_for_unknown_lines():
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    db.create_scene(pid, "S", content="Some ambiguous prose line.",
                    slugline="EXT. PARK - NIGHT")
    fountain = export_fountain(db, pid)
    assert "ambiguous prose line" in fountain  # degraded to action, not dropped


# ==========================================================================
# Story elements
# ==========================================================================


def test_story_elements_contains_all_sections():
    db, pid = _novel()
    data = build_story_elements(db, pid)
    for key in ("project", "outline", "plot", "timeline", "psyke", "notes"):
        assert key in data, f"missing {key}"


def test_full_export_is_import_compatible_and_complete():
    db, pid = _novel()
    data = build_full_export(db, pid)
    assert data.get("scenes") and data.get("psyke_entries") and data.get("notes")
    assert "outline" in data and "plot" in data and "timeline" in data
    assert data["project"].get("writing_mode") == "novel"


def test_psyke_export_has_entries():
    db, pid = _novel()
    data = build_psyke_data(db, pid)
    blob = to_json(data)
    assert "Alice" in blob


# ==========================================================================
# Safety: no API keys / abs paths; missing systems handled
# ==========================================================================


def test_no_api_key_in_any_export():
    from logosforge.settings import get_manager
    get_manager().set("ai_api_key", "sk-secret-xyz")
    db, pid = _novel()
    for blob in (export_json(db, pid), to_json(build_full_export(db, pid)),
                 to_json(build_story_elements(db, pid))):
        assert "sk-secret-xyz" not in blob
        assert "api_key" not in blob.lower()


def test_empty_project_exports_cleanly():
    db = Database()
    pid = db.create_project("Empty", narrative_engine="novel").id
    # No scenes / PSYKE / notes — exports must not raise.
    assert isinstance(export_markdown(db, pid), str)
    assert isinstance(export_json(db, pid), str)
    assert build_full_export(db, pid).get("project")


# ==========================================================================
# Import / export roundtrip
# ==========================================================================


def test_full_export_import_roundtrip():
    from logosforge.import_data import import_json, validate_import_data
    db, pid = _novel()
    raw = to_json(build_full_export(db, pid))
    data, err = validate_import_data(raw)
    assert data is not None and err == ""
    new_id = import_json(db, data)
    assert new_id != pid
    assert any("Alice arrived" in (s.content or "")
               for s in db.get_all_scenes(new_id))
    assert any(e.name == "Alice" for e in db.get_all_psyke_entries(new_id))


# ==========================================================================
# UI export error handling (readable, not a traceback)
# ==========================================================================


def test_on_export_reports_readable_error(monkeypatch):
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    QApplication.instance() or QApplication([])
    from logosforge.ui.main_window import MainWindow
    import logosforge.ui.main_window as mw
    db, pid = _novel()
    win = MainWindow(db, pid)

    # Simulate the user choosing a PDF path, and a missing-library failure.
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: ("/tmp/x.pdf", "PDF Manuscript (*.pdf)")))

    def _boom(*a, **k):
        raise ImportError("No module named 'reportlab'")

    monkeypatch.setattr(mw, "export_pdf", _boom, raising=False)
    captured = {}
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda parent, title, text, *a, **k:
                                     captured.update(title=title, text=text)))
    win._on_export()  # must NOT raise
    assert captured.get("title") == "Export failed"
    assert "reportlab" in captured.get("text", "")
