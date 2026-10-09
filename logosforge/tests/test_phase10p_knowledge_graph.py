"""Phase 10P — Narrative Knowledge Graph Consolidation."""

from __future__ import annotations

import warnings
from types import SimpleNamespace

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
from logosforge.knowledge_graph.builder import KnowledgeGraphResult
from logosforge.knowledge_graph.extractor_revision import extract_revision
from logosforge.knowledge_graph.extractor_progressions import extract_progressions
from logosforge.knowledge_graph.extractor_structure import extract_structure
from logosforge.knowledge_graph.models import KGEdge, KGNode, KnowledgeGraph
from logosforge.knowledge_graph import scoring


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


def _progression_command(db, project_id: int, kind: str, **fields):
    snapshot = db.read_progression_snapshot(project_id)
    assert snapshot is not None
    return db.execute_progression_command(
        project_id,
        kind=kind,
        expected_revision=snapshot.revision,
        **fields,
    )


def test_capped_structure_flow_metadata_uses_full_manuscript_total():
    class _StructureDb:
        def __init__(self):
            self.scenes = [
                SimpleNamespace(id=index + 1, title=f"Scene {index + 1}", act="")
                for index in range(2001)
            ]

        def get_project_by_id(self, _project_id):
            return SimpleNamespace(title="Capped story")

        def get_all_scenes(self, _project_id):
            return self.scenes

        def get_outline_nodes(self, _project_id):
            return []

        def build_link_graph(self, _project_id):
            return [], []

    graph = KnowledgeGraph(project_id=7)
    extract_structure(_StructureDb(), 7, graph)
    flow = [edge for edge in graph.edges if edge.edge_type == P.ET_PRECEDES]

    assert len(flow) == 1999
    assert flow[0].metadata["story_order_total"] == 2001
    assert flow[-1].metadata["story_order_total"] == 2001
    assert flow[-1].metadata["story_order_index"] == 1998


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


def test_psyke_progression_scene_id_creates_confirmed_graph_edge():
    db, pid, aid, _bid, _s1, _s2 = _project()
    quiet_scene = db.create_scene(pid, "Quiet", content="No names here.")
    db.create_psyke_progression(aid, "Arc turns here", scene_id=quiet_scene.id)
    graph = build_knowledge_graph(db, pid).graph
    expected_source = node_key(P.NT_CHARACTER, "psyke", aid)
    expected_target = node_key(P.NT_SCENE, "scene", quiet_scene.id)
    assert any(
        edge.source == expected_source
        and edge.target == expected_target
        and edge.provenance == P.PROV_PSYKE_PROGRESSION
        for edge in graph.edges
    )


