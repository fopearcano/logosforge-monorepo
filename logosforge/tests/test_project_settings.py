"""Tests for project-level narrative engine and writing format."""

from __future__ import annotations

from logosforge.db import Database
from logosforge.narrative_engines import engine_for_project
from logosforge.project_compat import (
    ENGINE_GRAPHIC_NOVEL,
    ENGINE_NOVEL,
    ENGINE_SCREENPLAY,
    ENGINE_SERIES,
    ENGINE_STAGE_SCRIPT,
    FORMAT_GRAPHIC_NOVEL,
    FORMAT_PROSE,
    FORMAT_SCREENPLAY,
    FORMAT_STAGE_SCRIPT,
    default_format_for_engine,
    get_project_narrative_engine,
    get_project_writing_format,
    is_screenplay_project,
    resolve_legacy_format,
)


# =========================================================================
# 1. PROJECT CREATION DEFAULTS
# =========================================================================

def test_create_novel_project_defaults():
    db = Database()
    p = db.create_project(
        "My Novel",
        narrative_engine=ENGINE_NOVEL,
        default_writing_format=FORMAT_PROSE,
    )
    assert p.narrative_engine == ENGINE_NOVEL
    assert p.default_writing_format == FORMAT_PROSE


def test_create_screenplay_project():
    db = Database()
    p = db.create_project(
        "Film Noir",
        narrative_engine=ENGINE_SCREENPLAY,
        default_writing_format=FORMAT_SCREENPLAY,
    )
    assert p.narrative_engine == ENGINE_SCREENPLAY
    assert p.default_writing_format == FORMAT_SCREENPLAY


def test_create_graphic_novel_project():
    db = Database()
    p = db.create_project(
        "GN",
        narrative_engine=ENGINE_GRAPHIC_NOVEL,
        default_writing_format=FORMAT_GRAPHIC_NOVEL,
    )
    assert p.narrative_engine == ENGINE_GRAPHIC_NOVEL
    assert p.default_writing_format == FORMAT_GRAPHIC_NOVEL


def test_create_stage_script_project():
    db = Database()
    p = db.create_project(
        "Stage",
        narrative_engine=ENGINE_STAGE_SCRIPT,
        default_writing_format=FORMAT_STAGE_SCRIPT,
    )
    assert p.narrative_engine == ENGINE_STAGE_SCRIPT
    assert p.default_writing_format == FORMAT_STAGE_SCRIPT


def test_create_series_project_defaults_safely():
    db = Database()
    p = db.create_project(
        "Series",
        narrative_engine=ENGINE_SERIES,
    )
    assert p.narrative_engine == ENGINE_SERIES
    # Series default format suggested by the engine.
    assert p.default_writing_format == default_format_for_engine(ENGINE_SERIES)


def test_create_with_legacy_format_mode():
    db = Database()
    p = db.create_project("Old style", format_mode="screenplay")
    assert p.narrative_engine == ENGINE_SCREENPLAY
    assert p.default_writing_format == FORMAT_SCREENPLAY


# =========================================================================
# 2. PROJECT UPDATES
# =========================================================================

def test_update_engine_persists():
    db = Database()
    p = db.create_project("X", narrative_engine=ENGINE_NOVEL)
    db.update_project_narrative_engine(p.id, ENGINE_SCREENPLAY)
    reloaded = db.get_project_by_id(p.id)
    assert reloaded.narrative_engine == ENGINE_SCREENPLAY


def test_update_format_persists():
    db = Database()
    p = db.create_project("X", narrative_engine=ENGINE_NOVEL)
    db.update_project_writing_format(p.id, FORMAT_SCREENPLAY)
    reloaded = db.get_project_by_id(p.id)
    assert reloaded.default_writing_format == FORMAT_SCREENPLAY


def test_update_format_syncs_legacy_field():
    db = Database()
    p = db.create_project("X", narrative_engine=ENGINE_NOVEL)
    db.update_project_writing_format(p.id, FORMAT_SCREENPLAY)
    reloaded = db.get_project_by_id(p.id)
    # Legacy format_mode kept in sync so old readers still see the change.
    assert reloaded.format_mode == FORMAT_SCREENPLAY


# =========================================================================
# 3. CENTRAL ACCESSORS
# =========================================================================

def test_get_engine_uses_new_field():
    db = Database()
    p = db.create_project("X", narrative_engine=ENGINE_SCREENPLAY)
    assert get_project_narrative_engine(p) == ENGINE_SCREENPLAY


def test_get_format_uses_new_field():
    db = Database()
    p = db.create_project(
        "X",
        narrative_engine=ENGINE_NOVEL,
        default_writing_format=FORMAT_PROSE,
    )
    assert get_project_writing_format(p) == FORMAT_PROSE


