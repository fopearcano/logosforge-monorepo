"""Per-document lifecycle gate and incarnation validation.

Numeric core-project ids may be reused by SQLite.  A lock alone can serialize a
request that already reached FastAPI, but it cannot tell whether a delayed
client request belongs to the deleted project or its replacement.  Each local
Whiteboard document therefore owns a durable random incarnation token.  The
desktop echoes that token on mutations; the gate validates it only after it has
acquired the document lock and resolved the current core project.
"""
from __future__ import annotations

import asyncio
import hmac
import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import httpx
from fastapi import HTTPException, Request, status

from app.core_client import resolve_pid
from app.local_state import (
    LocalStateError,
    WhiteboardCreate,
    comments_store,
    outline_items_store,
    whiteboard_store,
)
from app.persistence_order import begin_document_delete, create_document_incarnation


DOCUMENT_INCARNATION_HEADER = "X-LogosForge-Document-Incarnation"
_INCARNATION_RE = re.compile(r"^[0-9a-f]{32}$")
_DOCUMENT_LOCKS: dict[str, tuple[asyncio.AbstractEventLoop, asyncio.Lock]] = {}
_DOCUMENT_IDENTITY_PUBLICATION_LOCK: tuple[
    asyncio.AbstractEventLoop, asyncio.Lock
] | None = None
_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class LockedDocument:
    project_id: int
    document_id: str
    incarnation: str


def document_lifecycle_lock(document_id: str) -> asyncio.Lock:
    """Return the process-lifetime lock shared by every operation for one id."""
    loop = asyncio.get_running_loop()
    entry = _DOCUMENT_LOCKS.get(document_id)
    if entry is None or (entry[0] is not loop and not entry[1].locked()):
        lock = asyncio.Lock()
        _DOCUMENT_LOCKS[document_id] = (loop, lock)
        return lock
    if entry[0] is not loop:
        raise RuntimeError("document lifecycle lock is active on another event loop")
    return entry[1]


@asynccontextmanager
async def document_identity_publication() -> AsyncIterator[None]:
    """Keep a newly allocated core id private until its incarnation is durable.

    SQLite may reuse a deleted numeric project id.  Creation cannot know which
    per-id lock to take until the core has allocated that id, so it holds this
    short global gate across allocation and local-incarnation publication.
    Explicit requests take the same gate only while acquiring their per-id lock,
    then release it before doing any I/O.  The single global -> per-id acquisition
    order prevents the create gap without serializing unrelated documents for the
    lifetime of their requests.
    """
    global _DOCUMENT_IDENTITY_PUBLICATION_LOCK
    loop = asyncio.get_running_loop()
    entry = _DOCUMENT_IDENTITY_PUBLICATION_LOCK
    if entry is None or (entry[0] is not loop and not entry[1].locked()):
        entry = (loop, asyncio.Lock())
        _DOCUMENT_IDENTITY_PUBLICATION_LOCK = entry
    elif entry[0] is not loop:
        raise RuntimeError("document publication gate is active on another event loop")
    async with entry[1]:
        yield


async def complete_core_allocation(
    allocation: Awaitable[dict[str, Any] | tuple[int, bool]],
) -> tuple[dict[str, Any] | tuple[int, bool], bool]:
    """Obtain an allocation result even if the serving request is cancelled.

    Once the core operation starts, losing its response can leave a committed
    project whose id the wrapper cannot compensate. Shield the operation and
    report cancellation to the caller so it can roll back the now-known id.
    """
    task = asyncio.create_task(allocation)
    cancellation_requested = False
    while True:
        try:
            return await asyncio.shield(task), cancellation_requested
        except asyncio.CancelledError:
            cancellation_requested = True
            if task.done():
                # Propagate cancellation originating inside the allocation task.
                return task.result(), cancellation_requested


def _clear_allocated_document_state(document_id: str) -> list[str]:
    """Clear every local namespace before publishing a newly allocated id."""
    failed: list[str] = []
    for label, store in (
        ("manuscript", whiteboard_store),
        ("outline", outline_items_store),
        ("comments", comments_store),
    ):
        try:
            store.delete(document_id)
        except Exception:
            failed.append(label)
            _LOG.exception(
                "Could not clear stale %s state for allocated document %s",
                label,
                document_id,
            )
    return failed


