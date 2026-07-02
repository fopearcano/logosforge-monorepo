"""Tests for Notes → PSYKE + Assistant context integration."""

from logosforge.context_builder import gather_notes_context
from logosforge.assistant import build_messages
from logosforge.db import Database
from logosforge.export import export_json
from logosforge.import_data import import_json, validate_import_data


def _setup():
    db = Database()
    proj = db.create_project("NotesTest")
    return db, proj


# -- 1. Note model fields ---------------------------------------------------

def test_note_has_tags_and_pinned():
    db, proj = _setup()
    note = db.create_note(proj.id, "Research", "some content", tags="magic, lore", pinned=True)
    fetched = db.get_note_by_id(note.id)
    assert fetched.tags == "magic, lore"
    assert fetched.pinned is True


def test_note_defaults():
    db, proj = _setup()
    note = db.create_note(proj.id, "Plain")
    assert note.tags == ""
    assert note.pinned is False


def test_update_note_tags_pinned():
    db, proj = _setup()
    note = db.create_note(proj.id, "Draft", tags="old")
    db.update_note(note.id, "Draft", tags="new", pinned=True)
    fetched = db.get_note_by_id(note.id)
    assert fetched.tags == "new"
    assert fetched.pinned is True


# -- 2. Note ↔ PSYKE linking -----------------------------------------------

def test_link_note_to_psyke():
    db, proj = _setup()
    note = db.create_note(proj.id, "Hero Notes")
    entry = db.create_psyke_entry(proj.id, "Hero", entry_type="character")
    db.link_note_to_psyke(note.id, entry.id)
    assert entry.id in db.get_note_psyke_links(note.id)
    assert note.id in db.get_psyke_note_links(entry.id)


def test_unlink_note_from_psyke():
    db, proj = _setup()
    note = db.create_note(proj.id, "Hero Notes")
    entry = db.create_psyke_entry(proj.id, "Hero", entry_type="character")
    db.link_note_to_psyke(note.id, entry.id)
    db.unlink_note_from_psyke(note.id, entry.id)
    assert entry.id not in db.get_note_psyke_links(note.id)


def test_duplicate_psyke_link_is_idempotent():
    db, proj = _setup()
    note = db.create_note(proj.id, "N")
    entry = db.create_psyke_entry(proj.id, "E")
    db.link_note_to_psyke(note.id, entry.id)
    db.link_note_to_psyke(note.id, entry.id)
    assert db.get_note_psyke_links(note.id).count(entry.id) == 1


def test_delete_psyke_cascades_note_links():
    db, proj = _setup()
    note = db.create_note(proj.id, "Linked Note")
    entry = db.create_psyke_entry(proj.id, "Villain", entry_type="character")
    db.link_note_to_psyke(note.id, entry.id)
    db.delete_psyke_entry(entry.id)
    assert db.get_note_psyke_links(note.id) == []


# -- 3. Note ↔ Scene linking ------------------------------------------------

def test_link_note_to_scene():
    db, proj = _setup()
    note = db.create_note(proj.id, "Scene Notes")
    scene = db.create_scene(proj.id, "Battle", content="fight")
    db.link_note_to_scene(note.id, scene.id)
    assert scene.id in db.get_note_scene_links(note.id)
    assert note.id in db.get_scene_note_links(scene.id)


def test_unlink_note_from_scene():
    db, proj = _setup()
    note = db.create_note(proj.id, "Scene Notes")
    scene = db.create_scene(proj.id, "Battle", content="fight")
    db.link_note_to_scene(note.id, scene.id)
    db.unlink_note_from_scene(note.id, scene.id)
    assert scene.id not in db.get_note_scene_links(note.id)


def test_delete_scene_cascades_note_links():
    db, proj = _setup()
    note = db.create_note(proj.id, "Scene Note")
    scene = db.create_scene(proj.id, "Deleted Scene", content="x")
    db.link_note_to_scene(note.id, scene.id)
    db.delete_scene(scene.id)
    assert db.get_note_scene_links(note.id) == []


