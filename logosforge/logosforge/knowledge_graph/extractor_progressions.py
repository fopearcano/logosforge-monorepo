"""Native Progressions -> Narrative Knowledge Graph extraction.

Only first-class, non-legacy tracks are projected here.  Designated legacy
compatibility tracks remain owned by :mod:`extractor_psyke`, whose historical
PSYKE-to-scene edge reads those same canonical beats.  Skipping them here is
what prevents one author-authored fact from appearing twice in the graph.

The projection is reference-only and deterministic:

* every native track and bounded beat is a focusable graph node;
* tracks belong to the project and relate to their declared PSYKE subjects;
* beats belong to their track and preserve their explicit order;
* only scene-anchored beats appear in a scene (no guessed links for
  document-block or unanchored beats).
"""

from __future__ import annotations

from logosforge.knowledge_graph import provenance as P
from logosforge.knowledge_graph.extractor_psyke import psyke_node_key
from logosforge.knowledge_graph.models import KGEdge, KGNode, node_key

_MAX_NATIVE_TRACKS = 100
_MAX_NATIVE_BEATS = 400
_UNSET = object()
_DIAGNOSTIC_EVIDENCE_CAP = 5


def progression_track_node_key(track_id: int) -> str:
    return node_key(P.NT_PROGRESSION_TRACK, P.SS_PROGRESSIONS, track_id)


def progression_beat_node_key(beat_id: int) -> str:
    return node_key(P.NT_PROGRESSION_BEAT, P.SS_PROGRESSIONS, beat_id)


def _track_metadata(row) -> dict:
    track = row.track
    coverage = row.coverage
    return {
        "kind": track.kind,
        "sort_order": int(track.sort_order),
        "primary_psyke_entry_id": (
            int(row.primary_entry.id) if row.primary_entry is not None else None
        ),
        "secondary_psyke_entry_id": (
            int(row.secondary_entry.id)
            if row.secondary_entry is not None else None
        ),
        "legacy_compatibility": False,
        "total_beats": int(coverage.total_beats),
        "anchored_beats": int(coverage.anchored_beats),
        "unanchored_beats": int(coverage.unanchored_beats),
        "scene_anchored_beats": int(coverage.scene_anchored_beats),
        "document_anchored_beats": int(coverage.document_anchored_beats),
        "coverage_percent": float(coverage.coverage_percent),
        "coverage_status": coverage.status,
        "out_of_order_beat_ids": [
            int(beat_id) for beat_id in coverage.out_of_order_beat_ids
        ],
    }


def _add_subject_edge(graph, track_key: str, entry, *, role: str, kind: str) -> None:
    if entry is None:
        return
    subject_key = psyke_node_key(entry)
    if subject_key not in graph.nodes:
        return
    graph.add_edge(KGEdge(
        source=track_key,
        target=subject_key,
        edge_type=P.ET_RELATES_TO,
        confidence=P.CONF_CONFIRMED,
        provenance=P.PROV_PROGRESSION_TRACK,
        source_system=P.SS_PROGRESSIONS,
        explanation=f"{kind.title()} progression's {role} subject.",
        metadata={"subject_role": role, "track_kind": kind},
    ))


def _progression_diagnostics(native_rows) -> dict:
    empty_rows = [row for row in native_rows if not row.beats]
    unanchored_rows = [
        row for row in native_rows if row.coverage.unanchored_beats > 0
    ]
    out_of_order_rows = [
        row for row in native_rows if row.coverage.out_of_order_beat_ids
    ]

    def first_track_id(rows) -> int | None:
        return int(rows[0].track.id) if rows else None

    def first_beat_ids(rows, predicate) -> list[int]:
        result: list[int] = []
        for row in rows:
            for beat in row.beats:
                if predicate(row, beat):
                    result.append(int(beat.id))
                    if len(result) >= _DIAGNOSTIC_EVIDENCE_CAP:
                        return result
        return result

    def first_out_of_order_ids(rows) -> list[int]:
        result: list[int] = []
        for row in rows:
            for beat_id in row.coverage.out_of_order_beat_ids:
                result.append(int(beat_id))
                if len(result) >= _DIAGNOSTIC_EVIDENCE_CAP:
                    return result
        return result

    return {
        "native_track_count": len(native_rows),
        "empty": {
            "track_count": len(empty_rows),
            "first_track_id": first_track_id(empty_rows),
            "evidence_track_ids": [
                int(row.track.id)
                for row in empty_rows[:_DIAGNOSTIC_EVIDENCE_CAP]
            ],
        },
        "unanchored": {
            "track_count": len(unanchored_rows),
            "beat_count": sum(
                int(row.coverage.unanchored_beats)
                for row in unanchored_rows
            ),
            "first_track_id": first_track_id(unanchored_rows),
            "evidence_beat_ids": first_beat_ids(
                unanchored_rows,
                lambda _row, beat: beat.anchor_kind == "unanchored",
            ),
        },
        "out_of_order": {
            "track_count": len(out_of_order_rows),
            "beat_count": sum(
                len(row.coverage.out_of_order_beat_ids)
                for row in out_of_order_rows
            ),
            "first_track_id": first_track_id(out_of_order_rows),
            "evidence_beat_ids": first_out_of_order_ids(out_of_order_rows),
        },
    }


