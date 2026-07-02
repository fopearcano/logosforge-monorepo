"""Tests for Pacing & Insight System."""

from logosforge.pacing_insights import (
    Insight,
    generate_insights,
    insight_color,
    MIN_SCENES,
)
from logosforge.db import Database
from logosforge.ui import theme
from logosforge.ui.pacing_insights_view import PacingInsightsView


def _make_project():
    db = Database()
    proj = db.create_project("PacingTest")
    return db, proj


# -- Minimum threshold --------------------------------------------------------

def test_too_few_scenes_no_insights():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Alice")
    for i in range(MIN_SCENES - 1):
        db.create_scene(proj.id, f"S{i}", character_ids=[c1.id])
    result = generate_insights(db, proj.id)
    assert result == []


def test_empty_project():
    db, proj = _make_project()
    result = generate_insights(db, proj.id)
    assert result == []


# -- Disappearance -----------------------------------------------------------

def test_disappearance_detected():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Hero")
    c2 = db.create_character(proj.id, "Ghost")
    # Ghost appears at start and end, absent for 80% of scenes
    scenes = []
    for i in range(10):
        chars = [c1.id]
        if i == 0 or i == 9:
            chars.append(c2.id)
        scenes.append(db.create_scene(proj.id, f"S{i}", character_ids=chars))
    result = generate_insights(db, proj.id)
    disappearance = [i for i in result if i.category == "disappearance"]
    assert len(disappearance) == 1
    assert "Ghost" in disappearance[0].text


def test_no_disappearance_when_regular():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Hero")
    # Hero appears in every scene
    for i in range(8):
        db.create_scene(proj.id, f"S{i}", character_ids=[c1.id])
    result = generate_insights(db, proj.id)
    disappearance = [i for i in result if i.category == "disappearance"]
    assert disappearance == []


# -- Monotony ----------------------------------------------------------------

def test_monotony_plotline():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Hero")
    for i in range(6):
        db.create_scene(proj.id, f"S{i}", plotline="Main", character_ids=[c1.id])
    result = generate_insights(db, proj.id)
    monotony = [i for i in result if i.category == "monotony"]
    assert len(monotony) == 1
    assert "Main" in monotony[0].text


def test_monotony_character_set():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "A")
    c2 = db.create_character(proj.id, "B")
    for i in range(5):
        db.create_scene(proj.id, f"S{i}", character_ids=[c1.id, c2.id])
    result = generate_insights(db, proj.id)
    monotony = [i for i in result if i.category == "monotony"]
    assert len(monotony) == 1
    assert "character set" in monotony[0].text


def test_no_monotony_varied():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "A")
    c2 = db.create_character(proj.id, "B")
    plotlines = ["Main", "Sub", "Third", "Main", "Sub"]
    for i in range(5):
        chars = [c1.id] if i % 2 == 0 else [c2.id]
        db.create_scene(proj.id, f"S{i}", plotline=plotlines[i], character_ids=chars)
    result = generate_insights(db, proj.id)
    monotony = [i for i in result if i.category == "monotony"]
    assert monotony == []


# -- Stagnation --------------------------------------------------------------

def test_stagnation_middle_low_variety():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "A")
    c2 = db.create_character(proj.id, "B")
    c3 = db.create_character(proj.id, "C")
    # Start: diverse
    db.create_scene(proj.id, "S0", plotline="Main", character_ids=[c1.id, c2.id])
    db.create_scene(proj.id, "S1", plotline="Sub", character_ids=[c2.id, c3.id])
    db.create_scene(proj.id, "S2", plotline="Third", character_ids=[c1.id, c3.id])
    # Middle: monotone
    db.create_scene(proj.id, "S3", plotline="Main", character_ids=[c1.id])
    db.create_scene(proj.id, "S4", plotline="Main", character_ids=[c1.id])
    db.create_scene(proj.id, "S5", plotline="Main", character_ids=[c1.id])
    # End: diverse
    db.create_scene(proj.id, "S6", plotline="Sub", character_ids=[c2.id, c3.id])
    db.create_scene(proj.id, "S7", plotline="Third", character_ids=[c1.id, c2.id])
    db.create_scene(proj.id, "S8", plotline="Main", character_ids=[c3.id, c1.id])
    result = generate_insights(db, proj.id)
    stagnation = [i for i in result if i.category == "stagnation"]
    assert len(stagnation) == 1
    assert "Middle" in stagnation[0].text


def test_no_stagnation_balanced():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "A")
    c2 = db.create_character(proj.id, "B")
    for i in range(6):
        chars = [c1.id, c2.id] if i % 2 == 0 else [c1.id]
        db.create_scene(proj.id, f"S{i}", plotline="Main" if i % 2 == 0 else "Sub",
                        character_ids=chars)
    result = generate_insights(db, proj.id)
    stagnation = [i for i in result if i.category == "stagnation"]
    assert stagnation == []


# -- Arc neglect -------------------------------------------------------------

