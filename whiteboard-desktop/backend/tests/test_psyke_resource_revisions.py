from __future__ import annotations

import asyncio
import copy
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException, Response
from starlette.datastructures import Headers

import app.document_lifecycle as lifecycle
from app.routers import documents as documents_router
from app.local_state import PsykeRevisionStore, WhiteboardCreate, WhiteboardStore
from app.resource_revision import resource_etag
from app.routers import psyke as psyke_router


class _Core:
    def __init__(
        self,
        project_id: int,
        entries: list[dict] | None = None,
        *,
        relations: list[dict] | None = None,
        progressions: list[dict] | None = None,
    ) -> None:
        self.project_id = project_id
        self.entries = copy.deepcopy(entries or [])
        self.relations = copy.deepcopy(relations or [])
        self.progressions = copy.deepcopy(progressions or [])
        self.calls: list[tuple[str, str, dict | None]] = []
        self.next_id = max((int(entry["id"]) for entry in self.entries), default=0) + 1
        self.next_progression_id = (
            max(
                (int(progression["id"]) for progression in self.progressions),
                default=0,
            )
            + 1
        )

    async def ensure_project(self) -> int:
        return self.project_id

    async def ensure_project_with_status(self) -> tuple[int, bool]:
        return self.project_id, False

    async def request(self, method: str, path: str, **kwargs):
        payload = copy.deepcopy(kwargs.get("json"))
        self.calls.append((method, path, payload))
        project_path = f"/api/projects/{self.project_id}"
        entries_path = f"{project_path}/psyke/entries"
        relations_path = f"{project_path}/psyke/relations"
        progressions_path = f"{project_path}/psyke/progressions"
        if method == "GET" and path == project_path:
            return SimpleNamespace(json=lambda: {"id": self.project_id})
        if method == "GET" and path == entries_path:
            snapshot = copy.deepcopy(self.entries)
            return SimpleNamespace(json=lambda: snapshot)
        if method == "GET" and path == relations_path:
            snapshot = copy.deepcopy(self.relations)
            return SimpleNamespace(json=lambda: snapshot)
        if method == "GET" and path == progressions_path:
            snapshot = copy.deepcopy(self.progressions)
            return SimpleNamespace(json=lambda: snapshot)
        if method == "POST" and path == entries_path:
            entry = {"id": self.next_id, **(payload or {})}
            self.next_id += 1
            self.entries.append(entry)
            snapshot = copy.deepcopy(entry)
            return SimpleNamespace(json=lambda: snapshot)
        if method == "POST" and path == relations_path:
            source_id = int(payload["source_id"])
            target_id = int(payload["target_id"])
            source = next(entry for entry in self.entries if entry["id"] == source_id)
            target = next(entry for entry in self.entries if entry["id"] == target_id)
            relation = {
                "id": f"{source_id}:{target_id}",
                "source_id": source_id,
                "target_id": target_id,
                "source": source["name"],
                "target": target["name"],
                "relation_type": payload.get("relation_type", ""),
            }
            self.relations.append(relation)
            snapshot = copy.deepcopy(relation)
            return SimpleNamespace(json=lambda: snapshot)
        if method == "POST" and path == progressions_path:
            progression = {
                "id": self.next_progression_id,
                "entry_id": int(payload["entry_id"]),
                "text": payload["text"],
                "scene_id": payload.get("scene_id"),
                "scene_title": (
                    f'Scene {payload["scene_id"]}'
                    if payload.get("scene_id") is not None
                    else ""
                ),
                "sort_order": 1
                + max(
                    (
                        int(candidate.get("sort_order", 0))
                        for candidate in self.progressions
                        if candidate.get("entry_id") == payload["entry_id"]
                    ),
                    default=0,
                ),
            }
            self.next_progression_id += 1
            self.progressions.append(progression)
            snapshot = copy.deepcopy(progression)
            return SimpleNamespace(json=lambda: snapshot)
        prefix = entries_path + "/"
        if method == "PATCH" and path.startswith(prefix):
            element_id = int(path[len(prefix):])
            entry = next(
                (candidate for candidate in self.entries if int(candidate["id"]) == element_id),
                None,
            )
            if entry is None:
                request = httpx.Request(method, "http://logosforge-core" + path)
                response = httpx.Response(404, request=request)
                raise httpx.HTTPStatusError(
                    "missing", request=request, response=response
                )
            entry.update(payload or {})
            snapshot = copy.deepcopy(entry)
            return SimpleNamespace(json=lambda: snapshot)
        progression_prefix = progressions_path + "/"
        if method == "PATCH" and path.startswith(progression_prefix):
            progression_id = int(path[len(progression_prefix):])
            progression = next(
                (
                    candidate
                    for candidate in self.progressions
                    if int(candidate["id"]) == progression_id
                ),
                None,
            )
            if progression is None:
                request = httpx.Request(method, "http://logosforge-core" + path)
                response = httpx.Response(404, request=request)
                raise httpx.HTTPStatusError(
                    "missing", request=request, response=response
                )
            progression.update(payload or {})
            progression["scene_title"] = (
                f'Scene {progression["scene_id"]}'
                if progression.get("scene_id") is not None
                else ""
            )
            snapshot = copy.deepcopy(progression)
            return SimpleNamespace(json=lambda: snapshot)
        raise AssertionError(f"unexpected core request: {method} {path}")

    def write_count(self, method: str, resource: str = "entries") -> int:
        return sum(
            call_method == method and f"/psyke/{resource}" in path
            for call_method, path, _payload in self.calls
        )


