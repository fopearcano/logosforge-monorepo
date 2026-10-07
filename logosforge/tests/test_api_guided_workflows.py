"""Phase 7A Guided Workflow Project OS API and command guarantees."""

from __future__ import annotations

import json
import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from logosforge.api import create_api
from logosforge.db import Database


def _project(*, path: str | None = None, mode: str = "novel"):
    db = Database(path)
    project = db.create_project(
        "Workflow project",
        narrative_engine=mode,
        default_writing_format=mode,
    )
    return TestClient(create_api(db=db)), db, project.id


def _command(client, project_id, key, **body):
    return client.post(
        f"/api/projects/{project_id}/workflows/commands",
        headers={"Idempotency-Key": key},
        json=body,
    )


def _start(client, project_id, key="workflow-start-0001", **extra):
    response = _command(
        client,
        project_id,
        key,
        kind="start_workflow",
        template_id="project_setup",
        **extra,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_templates_are_mode_and_step_filtered():
    novel, _db, project_id = _project(mode="novel")
    templates = novel.get(
        f"/api/projects/{project_id}/workflow-templates"
    ).json()
    assert "screenplay_production_prep" not in {
        template["id"] for template in templates
    }
    drafting = next(
        template for template in templates if template["id"] == "scene_drafting"
    )
    assert all("screenplay" not in step["modes"] for step in drafting["steps"])

    screenplay, _db2, screenplay_id = _project(mode="screenplay")
    screenplay_templates = screenplay.get(
        f"/api/projects/{screenplay_id}/workflow-templates"
    ).json()
    assert "screenplay_production_prep" in {
        template["id"] for template in screenplay_templates
    }


def test_start_read_events_and_active_recommendation_suppression():
    client, _db, project_id = _project()
    before = client.get(
        f"/api/projects/{project_id}/workflow-recommendations"
    ).json()
    assert any(row["template_id"] == "project_setup" for row in before)
    started = _start(client, project_id)
    run = started["workflow"]
    assert started | {"workflow": None} == {
        "workflow": None,
        "changed": True,
        "replayed": False,
        "applied_revision": run["revision"],
    }
    assert len(run["revision"]) == 64
    assert run["steps"][0]["kind"] == "check"
    assert run["steps"][0]["completion_check"] == "project_has_title"

    fetched = client.get(
        f"/api/projects/{project_id}/workflows/{run['id']}"
    )
    assert fetched.status_code == 200
    assert fetched.json() == run
    events = client.get(
        f"/api/projects/{project_id}/workflows/{run['id']}/events"
    ).json()
    assert [event["event_type"] for event in events] == ["started"]
    after = client.get(
        f"/api/projects/{project_id}/workflow-recommendations"
    ).json()
    assert all(row["template_id"] != "project_setup" for row in after)


def test_exact_replay_is_durable_and_emits_one_broker_event(tmp_path):
    path = str(tmp_path / "workflow.db")
    client, db, project_id = _project(path=path)
    key = "workflow-durable-start-001"
    cursor = client.app.state.broker.latest_id()
    first = _start(client, project_id, key=key)
    replay = _start(client, project_id, key=key)
    assert replay["changed"] is False
    assert replay["replayed"] is True
    assert replay["applied_revision"] == first["applied_revision"]
    assert [event["event"] for event in client.app.state.broker.events_since(
        cursor, project_id,
    )] == ["workflow_changed"]
    assert [event.event_type for event in db.get_workflow_events(
        first["workflow"]["id"],
    )] == ["started"]

    receipt = client.get(
        f"/api/projects/{project_id}/workflows/command-receipt",
        headers={"Idempotency-Key": key},
    )
    assert receipt.status_code == 200
    assert receipt.headers["cache-control"] == "no-store"
    assert {"Authorization", "Idempotency-Key"} <= {
        item.strip() for item in receipt.headers["vary"].split(",")
    }
    assert receipt.json()["original_run_id"] == first["workflow"]["id"]
    with db._engine.connect() as connection:
        stored = connection.execute(text(
            "SELECT idempotency_key_hash, result_json "
            "FROM workflowcommandreceipt"
        )).fetchone()
    assert stored is not None and len(stored[0]) == 64
    assert key not in stored[0] and key not in stored[1]
    assert json.loads(stored[1])["schema_version"] == 1

    db._engine.dispose()
    reopened = Database(path)
    restarted = TestClient(create_api(db=reopened))
    recovered = _start(restarted, project_id, key=key)
    assert recovered["replayed"] is True
    assert len(reopened.get_workflow_runs(project_id)) == 1


def test_same_key_is_exactly_once_across_database_instances(tmp_path):
    path = str(tmp_path / "workflow-race.db")
    _client, seed, project_id = _project(path=path)
    first = Database(path)
    second = Database(path)
    barrier = threading.Barrier(3)
    results = []
    errors = []

    def start(database: Database) -> None:
        barrier.wait()
        try:
            results.append(database.execute_workflow_command(
                project_id,
                kind="start_workflow",
                template_id="project_setup",
                idempotency_key="workflow-cross-core-start-01",
            ))
        except Exception as exc:  # surfaced below with its original type
            errors.append(exc)

    one = threading.Thread(target=start, args=(first,))
    two = threading.Thread(target=start, args=(second,))
    one.start()
    two.start()
    barrier.wait()
    one.join(timeout=10)
    two.join(timeout=10)

    assert not one.is_alive() and not two.is_alive()
    assert errors == []
    assert sorted((result.changed, result.replayed) for result in results) == [
        (False, True),
        (True, False),
    ]
    runs = seed.get_workflow_runs(project_id)
    assert len(runs) == 1
    assert [event.event_type for event in seed.get_workflow_events(
        runs[0].id,
    )] == ["started"]
    first._engine.dispose()
    second._engine.dispose()


def test_key_conflict_stale_revision_and_state_guards_do_not_emit():
    client, _db, project_id = _project()
    start = _start(client, project_id, key="workflow-guard-start-01")
    run = start["workflow"]
    reused = _command(
        client,
        project_id,
        "workflow-guard-start-01",
        kind="start_workflow",
        template_id="scene_drafting",
    )
    assert reused.status_code == 409
    assert reused.json()["error"]["code"] == "idempotency_key_conflict"

    completed = _command(
        client,
        project_id,
        "workflow-guard-complete-01",
        kind="complete_step",
        run_id=run["id"],
        step_id="title",
        expected_revision=run["revision"],
    )
    assert completed.status_code == 200
    cursor = client.app.state.broker.latest_id()
    stale = _command(
        client,
        project_id,
        "workflow-guard-stale-0001",
        kind="pause",
        run_id=run["id"],
        expected_revision=run["revision"],
    )
    out_of_order = _command(
        client,
        project_id,
        "workflow-guard-order-0001",
        kind="complete_step",
        run_id=run["id"],
        step_id="mode",
        expected_revision=completed.json()["workflow"]["revision"],
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "workflow_conflict"
    assert out_of_order.status_code == 409
    assert out_of_order.json()["error"]["code"] == "workflow_state_conflict"
    assert client.app.state.broker.events_since(cursor, project_id) == []


def test_lifecycle_commands_and_terminal_guard():
    client, _db, project_id = _project()
    current = _start(client, project_id, key="workflow-life-start-001")["workflow"]
    advanced = _command(
        client, project_id, "workflow-life-advance-1",
        kind="advance", run_id=current["id"],
        expected_revision=current["revision"],
    ).json()["workflow"]
    assert advanced["current_step_id"] == "logline"
    paused = _command(
        client, project_id, "workflow-life-pause-001",
        kind="pause", run_id=current["id"],
        expected_revision=advanced["revision"],
    ).json()["workflow"]
    assert paused["status"] == "paused"
    resumed = _command(
        client, project_id, "workflow-life-resume-01",
        kind="resume", run_id=current["id"],
        expected_revision=paused["revision"],
    ).json()["workflow"]
    assert resumed["status"] == "active"
    cancelled = _command(
        client, project_id, "workflow-life-cancel-01",
        kind="cancel", run_id=current["id"],
        expected_revision=resumed["revision"],
    ).json()["workflow"]
    assert cancelled["status"] == "cancelled"
    rejected = _command(
        client, project_id, "workflow-life-terminal-1",
        kind="resume", run_id=current["id"],
        expected_revision=cancelled["revision"],
    )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "workflow_state_conflict"


def test_refresh_no_op_receipt_and_creative_steps_are_never_auto_completed():
    client, _db, project_id = _project()
    started = _command(
        client,
        project_id,
        "workflow-refresh-start-01",
        kind="start_workflow",
        template_id="scene_drafting",
    ).json()["workflow"]
    refreshed = _command(
        client,
        project_id,
        "workflow-refresh-noop-01",
        kind="refresh",
        run_id=started["id"],
        expected_revision=started["revision"],
    )
    assert refreshed.status_code == 200
    body = refreshed.json()
    assert body["changed"] is False
    assert body["workflow"]["revision"] == started["revision"]
    assert body["workflow"]["steps"][0]["kind"] == "creative"
    assert body["workflow"]["steps"][0]["status"] == "active"
    receipt = client.get(
        f"/api/projects/{project_id}/workflows/command-receipt",
        headers={"Idempotency-Key": "workflow-refresh-noop-01"},
    ).json()
    assert receipt["original_changed"] is False


def test_refresh_proves_checks_inside_its_sql_transaction(monkeypatch):
    client, db, project_id = _project()
    run = _start(
        client, project_id, key="workflow-refresh-coherent-start",
    )["workflow"]

    # A stale/out-of-transaction Project Intelligence report must be irrelevant
    # to completion. The command proves title state from its own SQL snapshot.
    import logosforge.project_intelligence as project_intelligence

    monkeypatch.setattr(
        project_intelligence,
        "build_project_intelligence_report",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("refresh must not read a separate report")
        ),
    )
    refreshed = _command(
        client,
        project_id,
        "workflow-refresh-coherent-01",
        kind="refresh",
        run_id=run["id"],
        expected_revision=run["revision"],
    )
    assert refreshed.status_code == 200
    result = refreshed.json()["workflow"]
    assert result["steps"][0]["status"] == "completed"
    assert result["current_step_id"] == "logline"
    assert db.get_project_by_id(project_id).title == "Workflow project"


def test_workflow_list_uses_batch_snapshot_not_legacy_torn_reads(monkeypatch):
    client, db, project_id = _project()
    _start(client, project_id, key="workflow-batch-list-start-1")

    monkeypatch.setattr(
        db,
        "get_workflow_run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("list must not re-read each run")
        ),
    )
    monkeypatch.setattr(
        db,
        "get_workflow_step_states",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("list must not re-read each run's steps")
        ),
    )
    response = client.get(f"/api/projects/{project_id}/workflows")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert len(response.json()[0]["revision"]) == 64


