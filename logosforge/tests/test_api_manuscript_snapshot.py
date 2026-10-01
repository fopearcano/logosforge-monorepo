"""Atomic, canonically ordered manuscript snapshot HTTP contract."""

from __future__ import annotations

import threading

import pytest
from sqlalchemy import event
from sqlmodel import Session as RawSQLModelSession
from sqlmodel import select

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from logosforge.api import serializers  # noqa: E402
from logosforge.api.app import create_api  # noqa: E402
from logosforge.api.config import ApiConfig  # noqa: E402
from logosforge.db import (  # noqa: E402
    Database,
    InMemoryTransactionReentryError,
)
from logosforge.models import (  # noqa: E402
    Scene,
    SceneCharacterLink,
    SceneCharacterState,
)


def _project(*, engine: str = "novel", path: str | None = None):
    db = Database(path)
    project = db.create_project(
        "Manuscript snapshot",
        narrative_engine=engine,
        default_writing_format=engine,
    )
    client = TestClient(create_api(db=db, config=ApiConfig(mode="desktop")))
    return client, db, project.id


def test_manuscript_snapshot_returns_full_scene_dtos_in_canonical_order(monkeypatch):
    client, db, project_id = _project()
    character = db.create_character(project_id, "Alice")
    place = db.create_place(project_id, "Library")
    a1 = db.create_scene(
        project_id,
        "A1",
        summary="summary",
        synopsis="synopsis",
        goal="goal",
        conflict="conflict",
        outcome="outcome",
        beat="Opening Image",
        tags="one, two",
        act="Act I",
        chapter="Chapter A",
        plotline="Main",
        color_label="#123456",
        content="First prose",
        who_knows_what="Alice knows",
        character_ids=[character.id],
        place_ids=[place.id],
        character_states=[(character.id, "uncertain")],
    )
    b1 = db.create_scene(
        project_id, "B1", act="Act I", chapter="Chapter B", content="B prose",
    )
    a2 = db.create_scene(
        project_id, "A2", act="Act I", chapter="Chapter A", content="A2 prose",
    )
    expected_revision = serializers.scene_revision(db, a1)

    # The endpoint serializer must consume only the captured transaction state;
    # these legacy per-row readers would split the response across transactions.
    def unexpected_read(*_args, **_kwargs):
        raise AssertionError("serializer issued a post-snapshot database read")

    for name in (
        "get_all_characters",
        "get_all_places",
        "get_scene_character_ids",
        "get_scene_place_ids",
        "get_scene_character_states",
    ):
        monkeypatch.setattr(db, name, unexpected_read)

    response = client.get(f"/api/projects/{project_id}/manuscript-snapshot")

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == project_id
    assert body["chapter_level"] is True
    assert body["scene_count"] == 3
    assert body["orphan_count"] == 0
    # Raw creation order was A1, B1, A2; canonical grouping keeps Chapter A
    # together, exactly like the structure navigator.
    assert [scene["id"] for scene in body["scenes"]] == [a1.id, a2.id, b1.id]
    assert [scene["order_index"] for scene in body["scenes"]] == [1, 2, 3]

    first = body["scenes"][0]
    assert first == {
        "id": a1.id,
        "title": "A1",
        "summary": "summary",
        "synopsis": "synopsis",
        "goal": "goal",
        "conflict": "conflict",
        "outcome": "outcome",
        "beat": "Opening Image",
        "act": "Act I",
        "chapter": "Chapter A",
        "plotline": "Main",
        "color_label": "#123456",
        "tags": ["one", "two"],
        "content": "First prose",
        "sort_order": 1,
        "order_index": 1,
        "character_ids": [character.id],
        "place_ids": [place.id],
        "who_knows_what": "Alice knows",
        "revision": expected_revision,
    }


def test_manuscript_snapshot_reports_orphans_and_non_novel_mode():
    client, db, project_id = _project(engine="screenplay")
    assigned = db.create_scene(
        project_id, "Assigned", act="Act I", chapter="Sequence A",
    )
    orphan = db.create_scene(project_id, "Loose")

    body = client.get(f"/api/projects/{project_id}/manuscript-snapshot").json()

    assert body["chapter_level"] is False
    assert body["scene_count"] == 2
    assert body["orphan_count"] == 1
    assert [scene["id"] for scene in body["scenes"]] == [assigned.id, orphan.id]


def test_manuscript_snapshot_is_project_isolated_and_missing_project_is_404():
    client, db, project_id = _project()
    other_id = db.create_project("Other", narrative_engine="novel").id
    owned = db.create_scene(
        project_id, "Owned", act="Act I", chapter="Chapter I",
    )
    db.create_scene(
        other_id, "Foreign", act="Foreign Act", chapter="Foreign Chapter",
    )

    response = client.get(f"/api/projects/{project_id}/manuscript-snapshot")

    assert response.status_code == 200
    assert [scene["id"] for scene in response.json()["scenes"]] == [owned.id]
    assert "Foreign" not in response.text
    assert client.get("/api/projects/999999/manuscript-snapshot").status_code == 404