def _request(
    core: _Core,
    incarnation: str | None,
    *,
    etag: str | None = None,
    mutation_id: str | None = None,
):
    headers: dict[str, str] = {}
    if incarnation is not None:
        headers["X-LogosForge-Document-Incarnation"] = incarnation
    if etag is not None:
        headers["If-Match"] = etag
    if mutation_id is not None:
        headers["X-LogosForge-Mutation-Id"] = mutation_id
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(core=core)),
        headers=Headers(headers),
    )


def _install(
    tmp_path: Path,
    monkeypatch,
    core: _Core,
) -> tuple[str, PsykeRevisionStore]:
    whiteboards = WhiteboardStore(tmp_path)
    document = whiteboards.create(
        str(core.project_id), WhiteboardCreate(title="PSYKE revisions")
    )
    revisions = PsykeRevisionStore(tmp_path)
    monkeypatch.setattr(lifecycle, "whiteboard_store", whiteboards)
    monkeypatch.setattr(psyke_router, "psyke_revision_store", revisions)
    return document.incarnation, revisions


def _entry(
    element_id: int,
    name: str,
    *,
    notes: str = "",
    details: dict | None = None,
) -> dict:
    return {
        "id": element_id,
        "name": name,
        "type": "character",
        "aliases": [f"{name} alias"],
        "notes": notes,
        "is_global": False,
        "details": copy.deepcopy(details or {}),
    }


def _relation(
    source_id: int,
    target_id: int,
    source: str,
    target: str,
    relation_type: str = "",
) -> dict:
    low, high = sorted((source_id, target_id))
    return {
        "id": f"{low}:{high}",
        "source_id": source_id,
        "target_id": target_id,
        "source": source,
        "target": target,
        "relation_type": relation_type,
    }


def _progression(
    progression_id: int,
    entry_id: int,
    text: str,
    *,
    scene_id: int | None = None,
    sort_order: int = 1,
) -> dict:
    return {
        "id": progression_id,
        "entry_id": entry_id,
        "text": text,
        "scene_id": scene_id,
        "scene_title": f"Scene {scene_id}" if scene_id is not None else "",
        "sort_order": sort_order,
    }


def _search(
    core: _Core,
    incarnation: str,
    *,
    query: str = "",
) -> tuple[dict, Response]:
    response = Response()
    result = asyncio.run(
        psyke_router.search(
            _request(core, incarnation),
            query,
            core.project_id,
            response,
        )
    )
    return result, response


def _relations_read(core: _Core, incarnation: str) -> tuple[dict, Response]:
    response = Response()
    result = asyncio.run(
        psyke_router.list_relations(
            _request(core, incarnation), core.project_id, response
        )
    )
    return result, response


def _progressions_read(core: _Core, incarnation: str) -> tuple[dict, Response]:
    response = Response()
    result = asyncio.run(
        psyke_router.list_progressions(
            _request(core, incarnation), core.project_id, response
        )
    )
    return result, response