def test_arc_neglect_detected():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Hero")
    # Main arc spans 3 acts
    db.create_scene(proj.id, "S0", plotline="Main", act="Act 1", character_ids=[c1.id])
    db.create_scene(proj.id, "S1", plotline="Main", act="Act 2", character_ids=[c1.id])
    db.create_scene(proj.id, "S2", plotline="Main", act="Act 3", character_ids=[c1.id])
    # Subplot only in Act 1
    db.create_scene(proj.id, "S3", plotline="Subplot", act="Act 1", character_ids=[c1.id])
    db.create_scene(proj.id, "S4", plotline="Subplot", act="Act 1", character_ids=[c1.id])
    result = generate_insights(db, proj.id)
    neglect = [i for i in result if i.category == "neglect"]
    assert len(neglect) == 1
    assert "Subplot" in neglect[0].text


def test_no_neglect_when_arcs_span_acts():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Hero")
    for act in ["Act 1", "Act 2", "Act 3"]:
        db.create_scene(proj.id, f"S-Main-{act}", plotline="Main", act=act,
                        character_ids=[c1.id])
        db.create_scene(proj.id, f"S-Sub-{act}", plotline="Sub", act=act,
                        character_ids=[c1.id])
    result = generate_insights(db, proj.id)
    neglect = [i for i in result if i.category == "neglect"]
    assert neglect == []


# -- Clustering --------------------------------------------------------------

def test_clustering_detected():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Hero")
    c2 = db.create_character(proj.id, "Cameo")
    # Cameo only in scenes 0-1 out of 10
    for i in range(10):
        chars = [c1.id]
        if i < 2:
            chars.append(c2.id)
        db.create_scene(proj.id, f"S{i}", character_ids=chars)
    result = generate_insights(db, proj.id)
    clustering = [i for i in result if i.category == "clustering"]
    assert len(clustering) == 1
    assert "Cameo" in clustering[0].text


def test_no_clustering_when_spread():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Hero")
    c2 = db.create_character(proj.id, "Ally")
    # Ally spread across the story
    for i in range(8):
        chars = [c1.id]
        if i % 2 == 0:
            chars.append(c2.id)
        db.create_scene(proj.id, f"S{i}", character_ids=chars)
    result = generate_insights(db, proj.id)
    clustering = [i for i in result if i.category == "clustering"]
    assert clustering == []


# -- Max insights cap ---------------------------------------------------------

def test_max_five_insights():
    db, proj = _make_project()
    # Even if we construct a pathological case, we get at most 5
    # (Since we only have 5 detectors, max is naturally 5)
    c1 = db.create_character(proj.id, "A")
    for i in range(10):
        db.create_scene(proj.id, f"S{i}", character_ids=[c1.id])
    result = generate_insights(db, proj.id)
    assert len(result) <= 5


# -- Severity ordering --------------------------------------------------------

def test_insights_sorted_by_severity():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Hero")
    c2 = db.create_character(proj.id, "Ghost")
    # Multiple issues
    for i in range(10):
        chars = [c1.id]
        if i == 0 or i == 9:
            chars.append(c2.id)
        db.create_scene(proj.id, f"S{i}", plotline="Main", character_ids=chars)
    result = generate_insights(db, proj.id)
    if len(result) >= 2:
        severities = [i.severity for i in result]
        assert severities == sorted(severities, reverse=True)


# -- insight_color ------------------------------------------------------------

def test_insight_color_disappearance():
    assert insight_color("disappearance") == "#f59e0b"


def test_insight_color_monotony():
    assert insight_color("monotony") == "#a855f7"


def test_insight_color_stagnation():
    assert insight_color("stagnation") == "#ef4444"


def test_insight_color_neglect():
    assert insight_color("neglect") == "#0ea5e9"


def test_insight_color_clustering():
    assert insight_color("clustering") == "#6366f1"


def test_insight_color_unknown():
    assert insight_color("unknown") == "#9ca3af"


# -- PacingInsightsView widget ------------------------------------------------

def test_view_construction():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "A")
    for i in range(6):
        db.create_scene(proj.id, f"S{i}", plotline="Main", character_ids=[c1.id])
    view = PacingInsightsView(db, proj.id)
    insights = view.get_insights()
    assert insights is not None


def test_view_empty_project():
    db, proj = _make_project()
    view = PacingInsightsView(db, proj.id)
    insights = view.get_insights()
    assert insights == []


def test_view_refresh():
    db, proj = _make_project()
    view = PacingInsightsView(db, proj.id)
    c1 = db.create_character(proj.id, "A")
    for i in range(6):
        db.create_scene(proj.id, f"S{i}", plotline="Main", character_ids=[c1.id])
    view.refresh()
    assert len(view.get_insights()) > 0


# -- Theme styles -------------------------------------------------------------

def test_theme_has_insights_view():
    ss = theme.build_stylesheet()
    assert "#pacingInsightsView" in ss


def test_theme_has_insight_row():
    ss = theme.build_stylesheet()
    assert "#insightRow" in ss


def test_theme_has_insight_text():
    ss = theme.build_stylesheet()
    assert "#insightText" in ss


def test_theme_has_insights_empty():
    ss = theme.build_stylesheet()
    assert "#insightsEmpty" in ss
