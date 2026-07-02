"""Tests for Series Plot and Timeline behavior (season/episode-aware)."""

import pytest

from logosforge.db import Database
from logosforge.series_plot import (
    SERIES_COLORS,
    get_episode_detail,
    get_season_progression,
    get_series_plot_blocks,
    get_series_plot_seasons,
    get_series_timeline,
    get_setup_payoff_chains,
    series_color_label,
)


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    yield
    settings._instance = None


def _show(db):
    return db.create_project(
        "Show", narrative_engine="series", default_writing_format="series",
    )


def _build(db, project_id):
    """Two seasons, three episodes, plotlines, and spanning arcs.

    S1E1 (Pilot)   — A/B plot, season + mystery arc setup, cliffhanger
    S1E2 (Fallout) — C plot
    S2E1 (Return)  — mystery payoff
    """
    s1 = db.create_season(project_id, title="Season 1", season_arc="rise")
    s2 = db.create_season(project_id, title="Season 2")
    e1 = db.create_episode(
        s1.id, title="Pilot", logline="A body turns up",
        act_breaks="Teaser\nAct 1\nAct 2", cliffhanger="The phone rings",
        estimated_runtime_minutes=42,
    )
    e2 = db.create_episode(s1.id, title="Fallout", logline="Aftermath")
    e3 = db.create_episode(
        s2.id, title="Return", logline="The truth", project_id=project_id,
    )
    db.create_episode_plotline(e1.id, type="A", title="The murder case")
    db.create_episode_plotline(e1.id, type="B", title="Cooper and Audrey")
    db.create_episode_plotline(e2.id, type="C", title="Town gossip")
    # Mystery arc set up in S1E1, paid off in S2E1 → spans every episode.
    db.create_series_arc(
        project_id, scope="mystery", title="Who killed Laura",
        setup_episode_id=e1.id, payoff_episode_id=e3.id, status="active",
    )
    # Season arc local to S1 (no payoff episode → open-ended).
    db.create_series_arc(
        project_id, scope="season", title="Cooper's redemption",
        setup_episode_id=e1.id, status="active",
    )
    return s1, s2, e1, e2, e3


# =========================================================================
# 1. Color / label system (§4)
# =========================================================================

def test_color_labels_cover_plot_and_arc_kinds():
    for kind in ("A", "B", "C", "runner", "mystery", "relationship",
                 "season", "series", "character", "episode"):
        assert series_color_label(kind) == SERIES_COLORS[kind]
        assert series_color_label(kind).startswith("#")


def test_color_label_unknown_is_empty():
    assert series_color_label("nope") == ""


def test_colors_persist_across_calls():
    db = Database()
    p = _show(db)
    _build(db, p.id)
    first = get_series_plot_blocks(db, p.id)[0]["plot_indicators"]
    second = get_series_plot_blocks(db, p.id)[0]["plot_indicators"]
    assert first == second
    assert {i["type"]: i["color"] for i in first} == {
        "A": SERIES_COLORS["A"], "B": SERIES_COLORS["B"],
    }


# =========================================================================
# 2. Plot grid — episodes grouped by seasons (§1)
# =========================================================================

def test_plot_blocks_carry_episode_metadata():
    db = Database()
    p = _show(db)
    _build(db, p.id)
    blocks = get_series_plot_blocks(db, p.id)
    pilot = blocks[0]
    assert pilot["title"] == "Pilot"
    assert pilot["logline"] == "A body turns up"
    assert pilot["cliffhanger"] == "The phone rings"
    assert pilot["runtime"] == 42
    assert [i["type"] for i in pilot["plot_indicators"]] == ["A", "B"]


def test_plot_grouped_by_seasons():
    db = Database()
    p = _show(db)
    _build(db, p.id)
    seasons = get_series_plot_seasons(db, p.id)
    assert [g["title"] for g in seasons] == ["Season 1", "Season 2"]
    assert [e["title"] for e in seasons[0]["episodes"]] == ["Pilot", "Fallout"]
    assert [e["title"] for e in seasons[1]["episodes"]] == ["Return"]


def test_plot_block_setup_and_payoff_markers():
    db = Database()
    p = _show(db)
    _s1, _s2, e1, _e2, e3 = _build(db, p.id)
    blocks = {b["id"]: b for b in get_series_plot_blocks(db, p.id)}
    assert "Who killed Laura" in blocks[e1.id]["setup_markers"]
    assert "Cooper's redemption" in blocks[e1.id]["setup_markers"]
    assert "Who killed Laura" in blocks[e3.id]["payoff_markers"]
    assert blocks[e1.id]["payoff_markers"] == []


def test_active_arcs_visible_and_span_episodes():
    db = Database()
    p = _show(db)
    _s1, _s2, e1, e2, e3 = _build(db, p.id)
    blocks = {b["id"]: b for b in get_series_plot_blocks(db, p.id)}
    # Mystery arc spans setup (E1) through payoff (E3): active in all three.
    for eid in (e1.id, e2.id, e3.id):
        titles = {a["title"] for a in blocks[eid]["active_arcs"]}
        assert "Who killed Laura" in titles
    # Season arc has no payoff → still open at the last episode.
    assert "Cooper's redemption" in {
        a["title"] for a in blocks[e3.id]["active_arcs"]
    }


def test_resolved_arc_not_active():
    db = Database()
    p = _show(db)
    _s1, _s2, e1, _e2, _e3 = _build(db, p.id)
    db.create_series_arc(p.id, scope="character", title="Closed",
                         setup_episode_id=e1.id, status="resolved")
    blocks = {b["id"]: b for b in get_series_plot_blocks(db, p.id)}
    assert "Closed" not in {a["title"] for a in blocks[e1.id]["active_arcs"]}