def test_search_revision_is_stable_across_queries_and_order_but_rotates_on_change(
    tmp_path: Path,
    monkeypatch,
) -> None:
    core = _Core(
        930101,
        [
            _entry(2, "Bex", notes="navigator"),
            _entry(1, "Mara", notes="sonar technician"),
        ],
    )
    incarnation, _revisions = _install(tmp_path, monkeypatch, core)

    first, first_response = _search(core, incarnation, query="mara")
    core.entries.reverse()
    second, second_response = _search(core, incarnation, query="navigator")

    assert [entry["name"] for entry in first["results"]] == ["Mara"]
    assert [entry["name"] for entry in second["results"]] == ["Bex"]
    assert first["revision"] == second["revision"]
    expected = resource_etag("psyke", incarnation, first["revision"])
    assert first_response.headers["etag"] == expected
    assert second_response.headers["etag"] == expected

    core.entries[0]["notes"] = "changed outside Whiteboard"
    changed, changed_response = _search(core, incarnation)
    assert changed["revision"] != first["revision"]
    assert changed_response.headers["etag"] == resource_etag(
        "psyke", incarnation, changed["revision"]
    )

    # Returning the content to its original bytes still must not revive the
    # first opaque validator after the changed snapshot was observed.
    core.entries[0]["notes"] = "sonar technician"
    restored, _ = _search(core, incarnation)
    assert restored["revision"] not in {first["revision"], changed["revision"]}


def test_all_psyke_reads_share_aggregate_revision_and_each_collection_rotates_it(
    tmp_path: Path,
    monkeypatch,
) -> None:
    core = _Core(
        930111,
        [_entry(1, "Mara"), _entry(2, "Bex")],
        relations=[_relation(1, 2, "Mara", "Bex", "thematic_echo")],
        progressions=[_progression(7, 1, "Mara takes command")],
    )
    incarnation, _revisions = _install(tmp_path, monkeypatch, core)

    entries, entries_response = _search(core, incarnation, query="mara")
    relations, relations_response = _relations_read(core, incarnation)
    progressions, progressions_response = _progressions_read(core, incarnation)
    revision = entries["revision"]
    expected_etag = resource_etag("psyke", incarnation, revision)

    assert relations["revision"] == revision
    assert progressions["revision"] == revision
    assert entries_response.headers["etag"] == expected_etag
    assert relations_response.headers["etag"] == expected_etag
    assert progressions_response.headers["etag"] == expected_etag

    core.entries.reverse()
    core.relations.reverse()
    core.progressions.reverse()
    reordered, _ = _search(core, incarnation)
    assert reordered["revision"] == revision

    core.relations[0]["relation_type"] = "visual_motif"
    relation_changed, _ = _relations_read(core, incarnation)
    assert relation_changed["revision"] != revision

    core.progressions[0]["text"] = "Mara relinquishes command"
    progression_changed, _ = _progressions_read(core, incarnation)
    assert progression_changed["revision"] not in {
        revision,
        relation_changed["revision"],
    }


def test_legacy_explicit_writes_remain_compatible_and_publish_new_revision(
    tmp_path: Path,
    monkeypatch,
) -> None:
    core = _Core(
        930102,
        [_entry(1, "Mara", details={"description": "old", "private": {"age": 31}})],
    )
    incarnation, _revisions = _install(tmp_path, monkeypatch, core)
    initial, _ = _search(core, incarnation)

    create_response = Response()
    created = asyncio.run(
        psyke_router.create_element(
            _request(core, incarnation),
            psyke_router.PsykeElementCreate(name="Bex", description="navigator"),
            core.project_id,
            create_response,
        )
    )
    assert created["revision"] != initial["revision"]
    assert create_response.headers["etag"] == resource_etag(
        "psyke", incarnation, created["revision"]
    )

    update_response = Response()
    updated = asyncio.run(
        psyke_router.update_element(
            _request(core, incarnation),
            1,
            psyke_router.PsykeElementUpdate(description="new"),
            core.project_id,
            update_response,
        )
    )
    assert updated["element"]["description"] == "new"
    assert core.entries[0]["details"] == {
        "description": "new",
        "private": {"age": 31},
    }
    assert update_response.headers["etag"] == resource_etag(
        "psyke", incarnation, updated["revision"]
    )