def test_native_progression_tracks_project_typed_traceable_graph_evidence():
    db = Database()
    project = db.create_project("Native arcs", narrative_engine="novel")
    first = db.create_scene(project.id, "Opening")
    second = db.create_scene(project.id, "Turn")
    alice = db.create_psyke_entry(project.id, "Alice", "character")
    bob = db.create_psyke_entry(project.id, "Bob", "character")
    theme = db.create_psyke_entry(project.id, "Mercy", "theme")
    place = db.create_psyke_entry(project.id, "Citadel", "place")

    specs = [
        ("story", "Story arc", None, None),
        ("character", "Alice arc", alice.id, None),
        ("relationship", "Alice and Bob", alice.id, bob.id),
        ("theme", "Mercy arc", theme.id, None),
        ("world", "Citadel arc", place.id, None),
        ("custom", "Weather arc", None, None),
    ]
    track_ids = {}
    for kind, title, primary_id, secondary_id in specs:
        fields = {"track_kind": kind, "title": title}
        if primary_id is not None:
            fields["primary_psyke_entry_id"] = primary_id
        if secondary_id is not None:
            fields["secondary_psyke_entry_id"] = secondary_id
        result = _progression_command(
            db, project.id, "create_track", **fields,
        )
        track_ids[kind] = result.created_track_id

    story_first = _progression_command(
        db, project.id, "create_beat",
        track_id=track_ids["story"], text="Promise",
        anchor_kind="scene", scene_id=first.id,
    ).created_beat_id
    story_second = _progression_command(
        db, project.id, "create_beat",
        track_id=track_ids["story"], text="Turn",
        anchor_kind="scene", scene_id=second.id,
    ).created_beat_id
    character_beat = _progression_command(
        db, project.id, "create_beat",
        track_id=track_ids["character"], text="Alice doubts herself",
        anchor_kind="unanchored",
    ).created_beat_id
    relationship_beat = _progression_command(
        db, project.id, "create_beat",
        track_id=track_ids["relationship"], text="They make a pact",
        anchor_kind="document_block", anchor_ref="drafter-pact",
        anchor_label="Pact draft",
    ).created_beat_id

    graph = build_knowledge_graph(db, project.id).graph
    track_nodes = graph.nodes_of_type(P.NT_PROGRESSION_TRACK)
    beat_nodes = graph.nodes_of_type(P.NT_PROGRESSION_BEAT)
    assert {node.metadata["kind"] for node in track_nodes} == {
        "story", "character", "relationship", "theme", "world", "custom",
    }
    assert {int(node.source_id) for node in beat_nodes} == {
        story_first, story_second, character_beat, relationship_beat,
    }
    assert all(node.source_type == P.SS_PROGRESSIONS for node in track_nodes)
    assert all(node.source_type == P.SS_PROGRESSIONS for node in beat_nodes)

    character_track_key = node_key(
        P.NT_PROGRESSION_TRACK, P.SS_PROGRESSIONS, track_ids["character"],
    )
    relationship_track_key = node_key(
        P.NT_PROGRESSION_TRACK, P.SS_PROGRESSIONS,
        track_ids["relationship"],
    )
    subject_edges = [
        edge for edge in graph.edges
        if edge.source_system == P.SS_PROGRESSIONS
        and edge.edge_type == P.ET_RELATES_TO
    ]
    assert {
        (edge.source, edge.target, edge.metadata["subject_role"])
        for edge in subject_edges
    } >= {
        (
            character_track_key,
            node_key(P.NT_CHARACTER, "psyke", alice.id),
            "primary",
        ),
        (
            relationship_track_key,
            node_key(P.NT_CHARACTER, "psyke", alice.id),
            "primary",
        ),
        (
            relationship_track_key,
            node_key(P.NT_CHARACTER, "psyke", bob.id),
            "secondary",
        ),
    }

    first_beat_key = node_key(
        P.NT_PROGRESSION_BEAT, P.SS_PROGRESSIONS, story_first,
    )
    second_beat_key = node_key(
        P.NT_PROGRESSION_BEAT, P.SS_PROGRESSIONS, story_second,
    )
    assert any(
        edge.source == first_beat_key
        and edge.target == second_beat_key
        and edge.edge_type == P.ET_PRECEDES
        and edge.confidence == P.CONF_CONFIRMED
        for edge in graph.edges
    )
    assert any(
        edge.source == first_beat_key
        and edge.target == node_key(P.NT_SCENE, "scene", first.id)
        and edge.edge_type == P.ET_ADVANCES_IN
        and edge.provenance == P.PROV_PROGRESSION_BEAT
        for edge in graph.edges
    )
    non_scene_beat_keys = {
        node_key(P.NT_PROGRESSION_BEAT, P.SS_PROGRESSIONS, character_beat),
        node_key(P.NT_PROGRESSION_BEAT, P.SS_PROGRESSIONS, relationship_beat),
    }
    assert not any(
        edge.source in non_scene_beat_keys
        and edge.edge_type == P.ET_ADVANCES_IN
        for edge in graph.edges
    )


def test_legacy_compatibility_progression_is_not_projected_twice():
    db = Database()
    project = db.create_project("Compatibility", narrative_engine="novel")
    scene = db.create_scene(project.id, "Turn", content="No name here.")
    alice = db.create_psyke_entry(project.id, "Alice", "character")
    legacy = db.create_psyke_progression(
        alice.id, "Alice changes", scene_id=scene.id,
    )

    graph = build_knowledge_graph(db, project.id).graph
    assert graph.nodes_of_type(P.NT_PROGRESSION_TRACK) == []
    assert graph.nodes_of_type(P.NT_PROGRESSION_BEAT) == []
    progression_edges = [
        edge for edge in graph.edges
        if edge.provenance == P.PROV_PSYKE_PROGRESSION
    ]
    assert len(progression_edges) == 1
    assert progression_edges[0].source == node_key(
        P.NT_CHARACTER, "psyke", alice.id,
    )
    assert progression_edges[0].target == node_key(
        P.NT_SCENE, "scene", scene.id,
    )
    assert legacy.id is not None


