"""Lightweight project versioning — timestamped JSON snapshots.

Snapshots are stored under ~/.logosforge/versions/<project_id>/ as
individual JSON files named by ISO-style timestamp.  A timed interval
(default 5 min) creates automatic snapshots while the project is dirty,
and manual snapshots can be created on demand.

Retention: oldest snapshots beyond MAX_VERSIONS are deleted automatically.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QObject, QTimer

from logosforge.db import Database
from logosforge.export import _gather_project_data

log = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".logosforge"
VERSIONS_DIR = CONFIG_DIR / "versions"

MAX_VERSIONS = 50
SNAPSHOT_INTERVAL_MS = 5 * 60 * 1000  # 5 minutes


@dataclass
class VersionInfo:
    path: Path
    timestamp: datetime
    reason: str
    label: str

    @property
    def display_time(self) -> str:
        return self.timestamp.strftime("%Y-%m-%d %H:%M:%S")

    @property
    def file_size_kb(self) -> float:
        try:
            return self.path.stat().st_size / 1024
        except OSError:
            return 0.0


def _version_dir(project_id: int) -> Path:
    return VERSIONS_DIR / str(project_id)


def _ts_filename() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%f")


def _parse_version_meta(path: Path) -> VersionInfo | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        meta = raw.get("_version_meta", {})
        ts_str = meta.get("timestamp", "")
        ts = datetime.fromisoformat(ts_str) if ts_str else datetime.fromtimestamp(
            path.stat().st_mtime, tz=timezone.utc,
        )
        return VersionInfo(
            path=path,
            timestamp=ts,
            reason=meta.get("reason", "unknown"),
            label=meta.get("label", ""),
        )
    except (json.JSONDecodeError, OSError, ValueError):
        return None


class VersionManager(QObject):
    """Manages snapshot creation, listing, retention, and restore."""

    def __init__(
        self,
        db: Database,
        project_id: int,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._project_id = project_id
        self._dirty_since_snapshot = False

        self._interval_timer = QTimer(self)
        self._interval_timer.setInterval(SNAPSHOT_INTERVAL_MS)
        self._interval_timer.timeout.connect(self._on_interval)

    def start(self) -> None:
        self._interval_timer.start()

    def stop(self) -> None:
        self._interval_timer.stop()

    def set_project(self, project_id: int) -> None:
        self._project_id = project_id
        self._dirty_since_snapshot = False

    def mark_dirty(self) -> None:
        self._dirty_since_snapshot = True

    # -- Snapshot creation ----------------------------------------------------

    def create_snapshot(
        self,
        reason: str = "autosave",
        label: str = "",
    ) -> Path | None:
        vdir = _version_dir(self._project_id)
        try:
            vdir.mkdir(parents=True, exist_ok=True)
        except OSError:
            log.exception("Cannot create version directory")
            return None

        data = _gather_project_data(self._db, self._project_id)
        now = datetime.now(timezone.utc)
        data["_version_meta"] = {
            "timestamp": now.isoformat(),
            "reason": reason,
            "label": label,
        }

        filename = f"{_ts_filename()}.json"
        path = vdir / filename
        try:
            path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            log.debug("Version snapshot: %s (%s)", path, reason)
        except OSError:
            log.exception("Failed to write version snapshot")
            return None

        self._dirty_since_snapshot = False
        self._enforce_retention()
        return path

    # -- Listing / reading ---------------------------------------------------

    def list_versions(self) -> list[VersionInfo]:
        vdir = _version_dir(self._project_id)
        if not vdir.is_dir():
            return []
        versions: list[VersionInfo] = []
        for p in sorted(vdir.glob("*.json"), reverse=True):
            info = _parse_version_meta(p)
            if info is not None:
                versions.append(info)
        return versions

    def load_version_data(self, path: Path) -> dict | None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw.pop("_version_meta", None)
            return raw
        except (json.JSONDecodeError, OSError) as exc:
            # Surface the cause (corrupt/unreadable snapshot) instead of failing
            # silently — the restore UI reports a generic error, this logs why.
            log.warning("Could not load version snapshot %s: %s", path, exc)
            return None

    # -- Restore -------------------------------------------------------------

    def restore_version(self, path: Path) -> int | None:
        """Restore a version. Creates a safety snapshot first.

        Returns the new project_id on success, or None on failure.
        """
        self.create_snapshot(reason="pre-restore safety snapshot")

        data = self.load_version_data(path)
        if data is None:
            return None

        from logosforge.import_data import import_json
        try:
            new_project_id = import_json(self._db, data)
            return new_project_id
        except Exception:
            log.exception("Failed to restore version")
            return None

    # -- Deletion ------------------------------------------------------------

    def delete_version(self, path: Path) -> bool:
        try:
            path.unlink(missing_ok=True)
            return True
        except OSError:
            return False

    # -- Retention -----------------------------------------------------------

    def _enforce_retention(self) -> None:
        versions = self.list_versions()
        if len(versions) <= MAX_VERSIONS:
            return
        to_delete = versions[MAX_VERSIONS:]
        for v in to_delete:
            try:
                v.path.unlink(missing_ok=True)
            except OSError:
                pass

    # -- Timer callback ------------------------------------------------------

    def _on_interval(self) -> None:
        if self._dirty_since_snapshot:
            self.create_snapshot(reason="periodic")