def test_conditional_write_requires_complete_header_triplet_before_core_write(
    tmp_path: Path,
    monkeypatch,
) -> None:
    core = _Core(930103)
    incarnation, _revisions = _install(tmp_path, monkeypatch, core)
    loaded, response = _search(core, incarnation)
    etag = response.headers["etag"]

    with pytest.raises(HTTPException) as missing_mutation:
        asyncio.run(
            psyke_router.create_element(
                _request(core, incarnation, etag=etag),
                psyke_router.PsykeElementCreate(name="No mutation id"),
                core.project_id,
                Response(),
            )
        )
    assert missing_mutation.value.status_code == 428
    assert missing_mutation.value.detail["code"] == "mutation_id_required"

    with pytest.raises(HTTPException) as missing_etag:
        asyncio.run(
            psyke_router.create_element(
                _request(core, incarnation, mutation_id="psyke-create-1"),
                psyke_router.PsykeElementCreate(name="No ETag"),
                core.project_id,
                Response(),
            )
        )
    assert missing_etag.value.status_code == 428
    assert missing_etag.value.detail["code"] == "revision_precondition_required"

    with pytest.raises(HTTPException) as missing_incarnation:
        asyncio.run(
            psyke_router.create_element(
                _request(
                    core,
                    None,
                    etag=resource_etag("psyke", incarnation, loaded["revision"]),
                    mutation_id="psyke-create-2",
                ),
                psyke_router.PsykeElementCreate(name="No incarnation"),
                core.project_id,
                Response(),
            )
        )
    assert missing_incarnation.value.status_code == 428

    with pytest.raises(HTTPException) as malformed_etag:
        asyncio.run(
            psyke_router.create_element(
                _request(
                    core,
                    incarnation,
                    etag="not-a-strong-etag",
                    mutation_id="psyke-create-3",
                ),
                psyke_router.PsykeElementCreate(name="Bad ETag"),
                core.project_id,
                Response(),
            )
        )
    assert malformed_etag.value.status_code == 400
    assert malformed_etag.value.detail["code"] == "invalid_if_match"

    with pytest.raises(HTTPException) as malformed_mutation:
        asyncio.run(
            psyke_router.create_element(
                _request(
                    core,
                    incarnation,
                    etag=etag,
                    mutation_id="contains a space",
                ),
                psyke_router.PsykeElementCreate(name="Bad mutation id"),
                core.project_id,
                Response(),
            )
        )
    assert malformed_mutation.value.status_code == 400
    assert malformed_mutation.value.detail["code"] == "invalid_mutation_id"
    assert core.write_count("POST") == 0


def test_conditional_create_replays_exactly_after_store_restart_and_rejects_reuse(
    tmp_path: Path,
    monkeypatch,
) -> None:
    core = _Core(930104)
    incarnation, _revisions = _install(tmp_path, monkeypatch, core)
    loaded, response = _search(core, incarnation)
    etag = response.headers["etag"]
    headers = _request(
        core,
        incarnation,
        etag=etag,
        mutation_id="psyke-create-durable",
    )
    payload = psyke_router.PsykeElementCreate(
        name="Mara", description="sonar technician"
    )

    first_response = Response()
    first = asyncio.run(
        psyke_router.create_element(
            headers, payload, core.project_id, first_response
        )
    )
    monkeypatch.setattr(
        psyke_router, "psyke_revision_store", PsykeRevisionStore(tmp_path)
    )
    retry_response = Response()
    retry = asyncio.run(
        psyke_router.create_element(
            headers, payload, core.project_id, retry_response
        )
    )

    assert retry == first
    assert retry_response.headers["etag"] == first_response.headers["etag"]
    assert core.write_count("POST") == 1
    assert len(core.entries) == 1

    with pytest.raises(HTTPException) as reused:
        asyncio.run(
            psyke_router.create_element(
                headers,
                psyke_router.PsykeElementCreate(name="Different"),
                core.project_id,
                Response(),
            )
        )
    assert reused.value.status_code == 409
    assert reused.value.detail["code"] == "mutation_id_conflict"
    assert core.write_count("POST") == 1
    assert loaded["revision"] != first["revision"]

    with pytest.raises(HTTPException) as cross_operation:
        asyncio.run(
            psyke_router.update_element(
                headers,
                int(first["element"]["id"]),
                psyke_router.PsykeElementUpdate(notes="different operation"),
                core.project_id,
                Response(),
            )
        )
    assert cross_operation.value.status_code == 409
    assert cross_operation.value.detail["code"] == "mutation_id_conflict"
    assert core.write_count("PATCH") == 0

    core.entries[0]["notes"] = "changed by another LogosForge surface"
    with pytest.raises(HTTPException) as changed_after_commit:
        asyncio.run(
            psyke_router.create_element(
                headers, payload, core.project_id, Response()
            )
        )
    assert changed_after_commit.value.status_code == 409
    assert changed_after_commit.value.detail["code"] == "revision_conflict"
    assert core.write_count("POST") == 1


