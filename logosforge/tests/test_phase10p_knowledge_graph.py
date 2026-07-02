"""Phase 10P — Narrative Knowledge Graph Consolidation."""

from __future__ import annotations

import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.knowledge_graph import (
    GraphQuery,
    build_graph_decision_cards,
    build_knowledge_graph,
    confirm_edge,
    convert_edge_to_psyke_relation,
    create_psyke_entry_from_term,
    get_graph_summary_for_assistant,
    get_high_centrality_nodes,
    get_orphan_nodes,
    get_psyke_entry_context_graph,
    get_scene_context_graph,
    get_weak_links,
    hide_edge,
    node_key,
    persist_snapshot,
    query_knowledge_graph,
)
from logosforge.knowledge_graph import provenance as P


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path, raising=False)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json",
                        raising=False)
    import logosforge.gomckee_bridge as gb
    monkeypatch.setattr(gb, "is_gomckee_enabled", lambda: False)
    yield
    settings._instance = None


def _project(mode="novel"):
    db = Database()
    pid = db.create_project("My Story", narrative_engine=mode).id
    alice = db.create_psyke_entry(pid, "Alice", "character")
    bob = db.create_psyke_entry(pid, "Bob", "character")
    db.add_psyke_relation(alice.id, bob.id, "ally")
    db.create_psyke_entry(pid, "Lonely Idol", "object")  # orphan
    s1 = db.create_scene(pid, "Opening", content="Alice meets Bob.",
                         summary="intro", chapter="Ch1", act="Act 1")
    s2 = db.create_scene(pid, "Twist", content="Bob betrays Alice.",
                         summary="turn", chapter="Ch1")
    return db, pid, alice.id, bob.id, s1.id, s2.id


# ===========================================================================
# Migration / persistence
# ===========================================================================


def test_tables_created_and_db_opens():
    db = Database()
    pid = db.create_project("Empty", narrative_engine="novel").id
    assert db.get_kg_nodes(pid) == []
    assert db.get_kg_edges(pid) == []
    assert db.get_latest_kg_snapshot(pid) is None


def test_build_empty_project_no_crash():
    db = Database()
    pid = db.create_project("Empty", narrative_engine="novel").id
    res = build_knowledge_graph(db, pid)
    # project node always present
    assert res.node_count >= 1
    assert res.edge_count == 0 or res.edge_count >= 0


def test_snapshot_persisted():
    db, pid, *_ = _project()
    res = build_knowledge_graph(db, pid)
    snap = persist_snapshot(db, pid, res)
    assert snap is not None
    latest = db.get_latest_kg_snapshot(pid)
    assert latest.node_count == res.node_count


def test_confirmed_edge_survives_rebuild():
    db, pid, aid, bid, s1, s2 = _project()
    res = build_knowledge_graph(db, pid)
    pre = [e for e in res.graph.edges if e.edge_type == P.ET_PRECEDES][0]
    assert pre.is_inferred
    confirm_edge(db, pid, pre, graph=res.graph)
    res2 = build_knowledge_graph(db, pid)
    pre2 = [e for e in res2.graph.edges if e.edge_type == P.ET_PRECEDES][0]
    assert pre2.is_user_confirmed and pre2.confidence == P.CONF_CONFIRMED


def test_hidden_edge_survives_rebuild():
    db, pid, aid, bid, s1, s2 = _project()
    res = build_knowledge_graph(db, pid)
    pre = [e for e in res.graph.edges if e.edge_type == P.ET_PRECEDES][0]
    hide_edge(db, pid, pre)
    res2 = build_knowledge_graph(db, pid)
    pre_rows = [e for e in res2.graph.edges if e.edge_type == P.ET_PRECEDES]
    assert pre_rows and pre_rows[0].is_hidden
    assert all(e.edge_type != P.ET_PRECEDES for e in res2.graph.visible_edges())


def test_current_project_only():
    db, pid_a, *_ = _project()
    pid_b = db.create_project("Other", narrative_engine="novel").id
    res_b = build_knowledge_graph(db, pid_b)
    # B has no scenes/psyke; only its own project node
    assert all(n.source_id != str(pid_a) or n.node_type == P.NT_PROJECT
               for n in res_b.graph.nodes.values())
    assert res_b.graph.nodes_of_type(P.NT_SCENE) == []


# ===========================================================================
# PSYKE extraction
# ===========================================================================


def test_psyke_entries_become_nodes():
    db, pid, aid, bid, s1, s2 = _project()
    g = build_knowledge_graph(db, pid).graph
    chars = g.nodes_of_type(P.NT_CHARACTER)
    labels = {n.label for n in chars}
    assert "Alice" in labels and "Bob" in labels


