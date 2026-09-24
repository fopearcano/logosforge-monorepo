from __future__ import annotations

import asyncio
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response
from starlette.datastructures import Headers

import app.document_lifecycle as lifecycle
from app.local_state import (
    MutationIdConflict,
    OutlineItemsDocument,
    OutlineItemsStore,
    ResourceRevisionConflict,
    WhiteboardCreate,
    WhiteboardStore,
    WhiteboardUpdate,
)
from app.main import resource_protocol_error_handler
from app.resource_revision import resource_etag, revision_conflict
from app.routers import outline as outline_router
from app.routers import whiteboard as whiteboard_router


_REVISION_RE = re.compile(r"^[0-9a-f]{32}$")


class _Core:
    def __init__(self, project_id: int) -> None:
        self.project_id = project_id

    async def request(self, _method: str, _path: str, **_kwargs):
        return SimpleNamespace()

    async def ensure_project_with_status(self) -> tuple[int, bool]:
        return self.project_id, False

    async def ensure_project(self) -> int:
        return self.project_id


def _request(core: _Core, headers: dict[str, str] | None = None):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(core=core)),
        headers=Headers(headers or {}),
    )


def _headers(
    incarnation: str,
    *,
    etag: str | None = None,
    mutation_id: str | None = None,
    order: int | None = None,
) -> dict[str, str]:
    headers = {"X-LogosForge-Document-Incarnation": incarnation}
    if etag is not None:
        headers["If-Match"] = etag
    if mutation_id is not None:
        headers["X-LogosForge-Mutation-Id"] = mutation_id
    if order is not None:
        headers["X-LogosForge-Persistence-Order"] = str(order)
    return headers


def _install_stores(monkeypatch, whiteboards: WhiteboardStore, outlines: OutlineItemsStore) -> None:
    monkeypatch.setattr(lifecycle, "whiteboard_store", whiteboards)
    monkeypatch.setattr(whiteboard_router, "whiteboard_store", whiteboards)
    monkeypatch.setattr(outline_router, "outline_items_store", outlines)


def test_legacy_resources_get_one_stable_revision_without_touching_updated_at(
    tmp_path: Path,
) -> None:
    timestamp = "2025-01-02T03:04:05+00:00"
    manuscript_path = tmp_path / "whiteboards" / "7.json"
    manuscript_path.parent.mkdir(parents=True)
    manuscript_path.write_text(
        json.dumps({
            "id": "7",
            "incarnation": "a" * 32,
            "title": "Legacy",
            "mode": "novel",
            "blocks": [],
            "settings": {},
            "updated_at": timestamp,
        }),
        encoding="utf-8",
    )
    whiteboards = WhiteboardStore(tmp_path)
    first = whiteboards.get("7")
    second = whiteboards.get("7")

    assert _REVISION_RE.fullmatch(first.revision)
    assert second.revision == first.revision
    assert first.updated_at == timestamp
    stored = json.loads(manuscript_path.read_text(encoding="utf-8"))
    assert stored["revision"] == first.revision
    assert stored["updated_at"] == timestamp

    outline_path = tmp_path / "outlines" / "7.json"
    outline_path.parent.mkdir(parents=True)
    outline_path.write_text('[{"id":"legacy"}]', encoding="utf-8")
    outlines = OutlineItemsStore(tmp_path)
    outline_first = outlines.get_document("7")
    outline_second = outlines.get_document("7")
    assert _REVISION_RE.fullmatch(outline_first.revision)
    assert outline_second.revision == outline_first.revision
    stored_outline = json.loads(outline_path.read_text(encoding="utf-8"))
    assert stored_outline["revision"] == outline_first.revision


def test_revision_conflict_uses_structured_error_envelope_and_current_etag() -> None:
    current_etag = resource_etag("whiteboard", "a" * 32, "c" * 32)
    response = asyncio.run(
        resource_protocol_error_handler(
            SimpleNamespace(),
            revision_conflict("whiteboard", "a" * 32, "b" * 32, "c" * 32),
        )
    )
    assert response.status_code == 409
    assert response.headers["etag"] == current_etag
    assert json.loads(response.body)["error"]["code"] == "revision_conflict"