def test_conditional_patch_replays_once_and_preserves_non_whiteboard_details(
    tmp_path: Path,
    monkeypatch,
) -> None:
    core = _Core(
        930105,
        [_entry(7, "Mara", details={"description": "old", "private": ["keep"]})],
    )
    incarnation, _revisions = _install(tmp_path, monkeypatch, core)
    loaded, response = _search(core, incarnation)
    request = _request(
        core,
        incarnation,
        etag=response.headers["etag"],
        mutation_id="psyke-patch-durable",
    )
    patch = psyke_router.PsykeElementUpdate(name="Mara Vale", description="new")

    first = asyncio.run(
        psyke_router.update_element(
            request, 7, patch, core.project_id, Response()
        )
    )
    monkeypatch.setattr(
        psyke_router, "psyke_revision_store", PsykeRevisionStore(tmp_path)
    )
    retry = asyncio.run(
        psyke_router.update_element(
            request, 7, patch, core.project_id, Response()
        )
    )

    assert retry == first
    assert core.write_count("PATCH") == 1
    assert core.entries[0]["details"] == {
        "description": "new",
        "private": ["keep"],
    }
    assert first["revision"] != loaded["revision"]


def test_stale_or_wrong_resource_precondition_rejects_without_mutating_core(
    tmp_path: Path,
    monkeypatch,
) -> None:
    core = _Core(930106, [_entry(1, "Mara")])
    incarnation, _revisions = _install(tmp_path, monkeypatch, core)
    loaded, _ = _search(core, incarnation)

    wrong_etag = resource_etag("outline", incarnation, loaded["revision"])
    with pytest.raises(HTTPException) as wrong:
        asyncio.run(
            psyke_router.update_element(
                _request(
                    core,
                    incarnation,
                    etag=wrong_etag,
                    mutation_id="psyke-wrong-kind",
                ),
                1,
                psyke_router.PsykeElementUpdate(name="Wrong"),
                core.project_id,
                Response(),
            )
        )
    assert wrong.value.status_code == 409
    assert wrong.value.headers == {
        "ETag": resource_etag("psyke", incarnation, loaded["revision"])
    }

    stale_etag = resource_etag("psyke", incarnation, "0" * 32)
    with pytest.raises(HTTPException) as stale:
        asyncio.run(
            psyke_router.update_element(
                _request(
                    core,
                    incarnation,
                    etag=stale_etag,
                    mutation_id="psyke-stale",
                ),
                1,
                psyke_router.PsykeElementUpdate(name="Stale"),
                core.project_id,
                Response(),
            )
        )
    assert stale.value.status_code == 409
    assert stale.value.detail["code"] == "revision_conflict"
    assert core.write_count("PATCH") == 0


def test_core_commit_without_receipt_fails_retry_safely_instead_of_duplicating_create(
    tmp_path: Path,
    monkeypatch,
) -> None:
    core = _Core(930107)
    incarnation, revisions = _install(tmp_path, monkeypatch, core)
    _loaded, response = _search(core, incarnation)
    request = _request(
        core,
        incarnation,
        etag=response.headers["etag"],
        mutation_id="psyke-uncertain-create",
    )
    original_commit = revisions.commit_mutation

    def fail_commit(*_args, **_kwargs):
        raise RuntimeError("simulated receipt write failure")

    monkeypatch.setattr(revisions, "commit_mutation", fail_commit)
    with pytest.raises(RuntimeError, match="receipt write failure"):
        asyncio.run(
            psyke_router.create_element(
                request,
                psyke_router.PsykeElementCreate(name="Mara"),
                core.project_id,
                Response(),
            )
        )
    monkeypatch.setattr(revisions, "commit_mutation", original_commit)

    with pytest.raises(HTTPException) as retry:
        asyncio.run(
            psyke_router.create_element(
                request,
                psyke_router.PsykeElementCreate(name="Mara"),
                core.project_id,
                Response(),
            )
        )
    assert retry.value.status_code == 409
    assert retry.value.detail["code"] == "revision_conflict"
    assert core.write_count("POST") == 1
    assert [entry["name"] for entry in core.entries] == ["Mara"]


