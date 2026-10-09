"""Focused Whiteboard adapter tests for canonical Progressions."""
from __future__ import annotations

import os
import sys
import tempfile
import asyncio
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))
_TMP = Path(tempfile.mkdtemp(prefix="lf-progressions-test-"))
os.environ["LOGOSFORGE_DATA_DIR"] = str(_TMP)
os.environ["LOGOSFORGE_DB_PATH"] = str(_TMP / "whiteboard.db")

from app.main import app  # noqa: E402


def test_progressions_wrapper_crud_anchor_and_receipt() -> None:
    with TestClient(app) as client:
        document = client.post(
            "/api/documents", json={"title": "Progressions adapter test"}
        ).json()["document"]
        document_id = document["id"]
        incarnation = document["incarnation"]
        headers = {"X-LogosForge-Document-Incarnation": incarnation}

        entry_response = client.post(
            f"/api/psyke/elements?doc={document_id}",
            headers=headers,
            json={
                "type": "character",
                "name": "Mara",
                "description": "A reluctant captain",
                "notes": "",
            },
        )
        assert entry_response.status_code == 200
        entry_id = int(entry_response.json()["element"]["id"])

        initial = client.get(
            f"/api/progressions?doc={document_id}", headers=headers
        )
        assert initial.status_code == 200
        snapshot = initial.json()
        assert snapshot["project_id"] == int(document_id)
        assert snapshot["tracks"] == []

        track_key = "whiteboard-test-track-command-0001"
        track_command = {
            "kind": "create_track",
            "expected_revision": snapshot["revision"],
            "track_kind": "character",
            "title": "Mara accepts command",
            "primary_psyke_entry_id": entry_id,
        }
        created = client.post(
            f"/api/progressions/commands?doc={document_id}",
            headers={**headers, "Idempotency-Key": track_key},
            json=track_command,
        )
        assert created.status_code == 200, created.text
        result = created.json()
        track_id = result["created_track_id"]
        assert result["changed"] is True
        assert result["replayed"] is False
        assert result["progressions"]["tracks"][0]["primary_psyke_entry_id"] == entry_id

        replay = client.post(
            f"/api/progressions/commands?doc={document_id}",
            headers={**headers, "Idempotency-Key": track_key},
            json=track_command,
        )
        assert replay.status_code == 200
        assert replay.json()["replayed"] is True
        assert replay.json()["created_track_id"] == track_id

        receipt = client.get(
            f"/api/progressions/command-receipt?doc={document_id}",
            headers={**headers, "Idempotency-Key": track_key},
        )
        assert receipt.status_code == 200
        assert receipt.headers["cache-control"] == "no-store"
        assert receipt.json()["original_created_track_id"] == track_id

        beat = client.post(
            f"/api/progressions/commands?doc={document_id}",
            headers={
                **headers,
                "Idempotency-Key": "whiteboard-test-beat-command-0001",
            },
            json={
                "kind": "create_beat",
                "expected_revision": result["progressions"]["revision"],
                "track_id": track_id,
                "text": "Mara answers the distress call.",
                "anchor_kind": "document_block",
                "anchor_ref": "block-stable-01",
                "anchor_label": "Chapter 3 — The Call",
            },
        )
        assert beat.status_code == 200, beat.text
        stored = beat.json()["progressions"]["tracks"][0]["beats"][0]
        assert stored["anchor_kind"] == "document_block"
        assert stored["anchor_ref"] == "block-stable-01"
        assert stored["scene_id"] is None


def test_progressions_wrapper_rejects_missing_document_identity() -> None:
    with TestClient(app) as client:
        document = client.post(
            "/api/documents", json={"title": "Progressions identity test"}
        ).json()["document"]
        document_id = document["id"]
        snapshot = client.get(f"/api/progressions?doc={document_id}").json()
        response = client.post(
            f"/api/progressions/commands?doc={document_id}",
            headers={"Idempotency-Key": "whiteboard-test-missing-identity-0001"},
            json={
                "kind": "create_track",
                "expected_revision": snapshot["revision"],
                "track_kind": "story",
                "title": "Global story arc",
            },
        )
        assert response.status_code == 428


def test_progressions_ai_context_is_bounded_and_relevance_first() -> None:
    from app.routers.littleboy import (
        LOGOS_NEARBY_MAX_CHARS,
        PROGRESSIONS_CONTEXT_MAX_CHARS,
        _logos_nearby_context,
        _progressions_context,
    )

    tracks = []
    for index in range(12):
        name = "Mara" if index == 9 else f"Person {index}"
        tracks.append({
            "id": index + 1,
            "sort_order": index,
            "kind": "character",
            "title": f"{name} arc",
            "description": "",
            "primary_psyke_entry_name": name,
            "secondary_psyke_entry_name": "",
            "beats": [{
                "text": f"{name} chooses a new path " + ("x" * 240),
                "anchor_label": f"Chapter {index + 1}",
            }],
        })

    class FakeCore:
        async def request(self, method: str, path: str):
            assert method == "GET" and path.endswith("/progressions")
            return SimpleNamespace(json=lambda: {"tracks": tracks})

    context = asyncio.run(_progressions_context(FakeCore(), 7, "Help with Mara"))
    assert len(context) <= PROGRESSIONS_CONTEXT_MAX_CHARS
    assert context.index("Mara arc") < context.index("Person 0 arc")
    logos = _logos_nearby_context(7, "cursor paragraph", "", context)
    assert len(logos) <= LOGOS_NEARBY_MAX_CHARS
    assert "Canonical Progressions" in logos
