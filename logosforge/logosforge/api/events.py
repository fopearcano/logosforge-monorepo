"""Change-event broker for live React sync.

The desktop app uses a Qt-signal event bus (``logosforge.project_events``)
which requires a running Qt event loop.  The HTTP API runs independently of Qt,
so it owns a small, thread-safe, Qt-free broker instead.  Mutating routes call
:meth:`ApiEventBroker.publish` after a successful change; clients receive those
events either over Server-Sent Events (``/events``) or by polling
(``/events/poll``).

Event names mirror the desktop bus so the React layer can treat both transports
identically:

    project_loaded, project_data_changed, scene_changed, scenes_changed,
    outline_changed, plot_changed, timeline_changed, psyke_changed,
    notes_changed, characters_changed, dashboard_changed, assistant_action_completed
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from typing import AsyncIterator

KNOWN_EVENTS = (
    "project_loaded",
    "project_data_changed",
    "scene_changed",
    "scenes_changed",
    "outline_changed",
    "plot_changed",
    "timeline_changed",
    "psyke_changed",
    "notes_changed",
    "characters_changed",
    "dashboard_changed",
    "assistant_action_completed",
)


class ApiEventBroker:
    """A bounded, thread-safe ring buffer of change events.

    Publishing is synchronous (routes run in a threadpool); consuming is done
    either synchronously (polling) or asynchronously (SSE tails the buffer).
    """

    def __init__(self, maxlen: int = 2000) -> None:
        self._lock = threading.Lock()
        self._events: deque[dict] = deque(maxlen=maxlen)
        self._counter = 0

    def publish(self, event: str, project_id: int | None = None, **data) -> dict:
        with self._lock:
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

    def latest_id(self) -> int:
        with self._lock:
            return self._counter

    def events_since(self, since: int, project_id: int | None = None) -> list[dict]:
        with self._lock:
            return [
                e for e in self._events
                if e["id"] > since
                and (project_id is None or e["project_id"] in (None, project_id))
            ]

    async def stream(
        self, project_id: int | None = None, *, heartbeat: float = 15.0,
        poll_interval: float = 0.5, once: bool = False,
    ) -> AsyncIterator[str]:
        """Yield SSE-formatted strings, tailing the buffer for *project_id*.

        With ``once=True`` the generator emits the initial ``connected`` event
        plus any already-buffered events and then stops — a finite "drain" mode
        used by health checks and tests so they never block on the live loop.
        """
        cursor = self.latest_id()
        yield _sse({"event": "connected", "project_id": project_id, "id": cursor})
        if once:
            for evt in self.events_since(cursor, project_id):
                yield _sse(evt)
            return
        last_beat = time.monotonic()
        while True:
            for evt in self.events_since(cursor, project_id):
                cursor = evt["id"]
                yield _sse(evt)
            now = time.monotonic()
            if now - last_beat >= heartbeat:
                last_beat = now
                yield ": keep-alive\n\n"
            await asyncio.sleep(poll_interval)


def _sse(payload: dict) -> str:
    import json

    name = payload.get("event", "message")
    return f"event: {name}\ndata: {json.dumps(payload)}\n\n"
