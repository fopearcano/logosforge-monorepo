"""Tests for Series graph modes."""

import pytest

from logosforge.db import Database
from logosforge.ui.focus_graph_view import (
    EDGE_SR_CONTAINS,
    EDGE_SR_CONTINUES,
    EDGE_SR_CONTRADICTS,
    EDGE_SR_ECHOES,
    EDGE_SR_ESCALATES,
    EDGE_SR_PAYS_OFF,
    EDGE_SR_RESOLVES,
    EDGE_SR_SETS_UP,
    FocusGraphView,
    MODE_ALL,
    MODE_PROFILES,
    MODE_SR_ABC_PLOT,
    MODE_SR_CHARACTER,
    MODE_SR_CONTINUITY,
    MODE_SR_EPISODE_DEP,
    MODE_SR_MYSTERY,
    MODE_SR_RELATIONSHIP,
    MODE_SR_SEASON_ARC,
    NODE_KIND_ARC,
    NODE_KIND_CHARACTER,
    NODE_KIND_EPISODE,
    NODE_KIND_MYSTERY,
    NODE_KIND_PLOTLINE,
    NODE_KIND_SEASON,
    SERIES_MODE_ORDER,
    build_graph_data,
    enrich_series_graph,
    node_kind,
    series_default_node_ids,
    series_filter_node_ids,
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
    """Two seasons, three episodes, plotlines, spanning + resolved arcs,
    and a flagged character with per-episode status."""
    from logosforge.psyke_series import set_series_memory
    s1 = db.create_season(project_id, title="Season 1", season_arc="rise")
    s2 = db.create_season(project_id, title="Season 2")
    e1 = db.create_episode(s1.id, title="Pilot")
    e2 = db.create_episode(s1.id, title="Fallout")
    e3 = db.create_episode(s2.id, title="Return")
    db.create_episode_plotline(e1.id, type="A", title="the case")
    db.create_episode_plotline(e1.id, type="B", title="romance")
    # Mystery spans E1→E3 (so E2 escalates); season arc set up, still open.
    db.create_series_arc(project_id, scope="mystery", title="Who killed Laura",
                         setup_episode_id=e1.id, payoff_episode_id=e3.id,
                         status="active")
    db.create_series_arc(project_id, scope="season", title="Redemption",
                         setup_episode_id=e1.id, status="active")
    # A resolved arc, paid off at E2.
    db.create_series_arc(project_id, scope="character", title="Debt",
                         setup_episode_id=e1.id, payoff_episode_id=e2.id,
                         status="resolved")
    cooper = db.create_psyke_entry(project_id, "Cooper", entry_type="character")
    set_series_memory(db, cooper.id, continuity_flags="lost an eye",
                      current_status_by_episode={str(e1.id): "arrives",
                                                 str(e3.id): "returns"})
    return s1, s2, e1, e2, e3, cooper


def _enriched(db, project_id):
    data = build_graph_data(db, project_id)
    enrich_series_graph(db, project_id, data)
    return data


# =========================================================================
# 1. Graph modes (§1)
# =========================================================================

def test_series_modes_registered():
    assert len(SERIES_MODE_ORDER) == 7
    for mode in SERIES_MODE_ORDER:
        assert mode in MODE_PROFILES


def test_season_arc_mode_profile():
    p = MODE_PROFILES[MODE_SR_SEASON_ARC]
    assert {NODE_KIND_SEASON, NODE_KIND_EPISODE} <= p.visible_kinds
    assert EDGE_SR_CONTAINS in p.visible_edge_types
    assert p.layout == "linear_timeline"


def test_episode_dependency_mode_profile():
    p = MODE_PROFILES[MODE_SR_EPISODE_DEP]
    assert p.visible_kinds == frozenset({NODE_KIND_EPISODE})
    assert EDGE_SR_CONTINUES in p.visible_edge_types


def test_abc_plot_mode_profile():
    p = MODE_PROFILES[MODE_SR_ABC_PLOT]
    assert NODE_KIND_PLOTLINE in p.visible_kinds


def test_mystery_mode_profile():
    p = MODE_PROFILES[MODE_SR_MYSTERY]
    assert NODE_KIND_MYSTERY in p.visible_kinds
    assert {EDGE_SR_SETS_UP, EDGE_SR_PAYS_OFF} <= p.visible_edge_types


def test_character_progression_mode_profile():
    p = MODE_PROFILES[MODE_SR_CHARACTER]
    assert NODE_KIND_CHARACTER in p.visible_kinds
    assert EDGE_SR_ECHOES in p.visible_edge_types


def test_continuity_mode_profile():
    p = MODE_PROFILES[MODE_SR_CONTINUITY]
    assert EDGE_SR_CONTRADICTS in p.visible_edge_types


def test_all_series_modes_have_descriptions():
    for mode in SERIES_MODE_ORDER:
        assert MODE_PROFILES[mode].description


# =========================================================================
# 2. Graph data mapping (§3)
# =========================================================================

def test_enrich_creates_series_nodes():
    db = Database()
    p = _show(db)
    _build(db, p.id)
    data = _enriched(db, p.id)
    kinds = {node_kind(n) for n in data.nodes.values()}
    assert {NODE_KIND_SEASON, NODE_KIND_EPISODE, NODE_KIND_MYSTERY,
            NODE_KIND_ARC, NODE_KIND_PLOTLINE} <= kinds


def test_enrich_creates_setup_and_payoff_edges():
    db = Database()
    p = _show(db)
    _build(db, p.id)
    data = _enriched(db, p.id)
    et = {e.edge_type for e in data.edges}
    assert EDGE_SR_SETS_UP in et
    assert EDGE_SR_PAYS_OFF in et       # active mystery payoff
    assert EDGE_SR_RESOLVES in et       # resolved "Debt" arc
    assert EDGE_SR_CONTAINS in et       # season→episode, episode→plotline
    assert EDGE_SR_CONTINUES in et      # episode dependency
    assert EDGE_SR_ESCALATES in et      # E2 lies between setup E1 and payoff E3


def test_enrich_creates_echo_and_contradiction_edges():
    db = Database()
    p = _show(db)
    _build(db, p.id)
    data = _enriched(db, p.id)
    et = {e.edge_type for e in data.edges}
    assert EDGE_SR_ECHOES in et         # character progression across episodes
    assert EDGE_SR_CONTRADICTS in et    # flagged continuity character


def test_continues_follows_reading_order_across_seasons():
    db = Database()
    p = _show(db)
    _s1, _s2, e1, e2, e3 = _build(db, p.id)[:5]
    data = _enriched(db, p.id)
    cont = {
        (e.source_id, e.target_id)
        for e in data.edges if e.edge_type == EDGE_SR_CONTINUES
    }
    assert (f"Episode:{e1.id}", f"Episode:{e2.id}") in cont
    assert (f"Episode:{e2.id}", f"Episode:{e3.id}") in cont


def test_enrich_noop_without_episodes():
    db = Database()
    p = _show(db)
    data = build_graph_data(db, p.id)
    before = len(data.nodes)
    enrich_series_graph(db, p.id, data)
    assert len(data.nodes) == before


# =========================================================================
# 3. Filters (§2)
# =========================================================================

def test_filter_by_season():
    db = Database()
    p = _show(db)
    _build(db, p.id)
    data = _enriched(db, p.id)
    ids = series_filter_node_ids(data, "season")
    kinds = {node_kind(data.nodes[i]) for i in ids}
    assert kinds <= {NODE_KIND_SEASON, NODE_KIND_EPISODE}
    assert any(node_kind(data.nodes[i]) == NODE_KIND_SEASON for i in ids)


def test_filter_by_episode():
    db = Database()
    p = _show(db)
    _build(db, p.id)
    data = _enriched(db, p.id)
    ids = series_filter_node_ids(data, "episode")
    assert all(node_kind(data.nodes[i]) == NODE_KIND_EPISODE for i in ids)
    assert ids


def test_filter_by_mystery_thread():
    db = Database()
    p = _show(db)
    _build(db, p.id)
    data = _enriched(db, p.id)
    ids = series_filter_node_ids(data, "mystery")
    kinds = {node_kind(data.nodes[i]) for i in ids}
    assert kinds <= {NODE_KIND_MYSTERY, NODE_KIND_EPISODE}
    assert any(node_kind(data.nodes[i]) == NODE_KIND_MYSTERY for i in ids)


def test_filter_by_character():
    db = Database()
    p = _show(db)
    _build(db, p.id)
    data = _enriched(db, p.id)
    ids = series_filter_node_ids(data, "character")
    assert all(node_kind(data.nodes[i]) == NODE_KIND_CHARACTER for i in ids)


# =========================================================================
# 4. View mode switching + no-hairball default (§4, §5)
# =========================================================================

def test_view_detects_series_mode():
    db = Database()
    p = _show(db)
    view = FocusGraphView(db, p.id)
    assert view._series_mode is True
    for mode in SERIES_MODE_ORDER:
        assert mode in view._mode_buttons


def test_novel_view_no_series_buttons():
    db = Database()
    p = db.create_project("Novel")
    view = FocusGraphView(db, p.id)
    assert view._series_mode is False
    for mode in SERIES_MODE_ORDER:
        assert mode not in view._mode_buttons


def test_default_mode_is_season_arc():
    db = Database()
    p = _show(db)
    _build(db, p.id)
    view = FocusGraphView(db, p.id)
    assert view.get_mode() == MODE_SR_SEASON_ARC


def test_no_hairball_default():
    """Default view shows only the current season + active arcs, not the
    whole series."""
    db = Database()
    p = _show(db)
    _s1, _s2, e1, e2, e3, _c = _build(db, p.id)
    data = _enriched(db, p.id)
    view = FocusGraphView(db, p.id)
    visible = set(view._node_items.keys())
    # Strictly fewer nodes than the full enriched graph.
    assert 0 < len(visible) < len(data.nodes)
    # Season 1's episodes (E1, E2) are NOT in the default view.
    assert f"Episode:{e1.id}" not in visible
    assert f"Episode:{e2.id}" not in visible
    # Season 2 (current) and its episode E3 ARE.
    assert f"Episode:{e3.id}" in visible


def test_switch_modes():
    db = Database()
    p = _show(db)
    _build(db, p.id)
    view = FocusGraphView(db, p.id)
    for mode in SERIES_MODE_ORDER:
        view.set_mode(mode)
        assert view.get_mode() == mode
    view.set_mode(MODE_ALL)
    assert view.get_mode() == MODE_ALL


def test_switching_mode_lifts_default_restriction():
    db = Database()
    p = _show(db)
    _build(db, p.id)
    view = FocusGraphView(db, p.id)
    # Switching to episode-dependency (a user action) drops the current-season
    # restriction → all episodes become visible.
    view.set_mode(MODE_SR_EPISODE_DEP)
    kinds = {node_kind(view._graph_data.nodes[n]) for n in view._node_items}
    assert kinds == {NODE_KIND_EPISODE}
    assert len(view._node_items) == 3   # all three episodes, not just current


def test_season_arc_mode_shows_seasons_and_episodes_only():
    db = Database()
    p = _show(db)
    _build(db, p.id)
    view = FocusGraphView(db, p.id)
    view.set_mode(MODE_SR_SEASON_ARC)   # explicit switch lifts restriction
    for nid in view._node_items:
        assert node_kind(view._graph_data.nodes[nid]) in {
            NODE_KIND_SEASON, NODE_KIND_EPISODE, NODE_KIND_ARC,
            NODE_KIND_MYSTERY,
        }


def test_mystery_mode_no_hairball():
    db = Database()
    p = _show(db)
    _build(db, p.id)
    view = FocusGraphView(db, p.id)
    view.set_mode(MODE_SR_MYSTERY)
    for nid in view._node_items:
        assert node_kind(view._graph_data.nodes[nid]) in {
            NODE_KIND_EPISODE, NODE_KIND_MYSTERY, NODE_KIND_ARC,
        }


def test_abc_plot_mode_includes_plotlines():
    db = Database()
    p = _show(db)
    _build(db, p.id)
    view = FocusGraphView(db, p.id)
    view.set_mode(MODE_SR_ABC_PLOT)
    kinds = {node_kind(view._graph_data.nodes[n]) for n in view._node_items}
    assert NODE_KIND_PLOTLINE in kinds


def test_continuity_mode_characters_and_episodes():
    db = Database()
    p = _show(db)
    _build(db, p.id)
    view = FocusGraphView(db, p.id)
    view.set_mode(MODE_SR_CONTINUITY)
    for nid in view._node_items:
        assert node_kind(view._graph_data.nodes[nid]) in {
            NODE_KIND_CHARACTER, NODE_KIND_EPISODE,
        }


def test_default_node_ids_empty_without_seasons():
    db = Database()
    p = _show(db)
    data = _enriched(db, p.id)
    assert series_default_node_ids(db, p.id, data) == set()