def test_legacy_and_native_subject_scene_evidence_keep_distinct_semantics():
    db = Database()
    project = db.create_project("Mixed evidence", narrative_engine="novel")
    scene = db.create_scene(project.id, "Turn", content="No names here.")
    alice = db.create_psyke_entry(project.id, "Alice", "character")
    db.create_psyke_progression(
        alice.id, "Legacy state", scene_id=scene.id,
    )
    native_track = _progression_command(
        db, project.id, "create_track",
        track_kind="character", title="Native Alice arc",
        primary_psyke_entry_id=alice.id,
    ).created_track_id
    _progression_command(
        db, project.id, "create_beat",
        track_id=native_track, text="Native state",
        anchor_kind="scene", scene_id=scene.id,
    )

    graph = build_knowledge_graph(db, project.id).graph
    source = node_key(P.NT_CHARACTER, "psyke", alice.id)
    target = node_key(P.NT_SCENE, "scene", scene.id)
    subject_scene_edges = [
        edge for edge in graph.edges
        if edge.source == source and edge.target == target
    ]
    assert {
        (edge.edge_type, edge.provenance, edge.source_system)
        for edge in subject_scene_edges
    } >= {
        (P.ET_APPEARS_IN, P.PROV_PSYKE_PROGRESSION, P.SS_PSYKE),
        (P.ET_ADVANCES_IN, P.PROV_PROGRESSION_BEAT, P.SS_PROGRESSIONS),
    }


def test_builder_reads_one_progression_snapshot_for_both_projections(monkeypatch):
    db = Database()
    project = db.create_project("One read", narrative_engine="novel")
    scene = db.create_scene(project.id, "Turn")
    entry = db.create_psyke_entry(project.id, "Alice", "character")
    db.create_psyke_progression(entry.id, "Legacy state", scene_id=scene.id)
    real_read = db.read_progression_snapshot
    calls = []

    def counted_read(project_id):
        calls.append(project_id)
        return real_read(project_id)

    monkeypatch.setattr(db, "read_progression_snapshot", counted_read)
    monkeypatch.setattr(
        db,
        "get_psyke_progressions",
        lambda *_args, **_kwargs: pytest.fail(
            "graph extraction must not perform per-entry progression reads"
        ),
    )

    graph = build_knowledge_graph(db, project.id).graph
    assert calls == [project.id]
    assert any(
        edge.provenance == P.PROV_PSYKE_PROGRESSION
        for edge in graph.edges
    )


def test_progression_read_failure_preserves_the_rest_of_the_graph(monkeypatch):
    db = Database()
    project = db.create_project("Partial graph", narrative_engine="novel")
    scene = db.create_scene(project.id, "Opening")
    entry = db.create_psyke_entry(project.id, "Alice", "character")
    monkeypatch.setattr(
        db,
        "read_progression_snapshot",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("progressions unavailable")
        ),
    )

    graph = build_knowledge_graph(db, project.id).graph
    assert graph.unavailable.count(P.SS_PROGRESSIONS) == 1
    assert node_key(P.NT_SCENE, "scene", scene.id) in graph.nodes
    assert node_key(P.NT_CHARACTER, "psyke", entry.id) in graph.nodes
    assert graph.nodes_of_type(P.NT_PROGRESSION_TRACK) == []
    assert graph.nodes_of_type(P.NT_PROGRESSION_BEAT) == []


def test_native_progression_graph_projection_is_project_isolated():
    db = Database()
    owner = db.create_project("Owner", narrative_engine="novel")
    foreign = db.create_project("Foreign", narrative_engine="novel")

    def create_track_and_beat(project_id: int, title: str):
        track = _progression_command(
            db, project_id, "create_track",
            track_kind="story", title=title,
        ).created_track_id
        beat = _progression_command(
            db, project_id, "create_beat",
            track_id=track, text=f"{title} beat",
            anchor_kind="unanchored",
        ).created_beat_id
        return track, beat

    owner_track, owner_beat = create_track_and_beat(owner.id, "Owner arc")
    foreign_track, foreign_beat = create_track_and_beat(
        foreign.id, "Foreign arc",
    )

    graph = build_knowledge_graph(db, owner.id).graph
    owner_track_key = node_key(
        P.NT_PROGRESSION_TRACK, P.SS_PROGRESSIONS, owner_track,
    )
    assert owner_track_key in graph.nodes
    assert node_key(
        P.NT_PROGRESSION_BEAT, P.SS_PROGRESSIONS, owner_beat,
    ) in graph.nodes
    assert node_key(
        P.NT_PROGRESSION_TRACK, P.SS_PROGRESSIONS, foreign_track,
    ) not in graph.nodes
    assert node_key(
        P.NT_PROGRESSION_BEAT, P.SS_PROGRESSIONS, foreign_beat,
    ) not in graph.nodes


