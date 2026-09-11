"""Regression tests for Whiteboard's protected local JSON persistence."""
from __future__ import annotations

import asyncio
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException


_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.local_state import (  # noqa: E402
    CommentAnchor,
    CommentCreate,
    CommentReplyCreate,
    CommentUpdate,
    CommentsStore,
    LocalStateCorruptionError,
    LocalStateIOError,
    OutlineItemsStore,
    WhiteboardCreate,
    WhiteboardStore,
    WhiteboardUpdate,
    consume_recovery_notices,
)
import app.local_state as local_state  # noqa: E402
from app.routers.export import _list_psyke  # noqa: E402
from app.routers import documents as documents_router  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_recovery_notices():
    consume_recovery_notices()
    documents_router._pending_local_cleanup.clear()
    yield
    consume_recovery_notices()
    documents_router._pending_local_cleanup.clear()


def _title(path: Path) -> str:
    return str(json.loads(path.read_text(encoding="utf-8"))["title"])


def test_manuscript_save_rotates_two_valid_backups(tmp_path: Path) -> None:
    store = WhiteboardStore(tmp_path)
    store.create("7", WhiteboardCreate(title="First"))
    store.update("7", WhiteboardUpdate(title="Second"))
    store.update("7", WhiteboardUpdate(title="Third"))

    current = tmp_path / "whiteboards" / "7.json"
    assert _title(current) == "Third"
    assert _title(current.with_name("7.json.bak")) == "Second"
    assert _title(current.with_name("7.json.bak.1")) == "First"
    assert not list(current.parent.glob("*.tmp"))


def test_whiteboard_partial_updates_preserve_project_settings(tmp_path: Path) -> None:
    store = WhiteboardStore(tmp_path)
    store.create(
        "7",
        WhiteboardCreate(
            title="Story",
            mode="novel",
            blocks=[{"id": "b1", "type": "paragraph", "text": "Draft"}],
            settings={"narrativePerson": "first", "slangLevel": "light"},
        ),
    )

    store.update("7", WhiteboardUpdate(mode="screenplay"))
    after_mode = store.update(
        "7",
        WhiteboardUpdate(blocks=[{"id": "b1", "type": "paragraph", "text": "Revised"}]),
    )
    assert after_mode.settings == {"narrativePerson": "first", "slangLevel": "light"}
    assert after_mode.mode == "screenplay"

    after_settings = store.update(
        "7",
        WhiteboardUpdate(settings={"narrativePerson": "third-limited"}),
    )
    assert after_settings.blocks[0].text == "Revised"
    assert after_settings.mode == "screenplay"
    assert after_settings.settings == {"narrativePerson": "third-limited"}


def test_read_modify_write_methods_hold_the_store_lock(tmp_path: Path, monkeypatch) -> None:
    """The outer lock must cover _load through _save, not only each file syscall."""
    whiteboard = WhiteboardStore(tmp_path)
    whiteboard.create("7", WhiteboardCreate(title="Story"))
    wb_load = whiteboard._load
    wb_lock_observed: list[bool] = []

    def checked_whiteboard_load(doc_id: str):
        wb_lock_observed.append(local_state._STATE_LOCK._is_owned())
        return wb_load(doc_id)

    monkeypatch.setattr(whiteboard, "_load", checked_whiteboard_load)
    whiteboard.update("7", WhiteboardUpdate(title="Changed"))
    assert wb_lock_observed == [True]

    comments = CommentsStore(tmp_path)
    comments.create(
        "7",
        "c1",
        CommentCreate(
            anchor=CommentAnchor(block_index=0, from_offset=0, to_offset=4),
            quote="Text",
            body="Note",
        ),
    )
    comments_load = comments._load
    comments_lock_observed: list[bool] = []

    def checked_comments_load(doc_id: str):
        comments_lock_observed.append(local_state._STATE_LOCK._is_owned())
        return comments_load(doc_id)

    monkeypatch.setattr(comments, "_load", checked_comments_load)
    comments.update("7", "c1", CommentUpdate(body="Changed"))
    assert comments_lock_observed == [True]


def test_concurrent_comment_creates_do_not_overwrite_each_other(tmp_path: Path) -> None:
    store = CommentsStore(tmp_path)
    workers = 16
    barrier = threading.Barrier(workers)

    def create(index: int) -> None:
        barrier.wait()
        store.create(
            "7",
            f"c{index}",
            CommentCreate(
                anchor=CommentAnchor(block_index=0, from_offset=0, to_offset=4),
                quote="Text",
                body=f"Note {index}",
            ),
        )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(create, range(workers)))

    saved = store.get("7").comments
    assert len(saved) == workers
    assert {comment.id for comment in saved} == {f"c{index}" for index in range(workers)}


def test_comment_reply_client_id_is_idempotent(tmp_path: Path) -> None:
    store = CommentsStore(tmp_path)
    store.create(
        "7",
        "c1",
        CommentCreate(
            anchor=CommentAnchor(block_index=0, from_offset=0, to_offset=4),
            quote="Rain",
            body="Note",
        ),
    )
    payload = CommentReplyCreate(body="Keep this once", client_id="reply-stable")

    first = store.add_reply("7", "c1", payload.client_id or "", payload)
    retried = store.add_reply("7", "c1", payload.client_id or "", payload)

    assert first is not None
    assert retried is not None
    assert [reply.id for reply in retried.replies] == ["reply-stable"]
    assert [reply.body for reply in retried.replies] == ["Keep this once"]


def test_corrupt_manuscript_recovers_backup_and_quarantines_original(tmp_path: Path) -> None:
    store = WhiteboardStore(tmp_path)
    store.create("7", WhiteboardCreate(title="Recover me"))
    store.update("7", WhiteboardUpdate(title="Newest"))
    current = tmp_path / "whiteboards" / "7.json"
    current.write_text("{ definitely broken", encoding="utf-8")

    recovered = store.get("7")

    assert recovered.title == "Recover me"
    assert _title(current) == "Recover me"
    quarantined = list(current.parent.glob("7.json.corrupt-*"))
    assert len(quarantined) == 1
    assert quarantined[0].read_text(encoding="utf-8") == "{ definitely broken"
    assert quarantined[0].suffix != ".json"
    notices = consume_recovery_notices()
    assert len(notices) == 1
    assert notices[0]["label"] == "manuscript for document 7"
    assert notices[0]["quarantined_path"] == str(quarantined[0])
    assert consume_recovery_notices() == []


def test_unrecoverable_manuscript_is_never_replaced_by_autosave(tmp_path: Path) -> None:
    store = WhiteboardStore(tmp_path)
    store.create("7", WhiteboardCreate(title="Original"))
    current = tmp_path / "whiteboards" / "7.json"
    broken = b"not-json-and-no-backup"
    current.write_bytes(broken)

    with pytest.raises(LocalStateCorruptionError, match="was not replaced or cleared"):
        store.update("7", WhiteboardUpdate(title="Must not overwrite"))

    assert current.read_bytes() == broken
    assert not current.with_name("7.json.bak").exists()


def test_unrecoverable_outline_is_never_replaced_by_full_list_put(tmp_path: Path) -> None:
    store = OutlineItemsStore(tmp_path)
    store.replace("7", [{"id": "only-copy"}])
    current = tmp_path / "outlines" / "7.json"
    broken = b"broken-outline-with-no-backup"
    current.write_bytes(broken)

    with pytest.raises(LocalStateCorruptionError):
        store.replace("7", [])

    assert current.read_bytes() == broken


def test_recovery_falls_back_to_older_generation(tmp_path: Path) -> None:
    store = WhiteboardStore(tmp_path)
    store.create("8", WhiteboardCreate(title="Oldest valid"))
    store.update("8", WhiteboardUpdate(title="Newest backup"))
    store.update("8", WhiteboardUpdate(title="Current"))
    current = tmp_path / "whiteboards" / "8.json"
    current.write_text("bad current", encoding="utf-8")
    current.with_name("8.json.bak").write_text("bad newest backup", encoding="utf-8")

    recovered = store.get("8")

    assert recovered.title == "Oldest valid"
    assert _title(current) == "Oldest valid"
    assert not current.with_name("8.json.bak").exists()
    assert len(list(current.parent.glob("8.json.bak.corrupt-*"))) == 1


def test_outline_and_comments_use_the_same_recovery_policy(tmp_path: Path) -> None:
    outline = OutlineItemsStore(tmp_path)
    outline.replace("9", [{"id": "old"}])
    outline.replace("9", [{"id": "new"}])
    outline_path = tmp_path / "outlines" / "9.json"
    outline_path.write_text("[] trailing garbage", encoding="utf-8")
    assert outline.get("9") == [{"id": "old"}]
    assert len(list(outline_path.parent.glob("9.json.corrupt-*"))) == 1

    comments = CommentsStore(tmp_path)
    comments.create(
        "9",
        "c1",
        CommentCreate(
            anchor=CommentAnchor(block_index=0, from_offset=0, to_offset=4),
            quote="Once",
            body="Keep this",
        ),
    )
    comments.update("9", "c1", CommentUpdate(body="Newest note"))
    comments_path = tmp_path / "comments" / "9.json"
    comments_path.write_text("{broken", encoding="utf-8")
    recovered_comments = comments.get("9")
    assert recovered_comments.comments[0].body == "Keep this"
    assert len(list(comments_path.parent.glob("9.json.corrupt-*"))) == 1


def test_delete_removes_rotating_backups(tmp_path: Path) -> None:
    store = OutlineItemsStore(tmp_path)
    store.replace("4", [{"id": "one"}])
    store.replace("4", [{"id": "two"}])
    path = tmp_path / "outlines" / "4.json"
    assert path.exists() and path.with_name("4.json.bak").exists()

    store.delete("4")

    assert not path.exists()
    assert not path.with_name("4.json.bak").exists()
    assert not path.with_name("4.json.bak.1").exists()


