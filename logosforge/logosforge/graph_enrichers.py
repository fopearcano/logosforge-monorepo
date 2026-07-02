"""Format-specific graph enrichers — Qt-free core (moved out of the Qt UI module).

Each enricher takes a base ``GraphData`` (from :func:`logosforge.graph_data.build_graph_data`)
and injects the format-specific nodes + typed edges that drive that format's graph
intelligence: screenplay (causality / setup-payoff / subtext / knowledge / continuity),
graphic novel (pages / panels / motifs / object-continuity), stage (cues / entrances /
props / blocking / offstage), series (seasons / episodes / arcs / plotlines).

They read only the DB and append ``GraphNode`` / ``GraphEdge`` objects — no Qt — so the
headless API (story-gravity, server mode) can enrich the graph without a display stack.
``logosforge.ui.focus_graph_view`` re-exports them for the Qt app.
"""

from __future__ import annotations

from logosforge.db import Database
from logosforge.graph_data import (
    GraphData,
    GraphEdge,
    GraphNode,
    NODE_KIND_CHARACTER,
    NODE_KIND_PLACE,
    NODE_KIND_SCENE,
    NODE_KIND_PAGE,
    NODE_KIND_PANEL,
    NODE_KIND_MOTIF,
    NODE_KIND_GN_OBJECT,
    NODE_KIND_CUE,
    NODE_KIND_OFFSTAGE,
    NODE_KIND_SEASON,
    NODE_KIND_EPISODE,
    NODE_KIND_ARC,
    NODE_KIND_MYSTERY,
    NODE_KIND_PLOTLINE,
    EDGE_CAUSALITY,
    EDGE_SETUP_PAYOFF,
    EDGE_KNOWLEDGE,
    EDGE_SUBTEXT,
    EDGE_VISUAL_MOTIF,
    EDGE_CONTINUITY,
    EDGE_GN_CONTAINS,
    EDGE_GN_PAGE_FLOW,
    EDGE_GN_PANEL_CAUSALITY,
    EDGE_GN_MOTIF,
    EDGE_GN_SYMBOL_ECHO,
    EDGE_GN_OBJECT_CONTINUITY,
    EDGE_SS_PRESSURE,
    EDGE_SS_SUBTEXT,
    EDGE_SS_ENTRANCE_EXIT,
    EDGE_SS_USES_PROP,
    EDGE_SS_BLOCKING,
    EDGE_SS_CUE,
    EDGE_SS_OFFSTAGE,
    EDGE_SR_CONTAINS,
    EDGE_SR_CONTINUES,
    EDGE_SR_SETS_UP,
    EDGE_SR_PAYS_OFF,
    EDGE_SR_RESOLVES,
    EDGE_SR_DELAYS,
    EDGE_SR_ESCALATES,
    EDGE_SR_ECHOES,
    EDGE_SR_CONTRADICTS,
)


