"""Regression tests for the Analytics legibility pass.

Every status label (Health), imbalance flag (Balance) now carries a
plain-language explanation; Pacing messages surface the computed numbers; the
Narrative tension score has a legend. These pin that work so the explanations
can't silently drift away from the labels.
"""

from __future__ import annotations

import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge import character_balance as cb
from logosforge import story_health as sh
from logosforge.db import Database
from logosforge.pacing_insights import generate_insights


@pytest.fixture(scope="module")
def _qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# Health — every (metric, label) has help; "Thin" is disambiguated by metric
# ---------------------------------------------------------------------------

# Mirrors the labels each metric can emit in story_health.py.
_HEALTH_LABELS = {
    "Structure": ["Empty", "Complete", "Partial", "Thin"],
    "Characters": ["No data", "Unused", "Balanced", "Uneven", "Lopsided"],
    "Arc Coverage": ["Empty", "No arcs", "Complete", "Partial", "Fragmented"],
    "Scene Density": ["Empty", "Overloaded", "Developed", "Sparse", "Thin"],
}


def test_health_every_label_has_help():
    for metric, labels in _HEALTH_LABELS.items():
        for label in labels:
            assert sh.signal_help(metric, label), f"no help for {metric}/{label}"


def test_health_thin_disambiguated_by_metric():
    structure = sh.signal_help("Structure", "Thin")
    density = sh.signal_help("Scene Density", "Thin")
    assert structure and density
    assert structure != density          # same word, different meaning


def test_health_unknown_pair_is_empty():
    assert sh.signal_help("Structure", "Nope") == ""


# ---------------------------------------------------------------------------
# Balance — every imbalance flag has help
# ---------------------------------------------------------------------------

def test_balance_every_flag_has_help():
    for flag in ("dominant", "underused", "thin"):
        assert cb.flag_help(flag), f"no help for flag {flag}"
    assert cb.flag_help("") == ""
    assert cb.flag_help("nope") == ""


# ---------------------------------------------------------------------------
# Pacing — messages carry the computed numbers (still keep the name substring)
# ---------------------------------------------------------------------------

def test_pacing_disappearance_message_is_quantitative():
    db = Database()
    proj = db.create_project("P")
    db.create_character(proj.id, "Hero")
    ghost = db.create_character(proj.id, "Ghost")
    for i in range(10):
        chars = [1] + ([ghost.id] if i in (0, 9) else [])
        db.create_scene(proj.id, f"S{i}", character_ids=chars)
    dis = [i for i in generate_insights(db, proj.id)
           if i.category == "disappearance"]
    assert dis, "disappearance should be detected"
    assert "Ghost" in dis[0].text          # name preserved (existing contract)
    assert "%" in dis[0].text              # quantitative context added


# ---------------------------------------------------------------------------
# Narrative — the tension score has an explanatory legend
# ---------------------------------------------------------------------------

def test_narrative_tension_legend_present(_qapp):
    from PySide6.QtWidgets import QLabel
    from logosforge.ui.narrative_dashboard_view import NarrativeDashboardView
    db = Database()
    proj = db.create_project("N")
    view = NarrativeDashboardView(db, proj.id)
    texts = [lbl.text() for lbl in view.findChildren(QLabel)]
    assert any("Tension" in t and "25 points" in t for t in texts), \
        "tension-score legend missing"


# ---------------------------------------------------------------------------
# Low-severity polish: distinct pacing colors, inferred-acts flag, onboarding,
# pacing threshold message, acts-spanned display
# ---------------------------------------------------------------------------

def test_pacing_colors_are_distinct():
    from logosforge.pacing_insights import insight_color
    cats = ["disappearance", "monotony", "stagnation", "neglect", "clustering"]
    colors = [insight_color(c) for c in cats]
    assert len(set(colors)) == len(cats)        # one color per category


def test_narrative_structure_inferred_without_acts():
    from logosforge.narrative_dashboard import compute_dashboard
    db = Database()
    proj = db.create_project("N")
    for i in range(4):
        db.create_scene(proj.id, f"S{i}")        # no Act labels
    data = compute_dashboard(db, proj.id)
    assert data.structure.inferred is True and data.structure.segments


def test_narrative_structure_not_inferred_with_acts():
    from logosforge.narrative_dashboard import compute_dashboard
    db = Database()
    proj = db.create_project("N")
    for i in range(4):
        db.create_scene(proj.id, f"S{i}", act="Act I")
    data = compute_dashboard(db, proj.id)
    assert data.structure.inferred is False


def test_health_onboarding_shown_only_when_empty(_qapp):
    from logosforge.ui.story_health_view import StoryHealthView
    db = Database()
    proj = db.create_project("H")                # no scenes
    view = StoryHealthView(db, proj.id)
    assert not view._onboarding.isHidden()       # guidance shown
    db.create_scene(proj.id, "S1")
    view.refresh()
    assert view._onboarding.isHidden()           # hidden once there's a scene


def test_pacing_view_distinguishes_too_small_from_clean(_qapp):
    from PySide6.QtWidgets import QLabel
    from logosforge.ui.pacing_insights_view import PacingInsightsView
    db = Database()
    proj = db.create_project("P")                # 0 scenes
    view = PacingInsightsView(db, proj.id)
    texts = [lbl.text() for lbl in view.findChildren(QLabel)]
    assert any("activates at" in t for t in texts)


def test_balance_arc_shows_acts_spanned(_qapp):
    from PySide6.QtWidgets import QLabel
    from logosforge.ui.character_balance_view import CharacterBalanceView
    db = Database()
    proj = db.create_project("B")
    db.create_scene(proj.id, "S1", act="Act I", plotline="Main")
    db.create_scene(proj.id, "S2", act="Act II", plotline="Main")
    view = CharacterBalanceView(db, proj.id)
    texts = [lbl.text() for lbl in view.findChildren(QLabel)]
    assert any("2 acts" in t for t in texts)     # acts_spanned now displayed
