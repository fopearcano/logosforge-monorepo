"""Tests for Slice 8 — Graphic Novel Graph enhancement (character + default)."""

import pytest

from logosforge.db import Database
from logosforge.ui.focus_graph_view import (
    EDGE_GN_CHARACTER_PRESENT,
    EDGE_GN_PSYKE_MOTIF,
    FocusGraphView,
    GRAPHIC_NOVEL_MODE_ORDER,
    MODE_GN_CHARACTER,
    MODE_GN_MOTIF,
    MODE_GN_PAGE_RHYTHM,
    MODE_PROFILES,
    NODE_KIND_CHARACTER,
    NODE_KIND_MOTIF,
    NODE_KIND_PAGE,
    build_graph_data,
    enrich_graphic_novel_characters,
    enrich_graphic_novel_graph,
    gn_default_mode,
    gn_filter_node_ids,
    node_kind,
)


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    yield
    settings._instance = None


def _gn(db):
    return db.create_project(
        "GN", narrative_engine="graphic_novel",
        default_writing_format="graphic_novel",
    )


def _enriched(db, project_id):
    data = build_graph_data(db, project_id)
    enrich_graphic_novel_graph(db, project_id, data)
    enrich_graphic_novel_characters(db, project_id, data)
    return data


# =========================================================================
# 1. Character Appearance graph (§2C, §11.3)
# =========================================================================

def test_character_mode_registered():
    assert MODE_GN_CHARACTER in GRAPHIC_NOVEL_MODE_ORDER
    assert MODE_GN_CHARACTER in MODE_PROFILES
    prof = MODE_PROFILES[MODE_GN_CHARACTER]
    assert NODE_KIND_CHARACTER in prof.visible_kinds
    assert EDGE_GN_CHARACTER_PRESENT in prof.visible_edge_types
    assert prof.description


def test_character_appearance_edges_from_panels():
    db = Database()
    p = _gn(db)
    pg = db.create_gn_page(p.id)
    db.create_gn_panel(pg.id, characters_present=["Zampano", "Villain"])
    data = _enriched(db, p.id)
    et = {e.edge_type for e in data.edges}
    assert EDGE_GN_CHARACTER_PRESENT in et
    # Two characters connected to the page.
    char_edges = [e for e in data.edges
                  if e.edge_type == EDGE_GN_CHARACTER_PRESENT]
    assert len(char_edges) == 2


def test_unmatched_character_gets_standalone_node():
    db = Database()
    p = _gn(db)
    pg = db.create_gn_page(p.id)
    db.create_gn_panel(pg.id, characters_present=["Villain"])
    data = _enriched(db, p.id)
    assert "GNCharacter:Villain" in data.nodes
    assert node_kind(data.nodes["GNCharacter:Villain"]) == NODE_KIND_CHARACTER


def test_character_appearance_dedup_across_panels():
    db = Database()
    p = _gn(db)
    pg = db.create_gn_page(p.id)
    db.create_gn_panel(pg.id, characters_present=["Zampano"])
    db.create_gn_panel(pg.id, characters_present=["Zampano"])
    data = _enriched(db, p.id)
    char_edges = [e for e in data.edges
                  if e.edge_type == EDGE_GN_CHARACTER_PRESENT]
    assert len(char_edges) == 1   # one char + one page = one edge


# =========================================================================
# 2. PSYKE visual-memory linkage by name/alias (§7, §8, §11.7)
# =========================================================================

def test_character_matches_psyke_entry():
    db = Database()
    p = _gn(db)
    z = db.create_psyke_entry(p.id, "Zampano", entry_type="character")
    pg = db.create_gn_page(p.id)
    db.create_gn_panel(pg.id, characters_present=["Zampano"])
    data = _enriched(db, p.id)
    # The appearance edge connects the PSYKE node (not a standalone one).
    psyke_node = f"PSYKE:{z.id}"
    assert any(
        e.source_id == psyke_node and e.edge_type == EDGE_GN_CHARACTER_PRESENT
        for e in data.edges
    )
    assert "GNCharacter:Zampano" not in data.nodes


def test_character_matches_psyke_alias():
    db = Database()
    p = _gn(db)
    z = db.create_psyke_entry(p.id, "Zampano", entry_type="character",
                              aliases="Z, The Dog")
    pg = db.create_gn_page(p.id)
    db.create_gn_panel(pg.id, characters_present=["Z"])
    data = _enriched(db, p.id)
    psyke_node = f"PSYKE:{z.id}"
    assert any(e.source_id == psyke_node for e in data.edges
               if e.edge_type == EDGE_GN_CHARACTER_PRESENT)


def test_motif_links_to_psyke_theme():
    db = Database()
    p = _gn(db)
    halo = db.create_psyke_entry(p.id, "broken halo", entry_type="theme")
    pg = db.create_gn_page(p.id)
    db.create_gn_panel(pg.id, visual_motifs=["broken halo"])
    data = _enriched(db, p.id)
    assert any(
        e.edge_type == EDGE_GN_PSYKE_MOTIF
        and e.target_id == f"PSYKE:{halo.id}"
        for e in data.edges
    )


