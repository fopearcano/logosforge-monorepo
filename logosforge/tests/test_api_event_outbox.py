"""Phase 7D transactional invalidation outbox and reconnect guarantees."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from logosforge.api import create_api
from logosforge.api.events import ApiEventBroker
from logosforge.db import Database


def _timeline_project(path: str | None = None):
    db = Database(path)
    project = db.create_project(
        "Event outbox",
        narrative_engine="novel",
        default_writing_format="novel",
    )
    snapshot = db.read_timeline_snapshot(project.id)
    assert snapshot is not None
    return db, project.id, snapshot.revision


def _commit_timeline_lane(
    db: Database,
    project_id: int,
    revision: str,
    *,
    key: str = "outbox-timeline-command-01",
):
    return db.execute_timeline_command(
        project_id,
        kind="create_lane",
        expected_revision=revision,
        idempotency_key=key,
        name="Durable lane",
    )


def _outbox_count(db: Database) -> int:
    with db._engine.connect() as connection:
        return int(connection.execute(text(
            "SELECT COUNT(*) FROM apieventoutbox"
        )).scalar_one())


def test_committed_invalidation_survives_restart_and_exact_replay_is_silent(
    tmp_path,
):
    path = str(tmp_path / "event-outbox.db")
    db, project_id, revision = _timeline_project(path)
    result = _commit_timeline_lane(db, project_id, revision)
    assert result.changed is True
    assert _outbox_count(db) == 1
    with db._engine.connect() as connection:
        row = connection.execute(text(
            "SELECT event_name, data_json FROM apieventoutbox"
        )).one()
    assert row[0] == "timeline_changed"
    envelope = json.loads(row[1])
    assert envelope["data"] == {}
    assert len(envelope["outbox_token"]) == 32

    # Simulate death after SQLite commit but before the route can notify.  A
    # fresh API reconciles the pending row at startup and acknowledges it.
    db._engine.dispose()
    reopened = Database(path)
    client = TestClient(create_api(db=reopened))
    assert _outbox_count(reopened) == 0
    assert [event["event"] for event in
            client.app.state.broker.events_since(0, project_id)] == [
        "timeline_changed",
    ]

    polled = client.get(
        f"/api/projects/{project_id}/events/poll",
        params={"since": 0},
    )
    assert polled.status_code == 200
    payload = polled.json()
    assert payload["broker_instance_id"]
    assert payload["cursor"] == 1
    assert [event["event"] for event in payload["events"]] == [
        "timeline_changed",
    ]

    streamed = client.get(
        f"/api/projects/{project_id}/events",
        params={"once": True, "since": 0},
    )
    assert streamed.status_code == 200
    assert "event: connected" in streamed.text
    assert '"data": {"broker_instance_id":' in streamed.text
    assert '"ts":' in streamed.text
    assert "event: timeline_changed\nid: 1" in streamed.text

    cursor = client.app.state.broker.latest_id()
    replay = client.post(
        f"/api/projects/{project_id}/timeline/commands",
        headers={"Idempotency-Key": "outbox-timeline-command-01"},
        json={
            "kind": "create_lane",
            "expected_revision": revision,
            "name": "Durable lane",
        },
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert client.app.state.broker.events_since(cursor, project_id) == []
    assert _outbox_count(reopened) == 0


def test_acknowledgement_failure_does_not_flood_one_broker(monkeypatch):
    db, project_id, revision = _timeline_project()
    _commit_timeline_lane(db, project_id, revision)
    acknowledge = db.acknowledge_api_events

    def fail_acknowledgement(_event_ids):
        raise RuntimeError("simulated acknowledgement failure")

    monkeypatch.setattr(db, "acknowledge_api_events", fail_acknowledgement)
    broker = ApiEventBroker(db)
    assert _outbox_count(db) == 1
    assert [event["event"] for event in broker.events_since(0, project_id)] == [
        "timeline_changed",
    ]
    broker.reconcile()
    assert len(broker.events_since(0, project_id)) == 1

    monkeypatch.setattr(db, "acknowledge_api_events", acknowledge)
    broker.reconcile()
    assert _outbox_count(db) == 0
    assert len(broker.events_since(0, project_id)) == 1


def test_outbox_insert_failure_rolls_back_mutation_and_receipt(tmp_path):
    db, project_id, revision = _timeline_project(
        str(tmp_path / "event-outbox-rollback.db")
    )
    key = "outbox-insert-rollback-01"
    with db._engine.begin() as connection:
        connection.execute(text("""
            CREATE TRIGGER reject_api_event_outbox
            BEFORE INSERT ON apieventoutbox
            BEGIN
                SELECT RAISE(ABORT, 'forced event outbox rollback');
            END;
        """))
    try:
        with pytest.raises(IntegrityError):
            _commit_timeline_lane(db, project_id, revision, key=key)
    finally:
        with db._engine.begin() as connection:
            connection.execute(text("DROP TRIGGER reject_api_event_outbox"))

    assert db.get_timeline_lanes(project_id) == []
    assert db.get_timeline_command_receipt(project_id, key) is None
    assert db.read_timeline_snapshot(project_id).revision == revision
    assert _outbox_count(db) == 0


def test_project_delete_removes_pending_outbox_rows_before_id_reuse(tmp_path):
    db, project_id, revision = _timeline_project(
        str(tmp_path / "event-outbox-delete.db")
    )
    _commit_timeline_lane(db, project_id, revision)
    assert _outbox_count(db) == 1

    db.delete_project(project_id)
    assert _outbox_count(db) == 0
    replacement = db.create_project("Replacement", narrative_engine="novel")
    assert replacement.id == project_id
    broker = ApiEventBroker(db)
    assert broker.events_since(0, replacement.id) == []


def test_failed_ack_does_not_hide_a_reused_outbox_row(monkeypatch):
    db, project_id, revision = _timeline_project()
    _commit_timeline_lane(db, project_id, revision)
    old_row = db.get_pending_api_events()[0]
    acknowledge = db.acknowledge_api_events

    def fail_acknowledgement(_events):
        raise RuntimeError("simulated acknowledgement failure")

    monkeypatch.setattr(db, "acknowledge_api_events", fail_acknowledgement)
    broker = ApiEventBroker(db)
    first_events = broker.events_since(0, project_id)
    assert len(first_events) == 1

    db.delete_project(project_id)
    replacement = db.create_project("Replacement", narrative_engine="novel")
    assert replacement.id == project_id
    replacement_snapshot = db.read_timeline_snapshot(replacement.id)
    _commit_timeline_lane(
        db,
        replacement.id,
        replacement_snapshot.revision,
        key="outbox-reused-row-command-01",
    )
    new_row = db.get_pending_api_events()[0]
    assert new_row.id == old_row.id
    assert new_row.data_json != old_row.data_json

    monkeypatch.setattr(db, "acknowledge_api_events", acknowledge)
    assert broker.reconcile() == 1
    new_events = broker.events_since(first_events[-1]["id"], replacement.id)
    assert [event["event"] for event in new_events] == ["timeline_changed"]
    assert _outbox_count(db) == 0


def test_acknowledgement_does_not_delete_a_concurrent_replacement(monkeypatch):
    db, project_id, revision = _timeline_project()
    _commit_timeline_lane(db, project_id, revision)
    old_row = db.get_pending_api_events()[0]
    acknowledge = db.acknowledge_api_events
    replacement_state = {}

    def replace_before_ack(events):
        monkeypatch.setattr(db, "acknowledge_api_events", acknowledge)
        db.delete_project(project_id)
        replacement = db.create_project("Replacement", narrative_engine="novel")
        snapshot = db.read_timeline_snapshot(replacement.id)
        _commit_timeline_lane(
            db,
            replacement.id,
            snapshot.revision,
            key="outbox-concurrent-replacement-01",
        )
        replacement_state["project_id"] = replacement.id
        replacement_state["row"] = db.get_pending_api_events()[0]
        return acknowledge(events)

    monkeypatch.setattr(db, "acknowledge_api_events", replace_before_ack)
    broker = ApiEventBroker(db)
    replacement_row = replacement_state["row"]
    assert replacement_row.id == old_row.id
    assert replacement_row.data_json != old_row.data_json
    assert _outbox_count(db) == 1

    assert broker.reconcile() == 1
    assert len(broker.events_since(0, replacement_state["project_id"])) == 2
    assert _outbox_count(db) == 0


def test_poll_and_live_stream_signal_ring_truncation():
    db, project_id, _revision = _timeline_project()
    other = db.create_project("Other", narrative_engine="novel")
    app = create_api(db=db)
    broker = ApiEventBroker(db, maxlen=2)
    app.state.broker = broker
    client = TestClient(app)

    initial = client.get(
        f"/api/projects/{project_id}/events/poll",
        params={"since": 0},
    ).json()
    assert initial["reset_required"] is False
    broker.publish("timeline_changed", project_id)
    broker.publish("timeline_changed", other.id)
    broker.publish("timeline_changed", other.id)

    truncated = client.get(
        f"/api/projects/{project_id}/events/poll",
        params={"since": initial["cursor"]},
    ).json()
    assert truncated["events"] == []
    assert truncated["cursor"] == 3
    assert truncated["reset_required"] is True

    async def observe_live_gap():
        live_broker = ApiEventBroker(db, maxlen=2)
        stream = live_broker.stream(
            project_id=project_id,
            heartbeat=60,
            poll_interval=0,
        )
        first = await anext(stream)
        live_broker.publish("timeline_changed", project_id)
        live_broker.publish("timeline_changed", other.id)
        live_broker.publish("timeline_changed", other.id)
        second = await anext(stream)
        await stream.aclose()
        return first, second

    first, second = asyncio.run(observe_live_gap())
    assert first.startswith("event: connected\n")
    assert second.startswith("event: connected\n")


def test_each_api_process_exposes_a_distinct_polling_identity():
    db, project_id, _revision = _timeline_project()
    first = TestClient(create_api(db=db)).get(
        f"/api/projects/{project_id}/events/poll"
    ).json()
    second = TestClient(create_api(db=db)).get(
        f"/api/projects/{project_id}/events/poll"
    ).json()
    assert first["broker_instance_id"] != second["broker_instance_id"]
    assert first["cursor"] == second["cursor"] == 0
