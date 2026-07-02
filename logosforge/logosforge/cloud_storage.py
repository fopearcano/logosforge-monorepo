"""Cloud-safe project storage primitives — provider-neutral.

Treats Google Drive, Dropbox, iCloud, OneDrive, and NAS folders as ordinary
filesystem paths.  Provides:

- atomic write (temp + fsync + os.replace) to avoid mid-sync corruption
- per-project lock files for cross-device "may already be open" warnings
- mtime+size fingerprint for external-change detection
- conflict-copy naming
- common cloud-folder discovery (for the folder picker — never required)

No OAuth, no provider APIs — that's a separate phase.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import platform
import socket
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

LOCK_SUFFIX = ".logosforge.lock"
CONFLICT_TAG = "conflict"
_STALE_LOCK_AGE_SECS = 24 * 60 * 60


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------

def atomic_write_text(path: str | os.PathLike, content: str,
                      encoding: str = "utf-8") -> None:
    """Write *content* to *path* atomically.

    Writes to a sibling tempfile, fsyncs it, then ``os.replace()`` onto the
    final name.  Safe on POSIX and Windows: a crash mid-write leaves either
    the previous file intact or the new file fully written — never a partial
    file that the cloud client could sync.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        prefix=target.name + ".",
        suffix=".tmp",
        dir=str(target.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(content)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
        os.replace(tmp_path, target)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Fingerprint (for external-change detection)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FileFingerprint:
    mtime_ns: int
    size: int

    @classmethod
    def of(cls, path: str | os.PathLike) -> "FileFingerprint | None":
        p = Path(path)
        try:
            st = p.stat()
        except OSError:
            return None
        return cls(mtime_ns=st.st_mtime_ns, size=st.st_size)

    def matches(self, other: "FileFingerprint | None") -> bool:
        if other is None:
            return False
        return self.mtime_ns == other.mtime_ns and self.size == other.size


def hash_file(path: str | os.PathLike) -> str | None:
    """SHA-256 of file content, or None if unreadable.  Optional check."""
    p = Path(path)
    try:
        h = hashlib.sha256()
        with p.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Lock file
# ---------------------------------------------------------------------------

def _lock_path_for(project_path: str | os.PathLike) -> Path:
    p = Path(project_path)
    return p.with_name(p.name + LOCK_SUFFIX)


def _app_version() -> str:
    try:
        from logosforge import __version__
        return str(__version__)
    except Exception:
        return "unknown"


def _device_name() -> str:
    try:
        return socket.gethostname() or platform.node() or "device"
    except Exception:
        return "device"


def _username() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return ""


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform.startswith("win"):
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid,
            )
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


