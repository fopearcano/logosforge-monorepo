"""Tests for temporal PSYKE reasoning layer (STEP 2)."""

from sqlmodel import Session

from logosforge.db import Database
from logosforge.models import Scene
from logosforge.temporal_psyke import TemporalGraph


def _make_project(db):
    return db.create_project("Test")


def _set_scene_order(db, scene_id, order):
    with Session(db._engine) as session:
        scene = session.get(Scene, scene_id)
        scene.sort_order = order
        session.commit()


# -- Entry with no progressions ------------------------------------------------

def test_entry_no_progressions():
    db = Database()
    proj = _make_project(db)
    entry = db.create_psyke_entry(proj.id, "Gandalf", entry_type="character")
    db.create_scene(proj.id, "Scene 1")

    tg = TemporalGraph(db, proj.id)
    state = tg.get_entry_state_at(entry.id, scene_order=0)
    assert state is not None
    assert state.name == "Gandalf"
    assert state.progression_text == ""
    assert state.progression_id is None
    assert state.has_progression is False


def test_entry_no_progressions_latest_is_none():
    db = Database()
    proj = _make_project(db)
    entry = db.create_psyke_entry(proj.id, "Frodo")

    tg = TemporalGraph(db, proj.id)
    prog = tg.get_latest_progression_before(entry.id, scene_order=5)
    assert prog is None


# -- Entry with multiple progressions ------------------------------------------

def test_multiple_progressions_insertion_order():
    db = Database()
    proj = _make_project(db)
    entry = db.create_psyke_entry(proj.id, "Aragorn", entry_type="character")
    db.create_psyke_progression(entry.id, "Ranger in the wild")
    db.create_psyke_progression(entry.id, "Revealed as Isildur's heir")
    db.create_psyke_progression(entry.id, "Crowned King of Gondor")

    tg = TemporalGraph(db, proj.id)
    state = tg.get_entry_state_at(entry.id, scene_order=999)
    assert state.has_progression
    assert state.progression_text == "Crowned King of Gondor"


def test_multiple_progressions_scene_linked():
    db = Database()
    proj = _make_project(db)
    entry = db.create_psyke_entry(proj.id, "Gandalf", entry_type="character")

    s1 = db.create_scene(proj.id, "Shire")
    s2 = db.create_scene(proj.id, "Moria")
    s3 = db.create_scene(proj.id, "Fangorn")
    _set_scene_order(db, s1.id, 1)
    _set_scene_order(db, s2.id, 2)
    _set_scene_order(db, s3.id, 3)

    db.create_psyke_progression(entry.id, "Gandalf the Grey", scene_id=s1.id)
    db.create_psyke_progression(entry.id, "Falls in Moria", scene_id=s2.id)
    db.create_psyke_progression(entry.id, "Returns as Gandalf the White", scene_id=s3.id)

    tg = TemporalGraph(db, proj.id)

    # At scene order 1 (Shire), only the first progression is available
    state1 = tg.get_entry_state_at(entry.id, scene_order=1)
    assert state1.progression_text == "Gandalf the Grey"

    # At scene order 2 (Moria), the second is latest
    state2 = tg.get_entry_state_at(entry.id, scene_order=2)
    assert state2.progression_text == "Falls in Moria"

    # At scene order 3 (Fangorn), the third is latest
    state3 = tg.get_entry_state_at(entry.id, scene_order=3)
    assert state3.progression_text == "Returns as Gandalf the White"


def test_scene_linked_beats_unanchored():
    db = Database()
    proj = _make_project(db)
    entry = db.create_psyke_entry(proj.id, "Hero")

    s1 = db.create_scene(proj.id, "Scene 1")
    _set_scene_order(db, s1.id, 5)

    # Unanchored progression (no scene_id)
    db.create_psyke_progression(entry.id, "Unanchored note")
    # Scene-anchored progression
    db.create_psyke_progression(entry.id, "Anchored at scene 1", scene_id=s1.id)

    tg = TemporalGraph(db, proj.id)
    state = tg.get_entry_state_at(entry.id, scene_order=5)
    # Scene-anchored should win over unanchored
    assert state.progression_text == "Anchored at scene 1"


