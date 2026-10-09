"""Change-event broker for live React sync.

The desktop app uses a Qt-signal event bus (``logosforge.project_events``)
which requires a running Qt event loop.  The HTTP API runs independently of Qt,
so it owns a small, thread-safe, Qt-free broker instead.  Legacy mutating
routes call :meth:`ApiEventBroker.publish` after a successful change.  The
revisioned command families instead commit a compact invalidation to SQLite in
the same transaction as their mutation and receipt; this broker reconciles
those pending rows into its live ring.  Clients receive events either over
Server-Sent Events (``/events``) or by polling (``/events/poll``).

Event names mirror the desktop bus so the React layer can treat both transports
identically:

    project_loaded, project_data_changed, scene_changed, scenes_changed,
    outline_changed, plot_changed, canvas_plot_changed, timeline_changed,
    progressions_changed,
    knowledge_graph_changed, continuity_changed, psyke_changed,
    workflow_changed,
    notes_changed, comments_changed, characters_changed, dashboard_changed,
    assistant_action_completed
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections import deque
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from logosforge.db import Database

KNOWN_EVENTS = (
    "project_loaded",
    "project_data_changed",
    "scene_changed",
    "scenes_changed",
    "outline_changed",
    "plot_changed",
    "canvas_plot_changed",
    "timeline_changed",
    "progressions_changed",
    "knowledge_graph_changed",
    "continuity_changed",
    "workflow_changed",
    "psyke_changed",
    "notes_changed",
    "comments_changed",
    "characters_changed",
    "dashboard_changed",
    "assistant_action_completed",
)


class ApiEventBroker:
    """A bounded, thread-safe ring buffer of change events.

    Publishing is synchronous (routes run in a threadpool); consuming is done
    either synchronously (polling) or asynchronously (SSE tails the buffer).
    """

    def __init__(self, db: Database, maxlen: int = 2000) -> None:
        self._db = db
        self._lock = threading.Lock()
        self._events: deque[dict] = deque(maxlen=maxlen)
        self._counter = 0
        self._instance_id = uuid4().hex
        self._published_outbox_tokens: set[str] = set()
        self.reconcile()

    @property
    def instance_id(self) -> str:
        return self._instance_id

    def _append_locked(
        self,
        event: str,
        project_id: int | None,
        data: dict,
    ) -> dict:
        self._counter += 1
        evt = {
            "id": self._counter,
            "event": event,
            "project_id": project_id,
            "data": data,
            "ts": time.time(),
        }
        self._events.append(evt)
        return evt

    def publish(self, event: str, project_id: int | None = None, **data) -> dict:
        """Publish a legacy best-effort invalidation to this process's ring."""
        with self._lock:
            return self._append_locked(event, project_id, data)

    def reconcile(self) -> int:
        """Move committed outbox rows into the live ring, then acknowledge.

        Publication is deliberately at-least-once.  If acknowledgement fails
        after a row reached memory, its delivery token is remembered so reads in
        this process do not flood the ring; a later process may publish it
        again, which is safe because these messages only trigger refetches.
        """
        appended = 0
        with self._lock:
            while True:
                try:
                    rows = self._db.get_pending_api_events(limit=1000)
                except Exception:
                    return appended
                if not rows:
                    return appended

                acknowledged_rows = []
                batch_tokens: list[str] = []
                for row in rows:
                    if row.id is None:
                        continue
                    acknowledged_rows.append(row)
                    try:
                        envelope = json.loads(row.data_json or "{}")
                    except (json.JSONDecodeError, TypeError):
                        envelope = {}
                    if not isinstance(envelope, dict):
                        envelope = {}
                    token = envelope.get("outbox_token")
                    tokenized = isinstance(token, str) and bool(token)
                    if not tokenized:
                        # Compatibility fallback for any early development row
                        # written before token-bearing envelopes existed.
                        token = (
                            f"legacy:{row.id}:{row.project_id}:"
                            f"{row.event_name}:{row.created_at!r}:{row.data_json}"
                        )
                    batch_tokens.append(token)
                    if token in self._published_outbox_tokens:
                        continue
                    data = envelope.get("data", {}) if tokenized else envelope
                    if not isinstance(data, dict):
                        data = {}
                    self._append_locked(
                        row.event_name,
                        int(row.project_id),
                        data,
                    )
                    self._published_outbox_tokens.add(token)
                    appended += 1

                if not acknowledged_rows:
                    return appended
                try:
                    self._db.acknowledge_api_events(tuple(acknowledged_rows))
                except Exception:
                    return appended
                self._published_outbox_tokens.difference_update(batch_tokens)
                if len(rows) < 1000:
                    return appended

    def latest_id(self) -> int:
        self.reconcile()
        with self._lock:
            return self._counter

    def events_since(self, since: int, project_id: int | None = None) -> list[dict]:
        self.reconcile()
        with self._lock:
            return [
                e for e in self._events
                if e["id"] > since
                and (project_id is None or e["project_id"] in (None, project_id))
            ]

    def snapshot(
        self,
        since: int,
        project_id: int | None = None,
    ) -> tuple[list[dict], int, str, bool]:
        """Return events, high-water cursor, identity, and ring-gap state."""
        self.reconcile()
        with self._lock:
            oldest_available = (
                self._events[0]["id"]
                if self._events
                else self._counter + 1
            )
            reset_required = since < oldest_available - 1
            events = [
                event for event in self._events
                if event["id"] > since
                and (
                    project_id is None
                    or event["project_id"] in (None, project_id)
                )
            ]
            return events, self._counter, self._instance_id, reset_required

    async def stream(
        self, project_id: int | None = None, *, heartbeat: float = 15.0,
        poll_interval: float = 0.5, once: bool = False,
        since: int | None = None,
    ) -> AsyncIterator[str]:
        """Yield SSE-formatted strings, tailing the buffer for *project_id*.

        With ``once=True`` the generator emits the initial ``connected`` event
        plus any already-buffered events and then stops — a finite "drain" mode
        used by health checks and tests so they never block on the live loop.
        """
        latest = self.latest_id()
        if since is None:
            cursor = 0 if once else latest
        else:
            # A process-local cursor from an older broker can be larger than
            # this process's high-water mark.  Reset it so the new stream can
            # advance normally; the connected event also forces a full refetch.
            cursor = 0 if since > latest else since
        yield _sse(self._connected_event(cursor, project_id), include_id=False)
        if once:
            events, _, _, _ = self.snapshot(cursor, project_id)
            for evt in events:
                yield _sse(evt)
            return
        last_beat = time.monotonic()
        while True:
            events, high_water, _, reset_required = self.snapshot(
                cursor,
                project_id,
            )
            if reset_required:
                yield _sse(
                    self._connected_event(high_water, project_id),
                    include_id=False,
                )
            for evt in events:
                yield _sse(evt)
            # The cursor is global to the broker, not project-local. Advancing
            # across filtered events prevents another project's traffic from
            # making an otherwise healthy stream appear permanently truncated.
            cursor = high_water
            now = time.monotonic()
            if now - last_beat >= heartbeat:
                last_beat = now
                yield ": keep-alive\n\n"
            await asyncio.sleep(poll_interval)

    def _connected_event(
        self,
        cursor: int,
        project_id: int | None,
    ) -> dict:
        return {
            "id": cursor,
            "event": "connected",
            "project_id": project_id,
            "data": {"broker_instance_id": self._instance_id},
            "ts": time.time(),
        }


def _sse(payload: dict, *, include_id: bool = True) -> str:
    name = payload.get("event", "message")
    lines = [f"event: {name}"]
    if include_id and isinstance(payload.get("id"), int):
        lines.append(f"id: {payload['id']}")
    lines.append(f"data: {json.dumps(payload)}")
    return "\n".join(lines) + "\n\n"
