"""Thread-safe live editor context shared with connector/MCP reads.

There are two writers:

* the legacy Qt desktop calls :func:`set_live_context` in-process; and
* the packaged Electron desktop publishes ordered snapshots through the
  authenticated ``PUT /api/live-context`` endpoint.

Only plain values cross either boundary. Published snapshots expire after a
short monotonic-clock TTL so a crashed or disconnected desktop cannot leave an
agent believing that an old selection is still live. The per-source revision
ledger deliberately outlives a clear or expiry; a delayed request can therefore
never resurrect older context.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

# Qt's QTextCursor.selectedText() encodes line breaks as U+2029 (paragraph sep).
_QT_PARAGRAPH_SEP = chr(0x2029)

MAX_SELECTION_CHARS = 20_000
LIVE_CONTEXT_TTL_SECONDS = 30.0


class StaleLiveContextRevision(ValueError):
    """Raised when a source replays or reorders a published snapshot."""

    def __init__(self, revision: int, current_revision: int) -> None:
        super().__init__(
            f"Live-context revision {revision} is not newer than "
            f"{current_revision}."
        )
        self.revision = revision
        self.current_revision = current_revision


@dataclass(frozen=True)
class LiveContext:
    project_id: int | None = None
    active_panel_id: str | None = None
    active_scene_id: int | None = None
    selection_section: str | None = None
    selection: str = ""
    # True only while a writer's most recent non-clear snapshot is fresh.
    available: bool = False
    # ``None`` denotes the revisionless legacy Qt writer.
    revision: int | None = None

    @property
    def has_selection(self) -> bool:
        return bool(self.selection)


@dataclass(frozen=True)
class LiveContextPublishResult:
    revision: int
    available: bool
    project_id: int | None
    active_panel_id: str | None
    active_scene_id: int | None
    selection_length: int


def _normalize_selection(selection: str) -> str:
    return (selection or "").replace(_QT_PARAGRAPH_SEP, "\n")[
        :MAX_SELECTION_CHARS
    ]


class _LiveContextStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ctx = LiveContext()
        self._expires_at: float | None = None
        self._last_revisions: dict[str, int] = {}

    def set(
        self,
        *,
        project_id: int | None = None,
        active_panel_id: str | None = None,
        active_scene_id: int | None = None,
        selection_section: str | None = None,
        selection: str = "",
    ) -> None:
        """Set context for the in-process Qt desktop.

        This intentionally keeps the original revisionless call signature
        compatible while accepting richer fields when a legacy caller can
        provide them.
        """
        sel = _normalize_selection(selection)
        with self._lock:
            self._ctx = LiveContext(
                project_id=project_id,
                active_panel_id=active_panel_id,
                active_scene_id=active_scene_id,
                selection_section=selection_section,
                selection=sel,
                available=True,
            )
            self._expires_at = time.monotonic() + LIVE_CONTEXT_TTL_SECONDS

    def publish(
        self,
        *,
        source_id: str,
        revision: int,
        project_id: int | None,
        active_panel_id: str | None = None,
        active_scene_id: int | None = None,
        selection_section: str | None = None,
        selection: str = "",
    ) -> LiveContextPublishResult:
        """Apply one ordered packaged-desktop snapshot.

        ``project_id is None`` is an ordered clear. Its revision is still
        recorded, which prevents an older in-flight snapshot from making the
        cleared project or selection visible again.
        """
        sel = _normalize_selection(selection)
        with self._lock:
            current_revision = self._last_revisions.get(source_id)
            if current_revision is not None and revision <= current_revision:
                raise StaleLiveContextRevision(revision, current_revision)
            self._last_revisions[source_id] = revision

            if project_id is None:
                self._ctx = LiveContext()
                self._expires_at = None
                return LiveContextPublishResult(
                    revision=revision,
                    available=False,
                    project_id=None,
                    active_panel_id=None,
                    active_scene_id=None,
                    selection_length=0,
                )

            self._ctx = LiveContext(
                project_id=project_id,
                active_panel_id=active_panel_id,
                active_scene_id=active_scene_id,
                selection_section=selection_section,
                selection=sel,
                available=True,
                revision=revision,
            )
            self._expires_at = time.monotonic() + LIVE_CONTEXT_TTL_SECONDS
            return LiveContextPublishResult(
                revision=revision,
                available=True,
                project_id=project_id,
                active_panel_id=active_panel_id,
                active_scene_id=active_scene_id,
                selection_length=len(sel),
            )

    def get(self) -> LiveContext:
        with self._lock:
            if (
                self._ctx.available
                and self._expires_at is not None
                and time.monotonic() >= self._expires_at
            ):
                # Expire the visible snapshot but retain _last_revisions. A
                # delayed older publish must not resurrect stale editor state.
                self._ctx = LiveContext()
                self._expires_at = None
            return self._ctx

    def clear(self) -> None:
        """Hard-reset the legacy process-local store.

        The ordered HTTP clear uses :meth:`publish` instead. This reset keeps
        the historical Qt/test helper behavior and is also useful when an
        embedded API shuts down completely.
        """
        with self._lock:
            self._ctx = LiveContext()
            self._expires_at = None
            self._last_revisions.clear()


_STORE = _LiveContextStore()


def get_live_context() -> LiveContext:
    return _STORE.get()


def set_live_context(
    *,
    project_id: int | None = None,
    active_panel_id: str | None = None,
    active_scene_id: int | None = None,
    selection_section: str | None = None,
    selection: str = "",
) -> None:
    _STORE.set(
        project_id=project_id,
        active_panel_id=active_panel_id,
        active_scene_id=active_scene_id,
        selection_section=selection_section,
        selection=selection,
    )


def publish_live_context(
    *,
    source_id: str,
    revision: int,
    project_id: int | None,
    active_panel_id: str | None = None,
    active_scene_id: int | None = None,
    selection_section: str | None = None,
    selection: str = "",
) -> LiveContextPublishResult:
    return _STORE.publish(
        source_id=source_id,
        revision=revision,
        project_id=project_id,
        active_panel_id=active_panel_id,
        active_scene_id=active_scene_id,
        selection_section=selection_section,
        selection=selection,
    )


def clear_live_context() -> None:
    _STORE.clear()