def _bounded_track_rows(native_rows, diagnostics: dict):
    """Keep the graph cap while guaranteeing each Radar target is focusable."""
    if len(native_rows) <= _MAX_NATIVE_TRACKS:
        return list(native_rows)
    selected = list(native_rows[:_MAX_NATIVE_TRACKS])
    selected_ids = {int(row.track.id) for row in selected}
    priority_ids = [
        diagnostics[name].get("first_track_id")
        for name in ("out_of_order", "unanchored", "empty")
    ]
    priority_ids = [int(track_id) for track_id in priority_ids if track_id]
    priority_set = set(priority_ids)
    by_id = {int(row.track.id): row for row in native_rows}
    for track_id in priority_ids:
        if track_id in selected_ids:
            continue
        replace_index = next(
            (
                index for index in range(len(selected) - 1, -1, -1)
                if int(selected[index].track.id) not in priority_set
            ),
            None,
        )
        if replace_index is None:
            break
        selected_ids.remove(int(selected[replace_index].track.id))
        selected[replace_index] = by_id[track_id]
        selected_ids.add(track_id)
    canonical_index = {
        int(row.track.id): index for index, row in enumerate(native_rows)
    }
    selected.sort(key=lambda row: canonical_index[int(row.track.id)])
    return selected


def extract_progressions(
    db,
    project_id: int,
    graph,
    *,
    progression_snapshot=_UNSET,
) -> None:
    """Add bounded native Progressions references to ``graph`` in place."""
    if progression_snapshot is _UNSET:
        try:
            snapshot = db.read_progression_snapshot(project_id)
        except Exception:
            if P.SS_PROGRESSIONS not in graph.unavailable:
                graph.unavailable.append(P.SS_PROGRESSIONS)
            return
    else:
        snapshot = progression_snapshot
    if snapshot is None:
        return

    all_native_rows = [
        row for row in snapshot.tracks
        if row.track.legacy_psyke_entry_id is None
    ]
    diagnostics = _progression_diagnostics(all_native_rows)
    graph.progression_diagnostics = diagnostics
    if len(all_native_rows) > _MAX_NATIVE_TRACKS:
        graph.warnings.append(
            f"Native Progressions extraction capped at {_MAX_NATIVE_TRACKS} tracks."
        )
    native_rows = _bounded_track_rows(all_native_rows, diagnostics)

    project_key = node_key(P.NT_PROJECT, "project", project_id)
    emitted_beats = 0
    beats_capped = False

    for row in native_rows:
        track = row.track
        track_id = int(track.id)
        track_key = progression_track_node_key(track_id)
        graph.add_node(KGNode(
            key=track_key,
            node_type=P.NT_PROGRESSION_TRACK,
            source_type=P.SS_PROGRESSIONS,
            source_id=str(track_id),
            label=track.title,
            summary=(track.description or "")[:160],
            metadata=_track_metadata(row),
        ))
        if project_key in graph.nodes:
            graph.add_edge(KGEdge(
                source=track_key,
                target=project_key,
                edge_type=P.ET_BELONGS_TO,
                confidence=P.CONF_CONFIRMED,
                provenance=P.PROV_PROGRESSION_TRACK,
                source_system=P.SS_PROGRESSIONS,
                explanation="Native progression track belongs to this project.",
                metadata={"track_kind": track.kind},
            ))
        _add_subject_edge(
            graph, track_key, row.primary_entry,
            role="primary", kind=track.kind,
        )
        _add_subject_edge(
            graph, track_key, row.secondary_entry,
            role="secondary", kind=track.kind,
        )

        previous_beat_key: str | None = None
        for beat in row.beats:
            if emitted_beats >= _MAX_NATIVE_BEATS:
                beats_capped = True
                break
            emitted_beats += 1
            beat_id = int(beat.id)
            beat_key = progression_beat_node_key(beat_id)
            graph.add_node(KGNode(
                key=beat_key,
                node_type=P.NT_PROGRESSION_BEAT,
                source_type=P.SS_PROGRESSIONS,
                source_id=str(beat_id),
                label=f"Beat {int(beat.sort_order) + 1}: {beat.text[:96]}",
                summary=beat.text[:160],
                metadata={
                    "track_id": track_id,
                    "track_kind": track.kind,
                    "sort_order": int(beat.sort_order),
                    "anchor_kind": beat.anchor_kind,
                    "scene_id": (
                        int(beat.scene_id) if beat.scene_id is not None else None
                    ),
                    "anchor_ref": beat.anchor_ref,
                    "anchor_label": beat.anchor_label,
                },
            ))
            graph.add_edge(KGEdge(
                source=beat_key,
                target=track_key,
                edge_type=P.ET_BELONGS_TO,
                confidence=P.CONF_CONFIRMED,
                provenance=P.PROV_PROGRESSION_BEAT,
                source_system=P.SS_PROGRESSIONS,
                explanation="Progression beat belongs to this ordered track.",
                metadata={
                    "track_id": track_id,
                    "track_kind": track.kind,
                    "sort_order": int(beat.sort_order),
                },
            ))
            if previous_beat_key is not None:
                graph.add_edge(KGEdge(
                    source=previous_beat_key,
                    target=beat_key,
                    edge_type=P.ET_PRECEDES,
                    confidence=P.CONF_CONFIRMED,
                    provenance=P.PROV_PROGRESSION_BEAT,
                    source_system=P.SS_PROGRESSIONS,
                    explanation="Explicit order within the progression track.",
                    metadata={"track_id": track_id},
                ))
            previous_beat_key = beat_key

            if beat.anchor_kind == "scene" and beat.scene_id is not None:
                scene_key = node_key(P.NT_SCENE, "scene", int(beat.scene_id))
                if scene_key in graph.nodes:
                    graph.add_edge(KGEdge(
                        source=beat_key,
                        target=scene_key,
                        edge_type=P.ET_ADVANCES_IN,
                        confidence=P.CONF_CONFIRMED,
                        provenance=P.PROV_PROGRESSION_BEAT,
                        source_system=P.SS_PROGRESSIONS,
                        explanation="Progression beat is explicitly anchored to this scene.",
                        metadata={
                            "track_id": track_id,
                            "track_kind": track.kind,
                            "beat_id": beat_id,
                        },
                    ))
                    # A typed progression subject changing state at an explicit
                    # scene is a direct, confirmed PSYKE-to-scene fact.  Keep
                    # this derived edge in addition to the track/beat path so
                    # scene diagnostics do not report a false missing-PSYKE
                    # link.  Subjectless story/custom tracks add no such edge.
                    for role, entry in (
                        ("primary", row.primary_entry),
                        ("secondary", row.secondary_entry),
                    ):
                        if entry is None:
                            continue
                        subject_key = psyke_node_key(entry)
                        if subject_key not in graph.nodes:
                            continue
                        graph.add_edge(KGEdge(
                            source=subject_key,
                            target=scene_key,
                            edge_type=P.ET_ADVANCES_IN,
                            confidence=P.CONF_CONFIRMED,
                            provenance=P.PROV_PROGRESSION_BEAT,
                            source_system=P.SS_PROGRESSIONS,
                            explanation=(
                                "Progression subject has an explicit state "
                                "change anchored to this scene."
                            ),
                            metadata={
                                "track_id": track_id,
                                "track_kind": track.kind,
                                "beat_id": beat_id,
                                "subject_role": role,
                            },
                        ))

    if beats_capped:
        graph.warnings.append(
            f"Native Progressions extraction capped at {_MAX_NATIVE_BEATS} beats."
        )
