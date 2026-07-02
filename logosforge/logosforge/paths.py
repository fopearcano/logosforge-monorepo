"""Resolve base paths for both source and PyInstaller-bundled execution."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def get_base_path() -> Path:
    if getattr(sys, "_MEIPASS", None):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def get_assets_path() -> Path:
    return get_base_path() / "assets"


def get_plugins_path() -> Path:
    return get_base_path() / "plugins"


def get_docs_path() -> Path:
    return get_base_path() / "docs"
