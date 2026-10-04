"""Atomic, revision-guarded Pro Timeline API."""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from logosforge.api import create_api
from logosforge.db import Database


def _project(*, path: str | None = None):
    db = Database(path)
    project = db.create_project(
        "Timeline commands",
        narrative_engine="novel",
        default_writing_format="novel",
    )
    return TestClient(create_api(db=db)), db, project.id


def _timeline(client: TestClient, project_id: int) -> dict:
    response = client.get(f"/api/projects/{project_id}/timeline")
    assert response.status_code == 200
    return response.json()


def _command(client: TestClient, project_id: int, **body):
    return client.post(
        f"/api/projects/{project_id}/timeline/commands",
        json=body,
    )


def _create_lane(
    client: TestClient, project_id: int, current: dict, name: str, **extra,
) -> dict:
    response = _command(
        client,
        project_id,
        kind="create_lane",
        expected_revision=current["revision"],
        name=name,
        **extra,
    )
    assert response.status_code == 200
    return response.json()


def test_snapshot_is_revisioned_opt_in_and_structurally_numbered():
    client, db, project_id = _project()
    off = db.create_scene(
        project_id, "Outline only", act="Act I", chapter="One",
    )
    event = db.create_scene(
        project_id,
        "On board",
        act="Act I",
        chapter="One",
        plotline="Main",
        color_label="amber",
        time_of_day="NIGHT",
        location="Bridge",
        estimated_duration_minutes=7,
    )
    character = db.create_character(project_id, "Ada")
    db.update_scene(
        event.id,
        title=event.title,
        act=event.act,
        chapter=event.chapter,
        plotline=event.plotline,
        color_label=event.color_label,
        time_of_day=event.time_of_day,
        location=event.location,
        estimated_duration_minutes=event.estimated_duration_minutes,
        character_ids=[character.id],
        character_states=[(character.id, "alert")],
    )
    lane = db.create_timeline_lane(project_id, "Main", "cyan")

    snapshot = _timeline(client, project_id)

    assert snapshot["project_id"] == project_id
    assert len(snapshot["revision"]) == 64
    assert snapshot["order_mode"] == "structural"
    assert snapshot["lanes"] == [{
        "id": lane.id,
        "name": "Main",
        "color_label": "cyan",
        "order_index": 0,
        "collapsed": False,
        "event_count": 1,
    }]
    assert [row["id"] for row in snapshot["events"]] == [event.id]
    row = snapshot["events"][0]
    assert row["structural_number"] == "1.1.2"
    assert (row["plotline"], row["color_label"], row["lane_id"]) == (
        "Main", "amber", lane.id,
    )
    assert (row["time_of_day"], row["location"], row["duration_minutes"]) == (
        "NIGHT", "Bridge", 7,
    )
    assert row["character_states"] == [{"character": "Ada", "state": "alert"}]
    assert snapshot["off_timeline"] == [{
        "id": off.id,
        "title": "Outline only",
        "structural_number": "1.1.1",
        "act": "Act I",
        "chapter": "One",
    }]