def test_native_progression_projection_caps_are_deterministic():
    graph = KnowledgeGraph(project_id=7)
    graph.add_node(KGNode(
        key=node_key(P.NT_PROJECT, "project", 7),
        node_type=P.NT_PROJECT,
        source_type="project",
        source_id="7",
        label="Capped",
    ))
    rows = []
    next_beat_id = 1000
    for track_index in range(101):
        beats = []
        for beat_index in range(5):
            beats.append(SimpleNamespace(
                id=next_beat_id,
                track_id=track_index + 1,
                text=f"Beat {track_index}-{beat_index}",
                sort_order=beat_index,
                anchor_kind="unanchored",
                scene_id=None,
                anchor_ref=None,
                anchor_label="",
            ))
            next_beat_id += 1
        rows.append(SimpleNamespace(
            track=SimpleNamespace(
                id=track_index + 1,
                legacy_psyke_entry_id=None,
                kind="story",
                title=f"Track {track_index + 1}",
                description="",
                sort_order=track_index,
            ),
            beats=tuple(beats),
            primary_entry=None,
            secondary_entry=None,
            coverage=SimpleNamespace(
                total_beats=5,
                anchored_beats=0,
                unanchored_beats=5,
                scene_anchored_beats=0,
                document_anchored_beats=0,
                coverage_percent=0.0,
                status="unanchored",
                out_of_order_beat_ids=(),
            ),
        ))
    rows.append(SimpleNamespace(
        track=SimpleNamespace(
            id=102,
            legacy_psyke_entry_id=None,
            kind="custom",
            title="Overflow empty track",
            description="",
            sort_order=101,
        ),
        beats=(),
        primary_entry=None,
        secondary_entry=None,
        coverage=SimpleNamespace(
            total_beats=0,
            anchored_beats=0,
            unanchored_beats=0,
            scene_anchored_beats=0,
            document_anchored_beats=0,
            coverage_percent=0.0,
            status="empty",
            out_of_order_beat_ids=(),
        ),
    ))

    extract_progressions(
        None,
        7,
        graph,
        progression_snapshot=SimpleNamespace(tracks=tuple(rows)),
    )

    assert len(graph.nodes_of_type(P.NT_PROGRESSION_TRACK)) == 100
    assert len(graph.nodes_of_type(P.NT_PROGRESSION_BEAT)) == 400
    assert node_key(P.NT_PROGRESSION_TRACK, P.SS_PROGRESSIONS, 99) in graph.nodes
    assert node_key(P.NT_PROGRESSION_TRACK, P.SS_PROGRESSIONS, 100) not in graph.nodes
    assert node_key(P.NT_PROGRESSION_TRACK, P.SS_PROGRESSIONS, 101) not in graph.nodes
    assert node_key(P.NT_PROGRESSION_TRACK, P.SS_PROGRESSIONS, 102) in graph.nodes
    assert graph.warnings == [
        "Native Progressions extraction capped at 100 tracks.",
        "Native Progressions extraction capped at 400 beats.",
    ]
    cards = build_graph_decision_cards(
        None,
        7,
        result=KnowledgeGraphResult(graph=graph),
        cap=50,
    )
    unanchored = next(
        card for card in cards
        if card.id == "kg_progression_unanchored_1"
    )
    assert unanchored.evidence_total == 505
    assert "101 track(s)" in unanchored.title
    empty = next(
        card for card in cards
        if card.id == "kg_progression_empty_102"
    )
    assert empty.evidence_total == 1
    assert empty.graph_focus_key == (
        f"{P.NT_PROGRESSION_TRACK}:{P.SS_PROGRESSIONS}:102"
    )