def _publish_allocated_default_identity(
    document_id: str,
    initialize_created: Callable[[str], None] | None = None,
) -> None:
    """Install a fresh local identity for a newly created default core project."""
    failed = _clear_allocated_document_state(document_id)
    if failed:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Default document creation was cancelled because stale local data "
                "for the reused project id could not be cleared."
            ),
        )
    try:
        with create_document_incarnation(document_id):
            if initialize_created is not None:
                initialize_created(document_id)
            if whiteboard_store.exists(document_id):
                whiteboard_store.ensure_incarnation(document_id)
            else:
                whiteboard_store.create(document_id, WhiteboardCreate())
    except LocalStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Default document creation was cancelled because local storage failed. {exc}",
        ) from exc


async def _settle_unpublished_default(core: Any, document_id: str) -> None:
    """Best-effort rollback of a default allocation, then quarantine its id."""
    try:
        await core.delete_project(int(document_id))
    except asyncio.CancelledError:
        _LOG.error("Core rollback was cancelled for unpublished default project %s", document_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != status.HTTP_404_NOT_FOUND:
            _LOG.exception("Could not roll back unpublished default project %s", document_id)
    except Exception:
        _LOG.exception("Could not roll back unpublished default project %s", document_id)

    async with document_lifecycle_lock(document_id):
        _clear_allocated_document_state(document_id)
        begin_document_delete(document_id)


async def _settle_unpublished_default_uninterruptibly(core: Any, document_id: str) -> None:
    settlement = asyncio.create_task(_settle_unpublished_default(core, document_id))
    while True:
        try:
            await asyncio.shield(settlement)
            return
        except asyncio.CancelledError:
            if settlement.done():
                settlement.result()
                return
            continue


@asynccontextmanager
async def locked_default_project(
    core: Any,
    *,
    initialize_created: Callable[[str], None] | None = None,
) -> AsyncIterator[int]:
    """Resolve/create the default under the publication gate and hold its id lock.

    Existing core-only projects remain core-only. Only a project allocated by
    this call receives a fresh local Whiteboard identity, which avoids both ABA
    reuse and accidental materialization of unrelated existing core projects.
    """
    lock: asyncio.Lock | None = None
    acquired = False
    document_id: str | None = None
    created = False
    published = False
    try:
        async with document_identity_publication():
            result, cancelled = await complete_core_allocation(core.ensure_project_with_status())
            pid, created = result
            document_id = str(pid)
            lock = document_lifecycle_lock(document_id)
            try:
                await lock.acquire()
                acquired = True
                if cancelled:
                    raise asyncio.CancelledError
                if created:
                    _publish_allocated_default_identity(document_id, initialize_created)
                published = True
            except BaseException:
                if acquired:
                    lock.release()
                    acquired = False
                if created and not published:
                    await _settle_unpublished_default_uninterruptibly(core, document_id)
                raise
        yield int(document_id)
    finally:
        if acquired and lock is not None:
            lock.release()


@asynccontextmanager
async def locked_document_lifecycle(document_id: str) -> AsyncIterator[None]:
    """Run a direct lifecycle transaction without crossing id publication.

    Callers of this lower-level helper perform their own authoritative lookup or
    delete reconciliation inside the context, so the publication gate must stay
    held for the whole transaction.  Higher-level ``locked_document_request``
    can release it earlier, immediately after it has resolved and validated the
    current incarnation while retaining the per-id lock.
    """
    lock = document_lifecycle_lock(document_id)
    acquired = False
    async with document_identity_publication():
        try:
            await lock.acquire()
            acquired = True
            yield
        finally:
            if acquired:
                lock.release()


def request_document_incarnation(
    request: Request,
    *,
    required: bool = False,
) -> str | None:
    """Parse the expected incarnation, optionally requiring the precondition."""
    raw = getattr(request, "headers", {}).get(DOCUMENT_INCARNATION_HEADER)
    if raw is None:
        if required:
            raise HTTPException(
                status_code=status.HTTP_428_PRECONDITION_REQUIRED,
                detail="Document incarnation is required for this mutation.",
            )
        return None
    value = raw.strip().lower()
    if not _INCARNATION_RE.fullmatch(value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document incarnation.",
        )
    return value


def document_incarnation_matches(expected: str | None, actual: str) -> bool:
    """Treat a missing legacy expectation as compatible; compare tokens safely."""
    return expected is None or hmac.compare_digest(expected, actual)


def require_document_incarnation(expected: str | None, actual: str) -> None:
    """Reject a delayed mutation aimed at an earlier use of the numeric id."""
    if not document_incarnation_matches(expected, actual):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This document id now belongs to a different document incarnation.",
        )