def test_delete_note_cascades_all_links():
    db, proj = _setup()
    note = db.create_note(proj.id, "Soon Gone")
    entry = db.create_psyke_entry(proj.id, "E")
    scene = db.create_scene(proj.id, "S", content="x")
    db.link_note_to_psyke(note.id, entry.id)
    db.link_note_to_scene(note.id, scene.id)
    db.delete_note(note.id)
    assert db.get_psyke_note_links(entry.id) == []
    assert db.get_scene_note_links(scene.id) == []


# -- 4. gather_notes_context — pinned notes always included -----------------

def test_pinned_note_in_context():
    db, proj = _setup()
    db.create_note(proj.id, "World Rules", "Magic costs blood", pinned=True)
    ctx = gather_notes_context(db, proj.id)
    assert "[Relevant Notes]" in ctx
    assert "World Rules" in ctx
    assert "pinned" in ctx


def test_unpinned_unlinked_note_excluded():
    db, proj = _setup()
    db.create_note(proj.id, "Random Thought", "Something unrelated")
    ctx = gather_notes_context(db, proj.id)
    assert ctx == ""


# -- 5. Scene-linked note appears in context --------------------------------

def test_scene_linked_note_in_context():
    db, proj = _setup()
    scene = db.create_scene(proj.id, "Battle", content="The hero fought bravely")
    note = db.create_note(proj.id, "Battle Strategy", "Flanking maneuver from the east")
    db.link_note_to_scene(note.id, scene.id)
    ctx = gather_notes_context(db, proj.id, scene_id=scene.id)
    assert "Battle Strategy" in ctx
    assert "linked to current scene" in ctx


# -- 6. PSYKE-linked note appears when entry is relevant --------------------

def test_psyke_linked_note_in_context():
    db, proj = _setup()
    entry = db.create_psyke_entry(proj.id, "Gandalf", entry_type="character")
    scene = db.create_scene(proj.id, "Council", content="Gandalf spoke wisely")
    note = db.create_note(proj.id, "Gandalf's Backstory", "He is a Maia spirit")
    db.link_note_to_psyke(note.id, entry.id)
    ctx = gather_notes_context(db, proj.id, scene_id=scene.id)
    assert "Gandalf's Backstory" in ctx
    assert "relevant PSYKE entry" in ctx


def test_psyke_linked_note_excluded_when_entry_not_relevant():
    db, proj = _setup()
    entry = db.create_psyke_entry(proj.id, "Sauron", entry_type="character")
    scene = db.create_scene(proj.id, "Shire Party", content="Hobbits danced")
    note = db.create_note(proj.id, "Sauron's Plan", "Conquer Middle Earth")
    db.link_note_to_psyke(note.id, entry.id)
    ctx = gather_notes_context(db, proj.id, scene_id=scene.id)
    assert "Sauron's Plan" not in ctx


# -- 7. Tag match -----------------------------------------------------------

def test_tag_match_note_in_context():
    db, proj = _setup()
    scene = db.create_scene(proj.id, "Forest Scene", content="The dark forest loomed", tags="nature")
    db.create_note(proj.id, "Forest Lore", "Ancient trees with memories", tags="nature, magic")
    ctx = gather_notes_context(db, proj.id, scene_id=scene.id)
    assert "Forest Lore" in ctx


# -- 8. Content mention match -----------------------------------------------

def test_content_mention_match():
    db, proj = _setup()
    entry = db.create_psyke_entry(proj.id, "Elrond", entry_type="character")
    scene = db.create_scene(proj.id, "Council", content="Elrond presided over the council")
    db.create_note(proj.id, "Elrond's History", "Founded Rivendell in the Second Age")
    ctx = gather_notes_context(db, proj.id, scene_id=scene.id)
    assert "Elrond's History" in ctx
    assert "mentions relevant entity" in ctx