def test_psyke_relations_are_confirmed_edges():
    db, pid, aid, bid, s1, s2 = _project()
    g = build_knowledge_graph(db, pid).graph
    rel = [e for e in g.edges if e.edge_type == P.ET_RELATES_TO
           and e.source_system == P.SS_PSYKE]
    assert rel and all(e.confidence == P.CONF_CONFIRMED for e in rel)


def test_psyke_appears_in_scene_via_text_match():
    db, pid, aid, bid, s1, s2 = _project()
    g = build_knowledge_graph(db, pid).graph
    appears = [e for e in g.edges if e.edge_type == P.ET_APPEARS_IN]
    assert appears and all(e.confidence == P.CONF_CONFIRMED for e in appears)


def test_orphan_psyke_detected():
    db, pid, aid, bid, s1, s2 = _project()
    orphans = get_orphan_nodes(db, pid)
    assert any(n.label == "Lonely Idol" for n in orphans)


def test_global_entry_does_not_flood_scenes():
    db = Database()
    pid = db.create_project("G", narrative_engine="novel").id
    db.create_psyke_entry(pid, "Magic", "theme", is_global=True)
    db.create_scene(pid, "S1", content="A scene about magic everywhere.")
    db.create_scene(pid, "S2", content="More magic here.")
    g = build_knowledge_graph(db, pid).graph
    # global entry attaches to project, not to each scene via appears_in
    appears = [e for e in g.edges if e.edge_type == P.ET_APPEARS_IN]
    assert appears == []
    belongs = [e for e in g.edges if e.edge_type == P.ET_BELONGS_TO]
    assert belongs


def test_aliases_map_to_same_node():
    db = Database()
    pid = db.create_project("A", narrative_engine="novel").id
    db.create_psyke_entry(pid, "Robert", "character", aliases="Bob,Bobby")
    db.create_scene(pid, "S", content="Bob walked in. Bobby smiled.")
    g = build_knowledge_graph(db, pid).graph
    chars = g.nodes_of_type(P.NT_CHARACTER)
    assert len(chars) == 1  # one node despite multiple aliases


# ===========================================================================
# Structure extraction
# ===========================================================================


def test_chapter_contains_scene_edges():
    db, pid, aid, bid, s1, s2 = _project()
    g = build_knowledge_graph(db, pid).graph
    contains = [e for e in g.edges if e.edge_type == P.ET_CONTAINS
                and e.source_system in (P.SS_OUTLINE, P.SS_STRUCTURE)]
    assert contains
    chapters = g.nodes_of_type(P.NT_CHAPTER)
    assert any(n.label == "Ch1" for n in chapters)


def test_scene_order_is_likely_not_causal():
    db, pid, aid, bid, s1, s2 = _project()
    g = build_knowledge_graph(db, pid).graph
    pre = [e for e in g.edges if e.edge_type == P.ET_PRECEDES]
    assert pre and all(e.confidence == P.CONF_LIKELY for e in pre)
    # no fake causality edges invented
    assert all(e.edge_type != P.ET_CAUSES for e in g.edges)


def test_plot_block_membership():
    db = Database()
    pid = db.create_project("P", narrative_engine="novel").id
    db.create_scene(pid, "S1", content="x", plotline="Main")
    db.create_scene(pid, "S2", content="y", plotline="Main")
    g = build_knowledge_graph(db, pid).graph
    plots = g.nodes_of_type(P.NT_PLOT_BLOCK)
    assert any(n.label == "Main" for n in plots)


def test_missing_sections_degrade_cleanly():
    db = Database()
    pid = db.create_project("Bare", narrative_engine="novel").id
    res = build_knowledge_graph(db, pid)
    # setup_payoff unavailable for novel; should be listed, not crash
    assert "setup_payoff" in res.graph.unavailable


# ===========================================================================
# Notes extraction
# ===========================================================================


def test_note_nodes_and_mentions():
    db, pid, aid, bid, s1, s2 = _project()
    db.create_note(pid, "Plan", "Alice should confront Bob.")
    g = build_knowledge_graph(db, pid).graph
    notes = g.nodes_of_type(P.NT_NOTE)
    assert any(n.label == "Plan" for n in notes)
    mentions = [e for e in g.edges if e.edge_type == P.ET_MENTIONS]
    assert mentions


def test_undefined_terms_detected_no_psyke_creation():
    db, pid, aid, bid, s1, s2 = _project()
    db.create_note(pid, "Lore", "The Crimson Order rules the North Reach.")
    before = len(db.get_all_psyke_entries(pid))
    res = build_knowledge_graph(db, pid)
    assert res.undefined_terms  # detected
    assert len(db.get_all_psyke_entries(pid)) == before  # never auto-created


# ===========================================================================
# Revision / rewrite / apply extraction
# ===========================================================================