def test_get_engine_returns_novel_for_none():
    assert get_project_narrative_engine(None) == ENGINE_NOVEL


def test_get_format_returns_prose_for_none():
    assert get_project_writing_format(None) == FORMAT_PROSE


def test_is_screenplay_project_true():
    db = Database()
    p = db.create_project("X", narrative_engine=ENGINE_SCREENPLAY)
    assert is_screenplay_project(p) is True


def test_is_screenplay_project_false_for_novel():
    db = Database()
    p = db.create_project("X", narrative_engine=ENGINE_NOVEL)
    assert is_screenplay_project(p) is False


# =========================================================================
# 4. LEGACY MIGRATION
# =========================================================================

def test_legacy_novel_maps_to_engine_and_format():
    assert resolve_legacy_format("novel") == (ENGINE_NOVEL, FORMAT_PROSE)


def test_legacy_book_maps_to_novel():
    assert resolve_legacy_format("book") == (ENGINE_NOVEL, FORMAT_PROSE)


def test_legacy_screenplay_maps_correctly():
    assert resolve_legacy_format("screenplay") == (
        ENGINE_SCREENPLAY, FORMAT_SCREENPLAY,
    )


def test_legacy_stage_script_maps_correctly():
    assert resolve_legacy_format("stage_script") == (
        ENGINE_STAGE_SCRIPT, FORMAT_STAGE_SCRIPT,
    )


def test_legacy_graphic_novel_maps_correctly():
    assert resolve_legacy_format("graphic_novel") == (
        ENGINE_GRAPHIC_NOVEL, FORMAT_GRAPHIC_NOVEL,
    )


def test_legacy_unknown_falls_back_to_novel():
    assert resolve_legacy_format("unknown_format") == (
        ENGINE_NOVEL, FORMAT_PROSE,
    )


def test_legacy_empty_falls_back_to_novel():
    assert resolve_legacy_format("") == (ENGINE_NOVEL, FORMAT_PROSE)


# =========================================================================
# 5. ENGINE-FOR-PROJECT WIRING
# =========================================================================

def test_engine_for_project_uses_new_field():
    db = Database()
    p = db.create_project("X", narrative_engine=ENGINE_SCREENPLAY)
    engine = engine_for_project(p)
    assert engine.name == ENGINE_SCREENPLAY


def test_engine_for_project_falls_back_to_legacy_format():
    """If a project somehow only has format_mode (e.g. raw load), the
    accessor still resolves the correct engine."""
    from logosforge.models.models import Project
    p = Project(
        title="Legacy",
        format_mode="screenplay",
        narrative_engine="",
        default_writing_format="",
    )
    assert get_project_narrative_engine(p) == ENGINE_SCREENPLAY


def test_engine_for_project_unknown_engine_falls_back():
    from logosforge.models.models import Project
    p = Project(
        title="X",
        format_mode="",
        narrative_engine="brand_new_engine_not_registered",
        default_writing_format="",
    )
    # Unknown engine name not in ALL_ENGINES → fallback via legacy path.
    assert get_project_narrative_engine(p) == ENGINE_NOVEL


# =========================================================================
# 6. DEFAULT FORMAT FOR ENGINE
# =========================================================================

def test_default_format_for_novel_is_prose():
    assert default_format_for_engine(ENGINE_NOVEL) == FORMAT_PROSE


def test_default_format_for_screenplay_is_screenplay():
    assert default_format_for_engine(ENGINE_SCREENPLAY) == FORMAT_SCREENPLAY


def test_default_format_for_stage_script_is_stage_script():
    assert default_format_for_engine(ENGINE_STAGE_SCRIPT) == FORMAT_STAGE_SCRIPT


def test_default_format_for_graphic_novel_is_graphic_novel():
    assert default_format_for_engine(ENGINE_GRAPHIC_NOVEL) == FORMAT_GRAPHIC_NOVEL


# =========================================================================
# 7. SECTION ADAPTATION
# =========================================================================

def test_story_grid_screenplay_mode_from_engine():
    """Plot grid keys its screenplay affordances off the project engine."""
    from logosforge.ui.story_grid_view import StoryGridView
    db = Database()
    p = db.create_project(
        "X",
        narrative_engine=ENGINE_SCREENPLAY,
        default_writing_format=FORMAT_SCREENPLAY,
    )
    view = StoryGridView(db, p.id)
    assert view.get_format_mode() == "screenplay"


def test_story_grid_novel_mode_from_engine():
    from logosforge.ui.story_grid_view import StoryGridView
    db = Database()
    p = db.create_project("X", narrative_engine=ENGINE_NOVEL)
    view = StoryGridView(db, p.id)
    assert view.get_format_mode() != "screenplay"


