"""Regression contracts for ownership-scoped Qt test cleanup."""

from __future__ import annotations

import threading

import pytest
import shiboken6
from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QObject,
    QThread,
    Signal,
    Slot,
)
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QDialog, QWidget

from tests.helpers import qt_cleanup
from tests.helpers.qt_cleanup import QtTestCleanupError, cleanup_qt_test_state


def _delete_later_now(obj: QObject) -> None:
    if not shiboken6.isValid(obj):
        return
    obj.deleteLater()
    QCoreApplication.sendPostedEvents(obj, QEvent.Type.DeferredDelete)


def test_reaper_flushes_only_owned_deferred_deletes(qapp: QApplication):
    roots = [QWidget(), QWidget()]
    for root in roots:
        root.show()

    sentinel = QObject()
    destroyed: list[bool] = []
    sentinel.destroyed.connect(lambda: destroyed.append(True))
    sentinel.deleteLater()

    try:
        cleanup_qt_test_state(qapp)

        assert all(not shiboken6.isValid(root) for root in roots)
        assert shiboken6.isValid(sentinel)
        assert destroyed == []
    finally:
        _delete_later_now(sentinel)


def test_reaper_closes_parented_top_level_child_first(qapp: QApplication):
    trace: list[str] = []

    class _Root(QWidget):
        def closeEvent(self, event: QCloseEvent) -> None:
            trace.append("root")
            event.accept()

    class _Child(QDialog):
        def closeEvent(self, event: QCloseEvent) -> None:
            trace.append("child")
            event.accept()

    root = _Root()
    child = _Child(root)
    root.show()
    child.show()
    assert child.parent() is root
    assert child in qapp.topLevelWidgets()

    cleanup_qt_test_state(qapp)

    assert trace == ["child", "root"]
    assert not shiboken6.isValid(child)
    assert not shiboken6.isValid(root)


def test_reaper_forces_hidden_vetoed_window_to_be_deleted(qapp: QApplication):
    close_calls: list[bool] = []

    class _Veto(QWidget):
        def closeEvent(self, event: QCloseEvent) -> None:
            close_calls.append(True)
            event.ignore()

    root = _Veto()
    root.show()

    cleanup_qt_test_state(qapp)

    assert close_calls == [True]
    assert not shiboken6.isValid(root)


def test_reaper_isolates_close_failure_and_deletes_every_root(
    qapp: QApplication,
):
    trace: list[str] = []

    class _BrokenRoot(QWidget):
        def closeEvent(self, event: QCloseEvent) -> None:
            raise RuntimeError("partial-window close failure")

    class _NormalRoot(QWidget):
        def closeEvent(self, event: QCloseEvent) -> None:
            trace.append("normal-close")
            event.accept()

    broken = _BrokenRoot()
    normal = _NormalRoot()
    broken.show()
    normal.show()

    with pytest.raises(
        QtTestCleanupError,
        match="partial-window close failure",
    ):
        cleanup_qt_test_state(qapp)

    assert trace == ["normal-close"]
    assert not shiboken6.isValid(broken)
    assert not shiboken6.isValid(normal)


def test_reaper_removes_application_filter_before_close(qapp: QApplication):
    probe_type = QEvent.Type(QEvent.registerEventType())
    trace: list[str] = []
    receiver = QObject()

    class _FilterRoot(QWidget):
        def eventFilter(self, watched: QObject, event: QEvent) -> bool:
            if event.type() == probe_type:
                trace.append("filter")
            return False

        def closeEvent(self, event: QCloseEvent) -> None:
            trace.append("close")
            QCoreApplication.sendEvent(receiver, QEvent(probe_type))
            event.accept()

    root = _FilterRoot()
    qapp.installEventFilter(root)
    QCoreApplication.sendEvent(receiver, QEvent(probe_type))
    assert trace == ["filter"]
    trace.clear()

    try:
        cleanup_qt_test_state(qapp)
        assert trace == ["close"]

        QCoreApplication.sendEvent(receiver, QEvent(probe_type))
        assert trace == ["close"]
    finally:
        _delete_later_now(receiver)


