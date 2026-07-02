"""Tests for the PSYKE long-form series-memory layer."""

import pytest

from logosforge.db import Database
from logosforge.psyke_series import (
    CHARACTER_SERIES_FIELDS,
    MOTIF_CALLBACK_FIELDS,
    add_relationship_evolution,
    build_series_memory_context,
    get_episode_memory,
    get_mystery_threads,
    get_relationship_evolution,
    get_series_memory,
    get_unresolved_threads,
    series_fields_for_type,
    set_series_memory,
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


# =========================================================================
# 1. Field schemas (§1, §4)
# =========================================================================

def test_character_series_fields():
    for f in ("season_arc", "episode_state", "long_term_goal",
              "unresolved_conflicts", "relationship_history",
              "continuity_flags", "current_status_by_episode"):
        assert f in CHARACTER_SERIES_FIELDS


def test_motif_callback_fields():
    for f in ("recurring_lines", "recurring_objects", "visual_motifs",
              "themes", "callbacks", "callback_episodes"):
        assert f in MOTIF_CALLBACK_FIELDS


def test_fields_for_type():
    assert series_fields_for_type("character") == CHARACTER_SERIES_FIELDS
    assert series_fields_for_type("theme") == MOTIF_CALLBACK_FIELDS
    assert series_fields_for_type("place") == ()


# =========================================================================
# 2. Character series memory persists (§1)
# =========================================================================

def test_series_memory_persists():
    db = Database()
    p = _show(db)
    e = db.create_psyke_entry(p.id, "Cooper", entry_type="character")
    set_series_memory(db, e.id, episode_state="grieving",
                      long_term_goal="solve the murder")
    mem = get_series_memory(db, e.id)
    assert mem["episode_state"] == "grieving"
    assert mem["long_term_goal"] == "solve the murder"


def test_current_status_by_episode_persists():
    db = Database()
    p = _show(db)
    e = db.create_psyke_entry(p.id, "Cooper", entry_type="character")
    set_series_memory(db, e.id, current_status_by_episode={"1": "arrives", "2": "leaves"})
    mem = get_series_memory(db, e.id)
    assert mem["current_status_by_episode"]["1"] == "arrives"


def test_series_memory_merges_and_isolates_sections():
    db = Database()
    p = _show(db)
    e = db.create_psyke_entry(
        p.id, "Cooper", entry_type="character", details={"role": "lead"},
    )
    db.set_psyke_visual_memory(e.id, {"silhouette": "tall"})
    set_series_memory(db, e.id, episode_state="x")
    details = db.get_psyke_entry_details(e.id)
    assert details["role"] == "lead"
    assert details["visual"]["silhouette"] == "tall"
    assert details["series"]["episode_state"] == "x"


def test_reload_from_disk(tmp_path):
    path = str(tmp_path / "show.db")
    db = Database(path)
    p = _show(db)
    e = db.create_psyke_entry(p.id, "Cooper", entry_type="character")
    set_series_memory(db, e.id, season_arc="redemption",
                      continuity_flags="lost an eye in ep3")
    eid = e.id
    db2 = Database(path)
    mem = get_series_memory(db2, eid)
    assert mem["season_arc"] == "redemption"
    assert mem["continuity_flags"] == "lost an eye in ep3"


# =========================================================================
# 3. Relationship evolution (§2)
# =========================================================================

def test_relationship_evolution_persists():
    db = Database()
    p = _show(db)
    e = db.create_psyke_entry(p.id, "Cooper", entry_type="character")
    s = db.create_season(p.id)
    ep1 = db.create_episode(s.id)
    ep2 = db.create_episode(s.id)
    add_relationship_evolution(db, e.id, episode_id=ep1.id, state="allies",
                               change="meet", cause="case",
                               unresolved_tension="trust")
    add_relationship_evolution(db, e.id, episode_id=ep2.id, state="betrayed",
                               change="lie revealed")
    beats = get_relationship_evolution(db, e.id)
    assert len(beats) == 2
    assert beats[0]["state"] == "allies"
    assert beats[0]["unresolved_tension"] == "trust"
    assert beats[1]["episode_id"] == ep2.id


def test_relationship_evolution_reloads(tmp_path):
    path = str(tmp_path / "rel.db")
    db = Database(path)
    p = _show(db)
    e = db.create_psyke_entry(p.id, "Cooper", entry_type="character")
    add_relationship_evolution(db, e.id, state="rivals", change="clash")
    eid = e.id
    db2 = Database(path)
    assert get_relationship_evolution(db2, eid)[0]["state"] == "rivals"


# =========================================================================
# 4. Mystery / thread tracking (§3)
# =========================================================================

def test_mystery_threads_from_arcs():
    db = Database()
    p = _show(db)
    s = db.create_season(p.id)
    e1 = db.create_episode(s.id)
    e2 = db.create_episode(s.id)
    db.create_series_arc(p.id, scope="mystery", title="Who killed Laura",
                         setup_episode_id=e1.id, payoff_episode_id=e2.id,
                         status="delayed")
    db.create_series_arc(p.id, scope="character", title="Redemption",
                         status="resolved")
    threads = get_mystery_threads(db, p.id)
    assert len(threads) == 2
    titles = {t["title"]: t for t in threads}
    assert titles["Who killed Laura"]["setup_episode_id"] == e1.id
    assert titles["Who killed Laura"]["payoff_episode_id"] == e2.id


def test_unresolved_threads():
    db = Database()
    p = _show(db)
    db.create_series_arc(p.id, scope="mystery", title="Open", status="active")
    db.create_series_arc(p.id, scope="mystery", title="Late", status="delayed")
    db.create_series_arc(p.id, scope="mystery", title="Done", status="resolved")
    titles = {t["title"] for t in get_unresolved_threads(db, p.id)}
    assert titles == {"Open", "Late"}


# =========================================================================
# 5. Episode memory (§5)
# =========================================================================

def test_episode_memory_setup_payoff_unresolved():
    db = Database()
    p = _show(db)
    s = db.create_season(p.id)
    e1 = db.create_episode(s.id)
    e2 = db.create_episode(s.id)
    db.create_series_arc(p.id, scope="mystery", title="The Killer",
                         setup_episode_id=e1.id, payoff_episode_id=e2.id,
                         status="active")
    db.create_episode_plotline(e1.id, type="A", title="case",
                               resolution_state="open")
    cooper = db.create_psyke_entry(p.id, "Cooper", entry_type="character")
    set_series_memory(db, cooper.id,
                      current_status_by_episode={str(e1.id): "arrives in town"})
    mem1 = get_episode_memory(db, p.id, e1.id)
    assert "The Killer" in mem1["set_up"]
    assert mem1["paid_off"] == []
    assert "The Killer" in mem1["unresolved"]
    assert any("case" in pl for pl in mem1["open_plotlines"])
    assert any("Cooper" in cs for cs in mem1["character_status"])
    mem2 = get_episode_memory(db, p.id, e2.id)
    assert "The Killer" in mem2["paid_off"]


# =========================================================================
# 6. Assistant context (§6, §7)
# =========================================================================

def test_context_includes_series_facets():
    db = Database()
    p = _show(db)
    s = db.create_season(p.id, title="Season 1")
    e1 = db.create_episode(s.id, title="Pilot")
    e2 = db.create_episode(s.id, title="Finale")
    cooper = db.create_psyke_entry(p.id, "Cooper", entry_type="character")
    set_series_memory(db, cooper.id, episode_state="grieving",
                      continuity_flags="wears the ring")
    db.create_series_arc(p.id, scope="mystery", title="Who killed Laura",
                         setup_episode_id=e1.id, payoff_episode_id=e2.id,
                         status="delayed")
    ctx = build_series_memory_context(db, p.id, e2.id)
    assert ctx.startswith("[Series Memory]")
    assert "Season 1" in ctx
    assert "Current episode: Finale" in ctx
    assert "Unresolved threads" in ctx and "Who killed Laura" in ctx
    assert "Character state" in ctx and "grieving" in ctx
    assert "Continuity risks" in ctx and "wears the ring" in ctx
    assert "Paid off here" in ctx


def test_context_empty_when_no_series_data():
    db = Database()
    p = _show(db)
    assert build_series_memory_context(db, p.id) == ""


def test_assistant_sees_series_context():
    from logosforge.ui.assistant_view import AssistantPanel
    db = Database()
    p = _show(db)
    s = db.create_season(p.id, title="Season 1")
    db.create_episode(s.id, title="Pilot")
    cooper = db.create_psyke_entry(p.id, "Cooper", entry_type="character")
    set_series_memory(db, cooper.id, episode_state="on the run")
    db.create_scene(p.id, "Scene", content="x")
    panel = AssistantPanel(db, p.id)
    structural = panel._build_context()[8]
    assert "[Series Memory]" in structural
    assert "on the run" in structural


def test_novel_project_no_series_context():
    from logosforge.ui.assistant_view import AssistantPanel
    db = Database()
    p = db.create_project("Novel")
    e = db.create_psyke_entry(p.id, "X", entry_type="character")
    set_series_memory(db, e.id, episode_state="y")
    db.create_scene(p.id, "Chapter 1", content="x")
    panel = AssistantPanel(db, p.id)
    assert "[Series Memory]" not in panel._build_context()[8]
