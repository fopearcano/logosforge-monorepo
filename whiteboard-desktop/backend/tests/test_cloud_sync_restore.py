"""Lossless, copy-on-write Whiteboard cloud snapshot restore."""

from __future__ import annotations

import asyncio
import copy
import sys
from pathlib import Path

import httpx
from fastapi import FastAPI

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.core_client import CoreClient
from app.local_state import (
    CloudRestorePreparedValidators,
    CloudRestoreReceiptStore,
    CommentsStore,
    DrafterPagesStore,
    OutlineItemsStore,
    PsykeRevisionStore,
    WhiteboardStore,
)
from app.routers import cloud_sync
from app.routers import documents as documents_router
from app.routers import export as export_router


class _Response:
    def __init__(self, value):
        self._value = value

    def json(self):
        return self._value


class _Core:
    def __init__(self) -> None:
        self.deleted: list[int] = []
        self.calls: list[tuple[str, str, dict]] = []
        self._entry_id = 100
        self._track_id = 200
        self._beat_id = 300
        self._revision_digit = 0
        self._project_id = 40
        self.projects: dict[int, dict] = {}

    async def create_project(self, title: str):
        self._project_id += 1
        project = {
            "id": self._project_id,
            "title": title,
            "description": "",
        }
        self.projects[self._project_id] = project
        return project

    async def delete_project(self, project_id: int) -> None:
        self.deleted.append(project_id)
        self.projects.pop(project_id, None)

    async def request(self, method: str, path: str, **kwargs):
        self.calls.append((method, path, kwargs))
        if method == "POST" and path == "/api/projects":
            self._project_id += 1
            project = {
                "id": self._project_id,
                "title": kwargs["json"]["title"],
                "description": kwargs["json"].get("description", ""),
            }
            self.projects[self._project_id] = project
            return _Response(project)
        if method == "GET" and path == "/api/projects":
            return _Response(list(self.projects.values()))
        if (
            method == "GET"
            and path.startswith("/api/projects/")
            and path.count("/") == 3
        ):
            project_id = int(path.rsplit("/", 1)[1])
            if project_id not in self.projects:
                request = httpx.Request(method, f"http://test{path}")
                response = httpx.Response(404, request=request)
                raise httpx.HTTPStatusError(
                    "not found", request=request, response=response
                )
            return _Response(self.projects[project_id])
        if method == "POST" and path.endswith("/psyke/entries"):
            self._entry_id += 1
            return _Response({"id": self._entry_id, **kwargs["json"]})
        if method == "GET" and (
            path.endswith(
                (
                    "/psyke/entries",
                    "/psyke/relations",
                    "/psyke/progressions",
                )
            )
        ):
            return _Response([])
        if method == "GET" and path.endswith("/progressions"):
            project_id = int(path.split("/")[3])
            return _Response({
                "project_id": project_id,
                "revision": "0" * 64,
                "tracks": [],
                "summary": {},
            })
        if method == "POST" and path.endswith("/progressions/commands"):
            self._revision_digit += 1
            revision = format(self._revision_digit % 16, "x") * 64
            body = kwargs["json"]
            result = {
                "progressions": {"revision": revision, "tracks": [], "summary": {}},
                "created_track_id": None,
                "created_beat_id": None,
            }
            if body["kind"] == "create_track":
                self._track_id += 1
                result["created_track_id"] = self._track_id
            else:
                self._beat_id += 1
                result["created_beat_id"] = self._beat_id
            return _Response(result)
        return _Response({"ok": True})