@pytest.mark.parametrize("path", [None, ":memory:"])
def test_in_memory_snapshot_rejects_same_thread_nested_transaction(path):
    _client, db, project_id = _project(path=path)
    old_character = db.create_character(project_id, "Old cast")
    scene = db.create_scene(
        project_id,
        "Before",
        act="Act I",
        chapter="Chapter I",
        content="old prose",
        character_ids=[old_character.id],
        character_states=[(old_character.id, "old state")],
    )
    errors: list[InMemoryTransactionReentryError] = []
    attempted = False

    def try_nested_commit(
        _conn, _cursor, statement, _parameters, _context, _executemany,
    ):
        nonlocal attempted
        normalized = " ".join(statement.lower().split())
        if attempted or "from character" not in normalized:
            return
        attempted = True
        try:
            # Use the public SQLModel Session class directly, matching core
            # extraction paths that do not call a Database helper.
            with RawSQLModelSession(db._engine) as nested:
                nested.get(Scene, scene.id)
        except InMemoryTransactionReentryError as exc:
            errors.append(exc)

    event.listen(db._engine, "before_cursor_execute", try_nested_commit)
    try:
        snapshot = db.read_manuscript_snapshot(project_id)
    finally:
        event.remove(db._engine, "before_cursor_execute", try_nested_commit)

    assert attempted is True
    assert len(errors) == 1
    assert snapshot is not None
    assert snapshot.scenes[0].title == "Before"
    assert snapshot.character_ids_by_scene[scene.id] == (old_character.id,)
    assert snapshot.character_states_by_scene[scene.id] == (
        (old_character.id, "old state"),
    )
    # The rejected nested transaction cannot partially mutate the shared
    # sqlite3 handle either.
    assert db.get_scene_by_id(scene.id).title == "Before"


@pytest.mark.parametrize("path", [None, ":memory:"])
def test_in_memory_snapshot_serializes_other_thread_transaction(path):
    _client, db, project_id = _project(path=path)
    old_character = db.create_character(project_id, "Old cast")
    new_character = db.create_character(project_id, "New cast")
    scene = db.create_scene(
        project_id,
        "Before",
        act="Act I",
        chapter="Chapter I",
        content="old prose",
        character_ids=[old_character.id],
    )
    writer_started = threading.Event()
    writer_finished = threading.Event()
    writer: threading.Thread | None = None

    def write_after_guard() -> None:
        writer_started.set()
        with RawSQLModelSession(db._engine) as raw:
            row = raw.get(Scene, scene.id)
            row.title = "After"
            row.content = "new prose"
            for link in raw.exec(
                select(SceneCharacterLink).where(
                    SceneCharacterLink.scene_id == scene.id
                )
            ).all():
                raw.delete(link)
            for state in raw.exec(
                select(SceneCharacterState).where(
                    SceneCharacterState.scene_id == scene.id
                )
            ).all():
                raw.delete(state)
            raw.add(SceneCharacterLink(
                scene_id=scene.id, character_id=new_character.id,
            ))
            raw.add(SceneCharacterState(
                scene_id=scene.id,
                character_id=new_character.id,
                state="new state",
            ))
            raw.commit()
        writer_finished.set()

    def start_competing_writer(
        _conn, _cursor, statement, _parameters, _context, _executemany,
    ):
        nonlocal writer
        normalized = " ".join(statement.lower().split())
        if writer is not None or "from character" not in normalized:
            return
        writer = threading.Thread(target=write_after_guard)
        writer.start()
        assert writer_started.wait(1)
        # It reached Database.update_scene but cannot enter a second Session
        # until this snapshot releases StaticPool's only connection.
        assert not writer_finished.wait(0.05)

    event.listen(db._engine, "before_cursor_execute", start_competing_writer)
    try:
        snapshot = db.read_manuscript_snapshot(project_id)
    finally:
        event.remove(db._engine, "before_cursor_execute", start_competing_writer)

    assert writer is not None
    writer.join(timeout=2)
    assert not writer.is_alive()
    assert writer_finished.is_set()
    assert snapshot is not None
    assert snapshot.scenes[0].title == "Before"
    assert snapshot.character_ids_by_scene[scene.id] == (old_character.id,)
    assert snapshot.character_states_by_scene[scene.id] == ()
    assert db.get_scene_by_id(scene.id).title == "After"
    assert db.get_scene_character_ids(scene.id) == [new_character.id]
    assert db.get_scene_character_states(scene.id) == [
        (new_character.id, "new state"),
    ]


def test_database_manuscript_snapshot_is_stable_across_concurrent_commit(tmp_path):
    path = str(tmp_path / "snapshot.db")
    _client, reader, project_id = _project(path=path)
    writer = Database(path)
    old_character = reader.create_character(project_id, "Old cast")
    new_character = reader.create_character(project_id, "New cast")
    scene = reader.create_scene(
        project_id,
        "Before",
        summary="old summary",
        act="Act I",
        chapter="Chapter I",
        content="old prose",
        character_ids=[old_character.id],
        character_states=[(old_character.id, "old state")],
    )
    committed = False

    def commit_between_snapshot_queries(
        _conn, _cursor, statement, _parameters, _context, _executemany,
    ):
        nonlocal committed
        normalized = " ".join(statement.lower().split())
        if committed or "from character" not in normalized:
            return
        committed = True
        writer.update_scene(
            scene.id,
            title="After",
            summary="new summary",
            act="Act I",
            chapter="Chapter I",
            content="new prose",
            character_ids=[new_character.id],
            character_states=[(new_character.id, "new state")],
        )

    event.listen(
        reader._engine, "before_cursor_execute", commit_between_snapshot_queries,
    )
    try:
        snapshot = reader.read_manuscript_snapshot(project_id)
    finally:
        event.remove(
            reader._engine, "before_cursor_execute", commit_between_snapshot_queries,
        )

    assert committed is True
    assert snapshot is not None
    assert snapshot.scenes[0].title == "Before"
    assert snapshot.scenes[0].content == "old prose"
    assert snapshot.character_ids_by_scene[scene.id] == (old_character.id,)
    assert snapshot.character_states_by_scene[scene.id] == (
        (old_character.id, "old state"),
    )
    # The competing connection really did commit; only the in-flight read stays
    # pinned to the earlier SQLite snapshot.
    assert writer.get_scene_by_id(scene.id).title == "After"
    assert writer.get_scene_character_ids(scene.id) == [new_character.id]
