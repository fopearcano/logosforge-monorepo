"""Tests for Character & Arc Balance View."""

from logosforge.character_balance import (
    ArcPresence,
    BalanceData,
    CharacterPresence,
    compute_balance,
    flag_color,
)
from logosforge.db import Database
from logosforge.ui import theme
from logosforge.ui.character_balance_view import CharacterBalanceView


def _make_project():
    db = Database()
    proj = db.create_project("BalanceTest")
    return db, proj


def _make_balanced_project():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Alice")
    c2 = db.create_character(proj.id, "Bob")
    c3 = db.create_character(proj.id, "Carol")
    for i in range(6):
        chars = [c1.id, c2.id] if i % 2 == 0 else [c2.id, c3.id]
        db.create_scene(
            proj.id, f"Scene {i+1}",
            plotline="Main" if i < 4 else "Sub",
            act="Act 1" if i < 2 else ("Act 2" if i < 4 else "Act 3"),
            character_ids=chars,
        )
    return db, proj, c1, c2, c3


def _make_unbalanced_project():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Hero")
    c2 = db.create_character(proj.id, "Sidekick")
    c3 = db.create_character(proj.id, "Ghost")
    for i in range(8):
        db.create_scene(
            proj.id, f"Scene {i+1}",
            plotline="Main",
            act="Act 1",
            character_ids=[c1.id],
        )
    db.create_scene(
        proj.id, "One off", plotline="Subplot",
        character_ids=[c2.id],
    )
    return db, proj, c1, c2, c3


# -- compute_balance basic ---------------------------------------------------

def test_empty_project():
    db, proj = _make_project()
    result = compute_balance(db, proj.id)
    assert isinstance(result, BalanceData)
    assert result.total_scenes == 0
    assert result.characters == []


def test_balanced_project():
    db, proj, c1, c2, c3 = _make_balanced_project()
    result = compute_balance(db, proj.id)
    assert result.total_scenes == 6
    assert len(result.characters) == 3


def test_characters_sorted_by_count():
    db, proj, c1, c2, c3 = _make_balanced_project()
    result = compute_balance(db, proj.id)
    counts = [p.scene_count for p in result.characters]
    assert counts == sorted(counts, reverse=True)


# -- Character flags ---------------------------------------------------------

def test_dominant_flag():
    db, proj, c1, c2, c3 = _make_unbalanced_project()
    result = compute_balance(db, proj.id)
    hero = next(p for p in result.characters if p.name == "Hero")
    assert hero.flag == "dominant"


def test_underused_flag():
    db, proj, c1, c2, c3 = _make_unbalanced_project()
    result = compute_balance(db, proj.id)
    ghost = next(p for p in result.characters if p.name == "Ghost")
    assert ghost.flag == "underused"


def test_no_flag_balanced():
    db, proj, c1, c2, c3 = _make_balanced_project()
    result = compute_balance(db, proj.id)
    flags = [p.flag for p in result.characters]
    assert all(f == "" for f in flags)


# -- Arc analysis ------------------------------------------------------------

def test_arcs_detected():
    db, proj, c1, c2, c3 = _make_balanced_project()
    result = compute_balance(db, proj.id)
    assert len(result.arcs) == 2
    plotlines = {a.plotline for a in result.arcs}
    assert "Main" in plotlines
    assert "Sub" in plotlines


def test_arc_sorted_by_count():
    db, proj, c1, c2, c3 = _make_balanced_project()
    result = compute_balance(db, proj.id)
    counts = [a.scene_count for a in result.arcs]
    assert counts == sorted(counts, reverse=True)


def test_thin_arc_flag():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Hero")
    for i in range(6):
        db.create_scene(
            proj.id, f"S{i}", plotline="Main", act=f"Act {i//2+1}",
            character_ids=[c1.id],
        )
    db.create_scene(proj.id, "Orphan", plotline="Thin")
    result = compute_balance(db, proj.id)
    thin = next(a for a in result.arcs if a.plotline == "Thin")
    assert thin.flag == "thin"


def test_no_arcs_no_plotlines():
    db, proj = _make_project()
    db.create_scene(proj.id, "No plot", content="test")
    result = compute_balance(db, proj.id)
    assert result.arcs == []


# -- CharacterPresence properties --------------------------------------------

def test_presence_ratio():
    p = CharacterPresence(1, "Alice", 3, 10)
    assert p.ratio == 0.3


def test_presence_ratio_zero_scenes():
    p = CharacterPresence(1, "Alice", 0, 0)
    assert p.ratio == 0.0


# -- flag_color --------------------------------------------------------------

def test_flag_color_dominant():
    assert flag_color("dominant") == "#f59e0b"


def test_flag_color_underused():
    assert flag_color("underused") == "#ef4444"


def test_flag_color_thin():
    assert flag_color("thin") == "#f59e0b"


def test_flag_color_none():
    assert flag_color("") == ""


# -- CharacterBalanceView widget ---------------------------------------------

def test_view_construction():
    db, proj, c1, c2, c3 = _make_balanced_project()
    view = CharacterBalanceView(db, proj.id)
    balance = view.get_balance()
    assert balance is not None
    assert len(balance.characters) == 3


def test_view_empty_project():
    db, proj = _make_project()
    view = CharacterBalanceView(db, proj.id)
    balance = view.get_balance()
    assert balance is not None
    assert balance.total_scenes == 0


def test_view_refresh():
    db, proj = _make_project()
    view = CharacterBalanceView(db, proj.id)
    c1 = db.create_character(proj.id, "New")
    db.create_scene(proj.id, "S1", plotline="Main", character_ids=[c1.id])
    view.refresh()
    balance = view.get_balance()
    assert len(balance.characters) == 1


def test_view_callback_character():
    db, proj, c1, c2, c3 = _make_balanced_project()
    calls = []
    view = CharacterBalanceView(
        db, proj.id,
        on_character_selected=lambda cid: calls.append(cid),
    )
    assert view.get_balance() is not None


def test_view_callback_plotline():
    db, proj, c1, c2, c3 = _make_balanced_project()
    calls = []
    view = CharacterBalanceView(
        db, proj.id,
        on_plotline_selected=lambda pl: calls.append(pl),
    )
    assert view.get_balance() is not None


# -- Theme styles -----------------------------------------------------------

def test_theme_has_balance_view():
    ss = theme.build_stylesheet()
    assert "#characterBalanceView" in ss


def test_theme_has_balance_row():
    ss = theme.build_stylesheet()
    assert "#balanceRow" in ss


def test_theme_has_balance_bar():
    ss = theme.build_stylesheet()
    assert "#balanceBar" in ss


def test_theme_has_balance_flag():
    ss = theme.build_stylesheet()
    assert "#balanceFlag" in ss