def _bundle() -> dict:
    return {
        "format": "logosforge-project-bundle",
        "version": "1.0",
        "exportedAt": "2026-11-17T10:00:00+00:00",
        "source": {"app": "logosforge-whiteboard"},
        "project": {
            "id": "7",
            "title": "Cloud novel",
            "mode": "novel",
            "settings": {"fontFamily": "Georgia"},
            "manuscript": {
                "blocks": [{"id": "block-1", "type": "paragraph", "text": "Opening"}],
            },
            "outline": [{"id": "outline-1", "title": "Act I"}],
            "comments": [
                {
                    "id": "comment-1",
                    "anchor": {
                        "surface": "manuscript",
                        "block_index": 0,
                        "block_id": "block-1",
                        "from_offset": 0,
                        "to_offset": 7,
                    },
                    "quote": "Opening",
                    "body": "Keep this",
                    "resolved": False,
                    "replies": [
                        {
                            "id": "reply-1",
                            "body": "Agreed",
                            "author": "you",
                            "created_at": "2026-11-17T10:00:00+00:00",
                        }
                    ],
                    "created_at": "2026-11-17T10:00:00+00:00",
                    "updated_at": "2026-11-17T10:01:00+00:00",
                }
            ],
            "drafter": {
                "pages": [
                    {
                        "id": "draft-1",
                        "title": "Alternate opening",
                        "blocks": [{"id": "draft-block-1", "text": "Maybe this"}],
                        "created_at": "2026-11-17T10:00:00+00:00",
                        "updated_at": "2026-11-17T10:00:00+00:00",
                    }
                ]
            },
            "psyke": {
                "elements": [
                    {
                        "id": "10",
                        "name": "Ada",
                        "entry_type": "character",
                        "aliases": ["A"],
                        "description": "Protagonist",
                        "notes": "Curious",
                    },
                    {
                        "id": "20",
                        "name": "The Archive",
                        "entry_type": "place",
                        "aliases": [],
                        "description": "Hidden library",
                        "notes": "",
                    },
                ],
                "relations": [
                    {
                        "id": "10:20",
                        "source_id": 10,
                        "target_id": 20,
                        "source": "Ada",
                        "target": "The Archive",
                        "relation_type": "seeks",
                    }
                ],
                "progressions": [
                    {
                        "id": 70,
                        "entry_id": 10,
                        "text": "Ada learns to trust herself",
                        "scene_id": None,
                        "scene_title": "",
                        "sort_order": 0,
                    }
                ],
            },
            "progression_tracks": [
                {
                    "id": 50,
                    "kind": "character",
                    "title": "Ada",
                    "description": "",
                    "color_label": "",
                    "sort_order": 0,
                    "legacy_compatibility": True,
                    "primary_psyke_entry_id": 10,
                    "primary_psyke_entry_name": "Ada",
                    "primary_psyke_entry_type": "character",
                    "secondary_psyke_entry_id": None,
                    "secondary_psyke_entry_name": "",
                    "secondary_psyke_entry_type": "",
                    "beats": [
                        {
                            "id": 60,
                            "track_id": 50,
                            "text": "Ada learns to trust herself",
                            "sort_order": 0,
                            "anchor_kind": "unanchored",
                            "scene_id": None,
                            "scene_title": "",
                            "anchor_ref": None,
                            "anchor_label": "",
                        }
                    ],
                },
                {
                    "id": 51,
                    "kind": "relationship",
                    "title": "Ada and the Archive",
                    "description": "A dangerous attraction",
                    "color_label": "violet",
                    "sort_order": 1,
                    "legacy_compatibility": False,
                    "primary_psyke_entry_id": 10,
                    "primary_psyke_entry_name": "Ada",
                    "primary_psyke_entry_type": "character",
                    "secondary_psyke_entry_id": 20,
                    "secondary_psyke_entry_name": "The Archive",
                    "secondary_psyke_entry_type": "place",
                    "beats": [
                        {
                            "id": 61,
                            "track_id": 51,
                            "text": "Ada opens the sealed door",
                            "sort_order": 0,
                            "anchor_kind": "document_block",
                            "scene_id": None,
                            "scene_title": "",
                            "anchor_ref": "block-1",
                            "anchor_label": "Opening",
                        }
                    ],
                },
            ],
        },
    }


def _install_stores(monkeypatch, tmp_path: Path):
    stores = {
        "whiteboard_store": WhiteboardStore(tmp_path),
        "outline_items_store": OutlineItemsStore(tmp_path),
        "drafter_pages_store": DrafterPagesStore(tmp_path),
        "comments_store": CommentsStore(tmp_path),
        "psyke_revision_store": PsykeRevisionStore(tmp_path),
        "cloud_restore_receipt_store": CloudRestoreReceiptStore(tmp_path),
    }
    for name, store in stores.items():
        if hasattr(cloud_sync, name):
            monkeypatch.setattr(cloud_sync, name, store)
        if hasattr(documents_router, name):
            monkeypatch.setattr(documents_router, name, store)
        if hasattr(export_router, name):
            monkeypatch.setattr(export_router, name, store)
    documents_router._pending_local_cleanup.clear()
    return stores


