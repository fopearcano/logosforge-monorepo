"""Drafter local-state, conditional-resource, recovery, and lifecycle tests."""
from __future__ import annotations

import asyncio
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException, Response
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.datastructures import Headers

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

import app.document_lifecycle as lifecycle  # noqa: E402
import app.local_state as local_state  # noqa: E402
from app.local_state import (  # noqa: E402
    DrafterPage,
    DrafterPageAlreadyExists,
    DrafterPagePatch,
    DrafterPagesDocument,
    DrafterPagesStore,
    LocalStateCorruptionError,
    MutationIdConflict,
    ResourceRevisionConflict,
    WhiteboardBlock,
    WhiteboardCreate,
    WhiteboardStore,
)
from app.persistence_order import request_delete_order_floors  # noqa: E402
from app.resource_revision import resource_etag  # noqa: E402
from app.routers import documents as documents_router  # noqa: E402
from app.routers import drafter as drafter_router  # noqa: E402


_REVISION_RE = re.compile(r"^[0-9a-f]{32}$")


class _Core:
    def __init__(self, project_id: int) -> None:
        self.project_id = project_id

    async def ensure_project_with_status(self) -> tuple[int, bool]:
        return self.project_id, False

    async def ensure_project(self) -> int:
        return self.project_id

    async def request(self, method: str, path: str, **_kwargs):
        assert method == "GET"
        assert path == f"/api/projects/{self.project_id}"
        return SimpleNamespace()


class _EmptyStore:
    def list_document_ids(self) -> set[str]:
        return set()

    def delete(self, _doc_id: str) -> None:
        pass


def _page(page_id: str = "page-1", text: str = "A separate scene.") -> DrafterPage:
    return DrafterPage(
        id=page_id,
        title="Scene experiment",
        blocks=[WhiteboardBlock(id=f"{page_id}-b1", text=text)],
        created_at="2026-09-26T10:00:00+02:00",
        updated_at="2026-09-26T10:00:00+02:00",
    )


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
    result = {"X-LogosForge-Document-Incarnation": incarnation}
    if etag is not None:
        result["If-Match"] = etag
    if mutation_id is not None:
        result["X-LogosForge-Mutation-Id"] = mutation_id
    if order is not None:
        result["X-LogosForge-Persistence-Order"] = str(order)
    return result


def _install_stores(
    monkeypatch: pytest.MonkeyPatch,
    manuscripts: WhiteboardStore,
    drafter: DrafterPagesStore,
) -> None:
    monkeypatch.setattr(lifecycle, "whiteboard_store", manuscripts)
    monkeypatch.setattr(lifecycle, "drafter_pages_store", drafter)
    monkeypatch.setattr(drafter_router, "drafter_pages_store", drafter)


def test_missing_drafter_materializes_one_stable_empty_revision(tmp_path: Path) -> None:
    store = DrafterPagesStore(tmp_path)

    first = store.get_document("7")
    second = store.get_document("7")

    assert first.pages == []
    assert _REVISION_RE.fullmatch(first.revision)
    assert second.revision == first.revision
    stored = json.loads((tmp_path / "drafter" / "7.json").read_text(encoding="utf-8"))
    assert stored["pages"] == []
    assert stored["revision"] == first.revision


def test_drafter_collection_rejects_invalid_and_duplicate_page_identity() -> None:
    with pytest.raises(ValidationError, match="safe ASCII"):
        _page("bad id")
    with pytest.raises(ValidationError, match="must not be blank"):
        DrafterPage(
            id="valid",
            title="   ",
            blocks=[],
            created_at="2026-09-26T08:00:00Z",
            updated_at="2026-09-26T08:00:00Z",
        )
    with pytest.raises(ValidationError, match="include a timezone"):
        DrafterPage(
            id="valid",
            title="Valid",
            blocks=[],
            created_at="2026-09-26T08:00:00",
            updated_at="2026-09-26T08:00:00Z",
        )
    with pytest.raises(ValidationError, match="must be unique"):
        DrafterPagesDocument(pages=[_page("same"), _page("same")])