def test_only_typed_progression_subjects_satisfy_scene_psyke_coverage():
    db = Database()
    project = db.create_project("Coverage", narrative_engine="novel")
    scene = db.create_scene(project.id, "Quiet", content="No names here.")
    alice = db.create_psyke_entry(project.id, "Alice", "character")
    story_track = _progression_command(
        db, project.id, "create_track",
        track_kind="story", title="Story arc",
    ).created_track_id
    _progression_command(
        db, project.id, "create_beat",
        track_id=story_track, text="The plot turns",
        anchor_kind="scene", scene_id=scene.id,
    )

    story_only = build_knowledge_graph(db, project.id).graph
    assert [
        node.source_id for node in scoring.scenes_without_psyke(story_only)
    ] == [str(scene.id)]

    character_track = _progression_command(
        db, project.id, "create_track",
        track_kind="character", title="Alice arc",
        primary_psyke_entry_id=alice.id,
    ).created_track_id
    character_beat = _progression_command(
        db, project.id, "create_beat",
        track_id=character_track, text="Alice makes a choice",
        anchor_kind="scene", scene_id=scene.id,
    ).created_beat_id

    with_character = build_knowledge_graph(db, project.id).graph
    assert scoring.scenes_without_psyke(with_character) == []
    assert any(
        edge.source == node_key(P.NT_CHARACTER, "psyke", alice.id)
        and edge.target == node_key(P.NT_SCENE, "scene", scene.id)
        and edge.edge_type == P.ET_ADVANCES_IN
        and edge.provenance == P.PROV_PROGRESSION_BEAT
        and edge.metadata["beat_id"] == character_beat
        for edge in with_character.edges
    )


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


def test_revision_extraction_is_newest_first_globally_bounded_and_deterministic():
    from logosforge.knowledge_graph.models import KGNode, KnowledgeGraph

    reports = [
        SimpleNamespace(
            id=report_id,
            title=f"Report {report_id}",
            summary="",
            impact_level="high",
            confidence=P.CONF_CONFIRMED,
            scene_id=1,
        )
        for report_id in range(1, 206)
    ]
    items_by_report = {
        205: [
            SimpleNamespace(
                id=item_id,
                target_type="scene",
                target_id=str(item_id),
                confidence=P.CONF_POSSIBLE,
                explanation=f"Risk {item_id}",
                severity="warning",
                impact_kind="depends_on",
                label=f"Scene {item_id}",
                suggested_action="Review it.",
            )
            for item_id in range(1, 151)
        ],
        204: [
            SimpleNamespace(
                id=item_id,
                target_type="scene",
                target_id=str(item_id),
                confidence=P.CONF_POSSIBLE,
                explanation=f"Risk {item_id}",
                severity="error",
                impact_kind="contradicts",
                label=f"Scene {item_id}",
                suggested_action="Resolve it.",
            )
            for item_id in range(151, 251)
        ],
    }
    longest_item = items_by_report[205][-1]
    longest_item.severity = "s" * 100
    longest_item.impact_kind = "k" * 100
    longest_item.label = "l" * 500
    longest_item.suggested_action = "a" * 1_000

    class FakeDb:
        def __init__(self, report_rows):
            self.report_rows = report_rows
            self.calls = []

        def get_revision_impact_reports(self, project_id):
            assert project_id == 7
            return list(self.report_rows)

        def get_revision_impact_items(self, report_id, *, limit=None):
            self.calls.append((report_id, limit))
            rows = items_by_report.get(report_id, [])
            return list(rows if limit is None else rows[:limit])

    def extracted(report_rows):
        fake = FakeDb(report_rows)
        graph = KnowledgeGraph(project_id=7)
        for scene_id in range(1, 251):
            graph.add_node(KGNode(
                key=node_key(P.NT_SCENE, "scene", scene_id),
                node_type=P.NT_SCENE,
                source_type="scene",
                source_id=str(scene_id),
                label=f"Scene {scene_id}",
            ))
        extract_revision(fake, 7, graph)
        return fake, graph

    ascending_db, ascending = extracted(reports)
    descending_db, descending = extracted(list(reversed(reports)))

    expected_report_ids = {str(value) for value in range(6, 206)}
    actual_report_ids = {
        node.source_id for node in ascending.nodes.values()
        if node.node_type == P.NT_REVISION_IMPACT
    }
    assert actual_report_ids == expected_report_ids
    assert sum(edge.edge_type == P.ET_REVISES for edge in ascending.edges) == 200
    risk_edges = [edge for edge in ascending.edges if edge.edge_type == P.ET_RISKS]
    assert len(risk_edges) == 200
    assert ascending_db.calls == [(205, 200), (204, 50)]
    assert descending_db.calls == ascending_db.calls
    assert ascending.to_dict() == descending.to_dict()
    assert risk_edges[0].metadata == {
        "item_id": 1,
        "severity": "warning",
        "impact_kind": "depends_on",
        "label": "Scene 1",
        "suggested_action": "Review it.",
    }
    bounded_metadata = next(
        edge.metadata for edge in risk_edges
        if edge.metadata["item_id"] == 150
    )
    assert len(bounded_metadata["severity"]) == 32
    assert len(bounded_metadata["impact_kind"]) == 64
    assert len(bounded_metadata["label"]) == 256
    assert len(bounded_metadata["suggested_action"]) == 512