def test_failed_core_patch_does_not_advance_revision_or_install_retry_receipt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    core = _Core(930108, [_entry(1, "Mara")])
    incarnation, _revisions = _install(tmp_path, monkeypatch, core)
    loaded, response = _search(core, incarnation)
    original_request = core.request

    async def fail_patch(method: str, path: str, **kwargs):
        if method == "PATCH":
            request = httpx.Request(method, "http://logosforge-core" + path)
            failed = httpx.Response(503, request=request)
            raise httpx.HTTPStatusError(
                "core unavailable", request=request, response=failed
            )
        return await original_request(method, path, **kwargs)

    monkeypatch.setattr(core, "request", fail_patch)
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(
            psyke_router.update_element(
                _request(
                    core,
                    incarnation,
                    etag=response.headers["etag"],
                    mutation_id="psyke-failed-patch",
                ),
                1,
                psyke_router.PsykeElementUpdate(name="Not committed"),
                core.project_id,
                Response(),
            )
        )
    after, _ = _search(core, incarnation)
    assert after["revision"] == loaded["revision"]
    assert core.entries[0]["name"] == "Mara"


def test_noop_patch_never_reaches_core_and_remains_retry_safe_if_receipt_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    core = _Core(930110, [_entry(1, "Mara", notes="already current")])
    incarnation, revisions = _install(tmp_path, monkeypatch, core)
    loaded, response = _search(core, incarnation)
    request = _request(
        core,
        incarnation,
        etag=response.headers["etag"],
        mutation_id="psyke-noop-patch",
    )
    patch = psyke_router.PsykeElementUpdate(
        name="Mara", notes="already current"
    )
    original_commit = revisions.commit_mutation

    def fail_commit(*_args, **_kwargs):
        raise RuntimeError("simulated no-op receipt failure")

    monkeypatch.setattr(revisions, "commit_mutation", fail_commit)
    with pytest.raises(RuntimeError, match="no-op receipt failure"):
        asyncio.run(
            psyke_router.update_element(
                request, 1, patch, core.project_id, Response()
            )
        )
    assert core.write_count("PATCH") == 0

    monkeypatch.setattr(revisions, "commit_mutation", original_commit)
    first = asyncio.run(
        psyke_router.update_element(
            request, 1, patch, core.project_id, Response()
        )
    )
    retry = asyncio.run(
        psyke_router.update_element(
            request, 1, patch, core.project_id, Response()
        )
    )
    assert retry == first
    assert first["revision"] != loaded["revision"]
    assert core.write_count("PATCH") == 0


def test_relation_create_is_conditional_create_only_and_exact_retry_is_durable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    core = _Core(930112, [_entry(1, "Mara"), _entry(2, "Bex")])
    incarnation, _revisions = _install(tmp_path, monkeypatch, core)
    loaded, response = _search(core, incarnation)
    request = _request(
        core,
        incarnation,
        etag=response.headers["etag"],
        mutation_id="psyke-relation-durable",
    )
    body = psyke_router.PsykeRelationCreate(
        source_id=1,
        target_id=2,
        relation_type="  allied_by_oath  ",
    )

    first_response = Response()
    first = asyncio.run(
        psyke_router.create_relation(
            request, body, core.project_id, first_response
        )
    )
    monkeypatch.setattr(
        psyke_router, "psyke_revision_store", PsykeRevisionStore(tmp_path)
    )
    retry_response = Response()
    retry = asyncio.run(
        psyke_router.create_relation(
            request, body, core.project_id, retry_response
        )
    )

    assert retry == first
    assert first["revision"] != loaded["revision"]
    assert retry_response.headers["etag"] == first_response.headers["etag"]
    assert core.write_count("POST", "relations") == 1
    assert core.relations[0]["relation_type"] == "allied_by_oath"

    with pytest.raises(HTTPException) as cross_operation:
        asyncio.run(
            psyke_router.create_progression(
                request,
                psyke_router.PsykeProgressionCreate(
                    entry_id=1, text="Mara trusts Bex"
                ),
                core.project_id,
                Response(),
            )
        )
    assert cross_operation.value.status_code == 409
    assert cross_operation.value.detail["code"] == "mutation_id_conflict"
    assert core.write_count("POST", "progressions") == 0

    duplicate_request = _request(
        core,
        incarnation,
        etag=first_response.headers["etag"],
        mutation_id="psyke-relation-reversed",
    )
    with pytest.raises(HTTPException) as duplicate:
        asyncio.run(
            psyke_router.create_relation(
                duplicate_request,
                psyke_router.PsykeRelationCreate(
                    source_id=2, target_id=1, relation_type="different"
                ),
                core.project_id,
                Response(),
            )
        )
    assert duplicate.value.status_code == 409
    assert duplicate.value.detail["code"] == "psyke_relation_already_exists"
    assert core.write_count("POST", "relations") == 1


