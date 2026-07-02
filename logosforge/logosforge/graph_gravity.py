"""Story Gravity — narrative-importance weights for graph nodes.

Each visible node gets three orthogonal weights (narrative / thematic /
structural), each in [0..1].  Their weighted sum drives:

  - size: high-gravity nodes are drawn larger
  - glow: a translucent halo appears above a threshold
  - centrality: in circular layouts, high-gravity nodes sit closer
    to the centre

Inputs (per node kind):

  Character  scene-participation count → narrative + structural
  Place      scene-participation count → narrative
  Scene      entity density + position (opening / midpoint / climax)
             + Controlling Idea alignment if any → narrative + structural
             + thematic
  PSYKE      relation + progression count → narrative;
             theme-typed gets 0.8 base thematic (1.0 if it is the
             Controlling Idea theme entry); other entries inherit
             thematic weight from the number of theme-typed neighbours
  Act        constant structural baseline (Acts anchor the structure)
  Wavefunction / Branch (Quantum mode)
             constant baselines; refined elsewhere if score data exists

The system is provider-neutral — it only reads the DB and (if present)
the Controlling Idea PSYKE entry.  Missing data is silently skipped.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from logosforge.db import Database
    from logosforge.graph_data import GraphData


GRAVITY_GLOW_THRESHOLD = 0.55


@dataclass
class StoryGravity:
    """Three-component narrative-importance weight for a single node."""

    narrative: float = 0.0
    thematic: float = 0.0
    structural: float = 0.0

    @property
    def total(self) -> float:
        v = 0.45 * self.narrative + 0.35 * self.thematic + 0.2 * self.structural
        return min(1.0, max(0.0, v))


def compute_gravity(
    db: "Database", project_id: int, data: "GraphData",
    *, screenplay_mode: bool = False, graphic_novel_mode: bool = False,
) -> dict[str, StoryGravity]:
    """Compute Story Gravity for every node in *data*."""
    result: dict[str, StoryGravity] = {}
    if not data or not data.nodes:
        return result

    # Graphic-novel node weights: pages by panel count + position, motifs by
    # recurrence (degree), objects by appearance count. Computed once here so
    # important motifs/pages render larger and pull toward centre.
    gn_page_panels: dict[str, int] = {}
    gn_max_panels = 1
    if graphic_novel_mode:
        for nid, node in data.nodes.items():
            if getattr(node, "etype", "") == "GNPage":
                gn_page_panels[nid] = len(data.adjacency.get(nid, set()))
        gn_max_panels = max(gn_page_panels.values(), default=1) or 1

    scenes = db.get_all_scenes(project_id)
    n_scenes = len(scenes)
    scene_index = {s.id: i for i, s in enumerate(scenes)}
    scene_map = {s.id: s for s in scenes}
    max_duration = 1
    if screenplay_mode:
        _durs = [getattr(s, "estimated_duration_minutes", 0) or 0 for s in scenes]
        max_duration = max(_durs, default=1) or 1

    char_scene_count: dict[int, int] = {}
    place_scene_count: dict[int, int] = {}
    scene_entity_count: dict[int, int] = {}
    for s in scenes:
        cids = db.get_scene_character_ids(s.id)
        pids = db.get_scene_place_ids(s.id)
        scene_entity_count[s.id] = len(cids) + len(pids)
        for cid in cids:
            char_scene_count[cid] = char_scene_count.get(cid, 0) + 1
        for pid in pids:
            place_scene_count[pid] = place_scene_count.get(pid, 0) + 1

    max_char_scenes = max(char_scene_count.values(), default=1) or 1
    max_place_scenes = max(place_scene_count.values(), default=1) or 1
    max_scene_entities = max(scene_entity_count.values(), default=1) or 1

    psyke_relations_count: dict[int, int] = {}
    psyke_progressions_count: dict[int, int] = {}
    psyke_theme_neighbours: dict[int, int] = {}
    for n in data.nodes.values():
        if n.etype == "PSYKE":
            rels = db.get_related_psyke_entries(n.entity_id)
            psyke_relations_count[n.entity_id] = len(rels)
            psyke_progressions_count[n.entity_id] = len(
                db.get_psyke_progressions(n.entity_id),
            )
            psyke_theme_neighbours[n.entity_id] = sum(
                1 for r in rels if (r.entry_type or "").lower() == "theme"
            )
    max_psyke_conn = max(
        (psyke_relations_count[i] + psyke_progressions_count[i]
         for i in psyke_relations_count),
        default=1,
    ) or 1

    n_themes = max(
        sum(
            1 for n in data.nodes.values()
            if n.etype == "PSYKE" and (n.subtype or "").lower() == "theme"
        ),
        1,
    )

    ci_scene_alignment: dict[str, str] = {}
    ci_psyke_alignment: dict[str, str] = {}
    ci_theme_entry_id: int | None = None
    try:
        from logosforge.controlling_idea import load as load_ci
        ci = load_ci(db, project_id)
        if ci.is_defined():
            ci_scene_alignment = dict(ci.scene_alignment)
            ci_psyke_alignment = dict(ci.psyke_alignment)
            ci_theme_entry_id = ci.theme_psyke_entry_id
    except Exception:
        pass

    for nid, node in data.nodes.items():
        g = StoryGravity()

        if node.etype == "Character":
            cnt = char_scene_count.get(node.entity_id, 0)
            g.narrative = cnt / max_char_scenes
            g.structural = cnt / max_char_scenes

        elif node.etype == "Place":
            cnt = place_scene_count.get(node.entity_id, 0)
            g.narrative = cnt / max_place_scenes
            g.structural = 0.3 * (cnt / max_place_scenes)

        elif node.etype == "Scene":
            ent = scene_entity_count.get(node.entity_id, 0)
            g.narrative = ent / max_scene_entities
            idx = scene_index.get(node.entity_id, -1)
            if idx >= 0 and n_scenes:
                g.structural = _scene_structural_weight(idx, n_scenes)
            if str(node.entity_id) in ci_scene_alignment:
                g.thematic = max(g.thematic, 0.7)
            if screenplay_mode:
                scene = scene_map.get(node.entity_id)
                if scene:
                    if (getattr(scene, "setup_payoff_links", "") or "").strip():
                        g.structural = max(g.structural, 0.7)
                    dur = getattr(scene, "estimated_duration_minutes", 0) or 0
                    if dur > 0:
                        g.narrative = max(g.narrative, dur / max_duration)

        elif node.etype == "PSYKE":
            sub = (node.subtype or "").lower()
            conn = (
                psyke_relations_count.get(node.entity_id, 0)
                + psyke_progressions_count.get(node.entity_id, 0)
            )
            g.narrative = conn / max_psyke_conn
            if sub == "theme":
                g.thematic = 0.8
                if (ci_theme_entry_id is not None
                        and node.entity_id == ci_theme_entry_id):
                    g.thematic = 1.0
                    g.structural = max(g.structural, 0.8)
            else:
                tc = psyke_theme_neighbours.get(node.entity_id, 0)
                if tc:
                    g.thematic = min(1.0, tc / n_themes)
                if str(node.entity_id) in ci_psyke_alignment:
                    g.thematic = max(g.thematic, 0.6)

        elif node.etype == "Act":
            g.structural = 0.7

        elif node.etype == "Wavefunction":
            g.structural = 0.7

        elif node.etype == "Branch":
            g.structural = 0.5

        elif node.etype == "GNPage":
            # Denser pages (more panels) and recurrence hubs weigh more.
            cnt = gn_page_panels.get(nid, 0)
            g.narrative = cnt / gn_max_panels
            g.structural = 0.3 + 0.5 * (cnt / gn_max_panels)

        elif node.etype == "GNMotif":
            # Recurrence = thematic weight; degree counts pages it touches.
            deg = len(data.adjacency.get(nid, set()))
            g.thematic = min(1.0, deg / 4.0)
            g.narrative = min(1.0, deg / 6.0)

        elif node.etype == "GNObject":
            deg = len(data.adjacency.get(nid, set()))
            g.narrative = min(1.0, deg / 4.0)
            g.structural = min(0.6, 0.2 * deg)

        elif node.etype == "GNPanel":
            g.structural = 0.2

        # -- Stage --
        elif node.etype == "Cue":
            # Staging cues are technical/structural anchors (leaf nodes).
            g.structural = 0.25

        elif node.etype == "Offstage":
            # Off-stage events carry narrative weight + tie to who knows of them.
            deg = len(data.adjacency.get(nid, set()))
            g.narrative = min(1.0, deg / 4.0)
            g.structural = 0.3

        # -- Series --
        elif node.etype == "Season":
            # A season is a top-level structural container (like an Act).
            g.structural = 0.7

        elif node.etype == "Episode":
            # Episodes weigh by connectivity (plotlines, arcs, neighbouring eps).
            deg = len(data.adjacency.get(nid, set()))
            g.narrative = min(1.0, deg / 6.0)
            g.structural = 0.5

        elif node.etype == "SeriesArc":
            # Arcs / mysteries are the thematic + setup-payoff spine; more
            # episodes spanned (escalation) = heavier.
            deg = len(data.adjacency.get(nid, set()))
            g.thematic = 0.6
            g.structural = min(1.0, 0.4 + 0.15 * deg)

        elif node.etype == "Plotline":
            # A/B/C threads — a modest structural weight.
            g.structural = 0.4

        result[nid] = g

    return result


def _scene_structural_weight(idx: int, total: int) -> float:
    """Higher near opening / midpoint / climax (final scene)."""
    if total <= 1:
        return 0.9
    pos = idx / (total - 1)
    if pos <= 0.05:
        return 0.85
    if pos >= 0.92:
        return 1.0
    if 0.45 <= pos <= 0.55:
        return 0.95
    if 0.20 <= pos <= 0.30:
        return 0.55
    if 0.70 <= pos <= 0.80:
        return 0.70
    return 0.3


def gravity_radius_multiplier(g: StoryGravity) -> float:
    """Scale factor for the node radius — 1.0 = unchanged, 1.6 = +60 %."""
    return 1.0 + 0.6 * g.total


def gravity_glow_alpha(g: StoryGravity) -> float:
    """Opacity for the gravity halo; 0 means no glow."""
    if g.total < GRAVITY_GLOW_THRESHOLD:
        return 0.0
    return min(0.6, 0.2 + 0.6 * (g.total - GRAVITY_GLOW_THRESHOLD))


def gravity_centrality_pull(g: StoryGravity) -> float:
    """Layout-radius multiplier: 1.0 = unchanged, 0.5 = pulled toward centre."""
    return max(0.5, 1.0 - 0.5 * g.total)