def test_insertion_order_fallback():
    db = Database()
    proj = _make_project(db)
    entry = db.create_psyke_entry(proj.id, "Villager")

    s1 = db.create_scene(proj.id, "Scene 1")
    _set_scene_order(db, s1.id, 10)

    # Scene-anchored at order 10 — not yet reached at order 5
    db.create_psyke_progression(entry.id, "Future event", scene_id=s1.id)
    # Unanchored progression
    db.create_psyke_progression(entry.id, "Background info")

    tg = TemporalGraph(db, proj.id)
    state = tg.get_entry_state_at(entry.id, scene_order=5)
    # Only unanchored is eligible
    assert state.progression_text == "Background info"


def test_no_eligible_progression_at_early_order():
    db = Database()
    proj = _make_project(db)
    entry = db.create_psyke_entry(proj.id, "LateChar")

    s1 = db.create_scene(proj.id, "Late Scene")
    _set_scene_order(db, s1.id, 100)

    db.create_psyke_progression(entry.id, "Only appears late", scene_id=s1.id)

    tg = TemporalGraph(db, proj.id)
    state = tg.get_entry_state_at(entry.id, scene_order=1)
    # No anchored prog <= 1, no unanchored — should have no progression
    assert state.has_progression is False
    assert state.progression_text == ""


# -- One-hop related entry activity --------------------------------------------

def test_related_entry_active_with_progression():
    db = Database()
    proj = _make_project(db)
    a = db.create_psyke_entry(proj.id, "Alpha")
    b = db.create_psyke_entry(proj.id, "Bravo")
    db.add_psyke_relation(a.id, b.id)

    s1 = db.create_scene(proj.id, "Scene 1")
    _set_scene_order(db, s1.id, 1)
    db.create_psyke_progression(b.id, "Bravo introduced", scene_id=s1.id)

    tg = TemporalGraph(db, proj.id)
    related = tg.get_active_related_entries(a.id, scene_order=1)
    assert len(related) == 1
    assert related[0].name == "Bravo"
    assert related[0].active is True
    assert related[0].state.progression_text == "Bravo introduced"


def test_related_entry_active_no_progression():
    db = Database()
    proj = _make_project(db)
    a = db.create_psyke_entry(proj.id, "Hero")
    b = db.create_psyke_entry(proj.id, "Sidekick")
    db.add_psyke_relation(a.id, b.id)

    tg = TemporalGraph(db, proj.id)
    related = tg.get_active_related_entries(a.id, scene_order=0)
    assert len(related) == 1
    assert related[0].active is True  # No progressions means always active


def test_related_entry_not_yet_active():
    db = Database()
    proj = _make_project(db)
    a = db.create_psyke_entry(proj.id, "Hero")
    b = db.create_psyke_entry(proj.id, "LateAlly")
    db.add_psyke_relation(a.id, b.id)

    s_late = db.create_scene(proj.id, "Late Scene")
    _set_scene_order(db, s_late.id, 50)
    db.create_psyke_progression(b.id, "LateAlly joins", scene_id=s_late.id)

    tg = TemporalGraph(db, proj.id)
    related = tg.get_active_related_entries(a.id, scene_order=5)
    assert len(related) == 1
    assert related[0].active is False  # Has progressions but none eligible yet


def test_related_one_hop_only():
    db = Database()
    proj = _make_project(db)
    a = db.create_psyke_entry(proj.id, "A")
    b = db.create_psyke_entry(proj.id, "B")
    c = db.create_psyke_entry(proj.id, "C")
    db.add_psyke_relation(a.id, b.id)
    db.add_psyke_relation(b.id, c.id)

    tg = TemporalGraph(db, proj.id)
    related = tg.get_active_related_entries(a.id, scene_order=0)
    names = [r.name for r in related]
    assert "B" in names
    assert "C" not in names  # C is two hops away


# -- State resolution at different scene orders --------------------------------

