"""Tests for Series data structures (season/episode/arc/plotline)."""

import pytest

from logosforge.db import Database
from logosforge.models import (
    Episode,
    EpisodePlotline,
    Season,
    SeriesArc,
)


def _show(db):
    return db.create_project(
        "Show", narrative_engine="series", default_writing_format="series",
    )


# =========================================================================
# 1. Models exist
# =========================================================================

def test_model_tables():
    assert Season.__tablename__ == "season"
    assert Episode.__tablename__ == "episode"
    assert SeriesArc.__tablename__ == "seriesarc"
    assert EpisodePlotline.__tablename__ == "episodeplotline"


def test_season_fields():
    f = Season.model_fields
    for name in ("season_number", "title", "summary", "season_arc",
                 "central_question", "finale_payoff", "status", "order_index"):
        assert name in f


def test_episode_fields():
    f = Episode.model_fields
    for name in ("season_id", "episode_number", "title", "logline", "summary",
                 "episode_engine", "teaser", "act_breaks", "cliffhanger",
                 "status", "estimated_runtime_minutes", "order_index"):
        assert name in f


def test_arc_fields():
    f = SeriesArc.model_fields
    for name in ("scope", "title", "summary", "setup_episode_id",
                 "payoff_episode_id", "status", "linked_psyke_entries", "notes"):
        assert name in f


def test_plotline_fields():
    f = EpisodePlotline.model_fields
    for name in ("episode_id", "type", "title", "summary", "characters",
                 "resolution_state", "order_index"):
        assert name in f


# =========================================================================
# 2. Seasons persist
# =========================================================================

def test_create_season_persists():
    db = Database()
    p = _show(db)
    s = db.create_season(
        p.id, title="Season 1", season_arc="find the truth",
        central_question="who did it?", finale_payoff="the reveal",
        status="active",
    )
    loaded = db.get_season_by_id(s.id)
    assert loaded.title == "Season 1"
    assert loaded.season_arc == "find the truth"
    assert loaded.central_question == "who did it?"
    assert loaded.finale_payoff == "the reveal"
    assert loaded.status == "active"


def test_seasons_auto_number_and_order():
    db = Database()
    p = _show(db)
    for _ in range(3):
        db.create_season(p.id)
    seasons = db.get_seasons(p.id)
    assert [s.season_number for s in seasons] == [1, 2, 3]
    assert [s.order_index for s in seasons] == [0, 1, 2]


def test_update_season():
    db = Database()
    p = _show(db)
    s = db.create_season(p.id, status="active")
    db.update_season(s.id, status="complete", finale_payoff="boom")
    loaded = db.get_season_by_id(s.id)
    assert loaded.status == "complete"
    assert loaded.finale_payoff == "boom"


# =========================================================================
# 3. Episodes persist
# =========================================================================

def test_create_episode_persists():
    db = Database()
    p = _show(db)
    s = db.create_season(p.id)
    e = db.create_episode(
        s.id, title="Pilot", logline="it begins",
        episode_engine="introduce the world", teaser="a cold body",
        cliffhanger="the gun reveal", estimated_runtime_minutes=42,
    )
    loaded = db.get_episode_by_id(e.id)
    assert loaded.title == "Pilot"
    assert loaded.logline == "it begins"
    assert loaded.episode_engine == "introduce the world"
    assert loaded.cliffhanger == "the gun reveal"
    assert loaded.estimated_runtime_minutes == 42
    assert loaded.project_id == p.id   # convenience scoping


def test_episodes_auto_number_and_order():
    db = Database()
    p = _show(db)
    s = db.create_season(p.id)
    for _ in range(3):
        db.create_episode(s.id)
    eps = db.get_episodes_for_season(s.id)
    assert [e.episode_number for e in eps] == [1, 2, 3]


def test_episodes_by_project():
    db = Database()
    p = _show(db)
    s1 = db.create_season(p.id)
    s2 = db.create_season(p.id)
    db.create_episode(s1.id, title="S1E1")
    db.create_episode(s2.id, title="S2E1")
    assert len(db.get_episodes(p.id)) == 2


