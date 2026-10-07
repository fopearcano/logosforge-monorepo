"""Phase 7C Timeline story-flow and mode-specific read projections."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from logosforge.api import create_api, schemas
from logosforge.db import Database
from logosforge.timeline_projections import build_timeline_mode_projection
from pydantic import ValidationError


def _project(engine: str):
    db = Database()
    project = db.create_project(
        f"{engine} Timeline",
        narrative_engine=engine,
        default_writing_format=("screenplay" if engine == "series" else engine),
    )
    return db, project, TestClient(create_api(db=db))


def _timeline(client: TestClient, project_id: int) -> dict:
    response = client.get(f"/api/projects/{project_id}/timeline")
    assert response.status_code == 200, response.text
    return response.json()


def _large_event_contract():
    event_count = 10_001
    event_ids = list(range(1, event_count + 1))
    events = [
        schemas.TimelineEventDTO(id=scene_id, title=f"Event {scene_id}")
        for scene_id in event_ids
    ]
    story_flow = schemas.TimelineStoryFlowDTO(
        points=[
            schemas.TimelineStoryFlowPointDTO(
                scene_id=scene_id,
                order_index=scene_id,
                tension_value=5,
                tension_source="default",
                scene_type="exposition",
                dialogue_ratio=0.0,
                action_ratio=0.0,
            )
            for scene_id in event_ids
        ],
        warnings=[
            schemas.TimelinePacingWarningDTO(
                start_scene_id=event_ids[0],
                end_scene_id=event_ids[-1],
                scene_ids=event_ids,
                reason="no_variation",
            )
        ],
    )
    return event_ids, events, story_flow


def test_story_flow_capacity_tracks_uncapped_timeline_events():
    event_ids, events, story_flow = _large_event_contract()

    snapshot = schemas.TimelineSnapshotDTO(
        project_id=1,
        revision="0" * 64,
        events=events,
        story_flow=story_flow,
        mode_projection={"kind": "novel"},
    )

    assert len(snapshot.events) == len(event_ids)
    assert len(snapshot.story_flow.points) == len(event_ids)
    assert len(snapshot.story_flow.warnings[0].scene_ids) == len(event_ids)


def test_event_cardinality_mode_projections_accept_10001_events():
    event_ids, events, story_flow = _large_event_contract()
    base = {
        "project_id": 1,
        "revision": "0" * 64,
        "events": events,
        "story_flow": story_flow,
    }

    screenplay = schemas.TimelineSnapshotDTO(
        **base,
        mode_projection={
            "kind": "screenplay",
            "scenes": [
                {
                    "scene_id": scene_id,
                    "interior_exterior": "",
                    "cinematic_pacing": "",
                    "dramatic_turn": "",
                    "emotional_turn": "",
                    "objective": "",
                    "conflict": "",
                    "turning_point": "",
                    "emotional_shift": "",
                    "visual_beat_count": 0,
                }
                for scene_id in event_ids
            ],
        },
    )
    assert len(screenplay.mode_projection.scenes) == len(event_ids)

    stage = schemas.TimelineSnapshotDTO(
        **base,
        mode_projection={
            "kind": "stage_script",
            "scenes": [
                {
                    "scene_id": scene_id,
                    "order_index": scene_id,
                    "act": "",
                    "title": "",
                    "entrances_exits": [],
                    "cues": [],
                    "offstage_events": "",
                    "has_offstage_events": False,
                    "props": [],
                    "emotional_pressure": "flat",
                }
                for scene_id in event_ids
            ],
        },
    )
    assert len(stage.mode_projection.scenes) == len(event_ids)

    assigned = schemas.TimelineSnapshotDTO(
        **base,
        mode_projection={
            "kind": "series",
            "episodes": [
                {
                    "episode_id": 1,
                    "order_index": 1,
                    "season_id": None,
                    "season": "",
                    "episode_number": 1,
                    "title": "Episode 1",
                    "cliffhanger": "",
                    "scene_ids": event_ids,
                    "active_arcs": [],
                    "setup_arc_ids": [],
                    "payoff_arc_ids": [],
                }
            ],
            "arc_chains": [],
            "unassigned_scene_ids": [],
        },
    )
    assert len(assigned.mode_projection.episodes[0].scene_ids) == len(event_ids)

    many_episodes = schemas.TimelineSnapshotDTO(
        **base,
        mode_projection={
            "kind": "series",
            "episodes": [
                {
                    "episode_id": scene_id,
                    "order_index": scene_id,
                    "season_id": 1,
                    "season": "Season One",
                    "episode_number": scene_id,
                    "title": f"Episode {scene_id}",
                    "cliffhanger": "",
                    "scene_ids": [scene_id],
                    "active_arcs": [],
                    "setup_arc_ids": [],
                    "payoff_arc_ids": [],
                }
                for scene_id in event_ids
            ],
            "arc_chains": [],
            "unassigned_scene_ids": [],
        },
    )
    assert len(many_episodes.mode_projection.episodes) == len(event_ids)

    unassigned = schemas.TimelineSnapshotDTO(
        **base,
        mode_projection={
            "kind": "series",
            "episodes": [],
            "arc_chains": [],
            "unassigned_scene_ids": event_ids,
        },
    )
    assert len(unassigned.mode_projection.unassigned_scene_ids) == len(event_ids)


def test_series_projection_preserves_assignment_beyond_10000_episodes():
    episodes = [
        SimpleNamespace(
            id=episode_id,
            season_id=1,
            episode_number=episode_id,
            order_index=episode_id,
            title=f"Episode {episode_id}",
            cliffhanger="",
        )
        for episode_id in range(1, 10_002)
    ]
    projection = build_timeline_mode_projection(
        SimpleNamespace(narrative_engine="series"),
        [SimpleNamespace(id=77, episode_id=10_001)],
        {},
        seasons=[
            SimpleNamespace(id=1, order_index=1, season_number=1, title="Season One")
        ],
        episodes=episodes,
        series_arcs=[
            SimpleNamespace(
                id=501,
                scope="series",
                status="active",
                title="Late arc",
                setup_episode_id=10_000,
                payoff_episode_id=10_001,
            )
        ],
    )

    assert len(projection["episodes"]) == 10_000
    assert projection["episodes"][-1]["episode_id"] == 10_001
    assert projection["episodes"][-1]["scene_ids"] == [77]
    assert projection["unassigned_scene_ids"] == []
    assert projection["episodes"][0]["active_arcs"] == []
    assert [arc["arc_id"] for arc in projection["episodes"][-1]["active_arcs"]] == [
        501
    ]
    assert projection["arc_chains"] == []

    empty_projection = build_timeline_mode_projection(
        SimpleNamespace(narrative_engine="series"),
        [],
        {},
        seasons=[
            SimpleNamespace(id=1, order_index=1, season_number=1, title="Season One")
        ],
        episodes=episodes,
    )
    assert len(empty_projection["episodes"]) == 10_000


def test_series_arc_chain_rejects_unknown_endpoints():
    with pytest.raises(
        ValidationError,
        match="series arc chains must reference projected episodes",
    ):
        schemas.TimelineSnapshotDTO(
            project_id=1,
            revision="0" * 64,
            story_flow={"points": [], "warnings": []},
            mode_projection={
                "kind": "series",
                "episodes": [],
                "arc_chains": [
                    {
                        "arc_id": 1,
                        "title": "Dangling",
                        "scope": "series",
                        "setup_episode_id": 101,
                        "payoff_episode_id": 102,
                        "setup_order_index": 1,
                        "payoff_order_index": 2,
                    }
                ],
                "unassigned_scene_ids": [],
            },
        )


def test_story_flow_matches_effective_events_and_is_not_part_of_revision():
    db, project, client = _project("novel")
    off_timeline = db.create_scene(
        project.id,
        "Notes only",
        tags="tension:10",
        content="Danger.",
    )
    events = [
        db.create_scene(
            project.id,
            f"Event {index}",
            plotline="Main",
            tags="tension:2",
            content="A quiet room.",
        )
        for index in range(1, 5)
    ]
    expected_order = [events[2].id, events[0].id, events[3].id, events[1].id]
    db.patch_project_settings(
        project.id,
        {
            "timeline_order_mode": "custom",
            "timeline_order": expected_order,
        },
    )

    before = _timeline(client, project.id)
    assert [row["id"] for row in before["events"]] == expected_order
    assert [row["scene_id"] for row in before["story_flow"]["points"]] == (
        expected_order
    )
    assert [row["order_index"] for row in before["story_flow"]["points"]] == [
        1,
        2,
        3,
        4,
    ]
    assert all(
        row["tension_source"] == "manual" and row["tension_value"] == 2
        for row in before["story_flow"]["points"]
    )
    assert before["story_flow"]["warnings"] == [
        {
            "start_scene_id": expected_order[0],
            "end_scene_id": expected_order[-1],
            "scene_ids": expected_order,
            "reason": "monotone_low",
        }
    ]
    assert off_timeline.id not in {
        scene_id
        for warning in before["story_flow"]["warnings"]
        for scene_id in warning["scene_ids"]
    }
    assert before["mode_projection"] == {"kind": "novel"}

    changed = events[2]
    db.update_scene(
        changed.id,
        changed.title,
        tags="tension:9",
        content='"Run!"\nHe sprinted and jumped.',
        plotline=changed.plotline,
    )
    after = _timeline(client, project.id)
    assert after["revision"] == before["revision"]
    assert after["story_flow"]["points"][0]["tension_value"] == 9
    assert after["story_flow"]["warnings"] == []

    command = client.post(
        f"/api/projects/{project.id}/timeline/commands",
        json={
            "kind": "set_order_mode",
            "expected_revision": after["revision"],
            "mode": "custom",
        },
    )
    assert command.status_code == 200, command.text
    body = command.json()
    assert body["changed"] is False
    assert body["timeline"]["story_flow"] == after["story_flow"]
    assert body["timeline"]["mode_projection"] == {"kind": "novel"}


def test_screenplay_projection_is_event_aligned_and_malformed_plans_degrade():
    db, project, client = _project("screenplay")
    overlong_turn = "x" * 5_000
    scene = db.create_scene(
        project.id,
        "INT. LAB - NIGHT",
        plotline="A",
        interior_exterior="INT",
        cinematic_pacing="fast",
        dramatic_turn=overlong_turn,
        emotional_turn="confidence to fear",
    )
    off_timeline = db.create_scene(project.id, "Unused")
    db.patch_project_settings(
        project.id,
        {
            "screenplay_beat_plans": {
                str(scene.id): {
                    "objective": "Escape",
                    "conflict": {"malformed": True},
                    "turning_point": "The lock fails",
                    "emotional_shift": "hope to dread",
                    "visual_beats": ["door", "alarm"],
                },
                str(off_timeline.id): {"objective": "Must not leak"},
                "corrupt": ["not", "a", "plan"],
            },
        },
    )

    first = _timeline(client, project.id)
    assert first["mode_projection"] == {
        "kind": "screenplay",
        "scenes": [
            {
                "scene_id": scene.id,
                "interior_exterior": "INT",
                "cinematic_pacing": "fast",
                "dramatic_turn": overlong_turn[:4_096],
                "emotional_turn": "confidence to fear",
                "objective": "Escape",
                "conflict": "",
                "turning_point": "The lock fails",
                "emotional_shift": "hope to dread",
                "visual_beat_count": 2,
            }
        ],
    }
    assert [row["scene_id"] for row in first["mode_projection"]["scenes"]] == [
        row["id"] for row in first["events"]
    ]
    assert len(first["mode_projection"]["scenes"][0]["dramatic_turn"]) == 4_096

    db.patch_project_settings(
        project.id,
        {
            "screenplay_beat_plans": {str(scene.id): {"objective": "Survive"}},
        },
    )
    second = _timeline(client, project.id)
    assert second["revision"] == first["revision"]
    assert second["mode_projection"]["scenes"][0]["objective"] == "Survive"


def test_graphic_novel_projection_is_owned_deterministic_and_normalized():
    db, project, client = _project("graphic_novel")
    issue = db.create_gn_issue(project.id, issue_number=1, title="Issue One")
    sequence = db.create_gn_sequence(project.id, title="Opening")
    setup = db.create_gn_page(
        project.id,
        sequence_id=sequence.id,
        issue_id=issue.id,
        page_number=1,
        density_level="dense",
        reveal_type="cliffhanger",
    )
    reveal = db.create_gn_page(
        project.id,
        page_number=2,
        density_level="corrupt-density",
    )
    db.create_gn_panel(
        setup.id,
        project_id=project.id,
        action="Hero leaps",
        dialogue_refs=["line-1", "line-2"],
    )
    db.create_gn_panel(setup.id, project_id=project.id)

    foreign = db.create_project("Foreign GN", narrative_engine="graphic_novel")
    foreign_issue = db.create_gn_issue(foreign.id, title="Secret Issue")
    db.create_gn_page(foreign.id, page_number=99, density_level="explosive")
    db.update_gn_page(reveal.id, issue_id=foreign_issue.id)

    before = _timeline(client, project.id)
    projection = before["mode_projection"]
    assert projection["kind"] == "graphic_novel"
    assert [page["page_id"] for page in projection["pages"]] == [
        setup.id,
        reveal.id,
    ]
    assert projection["pages"][0] == {
        "page_id": setup.id,
        "page_number": 1,
        "sequence_id": sequence.id,
        "issue_id": issue.id,
        "issue_title": "Issue One",
        "density": "dense",
        "rhythm": "fast",
        "reveal_timing": "cliffhanger",
        "splash_page": False,
        "panel_count": 2,
        "action_density": 0.5,
        "text_load": 2,
        "pacing": "cinematic",
        "is_silence": False,
        "is_action": True,
    }
    assert projection["pages"][1]["density"] == "unset"
    assert projection["pages"][1]["rhythm"] == "steady"
    assert projection["pages"][1]["issue_id"] is None
    assert projection["pages"][1]["issue_title"] == ""
    assert projection["page_turns"] == [
        {
            "setup_page_id": setup.id,
            "setup_page_number": 1,
            "reveal_page_id": reveal.id,
            "reveal_page_number": 2,
            "reveal_type": "cliffhanger",
        }
    ]
    assert "Secret Issue" not in str(projection)

    db.create_gn_page(project.id, page_number=3, density_level="silent")
    after = _timeline(client, project.id)
    assert after["revision"] == before["revision"]
    assert len(after["mode_projection"]["pages"]) == 3


def test_stage_projection_filters_foreign_refs_and_normalizes_enums():
    db, project, client = _project("stage_script")
    scene = db.create_scene(
        project.id,
        "The confrontation",
        plotline="Main",
        act="Act II",
        conflict="They cannot agree",
        offstage_events="A bell rings",
        prop_notes="Fallback prop",
    )
    off_timeline = db.create_scene(project.id, "Rehearsal note")
    actor = db.create_character(project.id, "Ada")
    prop = db.create_psyke_entry(project.id, "Silver Key", "object")

    foreign = db.create_project("Foreign Stage", narrative_engine="stage_script")
    foreign_actor = db.create_character(foreign.id, "Secret Actor")
    foreign_prop = db.create_psyke_entry(foreign.id, "Secret Prop", "object")

    db.create_stage_entrance_exit(
        scene.id,
        character_id=actor.id,
        type="malformed",
        moment_order=-3,
        cue_text="Now",
    )
    db.create_stage_entrance_exit(scene.id, character_id=foreign_actor.id)
    db.create_stage_entrance_exit(off_timeline.id, character_id=actor.id)
    db.create_stage_cue(
        scene.id,
        cue_type="laser",
        moment_order=-4,
        cue_text="Flash",
    )
    db.create_stage_business(scene.id, prop_psyke_entry_id=foreign_prop.id)
    db.create_stage_business(scene.id, prop_psyke_entry_id=prop.id)

    before = _timeline(client, project.id)
    assert before["mode_projection"] == {
        "kind": "stage_script",
        "scenes": [
            {
                "scene_id": scene.id,
                "order_index": 1,
                "act": "Act II",
                "title": "The confrontation",
                "entrances_exits": [
                    {
                        "character": "Ada",
                        "type": "entrance",
                        "moment_order": 0,
                        "cue_text": "Now",
                    }
                ],
                "cues": [
                    {
                        "type": "other",
                        "text": "Flash",
                        "moment_order": 0,
                    }
                ],
                "offstage_events": "A bell rings",
                "has_offstage_events": True,
                "props": ["Silver Key"],
                "emotional_pressure": "conflict",
            }
        ],
    }
    assert "Secret Actor" not in str(before["mode_projection"])
    assert "Secret Prop" not in str(before["mode_projection"])

    db.create_stage_cue(scene.id, cue_type="light", cue_text="Blackout")
    after = _timeline(client, project.id)
    assert after["revision"] == before["revision"]
    assert len(after["mode_projection"]["scenes"][0]["cues"]) == 2


def test_series_projection_uses_owned_episode_order_and_event_membership():
    db, project, client = _project("series")
    season_two = db.create_season(
        project.id,
        season_number=2,
        title="Second",
        order_index=1,
    )
    season_one = db.create_season(
        project.id,
        season_number=1,
        title="First",
        order_index=0,
    )
    first = db.create_episode(
        season_one.id,
        project_id=project.id,
        episode_number=1,
        title="Pilot",
        cliffhanger="The call arrives",
    )
    second = db.create_episode(
        season_two.id,
        project_id=project.id,
        episode_number=1,
        title="Return",
    )
    arc = db.create_series_arc(
        project.id,
        scope="mystery",
        title="Who called?",
        setup_episode_id=first.id,
        payoff_episode_id=second.id,
        status="active",
    )
    malformed_arc = db.create_series_arc(
        project.id,
        scope="invalid",
        title="Fallback",
        status="invalid",
    )
    first_scene = db.create_scene(
        project.id,
        "Cold open",
        plotline="A",
        episode_id=first.id,
    )
    second_scene = db.create_scene(
        project.id,
        "Finale",
        plotline="A",
        episode_id=second.id,
    )
    unassigned = db.create_scene(project.id, "Interstitial", plotline="B")
    db.create_scene(project.id, "Outline only", episode_id=first.id)

    foreign = db.create_project("Foreign Series", narrative_engine="series")
    foreign_season = db.create_season(foreign.id, season_number=1)
    foreign_episode = db.create_episode(
        foreign_season.id,
        project_id=foreign.id,
        episode_number=1,
    )
    foreign_event = db.create_scene(
        project.id,
        "Bad episode ref",
        plotline="C",
        episode_id=foreign_episode.id,
    )
    half_foreign_arc = db.create_series_arc(
        project.id,
        title="Broken endpoint",
        setup_episode_id=foreign_episode.id,
        payoff_episode_id=second.id,
    )

    before = _timeline(client, project.id)
    projection = before["mode_projection"]
    assert projection["kind"] == "series"
    assert [row["episode_id"] for row in projection["episodes"]] == [
        first.id,
        second.id,
    ]
    assert projection["episodes"][0]["scene_ids"] == [first_scene.id]
    assert projection["episodes"][1]["scene_ids"] == [second_scene.id]
    assert projection["unassigned_scene_ids"] == [unassigned.id, foreign_event.id]
    assert projection["arc_chains"] == [
        {
            "arc_id": arc.id,
            "title": "Who called?",
            "scope": "mystery",
            "setup_episode_id": first.id,
            "payoff_episode_id": second.id,
            "setup_order_index": 1,
            "payoff_order_index": 2,
        }
    ]
    fallback = next(
        row
        for row in projection["episodes"][0]["active_arcs"]
        if row["arc_id"] == malformed_arc.id
    )
    assert fallback["scope"] == "series"
    assert fallback["status"] == "active"
    assert half_foreign_arc.id in projection["episodes"][1]["payoff_arc_ids"]
    assert foreign_episode.id not in {
        row["episode_id"] for row in projection["episodes"]
    }

    db.create_series_arc(project.id, title="Presentation-only arc")
    after = _timeline(client, project.id)
    assert after["revision"] == before["revision"]
