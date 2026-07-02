"""Track recently opened/saved project file paths."""

import json
from pathlib import Path

MAX_RECENT = 10
CONFIG_DIR = Path.home() / ".logosforge"
RECENT_FILE = CONFIG_DIR / "recent_projects.json"


def load() -> list[str]:
    if not RECENT_FILE.exists():
        return []
    try:
        data = json.loads(RECENT_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [p for p in data if isinstance(p, str)]
    except (json.JSONDecodeError, OSError):
        pass
    return []


def add(path: str) -> None:
    paths = load()
    if path in paths:
        paths.remove(path)
    paths.insert(0, path)
    paths = paths[:MAX_RECENT]
    _save(paths)


def remove(path: str) -> None:
    paths = load()
    paths = [p for p in paths if p != path]
    _save(paths)


def clean() -> list[str]:
    """Drop paths whose files no longer exist on disk. Returns cleaned list."""
    paths = load()
    valid = [p for p in paths if Path(p).is_file()]
    if len(valid) != len(paths):
        _save(valid)
    return valid


def load_with_status() -> list[tuple[str, bool]]:
    """Return (path, exists) tuples without removing missing entries."""
    return [(p, Path(p).is_file()) for p in load()]


def rename(old_path: str, new_path: str) -> None:
    """Replace *old_path* with *new_path* in-place, preserving order."""
    paths = load()
    replaced = False
    out: list[str] = []
    for p in paths:
        if p == old_path:
            if not replaced and new_path not in out:
                out.append(new_path)
                replaced = True
        elif p == new_path:
            if not replaced:
                out.append(new_path)
                replaced = True
        else:
            out.append(p)
    if not replaced:
        out.insert(0, new_path)
    _save(out[:MAX_RECENT])


def _save(paths: list[str]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    RECENT_FILE.write_text(json.dumps(paths, indent=2), encoding="utf-8")