def test_new_psyke_mutations_require_complete_conditional_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    core = _Core(930113, [_entry(1, "Mara"), _entry(2, "Bex")])
    incarnation, _revisions = _install(tmp_path, monkeypatch, core)
    _loaded, response = _search(core, incarnation)

    with pytest.raises(HTTPException) as missing_mutation:
        asyncio.run(
            psyke_router.create_relation(
                _request(core, incarnation, etag=response.headers["etag"]),
                psyke_router.PsykeRelationCreate(source_id=1, target_id=2),
                core.project_id,
                Response(),
            )
        )
    assert missing_mutation.value.status_code == 428
    assert missing_mutation.value.detail["code"] == "mutation_id_required"

    with pytest.raises(HTTPException) as missing_etag:
        asyncio.run(
            psyke_router.create_progression(
                _request(
                    core,
                    incarnation,
                    mutation_id="psyke-progression-no-etag",
                ),
                psyke_router.PsykeProgressionCreate(entry_id=1, text="Changes"),
                core.project_id,
                Response(),
            )
        )
    assert missing_etag.value.status_code == 428
    assert missing_etag.value.detail["code"] == "revision_precondition_required"

    with pytest.raises(HTTPException) as missing_incarnation:
        asyncio.run(
            psyke_router.update_progression(
                _request(
                    core,
                    None,
                    etag=response.headers["etag"],
                    mutation_id="psyke-progression-no-incarnation",
                ),
                1,
                psyke_router.PsykeProgressionUpdate(text="Changes"),
                core.project_id,
                Response(),
            )
        )
    assert missing_incarnation.value.status_code == 428
    assert core.write_count("POST", "relations") == 0
    assert core.write_count("POST", "progressions") == 0
    assert core.write_count("PATCH", "progressions") == 0


def test_progression_create_retry_fails_safe_if_core_commits_without_receipt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    core = _Core(930114, [_entry(1, "Mara")])
    incarnation, revisions = _install(tmp_path, monkeypatch, core)
    _loaded, response = _progressions_read(core, incarnation)
    request = _request(
        core,
        incarnation,
        etag=response.headers["etag"],
        mutation_id="psyke-progression-uncertain",
    )
    body = psyke_router.PsykeProgressionCreate(
        entry_id=1, text="Mara accepts command"
    )
    original_commit = revisions.commit_mutation

    def fail_commit(*_args, **_kwargs):
        raise RuntimeError("simulated progression receipt failure")

    monkeypatch.setattr(revisions, "commit_mutation", fail_commit)
    with pytest.raises(RuntimeError, match="progression receipt failure"):
        asyncio.run(
            psyke_router.create_progression(
                request, body, core.project_id, Response()
            )
        )
    monkeypatch.setattr(revisions, "commit_mutation", original_commit)

    with pytest.raises(HTTPException) as retry:
        asyncio.run(
            psyke_router.create_progression(
                request, body, core.project_id, Response()
            )
        )
    assert retry.value.status_code == 409
    assert retry.value.detail["code"] == "revision_conflict"
    assert core.write_count("POST", "progressions") == 1
    assert [progression["text"] for progression in core.progressions] == [
        "Mara accepts command"
    ]


