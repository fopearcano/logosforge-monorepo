"""Shared test fixtures."""

import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def _isolate_config_dir(tmp_path_factory, monkeypatch):
    """Redirect the user-data config dir to a per-test temp dir so no test can
    write settings / preferences / recent-projects / version snapshots to the
    user's REAL ``~/.logosforge``.

    ``CONFIG_DIR`` (and the file/dir constants derived from it) are module-level
    constants computed from ``Path.home()`` at import time, so they must be
    patched per module. Most tests that touch these already patch CONFIG_DIR in
    their own fixtures; this is a blanket safety net so a missed one can never
    pollute — or worse, overwrite — the user's real config during a test run.
    """
    # A dedicated temp dir — NOT the test's own ``tmp_path``: some tests assert
    # on the exact contents of their ``tmp_path``, and a stray ``.logosforge``
    # there would break them (e.g. test_writer_qa_harness::test_reports_stay_in_tmp).
    cfg = tmp_path_factory.mktemp("logosforge_cfg")
    import logosforge.settings as settings
    import logosforge.preferences as preferences
    import logosforge.recent_projects as recent_projects
    import logosforge.version_manager as version_manager
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", cfg)
    monkeypatch.setattr(settings, "SETTINGS_FILE", cfg / "settings.json")
    monkeypatch.setattr(preferences, "CONFIG_DIR", cfg)
    monkeypatch.setattr(preferences, "PREFS_FILE", cfg / "preferences.json")
    monkeypatch.setattr(recent_projects, "CONFIG_DIR", cfg)
    monkeypatch.setattr(recent_projects, "RECENT_FILE", cfg / "recent_projects.json")
    monkeypatch.setattr(version_manager, "CONFIG_DIR", cfg)
    monkeypatch.setattr(version_manager, "VERSIONS_DIR", cfg / "versions")
    # quantum_outliner.collapse does ``from logosforge.settings import CONFIG_DIR``
    # (a by-value capture at import time), so patching settings.CONFIG_DIR above
    # does NOT reach it — it must be patched on the module that holds the binding,
    # or its ``CONFIG_DIR / "quantum"`` archive writes leak to the real home dir.
    import logosforge.quantum_outliner.collapse as _collapse
    monkeypatch.setattr(_collapse, "CONFIG_DIR", cfg)
    yield
    settings._instance = None


@pytest.fixture(autouse=True)
def _nonblocking_message_boxes(monkeypatch):
    """Stop modal QMessageBox dialogs from blocking headless tests.

    Several flows (e.g. MainWindow.closeEvent's unsaved-changes prompt)
    open a modal QMessageBox; with no event loop and no user, exec()
    blocks forever. No test asserts on QMessageBox return values, so we
    return safe non-destructive defaults: warnings discard, questions
    answer No, info/critical acknowledge.
    """
    from PySide6.QtWidgets import QMessageBox

    SB = QMessageBox.StandardButton
    monkeypatch.setattr(
        QMessageBox, "warning",
        staticmethod(lambda *a, **k: SB.Discard), raising=False,
    )
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: SB.No), raising=False,
    )
    monkeypatch.setattr(
        QMessageBox, "information",
        staticmethod(lambda *a, **k: SB.Ok), raising=False,
    )
    monkeypatch.setattr(
        QMessageBox, "critical",
        staticmethod(lambda *a, **k: SB.Ok), raising=False,
    )
    yield


@pytest.fixture(autouse=True)
def _auto_accept_project_dialogs(monkeypatch):
    """Auto-accept the modal project dialogs so headless tests that
    invoke _on_new_project() (which opens NewProjectDialog.exec()) don't
    block. No test drives these dialogs interactively, so returning
    Accepted lets the create-new-project flow proceed with its defaults.
    """
    from PySide6.QtWidgets import QDialog
    from logosforge.ui.new_project_dialog import NewProjectDialog
    monkeypatch.setattr(
        NewProjectDialog, "exec",
        lambda self: QDialog.DialogCode.Accepted, raising=False,
    )
    try:
        from logosforge.ui.project_settings_dialog import ProjectSettingsDialog
        monkeypatch.setattr(
            ProjectSettingsDialog, "exec",
            lambda self: QDialog.DialogCode.Rejected, raising=False,
        )
    except Exception:
        pass
    yield


@pytest.fixture(autouse=True)
def _reset_event_bus():
    """Give every test a fresh project event bus.

    The bus is a process-global singleton. Headless tests have no Qt
    event loop, so widgets and windows connected to it are never
    destroyed (deleteLater never runs, objects aren't GC'd promptly) and
    their slots would accumulate across tests — every emit would then fan
    out to a growing pile of stale receivers, eventually stalling the
    suite. Resetting the singleton around each test keeps emits scoped to
    that test's own objects.
    """
    from logosforge import project_events
    project_events._INSTANCE = None
    yield
    project_events._INSTANCE = None


@pytest.fixture(autouse=True)
def _reap_top_level_widgets():
    """Destroy every top-level widget a test leaves behind.

    Headless tests have no Qt event loop, so widgets created in a test are
    never closed and ``deleteLater`` never runs — they leak. MainWindow in
    particular installs itself as an *app-wide* event filter
    (``app.installEventFilter(self)``), and Qt only drops that filter when the
    object is destroyed. Across the suite the leaked windows accumulate: with
    N live MainWindows, ``QApplication.setStyleSheet`` (and every other
    app-wide event) fans out through N filters over ~30·N widgets — O(N²). So
    theme/style tests late in the run (e.g. test_assistant_theme_live) degrade
    from milliseconds to minutes and the suite appears to hang.

    Tearing the windows down after each test — drop any app-wide filter,
    schedule deletion, then flush DeferredDelete so the C++ objects actually
    die — keeps the live top-level widget count flat and the suite fast
    (measured: 0 leaked / <1ms vs. 1550 leaked / 14s at N=50). No test relies
    on a widget surviving across test functions: module-scoped fixtures only
    hold the QApplication, which is not a top-level widget.

    Before deleting, any async worker QThread the test left running is joined.
    The UI spawns *parentless* QThread workers (Logos, Assistant, Chat, inline
    edit, outline generation, grammar/style/energy analysis, …) held only as
    widget attributes; deleting the owner widget while its worker is still
    running corrupts memory (access violation on Windows). The leak used to
    mask this — the worker always had live objects to signal — so reaping
    widgets without first joining the workers exposes the race.
    """
    yield
    import gc
    from PySide6.QtCore import QCoreApplication, QEvent, QThread
    app = QApplication.instance()
    if app is None:
        return
    tops = list(app.topLevelWidgets())
    if tops:
        # Join running worker threads first. A gc scan finds them no matter how
        # they're referenced (they're parentless, so findChildren can't reach
        # them). Bounded wait so a genuinely stuck worker can't hang the suite.
        for obj in gc.get_objects():
            if isinstance(obj, QThread):
                try:
                    if obj.isRunning():
                        obj.wait(5000)
                except RuntimeError:
                    pass  # underlying C++ thread already gone
    for w in tops:
        app.removeEventFilter(w)
        w.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)  # delete the widgets now
    # Discard any still-queued posted events WITHOUT delivering them — chiefly
    # stale cross-thread QMetaCallEvents from worker ``done`` signals. We must
    # neither deliver them (``processEvents`` runs those slots against the
    # half-torn-down widgets we just deleted → "C++ object already deleted" /
    # access violation) nor leave them queued (they fire in a LATER test's
    # ``processEvents`` against freed objects — the test_logos_integration:97
    # crash). ``removePostedEvents`` clears them safely, running no slot at all.
    QCoreApplication.removePostedEvents(None)