# =========================================================================
# 3. Episode detail (§2)
# =========================================================================

def test_episode_detail_acts_and_plotlines():
    db = Database()
    p = _show(db)
    _s1, _s2, e1, _e2, _e3 = _build(db, p.id)
    detail = get_episode_detail(db, p.id, e1.id)
    assert detail["title"] == "Pilot"
    assert detail["acts"] == ["Teaser", "Act 1", "Act 2"]
    assert [pl["type"] for pl in detail["plotlines"]] == ["A", "B"]
    assert "Who killed Laura" in {a["title"] for a in detail["active_arcs"]}
    assert detail["scenes"] == []  # not linked yet (first pass)


def test_episode_detail_missing_returns_empty():
    db = Database()
    p = _show(db)
    assert get_episode_detail(db, p.id, 999) == {}


# =========================================================================
# 4. Timeline — episode order across seasons + arc evolution (§3)
# =========================================================================

def test_timeline_episode_order_across_seasons():
    db = Database()
    p = _show(db)
    _build(db, p.id)
    rows = get_series_timeline(db, p.id)
    assert [r["order"] for r in rows] == [1, 2, 3]
    assert [r["title"] for r in rows] == ["Pilot", "Fallout", "Return"]
    assert [r["season"] for r in rows] == ["Season 1", "Season 1", "Season 2"]


def test_timeline_setup_payoff_and_cliffhanger_markers():
    db = Database()
    p = _show(db)
    _build(db, p.id)
    rows = get_series_timeline(db, p.id)
    assert "Who killed Laura" in rows[0]["setup"]
    assert rows[0]["cliffhanger"] == "The phone rings"
    assert "Who killed Laura" in rows[2]["payoff"]


def test_timeline_active_arcs_evolve():
    db = Database()
    p = _show(db)
    _build(db, p.id)
    rows = get_series_timeline(db, p.id)
    for r in rows:
        assert "Who killed Laura" in {a["title"] for a in r["active_arcs"]}


def test_season_progression():
    db = Database()
    p = _show(db)
    _build(db, p.id)
    assert get_season_progression(db, p.id) == ["Season 1", "Season 2"]


def test_setup_payoff_chains():
    db = Database()
    p = _show(db)
    _s1, _s2, e1, _e2, e3 = _build(db, p.id)
    chains = get_setup_payoff_chains(db, p.id)
    # Only the mystery arc has both setup and payoff episodes.
    assert len(chains) == 1
    chain = chains[0]
    assert chain["title"] == "Who killed Laura"
    assert chain["setup_episode_id"] == e1.id
    assert chain["payoff_episode_id"] == e3.id
    assert chain["setup_order"] == 0
    assert chain["payoff_order"] == 2
    assert chain["color"] == SERIES_COLORS["mystery"]


# =========================================================================
# 5. Plot view integration (§1, §5)
# =========================================================================

def test_grid_view_series_mode():
    from logosforge.ui.story_grid_view import StoryGridView
    db = Database()
    p = _show(db)
    view = StoryGridView(db, p.id)
    assert view.is_series_mode() is True
    assert view._block_unit == "episode"
    assert view._block_number_label(1) == "Ep 1"


def test_grid_view_shows_episodes_grouped_by_seasons():
    from logosforge.ui.story_grid_view import StoryGridView
    db = Database()
    p = _show(db)
    _s1, _s2, e1, _e2, _e3 = _build(db, p.id)
    view = StoryGridView(db, p.id)
    seasons = view.get_series_plot_seasons()
    assert [g["title"] for g in seasons] == ["Season 1", "Season 2"]
    assert len(view.get_series_plot_blocks()) == 3
    assert view.get_series_episode_detail(e1.id)["title"] == "Pilot"


def test_grid_view_novel_no_series_blocks():
    from logosforge.ui.story_grid_view import StoryGridView
    db = Database()
    p = db.create_project("Novel")
    view = StoryGridView(db, p.id)
    assert view.is_series_mode() is False
    assert view.get_series_plot_blocks() == []
    assert view.get_series_plot_seasons() == []
    assert view.get_series_episode_detail(1) == {}


# =========================================================================
# 6. Timeline view integration (§3, §5)
# =========================================================================

def test_timeline_view_series_integration():
    from logosforge.ui.timeline_view import TimelineView
    db = Database()
    p = _show(db)
    _build(db, p.id)
    view = TimelineView(db, p.id)
    assert view.is_series_mode() is True
    rows = view.get_series_timeline_rows()
    assert [r["title"] for r in rows] == ["Pilot", "Fallout", "Return"]
    assert view.get_series_season_progression() == ["Season 1", "Season 2"]
    assert len(view.get_series_setup_payoff_chains()) == 1


def test_timeline_view_novel_empty():
    from logosforge.ui.timeline_view import TimelineView
    db = Database()
    p = db.create_project("Novel")
    view = TimelineView(db, p.id)
    assert view.is_series_mode() is False
    assert view.get_series_timeline_rows() == []
    assert view.get_series_season_progression() == []
    assert view.get_series_setup_payoff_chains() == []


# =========================================================================
# 7. Empty-project safety
# =========================================================================

def test_empty_project_safe():
    db = Database()
    p = _show(db)
    assert get_series_plot_blocks(db, p.id) == []
    assert get_series_plot_seasons(db, p.id) == []
    assert get_series_timeline(db, p.id) == []
    assert get_season_progression(db, p.id) == []
    assert get_setup_payoff_chains(db, p.id) == []
