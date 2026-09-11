"""Voice facade DTO/OpenAPI contract stays aligned with VoiceRoomService."""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import threading
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient

from logosforge.api import create_api, schemas
from logosforge.api.routes import voice as voice_routes
from logosforge.db import Database
from logosforge.voice.billy_bridge import OP_ASK
from logosforge.voice.intent_router import I_CLEANUP, I_INSERT_CLEANED
from logosforge.voice.service import VoiceRoomService
from logosforge.voice.transcriber import MockTranscriber


def _service() -> VoiceRoomService:
    db = Database()
    project = db.create_project("Voice contract", narrative_engine="novel")
    return VoiceRoomService(
        db,
        project.id,
        writing_mode="novel",
        transcriber=MockTranscriber(),
        ai_complete=lambda _prompt: "Billy response",
    )


def test_voice_service_outputs_validate_against_public_dtos() -> None:
    service = _service()

    entry = service.transcribe_segment(b"\x00\x00" * 160)
    assert entry is not None
    schemas.VoiceHistoryEntryDTO.model_validate(entry)
    schemas.VoiceHistoryDTO.model_validate({"entries": service.history()})
    schemas.VoiceIntentsDTO.model_validate({"intents": service.list_intents({})})

    preview = service.preview_intent(I_INSERT_CLEANED, "hello comma world", {})
    schemas.VoiceIntentPreviewDTO.model_validate(preview)
    schemas.VoiceApplyResultDTO.model_validate(service.apply_intent(preview["id"], {}))

    schemas.VoiceBillyOpsDTO.model_validate({"operations": service.billy_operations({})})
    proposal = service.generate_billy(OP_ASK, "What changes here?", {})
    schemas.VoiceBillyProposalDTO.model_validate(proposal)
    schemas.VoiceApplyResultDTO.model_validate(service.apply_billy(proposal["id"], {}))

    targets = service.commit_targets({})
    schemas.VoiceCommitTargetsDTO.model_validate({"targets": targets})
    schemas.VoiceApplyResultDTO.model_validate(service.commit("Draft", targets[0]["id"], {}))
    schemas.VoiceUndoStateDTO.model_validate(service.can_undo())
    schemas.VoiceUndoResultDTO.model_validate(service.undo_last())


def test_voice_service_keeps_history_canonical_across_http_panel_remounts() -> None:
    service = _service()
    first = service.transcribe_segment(b"\x00\x00" * 160)
    assert first is not None

    preview = service.preview_intent(
        I_CLEANUP,
        "hello comma world",
        {},
        source_segment_ids=[first["id"]],
    )
    applied = service.apply_intent(preview["id"], {})
    assert applied["applied"] is True
    assert service.history()[0]["text"] == applied["cleaned_text"]

    proposal = service.generate_billy(
        OP_ASK,
        "What changes here?",
        {},
        source_segment_ids=[first["id"]],
    )
    assert service.history()[0]["billy_state"] == "proposed"
    cancelled = service.cancel_billy(proposal["id"])
    assert cancelled["cancelled"] is True
    assert service.history()[0]["billy_state"] == "cancelled"

    target = service.commit_targets({})[0]
    committed = service.commit(
        service.history()[0]["text"],
        target["id"],
        {},
        source_segment_ids=[first["id"]],
    )
    assert committed["applied"] is True
    assert service.history()[0]["status"] == "committed"
    assert service.history()[0]["committed_target"] == target["id"]


def test_every_voice_facade_operation_has_an_openapi_success_schema() -> None:
    app = create_api(db=Database())
    paths = app.openapi()["paths"]
    operations = {
        "post": [
            "/api/projects/{project_id}/voice/transcribe-segment",
            "/api/projects/{project_id}/voice/intents",
            "/api/projects/{project_id}/voice/intents/preview",
            "/api/projects/{project_id}/voice/intents/apply",
            "/api/projects/{project_id}/voice/intents/cancel",
            "/api/projects/{project_id}/voice/billy/operations",
            "/api/projects/{project_id}/voice/billy/generate",
            "/api/projects/{project_id}/voice/billy/apply",
            "/api/projects/{project_id}/voice/billy/cancel",
            "/api/projects/{project_id}/voice/commit-targets",
            "/api/projects/{project_id}/voice/commit",
            "/api/projects/{project_id}/voice/undo",
        ],
        "get": [
            "/api/projects/{project_id}/voice/history",
            "/api/projects/{project_id}/voice/can-undo",
        ],
    }
    for method, route_paths in operations.items():
        for route_path in route_paths:
            response = paths[route_path][method]["responses"]["200"]
            schema = response["content"]["application/json"].get("schema")
            assert schema, f"missing response schema: {method.upper()} {route_path}"


