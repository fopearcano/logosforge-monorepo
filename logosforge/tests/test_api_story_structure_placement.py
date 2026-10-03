"""Transactional canonical Scene placement API."""

from __future__ import annotations

import re
import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError

from logosforge.api import create_api
from logosforge.db import Database


def _project(*, engine: str = "novel", path: str | None = None):
    db = Database(path)
    project = db.create_project(
        "Structure placement",
        narrative_engine=engine,
        default_writing_format="series" if engine == "series" else engine,
    )
    client = TestClient(create_api(db=db))
    return client, db, project.id


def _structure(client: TestClient, project_id: int) -> dict:
    response = client.get(f"/api/projects/{project_id}/story-structure")
    assert response.status_code == 200
    return response.json()


def _scenes(structure: dict) -> list[dict]:
    return [
        scene
        for act in structure["acts"]
        for chapter in act["chapters"]
        for scene in chapter["scenes"]
    ]


def _put(
    client: TestClient,
    project_id: int,
    scene_id: int,
    revision: str,
    *,
    act: str,
    chapter: str,
    index: int,
    episode_id=...,
):
    body = {
        "expected_revision": revision,
        "act": act,
        "chapter": chapter,
        "index": index,
    }
    if episode_id is not ...:
        body["episode_id"] = episode_id
    return client.put(
        f"/api/projects/{project_id}/story-structure/scenes/{scene_id}/placement",
        json=body,
    )


def test_same_group_move_is_adjacent_dense_and_publishes_both_events():
    client, db, project_id = _project()
    first = db.create_scene(project_id, "First", act="Act I", chapter="One")
    middle = db.create_scene(project_id, "Middle", act="Act I", chapter="One")
    last = db.create_scene(project_id, "Last", act="Act I", chapter="One")
    before = _structure(client, project_id)
    cursor = client.app.state.broker.latest_id()

    response = _put(
        client, project_id, middle.id, before["revision"],
        act="Act I", chapter="One", index=2,
    )

    assert response.status_code == 200
    body = response.json()
    assert [row["id"] for row in _scenes(body)] == [first.id, last.id, middle.id]
    assert body["revision"] != before["revision"]
    assert [scene.sort_order for scene in db.get_all_scenes(project_id)] == [0, 1, 2]
    events = client.app.state.broker.events_since(cursor, project_id)
    assert [(event["event"], event["data"]) for event in events] == [
        ("scene_changed", {"scene_id": middle.id}),
        ("scenes_changed", {}),
    ]

    # One adjacent step back uses the sibling index after removing the source.
    response = _put(
        client, project_id, middle.id, body["revision"],
        act="Act I", chapter="One", index=1,
    )
    assert [row["id"] for row in _scenes(response.json())] == [
        first.id, middle.id, last.id,
    ]


def test_cross_parent_move_preserves_canonical_groups_and_unassigned_last():
    client, db, project_id = _project()
    loose = db.create_scene(project_id, "Loose")
    source = db.create_scene(project_id, "Source", act="Act I", chapter="One")
    target_a = db.create_scene(project_id, "Target A", act="Act II", chapter="Two")
    target_b = db.create_scene(project_id, "Target B", act="Act II", chapter="Two")

    before = _structure(client, project_id)
    response = _put(
        client, project_id, source.id, before["revision"],
        act="  Act II ", chapter=" Two  ", index=1,
    )

    assert response.status_code == 200
    body = response.json()
    assert [row["id"] for row in _scenes(body)] == [
        target_a.id, source.id, target_b.id, loose.id,
    ]
    stored = db.get_scene_by_id(source.id)
    assert (stored.act, stored.chapter) == ("Act II", "Two")
    assert body["acts"][-1]["name"] == "Unassigned"

    # The public sentinel is translated back to empty stored labels and its
    # canonical bucket remains last regardless of the requested sibling index.
    response = _put(
        client, project_id, source.id, body["revision"],
        act="Unassigned", chapter="Unassigned", index=0,
    )
    assert response.status_code == 200
    stored = db.get_scene_by_id(source.id)
    assert (stored.act, stored.chapter) == ("", "")
    assert [row["id"] for row in _scenes(response.json())][-2:] == [
        source.id, loose.id,
    ]


