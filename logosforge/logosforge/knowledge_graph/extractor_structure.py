"""Structure → Knowledge Graph extraction (Phase 10P).

Outline (acts/chapters), Manuscript (scenes, order), Plot (plotline blocks),
Timeline (scene order), and the existing Graph section (link graph + confirmed
StoryLinks). Explicit membership is ``confirmed``; positional adjacency is
``likely`` (never fake causality).
"""

from __future__ import annotations

from logosforge.knowledge_graph import provenance as P
from logosforge.knowledge_graph.models import KGEdge, KGNode, node_key

_MAX_SCENES = 2000
_MAX_OUTLINE = 1000


def _scene_summary(scene) -> str:
    return (getattr(scene, "summary", "") or getattr(scene, "synopsis", "")
            or "")[:160]


def extract_structure(db, project_id: int, graph) -> None:
    project_key = node_key(P.NT_PROJECT, "project", project_id)
    try:
        project = db.get_project_by_id(project_id)
        title = getattr(project, "title", "") or "Project"
    except Exception:
        title = "Project"
    graph.add_node(KGNode(key=project_key, node_type=P.NT_PROJECT,
                          source_type="project", source_id=str(project_id),
                          label=title))

    try:
        scenes = db.get_all_scenes(project_id)
    except Exception:
        scenes = []
        graph.unavailable.append("manuscript")
    if len(scenes) > _MAX_SCENES:
        graph.warnings.append(f"Scene count {len(scenes)} exceeds cap; truncated.")
        scenes = scenes[:_MAX_SCENES]

    act_keys: dict[str, str] = {}
    chapter_keys: dict[str, str] = {}
    plot_keys: dict[str, str] = {}

    def _act_key(name: str) -> str:
        k = act_keys.get(name)
        if k is None:
            k = node_key(P.NT_ACT, "act", name)
            act_keys[name] = k
            graph.add_node(KGNode(key=k, node_type=P.NT_ACT, source_type="act",
                                  source_id=name, label=name))
            graph.add_edge(KGEdge(
                source=project_key, target=k, edge_type=P.ET_CONTAINS,
                confidence=P.CONF_CONFIRMED, provenance=P.PROV_ACT_MEMBERSHIP,
                source_system=P.SS_STRUCTURE, explanation="Act of the project."))
        return k

    def _chapter_key(name: str, act: str) -> str:
        k = chapter_keys.get(name)
        if k is None:
            k = node_key(P.NT_CHAPTER, "chapter", name)
            chapter_keys[name] = k
            graph.add_node(KGNode(key=k, node_type=P.NT_CHAPTER,
                                  source_type="chapter", source_id=name, label=name))
            parent = _act_key(act) if act else project_key
            graph.add_edge(KGEdge(
                source=parent, target=k, edge_type=P.ET_CONTAINS,
                confidence=P.CONF_CONFIRMED, provenance=P.PROV_CHAPTER_MEMBERSHIP,
                source_system=P.SS_STRUCTURE, explanation="Chapter membership."))
        return k

    def _plot_key(name: str) -> str:
        k = plot_keys.get(name)
        if k is None:
            k = node_key(P.NT_PLOT_BLOCK, "plot", name)
            plot_keys[name] = k
            graph.add_node(KGNode(key=k, node_type=P.NT_PLOT_BLOCK,
                                  source_type="plot", source_id=name, label=name))
        return k

    prev_scene_key = None
    for scene in scenes:
        skey = node_key(P.NT_SCENE, "scene", scene.id)
        graph.add_node(KGNode(
            key=skey, node_type=P.NT_SCENE, source_type="scene",
            source_id=str(scene.id), label=getattr(scene, "title", "") or "",
            summary=_scene_summary(scene),
            metadata={"chapter": getattr(scene, "chapter", "") or "",
                      "act": getattr(scene, "act", "") or "",
                      "plotline": getattr(scene, "plotline", "") or ""}))

        chapter = (getattr(scene, "chapter", "") or "").strip()
        act = (getattr(scene, "act", "") or "").strip()
        if chapter:
            graph.add_edge(KGEdge(
                source=_chapter_key(chapter, act), target=skey,
                edge_type=P.ET_CONTAINS, confidence=P.CONF_CONFIRMED,
                provenance=P.PROV_CHAPTER_MEMBERSHIP, source_system=P.SS_OUTLINE,
                explanation="Scene belongs to this chapter."))
        elif act:
            graph.add_edge(KGEdge(
                source=_act_key(act), target=skey, edge_type=P.ET_CONTAINS,
                confidence=P.CONF_CONFIRMED, provenance=P.PROV_ACT_MEMBERSHIP,
                source_system=P.SS_OUTLINE, explanation="Scene belongs to this act."))
        else:
            graph.add_edge(KGEdge(
                source=project_key, target=skey, edge_type=P.ET_CONTAINS,
                confidence=P.CONF_LIKELY, provenance=P.PROV_OUTLINE_STRUCTURE,
                source_system=P.SS_STRUCTURE,
                explanation="Scene not assigned to a chapter/act."))

        plotline = (getattr(scene, "plotline", "") or "").strip()
        if plotline:
            graph.add_edge(KGEdge(
                source=_plot_key(plotline), target=skey, edge_type=P.ET_CONTAINS,
                confidence=P.CONF_CONFIRMED, provenance=P.PROV_PLOT_MEMBERSHIP,
                source_system=P.SS_PLOT, explanation="Scene in this plot block."))

        # Scene order = likely precedence (a timeline_event facet), not causality.
        if prev_scene_key is not None:
            graph.add_edge(KGEdge(
                source=prev_scene_key, target=skey, edge_type=P.ET_PRECEDES,
                confidence=P.CONF_LIKELY, provenance=P.PROV_SCENE_ORDER,
                source_system=P.SS_TIMELINE,
                explanation="Manuscript order — sequential, not causal."))
        prev_scene_key = skey

        # setup_payoff_links CSV of related scene ids = confirmed dependency.
        raw = (getattr(scene, "setup_payoff_links", "") or "").strip()
        for tok in raw.split(","):
            tok = tok.strip()
            if tok.isdigit():
                graph.add_edge(KGEdge(
                    source=skey, target=node_key(P.NT_SCENE, "scene", int(tok)),
                    edge_type=P.ET_DEPENDS_ON, confidence=P.CONF_CONFIRMED,
                    provenance=P.PROV_SETUP_PAYOFF, source_system=P.SS_STRUCTURE,
                    explanation="Explicit setup/payoff scene link."))

    # Outline nodes (tree) — structural skeleton.
    try:
        outline = db.get_outline_nodes(project_id)[:_MAX_OUTLINE]
    except Exception:
        outline = []
    onode_keys = {o.id: node_key(P.NT_ACT, "outline", o.id) for o in outline}
    for o in outline:
        k = onode_keys[o.id]
        graph.add_node(KGNode(key=k, node_type=P.NT_CHAPTER, source_type="outline",
                              source_id=str(o.id), label=getattr(o, "title", "") or "",
                              summary=(getattr(o, "description", "") or "")[:160]))
        parent = onode_keys.get(getattr(o, "parent_id", None), project_key)
        graph.add_edge(KGEdge(
            source=parent, target=k, edge_type=P.ET_CONTAINS,
            confidence=P.CONF_CONFIRMED, provenance=P.PROV_OUTLINE_STRUCTURE,
            source_system=P.SS_OUTLINE, explanation="Outline structure."))

    _extract_graph_section(db, project_id, graph)


