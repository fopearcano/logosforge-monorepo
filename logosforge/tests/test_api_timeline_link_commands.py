"""Transactional Timeline link and structure-link API coverage."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import text

from logosforge.api import create_api
from logosforge.db import Database


def _project():
    db = Database()
    project = db.create_project(
        "Timeline links",
        narrative_engine="novel",
        default_writing_format="novel",
    )
    return TestClient(create_api(db=db)), db, int(project.id)


def _timeline(client: TestClient, project_id: int) -> dict:
    response = client.get(f"/api/projects/{project_id}/timeline")
    assert response.status_code == 200
    return response.json()


def _command(client: TestClient, project_id: int, **body):
    return client.post(
        f"/api/projects/{project_id}/timeline/commands",
        json=body,
    )


def _event_scenes(db: Database, project_id: int):
    first = db.create_scene(
        project_id,
        "First",
        act="Act I",
        chapter="One",
        plotline="Main",
    )
    second = db.create_scene(
        project_id,
        "Second",
        act="Act II",
        chapter="Two",
        plotline="Main",
    )
    return first, second


def test_six_link_commands_are_revisioned_and_report_focused_ids():
    client, db, project_id = _project()
    first, second = _event_scenes(db, project_id)
    current = _timeline(client, project_id)

    create_body = {
        "kind": "create_link",
        "expected_revision": current["revision"],
        "source_scene_id": first.id,
        "target_scene_id": second.id,
        "link_type": "causality",
        "color_label": "cyan",
        "label": "therefore",
    }
    created = client.post(
        f"/api/projects/{project_id}/timeline/commands",
        headers={"Idempotency-Key": "timeline-link-create-001"},
        json=create_body,
    )
    assert created.status_code == 200
    created_body = created.json()
    link_id = created_body["created_link_id"]
    assert created_body["changed"] is True
    assert created_body["affected_link_ids"] == [link_id]
    assert created_body["affected_scene_ids"] == []
    assert created_body["created_structure_link_id"] is None
    assert created_body["timeline"]["links"] == [{
        "id": link_id,
        "source_scene_id": first.id,
        "target_scene_id": second.id,
        "link_type": "causality",
        "color_label": "cyan",
        "label": "therefore",
        "created_at": created_body["timeline"]["links"][0]["created_at"],
    }]

    replay = client.post(
        f"/api/projects/{project_id}/timeline/commands",
        headers={"Idempotency-Key": "timeline-link-create-001"},
        json=create_body,
    )
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["changed"] is False
    assert replay.json()["created_link_id"] is None
    assert replay.json()["affected_link_ids"] == []
    assert replay.json()["timeline"] == created_body["timeline"]

    receipt = client.get(
        f"/api/projects/{project_id}/timeline/command-receipt",
        headers={"Idempotency-Key": "timeline-link-create-001"},
    )
    assert receipt.status_code == 200
    assert receipt.json()["original_affected_link_ids"] == [link_id]
    assert receipt.json()["original_created_link_id"] == link_id

    updated = _command(
        client,
        project_id,
        kind="update_link",
        expected_revision=created_body["timeline"]["revision"],
        link_id=link_id,
        link_type="setup_payoff",
        color_label="amber",
        label="payoff",
    )
    assert updated.status_code == 200
    updated_body = updated.json()
    assert updated_body["affected_link_ids"] == [link_id]
    assert updated_body["timeline"]["links"][0]["link_type"] == "setup_payoff"

    reverse_duplicate = _command(
        client,
        project_id,
        kind="create_link",
        expected_revision=updated_body["timeline"]["revision"],
        source_scene_id=second.id,
        target_scene_id=first.id,
    )
    assert reverse_duplicate.status_code == 200
    assert reverse_duplicate.json()["changed"] is False
    assert reverse_duplicate.json()["created_link_id"] is None
    assert reverse_duplicate.json()["timeline"] == updated_body["timeline"]

    deleted = _command(
        client,
        project_id,
        kind="delete_link",
        expected_revision=updated_body["timeline"]["revision"],
        link_id=link_id,
    )
    assert deleted.status_code == 200
    deleted_body = deleted.json()
    assert deleted_body["affected_link_ids"] == [link_id]
    assert deleted_body["timeline"]["links"] == []

    structure_created = _command(
        client,
        project_id,
        kind="create_structure_link",
        expected_revision=deleted_body["timeline"]["revision"],
        source_scene_id=first.id,
        target_type="act",
        target_ref="Act I",
    )
    assert structure_created.status_code == 200
    structure_body = structure_created.json()
    structure_link_id = structure_body["created_structure_link_id"]
    assert structure_body["affected_structure_link_ids"] == [
        structure_link_id
    ]
    assert structure_body["timeline"]["structure_links"][0][
        "target_exists"
    ] is True

    structure_updated = _command(
        client,
        project_id,
        kind="update_structure_link",
        expected_revision=structure_body["timeline"]["revision"],
        structure_link_id=structure_link_id,
        target_type="chapter",
        target_ref="Two",
    )
    assert structure_updated.status_code == 200
    structure_updated_body = structure_updated.json()
    assert structure_updated_body["affected_structure_link_ids"] == [
        structure_link_id
    ]
    assert structure_updated_body["timeline"]["structure_links"][0][
        "target_ref"
    ] == "Two"

    structure_deleted = _command(
        client,
        project_id,
        kind="delete_structure_link",
        expected_revision=structure_updated_body["timeline"]["revision"],
        structure_link_id=structure_link_id,
    )
    assert structure_deleted.status_code == 200
    assert structure_deleted.json()["affected_structure_link_ids"] == [
        structure_link_id
    ]
    assert structure_deleted.json()["timeline"]["structure_links"] == []


def test_creation_requires_current_membership_but_dormant_rows_can_be_repaired():
    client, db, project_id = _project()
    event, other_event = _event_scenes(db, project_id)
    dormant = db.create_scene(
        project_id,
        "Dormant",
        act="Act I",
        chapter="One",
    )
    event_link = db.add_timeline_link(project_id, event.id, dormant.id)
    structure_link = db.add_timeline_structure_link(
        project_id, dormant.id, "act", "Missing Act",
    )
    current = _timeline(client, project_id)
    assert current["links"][0]["id"] == event_link.id
    assert current["structure_links"][0] | {"created_at": "ignored"} == {
        "id": structure_link.id,
        "source_scene_id": dormant.id,
        "target_type": "act",
        "target_ref": "Missing Act",
        "target_exists": False,
        "created_at": "ignored",
    }

    create_event_link = _command(
        client,
        project_id,
        kind="create_link",
        expected_revision=current["revision"],
        source_scene_id=other_event.id,
        target_scene_id=dormant.id,
    )
    create_structure_link = _command(
        client,
        project_id,
        kind="create_structure_link",
        expected_revision=current["revision"],
        source_scene_id=dormant.id,
        target_type="act",
        target_ref="Act I",
    )
    assert create_event_link.status_code == 400
    assert create_structure_link.status_code == 400

    repaired_event = _command(
        client,
        project_id,
        kind="update_link",
        expected_revision=current["revision"],
        link_id=event_link.id,
        label="kept while dormant",
    )
    assert repaired_event.status_code == 200
    repaired_structure = _command(
        client,
        project_id,
        kind="update_structure_link",
        expected_revision=repaired_event.json()["timeline"]["revision"],
        structure_link_id=structure_link.id,
        target_ref="Act I",
    )
    assert repaired_structure.status_code == 200
    assert repaired_structure.json()["timeline"]["structure_links"][0][
        "target_exists"
    ] is True

    deleted_event = _command(
        client,
        project_id,
        kind="delete_link",
        expected_revision=repaired_structure.json()["timeline"]["revision"],
        link_id=event_link.id,
    )
    assert deleted_event.status_code == 200
    deleted_structure = _command(
        client,
        project_id,
        kind="delete_structure_link",
        expected_revision=deleted_event.json()["timeline"]["revision"],
        structure_link_id=structure_link.id,
    )
    assert deleted_structure.status_code == 200


def test_foreign_and_missing_link_endpoints_fail_closed_with_stable_error():
    for endpoint_kind in ("foreign", "missing"):
        client, db, project_id = _project()
        source, _ = _event_scenes(db, project_id)
        clean = _timeline(client, project_id)
        if endpoint_kind == "foreign":
            other_project = db.create_project("Other")
            target_id = db.create_scene(other_project.id, "Foreign").id
            db.add_timeline_link(project_id, source.id, target_id)
        else:
            with db._engine.connect() as connection:
                connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
                connection.execute(text("""
                    INSERT INTO timelinelink (
                        project_id, source_scene_id, target_scene_id,
                        color_label, link_type, label, created_at
                    ) VALUES (
                        :project_id, :source_id, :target_id,
                        'gray', 'custom', '', :created_at
                    )
                """), {
                    "project_id": project_id,
                    "source_id": source.id,
                    "target_id": 999_999,
                    "created_at": datetime.now(timezone.utc),
                })
                connection.commit()
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")

        read = client.get(f"/api/projects/{project_id}/timeline")
        command = _command(
            client,
            project_id,
            kind="set_order_mode",
            expected_revision=clean["revision"],
            mode="custom",
        )
        for response in (read, command):
            assert response.status_code == 500
            assert response.json() == {
                "error": {
                    "code": "timeline_state_corrupt",
                    "message": (
                        "Timeline state is inconsistent. Repair it before "
                        "continuing Timeline edits."
                    ),
                }
            }


def test_link_rows_participate_in_revision_but_prose_still_does_not():
    client, db, project_id = _project()
    first, second = _event_scenes(db, project_id)
    original = _timeline(client, project_id)
    link = db.add_timeline_link(project_id, first.id, second.id)
    with_link = _timeline(client, project_id)
    assert with_link["revision"] != original["revision"]

    db.set_timeline_link_label(link.id, "revised")
    with_label = _timeline(client, project_id)
    assert with_label["revision"] != with_link["revision"]

    prose_update = client.patch(
        f"/api/projects/{project_id}/scenes/{first.id}",
        json={"content": "New prose only"},
    )
    assert prose_update.status_code == 200
    after_prose = _timeline(client, project_id)
    assert after_prose["revision"] == with_label["revision"]

    db.add_timeline_structure_link(project_id, first.id, "act", "Act I")
    after_structure_link = _timeline(client, project_id)
    assert after_structure_link["revision"] != after_prose["revision"]


def test_v1_receipt_remains_readable_and_defaults_v2_fields():
    client, db, project_id = _project()
    revision = _timeline(client, project_id)["revision"]
    key = "timeline-v1-receipt-001"
    result = json.dumps({
        "schema_version": 1,
        "kind": "create_lane",
        "expected_revision": revision,
        "applied_revision": revision,
        "original_changed": False,
        "original_affected_scene_ids": [],
    })
    with db._engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO timelinecommandreceipt (
                project_id, idempotency_key_hash, request_digest,
                result_json, created_at
            ) VALUES (
                :project_id, :key_hash, :request_digest,
                :result_json, :created_at
            )
        """), {
            "project_id": project_id,
            "key_hash": hashlib.sha256(key.encode("ascii")).hexdigest(),
            "request_digest": "a" * 64,
            "result_json": result,
            "created_at": datetime.now(timezone.utc),
        })

    response = client.get(
        f"/api/projects/{project_id}/timeline/command-receipt",
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["command_kind"] == "create_lane"
    assert body["original_affected_scene_ids"] == []
    assert body["original_affected_link_ids"] == []
    assert body["original_affected_structure_link_ids"] == []
    assert body["original_created_link_id"] is None
    assert body["original_created_structure_link_id"] is None


def test_link_not_found_errors_have_stable_codes():
    client, _db, project_id = _project()
    current = _timeline(client, project_id)
    missing_link = _command(
        client,
        project_id,
        kind="delete_link",
        expected_revision=current["revision"],
        link_id=999,
    )
    missing_structure_link = _command(
        client,
        project_id,
        kind="delete_structure_link",
        expected_revision=current["revision"],
        structure_link_id=999,
    )
    assert missing_link.status_code == 404
    assert missing_link.json()["error"]["code"] == "timeline_link_not_found"
    assert missing_structure_link.status_code == 404
    assert missing_structure_link.json()["error"]["code"] == (
        "timeline_structure_link_not_found"
    )