def test_progression_patch_preserves_omitted_scene_allows_unlink_and_replays(
    tmp_path: Path,
    monkeypatch,
) -> None:
    core = _Core(
        930115,
        [_entry(1, "Mara")],
        progressions=[
            _progression(9, 1, "Mara refuses command", scene_id=44)
        ],
    )
    incarnation, _revisions = _install(tmp_path, monkeypatch, core)
    loaded, response = _progressions_read(core, incarnation)
    request = _request(
        core,
        incarnation,
        etag=response.headers["etag"],
        mutation_id="psyke-progression-patch",
    )

    first_response = Response()
    first = asyncio.run(
        psyke_router.update_progression(
            request,
            9,
            psyke_router.PsykeProgressionUpdate(text="Mara accepts command"),
            core.project_id,
            first_response,
        )
    )
    patch_calls = [
        payload
        for method, path, payload in core.calls
        if method == "PATCH" and "/psyke/progressions/" in path
    ]
    assert patch_calls == [{"text": "Mara accepts command", "scene_id": 44}]
    assert first["progression"]["scene_id"] == 44
    assert first["revision"] != loaded["revision"]

    monkeypatch.setattr(
        psyke_router, "psyke_revision_store", PsykeRevisionStore(tmp_path)
    )
    retry = asyncio.run(
        psyke_router.update_progression(
            request,
            9,
            psyke_router.PsykeProgressionUpdate(text="Mara accepts command"),
            core.project_id,
            Response(),
        )
    )
    assert retry == first
    assert core.write_count("PATCH", "progressions") == 1

    unlink_response = Response()
    unlinked = asyncio.run(
        psyke_router.update_progression(
            _request(
                core,
                incarnation,
                etag=first_response.headers["etag"],
                mutation_id="psyke-progression-unlink",
            ),
            9,
            psyke_router.PsykeProgressionUpdate(scene_id=None),
            core.project_id,
            unlink_response,
        )
    )
    assert unlinked["progression"]["text"] == "Mara accepts command"
    assert unlinked["progression"]["scene_id"] is None
    assert core.write_count("PATCH", "progressions") == 2

    noop_request = _request(
        core,
        incarnation,
        etag=unlink_response.headers["etag"],
        mutation_id="psyke-progression-noop",
    )
    noop = asyncio.run(
        psyke_router.update_progression(
            noop_request,
            9,
            psyke_router.PsykeProgressionUpdate(text="Mara accepts command"),
            core.project_id,
            Response(),
        )
    )
    noop_retry = asyncio.run(
        psyke_router.update_progression(
            noop_request,
            9,
            psyke_router.PsykeProgressionUpdate(text="Mara accepts command"),
            core.project_id,
            Response(),
        )
    )
    assert noop_retry == noop
    assert core.write_count("PATCH", "progressions") == 2


class _NoopCleanupStore:
    def delete(self, _document_id: str) -> None:
        pass

    def list_document_ids(self) -> set[str]:
        return set()


def test_document_cleanup_removes_psyke_revision_identity_before_id_reuse(
    tmp_path: Path,
    monkeypatch,
) -> None:
    document_id = "930109"
    digest = "a" * 64
    old_incarnation = "1" * 32
    new_incarnation = "2" * 32
    revisions = PsykeRevisionStore(tmp_path)
    old = revisions.observe(document_id, old_incarnation, digest)
    noop = _NoopCleanupStore()
    monkeypatch.setattr(lifecycle, "whiteboard_store", noop)
    monkeypatch.setattr(lifecycle, "outline_items_store", noop)
    monkeypatch.setattr(lifecycle, "comments_store", noop)
    monkeypatch.setattr(lifecycle, "psyke_revision_store", revisions)

    assert lifecycle._clear_allocated_document_state(document_id) == []
    assert revisions.list_document_ids() == set()
    replacement = revisions.observe(document_id, new_incarnation, digest)
    assert replacement.revision != old.revision
    assert replacement.incarnation == new_incarnation

    monkeypatch.setattr(documents_router, "whiteboard_store", noop)
    monkeypatch.setattr(documents_router, "outline_items_store", noop)
    monkeypatch.setattr(documents_router, "comments_store", noop)
    monkeypatch.setattr(documents_router, "psyke_revision_store", revisions)
    assert documents_router._cleanup_local_document_state(document_id) == []
    assert revisions.list_document_ids() == set()