def _extract_graph_section(db, project_id: int, graph) -> None:
    """Import the existing Graph section: link graph (likely) + StoryLinks
    (confirmed/user-created)."""
    try:
        nodes, edges = db.build_link_graph(project_id)
    except Exception:
        nodes, edges = [], []
    # The link graph uses [[wikilink]] references between scenes/notes — likely.
    label_to_scene = {}
    try:
        for s in db.get_all_scenes(project_id):
            label_to_scene[(getattr(s, "title", "") or "").lower()] = s.id
    except Exception:
        pass
    for (src_label, tgt_label) in edges:
        sid = label_to_scene.get(str(src_label).lower())
        tid = label_to_scene.get(str(tgt_label).lower())
        if sid and tid:
            graph.add_edge(KGEdge(
                source=node_key(P.NT_SCENE, "scene", sid),
                target=node_key(P.NT_SCENE, "scene", tid),
                edge_type=P.ET_RELATES_TO, confidence=P.CONF_LIKELY,
                provenance=P.PROV_NOTE_WIKILINK, source_system=P.SS_GRAPH,
                explanation="Wikilink reference in the link graph."))

    # Confirmed StoryLinks (user-confirmed screenplay story links).
    try:
        from sqlmodel import Session, select
        from logosforge.models.models import StoryLink
        with Session(db._engine) as session:
            stmt = select(StoryLink).where(StoryLink.project_id == project_id,
                                           StoryLink.status == "confirmed")
            links = list(session.exec(stmt).all())
    except Exception:
        links = []
    for ln in links:
        s_sid = getattr(ln, "source_scene_id", None)
        t_sid = getattr(ln, "target_scene_id", None)
        if s_sid and t_sid:
            graph.add_edge(KGEdge(
                source=node_key(P.NT_SCENE, "scene", s_sid),
                target=node_key(P.NT_SCENE, "scene", t_sid),
                edge_type=P.ET_SETS_UP, confidence=P.CONF_CONFIRMED,
                provenance=P.PROV_STORY_LINK, source_system=P.SS_GRAPH,
                is_user_confirmed=True,
                explanation=f"Confirmed story link ({getattr(ln, 'link_type', '') or 'link'})."))
