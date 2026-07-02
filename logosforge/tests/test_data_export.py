"""Tests for structured story/project data export (logosforge.data_export)."""

from __future__ import annotations

import json
import os

import pytest
from PySide6.QtWidgets import QApplication

from logosforge.db import Database
import logosforge.data_export as de
from logosforge.data_export import (
    ExportOptions,
    build_full_export,
    build_psyke_data,
    build_story_elements,
    default_filename,
    gather_export,
    sanitize_filename,
    to_csv_files,
    to_json,
    to_markdown,
    write_export,
)
from logosforge.import_data import import_json, validate_import_data
from logosforge.ui.export_data_dialog import ExportDataDialog


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_project(db: Database, title: str = "Test Saga"):
    p = db.create_project(title, narrative_engine="novel")
    pid = p.id
    alice = db.create_character(pid, "Alice")
    bob = db.create_character(pid, "Bob")
    db.create_place(pid, "Castle")
    s1 = db.create_scene(
        pid, "Opening", act="Act I", plotline="Main", summary="It begins",
        character_ids=[alice.id], content="Full opening text",
        time_of_day="DAY", location="Castle", estimated_duration_minutes=5,
    )
    db.create_scene(
        pid, "Midpoint", act="Act II", plotline="Subplot", summary="A twist",
        character_ids=[alice.id, bob.id], content="Midpoint text",
    )
    root = db.create_outline_node(pid, title="Act I", description="setup")
    db.create_outline_node(pid, title="Chapter 1", description="ch1", parent_id=root.id)
    theme = db.create_psyke_entry(
        pid, "Justice", entry_type="theme", notes="core theme",
        aliases="Fairness, Law",
    )
    hero = db.create_psyke_entry(pid, "Alice", entry_type="character", notes="the hero")
    db.add_psyke_relation(hero.id, theme.id, relation_type="thematic_echo")
    db.create_psyke_progression(hero.id, "starts naive", scene_id=s1.id)
    db.create_note(pid, "Idea", content="An idea body", tags="draft")
    return pid


# -- Filenames ---------------------------------------------------------------


def test_sanitize_filename_strips_unsafe_chars():
    assert sanitize_filename("My/Story: 2!") == "mystory_2"
    assert sanitize_filename("   ") == "project"
    assert sanitize_filename("Hello World") == "hello_world"


def test_default_filename():
    assert default_filename("My Story", "story_elements", "json") == "my_story_story_elements.json"
    assert default_filename("My Story", "psyke_data", "json") == "my_story_psyke_data.json"
    assert default_filename("My Story", "full_project", "json") == "my_story_full_export.json"


# -- Story Elements ----------------------------------------------------------


def test_export_story_elements_json_parses_and_has_sections():
    db = Database()
    pid = _make_project(db)
    data = build_story_elements(db, pid)
    text = to_json(data)
    parsed = json.loads(text)  # must parse
    assert parsed["export_type"] == "story_elements"
    assert parsed["project"]["title"] == "Test Saga"
    assert {"outline", "plot", "timeline", "psyke", "notes"} <= set(parsed)
    assert parsed["psyke"]["entries"]
    assert parsed["timeline"][0]["title"] == "Opening"
    assert [b["plotline"] for b in parsed["plot"]] == ["Main", "Subplot"]


def test_story_elements_default_excludes_scenes_content():
    db = Database()
    pid = _make_project(db)
    data = build_story_elements(db, pid)
    assert "scenes" not in data  # scenes section off by default


def test_relations_point_to_exported_entries():
    db = Database()
    pid = _make_project(db)
    data = build_story_elements(db, pid)
    names = {e["name"] for e in data["psyke"]["entries"]}
    assert data["psyke"]["relations"]
    for rel in data["psyke"]["relations"]:
        assert rel["source"] in names
        assert rel["target"] in names


# -- PSYKE Data --------------------------------------------------------------


def test_export_psyke_data_only_has_psyke():
    db = Database()
    pid = _make_project(db)
    data = build_psyke_data(db, pid)
    json.loads(to_json(data))
    assert data["export_type"] == "psyke_data"
    assert "psyke" in data
    assert "outline" not in data
    assert "plot" not in data
    assert "timeline" not in data
    assert "notes" not in data
    entry = next(e for e in data["psyke"]["entries"] if e["name"] == "Justice")
    assert entry["type"] == "theme"
    assert entry["aliases"] == ["Fairness", "Law"]


def test_psyke_progressions_link_scene_titles():
    db = Database()
    pid = _make_project(db)
    data = build_psyke_data(db, pid)
    progs = data["psyke"]["progressions"]
    assert progs
    assert progs[0]["entry"] == "Alice"
    assert progs[0]["scene_title"] == "Opening"


# -- Full project ------------------------------------------------------------


def test_export_full_project_is_import_compatible():
    db = Database()
    pid = _make_project(db)
    data = build_full_export(db, pid)
    text = to_json(data)
    validated, err = validate_import_data(text)
    assert validated is not None, err
    assert data["export_type"] == "full_project"
    # Round-trip: import into a fresh DB and check key entities survive.
    db2 = Database()
    new_pid = import_json(db2, validated)
    assert len(db2.get_all_scenes(new_pid)) == 2
    assert any(e.name == "Justice" for e in db2.get_all_psyke_entries(new_pid))


def test_full_project_includes_derived_and_settings():
    db = Database()
    pid = _make_project(db)
    data = build_full_export(db, pid)
    assert "plot" in data
    assert "timeline" in data
    assert "settings" in data


