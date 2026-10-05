"""Transactional canonical story-structure authoring commands."""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from logosforge.api import create_api
from logosforge.db import Database


def _project(*, engine: str = "novel", path: str | None = None):
    db = Database(path)
    project = db.create_project(
        "Structure commands",
        narrative_engine=engine,
        default_writing_format=engine,
    )
    return TestClient(create_api(db=db)), db, project.id


def _structure(client: TestClient, project_id: int) -> dict:
    response = client.get(f"/api/projects/{project_id}/story-structure")
    assert response.status_code == 200
    return response.json()


def _command(client: TestClient, project_id: int, **body):
    return client.post(
        f"/api/projects/{project_id}/story-structure/commands",
        json=body,
    )


def _scene_ids(structure: dict) -> list[int]:
    return [
        scene["id"]
        for act in structure["acts"]
        for chapter in act["chapters"]
        for scene in chapter["scenes"]
    ]


def test_create_commands_seed_and_insert_at_explicit_canonical_positions():
    client, _db, project_id = _project()
    current = _structure(client, project_id)

    act_two = _command(
        client,
        project_id,
        kind="create_act",
        expected_revision=current["revision"],
        act="Act II",
        index=0,
    ).json()
    assert act_two["changed"] is True
    assert act_two["affected_scene_ids"] == [act_two["created_scene_id"]]

    act_one = _command(
        client,
        project_id,
        kind="create_act",
        expected_revision=act_two["structure"]["revision"],
        act="Act I",
        chapter="Opening",
        title="Act seed",
        index=0,
    ).json()
    assert [act["name"] for act in act_one["structure"]["acts"]] == [
        "Act I",
        "Act II",
    ]

    chapter = _command(
        client,
        project_id,
        kind="create_chapter",
        expected_revision=act_one["structure"]["revision"],
        act="Act I",
        chapter="Prologue",
        title="Chapter seed",
        index=0,
    ).json()
    act = chapter["structure"]["acts"][0]
    assert [row["name"] for row in act["chapters"]] == ["Prologue", "Opening"]

    scene = _command(
        client,
        project_id,
        kind="create_scene",
        expected_revision=chapter["structure"]["revision"],
        act="Act I",
        chapter="Prologue",
        title="Before the seed",
        index=0,
    ).json()
    prologue = scene["structure"]["acts"][0]["chapters"][0]
    assert [row["title"] for row in prologue["scenes"]] == [
        "Before the seed",
        "Chapter seed",
    ]
    assert scene["created_scene_id"] == prologue["scenes"][0]["id"]


def test_flat_mode_uses_empty_chapter_as_valid_synthetic_parent():
    client, db, project_id = _project(engine="screenplay")
    current = _structure(client, project_id)

    seeded = _command(
        client,
        project_id,
        kind="create_act",
        expected_revision=current["revision"],
        act="Act I",
        index=0,
    ).json()
    seed_id = seeded["created_scene_id"]
    assert db.get_scene_by_id(seed_id).chapter == ""
    assert seeded["structure"]["orphan_count"] == 0

    created = _command(
        client,
        project_id,
        kind="create_scene",
        expected_revision=seeded["structure"]["revision"],
        act="Act I",
        chapter="",
        title="Second",
        index=1,
    )
    assert created.status_code == 200
    assert created.json()["structure"]["orphan_count"] == 0

    rejected = _command(
        client,
        project_id,
        kind="create_chapter",
        expected_revision=created.json()["structure"]["revision"],
        act="Act I",
        chapter="Not canonical here",
        index=0,
    )
    assert rejected.status_code == 400


