"""PSYKE → Knowledge Graph extraction (Phase 10P).

Read-only. Reuses the existing PSYKE matching semantics
(``revision_intelligence.psyke_impact``) rather than re-implementing a scanner.
No PSYKE mutation. Global entries are linked to the project, not flooded across
every scene.
"""

from __future__ import annotations

from logosforge.knowledge_graph import provenance as P
from logosforge.knowledge_graph.models import KGEdge, KGNode, node_key

_MAX_RELATIONS_PER_ENTRY = 12
_MAX_SCENE_MENTIONS = 400  # global cap on text-match mention edges
_UNSET = object()


def _entry_node_type(entry) -> str:
    et = (getattr(entry, "entry_type", "") or "other").lower()
    return P.PSYKE_TYPE_TO_NODE.get(et, P.NT_PSYKE_ENTRY)


def psyke_node_key(entry) -> str:
    return node_key(_entry_node_type(entry), "psyke", entry.id)


def extract_psyke(
    db,
    project_id: int,
    graph,
    *,
    progression_snapshot=_UNSET,
) -> None:
    try:
        entries = db.get_all_psyke_entries(project_id)
    except Exception:
        graph.unavailable.append("psyke")
        return

    project_key = node_key(P.NT_PROJECT, "project", project_id)
    by_id = {}
    for e in entries:
        key = psyke_node_key(e)
        by_id[e.id] = key
        graph.add_node(KGNode(
            key=key, node_type=_entry_node_type(e), source_type="psyke",
            source_id=str(e.id), label=getattr(e, "name", "") or "",
            summary=(getattr(e, "notes", "") or "")[:160],
            metadata={"is_global": bool(getattr(e, "is_global", False)),
                      "entry_type": (getattr(e, "entry_type", "") or "other")},
        ))
        # Global entries attach to the project (confirmed), not to every scene.
        if getattr(e, "is_global", False):
            graph.add_edge(KGEdge(
                source=key, target=project_key, edge_type=P.ET_BELONGS_TO,
                confidence=P.CONF_CONFIRMED, provenance=P.PROV_GLOBAL_THEME,
                source_system=P.SS_PSYKE,
                explanation="Global PSYKE entry — applies project-wide."))

    # Explicit, typed PSYKE relations = confirmed (capped per entry).
    for e in entries:
        try:
            related = db.get_typed_related_psyke_entries(e.id)
        except Exception:
            related = []
        for rel_entry, rel_type in related[:_MAX_RELATIONS_PER_ENTRY]:
            tgt = by_id.get(rel_entry.id)
            if not tgt:
                continue
            graph.add_edge(KGEdge(
                source=by_id[e.id], target=tgt, edge_type=P.ET_RELATES_TO,
                confidence=P.CONF_CONFIRMED, provenance=P.PROV_PSYKE_RELATION,
                source_system=P.SS_PSYKE,
                explanation=f"Explicit PSYKE relation ({rel_type or 'related'})."))

    # Scene text-match mentions = confirmed (direct name/alias hit), capped.
    try:
        from logosforge.revision_intelligence.psyke_impact import _mentioned
        scenes = db.get_all_scenes(project_id)
    except Exception:
        scenes = []
    mention_count = 0
    for scene in scenes:
        if mention_count >= _MAX_SCENE_MENTIONS:
            graph.warnings.append("PSYKE mention scan capped.")
            break
        text_low = " ".join([
            getattr(scene, f, "") or "" for f in
            ("content", "summary", "synopsis", "goal", "conflict", "outcome")
        ]).lower()
        if not text_low.strip():
            continue
        scene_key = node_key(P.NT_SCENE, "scene", scene.id)
        for e in entries:
            if getattr(e, "is_global", False):
                continue  # don't flood scenes with global entries
            if mention_count >= _MAX_SCENE_MENTIONS:
                break
            try:
                hit = _mentioned(e, text_low)
            except Exception:
                hit = False
            if hit:
                graph.add_edge(KGEdge(
                    source=by_id[e.id], target=scene_key,
                    edge_type=P.ET_APPEARS_IN, confidence=P.CONF_CONFIRMED,
                    provenance=P.PROV_SCENE_TEXT_MATCH, source_system=P.SS_PSYKE,
                    explanation="Name/alias appears in the scene text."))
                mention_count += 1

    # Designated legacy compatibility tracks retain the historical direct
    # PSYKE -> scene projection.  The builder passes the SAME canonical snapshot
    # to the native extractor, avoiding mixed-revision reads and duplicate
    # evidence.  A direct extractor call still reads one snapshot for backwards
    # compatibility with focused unit tests.
    if progression_snapshot is _UNSET:
        try:
            progression_snapshot = db.read_progression_snapshot(project_id)
        except Exception:
            progression_snapshot = None
            if P.SS_PROGRESSIONS not in graph.unavailable:
                graph.unavailable.append(P.SS_PROGRESSIONS)
    scene_ids = {int(s.id) for s in scenes}
    if progression_snapshot is not None:
        for row in progression_snapshot.tracks:
            track = row.track
            legacy_entry_id = track.legacy_psyke_entry_id
            if legacy_entry_id is None:
                continue
            source_key = by_id.get(int(legacy_entry_id))
            if source_key is None:
                continue
            for beat in row.beats[:_MAX_RELATIONS_PER_ENTRY]:
                if beat.anchor_kind != "scene" or beat.scene_id is None:
                    continue
                sid = int(beat.scene_id)
                if sid not in scene_ids:
                    continue
                graph.add_edge(KGEdge(
                    source=source_key,
                    target=node_key(P.NT_SCENE, "scene", sid),
                    edge_type=P.ET_APPEARS_IN,
                    confidence=P.CONF_CONFIRMED,
                    provenance=P.PROV_PSYKE_PROGRESSION,
                    source_system=P.SS_PSYKE,
                    explanation="PSYKE progression references this scene.",
                    metadata={
                        "track_id": int(track.id),
                        "beat_id": int(beat.id),
                        "legacy_compatibility": True,
                    },
                ))