@dataclass
class LockInfo:
    device: str
    user: str
    timestamp: float
    app_version: str
    pid: int

    def to_dict(self) -> dict:
        return {
            "device": self.device,
            "user": self.user,
            "timestamp": self.timestamp,
            "app_version": self.app_version,
            "pid": self.pid,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LockInfo":
        return cls(
            device=str(data.get("device", "")),
            user=str(data.get("user", "")),
            timestamp=float(data.get("timestamp", 0) or 0),
            app_version=str(data.get("app_version", "")),
            pid=int(data.get("pid", 0) or 0),
        )

    def is_same_machine(self) -> bool:
        return self.device == _device_name() and self.user == _username()

    def is_stale(self) -> bool:
        if self.is_same_machine() and not _pid_is_alive(self.pid):
            return True
        return (time.time() - self.timestamp) > _STALE_LOCK_AGE_SECS


def current_lock_info(project_path: str | os.PathLike) -> LockInfo | None:
    """Return the lock info if a lock file exists and is parseable."""
    lock = _lock_path_for(project_path)
    if not lock.exists():
        return None
    try:
        data = json.loads(lock.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return LockInfo.from_dict(data)
    except (json.JSONDecodeError, OSError):
        pass
    return None


def acquire_lock(project_path: str | os.PathLike) -> LockInfo:
    """Create or overwrite the lock file for this project.  Returns the info."""
    info = LockInfo(
        device=_device_name(),
        user=_username(),
        timestamp=time.time(),
        app_version=_app_version(),
        pid=os.getpid(),
    )
    atomic_write_text(
        _lock_path_for(project_path),
        json.dumps(info.to_dict(), indent=2),
    )
    return info


def release_lock(project_path: str | os.PathLike) -> None:
    """Remove the lock file if it exists.  Never raises."""
    lock = _lock_path_for(project_path)
    try:
        lock.unlink(missing_ok=True)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Conflict copies
# ---------------------------------------------------------------------------

def conflict_copy_path(project_path: str | os.PathLike,
                       when: float | None = None) -> Path:
    """Return a sibling path of the form ``<stem>_conflict_<device>_<ts><ext>``."""
    p = Path(project_path)
    ts = time.strftime("%Y%m%d-%H%M%S", time.localtime(when or time.time()))
    safe_device = "".join(
        c if c.isalnum() or c in "-_" else "-" for c in _device_name()
    ).strip("-") or "device"
    name = f"{p.stem}_{CONFLICT_TAG}_{safe_device}_{ts}{p.suffix}"
    return p.with_name(name)


def write_conflict_copy(project_path: str | os.PathLike, content: str) -> Path:
    """Write *content* to a fresh conflict-copy path beside *project_path*."""
    dest = conflict_copy_path(project_path)
    atomic_write_text(dest, content)
    return dest


# ---------------------------------------------------------------------------
# Cloud-folder detection (optional convenience for the picker)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CloudFolder:
    provider: str
    path: Path


def _candidate_paths() -> list[CloudFolder]:
    home = Path.home()
    out: list[CloudFolder] = []

    def add(provider: str, p: Path) -> None:
        out.append(CloudFolder(provider=provider, path=p))

    # macOS
    add("iCloud Drive", home / "Library" / "Mobile Documents" /
        "com~apple~CloudDocs")
    cloud_root = home / "Library" / "CloudStorage"
    if cloud_root.is_dir():
        try:
            for child in cloud_root.iterdir():
                name = child.name
                if name.startswith("GoogleDrive-"):
                    add("Google Drive", child)
                elif name.startswith("Dropbox"):
                    add("Dropbox", child)
                elif name.startswith("OneDrive"):
                    add("OneDrive", child)
        except OSError:
            pass

    # Cross-platform (POSIX-style home dir aliases)
    add("Dropbox", home / "Dropbox")
    add("Google Drive", home / "Google Drive")
    add("OneDrive", home / "OneDrive")

    # Windows env-var based
    onedrive = os.environ.get("OneDrive")
    if onedrive:
        add("OneDrive", Path(onedrive))
    onedrive_business = os.environ.get("OneDriveCommercial")
    if onedrive_business:
        add("OneDrive (Business)", Path(onedrive_business))
    return out


def detect_cloud_folders() -> list[CloudFolder]:
    """Return common cloud-sync folders that exist on this machine.

    Order is preserved; duplicates are removed by resolved path.
    """
    seen: set[str] = set()
    found: list[CloudFolder] = []
    for cand in _candidate_paths():
        if not cand.path.is_dir():
            continue
        try:
            key = str(cand.path.resolve())
        except OSError:
            key = str(cand.path)
        if key in seen:
            continue
        seen.add(key)
        found.append(cand)
    return found


def classify_path(path: str | os.PathLike) -> str:
    """Return the cloud provider name for *path* or ``"Local"``."""
    try:
        p = Path(path).resolve()
    except OSError:
        return "Local"
    for folder in detect_cloud_folders():
        try:
            p.relative_to(folder.path.resolve())
            return folder.provider
        except (ValueError, OSError):
            continue
    # Path-name heuristic for folders that may not be auto-detected
    s = str(p).lower()
    if "dropbox" in s:
        return "Dropbox"
    if "google drive" in s or "googledrive" in s:
        return "Google Drive"
    if "onedrive" in s:
        return "OneDrive"
    if "mobile documents" in s or "icloud" in s:
        return "iCloud Drive"
    return "Local"