def test_lane_create_update_reorder_and_exact_no_op():
    client, _db, project_id = _project()
    current = _timeline(client, project_id)
    first = _create_lane(client, project_id, current, "Main", color_label="cyan")
    second = _create_lane(
        client, project_id, first["timeline"], "Sub", index=0,
    )
    assert [lane["name"] for lane in second["timeline"]["lanes"]] == [
        "Sub", "Main",
    ]
    assert [lane["order_index"] for lane in second["timeline"]["lanes"]] == [0, 1]
    main = second["timeline"]["lanes"][1]

    updated = _command(
        client,
        project_id,
        kind="update_lane",
        expected_revision=second["timeline"]["revision"],
        lane_id=main["id"],
        name="Main Arc",
        color_label="violet",
        collapsed=True,
        index=0,
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["changed"] is True
    assert body["timeline"]["lanes"][0] | {"event_count": 0} == {
        "id": main["id"],
        "name": "Main Arc",
        "color_label": "violet",
        "order_index": 0,
        "collapsed": True,
        "event_count": 0,
    }

    cursor = client.app.state.broker.latest_id()
    no_op = _command(
        client,
        project_id,
        kind="update_lane",
        expected_revision=body["timeline"]["revision"],
        lane_id=main["id"],
        name="Main Arc",
        color_label="violet",
        collapsed=True,
        index=0,
    ).json()
    assert no_op["changed"] is False
    assert no_op["timeline"]["revision"] == body["timeline"]["revision"]
    assert client.app.state.broker.events_since(cursor, project_id) == []


def test_place_event_uses_custom_order_without_reordering_manuscript():
    client, db, project_id = _project()
    first = db.create_scene(
        project_id, "First", act="Act I", chapter="One", content="BODY A",
    )
    second = db.create_scene(
        project_id, "Second", act="Act I", chapter="One", content="BODY B",
    )
    lane_result = _create_lane(client, project_id, _timeline(client, project_id), "Main")
    lane_id = lane_result["timeline"]["lanes"][0]["id"]
    placed_first = _command(
        client,
        project_id,
        kind="place_event",
        expected_revision=lane_result["timeline"]["revision"],
        scene_id=first.id,
        lane_id=lane_id,
    ).json()
    placed_second = _command(
        client,
        project_id,
        kind="place_event",
        expected_revision=placed_first["timeline"]["revision"],
        scene_id=second.id,
        lane_id=lane_id,
        index=0,
    ).json()

    assert placed_second["timeline"]["order_mode"] == "custom"
    assert [row["id"] for row in placed_second["timeline"]["events"]] == [
        second.id, first.id,
    ]
    assert [row.id for row in db.get_all_scenes(project_id)] == [first.id, second.id]
    assert [row.content for row in db.get_all_scenes(project_id)] == [
        "BODY A", "BODY B",
    ]
    assert db.get_project_settings(project_id)["timeline_order"] == [
        second.id, first.id,
    ]


def test_remove_event_keeps_scene_and_actually_removes_membership():
    client, db, project_id = _project()
    scene = db.create_scene(
        project_id,
        "Keep me",
        act="Act I",
        chapter="One",
        plotline="Main",
        content="IRREPLACEABLE",
    )
    db.add_timeline_event(project_id, scene.id)
    current = _timeline(client, project_id)

    removed = _command(
        client,
        project_id,
        kind="remove_event",
        expected_revision=current["revision"],
        scene_id=scene.id,
    )

    assert removed.status_code == 200
    result = removed.json()
    assert result["changed"] is True
    assert result["timeline"]["events"] == []
    assert [row["id"] for row in result["timeline"]["off_timeline"]] == [scene.id]
    stored = db.get_scene_by_id(scene.id)
    assert stored is not None
    assert stored.content == "IRREPLACEABLE" and stored.plotline == ""
    assert scene.id not in db.get_timeline_event_ids(project_id)


def test_delete_lane_keeps_members_as_unassigned_events():
    client, db, project_id = _project()
    first = db.create_scene(project_id, "A", plotline="Main", content="A body")
    second = db.create_scene(project_id, "B", plotline="Main", content="B body")
    lane = db.create_timeline_lane(project_id, "Main", "cyan")
    current = _timeline(client, project_id)

    deleted = _command(
        client,
        project_id,
        kind="delete_lane",
        expected_revision=current["revision"],
        lane_id=lane.id,
    ).json()

    assert deleted["timeline"]["lanes"] == []
    assert [row["id"] for row in deleted["timeline"]["events"]] == [
        first.id, second.id,
    ]
    assert all(row["lane_id"] is None for row in deleted["timeline"]["events"])
    assert all(row["plotline"] == "" for row in deleted["timeline"]["events"])
    assert db.get_timeline_event_ids(project_id) == {first.id, second.id}
    assert [row.content for row in db.get_all_scenes(project_id)] == [
        "A body", "B body",
    ]


def test_order_mode_round_trip_restores_structural_order():
    client, db, project_id = _project()
    first = db.create_scene(project_id, "A", act="Act I", chapter="One")
    second = db.create_scene(project_id, "B", act="Act I", chapter="One")
    db.add_timeline_event(project_id, first.id)
    db.add_timeline_event(project_id, second.id)
    current = _timeline(client, project_id)
    moved = _command(
        client,
        project_id,
        kind="place_event",
        expected_revision=current["revision"],
        scene_id=second.id,
        lane_id=None,
        index=0,
    ).json()
    assert [row["id"] for row in moved["timeline"]["events"]] == [
        second.id, first.id,
    ]

    structural = _command(
        client,
        project_id,
        kind="set_order_mode",
        expected_revision=moved["timeline"]["revision"],
        mode="structural",
    ).json()
    assert structural["timeline"]["order_mode"] == "structural"
    assert [row["id"] for row in structural["timeline"]["events"]] == [
        first.id, second.id,
    ]


def test_explicit_index_enters_custom_mode_even_at_structural_position():
    client, db, project_id = _project()
    scene = db.create_scene(project_id, "A", act="Act I", chapter="One")
    db.add_timeline_event(project_id, scene.id)
    current = _timeline(client, project_id)

    placed = _command(
        client,
        project_id,
        kind="place_event",
        expected_revision=current["revision"],
        scene_id=scene.id,
        lane_id=None,
        index=0,
    )

    assert placed.status_code == 200
    body = placed.json()
    assert body["changed"] is True
    assert body["timeline"]["order_mode"] == "custom"
    assert [row["id"] for row in body["timeline"]["events"]] == [scene.id]


def test_explicit_index_persists_new_member_when_custom_projection_matches():
    client, db, project_id = _project()
    first = db.create_scene(project_id, "A", act="Act I", chapter="One")
    second = db.create_scene(project_id, "B", act="Act I", chapter="One")
    third = db.create_scene(project_id, "C", act="Act I", chapter="One")
    db.add_timeline_event(project_id, first.id)

    current = _timeline(client, project_id)
    custom = _command(
        client,
        project_id,
        kind="set_order_mode",
        expected_revision=current["revision"],
        mode="custom",
    ).json()
    placed_third = _command(
        client,
        project_id,
        kind="place_event",
        expected_revision=custom["timeline"]["revision"],
        scene_id=third.id,
        lane_id=None,
        index=1,
    ).json()

    assert [row["id"] for row in placed_third["timeline"]["events"]] == [
        first.id, third.id,
    ]
    assert db.get_project_settings(project_id)["timeline_order"] == [
        first.id, third.id,
    ]

    appended_second = _command(
        client,
        project_id,
        kind="place_event",
        expected_revision=placed_third["timeline"]["revision"],
        scene_id=second.id,
        lane_id=None,
    ).json()
    assert [row["id"] for row in appended_second["timeline"]["events"]] == [
        first.id, third.id, second.id,
    ]


@pytest.mark.parametrize(
    "via_structure_command",
    [False, True],
    ids=["scene-endpoint", "story-structure-command"],
)
def test_scene_deletion_scrubs_timeline_state_before_id_reuse(
    via_structure_command: bool,
):
    client, db, project_id = _project()
    scene = db.create_scene(project_id, "Old", act="Act I", chapter="One")
    db.save_project_settings(project_id, {
        "theme": "midnight",
        "timeline_event_ids": [str(scene.id), scene.id, True, "legacy"],
        "timeline_order": [scene.id, str(scene.id), True, {"legacy": 1}],
        "timeline_order_mode": "custom",
    })

    if via_structure_command:
        structure = client.get(
            f"/api/projects/{project_id}/story-structure",
        ).json()
        deleted = client.post(
            f"/api/projects/{project_id}/story-structure/commands",
            json={
                "kind": "delete_scene",
                "expected_revision": structure["revision"],
                "scene_id": scene.id,
            },
        )
    else:
        deleted = client.delete(f"/api/projects/{project_id}/scenes/{scene.id}")
    assert deleted.status_code == 200

    settings = db.get_project_settings(project_id)
    assert settings["timeline_event_ids"] == [True, "legacy"]
    assert settings["timeline_order"] == [True, {"legacy": 1}]
    assert settings["timeline_order_mode"] == "custom"
    assert settings["theme"] == "midnight"

    replacement = db.create_scene(
        project_id, "New", act="Act I", chapter="One",
    )
    assert replacement.id == scene.id
    timeline = _timeline(client, project_id)
    assert timeline["events"] == []
    assert [row["id"] for row in timeline["off_timeline"]] == [replacement.id]


def test_revision_rejects_scene_replacement_that_reuses_identical_id_and_topology():
    client, db, project_id = _project()
    original = db.create_scene(
        project_id, "Same", act="Act I", chapter="One",
    )
    stale = _timeline(client, project_id)

    assert client.delete(
        f"/api/projects/{project_id}/scenes/{original.id}",
    ).status_code == 200
    replacement = db.create_scene(
        project_id, "Same", act="Act I", chapter="One",
    )
    assert replacement.id == original.id
    current = _timeline(client, project_id)
    assert current["revision"] != stale["revision"]

    rejected = _command(
        client,
        project_id,
        kind="place_event",
        expected_revision=stale["revision"],
        scene_id=replacement.id,
        lane_id=None,
    )
    assert rejected.status_code == 409
    assert _timeline(client, project_id) == current


def test_revision_rejects_lane_replacement_that_reuses_identical_id_and_fields():
    client, db, project_id = _project()
    original = db.create_timeline_lane(
        project_id, "Main", "cyan", order_index=0,
    )
    stale = _timeline(client, project_id)

    db.delete_timeline_lane(original.id)
    replacement = db.create_timeline_lane(
        project_id, "Main", "cyan", order_index=0,
    )
    assert replacement.id == original.id
    current = _timeline(client, project_id)
    assert current["revision"] != stale["revision"]

    rejected = _command(
        client,
        project_id,
        kind="delete_lane",
        expected_revision=stale["revision"],
        lane_id=replacement.id,
    )
    assert rejected.status_code == 409
    assert _timeline(client, project_id) == current


def test_revision_rejects_project_replacement_that_reuses_identical_id_and_mode():
    client, db, project_id = _project()
    stale = _timeline(client, project_id)

    db.delete_project(project_id)
    replacement = db.create_project(
        "Timeline commands",
        narrative_engine="novel",
        default_writing_format="novel",
    )
    assert replacement.id == project_id
    current = _timeline(client, project_id)
    assert current["revision"] != stale["revision"]

    rejected = _command(
        client,
        project_id,
        kind="create_lane",
        expected_revision=stale["revision"],
        name="Should not exist",
    )
    assert rejected.status_code == 409
    assert _timeline(client, project_id) == current


def test_stale_revision_rejects_without_partial_mutation_or_events():
    client, db, project_id = _project()
    scene = db.create_scene(project_id, "Scene")
    stale = _timeline(client, project_id)["revision"]
    first = _create_lane(client, project_id, {"revision": stale}, "Winner")
    cursor = client.app.state.broker.latest_id()

    rejected = _command(
        client,
        project_id,
        kind="place_event",
        expected_revision=stale,
        scene_id=scene.id,
        lane_id=first["timeline"]["lanes"][0]["id"],
    )

    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "timeline_conflict"
    assert db.get_scene_by_id(scene.id).plotline == ""
    assert db.get_timeline_event_ids(project_id) == set()
    assert client.app.state.broker.events_since(cursor, project_id) == []


def test_foreign_scene_and_lane_are_indistinguishable_from_missing():
    client, db, project_id = _project()
    other = db.create_project("Other", narrative_engine="novel")
    foreign_scene = db.create_scene(other.id, "Foreign")
    foreign_lane = db.create_timeline_lane(other.id, "Foreign lane")
    current = _timeline(client, project_id)

    scene_response = _command(
        client,
        project_id,
        kind="place_event",
        expected_revision=current["revision"],
        scene_id=foreign_scene.id,
        lane_id=None,
    )
    lane_response = _command(
        client,
        project_id,
        kind="delete_lane",
        expected_revision=current["revision"],
        lane_id=foreign_lane.id,
    )
    assert scene_response.status_code == lane_response.status_code == 404
    assert _timeline(client, project_id) == current


def test_sql_failure_rolls_back_lane_rename_and_every_member(tmp_path):
    _client, db, project_id = _project(path=str(tmp_path / "timeline.db"))
    first = db.create_scene(project_id, "A", plotline="Main")
    second = db.create_scene(project_id, "B", plotline="Main")
    lane = db.create_timeline_lane(project_id, "Main", "cyan")
    snapshot = db.read_timeline_snapshot(project_id)
    assert snapshot is not None

    with db._engine.begin() as connection:
        connection.execute(text(f"""
            CREATE TRIGGER reject_second_timeline_rename
            BEFORE UPDATE OF plotline ON scene
            WHEN OLD.id = {second.id}
            BEGIN
                SELECT RAISE(ABORT, 'forced timeline rollback');
            END;
        """))
    try:
        with pytest.raises(IntegrityError):
            db.execute_timeline_command(
                project_id,
                kind="update_lane",
                expected_revision=snapshot.revision,
                lane_id=lane.id,
                name="Renamed",
            )
    finally:
        with db._engine.begin() as connection:
            connection.execute(text("DROP TRIGGER reject_second_timeline_rename"))

    assert [(row.id, row.plotline) for row in db.get_all_scenes(project_id)] == [
        (first.id, "Main"), (second.id, "Main"),
    ]
    assert [(row.id, row.name) for row in db.get_timeline_lanes(project_id)] == [
        (lane.id, "Main"),
    ]
    assert db.read_timeline_snapshot(project_id).revision == snapshot.revision


def test_concurrent_commands_have_one_winner_and_one_stale_conflict(tmp_path):
    client, db, project_id = _project(path=str(tmp_path / "race.db"))
    revision = _timeline(client, project_id)["revision"]
    barrier = threading.Barrier(3)
    responses = []

    def create(name: str) -> None:
        barrier.wait()
        responses.append(_command(
            client,
            project_id,
            kind="create_lane",
            expected_revision=revision,
            name=name,
        ))

    one = threading.Thread(target=create, args=("One",))
    two = threading.Thread(target=create, args=("Two",))
    one.start()
    two.start()
    barrier.wait()
    one.join(timeout=5)
    two.join(timeout=5)

    assert not one.is_alive() and not two.is_alive()
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert len(db.get_timeline_lanes(project_id)) == 1


def test_revision_ignores_prose_but_tracks_structure_and_timeline_topology():
    client, db, project_id = _project()
    first = db.create_scene(project_id, "A", act="Act I", chapter="One")
    second = db.create_scene(project_id, "B", act="Act I", chapter="One")
    db.add_timeline_event(project_id, first.id)
    before = _timeline(client, project_id)
    scene = client.get(f"/api/projects/{project_id}/scenes/{first.id}").json()

    prose = client.patch(
        f"/api/projects/{project_id}/scenes/{first.id}",
        json={"content": "New prose", "expected_revision": scene["revision"]},
    )
    assert prose.status_code == 200
    assert _timeline(client, project_id)["revision"] == before["revision"]

    db.reorder_scene(second.id, 0)
    assert _timeline(client, project_id)["revision"] != before["revision"]


def test_membership_only_command_publishes_only_timeline_changed():
    client, db, project_id = _project()
    scene = db.create_scene(project_id, "Scene")
    current = _timeline(client, project_id)
    cursor = client.app.state.broker.latest_id()

    response = _command(
        client,
        project_id,
        kind="place_event",
        expected_revision=current["revision"],
        scene_id=scene.id,
        lane_id=None,
    )

    assert response.status_code == 200
    assert [event["event"] for event in client.app.state.broker.events_since(
        cursor, project_id,
    )] == ["timeline_changed"]


def test_lane_assignment_publishes_scene_plot_and_timeline_changes():
    client, db, project_id = _project()
    scene = db.create_scene(project_id, "Scene")
    lane_result = _create_lane(
        client, project_id, _timeline(client, project_id), "Main",
    )
    lane = lane_result["timeline"]["lanes"][0]
    cursor = client.app.state.broker.latest_id()

    response = _command(
        client,
        project_id,
        kind="place_event",
        expected_revision=lane_result["timeline"]["revision"],
        scene_id=scene.id,
        lane_id=lane["id"],
    )

    assert response.status_code == 200
    assert response.json()["affected_scene_ids"] == [scene.id]
    assert [event["event"] for event in client.app.state.broker.events_since(
        cursor, project_id,
    )] == ["scene_changed", "plot_changed", "timeline_changed"]


def test_command_settings_rmw_preserves_unrelated_project_preferences():
    client, db, project_id = _project()
    db.save_project_settings(project_id, {
        "theme": "midnight",
        "nested": {"zoom": 1.25},
    })
    current = _timeline(client, project_id)

    created = _create_lane(client, project_id, current, "Main")

    assert created["changed"] is True
    settings = db.get_project_settings(project_id)
    assert settings["theme"] == "midnight"
    assert settings["nested"] == {"zoom": 1.25}


def test_update_lane_requires_at_least_one_patch_field():
    client, _db, project_id = _project()
    current = _timeline(client, project_id)
    lane = _create_lane(client, project_id, current, "Main")["timeline"]
    response = _command(
        client,
        project_id,
        kind="update_lane",
        expected_revision=lane["revision"],
        lane_id=lane["lanes"][0]["id"],
    )
    assert response.status_code == 422


def test_commands_reject_unscoped_fields_and_null_update_index():
    client, _db, project_id = _project()
    current = _timeline(client, project_id)
    lane = _create_lane(client, project_id, current, "Main")["timeline"]
    lane_id = lane["lanes"][0]["id"]

    unexpected = _command(
        client,
        project_id,
        kind="set_order_mode",
        expected_revision=lane["revision"],
        mode="custom",
        confirmed=True,
    )
    null_updates = [
        _command(
            client,
            project_id,
            kind="update_lane",
            expected_revision=lane["revision"],
            lane_id=lane_id,
            **{field: None},
        )
        for field in ("name", "color_label", "collapsed", "index")
    ]

    assert unexpected.status_code == 422
    assert all(response.status_code == 422 for response in null_updates)
    assert _timeline(client, project_id) == lane


@pytest.mark.parametrize(
    "case",
    [
        "create_index",
        "update_lane_id",
        "update_index",
        "delete_lane_id",
        "place_scene_id",
        "place_lane_id",
        "place_index",
        "remove_scene_id",
    ],
)
def test_command_integer_fields_reject_json_booleans(case: str):
    client, db, project_id = _project()
    scene = db.create_scene(project_id, "Scene")
    lane = db.create_timeline_lane(project_id, "Main")
    current = _timeline(client, project_id)
    bodies = {
        "create_index": {
            "kind": "create_lane", "name": "Other", "index": True,
        },
        "update_lane_id": {
            "kind": "update_lane", "lane_id": True, "name": "Renamed",
        },
        "update_index": {
            "kind": "update_lane", "lane_id": lane.id, "index": True,
        },
        "delete_lane_id": {
            "kind": "delete_lane", "lane_id": True,
        },
        "place_scene_id": {
            "kind": "place_event", "scene_id": True, "lane_id": lane.id,
        },
        "place_lane_id": {
            "kind": "place_event", "scene_id": scene.id, "lane_id": True,
        },
        "place_index": {
            "kind": "place_event", "scene_id": scene.id,
            "lane_id": lane.id, "index": True,
        },
        "remove_scene_id": {
            "kind": "remove_event", "scene_id": True,
        },
    }

    response = _command(
        client,
        project_id,
        expected_revision=current["revision"],
        **bodies[case],
    )

    assert response.status_code == 422
    assert _timeline(client, project_id) == current
