from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.document_lifecycle as lifecycle
from app.routers import documents as documents_router
from app.routers import littleboy as littleboy_router
from app.routers import psyke as psyke_router
from app.routers import settings as settings_router
from app.document_lifecycle import (
    DOCUMENT_INCARNATION_HEADER,
    document_identity_publication,
    document_lifecycle_lock,
    locked_document_request,
    request_document_incarnation,
)
from app.local_state import WhiteboardCreate, WhiteboardStore, WhiteboardUpdate


class _Core:
    def __init__(self, project_id: int) -> None:
        self.project_id = project_id
        self.calls: list[tuple[str, str]] = []
        self.deleted: list[int] = []

    async def ensure_project(self) -> int:
        return self.project_id

    async def ensure_project_with_status(self) -> tuple[int, bool]:
        return self.project_id, False

    async def request(self, method: str, path: str, **_kwargs):
        self.calls.append((method, path))
        return SimpleNamespace()

    async def list_projects(self) -> list[dict[str, int]]:
        return [{"id": self.project_id}]

    async def delete_project(self, project_id: int) -> None:
        self.deleted.append(project_id)


class _IncarnationStore:
    def __init__(self, incarnation: str) -> None:
        self.incarnation = incarnation

    def ensure_incarnation(self, _document_id: str) -> str:
        return self.incarnation

    def exists(self, _document_id: str) -> bool:
        return True


class _EmptyLocalStore:
    def list_document_ids(self) -> set[str]:
        return set()

    def delete(self, _document_id: str) -> None:
        pass


@pytest.fixture(autouse=True)
def _isolate_psyke_revision_cleanup(monkeypatch):
    store = _EmptyLocalStore()
    monkeypatch.setattr(lifecycle, "psyke_revision_store", store)
    monkeypatch.setattr(documents_router, "psyke_revision_store", store)


def _request(core: _Core, incarnation: str | None = None):
    headers = {} if incarnation is None else {DOCUMENT_INCARNATION_HEADER: incarnation}
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(core=core)),
        headers=headers,
    )


def test_whiteboard_incarnation_is_durable_and_rotates_on_id_reuse(tmp_path: Path) -> None:
    store = WhiteboardStore(tmp_path)
    original = store.create("42", WhiteboardCreate(title="Original"))
    assert len(original.incarnation) == 32

    updated = store.update("42", WhiteboardUpdate(title="Updated"))
    assert updated.incarnation == original.incarnation
    assert store.get("42").incarnation == original.incarnation

    store.delete("42")
    replacement = store.create("42", WhiteboardCreate(title="Replacement"))
    assert replacement.incarnation != original.incarnation


def test_legacy_document_gets_one_persisted_incarnation(tmp_path: Path) -> None:
    store = WhiteboardStore(tmp_path)
    path = tmp_path / "whiteboards" / "42.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"id":"42","title":"Legacy","mode":"novel","blocks":[],"settings":{},'
        '"updated_at":"2026-01-01T00:00:00+00:00"}',
        encoding="utf-8",
    )

    first = store.ensure_incarnation("42")
    second = store.ensure_incarnation("42")
    assert first == second == store.get("42").incarnation


