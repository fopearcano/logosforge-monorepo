"""Transactional Semantic Continuity issue-review commands."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session

from logosforge.api import create_api
from logosforge.continuity.collector import build_continuity_report
from logosforge.db import ContinuityRevisionConflict, Database
from logosforge.models import ContinuityIssue


def _project(*, path: str | None = None):
    db = Database(path)
    project = db.create_project("Continuity commands", narrative_engine="novel")
    db.create_psyke_entry(project.id, "Alice", "character")
    db.create_psyke_entry(project.id, "Solo", "character")
    db.create_psyke_entry(project.id, "Bob", "character")
    db.create_scene(
        project.id,
        "Open",
        content="Alice stood in the Kitchen.",
        location="Kitchen",
    )
    db.create_scene(
        project.id,
        "Next",
        content="Alice was at the Castle.",
        location="Castle",
    )
    db.create_scene(
        project.id,
        "Solo bit",
        content="Solo waved. Bob waited.",
        location="Castle",
    )
    db.create_scene(project.id, "Quiet", content="The rain fell.")
    db.create_scene(project.id, "Coda", content="Morning returned.")
    return TestClient(create_api(db=db)), db, project.id


def _report(client: TestClient, project_id: int) -> dict:
    response = client.get(f"/api/projects/{project_id}/continuity")
    assert response.status_code == 200, response.text
    return response.json()


def _command(
    client: TestClient,
    project_id: int,
    *,
    key: str | None,
    kind: str,
    revision: str,
    issue_id: str,
    fingerprint: str | None = None,
):
    if fingerprint is None:
        current = _report(client, project_id)
        fingerprint = next(
            (
                issue["review_fingerprint"]
                for issue in current["issues"]
                if issue["id"] == issue_id
            ),
            "0" * 64,
        )
    return client.post(
        f"/api/projects/{project_id}/continuity/commands",
        headers=None if key is None else {"Idempotency-Key": key},
        json={
            "kind": kind,
            "expected_revision": revision,
            "issue_id": issue_id,
            "expected_issue_fingerprint": fingerprint,
        },
    )


@pytest.mark.parametrize(("kind", "status"), [
    ("defer_issue", "deferred"),
    ("dismiss_issue", "dismissed"),
    ("resolve_issue", "resolved"),
])
def test_review_commands_require_confirmation_boundary_and_persist_status(
    kind: str,
    status: str,
):
    client, db, project_id = _project()
    initial = _report(client, project_id)
    issue = initial["issues"][0]
    assert initial["project_id"] == project_id
    assert len(initial["review_revision"]) == 64
    assert len(issue["review_fingerprint"]) == 64

    missing_key = _command(
        client,
        project_id,
        key=None,
        kind=kind,
        revision=initial["review_revision"],
        issue_id=issue["id"],
    )
    assert missing_key.status_code == 400

    response = _command(
        client,
        project_id,
        key=f"continuity-{kind}-0001",
        kind=kind,
        revision=initial["review_revision"],
        issue_id=issue["id"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["changed"] is True and body["replayed"] is False
    assert body["affected_issue_id"] == issue["id"]
    assert body["previous_status"] == "open"
    assert body["status"] == status
    assert body["applied_revision"] != initial["review_revision"]
    assert body["continuity"]["review_revision"] == body["applied_revision"]
    reviewed = next(
        item for item in body["continuity"]["issues"]
        if item["id"] == issue["id"]
    )
    assert reviewed["status"] == status
    assert db.get_continuity_issue_by_key(project_id, issue["id"]).status == status


def test_exact_replay_returns_current_report_and_original_applied_revision():
    client, _db, project_id = _project()
    initial = _report(client, project_id)
    first, second = initial["issues"][:2]
    key = "continuity-durable-retry-01"
    cursor = client.app.state.broker.latest_id()

    applied = _command(
        client,
        project_id,
        key=key,
        kind="defer_issue",
        revision=initial["review_revision"],
        issue_id=first["id"],
    ).json()
    advanced = _command(
        client,
        project_id,
        key="continuity-second-command-01",
        kind="resolve_issue",
        revision=applied["continuity"]["review_revision"],
        issue_id=second["id"],
    ).json()

    replay = _command(
        client,
        project_id,
        key=key,
        kind="defer_issue",
        revision=initial["review_revision"],
        issue_id=first["id"],
    )
    assert replay.status_code == 200, replay.text
    body = replay.json()
    assert body["replayed"] is True and body["changed"] is False
    assert body["applied_revision"] == applied["applied_revision"]
    assert body["continuity"]["review_revision"] == advanced["applied_revision"]
    events = client.app.state.broker.events_since(cursor, project_id)
    assert [event["event"] for event in events] == [
        "continuity_changed", "continuity_changed",
    ]


def test_key_reuse_stale_revision_and_foreign_issue_fail_without_receipts():
    client, db, project_id = _project()
    initial = _report(client, project_id)
    issue = initial["issues"][0]
    key = "continuity-key-conflict-01"
    applied = _command(
        client,
        project_id,
        key=key,
        kind="dismiss_issue",
        revision=initial["review_revision"],
        issue_id=issue["id"],
    )
    assert applied.status_code == 200

    mismatch = _command(
        client,
        project_id,
        key=key,
        kind="resolve_issue",
        revision=initial["review_revision"],
        issue_id=issue["id"],
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "idempotency_key_conflict"

    remaining = next(
        item for item in applied.json()["continuity"]["issues"]
        if item["status"] == "open"
    )
    stale_key = "continuity-stale-revision-01"
    stale = _command(
        client,
        project_id,
        key=stale_key,
        kind="defer_issue",
        revision=initial["review_revision"],
        issue_id=remaining["id"],
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "continuity_conflict"
    assert db.get_continuity_command_receipt(project_id, stale_key) is None

    foreign_key = "continuity-foreign-issue-01"
    foreign = _command(
        client,
        project_id,
        key=foreign_key,
        kind="resolve_issue",
        revision=applied.json()["continuity"]["review_revision"],
        issue_id="0123456789abcdef",
    )
    assert foreign.status_code == 404
    assert db.get_continuity_command_receipt(project_id, foreign_key) is None


def test_receipt_is_hashed_capability_scoped_and_no_store():
    client, db, project_id = _project()
    initial = _report(client, project_id)
    issue = initial["issues"][0]
    key = "continuity-receipt-proof-01"
    applied = _command(
        client,
        project_id,
        key=key,
        kind="resolve_issue",
        revision=initial["review_revision"],
        issue_id=issue["id"],
    ).json()

    response = client.get(
        f"/api/projects/{project_id}/continuity/command-receipt",
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert {part.strip() for part in response.headers["vary"].split(",")} >= {
        "Authorization", "Idempotency-Key",
    }
    receipt = response.json()
    assert receipt["command_kind"] == "resolve_issue"
    assert receipt["applied_revision"] == applied["applied_revision"]
    assert receipt["original_affected_issue_id"] == issue["id"]
    assert receipt["expected_issue_fingerprint"] == issue["review_fingerprint"]
    assert receipt["status"] == "resolved"

    with db._engine.connect() as connection:
        stored = connection.execute(text(
            "SELECT idempotency_key_hash, result_json "
            "FROM continuitycommandreceipt"
        )).one()
    assert len(stored[0]) == 64
    assert key not in stored[0] and key not in stored[1]

    for bad, expected in ((None, 400), ("continuity-unknown-key-01", 404)):
        missing = client.get(
            f"/api/projects/{project_id}/continuity/command-receipt",
            headers=None if bad is None else {"Idempotency-Key": bad},
        )
        assert missing.status_code == expected
        assert missing.headers["cache-control"] == "no-store"


def test_receipt_and_status_survive_api_restart(tmp_path: Path):
    path = tmp_path / "continuity.db"
    client, db, project_id = _project(path=str(path))
    initial = _report(client, project_id)
    issue = initial["issues"][0]
    key = "continuity-restart-retry-01"
    applied = _command(
        client,
        project_id,
        key=key,
        kind="defer_issue",
        revision=initial["review_revision"],
        issue_id=issue["id"],
    ).json()
    db._engine.dispose()

    restarted_db = Database(str(path))
    restarted = TestClient(create_api(db=restarted_db))
    replay = _command(
        restarted,
        project_id,
        key=key,
        kind="defer_issue",
        revision=initial["review_revision"],
        issue_id=issue["id"],
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert replay.json()["applied_revision"] == applied["applied_revision"]
    assert restarted_db.get_continuity_issue_by_key(
        project_id, issue["id"],
    ).status == "deferred"
    restarted_db._engine.dispose()


def test_project_scope_delete_and_corrupt_duplicate_state():
    client, db, first_id = _project()
    second = db.create_project("Other", narrative_engine="novel")
    db.create_psyke_entry(second.id, "Only", "character")
    db.create_scene(second.id, "Only scene", content="Only appeared.")
    db.create_scene(second.id, "After", content="Silence followed.")
    key = "continuity-project-scope-01"
    first = _report(client, first_id)
    second_report = _report(client, second.id)
    assert _command(
        client, first_id, key=key, kind="defer_issue",
        revision=first["review_revision"], issue_id=first["issues"][0]["id"],
    ).status_code == 200
    assert _command(
        client, second.id, key=key, kind="defer_issue",
        revision=second_report["review_revision"],
        issue_id=second_report["issues"][0]["id"],
    ).status_code == 200
    assert db.get_continuity_command_receipt(first_id, key) is not None
    assert db.get_continuity_command_receipt(second.id, key) is not None
    db.delete_project(first_id)
    assert db.get_continuity_command_receipt(first_id, key) is None
    assert db.get_continuity_command_receipt(second.id, key) is not None

    existing = db.get_continuity_issues(second.id)[0]
    with Session(db._engine) as session:
        session.add(ContinuityIssue(
            project_id=second.id,
            issue_key=existing.issue_key,
            status="open",
        ))
        session.commit()
    corrupt = client.get(f"/api/projects/{second.id}/continuity")
    assert corrupt.status_code == 500
    assert corrupt.json()["error"]["code"] == "continuity_review_state_corrupt"
    assert existing.title not in corrupt.text


def test_failed_receipt_write_rolls_back_issue_status(monkeypatch):
    client, db, project_id = _project()
    initial = _report(client, project_id)
    issue = initial["issues"][0]
    from logosforge.db import database as database_module

    def fail_receipt(**_kwargs):
        raise RuntimeError("simulated receipt failure")

    monkeypatch.setattr(
        database_module,
        "_continuity_receipt_result_json",
        fail_receipt,
    )
    with pytest.raises(RuntimeError, match="simulated receipt failure"):
        db.execute_continuity_command(
            project_id,
            kind="resolve_issue",
            expected_revision=initial["review_revision"],
            issue_key=issue["id"],
            expected_issue_fingerprint=issue["review_fingerprint"],
            idempotency_key="continuity-rollback-proof-01",
            issue=next(
                item for item in __import__(
                    "logosforge.continuity.collector",
                    fromlist=["build_continuity_report"],
                ).build_continuity_report(db, project_id).issues
                if item.issue_key == issue["id"]
            ),
        )
    assert db.get_continuity_issue_by_key(project_id, issue["id"]) is None
    assert db.get_continuity_command_receipt(
        project_id, "continuity-rollback-proof-01",
    ) is None


def test_exact_finding_fingerprint_blocks_stale_review_with_same_issue_key():
    _client, db, project_id = _project()
    report = build_continuity_report(db, project_id)
    issue = report.issues[0]
    reviewed_fingerprint = issue.review_fingerprint
    issue.explanation += " New evidence changed the reviewed finding."
    assert issue.issue_key == report.issues[0].issue_key
    assert issue.review_fingerprint != reviewed_fingerprint

    with pytest.raises(ContinuityRevisionConflict):
        db.execute_continuity_command(
            project_id,
            kind="resolve_issue",
            expected_revision=report.review_revision,
            issue_key=issue.issue_key,
            expected_issue_fingerprint=reviewed_fingerprint,
            idempotency_key="continuity-stale-fingerprint-01",
            issue=issue,
        )
    assert db.get_continuity_issue_by_key(project_id, issue.issue_key) is None
    assert db.get_continuity_command_receipt(
        project_id, "continuity-stale-fingerprint-01",
    ) is None