def test_rename_detach_and_repair_preserve_every_scene_body():
    client, db, project_id = _project()
    first = db.create_scene(
        project_id, "First", act="Act I", chapter="One", content="BODY ONE",
    )
    second = db.create_scene(
        project_id, "Second", act="Act I", chapter="One", content="BODY TWO",
    )
    current = _structure(client, project_id)

    renamed_act = _command(
        client,
        project_id,
        kind="rename_act",
        expected_revision=current["revision"],
        act="Act I",
        new_name="Act Alpha",
    ).json()
    assert renamed_act["affected_scene_ids"] == [first.id, second.id]

    renamed_chapter = _command(
        client,
        project_id,
        kind="rename_chapter",
        expected_revision=renamed_act["structure"]["revision"],
        act="Act Alpha",
        chapter="One",
        new_name="Opening",
    ).json()
    detached = _command(
        client,
        project_id,
        kind="detach_act",
        expected_revision=renamed_chapter["structure"]["revision"],
        act="Act Alpha",
    ).json()
    assert detached["structure"]["orphan_count"] == 2
    assert [
        db.get_scene_by_id(scene_id).chapter
        for scene_id in (first.id, second.id)
    ] == [
        "Opening",
        "Opening",
    ]

    repaired = _command(
        client,
        project_id,
        kind="repair_orphans",
        expected_revision=detached["structure"]["revision"],
    ).json()
    assert repaired["affected_scene_ids"] == [first.id, second.id]
    assert repaired["structure"]["orphan_count"] == 0
    assert [
        db.get_scene_by_id(scene_id).content
        for scene_id in (first.id, second.id)
    ] == [
        "BODY ONE",
        "BODY TWO",
    ]

    no_op = _command(
        client,
        project_id,
        kind="repair_orphans",
        expected_revision=repaired["structure"]["revision"],
    ).json()
    assert no_op == {
        "structure": repaired["structure"],
        "changed": False,
        "created_scene_id": None,
        "affected_scene_ids": [],
    }


def test_delete_scene_is_guarded_dense_and_publishes_delete_events():
    client, db, project_id = _project()
    first = db.create_scene(project_id, "First", act="Act I", chapter="One")
    doomed = db.create_scene(project_id, "Doomed", act="Act I", chapter="One")
    last = db.create_scene(project_id, "Last", act="Act I", chapter="One")
    current = _structure(client, project_id)
    cursor = client.app.state.broker.latest_id()

    response = _command(
        client,
        project_id,
        kind="delete_scene",
        expected_revision=current["revision"],
        scene_id=doomed.id,
    )

    assert response.status_code == 200
    result = response.json()
    assert result["created_scene_id"] is None
    assert result["affected_scene_ids"] == [doomed.id]
    assert _scene_ids(result["structure"]) == [first.id, last.id]
    assert db.get_scene_by_id(doomed.id) is None
    assert [row.sort_order for row in db.get_all_scenes(project_id)] == [0, 1]
    assert [event["event"] for event in client.app.state.broker.events_since(
        cursor, project_id,
    )] == [
        "scenes_changed",
        "comments_changed",
        "notes_changed",
        "psyke_changed",
        "outline_changed",
        "timeline_changed",
        "plot_changed",
        "canvas_plot_changed",
        "project_data_changed",
    ]