def enrich_screenplay_edges(
    db: Database, project_id: int, data: GraphData,
) -> None:
    """Add screenplay-specific typed edges to an existing graph.

    Called after build_graph_data() for screenplay projects to produce
    causality, setup/payoff, knowledge, subtext, visual-motif, and
    continuity edges from scene metadata, PSYKE typed relations, and
    story-memory entries.
    """
    scenes = db.get_all_scenes(project_id)
    scenes_sorted = sorted(scenes, key=lambda s: s.sort_order)

    scene_chars: dict[int, set[int]] = {}
    for s in scenes_sorted:
        scene_chars[s.id] = set(db.get_scene_character_ids(s.id))

    seen: set[tuple[str, str, str]] = set()

    def _add(src: str, tgt: str, etype: str) -> None:
        key = (min(src, tgt), max(src, tgt), etype)
        if key in seen or src not in data.nodes or tgt not in data.nodes:
            return
        seen.add(key)
        data.edges.append(GraphEdge(src, tgt, edge_type=etype))
        data.adjacency.setdefault(src, set()).add(tgt)
        data.adjacency.setdefault(tgt, set()).add(src)

    # 1. Causality: consecutive scenes sharing at least one character.
    for i in range(len(scenes_sorted) - 1):
        s1, s2 = scenes_sorted[i], scenes_sorted[i + 1]
        if scene_chars.get(s1.id, set()) & scene_chars.get(s2.id, set()):
            _add(f"Scene:{s1.id}", f"Scene:{s2.id}", EDGE_CAUSALITY)

    # 2–4. Typed PSYKE relations → setup/payoff, subtext, visual-motif edges.
    _PSYKE_EDGE_MAP: dict[str, str] = {
        "supports_setup": EDGE_SETUP_PAYOFF,
        "payoff": EDGE_SETUP_PAYOFF,
        "subtext_opposition": EDGE_SUBTEXT,
        "visual_motif": EDGE_VISUAL_MOTIF,
    }
    for entry in db.get_all_psyke_entries(project_id):
        for rel_entry, rel_type in db.get_typed_related_psyke_entries(entry.id):
            edge_type = _PSYKE_EDGE_MAP.get(rel_type)
            if edge_type:
                _add(f"PSYKE:{entry.id}", f"PSYKE:{rel_entry.id}", edge_type)

    # 5. Knowledge: scenes with who_knows_what sharing characters.
    knowledge_scenes = [s for s in scenes_sorted if (s.who_knows_what or "").strip()]
    for i, s1 in enumerate(knowledge_scenes):
        for s2 in knowledge_scenes[i + 1:]:
            if scene_chars.get(s1.id, set()) & scene_chars.get(s2.id, set()):
                _add(f"Scene:{s1.id}", f"Scene:{s2.id}", EDGE_KNOWLEDGE)

    # 6. Continuity: same target tracked across multiple scenes.
    memories = db.get_memories(project_id)
    target_scenes: dict[tuple[str, str], list[int]] = {}
    for m in memories:
        if not m.memory_type.startswith("continuity_"):
            continue
        target_scenes.setdefault((m.target, m.memory_type), []).append(m.scene_id)
    for scene_ids in target_scenes.values():
        unique_ids = sorted(set(scene_ids))
        for i in range(len(unique_ids) - 1):
            _add(
                f"Scene:{unique_ids[i]}",
                f"Scene:{unique_ids[i + 1]}",
                EDGE_CONTINUITY,
            )


def enrich_graphic_novel_graph(
    db: Database, project_id: int, data: GraphData,
) -> None:
    """Inject graphic-novel nodes + edges into the graph.

    Adds page, panel, motif and object nodes (which don't live in the base
    link graph) plus the edges that drive the GN graph modes: page-panel
    containment, page-flow / panel-causality (reading order), motif
    appearances + symbol echoes, and object-continuity appearances.
    """
    pages = db.get_gn_pages(project_id)
    if not pages:
        return

    def _node(node_id: str, etype: str, eid: int, name: str, kind: str) -> None:
        if node_id not in data.nodes:
            data.nodes[node_id] = GraphNode(node_id, etype, eid, name, subtype=kind)
            data.adjacency.setdefault(node_id, set())

    def _edge(src: str, tgt: str, etype: str) -> None:
        if src not in data.nodes or tgt not in data.nodes:
            return
        data.edges.append(GraphEdge(src, tgt, edge_type=etype))
        data.adjacency.setdefault(src, set()).add(tgt)
        data.adjacency.setdefault(tgt, set()).add(src)

    page_node = {p.id: f"GNPage:{p.id}" for p in pages}
    page_number = {p.id: p.page_number for p in pages}

    # Page + panel nodes, containment, panel reading order.
    motif_pages: dict[str, list[int]] = {}
    last_panel_node: str | None = None
    for page in pages:
        pn = page_node[page.id]
        _node(pn, "GNPage", page.id, f"Page {page.page_number}", NODE_KIND_PAGE)
        panels = db.get_gn_panels_for_page(page.id)
        for panel in panels:
            paneln = f"GNPanel:{panel.id}"
            _node(paneln, "GNPanel", panel.id,
                  f"P{page.page_number}.{panel.panel_number}", NODE_KIND_PANEL)
            _edge(pn, paneln, EDGE_GN_CONTAINS)
            if last_panel_node is not None:
                _edge(last_panel_node, paneln, EDGE_GN_PANEL_CAUSALITY)
            last_panel_node = paneln
            for motif in db.csv_split(panel.visual_motifs):
                motif_pages.setdefault(motif, [])
                if page.id not in motif_pages[motif]:
                    motif_pages[motif].append(page.id)

    # Page-flow (reading rhythm).
    for i in range(len(pages) - 1):
        _edge(page_node[pages[i].id], page_node[pages[i + 1].id], EDGE_GN_PAGE_FLOW)

    # Motif nodes + appearances + symbol echoes (pages sharing a motif).
    for idx, (motif, pids) in enumerate(sorted(motif_pages.items())):
        motif_node = f"GNMotif:{motif}"
        _node(motif_node, "GNMotif", idx, motif, NODE_KIND_MOTIF)
        for pid in pids:
            _edge(motif_node, page_node[pid], EDGE_GN_MOTIF)
        ordered = sorted(pids, key=lambda x: page_number.get(x, 0))
        for i in range(len(ordered) - 1):
            _edge(page_node[ordered[i]], page_node[ordered[i + 1]],
                  EDGE_GN_SYMBOL_ECHO)

    # Object continuity nodes + appearances.
    for item in db.get_gn_continuity_items(project_id):
        obj_node = f"GNObject:{item.id}"
        _node(obj_node, "GNObject", item.id, item.name, NODE_KIND_GN_OBJECT)
        for app in db.get_gn_continuity_appearances(item.id):
            pid = app.page_id
            if pid is None and app.panel_id is not None:
                panel = db.get_gn_panel_by_id(app.panel_id)
                pid = panel.page_id if panel else None
            if pid is not None and pid in page_node:
                _edge(obj_node, page_node[pid], EDGE_GN_OBJECT_CONTINUITY)