def test_whiteboard_get_and_conditional_put_publish_body_revision_and_etag(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_id = 920101
    whiteboards = WhiteboardStore(tmp_path)
    outlines = OutlineItemsStore(tmp_path)
    created = whiteboards.create(str(project_id), WhiteboardCreate(title="First"))
    _install_stores(monkeypatch, whiteboards, outlines)
    core = _Core(project_id)

    get_response = Response()
    loaded = asyncio.run(
        whiteboard_router.get_whiteboard(
            _request(core, _headers(created.incarnation)), get_response, project_id
        )
    )
    first_etag = resource_etag("whiteboard", created.incarnation, loaded.revision)
    assert get_response.headers["etag"] == first_etag
    assert loaded.revision == created.revision

    put_response = Response()
    updated = asyncio.run(
        whiteboard_router.update_whiteboard(
            _request(core, _headers(created.incarnation, etag=first_etag)),
            put_response,
            WhiteboardUpdate(title="Second"),
            project_id,
        )
    )
    assert updated.title == "Second"
    assert updated.revision != loaded.revision
    assert put_response.headers["etag"] == resource_etag(
        "whiteboard", created.incarnation, updated.revision
    )

    with pytest.raises(HTTPException) as duplicate:
        asyncio.run(
            whiteboard_router.create_whiteboard(
                _request(core, _headers(created.incarnation)),
                Response(),
                WhiteboardCreate(title="Replacement"),
                project_id,
            )
        )
    assert duplicate.value.status_code == 409
    assert duplicate.value.detail["code"] == "resource_already_exists"
    assert duplicate.value.headers == {
        "ETag": resource_etag("whiteboard", created.incarnation, updated.revision)
    }
    assert whiteboards.get(str(project_id)).title == "Second"


def test_whiteboard_post_creates_only_when_the_manuscript_is_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_id = 920113
    whiteboards = WhiteboardStore(tmp_path)
    _install_stores(monkeypatch, whiteboards, OutlineItemsStore(tmp_path))
    response = Response()

    created = asyncio.run(
        whiteboard_router.create_whiteboard(
            _request(_Core(project_id)),
            response,
            WhiteboardCreate(title="Created once"),
            None,
        )
    )

    assert created.title == "Created once"
    assert _REVISION_RE.fullmatch(created.revision)
    assert response.headers["etag"] == resource_etag(
        "whiteboard", created.incarnation, created.revision
    )
    with pytest.raises(HTTPException) as duplicate:
        asyncio.run(
            whiteboard_router.create_whiteboard(
                _request(_Core(project_id), _headers(created.incarnation)),
                Response(),
                WhiteboardCreate(title="Must not replace"),
                None,
            )
        )
    assert duplicate.value.status_code == 409
    assert duplicate.value.detail["code"] == "resource_already_exists"
    assert whiteboards.get(str(project_id)).title == "Created once"

    explicit_id = project_id + 1
    with pytest.raises(HTTPException) as unsafe_explicit_create:
        asyncio.run(
            whiteboard_router.create_whiteboard(
                _request(_Core(explicit_id)),
                Response(),
                WhiteboardCreate(title="Must use the document lifecycle"),
                explicit_id,
            )
        )
    assert unsafe_explicit_create.value.status_code == 409
    assert not whiteboards.exists(str(explicit_id))


@pytest.mark.parametrize("value", ["*", 'W/"tag"', '"other"', '"a","b"'])
def test_explicit_put_requires_one_well_formed_strong_if_match(
    tmp_path: Path,
    monkeypatch,
    value: str,
) -> None:
    project_id = 920102
    whiteboards = WhiteboardStore(tmp_path)
    created = whiteboards.create(str(project_id), WhiteboardCreate(title="Original"))
    _install_stores(monkeypatch, whiteboards, OutlineItemsStore(tmp_path))
    core = _Core(project_id)

    with pytest.raises(HTTPException) as caught:
        asyncio.run(
            whiteboard_router.update_whiteboard(
                _request(core, _headers(created.incarnation, etag=value)),
                Response(),
                WhiteboardUpdate(title="Rejected"),
                project_id,
            )
        )
    assert caught.value.status_code == 400
    assert caught.value.detail["code"] == "invalid_if_match"
    assert whiteboards.get(str(project_id)).title == "Original"


def test_missing_and_stale_preconditions_do_not_write_and_report_current_etag(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_id = 920103
    whiteboards = WhiteboardStore(tmp_path)
    created = whiteboards.create(str(project_id), WhiteboardCreate(title="Original"))
    _install_stores(monkeypatch, whiteboards, OutlineItemsStore(tmp_path))
    core = _Core(project_id)

    with pytest.raises(HTTPException) as missing:
        asyncio.run(
            whiteboard_router.update_whiteboard(
                _request(core, _headers(created.incarnation)),
                Response(),
                WhiteboardUpdate(title="Missing"),
                project_id,
            )
        )
    assert missing.value.status_code == 428
    assert missing.value.detail["code"] == "revision_precondition_required"

    initial_etag = resource_etag("whiteboard", created.incarnation, created.revision)
    current = asyncio.run(
        whiteboard_router.update_whiteboard(
            _request(core, _headers(created.incarnation, etag=initial_etag)),
            Response(),
            WhiteboardUpdate(title="Current"),
            project_id,
        )
    )
    with pytest.raises(HTTPException) as stale:
        asyncio.run(
            whiteboard_router.update_whiteboard(
                _request(core, _headers(created.incarnation, etag=initial_etag)),
                Response(),
                WhiteboardUpdate(title="Stale"),
                project_id,
            )
        )
    current_etag = resource_etag("whiteboard", created.incarnation, current.revision)
    assert stale.value.status_code == 409
    assert stale.value.detail == {
        "code": "revision_conflict",
        "message": "The resource changed after it was loaded. Reload before saving again.",
        "expected_revision": created.revision,
        "current_revision": current.revision,
        "current_etag": current_etag,
    }
    assert stale.value.headers == {"ETag": current_etag}
    assert whiteboards.get(str(project_id)).title == "Current"


def test_only_one_concurrent_write_from_the_same_revision_commits(tmp_path: Path) -> None:
    store = WhiteboardStore(tmp_path)
    created = store.create("920104", WhiteboardCreate(title="Base"))

    def write(title: str) -> tuple[str, str]:
        try:
            result = store.update(
                "920104",
                WhiteboardUpdate(title=title),
                expected_revision=created.revision,
            )
            return "saved", result.title
        except ResourceRevisionConflict:
            return "conflict", title

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(write, ["Alpha", "Beta"]))

    assert sorted(outcome for outcome, _title in outcomes) == ["conflict", "saved"]
    winner = next(title for outcome, title in outcomes if outcome == "saved")
    assert store.get("920104").title == winner


def test_outline_conditional_update_and_exact_idempotent_retry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_id = 920105
    whiteboards = WhiteboardStore(tmp_path)
    manuscript = whiteboards.create(str(project_id), WhiteboardCreate(title="Outline"))
    outlines = OutlineItemsStore(tmp_path)
    _install_stores(monkeypatch, whiteboards, outlines)
    core = _Core(project_id)

    get_response = Response()
    initial = asyncio.run(
        outline_router.get_outline_items(
            _request(core, _headers(manuscript.incarnation)), get_response, project_id
        )
    )
    initial_etag = resource_etag("outline", manuscript.incarnation, initial.revision)
    assert get_response.headers["etag"] == initial_etag

    headers = _headers(
        manuscript.incarnation,
        etag=initial_etag,
        mutation_id="outline-mutation-1",
    )
    first_response = Response()
    first = asyncio.run(
        outline_router.put_outline_items(
            _request(core, headers),
            first_response,
            OutlineItemsDocument(items=[{"id": "one"}]),
            project_id,
        )
    )
    first_etag = resource_etag("outline", manuscript.incarnation, first.revision)
    assert first_response.headers["etag"] == first_etag

    retry_response = Response()
    retried = asyncio.run(
        outline_router.put_outline_items(
            _request(core, headers),
            retry_response,
            OutlineItemsDocument(items=[{"id": "one"}]),
            project_id,
        )
    )
    assert retried.revision == first.revision
    assert retry_response.headers["etag"] == first_etag

    with pytest.raises(HTTPException) as reused:
        asyncio.run(
            outline_router.put_outline_items(
                _request(core, headers),
                Response(),
                OutlineItemsDocument(items=[{"id": "different"}]),
                project_id,
            )
        )
    assert reused.value.status_code == 409
    assert reused.value.detail["code"] == "mutation_id_conflict"

    raw = json.loads((tmp_path / "outlines" / f"{project_id}.json").read_text(encoding="utf-8"))
    assert raw["last_mutation_id"] == "outline-mutation-1"
    assert "last_mutation_id" not in retried.model_dump()
    assert outlines.get(str(project_id)) == [{"id": "one"}]


def test_missing_outline_conflict_advertises_one_durable_current_revision(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_id = 920114
    whiteboards = WhiteboardStore(tmp_path)
    manuscript = whiteboards.create(str(project_id), WhiteboardCreate(title="Outline"))
    outlines = OutlineItemsStore(tmp_path)
    _install_stores(monkeypatch, whiteboards, outlines)
    headers = _headers(
        manuscript.incarnation,
        etag=resource_etag("outline", manuscript.incarnation, "f" * 32),
    )

    advertised: list[str] = []
    for _attempt in range(2):
        with pytest.raises(HTTPException) as stale:
            asyncio.run(
                outline_router.put_outline_items(
                    _request(_Core(project_id), headers),
                    Response(),
                    OutlineItemsDocument(items=[{"id": "stale"}]),
                    project_id,
                )
            )
        assert stale.value.status_code == 409
        advertised.append(stale.value.detail["current_revision"])

    loaded = asyncio.run(
        outline_router.get_outline_items(
            _request(_Core(project_id), _headers(manuscript.incarnation)),
            Response(),
            project_id,
        )
    )
    assert advertised[0] == advertised[1] == loaded.revision
    assert outlines.get(str(project_id)) == []


def test_exact_whiteboard_retry_returns_prior_success_without_rotating_revision(
    tmp_path: Path,
) -> None:
    store = WhiteboardStore(tmp_path)
    created = store.create("920106", WhiteboardCreate(title="Original"))
    patch = WhiteboardUpdate(title="Saved")
    first = store.update(
        "920106",
        patch,
        expected_revision=created.revision,
        mutation_id="whiteboard-mutation-1",
    )
    retry = store.update(
        "920106",
        patch,
        expected_revision=created.revision,
        mutation_id="whiteboard-mutation-1",
    )
    assert retry.revision == first.revision
    with pytest.raises(MutationIdConflict):
        store.update(
            "920106",
            WhiteboardUpdate(title="Different"),
            expected_revision=created.revision,
            mutation_id="whiteboard-mutation-1",
        )
    raw = json.loads((tmp_path / "whiteboards" / "920106.json").read_text(encoding="utf-8"))
    assert raw["last_mutation_id"] == "whiteboard-mutation-1"
    assert "last_mutation_id" not in retry.model_dump()


def test_stale_persistence_order_is_a_noop_with_the_current_etag(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_id = 920107
    whiteboards = WhiteboardStore(tmp_path)
    created = whiteboards.create(str(project_id), WhiteboardCreate(title="Original"))
    _install_stores(monkeypatch, whiteboards, OutlineItemsStore(tmp_path))
    core = _Core(project_id)
    original_etag = resource_etag("whiteboard", created.incarnation, created.revision)

    newest = asyncio.run(
        whiteboard_router.update_whiteboard(
            _request(core, _headers(created.incarnation, etag=original_etag, order=2)),
            Response(),
            WhiteboardUpdate(title="Newest"),
            project_id,
        )
    )
    stale_response = Response()
    stale_result = asyncio.run(
        whiteboard_router.update_whiteboard(
            _request(core, _headers(created.incarnation, etag=original_etag, order=1)),
            stale_response,
            WhiteboardUpdate(title="Older"),
            project_id,
        )
    )
    assert stale_result.title == "Newest"
    assert stale_result.revision == newest.revision
    assert stale_response.headers["etag"] == resource_etag(
        "whiteboard", created.incarnation, newest.revision
    )


def test_whiteboard_external_write_invalidates_ordered_noop_lineage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_id = 920109
    whiteboards = WhiteboardStore(tmp_path)
    created = whiteboards.create(str(project_id), WhiteboardCreate(title="Original"))
    _install_stores(monkeypatch, whiteboards, OutlineItemsStore(tmp_path))
    core = _Core(project_id)
    initial_etag = resource_etag("whiteboard", created.incarnation, created.revision)

    ordered_headers = _headers(
        created.incarnation,
        etag=initial_etag,
        mutation_id="ordered-whiteboard-2",
        order=2,
    )
    ordered = asyncio.run(
        whiteboard_router.update_whiteboard(
            _request(core, ordered_headers),
            Response(),
            WhiteboardUpdate(title="Ordered"),
            project_id,
        )
    )
    ordered_etag = resource_etag("whiteboard", created.incarnation, ordered.revision)
    external = asyncio.run(
        whiteboard_router.update_whiteboard(
            _request(
                core,
                _headers(
                    created.incarnation,
                    etag=ordered_etag,
                    mutation_id="external-whiteboard",
                ),
            ),
            Response(),
            WhiteboardUpdate(title="External"),
            project_id,
        )
    )

    for delayed_headers in (
        _headers(created.incarnation, etag=initial_etag, order=1),
        ordered_headers,
    ):
        with pytest.raises(HTTPException) as stale:
            asyncio.run(
                whiteboard_router.update_whiteboard(
                    _request(core, delayed_headers),
                    Response(),
                    WhiteboardUpdate(title="Ordered"),
                    project_id,
                )
            )
        assert stale.value.status_code == 409
        assert stale.value.detail["code"] == "revision_conflict"
        assert stale.value.detail["current_revision"] == external.revision
    assert whiteboards.get(str(project_id)).title == "External"


def test_outline_external_write_invalidates_ordered_noop_lineage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_id = 920110
    whiteboards = WhiteboardStore(tmp_path)
    manuscript = whiteboards.create(str(project_id), WhiteboardCreate(title="Outline"))
    outlines = OutlineItemsStore(tmp_path)
    _install_stores(monkeypatch, whiteboards, outlines)
    core = _Core(project_id)
    initial = outlines.get_document(str(project_id))
    initial_etag = resource_etag("outline", manuscript.incarnation, initial.revision)

    ordered_headers = _headers(
        manuscript.incarnation,
        etag=initial_etag,
        mutation_id="ordered-outline-4",
        order=4,
    )
    ordered = asyncio.run(
        outline_router.put_outline_items(
            _request(core, ordered_headers),
            Response(),
            OutlineItemsDocument(items=[{"id": "ordered"}]),
            project_id,
        )
    )
    external = asyncio.run(
        outline_router.put_outline_items(
            _request(
                core,
                _headers(
                    manuscript.incarnation,
                    etag=resource_etag(
                        "outline", manuscript.incarnation, ordered.revision
                    ),
                    mutation_id="external-outline",
                ),
            ),
            Response(),
            OutlineItemsDocument(items=[{"id": "external"}]),
            project_id,
        )
    )

    with pytest.raises(HTTPException) as stale:
        asyncio.run(
            outline_router.put_outline_items(
                _request(core, ordered_headers),
                Response(),
                OutlineItemsDocument(items=[{"id": "ordered"}]),
                project_id,
            )
        )
    assert stale.value.status_code == 409
    assert stale.value.detail["code"] == "revision_conflict"
    assert stale.value.detail["current_revision"] == external.revision
    assert outlines.get(str(project_id)) == [{"id": "external"}]


def test_manuscript_recovery_rotates_revision_and_rejects_pre_recovery_etag(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_id = 920111
    whiteboards = WhiteboardStore(tmp_path)
    created = whiteboards.create(str(project_id), WhiteboardCreate(title="Original"))
    first = whiteboards.update(
        str(project_id),
        WhiteboardUpdate(title="Backup"),
        expected_revision=created.revision,
        mutation_id="manuscript-backup-mutation",
    )
    outlines = OutlineItemsStore(tmp_path)
    _install_stores(monkeypatch, whiteboards, outlines)
    current_headers = _headers(
        created.incarnation,
        etag=resource_etag("whiteboard", created.incarnation, first.revision),
        mutation_id="manuscript-current-mutation",
        order=7,
    )
    current = asyncio.run(
        whiteboard_router.update_whiteboard(
            _request(_Core(project_id), current_headers),
            Response(),
            WhiteboardUpdate(title="Current"),
            project_id,
        )
    )
    path = tmp_path / "whiteboards" / f"{project_id}.json"
    backup = json.loads(path.with_name(path.name + ".bak").read_text(encoding="utf-8"))
    assert backup["revision"] == first.revision
    assert backup["last_mutation_id"] == "manuscript-backup-mutation"
    path.write_text("{broken", encoding="utf-8")

    recovered = whiteboards.get(str(project_id))
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert recovered.title == "Backup"
    assert recovered.updated_at == backup["updated_at"]
    assert recovered.revision not in {first.revision, current.revision}
    assert stored["revision"] == recovered.revision
    assert stored["last_mutation_id"] == ""
    assert stored["last_mutation_fingerprint"] == ""

    with pytest.raises(HTTPException) as stale:
        asyncio.run(
            whiteboard_router.update_whiteboard(
                _request(_Core(project_id), current_headers),
                Response(),
                WhiteboardUpdate(title="Current"),
                project_id,
            )
        )
    assert stale.value.status_code == 409
    assert stale.value.detail["current_revision"] == recovered.revision


def test_outline_recovery_rotates_revision_and_rejects_pre_recovery_etag(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_id = 920112
    whiteboards = WhiteboardStore(tmp_path)
    manuscript = whiteboards.create(str(project_id), WhiteboardCreate(title="Outline"))
    outlines = OutlineItemsStore(tmp_path)
    initial = outlines.get_document(str(project_id))
    first = outlines.replace_document(
        str(project_id),
        [{"id": "backup"}],
        expected_revision=initial.revision,
        mutation_id="outline-backup-mutation",
    )
    _install_stores(monkeypatch, whiteboards, outlines)
    current_headers = _headers(
        manuscript.incarnation,
        etag=resource_etag("outline", manuscript.incarnation, first.revision),
        mutation_id="outline-current-mutation",
        order=7,
    )
    current = asyncio.run(
        outline_router.put_outline_items(
            _request(_Core(project_id), current_headers),
            Response(),
            OutlineItemsDocument(items=[{"id": "current"}]),
            project_id,
        )
    )
    path = tmp_path / "outlines" / f"{project_id}.json"
    backup = json.loads(path.with_name(path.name + ".bak").read_text(encoding="utf-8"))
    assert backup["revision"] == first.revision
    assert backup["last_mutation_id"] == "outline-backup-mutation"
    path.write_text("{broken", encoding="utf-8")

    recovered = outlines.get_document(str(project_id))
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert recovered.items == [{"id": "backup"}]
    assert recovered.revision not in {first.revision, current.revision}
    assert stored["revision"] == recovered.revision
    assert stored["last_mutation_id"] == ""
    assert stored["last_mutation_fingerprint"] == ""

    with pytest.raises(HTTPException) as stale:
        asyncio.run(
            outline_router.put_outline_items(
                _request(_Core(project_id), current_headers),
                Response(),
                OutlineItemsDocument(items=[{"id": "current"}]),
                project_id,
            )
        )
    assert stale.value.status_code == 409
    assert stale.value.detail["current_revision"] == recovered.revision


def test_legacy_default_put_without_if_match_remains_compatible(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_id = 920108
    whiteboards = WhiteboardStore(tmp_path)
    created = whiteboards.create(str(project_id), WhiteboardCreate(title="Legacy"))
    _install_stores(monkeypatch, whiteboards, OutlineItemsStore(tmp_path))

    response = Response()
    updated = asyncio.run(
        whiteboard_router.update_whiteboard(
            _request(_Core(project_id)),
            response,
            WhiteboardUpdate(title="Compatible"),
            None,
        )
    )
    assert updated.title == "Compatible"
    assert updated.revision != created.revision
    assert response.headers["etag"] == resource_etag(
        "whiteboard", created.incarnation, updated.revision
    )
