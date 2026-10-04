"""Ownership-scoped cleanup for Qt tests.

The desktop test suite intentionally shares one ``QApplication``.  Tests do
not run its event loop, so any widget or worker they leave behind must be
closed and destroyed explicitly without draining events owned by unrelated
Qt subsystems.
"""

from __future__ import annotations

import gc
import time

import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QThread
from PySide6.QtWidgets import QApplication, QWidget


class QtTestCleanupError(RuntimeError):
    """Raised when test-owned Qt state cannot be destroyed safely."""


_QUARANTINED_OBJECTS: list[QObject] = []


def _is_valid(obj: QObject) -> bool:
    return shiboken6.isValid(obj)


def _parent_depth(obj: QObject) -> int:
    """Return QObject ownership depth, tolerating an invalidated wrapper."""

    depth = 0
    current = obj
    try:
        while _is_valid(current):
            parent = current.parent()
            if parent is None:
                break
            depth += 1
            current = parent
    except RuntimeError:
        pass
    return depth


def _top_level_widgets(app: QApplication) -> list[QWidget]:
    """Snapshot valid top-level widgets, deepest QObject children first."""

    widgets = [widget for widget in app.topLevelWidgets() if _is_valid(widget)]
    widgets.sort(key=_parent_depth, reverse=True)
    return widgets


def _remove_application_filters(
    app: QApplication,
    widgets: list[QWidget],
) -> None:
    for widget in widgets:
        if not _is_valid(widget):
            continue
        try:
            app.removeEventFilter(widget)
        except RuntimeError:
            pass


def _close_and_hide(widgets: list[QWidget]) -> list[Exception]:
    """Run real close hooks child-first, bypassing instance test doubles."""

    errors: list[Exception] = []
    for widget in widgets:
        if not _is_valid(widget):
            continue
        try:
            # Tests sometimes replace ``widget.close``/``widget.hide`` with a
            # counting lambda.  Calling the unbound QWidget methods exercises
            # the real Qt lifecycle while still dispatching virtual
            # ``closeEvent`` implementations.
            QWidget.close(widget)
        except Exception as exc:  # noqa: BLE001 - lifecycle hook under test
            # Constructor-failure tests can leave a partial window whose
            # closeEvent reads attributes that were never created.  One broken
            # close hook must not prevent safe teardown of the other objects.
            errors.append(
                QtTestCleanupError(
                    f"{type(widget).__name__}.close failed: {exc}"
                )
            )
        try:
            if _is_valid(widget):
                QWidget.hide(widget)
        except Exception as exc:  # noqa: BLE001 - lifecycle hook under test
            errors.append(
                QtTestCleanupError(
                    f"{type(widget).__name__}.hide failed: {exc}"
                )
            )
    return errors


def _is_gui_thread(thread: QThread, app: QApplication) -> bool:
    try:
        if thread is app.thread() or thread is QThread.currentThread():
            return True
        is_current = getattr(thread, "isCurrentThread", None)
        return bool(is_current is not None and is_current())
    except RuntimeError:
        return False


def _discover_qthreads(app: QApplication) -> list[QThread]:
    """Find live Python-wrapped QThreads without touching the GUI thread."""

    threads: list[QThread] = []
    seen: set[int] = set()
    for obj in gc.get_objects():
        if not isinstance(obj, QThread):
            continue
        identity = id(obj)
        if identity in seen or not _is_valid(obj):
            continue
        seen.add(identity)
        if _is_gui_thread(obj, app):
            continue
        threads.append(obj)
    return threads


def snapshot_qthreads(app: QApplication) -> tuple[QThread, ...]:
    """Capture wrappers that predate a test and must remain untouched."""

    quarantined_ids = {id(obj) for obj in _QUARANTINED_OBJECTS}
    return tuple(
        thread
        for thread in _discover_qthreads(app)
        if id(thread) not in quarantined_ids
    )


def _thread_label(thread: QThread) -> str:
    try:
        name = thread.objectName()
    except RuntimeError:
        name = ""
    return name or type(thread).__name__


def _stop_running_qthreads(
    app: QApplication,
    *,
    timeout_ms: int,
    preserve_threads: tuple[QThread, ...] = (),
) -> list[QThread]:
    """Cooperatively stop and join every live non-GUI QThread.

    All stop requests are issued before waiting, then a single shared deadline
    bounds teardown.  A timeout is fatal: deleting a widget that owns a live
    worker can corrupt the process, especially on Windows.
    """

    if timeout_ms < 0:
        raise ValueError("timeout_ms must be non-negative")

    quarantined_ids = {id(obj) for obj in _QUARANTINED_OBJECTS}
    preserved_ids = {
        id(thread)
        for thread in preserve_threads
        if id(thread) not in quarantined_ids
    }
    threads = [
        thread
        for thread in _discover_qthreads(app)
        if id(thread) not in preserved_ids
    ]
    running: list[QThread] = []
    for thread in threads:
        try:
            if thread.isRunning():
                running.append(thread)
        except RuntimeError:
            continue

    for thread in running:
        cancel = getattr(thread, "cancel", None)
        if callable(cancel):
            try:
                cancel()
            except (RuntimeError, TypeError):
                pass
        try:
            thread.requestInterruption()
        except RuntimeError:
            pass
        try:
            thread.quit()
        except RuntimeError:
            pass

    if not running:
        return threads

    deadline = time.monotonic() + timeout_ms / 1000
    stuck: list[QThread] = []
    for thread in running:
        if not _is_valid(thread):
            continue
        remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
        try:
            if thread.isRunning():
                thread.wait(remaining_ms)
            if thread.isRunning():
                stuck.append(thread)
        except RuntimeError:
            continue

    if stuck:
        _quarantine([*app.topLevelWidgets(), *threads])
        labels = ", ".join(_thread_label(thread) for thread in stuck)
        raise QtTestCleanupError(
            f"Qt test cleanup timed out after {timeout_ms} ms waiting for: "
            f"{labels}"
        )

    return threads


