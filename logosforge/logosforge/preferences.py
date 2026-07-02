"""User preference flags persisted to a JSON file."""

import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".logosforge"
PREFS_FILE = CONFIG_DIR / "preferences.json"


def _load() -> dict:
    if not PREFS_FILE.exists():
        return {}
    try:
        data = json.loads(PREFS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def get_flag(name: str) -> bool:
    return bool(_load().get(name, False))


def get_string(name: str, default: str = "") -> str:
    val = _load().get(name, default)
    return str(val) if val else default


def set_flag(name: str, value: bool) -> None:
    _save(name, bool(value))


def set_string(name: str, value: str) -> None:
    _save(name, value)


def _save(name: str, value: object) -> None:
    data = _load()
    data[name] = value
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        PREFS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass
