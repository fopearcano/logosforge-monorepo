"""Tests for the process-isolated pytest module runner."""

from __future__ import annotations

import subprocess
from pathlib import Path

from tools import run_pytest_modules as runner


def test_discovery_uses_pytest_patterns_recursively_and_deduplicates(tmp_path):
    tests = tmp_path / "tests"
    nested = tests / "nested"
    nested.mkdir(parents=True)
    expected = [
        tests / "alpha_test.py",
        tests / "test_alpha.py",
        nested / "test_nested_test.py",  # matches both supported patterns
    ]
    for path in [*expected, tests / "helper.py"]:
        path.write_text("", encoding="utf-8")

    assert runner.discover_test_modules(tests) == sorted(
        expected, key=lambda path: path.as_posix().casefold(),
    )


def test_command_uses_same_python_faulthandler_and_quiet_pytest():
    command = runner.build_pytest_command(
        Path("tests/test_example.py"),
        python_executable="chosen-python",
        extra_pytest_args=("-k", "focused"),
    )

    assert command == [
        "chosen-python",
        "-X",
        "faulthandler",
        "-m",
        "pytest",
        "-q",
        "--tb=short",
        "-p",
        "no:cacheprovider",
        "-k",
        "focused",
        "tests/test_example.py",
    ]


def test_runner_launches_sorted_modules_exactly_once(tmp_path):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "passed", "")

    modules = [
        Path("tests/test_zeta.py"),
        Path("tests/test_alpha.py"),
        Path("tests/test_zeta.py"),
    ]
    messages = []
    failures = runner.run_test_modules(
        modules,
        cwd=tmp_path,
        python_executable="python-under-test",
        process_runner=fake_run,
        emit=messages.append,
    )

    assert failures == []
    assert [call[0][-1] for call in calls] == [
        "tests/test_alpha.py",
        "tests/test_zeta.py",
    ]
    assert all(call[1]["cwd"] == tmp_path for call in calls)
    assert all(call[1]["capture_output"] is True for call in calls)
    assert all(call[1]["env"]["PYTHONFAULTHANDLER"] == "1" for call in calls)


def test_runner_aggregates_failures_and_continues_after_native_crash(tmp_path):
    calls = []
    outcomes = {
        "tests/test_alpha.py": (1, "assertion output", ""),
        "tests/test_beta.py": (3221226356, "", "heap corruption"),
        "tests/test_gamma.py": (0, "passed", ""),
    }

    def fake_run(command, **kwargs):
        calls.append(command[-1])
        code, stdout, stderr = outcomes[command[-1]]
        return subprocess.CompletedProcess(command, code, stdout, stderr)

    messages = []
    failures = runner.run_test_modules(
        [Path(path) for path in reversed(outcomes)],
        cwd=tmp_path,
        process_runner=fake_run,
        emit=messages.append,
    )

    assert calls == sorted(outcomes)
    assert [(failure.module.as_posix(), failure.returncode) for failure in failures] == [
        ("tests/test_alpha.py", 1),
        ("tests/test_beta.py", 3221226356),
    ]
    rendered = "\n".join(messages)
    assert "assertion output" in rendered
    assert "heap corruption" in rendered
    assert "0xC0000374" in rendered


def test_main_returns_failure_when_any_child_failed(monkeypatch, capsys):
    module = runner.CORE_ROOT / "tests" / "test_failed.py"
    failure = runner.ModuleFailure(module, 3221226356)
    monkeypatch.setattr(runner, "discover_test_modules", lambda: [module])
    monkeypatch.setattr(runner, "run_test_modules", lambda modules: [failure])

    assert runner.main() == 1
    output = capsys.readouterr().out
    assert "FAILED: 1 of 1 test modules failed" in output
    assert "0xC0000374" in output