def test_revision_tracks_template_semantics_across_upgrade(monkeypatch):
    client, _db, project_id = _project()
    run = _start(
        client, project_id, key="workflow-template-revision-start",
    )["workflow"]
    from logosforge.guided_workflows.registry import get_template

    template = get_template("project_setup")
    assert template is not None
    monkeypatch.setattr(
        template.steps[0], "completion_check", "project_has_description",
    )
    upgraded = client.get(
        f"/api/projects/{project_id}/workflows/{run['id']}"
    ).json()
    assert upgraded["revision"] != run["revision"]
    stale = _command(
        client,
        project_id,
        "workflow-upgrade-stale-001",
        kind="refresh",
        run_id=run["id"],
        expected_revision=run["revision"],
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "workflow_conflict"


def test_recompute_stays_blocked_when_only_blocked_steps_remain():
    client, db, project_id = _project()
    run = _start(
        client, project_id, key="workflow-blocked-recompute-start",
    )["workflow"]
    states = db.get_workflow_step_states(run["id"])
    for state in states[1:]:
        db.update_workflow_step_state(state.id, status="blocked")
    current = client.get(
        f"/api/projects/{project_id}/workflows/{run['id']}"
    ).json()
    completed = _command(
        client,
        project_id,
        "workflow-blocked-recompute-01",
        kind="complete_step",
        run_id=run["id"],
        step_id="title",
        expected_revision=current["revision"],
    )
    assert completed.status_code == 200
    result = completed.json()["workflow"]
    assert result["status"] == "blocked"
    assert result["current_step_id"] == "logline"


def test_foreign_runs_are_non_disclosing_and_event_tail_is_bounded():
    client, db, project_id = _project()
    other = db.create_project("Other", narrative_engine="novel")
    foreign = db.create_workflow_run(
        other.id,
        template_id="project_setup",
        title="Foreign",
        writing_mode="novel",
    )
    assert client.get(
        f"/api/projects/{project_id}/workflows/{foreign.id}"
    ).status_code == 404
    missing = _command(
        client,
        project_id,
        "workflow-foreign-run-001",
        kind="pause",
        run_id=foreign.id,
        expected_revision="0" * 64,
    )
    assert missing.status_code == 404

    own = _start(client, project_id, key="workflow-events-start-01")["workflow"]
    for index in range(205):
        db.create_workflow_event(
            project_id,
            own["id"],
            event_type="note",
            message=str(index),
        )
    tail = client.get(
        f"/api/projects/{project_id}/workflows/{own['id']}/events?limit=200"
    )
    assert tail.status_code == 200
    assert len(tail.json()) == 200
    assert tail.json()[0]["message"] == "5"
    assert client.get(
        f"/api/projects/{project_id}/workflows/{own['id']}/events?limit=201"
    ).status_code == 422


def test_receipt_insert_failure_rolls_back_workflow_state(tmp_path):
    _client, db, project_id = _project(path=str(tmp_path / "rollback.db"))
    with db._engine.begin() as connection:
        connection.execute(text("""
            CREATE TRIGGER reject_workflow_receipt
            BEFORE INSERT ON workflowcommandreceipt
            BEGIN
                SELECT RAISE(ABORT, 'forced workflow receipt rollback');
            END;
        """))
    try:
        with pytest.raises(IntegrityError):
            db.execute_workflow_command(
                project_id,
                kind="start_workflow",
                template_id="project_setup",
                idempotency_key="workflow-rollback-start-1",
            )
    finally:
        with db._engine.begin() as connection:
            connection.execute(text("DROP TRIGGER reject_workflow_receipt"))
    assert db.get_workflow_runs(project_id) == []
    assert db.get_workflow_command_receipt(
        project_id, "workflow-rollback-start-1",
    ) is None


def test_commands_never_mutate_project_content_and_blocked_resume_is_coherent():
    client, db, project_id = _project()
    scene = db.create_scene(project_id, "Keep", content="IRREPLACEABLE")
    run = _start(client, project_id, key="workflow-content-start-01")["workflow"]
    db.update_workflow_run(
        run["id"], status="blocked", current_step_id="title",
    )
    first = db.get_workflow_step_states(run["id"])[0]
    db.update_workflow_step_state(first.id, status="blocked")
    blocked = client.get(
        f"/api/projects/{project_id}/workflows/{run['id']}"
    ).json()
    resumed = _command(
        client,
        project_id,
        "workflow-blocked-resume-1",
        kind="resume",
        run_id=run["id"],
        expected_revision=blocked["revision"],
    )
    assert resumed.status_code == 200
    result = resumed.json()["workflow"]
    assert result["status"] == "active"
    assert result["steps"][0]["status"] == "active"
    assert db.get_scene_by_id(scene.id).content == "IRREPLACEABLE"


def test_legacy_engine_writers_delegate_to_atomic_boundary(monkeypatch):
    from logosforge.guided_workflows import (
        complete_workflow_step,
        start_workflow,
    )

    _client, db, project_id = _project()

    def unsafe(*_args, **_kwargs):
        raise AssertionError("legacy multi-transaction writer was called")

    for name in (
        "create_workflow_run",
        "create_workflow_step_state",
        "create_workflow_event",
        "update_workflow_run",
        "update_workflow_step_state",
    ):
        monkeypatch.setattr(db, name, unsafe)

    started = start_workflow(db, project_id, "project_setup")
    assert started is not None
    completed = complete_workflow_step(db, started.run.id, "title")
    assert completed is not None
    assert completed.completed_steps == 1


def test_corrupt_cross_project_step_is_never_omitted_from_revision():
    _client, db, project_id = _project()
    other = db.create_project("Other", narrative_engine="novel")
    from logosforge.guided_workflows import start_workflow

    run = start_workflow(db, project_id, "project_setup")
    assert run is not None
    step_id = run.steps[0].id
    with db._engine.begin() as connection:
        connection.execute(
            text("UPDATE workflowstepstate SET project_id=:other WHERE id=:id"),
            {"other": other.id, "id": step_id},
        )

    with pytest.raises(
        RuntimeError,
        match="step project does not match its run",
    ):
        db.read_workflow_run_snapshot(project_id, run.run.id)
    with pytest.raises(
        RuntimeError,
        match="step project does not match its run",
    ):
        db.read_workflow_runs_snapshot(project_id)


def test_legacy_adapter_absorbs_concurrent_revision_change(monkeypatch):
    from logosforge.guided_workflows import advance_workflow_step, start_workflow

    _client, db, project_id = _project()
    run = start_workflow(db, project_id, "project_setup")
    assert run is not None
    original_execute = db.execute_workflow_command
    raced = False

    def execute_with_race(*args, **kwargs):
        nonlocal raced
        if kwargs.get("kind") == "advance" and not raced:
            raced = True
            current = db.read_workflow_run_snapshot(project_id, run.run.id)
            assert current is not None
            original_execute(
                project_id,
                kind="pause",
                run_id=run.run.id,
                expected_revision=current.revision,
                idempotency_key="workflow-legacy-race-pause",
            )
        return original_execute(*args, **kwargs)

    monkeypatch.setattr(db, "execute_workflow_command", execute_with_race)
    stable = advance_workflow_step(db, run.run.id)
    assert stable is not None
    assert stable.run.status == "paused"


def test_legacy_writing_mode_override_cannot_diverge_from_project():
    from logosforge.guided_workflows import start_workflow

    _client, db, project_id = _project(mode="novel")
    run = start_workflow(
        db,
        project_id,
        "project_setup",
        writing_mode="screenplay",
    )
    assert run is not None
    assert run.run.writing_mode == "novel"
    assert start_workflow(
        db,
        project_id,
        "screenplay_production_prep",
        writing_mode="screenplay",
    ) is None