def test_revision_extraction_skips_missing_project_targets():
    class FakeDb:
        def get_revision_impact_reports(self, _project_id):
            return [SimpleNamespace(
                id=1,
                title="Dangling report",
                summary="",
                impact_level="high",
                confidence=P.CONF_CONFIRMED,
                scene_id=999,
            )]

        def get_revision_impact_items(self, _report_id, *, limit=None):
            return [SimpleNamespace(
                id=1,
                target_type="scene",
                target_id=999,
                confidence=P.CONF_POSSIBLE,
                explanation="Foreign or deleted scene",
            )]

    graph = KnowledgeGraph(project_id=7)
    extract_revision(FakeDb(), 7, graph)

    assert len(graph.nodes_of_type(P.NT_REVISION_IMPACT)) == 1
    assert graph.edges == []


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
    build_knowledge_graph(db, pid)
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
    assert all(c.created_from == "knowledge_graph" for c in cards)
    assert all(c.graph_focus_key and c.graph_view_mode for c in cards)
    assert all(c.evidence and c.evidence_total >= len(c.evidence) for c in cards)
    undefined = next(c for c in cards if c.id == "kg_undefined_terms")
    assert undefined.evidence[0].kind == "term"
    assert undefined.evidence[0].graph_focus_key.startswith("note:note:")


def test_progression_decision_cards_are_bounded_traceable_and_actionable():
    db = Database()
    project = db.create_project("Progression radar", narrative_engine="novel")
    early = db.create_scene(project.id, "Early")
    late = db.create_scene(project.id, "Late")

    ordered = _progression_command(
        db, project.id, "create_track",
        track_kind="story", title="Main arc",
    ).created_track_id
    _progression_command(
        db, project.id, "create_beat",
        track_id=ordered, text="Late turn",
        anchor_kind="scene", scene_id=late.id,
    )
    out_of_order_beat = _progression_command(
        db, project.id, "create_beat",
        track_id=ordered, text="Earlier turn",
        anchor_kind="scene", scene_id=early.id,
    ).created_beat_id
    unanchored_beat = _progression_command(
        db, project.id, "create_beat",
        track_id=ordered, text="Floating state",
        anchor_kind="unanchored",
    ).created_beat_id
    second_ordered = _progression_command(
        db, project.id, "create_track",
        track_kind="story", title="Secondary arc",
    ).created_track_id
    _progression_command(
        db, project.id, "create_beat",
        track_id=second_ordered, text="Second late turn",
        anchor_kind="scene", scene_id=late.id,
    )
    second_out_of_order_beat = _progression_command(
        db, project.id, "create_beat",
        track_id=second_ordered, text="Second earlier turn",
        anchor_kind="scene", scene_id=early.id,
    ).created_beat_id
    second_unanchored_beat = _progression_command(
        db, project.id, "create_beat",
        track_id=second_ordered, text="Second floating state",
        anchor_kind="unanchored",
    ).created_beat_id
    empty = _progression_command(
        db, project.id, "create_track",
        track_kind="custom", title="Unused arc",
    ).created_track_id
    second_empty = _progression_command(
        db, project.id, "create_track",
        track_kind="custom", title="Second unused arc",
    ).created_track_id
    document_track = _progression_command(
        db, project.id, "create_track",
        track_kind="story", title="Drafter arc",
    ).created_track_id
    _progression_command(
        db, project.id, "create_beat",
        track_id=document_track, text="Draft-only scene",
        anchor_kind="document_block", anchor_ref="draft-scene-1",
        anchor_label="Draft scene",
    )

    cards = build_graph_decision_cards(db, project.id, cap=50)
    progression_cards = [
        card for card in cards if card.category == "progression"
    ]
    assert len(progression_cards) == 3
    by_id = {card.id: card for card in progression_cards}
    expected_ids = {
        f"kg_progression_order_{ordered}",
        f"kg_progression_unanchored_{ordered}",
        f"kg_progression_empty_{empty}",
    }
    assert set(by_id) == expected_ids
    assert all(card.related_section == "Progressions"
               for card in progression_cards)
    assert all(card.related_target_type == "progression_track"
               for card in progression_cards)
    assert {
        card.related_target_id for card in progression_cards
    } == {ordered, empty}
    assert all(card.graph_focus_key.startswith(
        f"{P.NT_PROGRESSION_TRACK}:{P.SS_PROGRESSIONS}:",
    ) for card in progression_cards)

    order_card = by_id[f"kg_progression_order_{ordered}"]
    assert order_card.evidence_total == 2
    assert all(item.related_target_type == "progression_beat"
               for item in order_card.evidence)
    assert {item.related_target_id for item in order_card.evidence} == {
        out_of_order_beat, second_out_of_order_beat,
    }
    unanchored_card = by_id[f"kg_progression_unanchored_{ordered}"]
    assert unanchored_card.evidence_total == 2
    assert {item.related_target_id for item in unanchored_card.evidence} == {
        unanchored_beat, second_unanchored_beat,
    }
    empty_card = by_id[f"kg_progression_empty_{empty}"]
    assert empty_card.evidence_total == 2
    assert {item.related_target_id for item in empty_card.evidence} == {
        empty, second_empty,
    }
    assert all(str(document_track) not in card.id for card in progression_cards)