def test_stale_revision_rejects_even_a_now_apparent_no_op_without_events():
    client, db, project_id = _project()
    first = db.create_scene(project_id, "First", act="Act I", chapter="One")
    second = db.create_scene(project_id, "Second", act="Act I", chapter="One")
    stale = _structure(client, project_id)["revision"]
    db.reorder_scene(second.id, 0)
    before_rows = [scene.id for scene in db.get_all_scenes(project_id)]
    cursor = client.app.state.broker.latest_id()

    response = _put(
        client, project_id, second.id, stale,
        act="Act I", chapter="One", index=0,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "structure_conflict"
    assert [scene.id for scene in db.get_all_scenes(project_id)] == before_rows
    assert client.app.state.broker.events_since(cursor, project_id) == []
    assert first.id in before_rows


def test_exact_no_op_preserves_revision_raw_orders_and_emits_nothing():
    client, db, project_id = _project()
    db.create_scene(project_id, "First", act="Act I", chapter="One")
    middle = db.create_scene(project_id, "Middle", act="Act I", chapter="One")
    db.create_scene(project_id, "Last", act="Act I", chapter="One")
    before = _structure(client, project_id)
    raw_before = [
        (scene.id, scene.sort_order) for scene in db.get_all_scenes(project_id)
    ]
    cursor = client.app.state.broker.latest_id()

    response = _put(
        client, project_id, middle.id, before["revision"],
        act=" Act I ", chapter=" One ", index=1,
    )

    assert response.status_code == 200
    assert response.json()["revision"] == before["revision"]
    assert [
        (scene.id, scene.sort_order) for scene in db.get_all_scenes(project_id)
    ] == raw_before
    assert client.app.state.broker.events_since(cursor, project_id) == []


def test_foreign_scene_and_invalid_destination_leave_project_unchanged():
    client, db, project_id = _project()
    source = db.create_scene(project_id, "Source", act="Act I", chapter="One")
    sibling = db.create_scene(project_id, "Sibling", act="Act I", chapter="One")
    other_id = db.create_project("Other", narrative_engine="novel").id
    foreign = db.create_scene(other_id, "Foreign", act="Act I", chapter="One")
    before = _structure(client, project_id)
    raw_before = [(scene.id, scene.sort_order) for scene in db.get_all_scenes(project_id)]

    foreign_response = _put(
        client, project_id, foreign.id, before["revision"],
        act="Act I", chapter="One", index=0,
    )
    missing_group = _put(
        client, project_id, source.id, before["revision"],
        act="New Act", chapter="New Chapter", index=0,
    )
    bad_index = _put(
        client, project_id, source.id, before["revision"],
        act="Act I", chapter="One", index=2,
    )

    assert foreign_response.status_code == 404
    assert missing_group.status_code == 400
    assert bad_index.status_code == 400
    assert [(scene.id, scene.sort_order) for scene in db.get_all_scenes(project_id)] == raw_before
    assert db.get_scene_by_id(source.id).act == "Act I"
    assert db.get_scene_by_id(sibling.id).chapter == "One"


def test_database_transaction_rolls_back_labels_and_all_orders_on_sql_failure():
    _client, db, project_id = _project()
    first = db.create_scene(project_id, "First", act="Act I", chapter="One")
    middle = db.create_scene(project_id, "Middle", act="Act I", chapter="One")
    last = db.create_scene(project_id, "Last", act="Act II", chapter="Two")
    snapshot = db.read_story_structure_snapshot(project_id)
    assert snapshot is not None
    before = [
        (scene.id, scene.act, scene.chapter, scene.sort_order)
        for scene in db.get_all_scenes(project_id)
    ]

    with db._engine.begin() as connection:
        connection.execute(text(f"""
            CREATE TRIGGER reject_structure_rewrite
            BEFORE UPDATE OF sort_order ON scene
            WHEN OLD.id = {last.id}
            BEGIN
                SELECT RAISE(ABORT, 'forced structure rollback');
            END;
        """))
    try:
        with pytest.raises(IntegrityError):
            db.place_scene_in_structure(
                project_id,
                first.id,
                expected_revision=snapshot.revision,
                act="Act II",
                chapter="Two",
                index=1,
            )
    finally:
        with db._engine.begin() as connection:
            connection.execute(text("DROP TRIGGER reject_structure_rewrite"))

    assert [
        (scene.id, scene.act, scene.chapter, scene.sort_order)
        for scene in db.get_all_scenes(project_id)
    ] == before
    assert db.read_story_structure_snapshot(project_id).revision == snapshot.revision
    assert middle.id in {row[0] for row in before}


def test_structure_revision_ignores_prose_but_tracks_structural_state():
    client, db, project_id = _project()
    scene = db.create_scene(project_id, "Before", act="Act I", chapter="One")
    before = _structure(client, project_id)
    assert re.fullmatch(r"[0-9a-f]{64}", before["revision"])

    db.update_scene_title(scene.id, "After")
    after_title = _structure(client, project_id)
    assert after_title["revision"] == before["revision"]
    assert _scenes(after_title)[0]["title"] == "After"

    db.set_scene_structure(scene.id, "Act II", "Two")
    assert _structure(client, project_id)["revision"] != before["revision"]


def test_series_sibling_indexes_are_episode_scoped_and_episode_is_exposed():
    client, db, project_id = _project(engine="series")
    season = db.create_season(project_id, season_number=1, title="S1")
    episode_one = db.create_episode(
        season.id, project_id=project_id, episode_number=1, title="E1",
    )
    episode_two = db.create_episode(
        season.id, project_id=project_id, episode_number=2, title="E2",
    )
    one_a = db.create_scene(
        project_id, "1A", act="Act I", chapter="One", episode_id=episode_one.id,
    )
    one_b = db.create_scene(
        project_id, "1B", act="Act I", chapter="One", episode_id=episode_one.id,
    )
    two_a = db.create_scene(
        project_id, "2A", act="Act I", chapter="One", episode_id=episode_two.id,
    )
    two_b = db.create_scene(
        project_id, "2B", act="Act I", chapter="One", episode_id=episode_two.id,
    )
    before = _structure(client, project_id)
    assert [row["episode_id"] for row in _scenes(before)] == [
        episode_one.id, episode_one.id, episode_two.id, episode_two.id,
    ]

    # Omission preserves Episode 1 and index zero ignores Episode 2 siblings.
    response = _put(
        client, project_id, one_b.id, before["revision"],
        act="Act I", chapter="One", index=0,
    )
    assert response.status_code == 200
    assert [scene.id for scene in db.get_scenes_for_episode(episode_one.id)] == [
        one_b.id, one_a.id,
    ]

    # Explicit Episode 2 reparents and inserts between its own two siblings.
    response = _put(
        client, project_id, one_b.id, response.json()["revision"],
        act="Act I", chapter="One", index=1, episode_id=episode_two.id,
    )
    assert response.status_code == 200
    assert db.get_scene_by_id(one_b.id).episode_id == episode_two.id
    assert [scene.id for scene in db.get_scenes_for_episode(episode_two.id)] == [
        two_a.id, one_b.id, two_b.id,
    ]


def test_series_episode_scope_rejects_foreign_ids_and_supports_unassign():
    client, db, project_id = _project(engine="series")
    season = db.create_season(project_id, season_number=1, title="S1")
    episode = db.create_episode(season.id, project_id=project_id, episode_number=1)
    source = db.create_scene(
        project_id, "Source", act="Act I", chapter="One", episode_id=episode.id,
    )
    unassigned = db.create_scene(project_id, "Unassigned", act="Act I", chapter="One")
    foreign_project = db.create_project("Foreign", narrative_engine="series").id
    foreign_season = db.create_season(foreign_project, season_number=1)
    foreign_episode = db.create_episode(
        foreign_season.id, project_id=foreign_project, episode_number=1,
    )
    before = _structure(client, project_id)

    rejected = _put(
        client, project_id, source.id, before["revision"],
        act="Act I", chapter="One", index=0, episode_id=foreign_episode.id,
    )
    assert rejected.status_code == 404
    assert db.get_scene_by_id(source.id).episode_id == episode.id

    response = _put(
        client, project_id, source.id, before["revision"],
        act="Act I", chapter="One", index=1, episode_id=None,
    )
    assert response.status_code == 200
    assert db.get_scene_by_id(source.id).episode_id is None
    unassigned_ids = [scene.id for scene in db.get_unassigned_series_scenes(project_id)]
    assert unassigned_ids == [unassigned.id, source.id]


def test_non_series_rejects_non_null_episode_destination():
    client, db, project_id = _project()
    source = db.create_scene(project_id, "Source", act="Act I", chapter="One")
    other_project = db.create_project("Series", narrative_engine="series").id
    season = db.create_season(other_project, season_number=1)
    episode = db.create_episode(season.id, project_id=other_project, episode_number=1)
    before = _structure(client, project_id)

    response = _put(
        client, project_id, source.id, before["revision"],
        act="Act I", chapter="One", index=0, episode_id=episode.id,
    )

    assert response.status_code == 400
    assert db.get_scene_by_id(source.id).episode_id is None


def test_placement_waits_for_inflight_scene_patch_then_keeps_new_parent(monkeypatch):
    client, db, project_id = _project()
    source = db.create_scene(project_id, "Source", act="Act I", chapter="One")
    db.create_scene(project_id, "Target", act="Act II", chapter="Two")
    structure_revision = _structure(client, project_id)["revision"]
    source_revision = client.get(
        f"/api/projects/{project_id}/scenes/{source.id}"
    ).json()["revision"]

    patch_has_read = threading.Event()
    allow_patch_write = threading.Event()
    placement_finished = threading.Event()
    original_update = db.update_scene

    def paused_update(*args, **kwargs):
        patch_has_read.set()
        assert allow_patch_write.wait(2)
        return original_update(*args, **kwargs)

    monkeypatch.setattr(db, "update_scene", paused_update)
    responses: dict[str, object] = {}

    def patch_scene() -> None:
        responses["patch"] = client.patch(
            f"/api/projects/{project_id}/scenes/{source.id}",
            json={"title": "Retitled", "expected_revision": source_revision},
        )

    def place_scene() -> None:
        responses["placement"] = _put(
            client, project_id, source.id, structure_revision,
            act="Act II", chapter="Two", index=1,
        )
        placement_finished.set()

    patch_thread = threading.Thread(target=patch_scene)
    patch_thread.start()
    assert patch_has_read.wait(2)
    placement_thread = threading.Thread(target=place_scene)
    placement_thread.start()
    assert not placement_finished.wait(0.1)

    allow_patch_write.set()
    patch_thread.join(timeout=3)
    placement_thread.join(timeout=3)

    assert not patch_thread.is_alive()
    assert not placement_thread.is_alive()
    assert responses["patch"].status_code == 200
    assert responses["placement"].status_code == 200
    stored = db.get_scene_by_id(source.id)
    assert (stored.title, stored.act, stored.chapter) == (
        "Retitled", "Act II", "Two",
    )


@pytest.mark.parametrize("legacy_writer", ["single", "bulk"])
def test_placement_cannot_cross_a_paused_legacy_global_reorder(
    tmp_path, legacy_writer,
):
    client, db, project_id = _project(path=str(tmp_path / "structure-race.db"))
    first = db.create_scene(project_id, "First", act="Act I", chapter="One")
    moving = db.create_scene(project_id, "Moving", act="Act I", chapter="One")
    target = db.create_scene(project_id, "Target", act="Act II", chapter="Two")
    revision = _structure(client, project_id)["revision"]

    reorder_read = threading.Event()
    allow_reorder_commit = threading.Event()
    placement_finished = threading.Event()
    reorder_thread_id: list[int] = []
    paused = False

    def pause_after_scene_list_read(
        _conn, _cursor, statement, _parameters, _context, _executemany,
    ):
        nonlocal paused
        normalized = " ".join(statement.lower().split())
        if (
            paused
            or not reorder_thread_id
            or threading.get_ident() != reorder_thread_id[0]
            or "from scene" not in normalized
            or "order by scene.sort_order" not in normalized
        ):
            return
        paused = True
        reorder_read.set()
        assert allow_reorder_commit.wait(3)

    event.listen(db._engine, "after_cursor_execute", pause_after_scene_list_read)
    responses: dict[str, object] = {}

    def reorder() -> None:
        reorder_thread_id.append(threading.get_ident())
        if legacy_writer == "single":
            db.reorder_scene(first.id, 2)
        else:
            db.reorder_scenes(project_id, [moving.id, target.id, first.id])

    def place() -> None:
        responses["placement"] = _put(
            client, project_id, moving.id, revision,
            act="Act II", chapter="Two", index=1,
        )
        placement_finished.set()

    reorder_thread = threading.Thread(target=reorder)
    placement_thread = threading.Thread(target=place)
    try:
        reorder_thread.start()
        assert reorder_read.wait(3)
        placement_thread.start()
        assert not placement_finished.wait(0.1)
        allow_reorder_commit.set()
        reorder_thread.join(timeout=4)
        placement_thread.join(timeout=4)
    finally:
        allow_reorder_commit.set()
        event.remove(db._engine, "after_cursor_execute", pause_after_scene_list_read)

    assert not reorder_thread.is_alive()
    assert not placement_thread.is_alive()
    # The reorder wins first; the placement then observes its stale token and
    # fails instead of rewriting from the pre-reorder scene list.
    assert responses["placement"].status_code == 409
    rows = db.get_all_scenes(project_id)
    assert [scene.id for scene in rows] == [moving.id, target.id, first.id]
    assert [scene.sort_order for scene in rows] == [0, 1, 2]