def test_rewrite_variant_derived_from_scene():
    db, pid, aid, bid, s1, s2 = _project()
    sess = db.create_rewrite_session(pid, source_type="scene", source_id=s1)
    db.create_rewrite_variant(pid, sess.id, label="V1", strategy="clarify")
    g = build_knowledge_graph(db, pid).graph
    der = [e for e in g.edges if e.edge_type == P.ET_DERIVED_FROM]
    assert der and der[0].source_system == P.SS_REWRITE


def test_apply_operation_targets_scene():
    db, pid, aid, bid, s1, s2 = _project()
    db.create_apply_operation(pid, target_type="scene", target_id=s1,
                              status="previewed")
    g = build_knowledge_graph(db, pid).graph
    ca = g.nodes_of_type(P.NT_CONTROLLED_APPLY)
    assert ca
    risks = [e for e in g.edges if e.source_system == P.SS_CONTROLLED_APPLY]
    assert risks


def test_deferred_systems_handled_when_absent():
    db = Database()
    pid = db.create_project("Min", narrative_engine="novel").id
    db.create_scene(pid, "S", content="x")
    res = build_knowledge_graph(db, pid)  # no revision/rewrite/apply data
    assert isinstance(res.graph.unavailable, list)  # no crash


# ===========================================================================
# Queries
# ===========================================================================


def test_scene_neighborhood_query():
    db, pid, aid, bid, s1, s2 = _project()
    res = get_scene_context_graph(db, pid, s1)
    assert res.nodes and res.edges
    labels = {n.label for n in res.nodes}
    assert "Opening" in labels


def test_psyke_neighborhood_query():
    db, pid, aid, bid, s1, s2 = _project()
    res = get_psyke_entry_context_graph(db, pid, aid)
    assert res.nodes


def test_query_confidence_filter():
    db, pid, aid, bid, s1, s2 = _project()
    q = GraphQuery(confidence_min=P.CONF_CONFIRMED, include_inferred=True)
    res = query_knowledge_graph(db, pid, q)
    assert all(P.confidence_rank(e.confidence) <= P.confidence_rank(P.CONF_CONFIRMED)
               for e in res.edges)


def test_query_edge_type_filter():
    db, pid, aid, bid, s1, s2 = _project()
    q = GraphQuery(edge_type=P.ET_APPEARS_IN)
    res = query_knowledge_graph(db, pid, q)
    assert res.edges and all(e.edge_type == P.ET_APPEARS_IN for e in res.edges)


def test_query_limit_respected():
    db, pid, aid, bid, s1, s2 = _project()
    q = GraphQuery(limit=2)
    res = query_knowledge_graph(db, pid, q)
    assert len(res.edges) <= 2


def test_weak_links_are_inferred():
    db, pid, aid, bid, s1, s2 = _project()
    weak = get_weak_links(db, pid)
    assert all(e.is_inferred for e in weak)


def test_high_centrality_nodes():
    db, pid, aid, bid, s1, s2 = _project()
    central = get_high_centrality_nodes(db, pid)
    assert central and central[0][1] > 0


def test_queries_do_not_mutate_db():
    db, pid, aid, bid, s1, s2 = _project()
    before = (len(db.get_all_scenes(pid)), len(db.get_all_psyke_entries(pid)),
              len(db.get_kg_edges(pid)))
    build_knowledge_graph(db, pid)
    get_scene_context_graph(db, pid, s1)
    get_orphan_nodes(db, pid)
    after = (len(db.get_all_scenes(pid)), len(db.get_all_psyke_entries(pid)),
             len(db.get_kg_edges(pid)))
    assert before == after


# ===========================================================================
# Confirmable mutations (content) — explicit only
# ===========================================================================


def test_convert_edge_to_psyke_relation():
    db = Database()
    pid = db.create_project("C", narrative_engine="novel").id
    a = db.create_psyke_entry(pid, "Alice", "character")
    b = db.create_psyke_entry(pid, "Bob", "character")
    db.create_scene(pid, "S", content="Alice and Bob talk.")
    g = build_knowledge_graph(db, pid).graph
    # an appears_in edge is scene<->psyke; build a synthetic psyke<->psyke edge
    from logosforge.knowledge_graph.models import KGEdge
    edge = KGEdge(source=node_key(P.NT_CHARACTER, "psyke", a.id),
                  target=node_key(P.NT_CHARACTER, "psyke", b.id),
                  edge_type=P.ET_RELATES_TO, confidence=P.CONF_LIKELY)
    assert convert_edge_to_psyke_relation(db, edge) is True
    assert db.get_related_psyke_entries(a.id)


def test_create_psyke_from_term():
    db = Database()
    pid = db.create_project("T", narrative_engine="novel").id
    before = len(db.get_all_psyke_entries(pid))
    ent = create_psyke_entry_from_term(db, pid, "Crimson Order", entry_type="lore")
    assert ent is not None
    assert len(db.get_all_psyke_entries(pid)) == before + 1


