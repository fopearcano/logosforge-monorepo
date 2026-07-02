"""Tests for Story Health Panel."""

from logosforge.db import Database
from logosforge.story_health import (
    HealthSignal,
    StoryHealth,
    compute_health,
    level_color,
)
from logosforge.ui import theme
from logosforge.ui.story_health_view import StoryHealthView


def _make_project():
    db = Database()
    proj = db.create_project("HealthTest")
    return db, proj


def _make_complete_project():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Alice")
    c2 = db.create_character(proj.id, "Bob")
    for i in range(6):
        act = "Act 1" if i < 2 else ("Act 2" if i < 4 else "Act 3")
        chapter = f"Ch {i // 2 + 1}"
        db.create_scene(
            proj.id, f"Scene {i+1}",
            content="x" * 600,
            act=act,
            chapter=chapter,
            plotline="Main",
            beat="Hook" if i == 0 else "",
            character_ids=[c1.id] if i % 2 == 0 else [c1.id, c2.id],
        )
    return db, proj, c1, c2


def _make_sparse_project():
    db, proj = _make_project()
    db.create_character(proj.id, "Loner")
    db.create_scene(proj.id, "Only scene", content="Short.")
    return db, proj


# -- compute_health basic ---------------------------------------------------

def test_empty_project():
    db, proj = _make_project()
    health = compute_health(db, proj.id)
    assert isinstance(health, StoryHealth)
    assert health.structure.level == "problematic"


def test_complete_project_structure():
    db, proj, *_ = _make_complete_project()
    health = compute_health(db, proj.id)
    assert health.structure.level == "balanced"
    assert health.structure.label == "Complete"


def test_sparse_project_structure():
    db, proj = _make_sparse_project()
    health = compute_health(db, proj.id)
    assert health.structure.level == "problematic"


# -- Character distribution -------------------------------------------------

def test_characters_balanced():
    db, proj, c1, c2 = _make_complete_project()
    health = compute_health(db, proj.id)
    assert health.characters.level in ("balanced", "sparse")


def test_characters_empty():
    db, proj = _make_project()
    db.create_scene(proj.id, "No chars", content="test")
    health = compute_health(db, proj.id)
    assert health.characters.label in ("No data", "Unused")


def test_characters_all_in_one():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Hero")
    c2 = db.create_character(proj.id, "Sidekick")
    db.create_scene(proj.id, "S1", content="test", character_ids=[c1.id])
    db.create_scene(proj.id, "S2", content="test", character_ids=[c1.id])
    db.create_scene(proj.id, "S3", content="test", character_ids=[c1.id])
    health = compute_health(db, proj.id)
    assert health.characters.level in ("sparse", "problematic")


# -- Arc coverage -----------------------------------------------------------

def test_arcs_complete():
    db, proj, *_ = _make_complete_project()
    health = compute_health(db, proj.id)
    assert health.arcs.level == "balanced"


def test_arcs_no_plotlines():
    db, proj = _make_project()
    db.create_scene(proj.id, "S1", content="test")
    db.create_scene(proj.id, "S2", content="test")
    health = compute_health(db, proj.id)
    assert health.arcs.label == "No arcs"


def test_arcs_fragmented():
    db, proj = _make_project()
    for i in range(6):
        db.create_scene(
            proj.id, f"S{i}", content="test",
            plotline=f"Plot{i}",
        )
    health = compute_health(db, proj.id)
    assert health.arcs.level == "problematic"


# -- Scene density ----------------------------------------------------------

def test_density_developed():
    db, proj, *_ = _make_complete_project()
    health = compute_health(db, proj.id)
    assert health.density.level == "balanced"
    assert health.density.label == "Developed"


def test_density_thin():
    db, proj = _make_sparse_project()
    health = compute_health(db, proj.id)
    assert health.density.level == "problematic"


def test_density_sparse():
    db, proj = _make_project()
    db.create_scene(proj.id, "S1", content="x" * 200)
    db.create_scene(proj.id, "S2", content="x" * 150)
    health = compute_health(db, proj.id)
    assert health.density.label == "Sparse"


# -- level_color ------------------------------------------------------------

def test_color_balanced():
    assert level_color("balanced") == "#4ade80"


def test_color_sparse():
    assert level_color("sparse") == "#f59e0b"


def test_color_problematic():
    assert level_color("problematic") == "#ef4444"


# -- HealthSignal dataclass -------------------------------------------------

def test_signal_fields():
    s = HealthSignal("Complete", "balanced", 0.85)
    assert s.label == "Complete"
    assert s.level == "balanced"
    assert s.score == 0.85


# -- StoryHealthView widget -------------------------------------------------

def test_view_construction():
    db, proj, *_ = _make_complete_project()
    view = StoryHealthView(db, proj.id)
    health = view.get_health()
    assert isinstance(health, StoryHealth)


def test_view_empty_project():
    db, proj = _make_project()
    view = StoryHealthView(db, proj.id)
    health = view.get_health()
    assert health.structure.level == "problematic"


def test_view_refresh():
    db, proj = _make_project()
    view = StoryHealthView(db, proj.id)
    db.create_scene(proj.id, "New", content="x" * 800, act="Act 1",
                    chapter="Ch 1", plotline="Main", beat="Hook")
    view.refresh()
    health = view.get_health()
    assert health.structure.score > 0


# -- Theme styles -----------------------------------------------------------

def test_theme_has_health_view():
    ss = theme.build_stylesheet()
    assert "#storyHealthView" in ss


def test_theme_has_health_title():
    ss = theme.build_stylesheet()
    assert "#healthTitle" in ss


def test_theme_has_health_bar():
    ss = theme.build_stylesheet()
    assert "#healthBar" in ss


def test_theme_has_health_progress():
    ss = theme.build_stylesheet()
    assert "#healthProgressBar" in ss