def test_state_evolves_over_scenes():
    db = Database()
    proj = _make_project(db)
    entry = db.create_psyke_entry(proj.id, "Kingdom", entry_type="place",
                                   notes="A peaceful land")

    s1 = db.create_scene(proj.id, "Prosperity")
    s2 = db.create_scene(proj.id, "War")
    s3 = db.create_scene(proj.id, "Rebuild")
    _set_scene_order(db, s1.id, 1)
    _set_scene_order(db, s2.id, 2)
    _set_scene_order(db, s3.id, 3)

    db.create_psyke_progression(entry.id, "Kingdom thriving", scene_id=s1.id)
    db.create_psyke_progression(entry.id, "Kingdom at war", scene_id=s2.id)
    db.create_psyke_progression(entry.id, "Kingdom rebuilding", scene_id=s3.id)

    tg = TemporalGraph(db, proj.id)

    assert tg.get_entry_state_at(entry.id, 0).progression_text == ""
    assert tg.get_entry_state_at(entry.id, 1).progression_text == "Kingdom thriving"
    assert tg.get_entry_state_at(entry.id, 2).progression_text == "Kingdom at war"
    assert tg.get_entry_state_at(entry.id, 3).progression_text == "Kingdom rebuilding"


def test_state_at_exact_boundary():
    db = Database()
    proj = _make_project(db)
    entry = db.create_psyke_entry(proj.id, "Sword")

    s1 = db.create_scene(proj.id, "Found")
    _set_scene_order(db, s1.id, 5)
    db.create_psyke_progression(entry.id, "Sword discovered", scene_id=s1.id)

    tg = TemporalGraph(db, proj.id)

    # Before the scene — not available
    assert tg.get_entry_state_at(entry.id, 4).has_progression is False
    # At the exact scene order — available
    assert tg.get_entry_state_at(entry.id, 5).progression_text == "Sword discovered"
    # After — still available
    assert tg.get_entry_state_at(entry.id, 6).progression_text == "Sword discovered"


# -- Inspection ----------------------------------------------------------------

def test_inspect_output():
    db = Database()
    proj = _make_project(db)
    entry = db.create_psyke_entry(proj.id, "Detective", entry_type="character")
    sidekick = db.create_psyke_entry(proj.id, "Watson")
    db.add_psyke_relation(entry.id, sidekick.id)

    s1 = db.create_scene(proj.id, "Case Begins")
    _set_scene_order(db, s1.id, 1)
    db.create_psyke_progression(entry.id, "Takes the case", scene_id=s1.id)
    db.create_psyke_progression(sidekick.id, "Watson joins", scene_id=s1.id)

    tg = TemporalGraph(db, proj.id)
    inspection = tg.inspect(entry.id, scene_order=1)

    assert inspection is not None
    assert inspection.entry_name == "Detective"
    assert inspection.query_scene_order == 1
    assert inspection.selected_progression_text == "Takes the case"
    assert inspection.selected_scene_order == 1
    assert len(inspection.all_progressions) == 1
    assert inspection.all_progressions[0]["eligible"] is True
    assert len(inspection.related_entries) == 1
    assert inspection.related_entries[0]["name"] == "Watson"
    assert inspection.related_entries[0]["active"] is True


def test_inspect_nonexistent_entry():
    db = Database()
    proj = _make_project(db)
    tg = TemporalGraph(db, proj.id)
    assert tg.inspect(9999, scene_order=0) is None


# -- Details in state ----------------------------------------------------------

def test_details_included_in_state():
    db = Database()
    proj = _make_project(db)
    details = {"appearance": "Tall", "voice": "Deep"}
    entry = db.create_psyke_entry(
        proj.id, "Wizard", entry_type="character", details=details,
    )

    tg = TemporalGraph(db, proj.id)
    state = tg.get_entry_state_at(entry.id, scene_order=0)
    assert state.details == details


# -- Edge cases ----------------------------------------------------------------

def test_nonexistent_entry_returns_none():
    db = Database()
    proj = _make_project(db)
    tg = TemporalGraph(db, proj.id)
    assert tg.get_entry_state_at(9999, scene_order=0) is None


def test_empty_project():
    db = Database()
    proj = _make_project(db)
    tg = TemporalGraph(db, proj.id)
    assert tg.get_active_related_entries(1, scene_order=0) == []


def test_global_entry_state():
    db = Database()
    proj = _make_project(db)
    entry = db.create_psyke_entry(proj.id, "Magic System", is_global=True)
    db.create_psyke_progression(entry.id, "Magic rules established")

    tg = TemporalGraph(db, proj.id)
    state = tg.get_entry_state_at(entry.id, scene_order=0)
    assert state.is_global is True
    assert state.has_progression is True