def enrich_stage_script_graph(
    db: Database, project_id: int, data: GraphData,
) -> None:
    """Inject stage-script nodes + edges into the graph.

    Adds cue and offstage-event nodes (which don't live in the base
    graph) plus the edges that drive the stage graph modes: character
    pressure / subtext (PSYKE theatre relations), entrances/exits
    (character ↔ scene), prop usage (character → prop → scene), blocking
    (scene ↔ set location), cues (scene → cue) and offstage events.
    """
    scenes = db.get_all_scenes(project_id)
    if not scenes:
        return

    char_name = {}
    try:
        char_name = {c.id: c.name for c in db.get_all_characters(project_id)}
    except Exception:
        char_name = {}
    place_name = {}
    try:
        place_name = {p.id: p.name for p in db.get_all_places(project_id)}
    except Exception:
        place_name = {}

    def _node(node_id, etype, eid, name, kind):
        if node_id not in data.nodes:
            data.nodes[node_id] = GraphNode(node_id, etype, eid, name, subtype=kind)
            data.adjacency.setdefault(node_id, set())

    def _edge(src, tgt, etype):
        if src not in data.nodes or tgt not in data.nodes:
            return
        data.edges.append(GraphEdge(src, tgt, edge_type=etype))
        data.adjacency.setdefault(src, set()).add(tgt)
        data.adjacency.setdefault(tgt, set()).add(src)

    # 1. Pressure / subtext — typed PSYKE theatre relations.
    _PRESSURE = {"pressures", "confronts", "dominates", "deceives", "interrupts"}
    _SUBTEXT = {"subtext_opposition", "avoids"}
    seen_rel: set[tuple[str, str, str]] = set()
    for entry in db.get_all_psyke_entries(project_id):
        try:
            typed = db.get_typed_related_psyke_entries(entry.id)
        except Exception:
            typed = []
        for rel_entry, rel_type in typed:
            etype = (
                EDGE_SS_PRESSURE if rel_type in _PRESSURE
                else EDGE_SS_SUBTEXT if rel_type in _SUBTEXT
                else None
            )
            if etype is None:
                continue
            src, tgt = f"PSYKE:{entry.id}", f"PSYKE:{rel_entry.id}"
            key = (min(src, tgt), max(src, tgt), etype)
            if key in seen_rel:
                continue
            seen_rel.add(key)
            _edge(src, tgt, etype)

    # 2. Entrances/exits — character ↔ scene.
    for scene in scenes:
        scene_node = f"Scene:{scene.id}"
        if scene_node not in data.nodes:
            _node(scene_node, "Scene", scene.id, scene.title, NODE_KIND_SCENE)
        for ee in db.get_stage_entrances_exits(scene.id):
            if ee.character_id is None:
                continue
            cnode = f"Character:{ee.character_id}"
            _node(cnode, "Character", ee.character_id,
                  char_name.get(ee.character_id, f"#{ee.character_id}"),
                  NODE_KIND_CHARACTER)
            _edge(cnode, scene_node, EDGE_SS_ENTRANCE_EXIT)

    # 3. Prop usage — character → prop → scene.
    for scene in scenes:
        scene_node = f"Scene:{scene.id}"
        for biz in db.get_stage_business(scene.id):
            if biz.prop_psyke_entry_id is None:
                continue
            prop_node = f"PSYKE:{biz.prop_psyke_entry_id}"
            if prop_node not in data.nodes:
                continue  # prop entry should exist in the base graph
            if biz.character_id is not None:
                cnode = f"Character:{biz.character_id}"
                _node(cnode, "Character", biz.character_id,
                      char_name.get(biz.character_id, f"#{biz.character_id}"),
                      NODE_KIND_CHARACTER)
                _edge(cnode, prop_node, EDGE_SS_USES_PROP)
            _edge(prop_node, scene_node, EDGE_SS_USES_PROP)

    # 4. Blocking — scene ↔ set location.
    for scene in scenes:
        scene_node = f"Scene:{scene.id}"
        try:
            place_ids = db.get_scene_place_ids(scene.id)
        except Exception:
            place_ids = []
        for pid in place_ids:
            pnode = f"Place:{pid}"
            _node(pnode, "Place", pid, place_name.get(pid, f"#{pid}"),
                  NODE_KIND_PLACE)
            _edge(scene_node, pnode, EDGE_SS_BLOCKING)

    # 5. Cues — scene → cue.
    for scene in scenes:
        scene_node = f"Scene:{scene.id}"
        for cue in db.get_stage_cues(scene.id):
            cue_node = f"Cue:{cue.id}"
            _node(cue_node, "Cue", cue.id,
                  cue.cue_type + (f": {cue.cue_text}" if cue.cue_text else ""),
                  NODE_KIND_CUE)
            _edge(scene_node, cue_node, EDGE_SS_CUE)

    # 6. Offstage events — scene → offstage node ↔ on-stage characters.
    for scene in scenes:
        if not (getattr(scene, "offstage_events", "") or "").strip():
            continue
        scene_node = f"Scene:{scene.id}"
        off_node = f"Offstage:{scene.id}"
        _node(off_node, "Offstage", scene.id, scene.offstage_events,
              NODE_KIND_OFFSTAGE)
        _edge(scene_node, off_node, EDGE_SS_OFFSTAGE)
        try:
            cids = db.get_scene_character_ids(scene.id)
        except Exception:
            cids = []
        for cid in cids:
            cnode = f"Character:{cid}"
            _node(cnode, "Character", cid, char_name.get(cid, f"#{cid}"),
                  NODE_KIND_CHARACTER)
            _edge(cnode, off_node, EDGE_SS_OFFSTAGE)


