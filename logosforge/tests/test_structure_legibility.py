"""Regression tests for the Structure-group legibility/actionability pass.

Acts gets a Range explanation; Beats gets a Save-the-Cat legend, phase coverage,
word counts, click-to-scene, and onboarding; Arcs explains "state" and tailors
its empty guidance. Also pins the `{theme.BORDER}` f-string bug fix.
"""

from __future__ import annotations

import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge.db import Database


@pytest.fixture(scope="module")
def _qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def _label_texts(view):
    from PySide6.QtWidgets import QLabel
    return [lbl.text() for lbl in view.findChildren(QLabel)]


# ---------------------------------------------------------------------------
# Acts
# ---------------------------------------------------------------------------

def test_acts_range_explained_and_no_literal_template(_qapp):
    from logosforge.ui.act_analysis_view import ActAnalysisView
    db = Database()
    proj = db.create_project("A")
    db.create_scene(proj.id, "S1", act="Act I")
    db.create_scene(proj.id, "S2", act="Act I")
    view = ActAnalysisView(db, proj.id)
    assert any("scene-position range" in t for t in _label_texts(view))
    assert "{theme.BORDER}" not in view._browser.toHtml()   # f-string bug fixed


# ---------------------------------------------------------------------------
# Beats
# ---------------------------------------------------------------------------

def test_beats_legend_phase_coverage_words(_qapp):
    from logosforge.ui.beat_analysis_view import BeatAnalysisView
    db = Database()
    proj = db.create_project("B")
    db.create_scene(proj.id, "S1", beat="Catalyst", content="one two three")
    view = BeatAnalysisView(db, proj.id)
    assert any("Save the Cat" in t for t in _label_texts(view))   # legend
    html = view._browser.toHtml()
    assert "Phase coverage" in html
    assert "Words" in html
    assert "{theme.BORDER}" not in html                           # bug fixed


def test_beats_empty_onboarding(_qapp):
    from logosforge.ui.beat_analysis_view import BeatAnalysisView
    db = Database()
    proj = db.create_project("B")
    view = BeatAnalysisView(db, proj.id)        # no scenes
    html = view._browser.toHtml()
    assert "Scenes" in html and "beat dropdown" in html


def test_beats_click_to_scene_navigation(_qapp):
    from PySide6.QtCore import QUrl
    from logosforge.ui.beat_analysis_view import BeatAnalysisView
    db = Database()
    proj = db.create_project("B")
    scene = db.create_scene(proj.id, "S1", beat="Midpoint")

    # No callback -> no scene links rendered.
    plain = BeatAnalysisView(db, proj.id)
    assert "scene:" not in plain._browser.toHtml()

    # With callback -> links rendered + the handler opens the scene.
    opened: list[int] = []
    nav = BeatAnalysisView(db, proj.id, on_open_scene=opened.append)
    assert "scene:" in nav._browser.toHtml()
    nav._on_anchor(QUrl(f"scene:{scene.id}"))
    assert opened == [scene.id]


# ---------------------------------------------------------------------------
# Arcs
# ---------------------------------------------------------------------------

def test_arcs_state_is_explained(_qapp):
    from logosforge.ui.character_arc_view import CharacterArcView
    db = Database()
    proj = db.create_project("C")
    view = CharacterArcView(db, proj.id)
    assert any("emotional/mental condition" in t for t in _label_texts(view))


def test_arcs_empty_guidance_tailored_to_no_scenes(_qapp):
    from logosforge.ui.character_arc_view import CharacterArcView
    db = Database()
    proj = db.create_project("C")
    db.create_psyke_entry(proj.id, "Loner", entry_type="character")
    view = CharacterArcView(db, proj.id)
    idx = view._char_combo.findData("Loner")
    view._char_combo.setCurrentIndex(idx)
    text = view._empty_label.text()
    assert "No scene states" in text          # existing contract preserved
    assert "Create scenes" in text            # tailored: project has no scenes


# ---------------------------------------------------------------------------
# Structure (b): now the Act -> Chapter -> Scene hierarchy, not beat-grouping
# ---------------------------------------------------------------------------

def test_structure_shows_act_chapter_scene_hierarchy(_qapp):
    from logosforge.ui.structure_view import StructureView
    db = Database()
    proj = db.create_project("S", narrative_engine="novel")
    db.create_scene(proj.id, "Opening", act="Act I", chapter="Chapter One",
                    beat="Catalyst")
    db.create_scene(proj.id, "Next", act="Act I", chapter="Chapter One")
    view = StructureView(db, proj.id)
    html = view._browser.toHtml()
    assert "Act 1" in html and "Chapter 1.1" in html
    assert "1.1.1" in html                       # canonical scene number
    assert "Catalyst" in html                    # beat annotation retained
    assert "No beats assigned" not in html       # no longer beat-grouped


def test_structure_empty_onboarding(_qapp):
    from logosforge.ui.structure_view import StructureView
    db = Database()
    proj = db.create_project("S")
    view = StructureView(db, proj.id)        # keep a ref so the widget lives
    html = view._browser.toHtml()
    assert "No scenes yet" in html and "Outline" in html


def test_structure_click_to_scene(_qapp):
    from PySide6.QtCore import QUrl
    from logosforge.ui.structure_view import StructureView
    db = Database()
    proj = db.create_project("S", narrative_engine="novel")
    scene = db.create_scene(proj.id, "Opening", act="Act I", chapter="Ch")
    opened: list[int] = []
    view = StructureView(db, proj.id, on_open_scene=opened.append)
    assert "scene:" in view._browser.toHtml()
    view._on_anchor(QUrl(f"scene:{scene.id}"))
    assert opened == [scene.id]
