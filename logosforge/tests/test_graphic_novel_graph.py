"""Tests for Graphic Novel graph modes."""

import pytest

from logosforge.db import Database
from logosforge.graph_gravity import compute_gravity
from logosforge.ui.focus_graph_view import (
    EDGE_GN_MOTIF,
    EDGE_GN_OBJECT_CONTINUITY,
    EDGE_GN_PAGE_FLOW,
    EDGE_GN_PANEL_CAUSALITY,
    EDGE_GN_SYMBOL_ECHO,
    FocusGraphView,
    GRAPHIC_NOVEL_MODE_ORDER,
    MODE_ALL,
    MODE_GN_MOTIF,
    MODE_GN_OBJECT_CONTINUITY,
    MODE_GN_PAGE_RHYTHM,
    MODE_GN_PANEL_CAUSALITY,
    MODE_GN_SYMBOL_RECURRENCE,
    MODE_PROFILES,
    NODE_KIND_GN_OBJECT,
    NODE_KIND_MOTIF,
    NODE_KIND_PAGE,
    NODE_KIND_PANEL,
    build_graph_data,
    enrich_graphic_novel_graph,
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


def _story(db, project_id):
    seq = db.create_gn_sequence(project_id, title="Chase")
    pg1 = db.create_gn_page(project_id, sequence_id=seq.id)
    pg2 = db.create_gn_page(project_id, sequence_id=seq.id)
    db.create_gn_panel(pg1.id, visual_motifs=["rain"])
    db.create_gn_panel(pg1.id, visual_motifs=["rain", "locket"])
    db.create_gn_panel(pg2.id, visual_motifs=["rain"])
    item = db.create_gn_continuity_item(project_id, "Gun", item_type="object")
    db.add_gn_continuity_appearance(item.id, page_id=pg1.id)
    db.add_gn_continuity_appearance(item.id, page_id=pg2.id)
    return seq, pg1, pg2


def _enriched(db, project_id):
    data = build_graph_data(db, project_id)
    enrich_graphic_novel_graph(db, project_id, data)
    return data


# =========================================================================
# 1. Graph modes exist (§1)
# =========================================================================

def test_gn_modes_registered():
    for mode in GRAPHIC_NOVEL_MODE_ORDER:
        assert mode in MODE_PROFILES


def test_motif_mode_profile():
    p = MODE_PROFILES[MODE_GN_MOTIF]
    assert NODE_KIND_MOTIF in p.visible_kinds
    assert EDGE_GN_MOTIF in p.visible_edge_types


def test_panel_causality_mode_profile():
    p = MODE_PROFILES[MODE_GN_PANEL_CAUSALITY]
    assert NODE_KIND_PANEL in p.visible_kinds
    assert EDGE_GN_PANEL_CAUSALITY in p.visible_edge_types
    assert p.layout == "linear_timeline"


def test_symbol_recurrence_mode_profile():
    p = MODE_PROFILES[MODE_GN_SYMBOL_RECURRENCE]
    assert EDGE_GN_SYMBOL_ECHO in p.visible_edge_types


def test_page_rhythm_mode_profile():
    p = MODE_PROFILES[MODE_GN_PAGE_RHYTHM]
    assert p.visible_kinds == frozenset({NODE_KIND_PAGE})
    assert EDGE_GN_PAGE_FLOW in p.visible_edge_types


def test_object_continuity_mode_profile():
    p = MODE_PROFILES[MODE_GN_OBJECT_CONTINUITY]
    assert NODE_KIND_GN_OBJECT in p.visible_kinds
    assert EDGE_GN_OBJECT_CONTINUITY in p.visible_edge_types


def test_all_gn_modes_have_descriptions():
    for mode in GRAPHIC_NOVEL_MODE_ORDER:
        assert MODE_PROFILES[mode].description


# =========================================================================
# 2. Graph enrichment builds GN nodes/edges
# =========================================================================

def test_enrich_creates_node_kinds():
    db = Database()
    p = _gn(db)
    _story(db, p.id)
    data = _enriched(db, p.id)
    kinds = {node_kind(n) for n in data.nodes.values()}
    assert {NODE_KIND_PAGE, NODE_KIND_PANEL, NODE_KIND_MOTIF,
            NODE_KIND_GN_OBJECT} <= kinds


def test_enrich_creates_edge_types():
    db = Database()
    p = _gn(db)
    _story(db, p.id)
    data = _enriched(db, p.id)
    etypes = {e.edge_type for e in data.edges}
    assert EDGE_GN_PAGE_FLOW in etypes
    assert EDGE_GN_PANEL_CAUSALITY in etypes
    assert EDGE_GN_MOTIF in etypes
    assert EDGE_GN_SYMBOL_ECHO in etypes      # rain on both pages
    assert EDGE_GN_OBJECT_CONTINUITY in etypes


def test_no_symbol_echo_for_single_page_motif():
    db = Database()
    p = _gn(db)
    pg = db.create_gn_page(p.id)
    db.create_gn_panel(pg.id, visual_motifs=["only_once"])
    data = _enriched(db, p.id)
    echoes = [e for e in data.edges if e.edge_type == EDGE_GN_SYMBOL_ECHO]
    assert echoes == []


def test_enrich_noop_without_pages():
    db = Database()
    p = _gn(db)
    data = build_graph_data(db, p.id)
    before = len(data.nodes)
    enrich_graphic_novel_graph(db, p.id, data)
    assert len(data.nodes) == before


# =========================================================================
# 3. Filters (§2)
# =========================================================================

def test_filter_motifs_only():
    db = Database()
    p = _gn(db)
    _story(db, p.id)
    data = _enriched(db, p.id)
    ids = gn_filter_node_ids(data, "motifs")
    assert ids
    assert all(node_kind(data.nodes[i]) == NODE_KIND_MOTIF for i in ids)


def test_filter_pages_only():
    db = Database()
    p = _gn(db)
    _story(db, p.id)
    data = _enriched(db, p.id)
    ids = gn_filter_node_ids(data, "pages")
    assert all(node_kind(data.nodes[i]) == NODE_KIND_PAGE for i in ids)
    assert len(ids) == 2


def test_filter_panel_continuity():
    db = Database()
    p = _gn(db)
    _story(db, p.id)
    data = _enriched(db, p.id)
    ids = gn_filter_node_ids(data, "panel_continuity")
    kinds = {node_kind(data.nodes[i]) for i in ids}
    assert kinds <= {NODE_KIND_PAGE, NODE_KIND_PANEL}


def test_filter_symbolic_echoes():
    db = Database()
    p = _gn(db)
    _story(db, p.id)
    data = _enriched(db, p.id)
    ids = gn_filter_node_ids(data, "symbolic_echoes")
    kinds = {node_kind(data.nodes[i]) for i in ids}
    assert kinds <= {NODE_KIND_MOTIF, NODE_KIND_PAGE}


# =========================================================================
# 4. Story gravity (§3): important motifs/pages weigh more
# =========================================================================

def test_recurring_motif_has_gravity():
    db = Database()
    p = _gn(db)
    _story(db, p.id)
    data = _enriched(db, p.id)
    g = compute_gravity(db, p.id, data, graphic_novel_mode=True)
    rain = g.get("GNMotif:rain")
    locket = g.get("GNMotif:locket")
    assert rain is not None and locket is not None
    # 'rain' recurs across more pages → heavier than the once-seen 'locket'.
    assert rain.total > locket.total


def test_denser_page_has_more_gravity():
    db = Database()
    p = _gn(db)
    seq, pg1, pg2 = _story(db, p.id)
    data = _enriched(db, p.id)
    g = compute_gravity(db, p.id, data, graphic_novel_mode=True)
    # pg1 has 2 panels, pg2 has 1 → pg1 weighs more.
    assert g[f"GNPage:{pg1.id}"].total > g[f"GNPage:{pg2.id}"].total


# =========================================================================
# 5. View mode switching + readability (§4, §5)
# =========================================================================

def test_view_detects_graphic_novel():
    db = Database()
    p = _gn(db)
    view = FocusGraphView(db, p.id)
    assert view._graphic_novel_mode is True
    for mode in GRAPHIC_NOVEL_MODE_ORDER:
        assert mode in view._mode_buttons


def test_novel_view_no_gn_buttons():
    db = Database()
    p = db.create_project("Novel")
    view = FocusGraphView(db, p.id)
    assert view._graphic_novel_mode is False
    for mode in GRAPHIC_NOVEL_MODE_ORDER:
        assert mode not in view._mode_buttons


def test_switch_modes():
    db = Database()
    p = _gn(db)
    _story(db, p.id)
    view = FocusGraphView(db, p.id)
    for mode in GRAPHIC_NOVEL_MODE_ORDER:
        view.set_mode(mode)
        assert view.get_mode() == mode
    view.set_mode(MODE_ALL)
    assert view.get_mode() == MODE_ALL


def test_page_rhythm_mode_shows_pages_only():
    db = Database()
    p = _gn(db)
    _story(db, p.id)
    view = FocusGraphView(db, p.id)
    view.set_mode(MODE_GN_PAGE_RHYTHM)
    assert view._active_layers == {NODE_KIND_PAGE}
    # Readability: only the 2 pages are visible (no spaghetti).
    assert view.get_visible_count() == 2


def test_motif_mode_no_spaghetti():
    """Motif mode shows only motifs + pages, not the whole graph."""
    db = Database()
    p = _gn(db)
    _story(db, p.id)
    view = FocusGraphView(db, p.id)
    view.set_mode(MODE_GN_MOTIF)
    # 2 pages + 2 motifs = 4 nodes; panels/objects excluded.
    assert view.get_visible_count() == 4


def test_object_continuity_mode_visible():
    db = Database()
    p = _gn(db)
    _story(db, p.id)
    view = FocusGraphView(db, p.id)
    view.set_mode(MODE_GN_OBJECT_CONTINUITY)
    # 2 pages + 1 object = 3.
    assert view.get_visible_count() == 3