def _quarantine(objects: list[QObject]) -> None:
    """Keep wrappers alive after a fatal timeout to avoid native destruction."""

    known = {id(obj) for obj in _QUARANTINED_OBJECTS}
    for obj in objects:
        if id(obj) not in known:
            _QUARANTINED_OBJECTS.append(obj)
            known.add(id(obj))


def _clear_safe_quarantine() -> None:
    """Release quarantine only when it contains no running native thread."""

    for obj in _QUARANTINED_OBJECTS:
        if not isinstance(obj, QThread) or not _is_valid(obj):
            continue
        try:
            if obj.isRunning():
                return
        except RuntimeError:
            continue
    _QUARANTINED_OBJECTS.clear()


def _clear_thread_events(threads: list[QThread]) -> None:
    """Discard queued calls and flush deletes for joined worker receivers.

    PySide addresses queued emissions connected to a Python lambda to the
    QThread wrapper itself.  Removing MetaCalls from widget descendants alone
    therefore misses callbacks that capture a soon-to-be-deleted widget.
    """

    for thread in threads:
        if not _is_valid(thread):
            continue
        try:
            QCoreApplication.removePostedEvents(
                thread,
                QEvent.Type.MetaCall,
            )
            QCoreApplication.sendPostedEvents(
                thread,
                QEvent.Type.DeferredDelete,
            )
        except RuntimeError:
            pass


def _ownership_roots(app: QApplication) -> list[QWidget]:
    """Re-snapshot roots after close hooks that may reparent child windows."""

    roots: list[QWidget] = []
    for widget in _top_level_widgets(app):
        try:
            if widget.parent() is None:
                roots.append(widget)
        except RuntimeError:
            continue
    return roots


def _delete_root(app: QApplication, root: QWidget) -> None:
    if not _is_valid(root):
        return

    try:
        app.removeEventFilter(root)
        receivers = [root, *root.findChildren(QObject)]
    except RuntimeError:
        return

    # Queued cross-thread signal deliveries are QMetaCallEvents.  Drop them
    # only for the ownership tree that is about to die.  A blanket
    # removePostedEvents(None) corrupts long-lived Qt subsystems such as
    # QtWebEngine.
    for receiver in receivers:
        if not _is_valid(receiver):
            continue
        try:
            QCoreApplication.removePostedEvents(
                receiver,
                QEvent.Type.MetaCall,
            )
        except RuntimeError:
            pass

    if not _is_valid(root):
        return
    root.deleteLater()
    QCoreApplication.sendPostedEvents(root, QEvent.Type.DeferredDelete)
    if _is_valid(root):
        raise QtTestCleanupError(
            f"Qt test cleanup could not delete ownership root "
            f"{type(root).__name__}"
        )


def cleanup_qt_test_state(
    app: QApplication,
    *,
    thread_wait_ms: int = 5000,
    preserve_threads: tuple[QThread, ...] = (),
) -> None:
    """Close and destroy Qt state left by one test.

    Cleanup is deliberately receiver-scoped.  In particular, it never calls
    ``processEvents()`` or globally flushes posted events.
    """

    app.setQuitOnLastWindowClosed(False)
    widgets = _top_level_widgets(app)
    _remove_application_filters(app, widgets)
    errors = _close_and_hide(widgets)

    threads = _stop_running_qthreads(
        app,
        timeout_ms=thread_wait_ms,
        preserve_threads=preserve_threads,
    )
    _clear_thread_events(threads)

    roots = _ownership_roots(app)
    for root in roots:
        try:
            _delete_root(app, root)
        except Exception as exc:  # noqa: BLE001 - finish remaining roots
            errors.append(exc)

    if errors:
        _quarantine([root for root in roots if _is_valid(root)])
        details = "; ".join(str(error) for error in errors)
        # Root deletion succeeded despite a close/hide hook failure, so any
        # earlier timeout quarantine is now safe to release.
        if not any(_is_valid(root) for root in roots):
            _clear_safe_quarantine()
        raise QtTestCleanupError(
            f"Qt test cleanup encountered {len(errors)} lifecycle failure(s): "
            f"{details}"
        ) from errors[0]

    # A successful pass makes any wrappers retained by an earlier, recovered
    # timeout safe to release.  Invalid wrappers are harmless Python shells;
    # stopped live wrappers no longer threaten QThread destruction.
    _clear_safe_quarantine()