async def _post(app: FastAPI, body: dict):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.post("/api/cloud-sync/restore", json=body)


async def _retire(
    app: FastAPI,
    document_id: str,
    incarnation: str,
    expected_bundle: dict,
    *,
    expected_digest: str | None = None,
):
    bundle_model = cloud_sync.CloudProjectBundle.model_validate(expected_bundle)
    digest = expected_digest or cloud_sync._canonical_cloud_digest(bundle_model)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.post(
            f"/api/cloud-sync/retire/{document_id}",
            headers={
                "X-LogosForge-Document-Incarnation": incarnation,
            },
            json={
                "expected_digest": digest,
                "expected_bundle": expected_bundle,
            },
        )


def _bundle_without_core_graph() -> dict:
    bundle = _bundle()
    bundle["project"]["psyke"] = {
        "elements": [],
        "relations": [],
        "progressions": [],
    }
    bundle["project"]["progression_tracks"] = []
    return bundle


def test_complete_snapshot_restores_copy_on_write_with_id_remapping(
    monkeypatch, tmp_path
):
    stores = _install_stores(monkeypatch, tmp_path)
    core = _Core()
    app = FastAPI()
    app.state.core = core
    app.include_router(cloud_sync.router)

    response = asyncio.run(
        _post(
            app,
            {
                "bundle": _bundle(),
                "restore_id": "cloud-project-1:snapshot-1",
            },
        )
    )

    assert response.status_code == 201, response.text
    result = response.json()
    assert result["idempotent"] is False
    assert result["source_project_id"] == "7"
    assert result["document"]["id"] == "41"
    assert stores["whiteboard_store"].get("41").blocks[0].text == "Opening"
    assert stores["whiteboard_store"].get("41").settings == {"fontFamily": "Georgia"}
    assert stores["outline_items_store"].get("41") == [
        {"id": "outline-1", "title": "Act I"}
    ]
    assert (
        stores["drafter_pages_store"].get_document("41").pages[0].title
        == "Alternate opening"
    )
    assert stores["comments_store"].get("41").comments[0].replies[0].body == "Agreed"
    assert core.deleted == []

    payloads = [call[2].get("json") for call in core.calls]
    relation = next(
        payload
        for payload in payloads
        if payload and payload.get("relation_type") == "seeks"
    )
    assert relation["source_id"] == 101
    assert relation["target_id"] == 102
    legacy = next(
        payload
        for payload in payloads
        if payload and payload.get("text") == "Ada learns to trust herself"
    )
    assert legacy["entry_id"] == 101
    track = next(
        payload
        for payload in payloads
        if payload and payload.get("kind") == "create_track"
    )
    assert track["primary_psyke_entry_id"] == 101
    assert track["secondary_psyke_entry_id"] == 102
    beat = next(
        payload
        for payload in payloads
        if payload and payload.get("kind") == "create_beat"
    )
    assert beat["track_id"] == 201
    assert beat["anchor_ref"] == "block-1"


def test_retirement_atomically_deletes_only_the_exact_complete_project(
    monkeypatch, tmp_path
):
    stores = _install_stores(monkeypatch, tmp_path)
    core = _Core()
    app = FastAPI()
    app.state.core = core
    app.include_router(cloud_sync.router)
    bundle = _bundle_without_core_graph()

    restored = asyncio.run(
        _post(app, {"bundle": bundle, "restore_id": "retire:exact"})
    )
    document = restored.json()["document"]
    retired = asyncio.run(
        _retire(app, document["id"], document["incarnation"], bundle)
    )

    assert retired.status_code == 200, retired.text
    assert retired.json() == {
        "ok": True,
        "deleted": document["id"],
        "already_absent": False,
        "cleanup_pending": False,
    }
    assert core.deleted == [int(document["id"])]
    assert not stores["whiteboard_store"].exists(document["id"])
    assert document["id"] not in stores["outline_items_store"].list_document_ids()
    assert document["id"] not in stores["drafter_pages_store"].list_document_ids()
    assert document["id"] not in stores["comments_store"].list_document_ids()