def test_reaper_never_stops_or_waits_on_gui_thread(
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
):
    gui_thread = qapp.thread()
    root = QWidget()
    root.show()
    calls: list[str] = []

    monkeypatch.setattr(
        gui_thread,
        "requestInterruption",
        lambda: calls.append("interrupt"),
    )
    monkeypatch.setattr(gui_thread, "quit", lambda: calls.append("quit"))
    monkeypatch.setattr(
        gui_thread,
        "wait",
        lambda *_args: calls.append("wait") or False,
    )

    cleanup_qt_test_state(qapp, thread_wait_ms=1)

    assert calls == []
    assert shiboken6.isValid(gui_thread)
    assert gui_thread.isRunning()
    assert not shiboken6.isValid(root)


def test_thread_shutdown_requests_every_worker_before_waiting(
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
):
    trace: list[tuple[str, str, int | None]] = []

    class _FakeRunningThread(QThread):
        def __init__(self, name: str) -> None:
            super().__init__()
            self._name = name
            self._running = True

        def isRunning(self) -> bool:
            return self._running

        def requestInterruption(self) -> None:
            trace.append((self._name, "interrupt", None))

        def quit(self) -> None:
            trace.append((self._name, "quit", None))

        def wait(self, timeout: int) -> bool:
            trace.append((self._name, "wait", timeout))
            self._running = False
            return True

    first = _FakeRunningThread("first")
    second = _FakeRunningThread("second")
    monotonic = iter((100.0, 100.1, 100.4))
    monkeypatch.setattr(
        qt_cleanup,
        "_discover_qthreads",
        lambda _app: [first, second],
    )
    monkeypatch.setattr(qt_cleanup.time, "monotonic", lambda: next(monotonic))

    try:
        found = qt_cleanup._stop_running_qthreads(qapp, timeout_ms=1000)

        assert found == [first, second]
        assert [operation for _, operation, _ in trace[:4]] == [
            "interrupt",
            "quit",
            "interrupt",
            "quit",
        ]
        waits = [timeout for _, operation, timeout in trace if operation == "wait"]
        assert len(waits) == 2
        assert waits[0] is not None and waits[1] is not None
        assert 0 <= waits[1] < waits[0] <= 1000
    finally:
        _delete_later_now(first)
        _delete_later_now(second)


def test_reaper_preserves_preexisting_qthread(qapp: QApplication):
    baseline = QThread()
    baseline.start()
    root = QWidget()
    root.show()

    try:
        cleanup_qt_test_state(qapp, preserve_threads=(baseline,))

        assert baseline.isRunning()
        assert not baseline.isInterruptionRequested()
        assert not shiboken6.isValid(root)
    finally:
        baseline.quit()
        assert baseline.wait(2000)
        _delete_later_now(baseline)


def test_reaper_joins_cooperative_thread_before_deleting_root(
    qapp: QApplication,
):
    started = threading.Event()
    trace: list[str] = []

    class _CooperativeThread(QThread):
        def run(self) -> None:
            started.set()
            while not self.isInterruptionRequested():
                self.msleep(1)
            trace.append("thread-finished")

    root = QWidget()
    root.show()
    root.destroyed.connect(lambda: trace.append("root-destroyed"))
    worker = _CooperativeThread()
    root.worker = worker
    worker.start()
    assert started.wait(1)

    try:
        cleanup_qt_test_state(qapp, thread_wait_ms=1000)

        assert not worker.isRunning()
        assert not shiboken6.isValid(root)
        assert trace.index("thread-finished") < trace.index("root-destroyed")
    finally:
        if shiboken6.isValid(worker) and worker.isRunning():
            worker.requestInterruption()
            worker.wait(2000)