def test_focus_graph_screenplay_mode_from_engine():
    from logosforge.ui.focus_graph_view import FocusGraphView
    db = Database()
    p = db.create_project("X", narrative_engine=ENGINE_SCREENPLAY)
    view = FocusGraphView(db, p.id)
    assert view._screenplay_mode is True


def test_focus_graph_novel_no_screenplay_buttons():
    from logosforge.ui.focus_graph_view import (
        FocusGraphView,
        SCREENPLAY_MODE_ORDER,
    )
    db = Database()
    p = db.create_project("X", narrative_engine=ENGINE_NOVEL)
    view = FocusGraphView(db, p.id)
    for m in SCREENPLAY_MODE_ORDER:
        assert m not in view._mode_buttons


# =========================================================================
# 8. UI DIALOGS
# =========================================================================

def test_new_project_dialog_defaults_to_novel():
    from logosforge.ui.new_project_dialog import NewProjectDialog
    dlg = NewProjectDialog()
    assert dlg.get_engine() == ENGINE_NOVEL
    assert dlg.get_format() == FORMAT_PROSE


def test_new_project_dialog_auto_updates_format_when_engine_changes():
    from logosforge.ui.new_project_dialog import NewProjectDialog
    dlg = NewProjectDialog()
    # Programmatically change to screenplay engine.
    idx = dlg._engine_combo.findData(ENGINE_SCREENPLAY)
    dlg._engine_combo.setCurrentIndex(idx)
    assert dlg.get_format() == FORMAT_SCREENPLAY


def test_new_project_dialog_keeps_format_when_user_overrode_it():
    from logosforge.ui.new_project_dialog import NewProjectDialog
    dlg = NewProjectDialog()
    # User manually picks treatment.
    from logosforge.project_compat import FORMAT_TREATMENT
    fidx = dlg._format_combo.findData(FORMAT_TREATMENT)
    dlg._format_combo.setCurrentIndex(fidx)
    assert dlg.get_format() == FORMAT_TREATMENT
    # Now changing the engine should NOT clobber the user pick.
    eidx = dlg._engine_combo.findData(ENGINE_SCREENPLAY)
    dlg._engine_combo.setCurrentIndex(eidx)
    assert dlg.get_format() == FORMAT_TREATMENT


def test_project_settings_dialog_shows_current_values():
    from logosforge.ui.project_settings_dialog import ProjectSettingsDialog
    db = Database()
    p = db.create_project(
        "X",
        narrative_engine=ENGINE_SCREENPLAY,
        default_writing_format=FORMAT_SCREENPLAY,
    )
    dlg = ProjectSettingsDialog(db, p.id)
    assert dlg.get_selected_engine() == ENGINE_SCREENPLAY
    assert dlg.get_selected_format() == FORMAT_SCREENPLAY


def test_project_settings_dialog_engine_change_updates_format():
    from logosforge.ui.project_settings_dialog import ProjectSettingsDialog
    db = Database()
    p = db.create_project("X", narrative_engine=ENGINE_NOVEL)
    dlg = ProjectSettingsDialog(db, p.id)
    idx = dlg._engine_combo.findData(ENGINE_GRAPHIC_NOVEL)
    dlg._engine_combo.setCurrentIndex(idx)
    assert dlg.get_selected_format() == FORMAT_GRAPHIC_NOVEL


# =========================================================================
# 9. MANUSCRIPT TOP BAR
# =========================================================================

def test_manuscript_top_bar_has_no_format_combo():
    """The Manuscript top bar must NOT carry a project-format selector."""
    from logosforge.ui.writing_core_view import WritingCoreView
    db = Database()
    p = db.create_project("X", narrative_engine=ENGINE_NOVEL)
    view = WritingCoreView(db, p.id)
    assert not hasattr(view, "_format_combo")


def test_manuscript_top_bar_shows_format_badge():
    from logosforge.ui.writing_core_view import WritingCoreView
    db = Database()
    p = db.create_project(
        "X",
        narrative_engine=ENGINE_SCREENPLAY,
        default_writing_format=FORMAT_SCREENPLAY,
    )
    view = WritingCoreView(db, p.id)
    assert hasattr(view, "_format_badge")
    text = view._format_badge.text()
    assert "Screenplay" in text


def test_manuscript_reload_project_format():
    from logosforge.ui.writing_core_view import WritingCoreView
    db = Database()
    p = db.create_project("X", narrative_engine=ENGINE_NOVEL)
    view = WritingCoreView(db, p.id)
    # Simulate Project Settings flipping the engine + format.
    db.update_project_narrative_engine(p.id, ENGINE_SCREENPLAY)
    db.update_project_writing_format(p.id, FORMAT_SCREENPLAY)
    view.reload_project_format()
    assert "Screenplay" in view._format_badge.text()
    assert view._format.name == "screenplay"