def test_update_episode():
    db = Database()
    p = _show(db)
    s = db.create_season(p.id)
    e = db.create_episode(s.id)
    db.update_episode(e.id, status="final", cliffhanger="she's alive")
    loaded = db.get_episode_by_id(e.id)
    assert loaded.status == "final"
    assert loaded.cliffhanger == "she's alive"


# =========================================================================
# 4. Arcs persist (reuse PSYKE, not duplicated)
# =========================================================================

def test_create_arc_persists():
    db = Database()
    p = _show(db)
    s = db.create_season(p.id)
    e1 = db.create_episode(s.id, title="Pilot")
    e2 = db.create_episode(s.id, title="Finale")
    hero = db.create_psyke_entry(p.id, "Detective", entry_type="character")
    arc = db.create_series_arc(
        p.id, scope="mystery", title="Who killed Laura",
        setup_episode_id=e1.id, payoff_episode_id=e2.id, status="delayed",
        linked_psyke_entries=[hero.id], notes="slow burn",
    )
    loaded = db.get_series_arcs(p.id)[0]
    assert loaded.scope == "mystery"
    assert loaded.title == "Who killed Laura"
    assert loaded.setup_episode_id == e1.id
    assert loaded.payoff_episode_id == e2.id
    assert loaded.status == "delayed"
    assert db.csv_split(loaded.linked_psyke_entries) == [str(hero.id)]


def test_update_arc_status_and_links():
    db = Database()
    p = _show(db)
    arc = db.create_series_arc(p.id, scope="series", title="The Big One")
    e = db.create_psyke_entry(p.id, "Theme", entry_type="theme")
    db.update_series_arc(arc.id, status="resolved", linked_psyke_entries=[e.id])
    loaded = db.get_series_arcs(p.id)[0]
    assert loaded.status == "resolved"
    assert db.csv_split(loaded.linked_psyke_entries) == [str(e.id)]


# =========================================================================
# 5. Plotlines persist + ordering
# =========================================================================

def test_create_plotlines_persist_and_order():
    db = Database()
    p = _show(db)
    s = db.create_season(p.id)
    e = db.create_episode(s.id)
    db.create_episode_plotline(e.id, type="A", title="main case",
                               characters=["Detective"], resolution_state="open")
    db.create_episode_plotline(e.id, type="B", title="subplot")
    db.create_episode_plotline(e.id, type="runner", title="running gag")
    pls = db.get_episode_plotlines(e.id)
    assert [pl.type for pl in pls] == ["A", "B", "runner"]
    assert [pl.order_index for pl in pls] == [0, 1, 2]
    assert db.csv_split(pls[0].characters) == ["Detective"]
    assert pls[0].resolution_state == "open"


# =========================================================================
# 6. Reload + backward compatibility
# =========================================================================

def test_reload_from_disk(tmp_path):
    path = str(tmp_path / "show.db")
    db = Database(path)
    p = _show(db)
    s = db.create_season(p.id, title="Season 1", season_arc="arc")
    e = db.create_episode(s.id, title="Pilot", estimated_runtime_minutes=45)
    db.create_episode_plotline(e.id, type="A", title="case")
    db.create_series_arc(p.id, scope="season", title="Arc")
    pid, sid, eid = p.id, s.id, e.id

    db2 = Database(path)
    assert db2.get_season_by_id(sid).season_arc == "arc"
    assert db2.get_episode_by_id(eid).estimated_runtime_minutes == 45
    assert len(db2.get_episodes_for_season(sid)) == 1
    assert len(db2.get_episode_plotlines(eid)) == 1
    assert len(db2.get_series_arcs(pid)) == 1


def test_old_project_loads_with_empty_series_data(tmp_path):
    path = str(tmp_path / "novel.db")
    db = Database(path)
    p = db.create_project("Novel")  # default novel engine
    db.create_scene(p.id, "Chapter 1", content="prose")
    db2 = Database(path)
    assert db2.get_seasons(p.id) == []
    assert db2.get_episodes(p.id) == []
    assert db2.get_series_arcs(p.id) == []


def test_series_data_scoped_to_project():
    db = Database()
    a = _show(db)
    b = _show(db)
    db.create_season(a.id, title="A-S1")
    db.create_season(b.id, title="B-S1")
    assert [s.title for s in db.get_seasons(a.id)] == ["A-S1"]
    assert [s.title for s in db.get_seasons(b.id)] == ["B-S1"]