def enrich_series_graph(
    db: Database, project_id: int, data: GraphData,
) -> None:
    """Inject series nodes + edges into the graph.

    Adds season, episode, arc/mystery and A/B/C plotline nodes (which don't
    live in the base link graph) plus the edges that drive the series graph
    modes: season→episode containment, episode→episode dependency, arc
    setups/payoffs/escalations (typed by status), character progression /
    callback echoes and continuity-risk contradictions.
    """
    from logosforge.series_plot import _ordered_episodes

    episodes = _ordered_episodes(db, project_id)
    if not episodes:
        return

    def _node(node_id, etype, eid, name, kind):
        if node_id not in data.nodes:
            data.nodes[node_id] = GraphNode(node_id, etype, eid, name, subtype=kind)
            data.adjacency.setdefault(node_id, set())

    def _edge(src, tgt, etype):
        if src not in data.nodes or tgt not in data.nodes:
            return
        data.edges.append(GraphEdge(src, tgt, edge_type=etype))
        data.adjacency.setdefault(src, set()).add(tgt)
        data.adjacency.setdefault(tgt, set()).add(src)

    ep_node = {ep.id: f"Episode:{ep.id}" for ep in episodes}
    ep_order = {ep.id: i for i, ep in enumerate(episodes)}

    # Season nodes + containment.
    for season in db.get_seasons(project_id):
        snode = f"Season:{season.id}"
        _node(snode, "Season", season.id,
              season.title or f"Season {season.season_number}", NODE_KIND_SEASON)
        for ep in db.get_episodes_for_season(season.id):
            enode = ep_node.get(ep.id)
            if enode is None:
                continue
            _node(enode, "Episode", ep.id,
                  ep.title or f"Episode {ep.episode_number}", NODE_KIND_EPISODE)
            _edge(snode, enode, EDGE_SR_CONTAINS)

    # Episode nodes (any not under a season) + A/B/C plotlines + dependency.
    for ep in episodes:
        enode = ep_node[ep.id]
        _node(enode, "Episode", ep.id,
              ep.title or f"Episode {ep.episode_number}", NODE_KIND_EPISODE)
        for pl in db.get_episode_plotlines(ep.id):
            pnode = f"Plotline:{pl.id}"
            _node(pnode, "Plotline", pl.id,
                  f"{pl.type}: {pl.title}" if pl.title else pl.type,
                  NODE_KIND_PLOTLINE)
            _edge(enode, pnode, EDGE_SR_CONTAINS)
    for i in range(len(episodes) - 1):
        _edge(ep_node[episodes[i].id], ep_node[episodes[i + 1].id],
              EDGE_SR_CONTINUES)

    # Arc / mystery nodes + setup / payoff / escalation edges.
    _PAYOFF_EDGE = {
        "resolved": EDGE_SR_RESOLVES,
        "delayed": EDGE_SR_DELAYS,
    }
    for arc in db.get_series_arcs(project_id):
        kind = NODE_KIND_MYSTERY if arc.scope == "mystery" else NODE_KIND_ARC
        anode = f"SeriesArc:{arc.id}"
        _node(anode, "SeriesArc", arc.id, arc.title or f"Arc {arc.id}", kind)
        s_ord = ep_order.get(arc.setup_episode_id)
        p_ord = ep_order.get(arc.payoff_episode_id)
        if arc.setup_episode_id in ep_node:
            _edge(ep_node[arc.setup_episode_id], anode, EDGE_SR_SETS_UP)
        if arc.payoff_episode_id in ep_node:
            _edge(ep_node[arc.payoff_episode_id], anode,
                  _PAYOFF_EDGE.get(arc.status, EDGE_SR_PAYS_OFF))
        # Escalation: episodes strictly between setup and payoff.
        if s_ord is not None and p_ord is not None and p_ord - s_ord > 1:
            for ep in episodes[s_ord + 1:p_ord]:
                _edge(ep_node[ep.id], anode, EDGE_SR_ESCALATES)

    # Character progression / callbacks (echoes) + continuity risk
    # (contradicts) — both derive from PSYKE series memory on characters.
    for entry in db.get_all_psyke_entries(project_id):
        if (entry.entry_type or "").lower() != "character":
            continue
        cnode = f"PSYKE:{entry.id}"
        if cnode not in data.nodes:
            continue
        try:
            mem = db.get_psyke_series_memory(entry.id) or {}
        except Exception:
            mem = {}
        status_map = mem.get("current_status_by_episode")
        flagged = bool((mem.get("continuity_flags") or "").strip())
        if isinstance(status_map, dict):
            for raw_eid in status_map:
                try:
                    eid = int(raw_eid)
                except (TypeError, ValueError):
                    continue
                enode = ep_node.get(eid)
                if enode is None:
                    continue
                _edge(cnode, enode, EDGE_SR_ECHOES)
                if flagged:
                    _edge(cnode, enode, EDGE_SR_CONTRADICTS)
