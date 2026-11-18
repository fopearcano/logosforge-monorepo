from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlmodel import Session

from logosforge.api import create_api
from logosforge.db import Database
from logosforge.models.models import (
    ApiEventOutbox,
    ChatMessage,
    ChatSummary,
    ContinuityIssue,
    ControlledApplyOperation,
    OutlineNode,
    ProductionDraft,
    QuantumStateRecord,
    RevisionChange,
    RevisionDiffSnapshot,
    RevisionImpactReport,
    RevisionSet,
    RewriteApplyRecord,
    RewriteSession,
    RewriteVariant,
    Stage,
    StageSnapshot,
    StoryLink,
    TimelineCommandReceipt,
)
from logosforge.project_cloud_snapshot import (
    ProjectCloudSnapshotConflict,
    ProjectCloudSnapshotError,
    apply_project_cloud_snapshot,
    build_project_cloud_snapshot,
    validate_project_cloud_snapshot,
)
from logosforge.stages import restore_snapshot


def _story(db: Database, title: str = "Cloud Story") -> int:
    project = db.create_project(title)
    entry = db.create_psyke_entry(project.id, "Ada", "character")
    character = db.create_character(project.id, "Ada", "Lead investigator")
    db.set_character_psyke_entry(character.id, entry.id)
    db.create_scene(
        project.id,
        "Opening",
        content="The observatory wakes before dawn.",
        character_ids=[character.id],
    )
    db.create_note(project.id, "Research", "Check the lunar calendar.")
    return project.id