class _FailedPsykeCore:
    async def request(self, method: str, path: str):
        request = httpx.Request(method, "http://logosforge-core" + path)
        response = httpx.Response(
            503,
            request=request,
            json={"error": {"message": "PSYKE database unavailable"}},
        )
        raise httpx.HTTPStatusError("failed", request=request, response=response)


def test_bundle_export_aborts_instead_of_silently_dropping_psyke() -> None:
    with pytest.raises(HTTPException) as caught:
        asyncio.run(_list_psyke(_FailedPsykeCore(), 12))

    assert caught.value.status_code == 502
    assert "export aborted" in str(caught.value.detail).lower()
    assert "PSYKE database unavailable" in str(caught.value.detail)


class _InvalidPsykeCore:
    async def request(self, _method: str, _path: str):
        return type("Response", (), {"json": lambda self: {"not": "a list"}})()


def test_bundle_export_rejects_invalid_psyke_payload() -> None:
    with pytest.raises(HTTPException, match="PSYKE response was invalid"):
        asyncio.run(_list_psyke(_InvalidPsykeCore(), 12))


class _CreatedProjectCore:
    def __init__(self, active_projects: list[dict] | None = None) -> None:
        self.deleted: list[int] = []
        self.active_projects = active_projects or []

    async def create_project(self, _title: str):
        return {"id": 77}

    async def delete_project(self, project_id: int) -> None:
        self.deleted.append(project_id)

    async def list_projects(self) -> list[dict]:
        return self.active_projects


class _FailingCreateStore:
    def delete(self, _doc_id: str) -> None:
        pass

    def create(self, _doc_id: str, _payload: WhiteboardCreate):
        raise LocalStateIOError(Path("failed.json"), "save", OSError("disk full"))


class _CleanupStore:
    def __init__(self, *, document_ids: set[str] | None = None, failures: int = 0) -> None:
        self.document_ids = set(document_ids or set())
        self.failures = failures
        self.deleted: list[str] = []
        self.included_summary_ids: set[str] | None = None

    def delete(self, doc_id: str) -> None:
        self.deleted.append(doc_id)
        if self.failures:
            self.failures -= 1
            raise LocalStateIOError(Path(f"{doc_id}.json"), "delete", OSError("locked"))
        self.document_ids.discard(doc_id)

    def list_document_ids(self) -> set[str]:
        return set(self.document_ids)

    def list_summaries(self, include_ids: set[str] | None = None) -> list:
        self.included_summary_ids = include_ids
        return []


def test_document_create_rolls_back_core_project_when_local_write_fails(monkeypatch) -> None:
    core = _CreatedProjectCore()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(core=core)))
    monkeypatch.setattr(documents_router, "whiteboard_store", _FailingCreateStore())
    monkeypatch.setattr(documents_router, "outline_items_store", _CleanupStore())
    monkeypatch.setattr(documents_router, "comments_store", _CleanupStore())

    with pytest.raises(HTTPException) as caught:
        asyncio.run(documents_router.create_document(request, WhiteboardCreate(title="New")))

    assert caught.value.status_code == 500
    assert core.deleted == [77]


def test_document_delete_succeeds_and_retries_after_local_cleanup_failure(monkeypatch) -> None:
    core = _CreatedProjectCore()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(core=core)))
    manuscript = _CleanupStore(document_ids={"77"}, failures=1)
    outline = _CleanupStore(document_ids={"77"})
    comments = _CleanupStore(document_ids={"77"})
    monkeypatch.setattr(documents_router, "whiteboard_store", manuscript)
    monkeypatch.setattr(documents_router, "outline_items_store", outline)
    monkeypatch.setattr(documents_router, "comments_store", comments)
    async def matching_incarnation(_request, _document_id: str) -> bool:
        return True
    monkeypatch.setattr(documents_router, "validate_delete_incarnation", matching_incarnation)

    deleted = asyncio.run(documents_router.delete_document(request, 77))

    assert deleted == {"ok": True, "deleted": "77", "cleanup_pending": True}
    assert core.deleted == [77]
    assert manuscript.deleted == ["77"]
    assert outline.deleted == ["77"]
    assert comments.deleted == ["77"]

    listed = asyncio.run(documents_router.list_documents(request))

    assert listed == {"documents": []}
    assert manuscript.deleted == ["77", "77"]
    assert "77" not in documents_router._pending_local_cleanup


def test_document_list_hides_and_retries_orphans_after_process_restart(monkeypatch) -> None:
    core = _CreatedProjectCore()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(core=core)))
    manuscript = _CleanupStore(document_ids={"77"}, failures=1)
    monkeypatch.setattr(documents_router, "whiteboard_store", manuscript)
    monkeypatch.setattr(documents_router, "outline_items_store", _CleanupStore())
    monkeypatch.setattr(documents_router, "comments_store", _CleanupStore())

    listed = asyncio.run(documents_router.list_documents(request))

    assert listed == {"documents": []}
    assert manuscript.deleted == ["77"]
    assert manuscript.included_summary_ids == set()
    assert documents_router._pending_local_cleanup == {"77"}