def test_stale_revision_rejects_without_partial_group_mutation_or_events():
    client, db, project_id = _project()
    first = db.create_scene(project_id, "First", act="Act I", chapter="One")
    second = db.create_scene(project_id, "Second", act="Act I", chapter="One")
    stale = _structure(client, project_id)["revision"]
    db.create_scene(project_id, "Concurrent", act="Act II", chapter="Two")
    before = [
        (scene.id, scene.act, scene.chapter, scene.content, scene.sort_order)
        for scene in db.get_all_scenes(project_id)
    ]
    cursor = client.app.state.broker.latest_id()

    response = _command(
        client,
        project_id,
        kind="rename_act",
        expected_revision=stale,
        act="Act I",
        new_name="Should Not Appear",
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "structure_conflict"
    assert [
        (scene.id, scene.act, scene.chapter, scene.content, scene.sort_order)
        for scene in db.get_all_scenes(project_id)
    ] == before
    assert db.get_scene_by_id(first.id).act == "Act I"
    assert db.get_scene_by_id(second.id).act == "Act I"
    assert client.app.state.broker.events_since(cursor, project_id) == []


def test_sql_failure_rolls_back_every_member_of_group_rename():
    _client, db, project_id = _project()
    first = db.create_scene(project_id, "First", act="Act I", chapter="One")
    second = db.create_scene(project_id, "Second", act="Act I", chapter="One")
    note = db.create_note(project_id, "Act note")
    db.add_note_structure_link(note.id, project_id, "act", "Act I")
    db.add_timeline_structure_link(project_id, first.id, "act", "Act I")
    db.save_project_settings(project_id, {
        "act_summaries": {"Act I": "Must roll back together"},
    })
    snapshot = db.read_story_structure_snapshot(project_id)
    assert snapshot is not None

    with db._engine.begin() as connection:
        connection.execute(text(f"""
            CREATE TRIGGER reject_second_act_rename
            BEFORE UPDATE OF act ON scene
            WHEN OLD.id = {second.id}
            BEGIN
                SELECT RAISE(ABORT, 'forced group rollback');
            END;
        """))
    try:
        with pytest.raises(IntegrityError):
            db.execute_story_structure_command(
                project_id,
                kind="rename_act",
                expected_revision=snapshot.revision,
                act="Act I",
                new_name="Act Renamed",
            )
    finally:
        with db._engine.begin() as connection:
            connection.execute(text("DROP TRIGGER reject_second_act_rename"))

    assert [(row.id, row.act) for row in db.get_all_scenes(project_id)] == [
        (first.id, "Act I"),
        (second.id, "Act I"),
    ]
    assert db.get_project_settings(project_id)["act_summaries"] == {
        "Act I": "Must roll back together",
    }
    assert db.get_note_structure_links(note.id) == [("act", "Act I")]
    assert [
        (link.target_type, link.target_ref)
        for link in db.get_timeline_structure_links(first.id)
    ] == [("act", "Act I")]
    assert db.read_story_structure_snapshot(project_id).revision == snapshot.revision


def test_concurrent_commands_serialize_one_winner_and_one_stale_conflict(tmp_path):
    client, db, project_id = _project(path=str(tmp_path / "commands.db"))
    db.create_scene(project_id, "Scene", act="Act I", chapter="One")
    revision = _structure(client, project_id)["revision"]
    barrier = threading.Barrier(3)
    responses = []

    def rename(new_name: str) -> None:
        barrier.wait()
        responses.append(_command(
            client,
            project_id,
            kind="rename_act",
            expected_revision=revision,
            act="Act I",
            new_name=new_name,
        ))

    one = threading.Thread(target=rename, args=("Winner A",))
    two = threading.Thread(target=rename, args=("Winner B",))
    one.start()
    two.start()
    barrier.wait()
    one.join(timeout=5)
    two.join(timeout=5)

    assert not one.is_alive() and not two.is_alive()
    assert sorted(response.status_code for response in responses) == [200, 409]
    stored = db.get_all_scenes(project_id)
    assert len(stored) == 1
    assert stored[0].act in {"Winner A", "Winner B"}


def test_content_patch_started_before_group_rename_cannot_restore_old_parent(
    monkeypatch,
):
    client, db, project_id = _project()
    scene = db.create_scene(
        project_id, "Before", act="Act I", chapter="One", content="Body",
    )
    structure_revision = _structure(client, project_id)["revision"]
    scene_revision = client.get(
        f"/api/projects/{project_id}/scenes/{scene.id}"
    ).json()["revision"]

    patch_has_read = threading.Event()
    allow_patch_write = threading.Event()
    original_update = db.update_scene

    def paused_update(*args, **kwargs):
        patch_has_read.set()
        assert allow_patch_write.wait(3)
        return original_update(*args, **kwargs)

    monkeypatch.setattr(db, "update_scene", paused_update)
    responses: dict[str, object] = {}

    def patch_scene() -> None:
        responses["patch"] = client.patch(
            f"/api/projects/{project_id}/scenes/{scene.id}",
            json={"title": "After", "expected_revision": scene_revision},
        )

    patch_thread = threading.Thread(target=patch_scene)
    patch_thread.start()
    assert patch_has_read.wait(3)

    responses["rename"] = _command(
        client,
        project_id,
        kind="rename_act",
        expected_revision=structure_revision,
        act="Act I",
        new_name="Act Renamed",
    )
    allow_patch_write.set()
    patch_thread.join(timeout=5)

    assert not patch_thread.is_alive()
    assert responses["rename"].status_code == 200
    assert responses["patch"].status_code == 200
    stored = db.get_scene_by_id(scene.id)
    assert (stored.title, stored.act, stored.chapter, stored.content) == (
        "After",
        "Act Renamed",
        "One",
        "Body",
    )


def test_series_create_validates_episode_ownership_before_any_mutation():
    client, db, project_id = _project(engine="series")
    season = db.create_season(project_id, season_number=1)
    episode = db.create_episode(season.id, project_id=project_id, episode_number=1)
    foreign_project = db.create_project("Foreign", narrative_engine="series")
    foreign_season = db.create_season(foreign_project.id, season_number=1)
    foreign_episode = db.create_episode(
        foreign_season.id,
        project_id=foreign_project.id,
        episode_number=1,
    )
    initial = _structure(client, project_id)

    rejected = _command(
        client,
        project_id,
        kind="create_act",
        expected_revision=initial["revision"],
        act="Act I",
        index=0,
        episode_id=foreign_episode.id,
    )
    assert rejected.status_code == 404
    assert db.get_all_scenes(project_id) == []
    assert _structure(client, project_id)["revision"] == initial["revision"]

    created = _command(
        client,
        project_id,
        kind="create_act",
        expected_revision=initial["revision"],
        act="Act I",
        index=0,
        episode_id=episode.id,
    )
    assert created.status_code == 200
    stored = db.get_scene_by_id(created.json()["created_scene_id"])
    assert stored.episode_id == episode.id
    assert stored.chapter == "Chapter 1"


def test_scene_patch_rejects_explicit_structural_fields_with_actionable_error():
    client, db, project_id = _project()
    scene = db.create_scene(project_id, "Scene", act="Act I", chapter="One")
    revision = client.get(
        f"/api/projects/{project_id}/scenes/{scene.id}"
    ).json()["revision"]

    response = client.patch(
        f"/api/projects/{project_id}/scenes/{scene.id}",
        json={"act": "Act II", "expected_revision": revision},
    )

    assert response.status_code == 400
    assert "story-structure" in response.json()["error"]["message"]
    assert db.get_scene_by_id(scene.id).act == "Act I"


def test_scene_patch_openapi_marks_legacy_structural_fields_rejected():
    client, _db, _project_id = _project()

    properties = client.get("/openapi.json").json()["components"]["schemas"][
        "SceneUpdateDTO"
    ]["properties"]

    for field in ("act", "chapter", "sort_order"):
        assert properties[field]["deprecated"] is True
        assert "Rejected by Scene PATCH" in properties[field]["description"]


def test_series_group_commands_are_episode_scoped_with_equal_labels():
    client, db, project_id = _project(engine="series")
    season = db.create_season(project_id, season_number=1)
    episode_one = db.create_episode(
        season.id, project_id=project_id, episode_number=1,
    )
    episode_two = db.create_episode(
        season.id, project_id=project_id, episode_number=2,
    )
    first = db.create_scene(
        project_id, "E1", act="Act I", chapter="One",
        episode_id=episode_one.id,
    )
    second = db.create_scene(
        project_id, "E2", act="Act I", chapter="One",
        episode_id=episode_two.id,
    )
    unassigned = db.create_scene(
        project_id, "Unassigned", act="Act I", chapter="One",
    )

    current = _structure(client, project_id)
    renamed_act = _command(
        client,
        project_id,
        kind="rename_act",
        expected_revision=current["revision"],
        act="Act I",
        new_name="Act Alpha",
        episode_id=episode_one.id,
    ).json()
    assert renamed_act["affected_scene_ids"] == [first.id]
    assert db.get_scene_by_id(first.id).act == "Act Alpha"
    assert db.get_scene_by_id(second.id).act == "Act I"
    assert db.get_scene_by_id(unassigned.id).act == "Act I"

    renamed_chapter = _command(
        client,
        project_id,
        kind="rename_chapter",
        expected_revision=renamed_act["structure"]["revision"],
        act="Act Alpha",
        chapter="One",
        new_name="Opening",
        episode_id=episode_one.id,
    ).json()
    assert renamed_chapter["affected_scene_ids"] == [first.id]
    assert db.get_scene_by_id(first.id).chapter == "Opening"
    assert db.get_scene_by_id(second.id).chapter == "One"

    detached_chapter = _command(
        client,
        project_id,
        kind="detach_chapter",
        expected_revision=renamed_chapter["structure"]["revision"],
        act="Act Alpha",
        chapter="Opening",
        episode_id=episode_one.id,
    ).json()
    assert detached_chapter["affected_scene_ids"] == [first.id]
    assert db.get_scene_by_id(first.id).chapter == ""
    assert db.get_scene_by_id(second.id).chapter == "One"

    repaired = _command(
        client,
        project_id,
        kind="repair_orphans",
        expected_revision=detached_chapter["structure"]["revision"],
    ).json()
    detached_act = _command(
        client,
        project_id,
        kind="detach_act",
        expected_revision=repaired["structure"]["revision"],
        act="Act Alpha",
        episode_id=episode_one.id,
    ).json()
    assert detached_act["affected_scene_ids"] == [first.id]
    assert db.get_scene_by_id(first.id).act == ""
    assert (
        db.get_scene_by_id(second.id).act,
        db.get_scene_by_id(second.id).chapter,
    ) == (
        "Act I",
        "One",
    )

    # Omitting episode_id intentionally scopes a Series group command to
    # episode-less scenes rather than every Episode sharing the same label.
    renamed_unassigned = _command(
        client,
        project_id,
        kind="rename_act",
        expected_revision=detached_act["structure"]["revision"],
        act="Act I",
        new_name="Unassigned Act",
    ).json()
    assert renamed_unassigned["affected_scene_ids"] == [unassigned.id]
    assert db.get_scene_by_id(second.id).act == "Act I"


def test_series_create_commands_scope_groups_and_indices_to_episode():
    client, db, project_id = _project(engine="series")
    season = db.create_season(project_id, season_number=1)
    episode_one = db.create_episode(
        season.id, project_id=project_id, episode_number=1,
    )
    episode_two = db.create_episode(
        season.id, project_id=project_id, episode_number=2,
    )
    db.create_scene(
        project_id, "E1 seed", act="Act I", chapter="One",
        episode_id=episode_one.id,
    )
    exclusive = db.create_scene(
        project_id, "E2 exclusive", act="Exclusive", chapter="Only E2",
        episode_id=episode_two.id,
    )
    db.create_scene(
        project_id, "E2 seed", act="Act I", chapter="One",
        episode_id=episode_two.id,
    )
    current = _structure(client, project_id)

    missing_destination = _command(
        client,
        project_id,
        kind="create_scene",
        expected_revision=current["revision"],
        act="Exclusive",
        chapter="Only E2",
        title="Must not cross Episode",
        index=1,
        episode_id=episode_one.id,
    )
    assert missing_destination.status_code == 400
    assert db.get_scene_by_id(exclusive.id).title == "E2 exclusive"

    first_act = _command(
        client,
        project_id,
        kind="create_act",
        expected_revision=current["revision"],
        act="Act II",
        index=1,
        episode_id=episode_one.id,
    ).json()
    second_act = _command(
        client,
        project_id,
        kind="create_act",
        expected_revision=first_act["structure"]["revision"],
        act="Act II",
        index=2,
        episode_id=episode_two.id,
    ).json()
    assert db.get_scene_by_id(first_act["created_scene_id"]).chapter == "Chapter 1"
    assert db.get_scene_by_id(second_act["created_scene_id"]).chapter == "Chapter 1"

    first_chapter = _command(
        client,
        project_id,
        kind="create_chapter",
        expected_revision=second_act["structure"]["revision"],
        act="Act I",
        chapter="Two",
        index=1,
        episode_id=episode_one.id,
    ).json()
    second_chapter = _command(
        client,
        project_id,
        kind="create_chapter",
        expected_revision=first_chapter["structure"]["revision"],
        act="Act I",
        chapter="Two",
        index=1,
        episode_id=episode_two.id,
    )
    assert second_chapter.status_code == 200


def test_series_requires_chapter_for_orphans_create_and_repair():
    client, db, project_id = _project(engine="series")
    season = db.create_season(project_id, season_number=1)
    episode = db.create_episode(
        season.id, project_id=project_id, episode_number=1,
    )
    orphan = db.create_scene(
        project_id, "Legacy orphan", act="Act I", chapter="",
        episode_id=episode.id,
    )
    current = _structure(client, project_id)
    assert current["chapter_level"] is False
    assert current["orphan_count"] == 1

    repaired = _command(
        client,
        project_id,
        kind="repair_orphans",
        expected_revision=current["revision"],
    ).json()
    assert repaired["affected_scene_ids"] == [orphan.id]
    assert db.get_scene_by_id(orphan.id).chapter == "Recovered Chapter"
    assert repaired["structure"]["orphan_count"] == 0

    blank_chapter = _command(
        client,
        project_id,
        kind="create_scene",
        expected_revision=repaired["structure"]["revision"],
        act="Act I",
        chapter="",
        index=0,
        episode_id=episode.id,
    )
    assert blank_chapter.status_code == 400


def test_non_series_rejects_non_null_episode_scope():
    client, db, project_id = _project()
    db.create_scene(project_id, "Scene", act="Act I", chapter="One")
    current = _structure(client, project_id)

    response = _command(
        client,
        project_id,
        kind="rename_act",
        expected_revision=current["revision"],
        act="Act I",
        new_name="Act Alpha",
        episode_id=999,
    )

    assert response.status_code == 400
    assert db.get_all_scenes(project_id)[0].act == "Act I"


def test_group_rename_and_detach_migrate_name_keyed_metadata_and_events():
    client, db, project_id = _project()
    scene = db.create_scene(
        project_id, "Scene", act="Act I", chapter="One",
    )
    note = db.create_note(project_id, "Structure note")
    db.add_note_structure_link(note.id, project_id, "act", "Act I")
    db.add_note_structure_link(note.id, project_id, "chapter", "One")
    db.add_timeline_structure_link(project_id, scene.id, "act", "Act I")
    db.add_timeline_structure_link(project_id, scene.id, "chapter", "One")
    db.save_project_settings(project_id, {
        "act_summaries": {"Act I": "Act summary"},
        "chapter_summaries": {"One": "Chapter summary"},
        "preserved": True,
    })
    current = _structure(client, project_id)
    cursor = client.app.state.broker.latest_id()

    renamed_act = _command(
        client,
        project_id,
        kind="rename_act",
        expected_revision=current["revision"],
        act="Act I",
        new_name="Act Alpha",
    ).json()
    settings = db.get_project_settings(project_id)
    assert settings["act_summaries"] == {"Act Alpha": "Act summary"}
    assert settings["preserved"] is True
    assert ("act", "Act Alpha") in db.get_note_structure_links(note.id)
    assert ("act", "Act I") not in db.get_note_structure_links(note.id)
    assert [
        (link.target_type, link.target_ref)
        for link in db.get_timeline_structure_links(scene.id)
        if link.target_type == "act"
    ] == [("act", "Act Alpha")]
    assert [event["event"] for event in client.app.state.broker.events_since(
        cursor, project_id,
    )] == [
        "scene_changed",
        "scenes_changed",
        "project_data_changed",
        "notes_changed",
        "timeline_changed",
    ]

    renamed_chapter = _command(
        client,
        project_id,
        kind="rename_chapter",
        expected_revision=renamed_act["structure"]["revision"],
        act="Act Alpha",
        chapter="One",
        new_name="Opening",
    ).json()
    assert db.get_project_settings(project_id)["chapter_summaries"] == {
        "Opening": "Chapter summary",
    }
    assert ("chapter", "Opening") in db.get_note_structure_links(note.id)

    detached_chapter = _command(
        client,
        project_id,
        kind="detach_chapter",
        expected_revision=renamed_chapter["structure"]["revision"],
        act="Act Alpha",
        chapter="Opening",
    ).json()
    assert db.get_project_settings(project_id)["chapter_summaries"] == {}
    assert all(
        target_type != "chapter"
        for target_type, _target_ref in db.get_note_structure_links(note.id)
    )

    _command(
        client,
        project_id,
        kind="detach_act",
        expected_revision=detached_chapter["structure"]["revision"],
        act="Act Alpha",
    )
    assert db.get_project_settings(project_id)["act_summaries"] == {}
    assert db.get_note_structure_links(note.id) == []
    assert db.get_timeline_structure_links(scene.id) == []


def test_series_metadata_stays_global_until_last_label_reference_moves():
    client, db, project_id = _project(engine="series")
    season = db.create_season(project_id, season_number=1)
    episode_one = db.create_episode(
        season.id, project_id=project_id, episode_number=1,
    )
    episode_two = db.create_episode(
        season.id, project_id=project_id, episode_number=2,
    )
    first = db.create_scene(
        project_id, "E1", act="Shared Act", chapter="Shared Chapter",
        episode_id=episode_one.id,
    )
    second = db.create_scene(
        project_id, "E2", act="Shared Act", chapter="Shared Chapter",
        episode_id=episode_two.id,
    )
    note = db.create_note(project_id, "Shared structure note")
    db.add_note_structure_link(note.id, project_id, "act", "Shared Act")
    db.add_note_structure_link(note.id, project_id, "chapter", "Shared Chapter")
    db.add_timeline_structure_link(
        project_id, first.id, "act", "Shared Act",
    )
    db.add_timeline_structure_link(
        project_id, first.id, "chapter", "Shared Chapter",
    )
    db.save_project_settings(project_id, {
        "act_summaries": {"Shared Act": "Act summary"},
        "chapter_summaries": {"Shared Chapter": "Chapter summary"},
    })
    current = _structure(client, project_id)

    first_act = _command(
        client,
        project_id,
        kind="rename_act",
        expected_revision=current["revision"],
        act="Shared Act",
        new_name="Renamed Act",
        episode_id=episode_one.id,
    ).json()
    first_chapter = _command(
        client,
        project_id,
        kind="rename_chapter",
        expected_revision=first_act["structure"]["revision"],
        act="Renamed Act",
        chapter="Shared Chapter",
        new_name="Renamed Chapter",
        episode_id=episode_one.id,
    ).json()
    # E2 still owns both old labels, so project-global name keys stay put.
    assert (
        db.get_scene_by_id(second.id).act,
        db.get_scene_by_id(second.id).chapter,
    ) == (
        "Shared Act",
        "Shared Chapter",
    )
    settings = db.get_project_settings(project_id)
    assert settings["act_summaries"] == {"Shared Act": "Act summary"}
    assert settings["chapter_summaries"] == {
        "Shared Chapter": "Chapter summary",
    }
    assert ("act", "Shared Act") in db.get_note_structure_links(note.id)
    assert ("chapter", "Shared Chapter") in db.get_note_structure_links(note.id)

    second_act = _command(
        client,
        project_id,
        kind="rename_act",
        expected_revision=first_chapter["structure"]["revision"],
        act="Shared Act",
        new_name="Renamed Act",
        episode_id=episode_two.id,
    ).json()
    _command(
        client,
        project_id,
        kind="rename_chapter",
        expected_revision=second_act["structure"]["revision"],
        act="Renamed Act",
        chapter="Shared Chapter",
        new_name="Renamed Chapter",
        episode_id=episode_two.id,
    )
    settings = db.get_project_settings(project_id)
    assert settings["act_summaries"] == {"Renamed Act": "Act summary"}
    assert settings["chapter_summaries"] == {
        "Renamed Chapter": "Chapter summary",
    }
    assert db.get_note_structure_links(note.id) == [
        ("act", "Renamed Act"),
        ("chapter", "Renamed Chapter"),
    ]


def test_group_metadata_migration_preserves_concurrent_settings_patch():
    client, db, project_id = _project()
    db.create_scene(project_id, "Scene", act="Act I", chapter="One")
    db.save_project_settings(project_id, {
        "act_summaries": {"Act I": "Summary"},
    })
    revision = _structure(client, project_id)["revision"]
    response: dict[str, object] = {}

    def rename() -> None:
        response["value"] = _command(
            client,
            project_id,
            kind="rename_act",
            expected_revision=revision,
            act="Act I",
            new_name="Act Alpha",
        )

    with db._settings_lock:
        thread = threading.Thread(target=rename)
        thread.start()
        db.patch_project_settings(project_id, {"concurrent": "preserved"})
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert response["value"].status_code == 200
    assert db.get_project_settings(project_id) == {
        "act_summaries": {"Act Alpha": "Summary"},
        "concurrent": "preserved",
    }


def test_delete_scrubs_scene_references_and_invalidates_survivors():
    client, db, project_id = _project(engine="screenplay")
    doomed = db.create_scene(project_id, "Doomed", act="Act I")
    survivor = db.create_scene(
        project_id,
        "Survivor",
        act="Act I",
        setup_payoff_links=(
            f"{doomed.id}, {doomed.id}0, note {doomed.id}, {doomed.id}"
        ),
    )
    untouched = db.create_scene(
        project_id,
        "Untouched",
        act="Act I",
        setup_payoff_links=f"{doomed.id}0",
    )
    source_link = db.create_story_link(
        project_id,
        source_type="scene",
        source_id=str(doomed.id),
        source_scene_id=doomed.id,
        target_type="scene",
        target_id=str(survivor.id),
        target_scene_id=survivor.id,
    )
    target_link = db.create_story_link(
        project_id,
        source_type="scene",
        source_id=str(survivor.id),
        source_scene_id=survivor.id,
        target_type="scene",
        target_id=str(doomed.id),
        target_scene_id=doomed.id,
    )
    unrelated_link = db.create_story_link(
        project_id,
        source_type="psyke",
        source_id=str(doomed.id),
        target_type="scene",
        target_id=str(survivor.id),
        target_scene_id=survivor.id,
    )
    unrelated_updated_at = unrelated_link.updated_at
    current = _structure(client, project_id)
    cursor = client.app.state.broker.latest_id()

    response = _command(
        client,
        project_id,
        kind="delete_scene",
        expected_revision=current["revision"],
        scene_id=doomed.id,
    )

    assert response.status_code == 200
    assert response.json()["affected_scene_ids"] == [doomed.id, survivor.id]
    assert db.get_scene_by_id(survivor.id).setup_payoff_links == (
        f"{doomed.id}0, note {doomed.id}"
    )
    assert db.get_scene_by_id(untouched.id).setup_payoff_links == f"{doomed.id}0"
    links = {link.id: link for link in db.get_story_links(project_id)}
    assert (
        links[source_link.id].source_type,
        links[source_link.id].source_id,
        links[source_link.id].source_scene_id,
    ) == ("", "", None)
    assert links[source_link.id].target_scene_id == survivor.id
    assert (
        links[target_link.id].target_type,
        links[target_link.id].target_id,
        links[target_link.id].target_scene_id,
    ) == ("", "", None)
    assert links[target_link.id].source_scene_id == survivor.id
    assert (
        links[unrelated_link.id].source_type,
        links[unrelated_link.id].source_id,
        links[unrelated_link.id].updated_at,
    ) == ("psyke", str(doomed.id), unrelated_updated_at)
    events = client.app.state.broker.events_since(cursor, project_id)
    assert events[0]["event"] == "scene_changed"
    assert events[0]["data"]["scene_id"] == survivor.id
    assert [event["event"] for event in events[1:]] == [
        "scenes_changed",
        "comments_changed",
        "notes_changed",
        "psyke_changed",
        "outline_changed",
        "timeline_changed",
        "plot_changed",
        "canvas_plot_changed",
        "project_data_changed",
    ]


def test_delete_does_not_scrub_story_links_owned_by_another_project():
    client, db, project_id = _project(engine="screenplay")
    doomed = db.create_scene(project_id, "Doomed", act="Act I")
    foreign_project = db.create_project(
        "Foreign screenplay", narrative_engine="screenplay",
    )
    foreign_link = db.create_story_link(
        foreign_project.id,
        source_type=" scene ",
        source_id=f" {doomed.id} ",
        source_scene_id=doomed.id,
        source_block_index=3,
        target_type="scene",
        target_id=str(doomed.id),
        target_scene_id=doomed.id,
        target_block_index=5,
        evidence="Foreign project evidence",
    )
    before = foreign_link.model_dump()
    current = _structure(client, project_id)

    response = _command(
        client,
        project_id,
        kind="delete_scene",
        expected_revision=current["revision"],
        scene_id=doomed.id,
    )

    assert response.status_code == 200
    persisted = db.get_story_link_by_id(foreign_link.id)
    assert persisted is not None
    assert persisted.model_dump() == before


def test_legacy_scene_delete_scrubs_and_invalidates_survivors():
    client, db, project_id = _project(engine="screenplay")
    doomed = db.create_scene(project_id, "Doomed", act="Act I")
    survivor = db.create_scene(
        project_id,
        "Survivor",
        act="Act I",
        setup_payoff_links=str(doomed.id),
    )
    cursor = client.app.state.broker.latest_id()

    response = client.delete(
        f"/api/projects/{project_id}/scenes/{doomed.id}"
    )

    assert response.status_code == 200
    assert db.get_scene_by_id(survivor.id).setup_payoff_links == ""
    events = client.app.state.broker.events_since(cursor, project_id)
    assert events[0]["event"] == "scene_changed"
    assert events[0]["data"]["scene_id"] == survivor.id
    assert [event["event"] for event in events[1:]] == [
        "scenes_changed",
        "comments_changed",
        "notes_changed",
        "psyke_changed",
        "outline_changed",
        "timeline_changed",
        "plot_changed",
        "canvas_plot_changed",
        "project_data_changed",
    ]