def test_retirement_preserves_a_project_changed_after_the_expected_snapshot(
    monkeypatch, tmp_path
):
    stores = _install_stores(monkeypatch, tmp_path)
    core = _Core()
    app = FastAPI()
    app.state.core = core
    app.include_router(cloud_sync.router)
    bundle = _bundle_without_core_graph()
    restored = asyncio.run(
        _post(app, {"bundle": bundle, "restore_id": "retire:changed"})
    )
    document = restored.json()["document"]
    stores["outline_items_store"].replace_document(
        document["id"],
        [
            {"id": "outline-1", "title": "Act I"},
            {"id": "late-edit", "title": "Written after the pull"},
        ],
    )

    refused = asyncio.run(
        _retire(app, document["id"], document["incarnation"], bundle)
    )

    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "cloud_retire_content_changed"
    assert core.deleted == []
    assert int(document["id"]) in core.projects
    assert stores["whiteboard_store"].exists(document["id"])
    assert stores["outline_items_store"].get(document["id"])[1]["id"] == "late-edit"


def test_retirement_rejects_a_digest_that_does_not_name_the_expected_bundle(
    monkeypatch, tmp_path
):
    stores = _install_stores(monkeypatch, tmp_path)
    core = _Core()
    app = FastAPI()
    app.state.core = core
    app.include_router(cloud_sync.router)
    bundle = _bundle_without_core_graph()
    restored = asyncio.run(
        _post(app, {"bundle": bundle, "restore_id": "retire:bad-digest"})
    )
    document = restored.json()["document"]

    refused = asyncio.run(
        _retire(
            app,
            document["id"],
            document["incarnation"],
            bundle,
            expected_digest="f" * 64,
        )
    )

    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "cloud_retire_precondition_invalid"
    assert core.deleted == []
    assert stores["whiteboard_store"].exists(document["id"])