# -- 9. Notes in build_messages ----------------------------------------------

def test_notes_context_in_build_messages():
    messages = build_messages(
        "Write a scene",
        "[Scene Context]\nSome scene",
        notes_context="[Relevant Notes]\n- \"Magic Rules\": Blood magic costs life (pinned)",
    )
    content = messages[1]["content"]
    assert "[Relevant Notes]" in content
    assert "Magic Rules" in content


# -- 10. No irrelevant note flood -------------------------------------------

def test_no_flood_many_unrelated_notes():
    db, proj = _setup()
    for i in range(30):
        db.create_note(proj.id, f"Random {i}", f"Unrelated content {i}")
    scene = db.create_scene(proj.id, "Focus Scene", content="Specific topic")
    ctx = gather_notes_context(db, proj.id, scene_id=scene.id)
    assert ctx == ""


# -- 11. Edit note → context refreshes --------------------------------------

def test_edit_note_context_refreshes():
    db, proj = _setup()
    note = db.create_note(proj.id, "Rules", "Old rules", pinned=True)
    ctx1 = gather_notes_context(db, proj.id)
    assert "Old rules" in ctx1

    db.update_note(note.id, "Rules", "New rules", pinned=True)
    ctx2 = gather_notes_context(db, proj.id)
    assert "New rules" in ctx2
    assert "Old rules" not in ctx2


# -- 12. Export/import preserves note metadata --------------------------------

def test_export_import_preserves_note_metadata():
    db, proj = _setup()
    note = db.create_note(proj.id, "Lore", "Ancient history", tags="history, lore", pinned=True)
    entry = db.create_psyke_entry(proj.id, "Wizard", entry_type="character")
    scene = db.create_scene(proj.id, "Magic Scene", content="The wizard cast a spell")
    db.link_note_to_psyke(note.id, entry.id)
    db.link_note_to_scene(note.id, scene.id)

    json_str = export_json(db, proj.id)
    data, err = validate_import_data(json_str)
    assert data is not None, err

    db2 = Database()
    new_id = import_json(db2, data)

    notes = db2.get_all_notes(new_id)
    lore_note = [n for n in notes if n.title == "Lore"][0]
    assert lore_note.tags == "history, lore"
    assert lore_note.pinned is True

    psyke_links = db2.get_note_psyke_links(lore_note.id)
    assert len(psyke_links) == 1
    linked_entry = db2.get_psyke_entry_by_id(psyke_links[0])
    assert linked_entry.name == "Wizard"

    scene_links = db2.get_note_scene_links(lore_note.id)
    assert len(scene_links) == 1
    linked_scene = db2.get_scene_by_id(scene_links[0])
    assert linked_scene.title == "Magic Scene"


# -- 13. NotesView refresh method exists ------------------------------------

def test_notes_view_has_refresh():
    from logosforge.ui.notes_view import NotesView
    db, proj = _setup()
    view = NotesView(db, proj.id)
    assert hasattr(view, "refresh")
    view.refresh()


# -- 14. Multiple pinned notes all included ---------------------------------

def test_multiple_pinned_notes():
    db, proj = _setup()
    db.create_note(proj.id, "Rule 1", "First rule", pinned=True)
    db.create_note(proj.id, "Rule 2", "Second rule", pinned=True)
    db.create_note(proj.id, "Rule 3", "Third rule", pinned=True)
    ctx = gather_notes_context(db, proj.id)
    assert "Rule 1" in ctx
    assert "Rule 2" in ctx
    assert "Rule 3" in ctx


# -- 15. Long note content is truncated ------------------------------------

def test_note_excerpt_truncation():
    db, proj = _setup()
    long_content = "word " * 100
    db.create_note(proj.id, "Long Note", long_content, pinned=True)
    ctx = gather_notes_context(db, proj.id)
    assert "..." in ctx
    assert len(ctx) < len(long_content)
