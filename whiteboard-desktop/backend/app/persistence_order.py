"""In-process ordering gate for main-process Whiteboard snapshot writes.

Electron assigns a total order per document/resource before dispatching a PUT.
An aborted HTTP client does not prove FastAPI stopped the accepted request, so
the authoritative comparison happens immediately around the local store write.
"""
from __future__ import annotations

from contextlib import contextmanager
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from fastapi import HTTPException, Request, status


_ORDER_HEADER = "X-LogosForge-Persistence-Order"
_DELETE_FLOOR_HEADERS = {
    "whiteboard": "X-LogosForge-Whiteboard-Order-Floor",
    "outline": "X-LogosForge-Outline-Order-Floor",
}
_LOCK = threading.RLock()
_HIGHEST: dict[tuple[str, str], int] = {}
_LINEAGE_REVISION: dict[tuple[str, str], str] = {}
_REJECT_THROUGH: dict[tuple[str, str], int] = {}
_DELETING_DOCUMENTS: set[str] = set()


@dataclass
class PersistenceWriteDecision:
    """One ordering decision held under the gate until the store write ends."""

    accepted: bool
    _committed_revision: str | None = None

    def __bool__(self) -> bool:
        return self.accepted

    def commit(self, revision: str) -> None:
        """Record the durable revision produced (or proven) by this request."""
        if not self.accepted:
            raise RuntimeError("A rejected persistence write cannot be committed.")
        if not revision:
            raise ValueError("A committed persistence write requires a revision.")
        self._committed_revision = revision


def request_persistence_order(request: Request) -> int | None:
    """Parse Electron's optional ordering header; ordinary API clients omit it."""
    raw = getattr(request, "headers", {}).get(_ORDER_HEADER)
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid persistence order.",
        ) from exc
    if value < 1 or value > 9_007_199_254_740_991:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid persistence order.",
        )
    return value


def request_delete_order_floors(request: Request) -> dict[str, int]:
    """Read the highest main-issued order for each DELETE-owned resource."""
    floors: dict[str, int] = {}
    headers = getattr(request, "headers", {})
    for kind, header in _DELETE_FLOOR_HEADERS.items():
        raw = headers.get(header)
        if raw is None:
            continue
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid persistence delete floor.",
            ) from exc
        if value < 0 or value > 9_007_199_254_740_991:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid persistence delete floor.",
            )
        floors[kind] = value
    return floors


@contextmanager
def accept_persistence_write(
    kind: str,
    document_id: str,
    order: int | None,
    *,
    current_revision: Callable[[], str] | None = None,
) -> Iterator[PersistenceWriteDecision]:
    """Hold ordering through the synchronous store write and reject safe stale PUTs.

    A lower/equal order is a no-op only while the resource still has the exact
    revision produced by the newest ordered commit. If an unordered writer or
    backup recovery changed the resource, the lineage is invalidated and the
    request reaches the conditional store write, where its ``If-Match`` or exact
    mutation id must prove safety. This keeps ordering and the actual write in
    one critical section without allowing the order ledger to bypass ETags.
    """
    key = (kind, document_id)
    with _LOCK:
        if document_id in _DELETING_DOCUMENTS:
            yield PersistenceWriteDecision(False)
            return

        if order is not None and order <= _REJECT_THROUGH.get(key, 0):
            yield PersistenceWriteDecision(False)
            return

        previous = _HIGHEST.get(key, 0)
        lineage_revision = _LINEAGE_REVISION.get(key)
        if lineage_revision is not None and current_revision is not None:
            observed_revision = current_revision()
            if observed_revision != lineage_revision:
                # Revision tokens are non-repeating. A mismatch proves that an
                # unordered write or recovery left the ordered lineage.
                _LINEAGE_REVISION.pop(key, None)
                lineage_revision = None

        if order is not None and order <= previous and lineage_revision is not None:
            # With no intervening state change, the latest ordered snapshot is
            # already durable and every earlier/equal dispatch is superseded.
            yield PersistenceWriteDecision(False)
            return

        decision = PersistenceWriteDecision(True)
        yield decision
        if decision._committed_revision is None:
            return
        if order is None:
            # An ordinary API write deliberately breaks the Electron sequence.
            _LINEAGE_REVISION.pop(key, None)
            return
        _HIGHEST[key] = max(previous, order)
        _LINEAGE_REVISION[key] = decision._committed_revision


def begin_document_delete(
    document_id: str,
    issued_floors: dict[str, int] | None = None,
) -> None:
    """Wait for an accepted store write, then reject every later old request."""
    with _LOCK:
        kinds = {kind for kind, doc_id in _HIGHEST if doc_id == document_id}
        kinds.update((issued_floors or {}).keys())
        for kind in kinds:
            key = (kind, document_id)
            floor = max(_HIGHEST.get(key, 0), (issued_floors or {}).get(kind, 0))
            _HIGHEST[key] = floor
            _REJECT_THROUGH[key] = max(_REJECT_THROUGH.get(key, 0), floor)
            _LINEAGE_REVISION.pop(key, None)
        _DELETING_DOCUMENTS.add(document_id)


def cancel_document_delete(document_id: str) -> None:
    with _LOCK:
        _DELETING_DOCUMENTS.discard(document_id)


@contextmanager
def create_document_incarnation(document_id: str) -> Iterator[None]:
    """Atomically reopen a reused id and install its initial local document.

    Keep the highest transport order: Electron's per-resource counter is also
    monotonic across numeric-id reuse, so a still-running old request remains
    distinguishable from the new incarnation's later snapshot.
    """
    with _LOCK:
        _DELETING_DOCUMENTS.discard(document_id)
        for key in tuple(_LINEAGE_REVISION):
            if key[1] == document_id:
                _LINEAGE_REVISION.pop(key, None)
        yield
