"""Post-rollback: the mode-aware primary-unit adapter is the single source of
truth for Novel = Chapter / others = Scene, and the Manuscript add label binds
to it. Manuscript itself stays the scene-based editor (rollback preserved)."""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.writing_modes import (
    current_add_button_label,
    current_primary_unit_label,
    current_primary_unit_type,
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


def _project(db, engine, fmt=""):
    return db.get_project_by_id(
        db.create_project("P", narrative_engine=engine,
                          default_writing_format=fmt or engine).id)


# ==========================================================================
# Helper trio (Phase 3 adapter)
# ==========================================================================


def test_novel_helpers():
    db = Database()
    p = _project(db, "novel")
    assert current_primary_unit_type(p) == "chapter"
    assert current_primary_unit_label(p) == "Chapter"
    assert current_add_button_label(p) == "+ Chapter"


@pytest.mark.parametrize("engine,fmt", [
    ("screenplay", "screenplay"),
    ("graphic_novel", "graphic_novel"),
    ("stage_script", "stage_script"),
    ("series", "series"),
])
def test_non_novel_helpers(engine, fmt):
    db = Database()
    p = _project(db, engine, fmt)
    assert current_primary_unit_type(p) == "scene"
    assert current_primary_unit_label(p) == "Scene"
    assert current_add_button_label(p) == "+ Scene"


def test_none_project_is_safe():
    # Defensive: a missing project never crashes and yields a valid label.
    # (The app's documented fallback mode is Novel, so this resolves to Chapter.)
    assert current_primary_unit_label(None) in ("Chapter", "Scene")
    assert current_add_button_label(None).startswith("+ ")


# ==========================================================================
# Manuscript add label binds to the adapter (still scene-based editor)
# ==========================================================================


def test_manuscript_label_binds_to_adapter():
    from logosforge.ui.writing_core_view import WritingCoreView
    db = Database()
    nov = db.create_project("N", narrative_engine="novel").id
    scr = db.create_project("S", narrative_engine="screenplay",
                            default_writing_format="screenplay").id
    assert WritingCoreView(db, nov).add_button_text() == "+ Chapter"
    assert WritingCoreView(db, scr).add_button_text() == "+ Scene"


def test_core_chapter_scene_architecture_intact():
    # The rollback kept the core: Chapter store, Scene store, outline apply paths.
    from logosforge.models import Chapter, Scene  # noqa: F401
    from logosforge.outline_actions import (  # noqa: F401
        apply_outline_as_chapters,
        apply_outline_as_scenes,
        build_mode_outline_prompt,
    )
    db = Database()
    pid = db.create_project("N", narrative_engine="novel").id
    assert db.get_chapters(pid) == []          # chapter store usable
    ch = db.create_chapter(pid, title="C1")
    assert db.get_chapters(pid)[0].id == ch.id


def test_no_chapter_manuscript_debris():
    import importlib
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("logosforge.ui.chapter_manuscript_view")