def test_graph_decision_cards_reject_a_foreign_precomputed_result():
    db, pid, *_ = _project()
    result = build_knowledge_graph(db, pid)
    foreign_pid = db.create_project(
        "Foreign graph",
        narrative_engine="novel",
    ).id

    with pytest.raises(ValueError, match="does not belong"):
        build_graph_decision_cards(db, foreign_pid, result=result)


def test_decision_cards_no_hallucination_on_clean_project():
    db = Database()
    pid = db.create_project("Clean", narrative_engine="novel").id
    db.create_psyke_entry(pid, "Alice", "character")
    db.create_scene(pid, "S", content="Alice acts.", chapter="Ch1")
    cards = build_graph_decision_cards(db, pid)
    # no orphan/undefined cards for a clean tiny project
    assert all(not c.id.startswith("kg_isolated") for c in cards)


def test_decision_cards_do_not_duplicate_an_orphan_theme():
    db = Database()
    pid = db.create_project("Theme", narrative_engine="novel").id
    theme = db.create_psyke_entry(pid, "Isolation", "theme")

    cards = build_graph_decision_cards(db, pid)
    theme_key = f"theme:psyke:{theme.id}"
    matching = [card for card in cards if theme_key in card.id]

    assert len(matching) == 1
    assert matching[0].id.startswith("kg_isolated_")


def test_decision_cards_filter_orphans_before_the_card_cap():
    graph = KnowledgeGraph(project_id=7)
    capped_notes = []
    for index in range(55):
        note = KGNode(
            key=f"note:note:{index}",
            node_type=P.NT_NOTE,
            source_type="note",
            source_id=str(index),
            label=f"Note {index}",
        )
        graph.add_node(note)
        capped_notes.append(note)
    relic = KGNode(
        key="object:psyke:99",
        node_type=P.NT_OBJECT,
        source_type="psyke",
        source_id="99",
        label="Relic",
    )
    graph.add_node(relic)
    result = KnowledgeGraphResult(graph=graph, orphans=capped_notes[:50])

    cards = build_graph_decision_cards(None, 7, result=result)

    assert any(card.id == "kg_isolated_object:psyke:99" for card in cards)


def test_decision_cards_filter_central_story_nodes_before_the_card_cap():
    graph = KnowledgeGraph(project_id=7)
    support_nodes = []
    for index in range(10):
        node_type = P.NT_REVISION_IMPACT if index == 0 else P.NT_WORKFLOW_RUN
        node = KGNode(
            key=f"{node_type}:system:{index}",
            node_type=node_type,
            source_type="system",
            source_id=str(index),
            label=f"System {index}",
        )
        graph.add_node(node)
        support_nodes.append(node)
    for left_index, left in enumerate(support_nodes):
        for right in support_nodes[left_index + 1:]:
            graph.add_edge(KGEdge(
                source=left.key,
                target=right.key,
                edge_type=P.ET_RELATES_TO,
                confidence=P.CONF_CONFIRMED,
            ))
    character = KGNode(
        key="character:psyke:42",
        node_type=P.NT_CHARACTER,
        source_type="psyke",
        source_id="42",
        label="Mara",
    )
    graph.add_node(character)
    graph.add_edge(KGEdge(
        source=support_nodes[0].key,
        target=character.key,
        edge_type=P.ET_RISKS,
        confidence=P.CONF_CONFIRMED,
        explanation="The revision can change Mara's established state.",
    ))
    result = KnowledgeGraphResult(
        graph=graph,
        central=[(node, graph.degree(node.key)) for node in support_nodes],
    )

    cards = build_graph_decision_cards(None, 7, result=result)

    assert any(card.id == "kg_risk_central" for card in cards)


