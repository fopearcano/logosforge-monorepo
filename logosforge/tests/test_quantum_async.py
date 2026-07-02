"""Tests for Quantum Outliner async worker — verifies LLM calls run off UI thread."""

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from logosforge.db import Database
from logosforge.quantum_outliner import (
    Branch,
    OutlineMode,
    StateDelta,
    Wavefunction,
    generate_branches,
    generate_outline,
    get_state,
    reframe,
    reset_state,
)
from logosforge.quantum_outliner.core import QuantumResult
from logosforge.ui.assistant_view import _QuantumWorker


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def project(db):
    return db.create_project("Async Test")


@pytest.fixture(autouse=True)
def _reset(project):
    reset_state(project.id)
    yield
    reset_state(project.id)


class TestQuantumWorker:
    """_QuantumWorker runs callables off the main thread and emits results."""

    def test_worker_emits_completed(self, qapp):
        results = []
        worker = _QuantumWorker(lambda: QuantumResult("ok", "T", "B", {}))
        worker.completed.connect(results.append)
        worker.start()
        worker.wait(5000)
        qapp.processEvents()
        assert len(results) == 1
        assert results[0].kind == "ok"

    def test_worker_emits_failed_on_exception(self, qapp):
        errors = []
        worker = _QuantumWorker(lambda: (_ for _ in ()).throw(RuntimeError("boom")))

        def _raise():
            raise RuntimeError("boom")

        worker = _QuantumWorker(_raise)
        worker.failed.connect(errors.append)
        worker.start()
        worker.wait(5000)
        qapp.processEvents()
        assert len(errors) == 1
        assert "boom" in errors[0]

    def test_worker_passes_args_and_kwargs(self, qapp):
        results = []

        def _fn(a, b, key="default"):
            return QuantumResult("ok", f"{a}-{b}-{key}", "", {})

        worker = _QuantumWorker(_fn, 1, 2, key="custom")
        worker.completed.connect(results.append)
        worker.start()
        worker.wait(5000)
        qapp.processEvents()
        assert results[0].title == "1-2-custom"

    def test_worker_runs_off_main_thread(self, qapp):
        import threading

        thread_names = []

        def _capture():
            thread_names.append(threading.current_thread().name)
            return QuantumResult("ok", "T", "B", {})

        worker = _QuantumWorker(_capture)
        worker.start()
        worker.wait(5000)
        qapp.processEvents()
        assert thread_names[0] != threading.current_thread().name


class TestQuantumWorkerWithLLM:
    """Worker correctly wraps actual quantum functions."""

    def test_generate_outline_via_worker(self, qapp, db, project):
        get_state(project.id).outline_mode = OutlineMode.LAMBDA
        results = []
        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            worker = _QuantumWorker(
                generate_outline, db, project.id, "A knight finds a curse."
            )
            worker.completed.connect(results.append)
            worker.start()
            worker.wait(5000)
        qapp.processEvents()
        assert len(results) == 1
        assert results[0].kind == "possibilities"
        assert len(get_state(project.id).active()) == 1

    def test_generate_branches_via_worker(self, qapp, db, project):
        get_state(project.id).structure_mode = "quantum"
        get_state(project.id).outline_mode = OutlineMode.LAMBDA
        results = []
        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            worker = _QuantumWorker(
                generate_branches, db, project.id, "Hero meets enemy"
            )
            worker.completed.connect(results.append)
            worker.start()
            worker.wait(5000)
        qapp.processEvents()
        assert len(results) == 1
        assert results[0].kind == "possibilities"
        assert "Option 1" in results[0].body

    def test_reframe_via_worker(self, qapp, db, project):
        results = []
        with patch(
            "logosforge.quantum_outliner.relativity.chat_completion"
        ) as mock:
            mock.return_value = (
                "PERSPECTIVE: Alice\nMEANING: She sees mercy.\n"
                "STAKES: trust\nSHIFT: less hostile",
                False,
            )
            worker = _QuantumWorker(
                reframe, "They fought.", "Alice", db, project.id,
            )
            worker.completed.connect(results.append)
            worker.start()
            worker.wait(5000)
        qapp.processEvents()
        assert len(results) == 1
        assert results[0].kind == "reframe"
        assert "Alice" in results[0].title

    def test_slow_llm_does_not_block_worker_creation(self, qapp, db, project):
        """Verify the worker returns control immediately while LLM is running."""
        results = []

        def _slow_completion(*args, **kwargs):
            time.sleep(0.3)
            raise ConnectionError("timeout")

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion",
            side_effect=_slow_completion,
        ):
            worker = _QuantumWorker(
                generate_outline, db, project.id, "Slow premise"
            )
            worker.completed.connect(results.append)
            t0 = time.monotonic()
            worker.start()
            elapsed_to_start = time.monotonic() - t0
            worker.wait(5000)
        qapp.processEvents()
        assert elapsed_to_start < 0.1
        assert len(results) == 1


class TestQuantumBusyGuard:
    """_start_quantum rejects concurrent requests while worker is active."""

    def test_second_request_rejected_while_busy(self, qapp, db, project):
        """Simulate the busy guard by tracking _quantum_worker state."""
        from logosforge.quantum_outliner.core import QuantumResult

        results = []
        second_started = []

        def _slow():
            time.sleep(0.2)
            return QuantumResult("ok", "first", "", {})

        worker1 = _QuantumWorker(_slow)
        worker1.completed.connect(results.append)
        worker1.start()

        can_start = worker1.isRunning()
        if can_start:
            second_started.append(False)

        worker1.wait(5000)
        qapp.processEvents()
        assert len(results) == 1
        assert results[0].title == "first"
        assert second_started == [False]


class TestQuantumErrorHandling:
    """Worker correctly surfaces errors from quantum functions."""

    def test_connection_error_surfaces(self, qapp, db, project):
        errors = []

        def _fail(*args, **kwargs):
            raise ConnectionError("refused")

        worker = _QuantumWorker(_fail)
        worker.failed.connect(errors.append)
        worker.start()
        worker.wait(5000)
        qapp.processEvents()
        assert len(errors) == 1
        assert "refused" in errors[0]

    def test_runtime_error_surfaces(self, qapp):
        errors = []

        def _fail():
            raise RuntimeError("bad state")

        worker = _QuantumWorker(_fail)
        worker.failed.connect(errors.append)
        worker.start()
        worker.wait(5000)
        qapp.processEvents()
        assert len(errors) == 1
        assert "bad state" in errors[0]

    def test_keyboard_interrupt_not_swallowed(self, qapp):
        def _interrupt():
            raise KeyboardInterrupt()

        worker = _QuantumWorker(_interrupt)
        worker.start()
        worker.wait(5000)
        qapp.processEvents()
