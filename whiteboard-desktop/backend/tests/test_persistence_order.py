from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.routers import documents as documents_router
from app.persistence_order import (
    accept_persistence_write,
    begin_document_delete,
    cancel_document_delete,
    create_document_incarnation,
)


def test_older_timed_out_request_cannot_overwrite_a_newer_dispatch() -> None:
    doc_id = "910001"
    saved: list[str] = []

    # Model the newer request reaching the actual store boundary first.
    with accept_persistence_write("whiteboard", doc_id, 2) as accepted:
        assert accepted
        saved.append("new")
    with accept_persistence_write("whiteboard", doc_id, 1) as accepted:
        assert not accepted
        if accepted:
            saved.append("old")

    assert saved == ["new"]


def test_failed_store_write_rolls_back_order_for_retry() -> None:
    doc_id = "910002"
    with pytest.raises(OSError):
        with accept_persistence_write("outline", doc_id, 7) as accepted:
            assert accepted
            raise OSError("disk full")
    with accept_persistence_write("outline", doc_id, 7) as accepted:
        assert accepted


def test_delete_tombstone_blocks_old_write_and_reused_id_keeps_watermark() -> None:
    doc_id = "910003"
    with accept_persistence_write("whiteboard", doc_id, 4) as accepted:
        assert accepted
    begin_document_delete(doc_id)
    with accept_persistence_write("whiteboard", doc_id, 5) as accepted:
        assert not accepted

    with create_document_incarnation(doc_id):
        pass
    with accept_persistence_write("whiteboard", doc_id, 4) as accepted:
        assert not accepted
    with accept_persistence_write("whiteboard", doc_id, 6) as accepted:
        assert accepted


def test_delete_floor_rejects_issued_request_that_reaches_gate_after_id_reuse() -> None:
    doc_id = "910005"
    # Order 8 was issued by main but is still stalled in resolve_pid, so the
    # backend has never observed it at the store gate when DELETE starts.
    begin_document_delete(doc_id, {"whiteboard": 8, "outline": 3})
    with create_document_incarnation(doc_id):
        pass
    with accept_persistence_write("whiteboard", doc_id, 8) as accepted:
        assert not accepted
    with accept_persistence_write("outline", doc_id, 3) as accepted:
        assert not accepted
    with accept_persistence_write("whiteboard", doc_id, 9) as accepted:
        assert accepted


def test_failed_delete_reopens_document_for_retained_write() -> None:
    doc_id = "910004"
    begin_document_delete(doc_id)
    cancel_document_delete(doc_id)
    with accept_persistence_write("whiteboard", doc_id, 1) as accepted:
        assert accepted


def test_existence_reconciliation_waits_for_an_accepted_delete(monkeypatch) -> None:
    class Store:
        def delete(self, _doc_id: str) -> None:
            pass

        def list_document_ids(self) -> set[str]:
            return set()

    class Core:
        def __init__(self) -> None:
            self.projects = [{"id": 910006}]
            self.delete_started = asyncio.Event()
            self.finish_delete = asyncio.Event()

        async def delete_project(self, _doc_id: int) -> None:
            self.delete_started.set()
            await self.finish_delete.wait()
            self.projects = []

        async def list_projects(self) -> list[dict[str, int]]:
            return list(self.projects)

    async def scenario() -> None:
        core = Core()
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(core=core)),
            headers={},
        )
        deleting = asyncio.create_task(documents_router.delete_document(request, 910006))
        await core.delete_started.wait()
        reconciling = asyncio.create_task(documents_router.document_exists(request, 910006))
        await asyncio.sleep(0)
        assert not reconciling.done()
        core.finish_delete.set()
        await deleting
        assert await reconciling == {"exists": False}

    store = Store()
    monkeypatch.setattr(documents_router, "whiteboard_store", store)
    monkeypatch.setattr(documents_router, "outline_items_store", store)
    monkeypatch.setattr(documents_router, "comments_store", store)
    async def matching_incarnation(_request, _document_id: str) -> bool:
        return True
    monkeypatch.setattr(documents_router, "validate_delete_incarnation", matching_incarnation)
    asyncio.run(scenario())