def test_retirement_is_idempotent_after_the_exact_incarnation_is_absent(
    monkeypatch, tmp_path
):
    _install_stores(monkeypatch, tmp_path)
    core = _Core()
    app = FastAPI()
    app.state.core = core
    app.include_router(cloud_sync.router)
    bundle = _bundle_without_core_graph()
    restored = asyncio.run(
        _post(app, {"bundle": bundle, "restore_id": "retire:idempotent"})
    )
    document = restored.json()["document"]

    first = asyncio.run(
        _retire(app, document["id"], document["incarnation"], bundle)
    )
    second = asyncio.run(
        _retire(app, document["id"], document["incarnation"], bundle)
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["already_absent"] is True
    assert core.deleted == [int(document["id"])]


def test_retirement_digest_converges_after_core_id_and_timestamp_remapping():
    source = _bundle()
    remapped = copy.deepcopy(source)
    remapped["exportedAt"] = "2027-01-01T00:00:00+00:00"
    remapped["project"]["id"] = "999"
    entries = remapped["project"]["psyke"]["elements"]
    entries[0].update({"id": "101", "created_at": "later", "updated_at": "later"})
    entries[1].update({"id": "202", "created_at": "later", "updated_at": "later"})
    relation = remapped["project"]["psyke"]["relations"][0]
    relation.update({"id": "101:202", "source_id": 101, "target_id": 202})
    legacy = remapped["project"]["psyke"]["progressions"][0]
    legacy.update({"id": 701, "entry_id": 101})
    tracks = remapped["project"]["progression_tracks"]
    tracks[0].update({"id": 501, "primary_psyke_entry_id": 101})
    tracks[0]["beats"][0].update({"id": 601, "track_id": 501})
    tracks[1].update({
        "id": 502,
        "primary_psyke_entry_id": 101,
        "secondary_psyke_entry_id": 202,
    })
    tracks[1]["beats"][0].update({"id": 602, "track_id": 502})

    source_digest = cloud_sync._canonical_cloud_digest(
        cloud_sync.CloudProjectBundle.model_validate(source)
    )
    remapped_digest = cloud_sync._canonical_cloud_digest(
        cloud_sync.CloudProjectBundle.model_validate(remapped)
    )

    assert remapped_digest == source_digest


def test_retirement_digest_matches_the_electron_stable_json_contract():
    bundle = _bundle_without_core_graph()
    bundle["project"]["title"] = "T"
    bundle["project"]["settings"] = {
        "whole": 1.0,
        "small": 0.000001,
        "tiny": 0.0000001,
        "huge": 1e21,
    }
    bundle["project"]["manuscript"] = {"blocks": []}
    bundle["project"]["outline"] = []
    bundle["project"]["comments"] = []
    bundle["project"]["drafter"] = {"pages": []}

    digest = cloud_sync._canonical_cloud_digest(
        cloud_sync.CloudProjectBundle.model_validate(bundle)
    )

    # Contract fixture produced by Electron's cloudSyncContentDigest.
    assert digest == "11180b3515203208ef42df34a172b427b7835d54ea7028df813ea96cf79b1899"


def test_failed_restore_removes_core_and_every_partial_local_store(
    monkeypatch, tmp_path
):
    stores = _install_stores(monkeypatch, tmp_path)
    core = _Core()
    app = FastAPI()
    app.state.core = core
    app.include_router(cloud_sync.router)

    def fail_comments(_doc_id, _comments):
        raise ValueError("simulated disk failure")

    monkeypatch.setattr(stores["comments_store"], "replace_document", fail_comments)
    response = asyncio.run(
        _post(
            app,
            {
                "bundle": _bundle(),
                "restore_id": "cloud-project-1:snapshot-failure",
            },
        )
    )

    assert response.status_code == 500
    assert core.deleted == [41]
    assert not stores["whiteboard_store"].exists("41")
    assert "41" not in stores["outline_items_store"].list_document_ids()
    assert "41" not in stores["drafter_pages_store"].list_document_ids()
    assert "41" not in stores["comments_store"].list_document_ids()


def test_invalid_cross_reference_is_rejected_before_core_allocation(
    monkeypatch, tmp_path
):
    _install_stores(monkeypatch, tmp_path)
    core = _Core()
    app = FastAPI()
    app.state.core = core
    app.include_router(cloud_sync.router)
    bundle = _bundle()
    bundle["project"]["psyke"]["relations"][0]["target_id"] = 999
    bundle["project"]["psyke"]["relations"][0]["id"] = "10:999"

    response = asyncio.run(
        _post(
            app,
            {
                "bundle": bundle,
                "restore_id": "cloud-project-1:snapshot-invalid",
            },
        )
    )

    assert response.status_code == 422
    assert core.projects == {}
    assert core.calls == []


def test_restore_contract_round_trips_through_the_real_core_api(monkeypatch, tmp_path):
    stores = _install_stores(monkeypatch, tmp_path / "local")
    monkeypatch.setenv("LOGOSFORGE_DB_PATH", str(tmp_path / "core.db"))

    async def exercise():
        core = CoreClient()
        try:
            app = FastAPI()
            app.state.core = core
            app.include_router(cloud_sync.router)
            response = await _post(
                app,
                {
                    "bundle": _bundle(),
                    "restore_id": "cloud-project-real:snapshot-1",
                },
            )
            assert response.status_code == 201, response.text
            doc_id = int(response.json()["document"]["id"])
            entries = (
                await core.request("GET", f"/api/projects/{doc_id}/psyke/entries")
            ).json()
            relations = (
                await core.request("GET", f"/api/projects/{doc_id}/psyke/relations")
            ).json()
            legacy = (
                await core.request("GET", f"/api/projects/{doc_id}/psyke/progressions")
            ).json()
            progressions = (
                await core.request("GET", f"/api/projects/{doc_id}/progressions")
            ).json()
            return doc_id, entries, relations, legacy, progressions
        finally:
            await core.aclose()

    doc_id, entries, relations, legacy, progressions = asyncio.run(exercise())
    assert [entry["name"] for entry in entries] == ["Ada", "The Archive"]
    assert relations[0]["relation_type"] == "seeks"
    assert legacy[0]["text"] == "Ada learns to trust herself"
    assert [track["legacy_compatibility"] for track in progressions["tracks"]] == [
        True,
        False,
    ]
    assert progressions["tracks"][1]["beats"][0]["anchor_ref"] == "block-1"
    assert stores["whiteboard_store"].get(str(doc_id)).title == "Cloud novel"


def test_exact_retry_uses_durable_receipt_without_creating_a_duplicate(
    monkeypatch, tmp_path
):
    stores = _install_stores(monkeypatch, tmp_path)
    core = _Core()
    app = FastAPI()
    app.state.core = core
    app.include_router(cloud_sync.router)
    body = {"bundle": _bundle(), "restore_id": "project-a:snapshot-a"}

    first = asyncio.run(_post(app, body))
    # Re-open the receipt file through a fresh store instance, as a backend
    # restart would, before replaying the same renderer request.
    reopened = CloudRestoreReceiptStore(tmp_path)
    monkeypatch.setattr(cloud_sync, "cloud_restore_receipt_store", reopened)
    second = asyncio.run(_post(app, body))

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["idempotent"] is True
    assert second.json()["document"]["id"] == first.json()["document"]["id"]
    allocations = [
        call for call in core.calls if call[0:2] == ("POST", "/api/projects")
    ]
    assert len(allocations) == 1
    assert reopened.get_receipt(body["restore_id"]) is not None
    assert stores["whiteboard_store"].list_document_ids() == {"41"}


def test_retry_refuses_to_return_a_restored_document_after_any_edit(
    monkeypatch, tmp_path
):
    stores = _install_stores(monkeypatch, tmp_path)
    core = _Core()
    app = FastAPI()
    app.state.core = core
    app.include_router(cloud_sync.router)
    body = {"bundle": _bundle(), "restore_id": "project-b:snapshot-b"}

    first = asyncio.run(_post(app, body))
    assert first.status_code == 201
    stores["outline_items_store"].replace_document(
        "41", [{"id": "outline-2", "title": "Edited after restore"}]
    )
    second = asyncio.run(_post(app, body))

    assert second.status_code == 409
    detail = second.json()["detail"]
    assert detail["code"] == "cloud_restore_retry_stale"
    assert detail["document_id"] == first.json()["document"]["id"] == "41"
    assert detail["incarnation"] == first.json()["document"]["incarnation"]
    assert set(detail) == {"code", "message", "document_id", "incarnation"}
    allocations = [
        call for call in core.calls if call[0:2] == ("POST", "/api/projects")
    ]
    assert len(allocations) == 1
    assert stores["whiteboard_store"].list_document_ids() == {"41"}
    assert stores["outline_items_store"].get("41") == [
        {"id": "outline-2", "title": "Edited after restore"}
    ]
    assert 41 in core.projects


def test_deleted_receipt_identity_is_rebuilt_under_a_fresh_document(
    monkeypatch, tmp_path
):
    stores = _install_stores(monkeypatch, tmp_path)
    core = _Core()
    app = FastAPI()
    app.state.core = core
    app.include_router(cloud_sync.router)
    body = {"bundle": _bundle(), "restore_id": "project-c:snapshot-c"}

    first = asyncio.run(_post(app, body))
    assert first.status_code == 201
    asyncio.run(core.delete_project(41))
    documents_router._cleanup_local_document_state("41")
    second = asyncio.run(_post(app, body))

    assert second.status_code == 201
    assert second.json()["idempotent"] is False
    assert second.json()["document"]["id"] == "42"
    assert stores["whiteboard_store"].list_document_ids() == {"42"}


def test_concurrent_duplicate_restore_ids_are_serialized(monkeypatch, tmp_path):
    _install_stores(monkeypatch, tmp_path)
    core = _Core()
    app = FastAPI()
    app.state.core = core
    app.include_router(cloud_sync.router)
    body = {"bundle": _bundle(), "restore_id": "project-d:snapshot-d"}

    async def concurrent():
        return await asyncio.gather(_post(app, body), _post(app, body))

    responses = asyncio.run(concurrent())

    assert sorted(response.status_code for response in responses) == [200, 201]
    assert {response.json()["document"]["id"] for response in responses} == {"41"}
    allocations = [
        call for call in core.calls if call[0:2] == ("POST", "/api/projects")
    ]
    assert len(allocations) == 1


def test_prepared_intent_recovers_crash_after_manuscript_publication(
    monkeypatch, tmp_path
):
    stores = _install_stores(monkeypatch, tmp_path)
    core = _Core()
    app = FastAPI()
    app.state.core = core
    app.include_router(cloud_sync.router)
    body = {"bundle": _bundle(), "restore_id": "project-e:snapshot-e"}

    first = asyncio.run(_post(app, body))
    assert first.status_code == 201
    receipt_store = stores["cloud_restore_receipt_store"]
    receipt = receipt_store.get_receipt(body["restore_id"])
    assert receipt is not None
    receipt_store.discard_receipt(body["restore_id"])
    pending = receipt_store.begin(
        receipt.restore_id,
        receipt.request_digest,
        receipt.document_id,
        receipt.source_project_id,
    )
    assert pending.prepared is None
    prepared = CloudRestorePreparedValidators(
        **receipt.validators.model_dump(exclude={"whiteboard_revision"})
    )
    receipt_store.mark_prepared(receipt.restore_id, receipt.request_digest, prepared)

    recovered = asyncio.run(_post(app, body))

    assert recovered.status_code == 200
    assert recovered.json()["idempotent"] is True
    assert receipt_store.get_pending(body["restore_id"]) is None
    assert receipt_store.get_receipt(body["restore_id"]) is not None


def test_edited_prepared_intent_returns_the_preserved_identity(
    monkeypatch, tmp_path
):
    stores = _install_stores(monkeypatch, tmp_path)
    core = _Core()
    app = FastAPI()
    app.state.core = core
    app.include_router(cloud_sync.router)
    body = {"bundle": _bundle(), "restore_id": "project-pending:snapshot"}

    first = asyncio.run(_post(app, body))
    assert first.status_code == 201
    receipt_store = stores["cloud_restore_receipt_store"]
    receipt = receipt_store.get_receipt(body["restore_id"])
    assert receipt is not None
    receipt_store.discard_receipt(body["restore_id"])
    receipt_store.begin(
        receipt.restore_id,
        receipt.request_digest,
        receipt.document_id,
        receipt.source_project_id,
    )
    prepared = CloudRestorePreparedValidators(
        **receipt.validators.model_dump(exclude={"whiteboard_revision"})
    )
    receipt_store.mark_prepared(receipt.restore_id, receipt.request_digest, prepared)
    stores["outline_items_store"].replace_document(
        receipt.document_id,
        [{"id": "pending-edit", "title": "Preserve this"}],
    )

    refused = asyncio.run(_post(app, body))

    assert refused.status_code == 409
    detail = refused.json()["detail"]
    assert detail["code"] == "cloud_restore_retry_stale"
    assert detail["document_id"] == receipt.document_id
    assert detail["incarnation"] == receipt.incarnation
    assert set(detail) == {"code", "message", "document_id", "incarnation"}
    assert stores["outline_items_store"].get(receipt.document_id) == [
        {"id": "pending-edit", "title": "Preserve this"}
    ]
    assert int(receipt.document_id) in core.projects
    assert receipt_store.get_pending(body["restore_id"]) is not None
    assert receipt_store.get_receipt(body["restore_id"]) is None


def test_restore_id_cannot_be_reused_for_different_snapshot_bytes(
    monkeypatch, tmp_path
):
    _install_stores(monkeypatch, tmp_path)
    core = _Core()
    app = FastAPI()
    app.state.core = core
    app.include_router(cloud_sync.router)
    first_body = {"bundle": _bundle(), "restore_id": "project-f:snapshot-f"}
    second_bundle = _bundle()
    second_bundle["project"]["manuscript"]["blocks"][0]["text"] = "Different"

    first = asyncio.run(_post(app, first_body))
    conflict = asyncio.run(
        _post(app, {"bundle": second_bundle, "restore_id": first_body["restore_id"]})
    )

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "cloud_restore_id_conflict"
    allocations = [
        call for call in core.calls if call[0:2] == ("POST", "/api/projects")
    ]
    assert len(allocations) == 1
