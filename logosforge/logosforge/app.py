"""Application factory — creates the QApplication and MainWindow."""

import os
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from logosforge import preferences
from logosforge.db import Database
from logosforge.paths import get_assets_path
from logosforge.plugin_manager import get_plugin_manager
from logosforge.settings import get_manager as get_settings
from logosforge.ui.main_window import MainWindow
from logosforge.ui import theme

DB_PATH = "logosforge.db"


def _set_macos_app_name(name: str) -> None:
    """Set CFBundleName so macOS shows the correct name in the menu bar and dock."""
    if sys.platform != "darwin":
        return
    try:
        from Foundation import NSBundle
        info = NSBundle.mainBundle().infoDictionary()
        info["CFBundleName"] = name
    except Exception:
        pass


def _migrate_legacy_config_dir() -> None:
    """One-time migration of the user-data dir from the legacy ``~/.storyplanner``
    to ``~/.logosforge`` (the package was renamed storyplanner -> logosforge).

    Runs once at app startup — never at import, so the test suite's home-dir
    isolation is untouched. Carries over every item present in the legacy dir
    but missing from the new one (settings, recent projects, version snapshots,
    memory, …) *non-destructively*: anything already in ``~/.logosforge`` wins,
    so a partially-populated new dir is never clobbered. A marker file makes it
    run at most once. Best-effort; never fatal.
    """
    try:
        import shutil
        legacy = Path.home() / ".storyplanner"
        new = Path.home() / ".logosforge"
        if not legacy.is_dir():
            return
        marker = new / ".migrated_from_storyplanner"
        if marker.exists():
            return
        new.mkdir(parents=True, exist_ok=True)
        for item in legacy.iterdir():
            dest = new / item.name
            if not dest.exists():
                shutil.move(str(item), str(dest))
        marker.write_text("migrated from ~/.storyplanner\n", encoding="utf-8")
    except Exception:
        pass


def _migrate_legacy_db(db_path: str) -> None:
    """One-time migration of the default project DB ``storyplanner.db`` ->
    ``logosforge.db``. Acts only on the bare default filename: if the new DB is
    absent but a legacy ``storyplanner.db`` sits beside it, rename it so the
    project data carries over. Explicit/other paths are left untouched.
    """
    try:
        new = Path(db_path)
        if new.name != "logosforge.db" or new.exists():
            return
        legacy = new.with_name("storyplanner.db")
        if legacy.is_file():
            legacy.rename(new)
    except Exception:
        pass


def create_app() -> tuple[QApplication, MainWindow]:
    _set_macos_app_name("Logosforge")
    QApplication.setApplicationName("Logosforge")
    QApplication.setApplicationDisplayName("Logosforge")
    QApplication.setOrganizationName("Logosforge")
    # Expose the canonical version as Qt/OS app metadata (no visible widget).
    from logosforge import __version__ as _app_version
    QApplication.setApplicationVersion(_app_version)
    app = QApplication.instance() or QApplication(sys.argv)

    assets = get_assets_path()
    for icon_name in ("icon.png", "icon.svg"):
        icon_path = str(assets / icon_name)
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))
            break

    _migrate_legacy_config_dir()
    mgr = get_settings()
    # Make local GPU voice transcription work without a launcher wrapper: add
    # any user-configured CUDA runtime DLL directories to the search path
    # before faster-whisper is (lazily) loaded. No-op when unset.
    from logosforge.voice.cuda_paths import ensure_cuda_dll_path
    ensure_cuda_dll_path(mgr.get("voice_cuda_dll_dirs") or [])

    saved = str(mgr.get("appearance"))
    if saved in theme.PALETTE_NAMES:
        theme.set_palette(saved)

    app.setStyleSheet(theme.build_stylesheet())

    _migrate_legacy_db(DB_PATH)
    db = Database(DB_PATH)

    projects = db.get_all_projects()
    if projects:
        project = projects[0]
    else:
        project = db.create_project("My Story")

    pm = get_plugin_manager()
    pm.discover()
    pm.set_app_context(db, project.id)
    pm.load_enabled()

    window = MainWindow(db, project.id)
    # Repair any legacy orphan structure on the initial project so no section
    # ever opens on scenes outside the Act → Chapter → Scene chain. (Opening a
    # different last_project below goes through _switch_project, which repairs.)
    window._repair_structure(project.id)

    last_path = str(mgr.get("last_project_path") or "")
    if last_path:
        window.load_file_quiet(last_path)

    # Always land on Projects at startup — never Dashboard by default.
    # Runs after any session restore so it wins the final navigation and
    # rebuilds the Projects list against current data.
    window.show_initial_section()

    window._refresh_plugins_menu()

    return app, window