def test_reaper_calls_worker_cancel_hook_before_join(qapp: QApplication):
    started = threading.Event()
    release = threading.Event()
    cancelled: list[bool] = []

    class _CancelOnlyThread(QThread):
        def cancel(self) -> None:
            cancelled.append(True)
            release.set()

        def run(self) -> None:
            started.set()
            release.wait()

    root = QWidget()
    root.show()
    worker = _CancelOnlyThread()
    root.worker = worker
    worker.start()
    assert started.wait(1)

    try:
        cleanup_qt_test_state(qapp, thread_wait_ms=1000)

        assert cancelled == [True]
        assert not worker.isRunning()
        assert not shiboken6.isValid(root)
    finally:
        release.set()
        if shiboken6.isValid(worker) and worker.isRunning():
            worker.wait(2000)


def test_reaper_drops_python_lambda_metacall_from_joined_thread(
    qapp: QApplication,
):
    delivered: list[bool] = []

    class _EmittingThread(QThread):
        done = Signal()

        def run(self) -> None:
            self.done.emit()

    root = QWidget()
    root.show()
    worker = _EmittingThread()
    root.worker = worker
    worker.done.connect(lambda: delivered.append(True))
    worker.start()
    assert worker.wait(2000)
    assert delivered == []

    cleanup_qt_test_state(qapp)
    QCoreApplication.sendPostedEvents(worker, QEvent.Type.MetaCall)

    assert delivered == []
    assert not shiboken6.isValid(root)


def test_reaper_preserves_unrelated_receiver_metacall(qapp: QApplication):
    delivered: list[bool] = []

    class _Receiver(QObject):
        @Slot()
        def receive(self) -> None:
            delivered.append(True)

    class _Emitter(QThread):
        emitted = Signal()

        def run(self) -> None:
            self.emitted.emit()

    receiver = _Receiver()
    emitter = _Emitter()
    emitter.emitted.connect(receiver.receive)
    emitter.start()
    assert emitter.wait(2000)
    assert delivered == []
    root = QWidget()
    root.show()

    try:
        cleanup_qt_test_state(qapp)
        assert delivered == []

        QCoreApplication.sendPostedEvents(receiver, QEvent.Type.MetaCall)
        assert delivered == [True]
        assert not shiboken6.isValid(root)
    finally:
        _delete_later_now(receiver)
        _delete_later_now(emitter)


def test_reaper_aborts_before_deleting_owner_of_stubborn_thread(
    qapp: QApplication,
):
    started = threading.Event()
    release = threading.Event()

    class _StubbornThread(QThread):
        def run(self) -> None:
            started.set()
            release.wait()

    root = QWidget()
    root.show()
    destroyed: list[bool] = []
    root.destroyed.connect(lambda: destroyed.append(True))
    worker = _StubbornThread()
    worker.setObjectName("stubborn-worker")
    root.worker = worker
    worker.start()
    assert started.wait(1)

    try:
        with pytest.raises(
            QtTestCleanupError,
            match=r"timed out.*stubborn-worker",
        ):
            cleanup_qt_test_state(qapp, thread_wait_ms=10)

        assert shiboken6.isValid(root)
        assert not root.isVisible()
        assert worker.isRunning()
        assert destroyed == []
        assert worker not in qt_cleanup.snapshot_qthreads(qapp)
    finally:
        release.set()
        assert worker.wait(2000)
        if shiboken6.isValid(root):
            cleanup_qt_test_state(qapp, thread_wait_ms=1000)


def test_reaper_skips_invalid_qthread_wrapper(qapp: QApplication):
    dead_thread = QThread()
    shiboken6.delete(dead_thread)
    assert not shiboken6.isValid(dead_thread)

    root = QWidget()
    root.dead_thread = dead_thread
    root.show()

    cleanup_qt_test_state(qapp)

    assert not shiboken6.isValid(root)