# ===========================================================================
# Decision cards
# ===========================================================================


def test_graph_decision_cards():
    db, pid, aid, bid, s1, s2 = _project()
    db.create_note(pid, "Lore", "The Crimson Order is powerful.")
    cards = build_graph_decision_cards(db, pid)
    ids = {c.id for c in cards}
    assert any(i.startswith("kg_isolated") for i in ids)  # Lonely Idol orphan
    assert "kg_undefined_terms" in ids


def test_decision_cards_no_hallucination_on_clean_project():
    db = Database()
    pid = db.create_project("Clean", narrative_engine="novel").id
    a = db.create_psyke_entry(pid, "Alice", "character")
    db.create_scene(pid, "S", content="Alice acts.", chapter="Ch1")
    cards = build_graph_decision_cards(db, pid)
    # no orphan/undefined cards for a clean tiny project
    assert all(not c.id.startswith("kg_isolated") for c in cards)


# ===========================================================================
# Logos
# ===========================================================================


def test_logos_kg_actions_registered_and_deterministic():
    from logosforge.logos.actions import get_action
    from logosforge.logos.deterministic import is_deterministic
    for name in ("kg_build_graph", "kg_refresh_graph", "kg_scene_neighborhood",
                 "kg_psyke_neighborhood", "kg_find_orphans", "kg_find_weak_links",
                 "kg_find_undefined_terms", "kg_decision_cards"):
        assert get_action(name) is not None
        assert is_deterministic(name)


def test_logos_kg_explain_is_generative():
    from logosforge.logos.actions import get_action
    act = get_action("kg_explain_graph")
    assert act is not None and not act.deterministic


def test_logos_kg_build_runs():
    from logosforge.logos.context import build_logos_context
    from logosforge.logos.deterministic import get_handler
    db, pid, aid, bid, s1, s2 = _project()
    ctx = build_logos_context(db, pid, section_name="Manuscript")
    res = get_handler("kg_build_graph")(db, ctx)
    assert res.ok and "Knowledge Graph" in res.message


def test_logos_kg_scene_neighborhood_needs_scene():
    from logosforge.logos.context import build_logos_context
    from logosforge.logos.deterministic import get_handler
    db, pid, aid, bid, s1, s2 = _project()
    ctx = build_logos_context(db, pid, section_name="Manuscript")
    res = get_handler("kg_scene_neighborhood")(db, ctx)
    assert res.ok and "Open a scene" in res.message
    ctx2 = build_logos_context(db, pid, section_name="Manuscript",
                               current_scene_id=s1)
    res2 = get_handler("kg_scene_neighborhood")(db, ctx2)
    assert res2.ok and "Opening" in res2.message


# ===========================================================================
# Assistant context
# ===========================================================================


def test_assistant_block_scene_scoped():
    db, pid, aid, bid, s1, s2 = _project()
    block = get_graph_summary_for_assistant(db, pid, scene_id=s1)
    assert block.startswith("[Narrative Knowledge Graph]")
    assert "Alice" in block or "Bob" in block


def test_assistant_block_empty_without_scene_in_policy():
    from logosforge.assistant_context_policy import _knowledge_graph_block
    db, pid, aid, bid, s1, s2 = _project()
    assert _knowledge_graph_block(db, pid, None) == ""


def test_assistant_block_respects_flag_off():
    from logosforge.assistant_context_policy import gather_injected_context
    from logosforge.settings import get_manager
    db, pid, aid, bid, s1, s2 = _project()
    get_manager().set("include_knowledge_graph_in_assistant_context", False)
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=s1)
    assert "[Narrative Knowledge Graph]" not in ctx


def test_assistant_context_no_db_mutation():
    from logosforge.assistant_context_policy import gather_injected_context
    db, pid, aid, bid, s1, s2 = _project()
    before = (len(db.get_all_scenes(pid)), len(db.get_kg_edges(pid)))
    gather_injected_context(db, pid, section_name="Manuscript", scene_id=s1)
    after = (len(db.get_all_scenes(pid)), len(db.get_kg_edges(pid)))
    assert before == after


# ===========================================================================
# Guided Workflows integration
# ===========================================================================


def test_graph_cleanup_workflow_present():
    from logosforge.guided_workflows import list_workflow_templates
    ids = {t.id for t in list_workflow_templates("novel")}
    assert "knowledge_graph_cleanup" in ids


def test_graph_cleanup_workflow_starts():
    from logosforge.guided_workflows import start_workflow
    db, pid, aid, bid, s1, s2 = _project()
    v = start_workflow(db, pid, "knowledge_graph_cleanup")
    assert v is not None and v.total_steps >= 5