def test_drafter_collection_caps_pages_and_blocks() -> None:
    with pytest.raises(ValidationError, match="too many pages"):
        DrafterPagesDocument(
            pages=[_page(f"page-{index}") for index in range(257)]
        )
    with pytest.raises(ValidationError, match="too many blocks"):
        DrafterPage(
            id="large",
            title="Large",
            blocks=[WhiteboardBlock(id=f"b-{index}") for index in range(20_001)],
            created_at="2026-09-26T08:00:00Z",
            updated_at="2026-09-26T08:00:00Z",
        )

    with pytest.raises(ValidationError, match="too many inline marks"):
        DrafterPage(
            id="marks",
            title="Marks",
            blocks=[WhiteboardBlock(id="b-1", marks=[{}] * 20_001)],
            created_at="2026-09-26T08:00:00Z",
            updated_at="2026-09-26T08:00:00Z",
        )
    with pytest.raises(ValidationError, match="mark metadata"):
        DrafterPage(
            id="mark-data",
            title="Mark data",
            blocks=[WhiteboardBlock(
                id="b-1",
                marks=[{"type": "comment", "payload": "x" * 1_000_001}],
            )],
            created_at="2026-09-26T08:00:00Z",
            updated_at="2026-09-26T08:00:00Z",
        )


def test_drafter_collection_caps_aggregate_inline_mark_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(local_state, "_DRAFTER_MAX_MARKS_TOTAL", 3)
    pages = [
        DrafterPage(
            id=f"marks-{index}",
            title="Marks",
            blocks=[WhiteboardBlock(id="b-1", marks=[{}, {}])],
            created_at="2026-09-26T08:00:00Z",
            updated_at="2026-09-26T08:00:00Z",
        )
        for index in range(2)
    ]

    with pytest.raises(ValidationError, match="drafter contains too many inline marks"):
        DrafterPagesDocument(pages=pages)


def test_drafter_collection_caps_aggregate_inline_mark_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        DrafterPage(
            id=f"metadata-{index}",
            title="Metadata",
            blocks=[WhiteboardBlock(
                id="b-1",
                marks=[{"type": "comment", "payload": "unicode è"}],
            )],
            created_at="2026-09-26T08:00:00Z",
            updated_at="2026-09-26T08:00:00Z",
        )
        for index in range(2)
    ]
    one_mark_characters = len(json.dumps(
        pages[0].blocks[0].marks[0],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ))
    monkeypatch.setattr(
        local_state,
        "_DRAFTER_MAX_MARK_METADATA_CHARS_TOTAL",
        one_mark_characters * 2 - 1,
    )

    with pytest.raises(ValidationError, match="drafter inline-mark metadata"):
        DrafterPagesDocument(pages=pages)