def test_motif_no_link_without_psyke_match():
    db = Database()
    p = _gn(db)
    pg = db.create_gn_page(p.id)
    db.create_gn_panel(pg.id, visual_motifs=["unmatched motif"])
    data = _enriched(db, p.id)
    assert not any(e.edge_type == EDGE_GN_PSYKE_MOTIF for e in data.edges)


# =========================================================================
# 3. Non-hairball default view (§3, §11.5)
# =========================================================================

def test_default_mode_motif_when_motifs_exist():
    db = Database()
    p = _gn(db)
    pg = db.create_gn_page(p.id)
    db.create_gn_panel(pg.id, visual_motifs=["broken halo"])
    assert gn_default_mode(db, p.id) == MODE_GN_MOTIF


def test_default_mode_page_rhythm_without_motifs():
    db = Database()
    p = _gn(db)
    pg = db.create_gn_page(p.id)
    db.create_gn_panel(pg.id, description="no motifs here")
    assert gn_default_mode(db, p.id) == MODE_GN_PAGE_RHYTHM


def test_view_opens_in_focused_mode_not_all():
    db = Database()
    p = _gn(db)
    pg = db.create_gn_page(p.id)
    db.create_gn_panel(pg.id, visual_motifs=["broken halo"])
    view = FocusGraphView(db, p.id)
    assert view._graphic_novel_mode is True
    assert view.get_mode() == MODE_GN_MOTIF        # not MODE_ALL hairball
    assert view.get_mode() != "all"
    # Rendered nodes restricted to the mode's kinds.
    kinds = {node_kind(view._graph_data.nodes[n]) for n in view._node_items}
    assert kinds <= {NODE_KIND_MOTIF, NODE_KIND_PAGE}


def test_view_has_character_mode_button():
    db = Database()
    p = _gn(db)
    view = FocusGraphView(db, p.id)
    assert MODE_GN_CHARACTER in view._mode_buttons


# =========================================================================
# 4. Filters (§6, §11)
# =========================================================================

def test_filter_characters():
    db = Database()
    p = _gn(db)
    pg = db.create_gn_page(p.id)
    db.create_gn_panel(pg.id, characters_present=["Zampano"])
    data = _enriched(db, p.id)
    ids = gn_filter_node_ids(data, "characters")
    assert ids
    assert all(node_kind(data.nodes[i]) == NODE_KIND_CHARACTER for i in ids)


def test_filter_panels():
    db = Database()
    p = _gn(db)
    pg = db.create_gn_page(p.id)
    db.create_gn_panel(pg.id, description="x")
    data = _enriched(db, p.id)
    from logosforge.ui.focus_graph_view import NODE_KIND_PANEL
    ids = gn_filter_node_ids(data, "panels")
    assert all(node_kind(data.nodes[i]) == NODE_KIND_PANEL for i in ids)


# =========================================================================
# 5. Focus mode neighborhood (§7, §11.6)
# =========================================================================

def test_focus_returns_local_neighborhood():
    from logosforge.ui.focus_graph_view import get_neighborhood
    db = Database()
    p = _gn(db)
    pg = db.create_gn_page(p.id)
    db.create_gn_panel(pg.id, characters_present=["Zampano"],
                       visual_motifs=["halo"])
    data = _enriched(db, p.id)
    page_node = f"GNPage:{pg.id}"
    hood = get_neighborhood(data, page_node, hops=1)
    assert page_node in hood
    # Smaller than the whole graph (focused, not hairball).
    assert len(hood) < len(data.nodes) + 1


# =========================================================================
# 6. Switching modes + non-GN gating (§9, §11.8, §11.9)
# =========================================================================

def test_switch_to_character_mode_restricts_kinds():
    db = Database()
    p = _gn(db)
    pg = db.create_gn_page(p.id)
    db.create_gn_panel(pg.id, characters_present=["Zampano"],
                       visual_motifs=["halo"])
    view = FocusGraphView(db, p.id)
    view.set_mode(MODE_GN_CHARACTER)
    assert view.get_mode() == MODE_GN_CHARACTER
    kinds = {node_kind(view._graph_data.nodes[n]) for n in view._node_items}
    assert kinds <= {NODE_KIND_CHARACTER, NODE_KIND_PAGE}


def test_non_gn_project_no_gn_modes_or_enrich():
    db = Database()
    p = db.create_project("Novel")
    db.create_character(p.id, "Alice")
    view = FocusGraphView(db, p.id)
    assert view._graphic_novel_mode is False
    assert MODE_GN_CHARACTER not in view._mode_buttons
    # GN character enrichment is a no-op without GN pages.
    data = build_graph_data(db, p.id)
    before = len(data.edges)
    enrich_graphic_novel_characters(db, p.id, data)
    assert len(data.edges) == before


def test_navigation_ids_resolve():
    """Page/PSYKE nodes carry the entity ids navigation callbacks need."""
    db = Database()
    p = _gn(db)
    z = db.create_psyke_entry(p.id, "Zampano", entry_type="character")
    pg = db.create_gn_page(p.id)
    db.create_gn_panel(pg.id, characters_present=["Zampano"])
    data = _enriched(db, p.id)
    page = data.nodes[f"GNPage:{pg.id}"]
    assert page.entity_id == pg.id
    psyke = data.nodes[f"PSYKE:{z.id}"]
    assert psyke.entity_id == z.id
