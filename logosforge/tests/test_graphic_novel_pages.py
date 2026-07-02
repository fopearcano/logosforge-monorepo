"""Tests for Graphic Novel Page/Panel data structures and continuity."""

import pytest

from logosforge.db import Database
from logosforge.models import (
    GraphicNovelPage,
    GraphicNovelPanel,
    GraphicNovelSequence,
)


def _gn_project(db):
    return db.create_project(
        "GN", narrative_engine="graphic_novel",
        default_writing_format="graphic_novel",
    )


# =========================================================================
# 1. Models exist and are typed
# =========================================================================

def test_models_importable():
    assert GraphicNovelSequence.__tablename__ == "graphicnovelsequence"
    assert GraphicNovelPage.__tablename__ == "graphicnovelpage"
    assert GraphicNovelPanel.__tablename__ == "graphicnovelpanel"


def test_page_has_required_fields():
    fields = GraphicNovelPage.model_fields
    for f in (
        "sequence_id", "page_number", "summary", "emotional_beat",
        "density_level", "reveal_type", "splash_page", "notes",
    ):
        assert f in fields


def test_panel_has_required_fields():
    fields = GraphicNovelPanel.model_fields
    for f in (
        "page_id", "panel_number", "description", "camera_angle",
        "shot_type", "emotional_tone", "action", "characters_present",
        "dialogue_refs", "visual_motifs", "reading_priority",
        "transition_type",
    ):
        assert f in fields


# =========================================================================
# 2. Pages persist
# =========================================================================

def test_create_page_persists():
    db = Database()
    p = _gn_project(db)
    page = db.create_gn_page(
        p.id, summary="rooftop", emotional_beat="dread",
        density_level="dense", reveal_type="cliffhanger", splash_page=True,
    )
    loaded = db.get_gn_page_by_id(page.id)
    assert loaded is not None
    assert loaded.summary == "rooftop"
    assert loaded.density_level == "dense"
    assert loaded.reveal_type == "cliffhanger"
    assert loaded.splash_page is True


def test_pages_auto_number_and_order():
    db = Database()
    p = _gn_project(db)
    for _ in range(3):
        db.create_gn_page(p.id)
    pages = db.get_gn_pages(p.id)
    assert [pg.page_number for pg in pages] == [1, 2, 3]


def test_explicit_page_numbers_order():
    db = Database()
    p = _gn_project(db)
    db.create_gn_page(p.id, page_number=3, summary="c")
    db.create_gn_page(p.id, page_number=1, summary="a")
    db.create_gn_page(p.id, page_number=2, summary="b")
    summaries = [pg.summary for pg in db.get_gn_pages(p.id)]
    assert summaries == ["a", "b", "c"]


def test_update_page():
    db = Database()
    p = _gn_project(db)
    page = db.create_gn_page(p.id, density_level="light")
    db.update_gn_page(page.id, density_level="explosive", summary="boom")
    loaded = db.get_gn_page_by_id(page.id)
    assert loaded.density_level == "explosive"
    assert loaded.summary == "boom"


# =========================================================================
# 3. Panels persist + ordering
# =========================================================================

def test_create_panel_persists():
    db = Database()
    p = _gn_project(db)
    page = db.create_gn_page(p.id)
    panel = db.create_gn_panel(
        page.id, description="wide establishing", shot_type="WS",
        camera_angle="high", emotional_tone="ominous",
        action="rain falls", reading_priority=1,
        transition_type="scene_to_scene",
        characters_present=["Alice", "Bob"], visual_motifs=["rain"],
        dialogue_refs=["d1"],
    )
    loaded = db.get_gn_panel_by_id(panel.id)
    assert loaded.description == "wide establishing"
    assert loaded.shot_type == "WS"
    assert loaded.reading_priority == 1
    assert loaded.transition_type == "scene_to_scene"
    assert db.csv_split(loaded.characters_present) == ["Alice", "Bob"]
    assert db.csv_split(loaded.visual_motifs) == ["rain"]
    assert db.csv_split(loaded.dialogue_refs) == ["d1"]


def test_panels_auto_number_and_order():
    db = Database()
    p = _gn_project(db)
    page = db.create_gn_page(p.id)
    for _ in range(4):
        db.create_gn_panel(page.id)
    panels = db.get_gn_panels_for_page(page.id)
    assert [pn.panel_number for pn in panels] == [1, 2, 3, 4]


def test_reorder_panels():
    db = Database()
    p = _gn_project(db)
    page = db.create_gn_page(p.id)
    a = db.create_gn_panel(page.id, description="A")
    b = db.create_gn_panel(page.id, description="B")
    c = db.create_gn_panel(page.id, description="C")
    db.reorder_gn_panels(page.id, [c.id, a.id, b.id])
    order = [pn.description for pn in db.get_gn_panels_for_page(page.id)]
    assert order == ["C", "A", "B"]


def test_delete_panel_safe():
    db = Database()
    p = _gn_project(db)
    page = db.create_gn_page(p.id)
    a = db.create_gn_panel(page.id, description="A")
    db.create_gn_panel(page.id, description="B")
    db.delete_gn_panel(a.id)
    remaining = [pn.description for pn in db.get_gn_panels_for_page(page.id)]
    assert remaining == ["B"]
    assert db.get_gn_panel_by_id(a.id) is None


