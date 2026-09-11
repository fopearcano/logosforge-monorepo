"""In-process ordering gate for main-process Whiteboard snapshot writes.

Electron assigns a total order per document/resource before dispatching a PUT.
An aborted HTTP client does not prove FastAPI stopped the accepted request, so
the authoritative comparison happens immediately around the local store write.
"""
from __future__ import annotations

from contextlib import contextmanager
import threading
from collections.abc import Iterator

from fastapi import HTTPException, Request, status


_ORDER_HEADER = "X-LogosForge-Persistence-Order"
_DELETE_FLOOR_HEADERS = {
    "whiteboard": "X-LogosForge-Whiteboard-Order-Floor",
    "outline": "X-LogosForge-Outline-Order-Floor",
}
_LOCK = threading.RLock()
_HIGHEST: dict[tuple[str, str], int] = {}
_DELETING_DOCUMENTS: set[str] = set()


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
) -> Iterator[bool]:
    """Hold ordering through the synchronous store write and reject stale PUTs."""
    key = (kind, document_id)
    with _LOCK:
        if document_id in _DELETING_DOCUMENTS:
            yield False
            return
        previous = _HIGHEST.get(key, 0)
        if order is not None and order <= previous:
            yield False
            return
        if order is not None:
            _HIGHEST[key] = order
        try:
            yield True
        except BaseException:
            # A retry receives a newer main dispatch order, but rollback also
            # keeps direct focused tests and future transports unsurprising.
            if order is not None and _HIGHEST.get(key) == order:
                if previous:
                    _HIGHEST[key] = previous
                else:
                    _HIGHEST.pop(key, None)
            raise


def begin_document_delete(
    document_id: str,
    issued_floors: dict[str, int] | None = None,
) -> None:
    """Wait for an accepted store write, then reject every later old request."""
    with _LOCK:
        for kind, floor in (issued_floors or {}).items():
            key = (kind, document_id)
            _HIGHEST[key] = max(_HIGHEST.get(key, 0), floor)
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
        yield