def test_decision_cards_report_the_full_undefined_term_count():
    db = Database()
    pid = db.create_project("Terms", narrative_engine="novel").id
    terms = [
        f"NameA{chr(97 + index // 26)}{chr(97 + index % 26)}"
        for index in range(30)
    ]
    db.create_note(pid, "Glossary", ". ".join(terms))

    result = build_knowledge_graph(db, pid)
    card = next(
        item
        for item in build_graph_decision_cards(db, pid, result=result)
        if item.id == "kg_undefined_terms"
    )

    assert len(result.undefined_terms) == 25
    assert result.undefined_term_total == 30
    assert card.title == "30 note term(s) not in PSYKE."
    assert card.evidence_total == 30
    assert len(card.evidence) == 5


def test_decision_cards_never_publish_dangling_edge_endpoints():
    graph = KnowledgeGraph(project_id=7)
    character = KGNode(
        key="character:psyke:1",
        node_type=P.NT_CHARACTER,
        source_type="psyke",
        source_id="1",
        label="Mara",
    )
    support = KGNode(
        key="theme:psyke:2",
        node_type=P.NT_THEME,
        source_type="psyke",
        source_id="2",
        label="Duty",
    )
    graph.add_node(character)
    graph.add_node(support)
    graph.add_edge(KGEdge(
        source=character.key,
        target=support.key,
        edge_type=P.ET_RELATES_TO,
        confidence=P.CONF_CONFIRMED,
    ))
    graph.add_edge(KGEdge(
        source="revision_impact:revision:foreign",
        target=character.key,
        edge_type=P.ET_RISKS,
        confidence=P.CONF_POSSIBLE,
    ))

    cards = build_graph_decision_cards(
        None,
        7,
        result=KnowledgeGraphResult(graph=graph),
    )

    assert all(card.id != "kg_risk_central" for card in cards)
    assert all(
        graph.get_node(item.source_key) is not None
        and graph.get_node(item.target_key) is not None
        for card in cards
        for item in card.evidence
        if item.kind == "edge"
    )


def test_decision_cards_are_stable_across_equivalent_insertion_orders():
    def result(reverse: bool) -> KnowledgeGraphResult:
        graph = KnowledgeGraph(project_id=7)
        nodes = [
            KGNode(
                key="theme:psyke:a",
                node_type=P.NT_THEME,
                source_type="psyke",
                source_id="a",
                label="Alpha",
            ),
            KGNode(
                key="theme:psyke:b",
                node_type=P.NT_THEME,
                source_type="psyke",
                source_id="b",
                label="Beta",
            ),
            KGNode(
                key="revision_impact:revision:a",
                node_type=P.NT_REVISION_IMPACT,
                source_type="revision",
                source_id="a",
                label="Revision A",
            ),
            KGNode(
                key="revision_impact:revision:b",
                node_type=P.NT_REVISION_IMPACT,
                source_type="revision",
                source_id="b",
                label="Revision B",
            ),
        ]
        edges = [
            KGEdge(
                source="theme:psyke:a",
                target="theme:psyke:b",
                edge_type=P.ET_RELATES_TO,
                confidence=P.CONF_CONFIRMED,
            ),
            KGEdge(
                source="revision_impact:revision:a",
                target="theme:psyke:a",
                edge_type=P.ET_RISKS,
                confidence=P.CONF_CONFIRMED,
                explanation="Risk A",
            ),
            KGEdge(
                source="revision_impact:revision:b",
                target="theme:psyke:b",
                edge_type=P.ET_RISKS,
                confidence=P.CONF_CONFIRMED,
                explanation="Risk B",
            ),
        ]
        for node in reversed(nodes) if reverse else nodes:
            graph.add_node(node)
        for edge in reversed(edges) if reverse else edges:
            graph.add_edge(edge)
        return KnowledgeGraphResult(graph=graph)

    forward = [
        card.to_dict()
        for card in build_graph_decision_cards(None, 7, result=result(False))
    ]
    reversed_order = [
        card.to_dict()
        for card in build_graph_decision_cards(None, 7, result=result(True))
    ]

    assert forward == reversed_order


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
