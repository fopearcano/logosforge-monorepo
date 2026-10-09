"""Focused first-class Progressions API and compatibility tests."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from logosforge.api.app import create_api
from logosforge.context_builder import gather_progressions_context
from logosforge.db import (
    Database,
    ProgressionBeatNotFound,
    ProgressionCommandError,
)
from logosforge.models import ProgressionBeat
from sqlmodel import Session


def _client():
    db = Database()
    project = db.create_project("Progressions")
    return db, project, TestClient(create_api(db=db))


def _snapshot(client: TestClient, project_id: int) -> dict:
    response = client.get(f"/api/projects/{project_id}/progressions")
    assert response.status_code == 200
    return response.json()


def _command(
    client: TestClient,
    project_id: int,
    body: dict,
    key: str,
):
    return client.post(
        f"/api/projects/{project_id}/progressions/commands",
        json=body,
        headers={"Idempotency-Key": key},
    )


def test_progression_snapshot_anchors_coverage_and_receipt_replay():
    db, project, client = _client()
    early = db.create_scene(project.id, "Early")
    late = db.create_scene(project.id, "Late")
    revision = _snapshot(client, project.id)["revision"]

    create_track = {
        "kind": "create_track",
        "expected_revision": revision,
        "track_kind": "story",
        "title": "Main arc",
    }
    response = _command(
        client, project.id, create_track, "progression-test-track-0001",
    )
    assert response.status_code == 200
    result = response.json()
    assert result["changed"] is True
    assert result["created_track_id"] is not None
    track_id = result["created_track_id"]
    original_applied_revision = result["applied_revision"]
    assert [
        event["event"]
        for event in client.app.state.broker.events_since(0, project.id)
    ] == ["progressions_changed"]

    response = _command(client, project.id, {
        "kind": "create_beat",
        "expected_revision": result["progressions"]["revision"],
        "track_id": track_id,
        "text": "The promise",
        "anchor_kind": "scene",
        "scene_id": late.id,
    }, "progression-test-beat-00001")
    assert response.status_code == 200
    result = response.json()
    response = _command(client, project.id, {
        "kind": "create_beat",
        "expected_revision": result["progressions"]["revision"],
        "track_id": track_id,
        "text": "An earlier reveal",
        "anchor_kind": "scene",
        "scene_id": early.id,
    }, "progression-test-beat-00002")
    assert response.status_code == 200
    track = response.json()["progressions"]["tracks"][0]
    assert track["coverage"] == {
        "total_beats": 2,
        "anchored_beats": 2,
        "unanchored_beats": 0,
        "scene_anchored_beats": 2,
        "document_anchored_beats": 0,
        "coverage_percent": 100.0,
        "status": "complete",
        "out_of_order_beat_ids": [track["beats"][1]["id"]],
    }

    # Exact retry is resolved before the now-stale revision check.
    replay = _command(
        client, project.id, create_track, "progression-test-track-0001",
    )
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["changed"] is False
    assert replay.json()["created_track_id"] == track_id
    assert replay.json()["applied_revision"] == original_applied_revision

    receipt = client.get(
        f"/api/projects/{project.id}/progressions/command-receipt",
        headers={"Idempotency-Key": "progression-test-track-0001"},
    )
    assert receipt.status_code == 200
    assert receipt.headers["cache-control"] == "no-store"
    assert receipt.json()["command_kind"] == "create_track"
    assert receipt.json()["original_created_track_id"] == track_id

    collision = dict(create_track, title="Different command")
    response = _command(
        client, project.id, collision, "progression-test-track-0001",
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "idempotency_key_conflict"


def test_progression_subject_anchor_and_reorder_guards():
    db, project, client = _client()
    character = db.create_psyke_entry(project.id, "Hero", "character")
    theme = db.create_psyke_entry(project.id, "Mercy", "theme")
    revision = _snapshot(client, project.id)["revision"]

    wrong_subject = _command(client, project.id, {
        "kind": "create_track",
        "expected_revision": revision,
        "track_kind": "character",
        "title": "Wrong",
        "primary_psyke_entry_id": theme.id,
    }, "progression-test-guard-0001")
    assert wrong_subject.status_code == 400

    relationship = _command(client, project.id, {
        "kind": "create_track",
        "expected_revision": revision,
        "track_kind": "relationship",
        "title": "Self",
        "primary_psyke_entry_id": character.id,
        "secondary_psyke_entry_id": character.id,
    }, "progression-test-guard-0002")
    assert relationship.status_code == 400

    first = _command(client, project.id, {
        "kind": "create_track",
        "expected_revision": revision,
        "track_kind": "character",
        "title": "Hero arc",
        "primary_psyke_entry_id": character.id,
    }, "progression-test-guard-0003")
    assert first.status_code == 200
    result = first.json()
    second = _command(client, project.id, {
        "kind": "create_track",
        "expected_revision": result["progressions"]["revision"],
        "track_kind": "story",
        "title": "Story",
    }, "progression-test-guard-0004")
    assert second.status_code == 200
    snapshot = second.json()["progressions"]
    ids = [row["id"] for row in snapshot["tracks"]]

    duplicate = _command(client, project.id, {
        "kind": "reorder_tracks",
        "expected_revision": snapshot["revision"],
        "track_ids": [ids[0], ids[0]],
    }, "progression-test-guard-0005")
    assert duplicate.status_code == 400
    missing = _command(client, project.id, {
        "kind": "reorder_tracks",
        "expected_revision": snapshot["revision"],
        "track_ids": [ids[0]],
    }, "progression-test-guard-0006")
    assert missing.status_code == 400
    coerced = _command(client, project.id, {
        "kind": "reorder_tracks",
        "expected_revision": snapshot["revision"],
        "track_ids": [True, ids[1]],
    }, "progression-test-guard-0007")
    assert coerced.status_code == 422


def test_unanchored_beats_reject_anchor_labels_at_every_write_boundary():
    db, project, client = _client()
    created = _command(client, project.id, {
        "kind": "create_track",
        "expected_revision": _snapshot(client, project.id)["revision"],
        "track_kind": "story",
        "title": "Arc",
    }, "progression-anchor-label-0001")
    assert created.status_code == 200
    result = created.json()

    rejected = _command(client, project.id, {
        "kind": "create_beat",
        "expected_revision": result["progressions"]["revision"],
        "track_id": result["created_track_id"],
        "text": "Floating beat",
        "anchor_kind": "unanchored",
        "anchor_label": "Not actually unanchored",
    }, "progression-anchor-label-0002")
    assert rejected.status_code == 422

    with pytest.raises(ProgressionCommandError):
        db.execute_progression_command(
            project.id,
            kind="create_beat",
            expected_revision=result["progressions"]["revision"],
            track_id=result["created_track_id"],
            text="Floating beat",
            anchor_kind="unanchored",
            anchor_label="Still invalid",
        )
    assert _snapshot(client, project.id)["summary"]["total_beats"] == 0


def test_psyke_type_change_rejects_incompatible_canonical_subject_atomically():
    db, project, client = _client()
    character = db.create_psyke_entry(project.id, "Hero", "character")
    revision = _snapshot(client, project.id)["revision"]
    created = _command(client, project.id, {
        "kind": "create_track",
        "expected_revision": revision,
        "track_kind": "character",
        "title": "Hero arc",
        "primary_psyke_entry_id": character.id,
    }, "progression-type-guard-0001")
    assert created.status_code == 200

    rejected = client.patch(
        f"/api/projects/{project.id}/psyke/entries/{character.id}",
        json={"type": "place"},
    )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == (
        "psyke_progression_subject_conflict"
    )
    assert db.get_psyke_entry_by_id(character.id).entry_type == "character"
    snapshot = _snapshot(client, project.id)
    assert snapshot["tracks"][0]["kind"] == "character"
    assert snapshot["tracks"][0]["primary_psyke_entry_type"] == "character"

    place = db.create_psyke_entry(project.id, "Harbor", "place")
    created = _command(client, project.id, {
        "kind": "create_track",
        "expected_revision": snapshot["revision"],
        "track_kind": "world",
        "title": "Harbor evolution",
        "primary_psyke_entry_id": place.id,
    }, "progression-type-guard-0002")
    assert created.status_code == 200
    allowed = client.patch(
        f"/api/projects/{project.id}/psyke/entries/{place.id}",
        json={"type": "object"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["type"] == "object"
    rejected = client.patch(
        f"/api/projects/{project.id}/psyke/entries/{place.id}",
        json={"type": "theme"},
    )
    assert rejected.status_code == 409
    assert db.get_psyke_entry_by_id(place.id).entry_type == "object"


def test_legacy_psyke_progressions_share_the_canonical_store():
    db, project, client = _client()
    scene = db.create_scene(project.id, "Scene")
    entry = db.create_psyke_entry(project.id, "Hero", "character")
    legacy = db.create_psyke_progression(entry.id, "Begins", scene.id)

    snapshot = _snapshot(client, project.id)
    assert snapshot["summary"]["total_tracks"] == 1
    track = snapshot["tracks"][0]
    assert track["primary_psyke_entry_id"] == entry.id
    assert track["legacy_compatibility"] is True
    assert track["beats"][0]["id"] == legacy.id

    updated = _command(client, project.id, {
        "kind": "update_beat",
        "expected_revision": snapshot["revision"],
        "beat_id": legacy.id,
        "text": "Changes",
    }, "progression-test-legacy-0001")
    assert updated.status_code == 200
    assert db.get_psyke_progressions(entry.id)[0].text == "Changes"

    db.update_psyke_progression(legacy.id, "Legacy edit", None)
    refreshed = _snapshot(client, project.id)["tracks"][0]["beats"][0]
    assert refreshed["text"] == "Legacy edit"
    assert refreshed["anchor_kind"] == "unanchored"

    db.delete_scene(scene.id)
    assert db.get_psyke_progressions(entry.id)[0].scene_id is None


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_legacy_progression_write_revalidates_track_identity_after_lock(
    monkeypatch, operation,
):
    """A stale legacy lookup must not mutate an id reused by a native beat."""
    db, project, client = _client()
    created = _command(client, project.id, {
        "kind": "create_track",
        "expected_revision": _snapshot(client, project.id)["revision"],
        "track_kind": "story",
        "title": "Native story arc",
    }, f"progression-race-track-{operation}")
    assert created.status_code == 200
    native_track_id = created.json()["created_track_id"]

    entry = db.create_psyke_entry(project.id, "Hero", "character")
    legacy = db.create_psyke_progression(entry.id, "Legacy beat")
    original_lock = db.progression_write_lock

    @contextmanager
    def replace_target_before_lock(project_id):
        # This models deletion/id reuse between the optimistic compatibility
        # lookup and lock acquisition without depending on SQLite's allocator.
        with Session(db._engine) as session:
            beat = session.get(ProgressionBeat, legacy.id)
            assert beat is not None
            beat.track_id = native_track_id
            beat.text = "Native beat with reused identity"
            beat.anchor_kind = "unanchored"
            beat.scene_id = None
            beat.anchor_ref = None
            beat.anchor_label = ""
            session.add(beat)
            session.commit()
        with original_lock(project_id):
            yield

    monkeypatch.setattr(db, "progression_write_lock", replace_target_before_lock)

    if operation == "update":
        with pytest.raises(ProgressionBeatNotFound):
            db.update_psyke_progression(legacy.id, "Must not overwrite")
    else:
        db.delete_psyke_progression(legacy.id)

    with Session(db._engine) as session:
        surviving = session.get(ProgressionBeat, legacy.id)
        assert surviving is not None
        assert surviving.track_id == native_track_id
        assert surviving.text == "Native beat with reused identity"


def test_legacy_other_entry_maps_to_designated_custom_subject_track():
    db, project, client = _client()
    entry = db.create_psyke_entry(project.id, "Unclassified", "other")
    legacy = db.create_psyke_progression(entry.id, "Changes shape", None)

    snapshot = _snapshot(client, project.id)
    assert snapshot["summary"]["total_tracks"] == 1
    track = snapshot["tracks"][0]
    assert track["kind"] == "custom"
    assert track["legacy_compatibility"] is True
    assert track["primary_psyke_entry_id"] == entry.id
    assert track["primary_psyke_entry_type"] == "other"
    assert track["beats"][0]["id"] == legacy.id


def test_legacy_subject_type_change_remaps_designated_track_atomically():
    db, project, client = _client()
    entry = db.create_psyke_entry(project.id, "Mutable", "character")
    legacy = db.create_psyke_progression(entry.id, "Begins", None)

    changed = client.patch(
        f"/api/projects/{project.id}/psyke/entries/{entry.id}",
        json={"type": "place"},
    )
    assert changed.status_code == 200
    snapshot = _snapshot(client, project.id)
    track = snapshot["tracks"][0]
    assert track["kind"] == "world"
    assert track["primary_psyke_entry_type"] == "place"
    assert track["beats"][0]["id"] == legacy.id

    changed = client.patch(
        f"/api/projects/{project.id}/psyke/entries/{entry.id}",
        json={"type": "other"},
    )
    assert changed.status_code == 200
    track = _snapshot(client, project.id)["tracks"][0]
    assert track["kind"] == "custom"
    assert track["primary_psyke_entry_type"] == "other"
    assert track["beats"][0]["id"] == legacy.id


def test_v6_legacy_progressions_migrate_once(tmp_path):
    path = tmp_path / "legacy-progressions.db"
    db = Database(str(path))
    project = db.create_project("Legacy")
    scene = db.create_scene(project.id, "Anchor")
    entry = db.create_psyke_entry(project.id, "Hero", "character")
    other_project = db.create_project("Other")
    foreign_scene = db.create_scene(other_project.id, "Foreign anchor")

    with sqlite3.connect(path) as conn:
        conn.executemany(
            "INSERT INTO psykeprogression "
            "(id, entry_id, text, scene_id, sort_order) VALUES (?, ?, ?, ?, ?)",
            [
                (42, entry.id, "Inherited beat", scene.id, 9),
                (43, entry.id, "Foreign beat", foreign_scene.id, 10),
            ],
        )
        conn.execute("PRAGMA user_version = 6")
        conn.commit()

    upgraded = Database(str(path))
    rows = upgraded.get_psyke_progressions(entry.id)
    assert [(row.id, row.text, row.scene_id) for row in rows] == [
        (42, "Inherited beat", scene.id),
        (43, "Foreign beat", None),
    ]
    assert rows[0].sort_order == 0
    assert rows[1].sort_order == 1
    assert upgraded.read_progression_snapshot(project.id).tracks[0].beats[0].id == 42
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
        assert conn.execute("SELECT COUNT(*) FROM psykeprogression").fetchone()[0] == 0

    # Reopening v7 is idempotent and cannot duplicate the compatibility rows.
    reopened = Database(str(path))
    assert [row.id for row in reopened.get_psyke_progressions(entry.id)] == [42, 43]
    assert path.with_name(path.name + ".pre-v7.bak").exists()


def test_progression_restore_is_atomic_on_invalid_subject():
    db, project, _client_instance = _client()
    theme = db.create_psyke_entry(project.id, "Mercy", "theme")

    with pytest.raises(ProgressionCommandError):
        db.restore_progression_tracks(project.id, [
            {
                "kind": "story",
                "title": "Would otherwise be valid",
                "beats": [],
            },
            {
                "kind": "character",
                "title": "Invalid subject",
                "primary_psyke_entry_id": theme.id,
                "beats": [],
            },
        ])

    snapshot = db.read_progression_snapshot(project.id)
    assert snapshot is not None
    assert snapshot.tracks == ()


def test_progressions_context_is_bounded_and_project_scoped():
    db, project, _client_instance = _client()
    other = db.create_project("Other")
    scene = db.create_scene(project.id, "Here", content="Hero decides.")
    hero = db.create_psyke_entry(project.id, "Hero", "character")
    foreign = db.create_psyke_entry(other.id, "Secret", "character")
    db.create_psyke_progression(
        hero.id, "Chooses mercy " + ("x" * 400), scene.id,
    )
    db.create_psyke_progression(foreign.id, "Foreign secret")

    context = gather_progressions_context(
        db, project.id, scene.id, max_chars=300,
    )
    assert context.startswith("[Progressions]")
    assert "Hero" in context
    assert "Chooses mercy" in context
    assert "Secret" not in context
    assert len(context) <= 300


def test_scene_detaches_beats_and_psyke_delete_cascades_subject_tracks():
    db, project, client = _client()
    scene = db.create_scene(project.id, "Anchor")
    hero = db.create_psyke_entry(project.id, "Hero", "character")
    snapshot = _snapshot(client, project.id)
    response = _command(client, project.id, {
        "kind": "create_track",
        "expected_revision": snapshot["revision"],
        "track_kind": "character",
        "title": "Hero arc",
        "primary_psyke_entry_id": hero.id,
    }, "progression-test-cascade-001")
    track_id = response.json()["created_track_id"]
    response = _command(client, project.id, {
        "kind": "create_beat",
        "expected_revision": response.json()["progressions"]["revision"],
        "track_id": track_id,
        "text": "Anchored",
        "anchor_kind": "scene",
        "scene_id": scene.id,
    }, "progression-test-cascade-002")
    assert response.status_code == 200

    db.delete_scene(scene.id)
    beat = _snapshot(client, project.id)["tracks"][0]["beats"][0]
    assert beat["anchor_kind"] == "unanchored"
    assert beat["scene_id"] is None

    db.delete_psyke_entry(hero.id)
    assert _snapshot(client, project.id)["tracks"] == []