def test_drafter_collection_caps_utf8_serialized_snapshot_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _page(text="🩶" * 32)
    serialized_bytes = len(json.dumps(
        {"pages": [page.model_dump(mode="json")]},
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8"))
    monkeypatch.setattr(
        local_state,
        "_DRAFTER_MAX_SERIALIZED_BYTES_TOTAL",
        serialized_bytes,
    )
    assert DrafterPagesDocument(pages=[page]).pages == [page]

    monkeypatch.setattr(
        local_state,
        "_DRAFTER_MAX_SERIALIZED_BYTES_TOTAL",
        serialized_bytes - 1,
    )
    with pytest.raises(ValidationError, match="desktop transport safety limit"):
        DrafterPagesDocument(pages=[page])


def test_drafter_patch_validates_page_limits_before_store_dispatch() -> None:
    with pytest.raises(ValidationError, match="too many blocks"):
        DrafterPagePatch(
            blocks=[WhiteboardBlock(id=f"b-{index}") for index in range(20_001)]
        )
    with pytest.raises(ValidationError, match="must contain 1-128 characters"):
        DrafterPagePatch(blocks=[WhiteboardBlock(id="x" * 129)])


def test_conditional_store_write_is_atomic_and_exact_retry_is_idempotent(
    tmp_path: Path,
) -> None:
    store = DrafterPagesStore(tmp_path)
    initial = store.get_document("7")
    first = store.replace_document(
        "7",
        [_page()],
        expected_revision=initial.revision,
        mutation_id="drafter-save-1",
    )
    retry = store.replace_document(
        "7",
        [_page()],
        expected_revision=initial.revision,
        mutation_id="drafter-save-1",
    )

    assert retry == first
    assert retry.revision == first.revision
    with pytest.raises(MutationIdConflict):
        store.replace_document(
            "7",
            [_page(text="Different request")],
            expected_revision=initial.revision,
            mutation_id="drafter-save-1",
        )
    with pytest.raises(ResourceRevisionConflict):
        store.replace_document(
            "7", [_page("page-2")], expected_revision=initial.revision
        )
    assert store.get_document("7") == first


def test_only_one_concurrent_drafter_write_from_same_revision_commits(
    tmp_path: Path,
) -> None:
    store = DrafterPagesStore(tmp_path)
    initial = store.get_document("7")

    def write(page_id: str) -> str:
        try:
            store.replace_document(
                "7", [_page(page_id)], expected_revision=initial.revision
            )
            return "saved"
        except ResourceRevisionConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(write, ["alpha", "beta"]))

    assert sorted(outcomes) == ["conflict", "saved"]
    assert store.get_document("7").pages[0].id in {"alpha", "beta"}


def test_drafter_recovers_newest_valid_backup_with_fresh_revision(
    tmp_path: Path,
) -> None:
    store = DrafterPagesStore(tmp_path)
    initial = store.get_document("7")
    first = store.replace_document(
        "7", [_page("first")], expected_revision=initial.revision
    )
    second = store.replace_document(
        "7", [_page("second")], expected_revision=first.revision
    )
    path = tmp_path / "drafter" / "7.json"
    path.write_text("not-json", encoding="utf-8")

    recovered = store.get_document("7")

    assert recovered.pages[0].id == "first"
    assert recovered.revision not in {first.revision, second.revision}
    assert path.exists()
    assert list(path.parent.glob("7.json.corrupt-*"))


def test_drafter_corruption_without_valid_backup_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "drafter" / "7.json"
    path.parent.mkdir(parents=True)
    path.write_text("not-json", encoding="utf-8")

    with pytest.raises(LocalStateCorruptionError):
        DrafterPagesStore(tmp_path).get_document("7")

    assert path.read_text(encoding="utf-8") == "not-json"


def test_drafter_get_and_conditional_put_publish_revision_etag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = 940101
    manuscripts = WhiteboardStore(tmp_path)
    manuscript = manuscripts.create(str(project_id), WhiteboardCreate(title="Drafts"))
    drafter = DrafterPagesStore(tmp_path)
    _install_stores(monkeypatch, manuscripts, drafter)
    core = _Core(project_id)

    get_response = Response()
    loaded = asyncio.run(
        drafter_router.get_drafter_pages(
            _request(core, _headers(manuscript.incarnation)),
            get_response,
            project_id,
        )
    )
    first_etag = resource_etag("drafter", manuscript.incarnation, loaded.revision)
    assert get_response.headers["etag"] == first_etag

    put_response = Response()
    updated = asyncio.run(
        drafter_router.put_drafter_pages(
            _request(
                core,
                _headers(
                    manuscript.incarnation,
                    etag=first_etag,
                    mutation_id="route-save-1",
                ),
            ),
            put_response,
            DrafterPagesDocument(pages=[_page()]),
            project_id,
        )
    )
    assert updated.pages[0].id == "page-1"
    assert put_response.headers["etag"] == resource_etag(
        "drafter", manuscript.incarnation, updated.revision
    )

    with pytest.raises(HTTPException) as stale:
        asyncio.run(
            drafter_router.put_drafter_pages(
                _request(
                    core,
                    _headers(manuscript.incarnation, etag=first_etag),
                ),
                Response(),
                DrafterPagesDocument(pages=[_page("stale")]),
                project_id,
            )
        )
    assert stale.value.status_code == 409
    assert stale.value.detail["code"] == "revision_conflict"
    assert drafter.get_document(str(project_id)) == updated


def test_explicit_drafter_put_requires_incarnation_and_if_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = 940102
    manuscripts = WhiteboardStore(tmp_path)
    manuscript = manuscripts.create(str(project_id), WhiteboardCreate())
    drafter = DrafterPagesStore(tmp_path)
    _install_stores(monkeypatch, manuscripts, drafter)
    core = _Core(project_id)

    with pytest.raises(HTTPException) as missing_incarnation:
        asyncio.run(
            drafter_router.put_drafter_pages(
                _request(core),
                Response(),
                DrafterPagesDocument(pages=[]),
                project_id,
            )
        )
    assert missing_incarnation.value.status_code == 428

    with pytest.raises(HTTPException) as missing_etag:
        asyncio.run(
            drafter_router.put_drafter_pages(
                _request(core, _headers(manuscript.incarnation)),
                Response(),
                DrafterPagesDocument(pages=[]),
                project_id,
            )
        )
    assert missing_etag.value.status_code == 428


def test_older_ordered_drafter_snapshot_cannot_replace_newer_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = 940104
    manuscripts = WhiteboardStore(tmp_path)
    manuscript = manuscripts.create(str(project_id), WhiteboardCreate())
    drafter = DrafterPagesStore(tmp_path)
    initial = drafter.get_document(str(project_id))
    _install_stores(monkeypatch, manuscripts, drafter)
    core = _Core(project_id)
    initial_etag = resource_etag(
        "drafter", manuscript.incarnation, initial.revision
    )

    newest = asyncio.run(
        drafter_router.put_drafter_pages(
            _request(
                core,
                _headers(
                    manuscript.incarnation,
                    etag=initial_etag,
                    mutation_id="ordered-newest",
                    order=2,
                ),
            ),
            Response(),
            DrafterPagesDocument(pages=[_page("newest")]),
            project_id,
        )
    )
    delayed = asyncio.run(
        drafter_router.put_drafter_pages(
            _request(
                core,
                _headers(
                    manuscript.incarnation,
                    etag=initial_etag,
                    mutation_id="ordered-delayed",
                    order=1,
                ),
            ),
            Response(),
            DrafterPagesDocument(pages=[_page("delayed")]),
            project_id,
        )
    )

    assert delayed == newest
    assert drafter.get_document(str(project_id)).pages[0].id == "newest"


def test_drafter_delete_floor_header_is_parsed() -> None:
    request = SimpleNamespace(
        headers=Headers({"X-LogosForge-Drafter-Order-Floor": "17"})
    )
    assert request_delete_order_floors(request) == {"drafter": 17}


def test_document_cleanup_and_reused_id_clear_drafter_generations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc_id = "940103"
    drafter = DrafterPagesStore(tmp_path)
    initial = drafter.get_document(doc_id)
    current = drafter.replace_document(
        doc_id, [_page()], expected_revision=initial.revision
    )
    drafter.replace_document(
        doc_id, [_page("second")], expected_revision=current.revision
    )
    assert (tmp_path / "drafter" / f"{doc_id}.json.bak").exists()

    empty = _EmptyStore()
    monkeypatch.setattr(documents_router, "whiteboard_store", empty)
    monkeypatch.setattr(documents_router, "outline_items_store", empty)
    monkeypatch.setattr(documents_router, "comments_store", empty)
    monkeypatch.setattr(documents_router, "psyke_revision_store", empty)
    monkeypatch.setattr(documents_router, "drafter_pages_store", drafter)
    assert documents_router._local_document_ids() == {doc_id}

    assert documents_router._cleanup_local_document_state(doc_id) == []
    assert not list((tmp_path / "drafter").glob(f"{doc_id}.json*"))

    # The lower-level allocation cleanup uses the same Drafter namespace before
    # a reused core numeric id receives its fresh document incarnation.
    drafter.get_document(doc_id)
    monkeypatch.setattr(lifecycle, "whiteboard_store", empty)
    monkeypatch.setattr(lifecycle, "outline_items_store", empty)
    monkeypatch.setattr(lifecycle, "comments_store", empty)
    monkeypatch.setattr(lifecycle, "psyke_revision_store", empty)
    monkeypatch.setattr(lifecycle, "drafter_pages_store", drafter)
    assert lifecycle._clear_allocated_document_state(doc_id) == []
    assert not list((tmp_path / "drafter").glob(f"{doc_id}.json*"))


def test_page_level_store_create_patch_and_exact_retries(tmp_path: Path) -> None:
    store = DrafterPagesStore(tmp_path)
    initial = store.get_document("7")
    page = _page(text="Keep this large body out of title-only responses.")

    created = store.create_page(
        "7",
        page,
        expected_revision=initial.revision,
        mutation_id="create-page-1",
    )
    retry = store.create_page(
        "7",
        page,
        expected_revision=initial.revision,
        mutation_id="create-page-1",
    )
    assert retry == created
    assert created.page.block_count == 1
    assert created.page.character_count == len(page.blocks[0].text)
    with pytest.raises(DrafterPageAlreadyExists):
        store.create_page(
            "7",
            page,
            expected_revision=created.revision,
            mutation_id="create-page-duplicate",
        )

    patched = store.patch_page(
        "7",
        page.id,
        DrafterPagePatch(title="A better experiment"),
        expected_revision=created.revision,
        mutation_id="patch-page-1",
    )
    patch_retry = store.patch_page(
        "7",
        page.id,
        DrafterPagePatch(title="A better experiment"),
        expected_revision=created.revision,
        mutation_id="patch-page-1",
    )
    assert patch_retry == patched
    saved = store.get_document("7").pages[0]
    assert saved.title == "A better experiment"
    assert saved.blocks == page.blocks
    assert saved.created_at == page.created_at
    assert saved.updated_at != page.updated_at
    with pytest.raises(MutationIdConflict):
        store.patch_page(
            "7",
            page.id,
            DrafterPagePatch(title="Different retry"),
            expected_revision=created.revision,
            mutation_id="patch-page-1",
        )
    with pytest.raises(ResourceRevisionConflict):
        store.patch_page(
            "7",
            page.id,
            DrafterPagePatch(title="Stale"),
            expected_revision=created.revision,
            mutation_id="patch-page-stale",
        )
    replacement_blocks = [WhiteboardBlock(id="replacement", text="New body")]
    replaced = store.patch_page(
        "7",
        page.id,
        DrafterPagePatch(blocks=replacement_blocks),
        expected_revision=patched.revision,
        mutation_id="patch-page-blocks",
    )
    assert replaced.page.block_count == 1
    assert store.get_document("7").pages[0].blocks == replacement_blocks


def test_bounded_page_index_and_resumable_page_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = 940105
    manuscripts = WhiteboardStore(tmp_path)
    manuscript = manuscripts.create(str(project_id), WhiteboardCreate(title="Drafts"))
    drafter = DrafterPagesStore(tmp_path)
    first = DrafterPage(
        id="scene-a",
        title="Scene A",
        blocks=[
            WhiteboardBlock(
                id="b-1",
                text="abc",
                marks=[{"type": "bold", "from": 0, "to": 2}],
            ),
            WhiteboardBlock(
                id="b-2",
                text="defgh",
                marks=[{"type": "italic", "from": 1, "to": 4}],
            ),
        ],
        created_at="2026-09-26T08:00:00Z",
        updated_at="2026-09-26T08:00:00Z",
    )
    initial = drafter.get_document(str(project_id))
    saved = drafter.replace_document(
        str(project_id),
        [first, _page("scene-b", "No match here.")],
        expected_revision=initial.revision,
    )
    _install_stores(monkeypatch, manuscripts, drafter)
    core = _Core(project_id)

    index_response = Response()
    index = asyncio.run(drafter_router.get_drafter_page_index(
        _request(core), index_response, project_id
    ))
    assert index.page_count == 2
    assert index.revision == saved.revision
    assert index.pages[0].model_dump() == {
        "id": "scene-a",
        "title": "Scene A",
        "created_at": "2026-09-26T08:00:00Z",
        "updated_at": "2026-09-26T08:00:00Z",
        "block_count": 2,
        "character_count": 8,
    }
    assert "blocks" not in index.model_dump()["pages"][0]
    assert index_response.headers["etag"] == resource_etag(
        "drafter", manuscript.incarnation, saved.revision
    )

    page_response = Response()
    excerpt = asyncio.run(drafter_router.get_drafter_page(
        _request(core), page_response, "scene-a", project_id, 0, 10, 5, 0
    ))
    assert [item.block.text for item in excerpt.blocks] == ["abc", "de"]
    assert excerpt.blocks[0].complete is True
    assert excerpt.blocks[0].block.marks == first.blocks[0].marks
    assert excerpt.blocks[1].complete is False
    assert excerpt.blocks[1].marks_omitted is True
    assert excerpt.blocks[1].block.marks is None
    assert excerpt.pagination.next_offset == 1
    assert excerpt.pagination.next_text_offset == 2
    assert excerpt.pagination.truncated is True

    resumed = asyncio.run(drafter_router.get_drafter_page(
        _request(core), Response(), "scene-a", project_id, 1, 10, 5, 2
    ))
    assert [item.block.text for item in resumed.blocks] == ["fgh"]
    assert resumed.blocks[0].text_offset == 2
    assert resumed.blocks[0].marks_omitted is True
    assert resumed.pagination.next_offset is None
    assert resumed.pagination.truncated is False

    with pytest.raises(HTTPException) as invalid_range:
        asyncio.run(drafter_router.get_drafter_page(
            _request(core), Response(), "scene-a", project_id, 1, 10, 5, 99
        ))
    assert invalid_range.value.status_code == 416


def test_bounded_drafter_search_reports_exact_total_matches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = 940106
    manuscripts = WhiteboardStore(tmp_path)
    manuscript = manuscripts.create(str(project_id), WhiteboardCreate())
    drafter = DrafterPagesStore(tmp_path)
    pages = [
        DrafterPage(
            id="needle-page",
            title="Needle planning",
            blocks=[
                WhiteboardBlock(id="b-1", text="x" * 80 + " NEEDLE " + "y" * 80),
                WhiteboardBlock(id="b-2", text="No match."),
            ],
            created_at="2026-09-26T08:00:00Z",
            updated_at="2026-09-26T08:00:00Z",
        ),
        _page("second-page", "A second needle is here."),
    ]
    initial = drafter.get_document(str(project_id))
    saved = drafter.replace_document(
        str(project_id), pages, expected_revision=initial.revision
    )
    _install_stores(monkeypatch, manuscripts, drafter)

    response = Response()
    result = asyncio.run(drafter_router.search_drafter_pages(
        _request(_Core(project_id)), response, project_id, "needle", 2, 40
    ))
    assert result.total_matches == 3
    assert len(result.results) == 2
    assert result.truncated is True
    assert [item.match_scope for item in result.results] == ["title", "block"]
    assert all(len(item.snippet) <= 40 for item in result.results)
    assert result.revision == saved.revision
    assert result.page_count == 2
    assert response.headers["etag"] == resource_etag(
        "drafter", manuscript.incarnation, saved.revision
    )


def test_conditional_page_routes_return_only_summary_and_enforce_revisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = 940107
    manuscripts = WhiteboardStore(tmp_path)
    manuscript = manuscripts.create(str(project_id), WhiteboardCreate())
    drafter = DrafterPagesStore(tmp_path)
    initial = drafter.get_document(str(project_id))
    _install_stores(monkeypatch, manuscripts, drafter)
    core = _Core(project_id)
    initial_etag = resource_etag(
        "drafter", manuscript.incarnation, initial.revision
    )
    page = _page(text="Body that must not be returned by a mutation.")

    create_response = Response()
    created = asyncio.run(drafter_router.create_drafter_page(
        _request(core, _headers(
            manuscript.incarnation,
            etag=initial_etag,
            mutation_id="page-route-create",
        )),
        create_response,
        page,
        project_id,
    ))
    assert "blocks" not in created.page.model_dump()
    assert created.page_count == 1
    assert create_response.headers["etag"] == resource_etag(
        "drafter", manuscript.incarnation, created.revision
    )

    retry = asyncio.run(drafter_router.create_drafter_page(
        _request(core, _headers(
            manuscript.incarnation,
            etag=initial_etag,
            mutation_id="page-route-create",
        )),
        Response(),
        page,
        project_id,
    ))
    assert retry == created

    with pytest.raises(HTTPException) as duplicate:
        asyncio.run(drafter_router.create_drafter_page(
            _request(core, _headers(
                manuscript.incarnation,
                etag=resource_etag(
                    "drafter", manuscript.incarnation, created.revision
                ),
                mutation_id="page-route-duplicate",
            )),
            Response(),
            page,
            project_id,
        ))
    assert duplicate.value.status_code == 409
    assert duplicate.value.detail["code"] == "drafter_page_already_exists"

    patched = asyncio.run(drafter_router.patch_drafter_page(
        _request(core, _headers(
            manuscript.incarnation,
            etag=resource_etag("drafter", manuscript.incarnation, created.revision),
            mutation_id="page-route-patch",
        )),
        Response(),
        page.id,
        DrafterPagePatch(title="Renamed"),
        project_id,
    ))
    assert patched.page.title == "Renamed"
    assert "blocks" not in patched.page.model_dump()
    assert drafter.get_document(str(project_id)).pages[0].blocks == page.blocks

    replacement_blocks = [WhiteboardBlock(id="replacement", text="Replacement body")]
    blocks_patched = asyncio.run(drafter_router.patch_drafter_page(
        _request(core, _headers(
            manuscript.incarnation,
            etag=resource_etag("drafter", manuscript.incarnation, patched.revision),
            mutation_id="page-route-block-patch",
        )),
        Response(),
        page.id,
        DrafterPagePatch(blocks=replacement_blocks),
        project_id,
    ))
    assert blocks_patched.page.character_count == len("Replacement body")
    assert drafter.get_document(str(project_id)).pages[0].blocks == replacement_blocks

    with pytest.raises(HTTPException) as stale:
        asyncio.run(drafter_router.patch_drafter_page(
            _request(core, _headers(
                manuscript.incarnation,
                etag=resource_etag(
                    "drafter", manuscript.incarnation, created.revision
                ),
                mutation_id="page-route-stale",
            )),
            Response(),
            page.id,
            DrafterPagePatch(title="Stale"),
            project_id,
        ))
    assert stale.value.status_code == 409
    assert stale.value.detail["code"] == "revision_conflict"

    with pytest.raises(HTTPException) as missing:
        asyncio.run(drafter_router.patch_drafter_page(
            _request(core, _headers(
                manuscript.incarnation,
                etag=resource_etag(
                    "drafter", manuscript.incarnation, blocks_patched.revision
                ),
                mutation_id="page-route-missing",
            )),
            Response(),
            "missing",
            DrafterPagePatch(title="Missing"),
            project_id,
        ))
    assert missing.value.status_code == 404
    assert missing.value.detail["code"] == "drafter_page_not_found"

    with pytest.raises(HTTPException) as missing_mutation_id:
        asyncio.run(drafter_router.create_drafter_page(
            _request(core, _headers(
                manuscript.incarnation,
                etag=resource_etag(
                    "drafter", manuscript.incarnation, blocks_patched.revision
                ),
            )),
            Response(),
            _page("another-page"),
            project_id,
        ))
    assert missing_mutation_id.value.status_code == 428
    assert missing_mutation_id.value.detail["code"] == "mutation_id_required"


def test_page_create_collection_limit_is_a_controlled_422(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = 940108
    manuscripts = WhiteboardStore(tmp_path)
    manuscript = manuscripts.create(str(project_id), WhiteboardCreate())
    drafter = DrafterPagesStore(tmp_path)
    initial = drafter.get_document(str(project_id))
    full = drafter.replace_document(
        str(project_id),
        [_page(f"page-{index}", "") for index in range(256)],
        expected_revision=initial.revision,
    )
    _install_stores(monkeypatch, manuscripts, drafter)

    with pytest.raises(HTTPException) as over_limit:
        asyncio.run(drafter_router.create_drafter_page(
            _request(_Core(project_id), _headers(
                manuscript.incarnation,
                etag=resource_etag("drafter", manuscript.incarnation, full.revision),
                mutation_id="page-route-over-limit",
            )),
            Response(),
            _page("page-257", ""),
            project_id,
        ))
    assert over_limit.value.status_code == 422
    assert over_limit.value.detail["code"] == "drafter_limits_exceeded"
    assert drafter.get_document(str(project_id)) == full


def test_patch_oversize_body_is_rejected_as_http_422(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = 940109
    manuscripts = WhiteboardStore(tmp_path)
    manuscript = manuscripts.create(str(project_id), WhiteboardCreate())
    drafter = DrafterPagesStore(tmp_path)
    initial = drafter.get_document(str(project_id))
    saved = drafter.replace_document(
        str(project_id), [_page()], expected_revision=initial.revision
    )
    _install_stores(monkeypatch, manuscripts, drafter)
    route_app = FastAPI()
    route_app.state.core = _Core(project_id)
    route_app.include_router(drafter_router.router)

    with TestClient(route_app) as client:
        response = client.patch(
            f"/api/drafter/pages/page-1?doc={project_id}",
            headers=_headers(
                manuscript.incarnation,
                etag=resource_etag(
                    "drafter", manuscript.incarnation, saved.revision
                ),
                mutation_id="oversize-body",
            ),
            json={
                "blocks": [
                    {"id": f"b-{index}", "type": "paragraph", "text": ""}
                    for index in range(20_001)
                ]
            },
        )
    assert response.status_code == 422
    assert drafter.get_document(str(project_id)) == saved