def test_voice_facade_runtime_responses_pass_fastapi_validation(monkeypatch) -> None:
    db = Database()
    project = db.create_project("Voice HTTP contract", narrative_engine="novel")
    service = VoiceRoomService(
        db,
        project.id,
        transcriber=MockTranscriber(),
        ai_complete=lambda _prompt: "Billy response",
    )
    monkeypatch.setitem(voice_routes._SESSIONS, project.id, service)
    client = TestClient(create_api(db=db))
    root = f"/api/projects/{project.id}/voice"

    invalid = client.post(root + "/transcribe-segment", json={"audio_base64": "a"})
    assert invalid.status_code == 200
    assert invalid.json() == {"error": "invalid audio payload"}
    empty = client.post(root + "/transcribe-segment", json={"audio_base64": ""})
    assert empty.status_code == 200
    assert empty.json() == {"empty": True}

    segment = client.post(
        root + "/transcribe-segment",
        json={"audio_base64": base64.b64encode(b"\x00\x00" * 160).decode("ascii")},
    )
    assert segment.status_code == 200
    assert segment.json()["session_id"]
    assert client.get(root + "/history").status_code == 200
    assert client.post(root + "/intents", json={"ctx": {}}).status_code == 200

    preview = client.post(
        root + "/intents/preview",
        json={"intent_id": I_INSERT_CLEANED, "source_text": "hello comma world", "ctx": {}},
    )
    assert preview.status_code == 200
    assert client.post(
        root + "/intents/apply",
        json={"preview_id": preview.json()["id"], "ctx": {}},
    ).status_code == 200
    cancelled_preview = client.post(
        root + "/intents/preview",
        json={"intent_id": I_INSERT_CLEANED, "source_text": "cancel me", "ctx": {}},
    )
    cancelled_intent = client.post(
        root + "/intents/cancel",
        json={"preview_id": cancelled_preview.json()["id"]},
    )
    assert cancelled_intent.status_code == 200
    assert cancelled_intent.json()["cancelled"] is True

    assert client.post(root + "/billy/operations", json={"ctx": {}}).status_code == 200
    proposal = client.post(
        root + "/billy/generate",
        json={"operation": OP_ASK, "transcript_text": "What changes here?", "ctx": {}},
    )
    assert proposal.status_code == 200
    assert client.post(
        root + "/billy/apply",
        json={"proposal_id": proposal.json()["id"], "ctx": {}},
    ).status_code == 200
    cancelled_proposal = client.post(
        root + "/billy/generate",
        json={"operation": OP_ASK, "transcript_text": "Cancel this", "ctx": {}},
    )
    cancelled_billy = client.post(
        root + "/billy/cancel",
        json={"proposal_id": cancelled_proposal.json()["id"]},
    )
    assert cancelled_billy.status_code == 200
    assert cancelled_billy.json()["cancelled"] is True

    targets = client.post(root + "/commit-targets", json={"ctx": {}})
    assert targets.status_code == 200 and targets.json()["targets"]
    assert client.post(
        root + "/commit",
        json={
            "text": "Draft",
            "target_id": targets.json()["targets"][0]["id"],
            "source_segment_ids": [segment.json()["id"]],
            "ctx": {},
        },
    ).status_code == 200
    assert client.get(root + "/can-undo").status_code == 200
    assert client.post(root + "/undo").status_code == 200


def test_voice_session_operations_are_serialized_per_project(monkeypatch) -> None:
    db = object()
    project = SimpleNamespace(id=7101, narrative_engine="novel")
    state_lock = threading.Lock()
    active = 0
    maximum = 0

    class SlowService:
        _db = db

        def set_project(self, _project_id, *, writing_mode):
            assert writing_mode == "novel"

        def operation(self, value):
            nonlocal active, maximum
            with state_lock:
                active += 1
                maximum = max(maximum, active)
            time.sleep(0.025)
            with state_lock:
                active -= 1
            return value

    monkeypatch.setattr(voice_routes, "_SESSIONS", {project.id: SlowService()})
    monkeypatch.setattr(voice_routes, "_SESSION_LOCKS", {})
    start = threading.Barrier(5)

    def invoke(value):
        start.wait(timeout=2)
        return voice_routes._call_session(db, project, "operation", value)

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(invoke, range(5)))

    assert results == list(range(5))
    assert maximum == 1


def test_voice_session_replacement_keeps_the_project_lock(monkeypatch) -> None:
    db_a = Database()
    db_b = Database()
    project_a = db_a.create_project("Voice A", narrative_engine="novel")
    project_b = db_b.create_project("Voice B", narrative_engine="novel")
    assert project_a.id == project_b.id
    monkeypatch.setattr(voice_routes, "_SESSIONS", {})
    monkeypatch.setattr(voice_routes, "_SESSION_LOCKS", {})
    monkeypatch.setattr(voice_routes, "_get_transcriber", lambda: MockTranscriber())

    service_a = voice_routes._session(db_a, project_a)
    project_lock = voice_routes._SESSION_LOCKS[project_a.id]
    service_b = voice_routes._session(db_b, project_b)

    assert service_b is not service_a
    assert service_b._db is db_b
    assert voice_routes._SESSION_LOCKS[project_b.id] is project_lock