@asynccontextmanager
async def locked_document_request(
    request: Request,
    doc: int | None,
    *,
    mutation: bool = False,
    create_missing: bool = False,
) -> AsyncIterator[LockedDocument]:
    """Lock before authoritative resolution, then validate the current identity.

    Explicit document ids (all multi-document desktop calls) are locked before
    the first core lookup.  The legacy ``doc=None`` path first obtains its cached
    default-id hint, then re-resolves that id while holding the same per-id lock.
    """
    # An explicit id claims a particular document identity. Its token becomes a
    # required precondition for mutation after the authoritative lookup below.
    # Keeping resolution first preserves the existing 404 contract for an id
    # that has never named a core project, without touching any local file.
    expected = request_document_incarnation(request)
    core = request.app.state.core
    if doc is None:
        async with locked_default_project(core) as pid:
            document_id = str(pid)
            if create_missing and not whiteboard_store.exists(document_id):
                if expected is not None:
                    require_document_incarnation(expected, "")
                incarnation = ""
            else:
                incarnation = whiteboard_store.ensure_incarnation(document_id)
                require_document_incarnation(expected, incarnation)
            yield LockedDocument(
                project_id=pid,
                document_id=document_id,
                incarnation=incarnation,
            )
        return

    lock: asyncio.Lock | None = None
    acquired = False
    try:
        # Retain the publication gate through authoritative resolution and token
        # validation. A request that already owns the per-id lock must not release
        # the global gate before it has decided whether the id is absent/current;
        # otherwise creation could publish a reused core id underneath that check.
        async with document_identity_publication():
            hinted_pid = doc
            document_id = str(hinted_pid)
            lock = document_lifecycle_lock(document_id)
            await lock.acquire()
            acquired = True
            pid = await resolve_pid(core, int(hinted_pid))
            resource_exists = whiteboard_store.exists(str(pid))
            if create_missing and not resource_exists:
                # A headerless request cannot prove which lifetime of a reused
                # numeric core id it belongs to. Multi-document creation owns
                # identity publication through POST /api/documents instead.
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "An explicit Whiteboard resource must be created through "
                        "/api/documents."
                    ),
                )
            if mutation and expected is None and not (create_missing and not resource_exists):
                request_document_incarnation(request, required=True)
            incarnation = whiteboard_store.ensure_incarnation(str(pid))
            require_document_incarnation(expected, incarnation)
        locked = LockedDocument(
            project_id=pid,
            document_id=str(pid),
            incarnation=incarnation,
        )
        yield locked
    finally:
        if acquired and lock is not None:
            lock.release()


async def validate_delete_incarnation(request: Request, document_id: str) -> bool:
    """Validate a DELETE target while its lifecycle lock is already held.

    ``False`` means the core project is already absent, so the same-incarnation
    DELETE is idempotently complete.  If SQLite has reused the id, resolving the
    live project yields its new token and the old request receives HTTP 409.
    """
    expected = request_document_incarnation(request, required=True)
    try:
        pid = await resolve_pid(request.app.state.core, int(document_id))
    except HTTPException as exc:
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            return False
        raise
    incarnation = whiteboard_store.ensure_incarnation(str(pid))
    require_document_incarnation(expected, incarnation)
    return True