def test_update_panel_list_field():
    db = Database()
    p = _gn_project(db)
    page = db.create_gn_page(p.id)
    panel = db.create_gn_panel(page.id)
    db.update_gn_panel(panel.id, characters_present=["X", "Y"], shot_type="CU")
    loaded = db.get_gn_panel_by_id(panel.id)
    assert db.csv_split(loaded.characters_present) == ["X", "Y"]
    assert loaded.shot_type == "CU"


# =========================================================================
# 4. Relationships: Sequence -> Pages -> Panels (§3)
# =========================================================================

def test_sequence_pages_panels_hierarchy():
    db = Database()
    p = _gn_project(db)
    seq = db.create_gn_sequence(p.id, title="Chase")
    pg1 = db.create_gn_page(p.id, sequence_id=seq.id, summary="rooftop")
    pg2 = db.create_gn_page(p.id, sequence_id=seq.id, summary="alley")
    other = db.create_gn_page(p.id, summary="unassigned")
    db.create_gn_panel(pg1.id, description="p1")
    db.create_gn_panel(pg1.id, description="p2")

    seq_pages = db.get_gn_pages_for_sequence(seq.id)
    assert {pg.summary for pg in seq_pages} == {"rooftop", "alley"}
    assert other.id not in {pg.id for pg in seq_pages}
    assert len(db.get_gn_panels_for_page(pg1.id)) == 2
    assert len(db.get_gn_panels_for_page(pg2.id)) == 0


def test_assign_page_to_sequence():
    db = Database()
    p = _gn_project(db)
    seq = db.create_gn_sequence(p.id, title="S")
    page = db.create_gn_page(p.id)
    assert page.sequence_id is None
    db.assign_gn_page_to_sequence(page.id, seq.id)
    assert db.get_gn_page_by_id(page.id).sequence_id == seq.id


def test_delete_page_cascades_panels():
    db = Database()
    p = _gn_project(db)
    page = db.create_gn_page(p.id)
    pan = db.create_gn_panel(page.id)
    db.delete_gn_page(page.id)
    assert db.get_gn_page_by_id(page.id) is None
    assert db.get_gn_panel_by_id(pan.id) is None


# =========================================================================
# 5. Continuity (§4): props / costumes / wounds / object persistence
# =========================================================================

def test_continuity_item_and_appearances():
    db = Database()
    p = _gn_project(db)
    page1 = db.create_gn_page(p.id)
    page2 = db.create_gn_page(p.id)
    panel = db.create_gn_panel(page1.id)
    item = db.create_gn_continuity_item(
        p.id, "Detective's coat", item_type="costume",
        description="torn at the sleeve",
    )
    db.add_gn_continuity_appearance(
        item.id, page_id=page1.id, panel_id=panel.id,
        state_description="intact", continuity_status="consistent",
    )
    db.add_gn_continuity_appearance(
        item.id, page_id=page2.id,
        state_description="torn sleeve", continuity_status="changed",
    )
    items = db.get_gn_continuity_items(p.id)
    assert len(items) == 1 and items[0].item_type == "costume"
    apps = db.get_gn_continuity_appearances(item.id)
    assert [a.continuity_status for a in apps] == ["consistent", "changed"]


def test_continuity_links_to_psyke():
    db = Database()
    p = _gn_project(db)
    e = db.create_psyke_entry(p.id, "Locket", entry_type="object")
    item = db.create_gn_continuity_item(
        p.id, "Locket", item_type="prop", linked_psyke_entry_id=e.id,
    )
    assert db.get_gn_continuity_items(p.id)[0].linked_psyke_entry_id == e.id


# =========================================================================
# 6. Reload (separate Database over a file) — §5
# =========================================================================

def test_reload_from_disk(tmp_path):
    path = str(tmp_path / "gn.db")
    db = Database(path)
    p = _gn_project(db)
    seq = db.create_gn_sequence(p.id, title="Opening")
    page = db.create_gn_page(p.id, sequence_id=seq.id, summary="splash",
                             splash_page=True)
    db.create_gn_panel(page.id, description="hero lands",
                       characters_present=["Hero"])
    pid = p.id
    page_id = page.id

    # Reopen the same file with a fresh Database instance.
    db2 = Database(path)
    pages = db2.get_gn_pages(pid)
    assert len(pages) == 1
    assert pages[0].summary == "splash"
    assert pages[0].splash_page is True
    panels = db2.get_gn_panels_for_page(page_id)
    assert len(panels) == 1
    assert db2.csv_split(panels[0].characters_present) == ["Hero"]
    assert len(db2.get_gn_sequences(pid)) == 1


def test_old_project_without_gn_data_is_safe(tmp_path):
    """A project that never used GN tables loads with empty GN collections."""
    path = str(tmp_path / "novel.db")
    db = Database(path)
    p = db.create_project("Novel")  # default novel engine
    db.create_scene(p.id, "Chapter 1", content="prose")
    db2 = Database(path)
    assert db2.get_gn_pages(p.id) == []
    assert db2.get_gn_sequences(p.id) == []
    assert db2.get_gn_continuity_items(p.id) == []


# =========================================================================
# 7. Project isolation
# =========================================================================

def test_pages_scoped_to_project():
    db = Database()
    a = _gn_project(db)
    b = _gn_project(db)
    db.create_gn_page(a.id, summary="A-page")
    db.create_gn_page(b.id, summary="B-page")
    assert [pg.summary for pg in db.get_gn_pages(a.id)] == ["A-page"]
    assert [pg.summary for pg in db.get_gn_pages(b.id)] == ["B-page"]
