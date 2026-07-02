"""Autosave manager with debounced saves and status signals.

Replaces the synchronous _auto_save() in MainWindow with a debounced,
non-blocking save that coalesces rapid edits and reports status.
"""

import json
import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from logosforge.cloud_storage import (
    FileFingerprint,
    atomic_write_text,
    write_conflict_copy,
)
from logosforge.db import Database
from logosforge.export import _gather_project_data

log = logging.getLogger(__name__)

_DEBOUNCE_MS = 3000


class ExternalChangeError(Exception):
    """Raised when the project file changed on disk since we loaded it."""

    def __init__(self, message: str, content: str) -> None:
        super().__init__(message)
        self.pending_content = content


class AutosaveManager(QObject):
    """Debounced autosave that writes project JSON after edits settle."""

    status_changed = Signal(str)  # "Saving…", "Saved", "Save failed"
    external_change_detected = Signal(str)  # file path

    def __init__(
        self,
        db: Database,
        project_id: int,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._project_id = project_id
        self._file_path: str | None = None
        self._dirty = False
        self._saving = False
        self._queued = False
        self._fingerprint: FileFingerprint | None = None
        self._ignore_external_change_once = False

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(_DEBOUNCE_MS)
        self._debounce.timeout.connect(self._do_save)

    @property
    def dirty(self) -> bool:
        return self._dirty

    @property
    def file_path(self) -> str | None:
        return self._file_path

    @file_path.setter
    def file_path(self, path: str | None) -> None:
        self._file_path = path
        self.refresh_fingerprint()

    def set_project(self, project_id: int) -> None:
        self._debounce.stop()
        self._project_id = project_id
        self._dirty = False
        self._queued = False

    def mark_dirty(self) -> None:
        self._dirty = True
        if self._file_path:
            self._debounce.start()

    def mark_clean(self) -> None:
        self._dirty = False
        self._debounce.stop()

    def refresh_fingerprint(self) -> None:
        """Re-read mtime/size from disk — call after loading or external reload."""
        if self._file_path:
            self._fingerprint = FileFingerprint.of(self._file_path)
        else:
            self._fingerprint = None

    def has_external_change(self) -> bool:
        if not self._file_path or self._fingerprint is None:
            return False
        current = FileFingerprint.of(self._file_path)
        if current is None:
            return False
        return not self._fingerprint.matches(current)

    def force_next_save(self) -> None:
        """Allow the next save to overwrite even if an external change is seen."""
        self._ignore_external_change_once = True

    def save_now(self) -> bool:
        """Immediate save (Ctrl+S or close). Returns True on success."""
        self._debounce.stop()
        return self._do_save()

    def write_conflict_copy_now(self) -> str | None:
        """Write the pending content to a conflict-copy file beside the project."""
        if not self._file_path:
            return None
        data = _gather_project_data(self._db, self._project_id)
        content = json.dumps(data, indent=2, ensure_ascii=False)
        try:
            dest = write_conflict_copy(self._file_path, content)
            return str(dest)
        except OSError:
            log.exception("Conflict-copy write failed")
            return None

    def _do_save(self) -> bool:
        if not self._file_path:
            return False
        if self._saving:
            self._queued = True
            return False

        self._saving = True
        self.status_changed.emit("Saving…")

        try:
            data = _gather_project_data(self._db, self._project_id)
            content = json.dumps(data, indent=2, ensure_ascii=False)

            if (
                self._fingerprint is not None
                and not self._ignore_external_change_once
                and Path(self._file_path).exists()
                and self.has_external_change()
            ):
                self.status_changed.emit("Save blocked: external changes")
                self.external_change_detected.emit(self._file_path)
                return False

            atomic_write_text(self._file_path, content)
            self._fingerprint = FileFingerprint.of(self._file_path)
            self._ignore_external_change_once = False
            self._dirty = False
            self.status_changed.emit("Saved")
            log.debug("Autosaved to %s", self._file_path)
            ok = True
        except Exception:
            log.exception("Autosave failed")
            self.status_changed.emit("Save failed")
            ok = False
        finally:
            self._saving = False

        if self._queued:
            self._queued = False
            QTimer.singleShot(100, self._do_save)

        return ok

    def gather_data(self) -> dict:
        return _gather_project_data(self._db, self._project_id)