def _redigest(snapshot: dict) -> None:
    digest_payload = {key: item for key, item in snapshot.items() if key != "digest"}
    snapshot["digest"] = hashlib.sha256(json.dumps(
        digest_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def test_round_trip_digest_is_stable_when_target_ids_collide() -> None:
    source = Database()
    source_id = _story(source)
    source_snapshot = build_project_cloud_snapshot(source, source_id)

    target = Database()
    unrelated = target.create_project("Unrelated local project")
    # Force every common integer table to allocate ids that collide with, and
    # move beyond, the source database's ids.
    for index in range(8):
        target.create_scene(unrelated.id, f"Other scene {index}")
        target.create_character(unrelated.id, f"Other character {index}")
        target.create_note(unrelated.id, f"Other note {index}")
        target.create_psyke_entry(unrelated.id, f"Other entry {index}")

    result = apply_project_cloud_snapshot(
        target,
        source_snapshot,
        mode="import",
        restore_id=str(uuid4()),
    )
    restored_snapshot = build_project_cloud_snapshot(target, result.project_id)

    assert restored_snapshot["digest"] == source_snapshot["digest"]
    assert len(target.get_all_scenes(unrelated.id)) == 8
    assert target.get_project_by_id(unrelated.id).title == "Unrelated local project"


def test_stage_and_continuity_json_ids_remap_without_cross_project_writes() -> None:
    source = Database()
    source_id = _story(source, "Portable Stage")
    source_scene = source.get_all_scenes(source_id)[0]
    source_character = source.get_all_characters(source_id)[0]
    with Session(source._engine, expire_on_commit=False) as session:
        stage = Stage(
            project_id=source_id,
            name="Historical scene",
            scope_type="scene",
            scope_id=source_scene.id,
        )
        session.add(stage)
        session.flush()
        session.add(StageSnapshot(
            stage_id=stage.id,
            data_json=json.dumps({
                "scope_type": "scene",
                "scope_id": source_scene.id,
                "data": {
                    "title": "Historical title",
                    "content": "Historical content",
                    "character_ids": [source_character.id],
                    "character_states": [{
                        "character_id": source_character.id,
                        "state": "determined",
                    }],
                },
            }),
        ))
        session.add(ContinuityIssue(
            project_id=source_id,
            issue_key="portable-stage-scene",
            related_scene_ids_json=json.dumps([source_scene.id]),
        ))
        session.commit()
    source_snapshot = build_project_cloud_snapshot(source, source_id)

    target = Database()
    unrelated_id = _story(target, "Unrelated local project")
    unrelated_scene = target.get_all_scenes(unrelated_id)[0]
    unrelated_before = (unrelated_scene.title, unrelated_scene.content)

    malicious_stage = deepcopy(source_snapshot)
    malicious_stage_value = malicious_stage["tables"]["stagesnapshot"][0][
        "values"
    ]
    malicious_stage_payload = json.loads(malicious_stage_value["data_json"])
    malicious_stage_payload["scope_id"] = source_scene.id
    malicious_stage_value["data_json"] = json.dumps(
        malicious_stage_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    _redigest(malicious_stage)
    with pytest.raises(ProjectCloudSnapshotError, match="portable reference"):
        apply_project_cloud_snapshot(
            target,
            malicious_stage,
            mode="import",
            restore_id=str(uuid4()),
        )

    malicious_continuity = deepcopy(source_snapshot)
    malicious_issue_value = malicious_continuity["tables"]["continuityissue"][0][
        "values"
    ]
    malicious_issue_value["related_scene_ids_json"] = json.dumps([source_scene.id])
    _redigest(malicious_continuity)
    with pytest.raises(ProjectCloudSnapshotError, match="portable reference"):
        apply_project_cloud_snapshot(
            target,
            malicious_continuity,
            mode="import",
            restore_id=str(uuid4()),
        )

    assert len(target.get_all_projects()) == 1
    assert len(target.get_all_scenes(unrelated_id)) == 1
    unchanged_unrelated = target.get_scene_by_id(unrelated_scene.id)
    assert (unchanged_unrelated.title, unchanged_unrelated.content) == unrelated_before

    result = apply_project_cloud_snapshot(
        target,
        source_snapshot,
        mode="import",
        restore_id=str(uuid4()),
    )
    imported_scene = target.get_all_scenes(result.project_id)[0]
    imported_character = target.get_all_characters(result.project_id)[0]

    with Session(target._engine) as session:
        imported_stage_snapshot = session.execute(
            select(StageSnapshot)
            .join(Stage, StageSnapshot.stage_id == Stage.id)
            .where(Stage.project_id == result.project_id)
        ).scalar_one()
        imported_issue = session.execute(
            select(ContinuityIssue).where(
                ContinuityIssue.project_id == result.project_id
            )
        ).scalar_one()
        stage_payload = json.loads(imported_stage_snapshot.data_json)
        assert stage_payload["scope_id"] == imported_scene.id
        assert stage_payload["data"]["character_ids"] == [imported_character.id]
        assert stage_payload["data"]["character_states"][0]["character_id"] == (
            imported_character.id
        )
        assert json.loads(imported_issue.related_scene_ids_json) == [imported_scene.id]
        imported_stage_snapshot_id = imported_stage_snapshot.id

    assert build_project_cloud_snapshot(target, result.project_id)["digest"] == (
        source_snapshot["digest"]
    )
    restored = restore_snapshot(
        target,
        result.project_id,
        imported_stage_snapshot_id,
        take_safety=False,
    )
    assert restored["ok"] is True
    unrelated_after = target.get_scene_by_id(unrelated_scene.id)
    assert (unrelated_after.title, unrelated_after.content) == unrelated_before
    restored_imported = target.get_scene_by_id(imported_scene.id)
    assert restored_imported.title == "Historical title"
    assert restored_imported.content == "Historical content"
    assert target.get_scene_character_ids(imported_scene.id) == [imported_character.id]


def test_restore_is_atomic_preserves_local_path_and_drops_operational_rows() -> None:
    source = Database()
    source_id = _story(source, "Remote winner")
    source_snapshot = build_project_cloud_snapshot(source, source_id)

    target = Database()
    target_id = _story(target, "Local loser")
    target.patch_project_settings(target_id, {"source_path": "D:/local/story.lf"})
    current = build_project_cloud_snapshot(target, target_id)
    with Session(target._engine) as session:
        session.add(ApiEventOutbox(
            project_id=target_id,
            event_name="stale_event",
            data_json="{}",
        ))
        session.add(TimelineCommandReceipt(
            project_id=target_id,
            idempotency_key_hash="a" * 64,
            request_digest="b" * 64,
            result_json="{}",
        ))
        session.commit()

    with pytest.raises(ProjectCloudSnapshotError, match="expected local digest"):
        apply_project_cloud_snapshot(
            target,
            source_snapshot,
            mode="replace",
            target_project_id=target_id,
            expected_current_digest=None,
            restore_id=str(uuid4()),
        )
    assert target.get_project_by_id(target_id).title == "Local loser"

    restore_id = str(uuid4())
    result = apply_project_cloud_snapshot(
        target,
        source_snapshot,
        mode="replace",
        target_project_id=target_id,
        expected_current_digest=current["digest"],
        restore_id=restore_id,
    )
    replay = apply_project_cloud_snapshot(
        target,
        source_snapshot,
        mode="replace",
        target_project_id=target_id,
        # A receipt replay remains safe even when the caller no longer has CAS.
        expected_current_digest=None,
        restore_id=restore_id,
    )

    assert result == replay
    assert target.get_project_by_id(target_id).title == "Remote winner"
    assert target.get_project_settings(target_id)["source_path"] == "D:/local/story.lf"
    with Session(target._engine) as session:
        assert session.scalar(select(func.count()).select_from(ApiEventOutbox).where(
            ApiEventOutbox.project_id == target_id
        )) == 0
        assert session.scalar(select(func.count()).select_from(TimelineCommandReceipt).where(
            TimelineCommandReceipt.project_id == target_id
        )) == 0


def test_tamper_and_restore_id_reuse_fail_closed_without_mutation() -> None:
    source = Database()
    first_id = _story(source, "First")
    second_id = _story(source, "Second")
    first = build_project_cloud_snapshot(source, first_id)
    second = build_project_cloud_snapshot(source, second_id)
    tampered = deepcopy(first)
    tampered["tables"]["project"][0]["values"]["title"] = "Tampered"

    target = Database()
    restore_id = str(uuid4())
    before = len(target.get_all_projects())
    with pytest.raises(ProjectCloudSnapshotError, match="digest"):
        apply_project_cloud_snapshot(
            target,
            tampered,
            mode="import",
            restore_id=str(uuid4()),
        )
    assert len(target.get_all_projects()) == before

    wrong_type = deepcopy(first)
    wrong_type["tables"]["scene"][0]["values"]["sort_order"] = "first"
    _redigest(wrong_type)
    with pytest.raises(ProjectCloudSnapshotError, match="wrong type"):
        apply_project_cloud_snapshot(
            target,
            wrong_type,
            mode="import",
            restore_id=str(uuid4()),
        )
    assert len(target.get_all_projects()) == before

    apply_project_cloud_snapshot(
        target,
        first,
        mode="import",
        restore_id=restore_id,
    )
    with pytest.raises(ProjectCloudSnapshotConflict, match="restore id"):
        apply_project_cloud_snapshot(
            target,
            second,
            mode="fork",
            restore_id=restore_id,
        )
    assert len(target.get_all_projects()) == before + 1


def test_device_local_and_receipt_metadata_do_not_change_content_digest() -> None:
    db = Database()
    project_id = _story(db)
    first = build_project_cloud_snapshot(db, project_id)
    db.patch_project_settings(project_id, {"source_path": "C:/device/one.lf"})
    second = build_project_cloud_snapshot(db, project_id)
    assert second["digest"] == first["digest"]
    assert validate_project_cloud_snapshot(second)["digest"] == first["digest"]


def test_soft_references_and_quantum_json_remap_with_round_trip_digest() -> None:
    source = Database()
    project_id = _story(source, "Reference graph")
    scene = source.get_all_scenes(project_id)[0]
    with Session(source._engine, expire_on_commit=False) as session:
        parent = OutlineNode(project_id=project_id, title="Act I")
        session.add(parent)
        session.flush()
        child = OutlineNode(
            project_id=project_id,
            parent_id=parent.id,
            scene_id=scene.id,
            title="Opening node",
        )
        message = ChatMessage(project_id=project_id, role="user", content="Remember this")
        session.add_all([child, message])
        session.flush()
        session.add(ChatSummary(
            project_id=project_id,
            summary="Earlier discussion",
            last_summarized_message_id=message.id,
        ))
        draft = ProductionDraft(project_id=project_id, name="Blue draft")
        session.add(draft)
        session.flush()
        revision_set = RevisionSet(
            project_id=project_id, draft_id=draft.id, label="Blue pages",
        )
        session.add(revision_set)
        session.flush()
        change = RevisionChange(
            project_id=project_id,
            draft_id=draft.id,
            revision_set_id=revision_set.id,
            scene_id=scene.id,
            summary="Opening changed",
        )
        session.add(change)
        session.flush()
        report = RevisionImpactReport(
            project_id=project_id,
            draft_id=draft.id,
            revision_set_id=revision_set.id,
            scene_id=scene.id,
            source_revision_change_id=change.id,
            title="Impact",
        )
        session.add(report)
        session.flush()
        session.add(RevisionDiffSnapshot(
            project_id=project_id,
            scene_id=scene.id,
            revision_set_id=revision_set.id,
        ))
        rewrite_session = RewriteSession(
            project_id=project_id,
            source_type="scene",
            source_id=scene.id,
            title="Rewrite",
        )
        session.add(rewrite_session)
        session.flush()
        variant = RewriteVariant(
            project_id=project_id,
            session_id=rewrite_session.id,
            impact_report_id=report.id,
            label="Variant A",
        )
        stage = Stage(
            project_id=project_id,
            name="Before rewrite",
            scope_type="scene",
            scope_id=scene.id,
        )
        session.add_all([variant, stage])
        session.flush()
        session.add(RewriteApplyRecord(
            project_id=project_id,
            session_id=rewrite_session.id,
            variant_id=variant.id,
            source_type="scene",
            source_id=scene.id,
            created_stage_id=stage.id,
        ))
        session.add(ControlledApplyOperation(
            project_id=project_id,
            source_type="rewrite_variant",
            source_id=variant.id,
            target_type="scene",
            target_id=scene.id,
            created_stage_id=stage.id,
        ))
        session.add(StoryLink(
            project_id=project_id,
            source_type="scene",
            source_id=str(scene.id),
            source_scene_id=scene.id,
            target_type="scene",
            target_id=str(scene.id),
            target_scene_id=scene.id,
        ))
        session.add(QuantumStateRecord(
            project_id=project_id,
            state_json=json.dumps({
                "project_id": project_id,
                "linked_scene_id": scene.id,
                "wavefunctions": [{
                    "source_scene_id": scene.id,
                    "target_scene_id": scene.id,
                }],
            }),
        ))
        session.commit()

    source_snapshot = build_project_cloud_snapshot(source, project_id)
    target = Database()
    for index in range(5):
        _story(target, f"Collider {index}")
    result = apply_project_cloud_snapshot(
        target, source_snapshot, mode="import", restore_id=str(uuid4()),
    )
    restored_snapshot = build_project_cloud_snapshot(target, result.project_id)
    assert restored_snapshot["digest"] == source_snapshot["digest"]

    restored_scene = target.get_all_scenes(result.project_id)[0]
    with Session(target._engine) as session:
        nodes = list(session.execute(
            select(OutlineNode).where(OutlineNode.project_id == result.project_id)
        ).scalars().all())
        by_title = {node.title: node for node in nodes}
        assert by_title["Opening node"].parent_id == by_title["Act I"].id
        assert by_title["Opening node"].scene_id == restored_scene.id
        summary = session.get(ChatSummary, result.project_id)
        message = session.get(ChatMessage, summary.last_summarized_message_id)
        assert message.content == "Remember this"
        quantum = session.get(QuantumStateRecord, result.project_id)
        state = json.loads(quantum.state_json)
        assert state["project_id"] == result.project_id
        assert state["linked_scene_id"] == restored_scene.id
        assert state["wavefunctions"][0]["source_scene_id"] == restored_scene.id


def test_older_restore_receipt_cannot_reapply_after_a_newer_restore() -> None:
    first_source = Database()
    first_id = _story(first_source, "First remote")
    first = build_project_cloud_snapshot(first_source, first_id)
    second_source = Database()
    second_id = _story(second_source, "Second remote")
    second = build_project_cloud_snapshot(second_source, second_id)

    target = Database()
    target_id = _story(target, "Local")
    local = build_project_cloud_snapshot(target, target_id)
    first_restore_id = str(uuid4())
    apply_project_cloud_snapshot(
        target,
        first,
        mode="replace",
        target_project_id=target_id,
        expected_current_digest=local["digest"],
        restore_id=first_restore_id,
    )
    after_first = build_project_cloud_snapshot(target, target_id)
    apply_project_cloud_snapshot(
        target,
        second,
        mode="replace",
        target_project_id=target_id,
        expected_current_digest=after_first["digest"],
        restore_id=str(uuid4()),
    )

    replay = apply_project_cloud_snapshot(
        target,
        first,
        mode="replace",
        target_project_id=target_id,
        expected_current_digest=local["digest"],
        restore_id=first_restore_id,
    )
    assert replay.project_id == target_id
    assert target.get_project_by_id(target_id).title == "Second remote"


def test_cloud_snapshot_api_maps_validation_conflict_and_missing_errors() -> None:
    db = Database()
    project_id = _story(db)
    client = TestClient(create_api(db=db))
    snapshot = client.get(
        f"/api/projects/{project_id}/cloud-sync/snapshot"
    ).json()

    assert client.get("/api/projects/9999/cloud-sync/snapshot").status_code == 404

    tampered = deepcopy(snapshot)
    tampered["project"]["title"] = "tampered"
    invalid = client.post(
        "/api/cloud-sync/projects/import",
        json={
            "snapshot": tampered,
            "mode": "import",
            "restore_id": str(uuid4()),
        },
    )
    assert invalid.status_code == 400

    unguarded = client.post(
        f"/api/projects/{project_id}/cloud-sync/restore",
        json={
            "snapshot": snapshot,
            "restore_id": str(uuid4()),
        },
    )
    assert unguarded.status_code == 400

    expected = snapshot["digest"]
    db.update_project(project_id, title="Changed after conflict review")
    stale = client.post(
        f"/api/projects/{project_id}/cloud-sync/restore",
        json={
            "snapshot": snapshot,
            "restore_id": str(uuid4()),
            "expected_current_digest": expected,
        },
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "cloud_sync_conflict"