# -- Markdown ----------------------------------------------------------------


def test_export_markdown_has_readable_sections():
    db = Database()
    pid = _make_project(db)
    md = to_markdown(build_story_elements(db, pid))
    assert "# Test Saga" in md
    assert "## Outline" in md
    assert "## Plot" in md
    assert "## Timeline" in md
    assert "## Notes" in md
    # PSYKE entries grouped by kind heading.
    assert "## Themes" in md or "## Characters" in md


def test_markdown_handles_full_flat_shape():
    db = Database()
    pid = _make_project(db)
    md = to_markdown(build_full_export(db, pid))
    assert "# Test Saga" in md
    assert "## Characters" in md  # flat shape characters render


# -- CSV ---------------------------------------------------------------------


def test_export_csv_files_split_by_section():
    db = Database()
    pid = _make_project(db)
    files = to_csv_files(build_story_elements(db, pid))
    assert "timeline.csv" in files
    assert "outline.csv" in files
    assert "plot.csv" in files
    assert "psyke_relations.csv" in files
    # PSYKE entries grouped per kind.
    assert "themes.csv" in files
    # Each CSV is valid (header + at least one line).
    assert files["timeline.csv"].splitlines()[0].startswith("order_index")


def test_csv_empty_sections_raise_on_write(tmp_path):
    db = Database()
    p = db.create_project("Empty")
    opts = ExportOptions(
        include_project_metadata=False, include_outline=False,
        include_plot=False, include_timeline=False, include_scenes=False,
        include_psyke_entries=False, include_psyke_relations=False,
        include_psyke_progressions=False, include_notes=False,
    )
    data = gather_export(db, p.id, opts)
    with pytest.raises(ValueError):
        write_export(data, "csv", str(tmp_path / "out.csv"))


# -- write_export ------------------------------------------------------------


def test_write_export_json(tmp_path):
    db = Database()
    pid = _make_project(db)
    data = build_story_elements(db, pid)
    path = str(tmp_path / "story")
    written = write_export(data, "json", path)
    assert len(written) == 1
    assert written[0].endswith(".json")
    with open(written[0], encoding="utf-8") as fh:
        json.loads(fh.read())


def test_write_export_markdown(tmp_path):
    db = Database()
    pid = _make_project(db)
    written = write_export(build_story_elements(db, pid), "markdown", str(tmp_path / "story"))
    assert written[0].endswith(".md")
    assert os.path.exists(written[0])


def test_write_export_csv_creates_folder(tmp_path):
    db = Database()
    pid = _make_project(db)
    written = write_export(build_story_elements(db, pid), "csv", str(tmp_path / "story.csv"))
    assert len(written) > 1
    for path in written:
        assert path.endswith(".csv")
        assert os.path.exists(path)


# -- Data consistency / isolation -------------------------------------------


def test_export_does_not_leak_other_projects():
    db = Database()
    pid_a = _make_project(db, title="Project A")
    # A second project with uniquely-named data in the same DB.
    pid_b = db.create_project("Project B").id
    db.create_character(pid_b, "ZorgleFromB")
    db.create_scene(pid_b, "SceneOnlyInB", plotline="BPlot")
    db.create_psyke_entry(pid_b, "BThemeUnique", entry_type="theme")

    text = to_json(build_full_export(db, pid_a))
    assert "ZorgleFromB" not in text
    assert "SceneOnlyInB" not in text
    assert "BThemeUnique" not in text


def test_export_reflects_unsaved_db_changes():
    db = Database()
    pid = _make_project(db)
    scenes = db.get_all_scenes(pid)
    # Mutate live (as the UI would, before any file save).
    db.update_scene(scenes[0].id, title="Renamed Opening")
    data = build_story_elements(db, pid, ExportOptions(include_scenes=True))
    titles = [s["title"] for s in data["scenes"]]
    assert "Renamed Opening" in titles


# -- Options -----------------------------------------------------------------


def test_include_ids_adds_identifiers():
    db = Database()
    pid = _make_project(db)
    data = gather_export(
        db, pid, ExportOptions(include_ids=True, include_scenes=True),
    )
    assert "id" in data["project"]
    assert all("id" in s for s in data["scenes"])
    assert all("id" in e for e in data["psyke"]["entries"])


def test_summaries_only_omits_full_text():
    db = Database()
    pid = _make_project(db)
    data = gather_export(
        db, pid, ExportOptions(include_scenes=True, summaries_only=True),
    )
    assert all("content" not in s for s in data["scenes"])


# -- Dialog ------------------------------------------------------------------


def test_dialog_constructs_for_each_mode():
    for mode in ("story_elements", "psyke_data", "full_project"):
        dlg = ExportDataDialog(mode)
        assert dlg.windowTitle()
        opts = dlg.get_options()
        assert opts.export_type == mode


def test_dialog_full_mode_locks_sections_on():
    dlg = ExportDataDialog("full_project")
    for cb in dlg._section_checks.values():
        assert cb.isChecked()
        assert not cb.isEnabled()


def test_dialog_get_options_reflects_checkboxes():
    dlg = ExportDataDialog("story_elements")
    dlg._section_checks["include_notes"].setChecked(False)
    dlg._section_checks["include_outline"].setChecked(True)
    dlg._option_checks["include_ids"].setChecked(True)
    opts = dlg.get_options()
    assert opts.include_notes is False
    assert opts.include_outline is True
    assert opts.include_ids is True


def test_dialog_selected_format_default_json():
    dlg = ExportDataDialog("story_elements")
    assert dlg.selected_format() == "json"
