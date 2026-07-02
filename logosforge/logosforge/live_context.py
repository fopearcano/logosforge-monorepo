"""Process-local LIVE editor context — current project, active scene, selection.

The desktop UI **pushes** plain values here on the Qt GUI thread; the in-process
API (running on a uvicorn worker thread) **reads** them. Only plain data crosses
the thread boundary, guarded by a lock — never Qt widgets — so it is safe.

When the API runs as a *separate* process this store is simply empty
(``available == False``); callers treat that as "no live context" and fall back
to persisted data. This is the single boundary that gives an external agent the
user's *live* editing state without unsafe cross-thread widget access.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

# Qt's QTextCursor.selectedText() encodes line breaks as U+2029 (paragraph sep).
_QT_PARAGRAPH_SEP = chr(0x2029)


@dataclass(frozen=True)
class LiveContext:
    project_id: int | None = None
    active_scene_id: int | None = None
    selection: str = ""
    # True once the desktop has pushed at least once (i.e. the API is in-process).
    available: bool = False

    @property
    def has_selection(self) -> bool:
        return bool(self.selection)


class _LiveContextStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ctx = LiveContext()

    def set(
        self,
        *,
        project_id: int | None = None,
        active_scene_id: int | None = None,
        selection: str = "",
    ) -> None:
        sel = (selection or "").replace(_QT_PARAGRAPH_SEP, "\n")
        with self._lock:
            self._ctx = LiveContext(
                project_id=project_id,
                active_scene_id=active_scene_id,
                selection=sel,
                available=True,
            )

    def get(self) -> LiveContext:
        with self._lock:
            return self._ctx

    def clear(self) -> None:
        with self._lock:
            self._ctx = LiveContext()


_STORE = _LiveContextStore()


def get_live_context() -> LiveContext:
    return _STORE.get()


def set_live_context(
    *,
    project_id: int | None = None,
    active_scene_id: int | None = None,
    selection: str = "",
) -> None:
    _STORE.set(
        project_id=project_id,
        active_scene_id=active_scene_id,
        selection=selection,
    )


def clear_live_context() -> None:
    _STORE.clear()