def test_document_list_does_not_materialize_core_only_projects(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_id = 991046
    store = WhiteboardStore(tmp_path)
    monkeypatch.setattr(documents_router, "whiteboard_store", store)
    monkeypatch.setattr(documents_router, "outline_items_store", _EmptyLocalStore())
    monkeypatch.setattr(documents_router, "comments_store", _EmptyLocalStore())

    result = asyncio.run(documents_router.list_documents(_request(_Core(project_id))))

    assert result == {"documents": []}
    assert not (tmp_path / "whiteboards" / f"{project_id}.json").exists()


def test_invalid_incarnation_header_is_rejected() -> None:
    with pytest.raises(HTTPException) as caught:
        request_document_incarnation(_request(_Core(42), "not-a-token"))
    assert caught.value.status_code == 400


def test_explicit_document_mutation_requires_incarnation_header() -> None:
    core = _Core(991047)

    async def scenario() -> None:
        async with locked_document_request(
            _request(core),
            core.project_id,
            mutation=True,
        ):
            raise AssertionError("headerless explicit mutation crossed the lifecycle fence")

    with pytest.raises(HTTPException) as caught:
        asyncio.run(scenario())

    assert caught.value.status_code == 428
    assert core.calls == [("GET", f"/api/projects/{core.project_id}")]


def test_document_delete_requires_incarnation_header() -> None:
    core = _Core(991048)

    with pytest.raises(HTTPException) as caught:
        asyncio.run(documents_router.delete_document(_request(core), core.project_id))

    assert caught.value.status_code == 428
    assert core.deleted == []


def test_queued_old_incarnation_is_rejected_after_numeric_id_reuse(monkeypatch) -> None:
    old = "1" * 32
    new = "2" * 32
    core = _Core(991042)
    store = _IncarnationStore(old)
    monkeypatch.setattr(lifecycle, "whiteboard_store", store)

    async def scenario() -> None:
        gate = document_lifecycle_lock(str(core.project_id))
        await gate.acquire()

        async def delayed_old_mutation() -> None:
            async with locked_document_request(_request(core, old), core.project_id):
                raise AssertionError("stale mutation crossed the incarnation fence")

        delayed = asyncio.create_task(delayed_old_mutation())
        await asyncio.sleep(0)
        assert not delayed.done()

        # Model DELETE + CREATE reusing the same numeric id while the old request
        # is queued at the shared backend lifecycle boundary.
        store.incarnation = new
        gate.release()
        with pytest.raises(HTTPException) as caught:
            await delayed
        assert caught.value.status_code == 409

        async with locked_document_request(_request(core, new), core.project_id) as locked:
            assert locked.document_id == str(core.project_id)
            assert locked.incarnation == new

    asyncio.run(scenario())


def test_existence_reconciliation_does_not_confuse_reused_id_for_old_document(
    monkeypatch,
) -> None:
    old = "3" * 32
    new = "4" * 32
    core = _Core(991043)
    store = _IncarnationStore(new)
    monkeypatch.setattr(documents_router, "whiteboard_store", store)

    result = asyncio.run(
        documents_router.document_exists(_request(core, old), core.project_id),
    )
    assert result == {"exists": False}


def test_existence_reconciliation_does_not_materialize_core_only_reuse(
    tmp_path: Path,
    monkeypatch,
) -> None:
    document_id = 991055
    store = WhiteboardStore(tmp_path)
    monkeypatch.setattr(documents_router, "whiteboard_store", store)

    result = asyncio.run(
        documents_router.document_exists(
            _request(_Core(document_id), "d" * 32),
            document_id,
        )
    )

    assert result == {"exists": False}
    assert not store.exists(str(document_id))


def test_stale_delete_cannot_delete_reused_numeric_id(monkeypatch) -> None:
    old = "5" * 32
    new = "6" * 32
    core = _Core(991044)
    monkeypatch.setattr(lifecycle, "whiteboard_store", _IncarnationStore(new))

    with pytest.raises(HTTPException) as caught:
        asyncio.run(documents_router.delete_document(_request(core, old), core.project_id))

    assert caught.value.status_code == 409
    assert core.deleted == []


def test_psyke_mutation_validates_incarnation_before_core_write(monkeypatch) -> None:
    old = "7" * 32
    new = "8" * 32
    core = _Core(991045)
    monkeypatch.setattr(lifecycle, "whiteboard_store", _IncarnationStore(new))

    with pytest.raises(HTTPException) as caught:
        asyncio.run(
            psyke_router.create_element(
                _request(core, old),
                psyke_router.PsykeElementCreate(name="Delayed"),
                core.project_id,
            ),
        )

    assert caught.value.status_code == 409
    assert core.calls == [("GET", f"/api/projects/{core.project_id}")]


def test_explicit_littleboy_requests_require_document_incarnation() -> None:
    core = _Core(991049)
    request = _request(core)

    with pytest.raises(HTTPException) as billy_caught:
        asyncio.run(
            littleboy_router.billy_chat(
                request,
                littleboy_router.BillyChatRequest(message="Help"),
                core.project_id,
            ),
        )
    assert billy_caught.value.status_code == 428

    core.calls.clear()
    with pytest.raises(HTTPException) as logos_caught:
        asyncio.run(
            littleboy_router.logos_inline(
                request,
                littleboy_router.LogosRequest(action="rewrite"),
                core.project_id,
            ),
        )
    assert logos_caught.value.status_code == 428
    assert core.calls == [("GET", f"/api/projects/{core.project_id}")]


def test_queued_old_littleboy_request_cannot_cross_id_reuse(monkeypatch) -> None:
    old = "9" * 32
    new = "a" * 32
    core = _Core(991050)
    store = _IncarnationStore(old)
    monkeypatch.setattr(lifecycle, "whiteboard_store", store)

    async def scenario() -> None:
        gate = document_lifecycle_lock(str(core.project_id))
        await gate.acquire()
        delayed = asyncio.create_task(
            littleboy_router.billy_chat(
                _request(core, old),
                littleboy_router.BillyChatRequest(message="Old request"),
                core.project_id,
            ),
        )
        await asyncio.sleep(0)
        assert not delayed.done()

        # DELETE + CREATE reused the id before the already-received request got
        # its turn at the authoritative lifecycle boundary.
        store.incarnation = new
        gate.release()
        with pytest.raises(HTTPException) as caught:
            await delayed
        assert caught.value.status_code == 409

    asyncio.run(scenario())
    assert core.calls == [("GET", f"/api/projects/{core.project_id}")]


def test_littleboy_holds_lifecycle_lock_through_long_response(monkeypatch) -> None:
    old = "b" * 32
    new = "c" * 32
    project_id = 991051
    store = _IncarnationStore(old)
    monkeypatch.setattr(lifecycle, "whiteboard_store", store)

    class _Response:
        def __init__(self, data: dict) -> None:
            self.data = data

        def json(self) -> dict:
            return self.data

    class _LongCore(_Core):
        def __init__(self) -> None:
            super().__init__(project_id)
            self.ai_started = asyncio.Event()
            self.release_ai = asyncio.Event()

        async def request(self, method: str, path: str, **_kwargs):
            self.calls.append((method, path))
            if method == "POST" and path.endswith("/assistant/chat"):
                self.ai_started.set()
                await self.release_ai.wait()
                return _Response({"reply": "old document answer"})
            if method == "GET" and path.endswith("/assistant/settings"):
                return _Response({"provider": "test"})
            return _Response({})

    async def scenario() -> None:
        core = _LongCore()
        request_task = asyncio.create_task(
            littleboy_router.billy_chat(
                _request(core, old),
                littleboy_router.BillyChatRequest(message="Wait for it"),
                project_id,
            ),
        )
        await core.ai_started.wait()

        replacement_entered = asyncio.Event()

        async def delete_and_reuse() -> None:
            async with document_lifecycle_lock(str(project_id)):
                replacement_entered.set()
                store.incarnation = new

        replacement = asyncio.create_task(delete_and_reuse())
        await asyncio.sleep(0)
        assert not replacement_entered.is_set()

        core.release_ai.set()
        response = await request_task
        assert response.message.content == "old document answer"
        await replacement
        assert replacement_entered.is_set()
        assert store.incarnation == new

    asyncio.run(scenario())


def test_reused_id_is_not_visible_to_stale_request_before_new_incarnation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A stale request cannot enter after core allocation but before token rotation."""
    document_id = 991049
    store = WhiteboardStore(tmp_path)
    original = store.create(str(document_id), WhiteboardCreate(title="Deleted document"))

    class ReusingCore(_Core):
        def __init__(self) -> None:
            super().__init__(document_id)
            self.allocated = asyncio.Event()
            self.publish = asyncio.Event()

        async def create_project(self, _title: str) -> dict[str, int]:
            # Model SQLite reusing an id while the old local file still carries
            # the deleted document's incarnation (cleanup failure/process loss).
            self.allocated.set()
            await self.publish.wait()
            return {"id": self.project_id}

    core = ReusingCore()
    empty_store = _EmptyLocalStore()
    monkeypatch.setattr(lifecycle, "whiteboard_store", store)
    monkeypatch.setattr(documents_router, "whiteboard_store", store)
    monkeypatch.setattr(documents_router, "outline_items_store", empty_store)
    monkeypatch.setattr(documents_router, "comments_store", empty_store)

    async def scenario() -> None:
        creating = asyncio.create_task(
            documents_router.create_document(
                _request(core),
                WhiteboardCreate(title="Replacement"),
            )
        )
        await core.allocated.wait()

        crossed = False

        async def stale_request() -> None:
            nonlocal crossed
            async with locked_document_request(
                _request(core, original.incarnation),
                document_id,
                mutation=True,
            ):
                crossed = True

        stale = asyncio.create_task(stale_request())
        stale_delete = asyncio.create_task(
            documents_router.delete_document(
                _request(core, original.incarnation),
                document_id,
            )
        )
        await asyncio.sleep(0)
        assert not stale.done()
        assert not stale_delete.done()
        assert not crossed

        core.publish.set()
        created = await creating
        assert created["document"]["incarnation"] != original.incarnation

        with pytest.raises(HTTPException) as caught:
            await stale
        assert caught.value.status_code == 409
        with pytest.raises(HTTPException) as delete_caught:
            await stale_delete
        assert delete_caught.value.status_code == 409
        assert core.deleted == []
        assert not crossed

    asyncio.run(scenario())


def test_cancelled_create_settles_reused_allocation_before_publication_gate_opens(
    tmp_path: Path,
    monkeypatch,
) -> None:
    document_id = 991052
    store = WhiteboardStore(tmp_path)
    original = store.create(str(document_id), WhiteboardCreate(title="Old identity"))

    class ReusingCore(_Core):
        def __init__(self) -> None:
            super().__init__(document_id)
            self.allocated = asyncio.Event()

        async def create_project(self, _title: str) -> dict[str, int]:
            self.allocated.set()
            return {"id": self.project_id}

    core = ReusingCore()
    empty_store = _EmptyLocalStore()
    monkeypatch.setattr(lifecycle, "whiteboard_store", store)
    monkeypatch.setattr(documents_router, "whiteboard_store", store)
    monkeypatch.setattr(documents_router, "outline_items_store", empty_store)
    monkeypatch.setattr(documents_router, "comments_store", empty_store)

    async def scenario() -> None:
        id_lock = document_lifecycle_lock(str(document_id))
        await id_lock.acquire()
        creating = asyncio.create_task(
            documents_router.create_document(
                _request(core),
                WhiteboardCreate(title="Cancelled replacement"),
            )
        )
        await core.allocated.wait()
        await asyncio.sleep(0)
        assert not creating.done()

        creating.cancel()
        await asyncio.sleep(0)
        assert not creating.done(), "cancellation exposed the allocation before compensation"

        observed_after_settlement = False

        async def observe_publication_boundary() -> None:
            nonlocal observed_after_settlement
            async with document_identity_publication():
                assert core.deleted == [document_id]
                assert not store.exists(str(document_id))
                observed_after_settlement = True

        observer = asyncio.create_task(observe_publication_boundary())
        await asyncio.sleep(0)
        assert not observer.done()

        id_lock.release()
        with pytest.raises(asyncio.CancelledError):
            await creating
        await observer
        assert observed_after_settlement
        assert original.incarnation

    asyncio.run(scenario())


def test_settings_default_allocation_rotates_reused_identity_before_visibility(
    tmp_path: Path,
    monkeypatch,
) -> None:
    document_id = 991053
    store = WhiteboardStore(tmp_path)
    original = store.create(str(document_id), WhiteboardCreate(title="Deleted default"))

    class AllocatingCore(_Core):
        def __init__(self) -> None:
            super().__init__(document_id)
            self.allocated = asyncio.Event()
            self.finish_allocation = asyncio.Event()

        async def ensure_project_with_status(self) -> tuple[int, bool]:
            self.allocated.set()
            await self.finish_allocation.wait()
            return self.project_id, True

        async def request(self, method: str, path: str, **_kwargs):
            self.calls.append((method, path))
            return SimpleNamespace(
                json=lambda: {
                    "provider": "",
                    "model": "",
                    "base_url": "",
                    "timeout": 0,
                }
            )

    core = AllocatingCore()
    empty_store = _EmptyLocalStore()
    monkeypatch.setattr(lifecycle, "whiteboard_store", store)
    monkeypatch.setattr(lifecycle, "outline_items_store", empty_store)
    monkeypatch.setattr(lifecycle, "comments_store", empty_store)

    async def scenario() -> None:
        settings = asyncio.create_task(settings_router.get_ai_settings(_request(core)))
        await core.allocated.wait()

        crossed = False

        async def stale_request() -> None:
            nonlocal crossed
            async with locked_document_request(
                _request(core, original.incarnation),
                document_id,
                mutation=True,
            ):
                crossed = True

        stale = asyncio.create_task(stale_request())
        await asyncio.sleep(0)
        assert not stale.done()
        assert not crossed

        core.finish_allocation.set()
        result = await settings
        assert result.provider == ""
        replacement = store.get(str(document_id))
        assert replacement.incarnation != original.incarnation

        with pytest.raises(HTTPException) as caught:
            await stale
        assert caught.value.status_code == 409
        assert not crossed

    asyncio.run(scenario())


def test_settings_does_not_materialize_existing_core_only_project(
    tmp_path: Path,
    monkeypatch,
) -> None:
    document_id = 991054
    store = WhiteboardStore(tmp_path)

    class ExistingCore(_Core):
        async def request(self, method: str, path: str, **_kwargs):
            self.calls.append((method, path))
            return SimpleNamespace(json=lambda: {})

    core = ExistingCore(document_id)
    monkeypatch.setattr(lifecycle, "whiteboard_store", store)

    result = asyncio.run(settings_router.get_ai_settings(_request(core)))

    assert result.provider == ""
    assert not store.exists(str(document_id))
