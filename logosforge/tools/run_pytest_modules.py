"""Run every pytest module in a fresh Python process.

The desktop test suite creates and destroys thousands of Qt objects. Keeping
all modules in one interpreter can make a native lifetime bug in one module
surface much later as an unhelpful crash in an unrelated test. This runner
preserves normal within-module pytest behavior while giving each module a clean
QApplication and native heap.

Only the standard library is imported here. In particular, the parent process
must never import pytest, PySide6, or application code.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEST_ROOT = CORE_ROOT / "tests"


@dataclass(frozen=True)
class ModuleFailure:
    """One pytest child process that did not exit successfully."""

    module: Path
    returncode: int
    stdout: str = ""
    stderr: str = ""


def _module_sort_key(path: Path) -> str:
    """Return a stable, platform-independent ordering key."""

    return path.as_posix().casefold()


def unique_sorted_modules(modules: Iterable[Path]) -> list[Path]:
    """Normalize module paths so every file is launched exactly once."""

    return sorted({Path(module) for module in modules}, key=_module_sort_key)


def discover_test_modules(test_root: Path = DEFAULT_TEST_ROOT) -> list[Path]:
    """Discover pytest's two default Python test-module name patterns."""

    root = Path(test_root)
    modules = unique_sorted_modules(
        path
        for pattern in ("test_*.py", "*_test.py")
        for path in root.rglob(pattern)
        if path.is_file()
    )
    if not modules:
        raise RuntimeError(f"No pytest modules found under {root}")
    return modules


def build_pytest_command(
    module: Path,
    *,
    python_executable: str = sys.executable,
    extra_pytest_args: Sequence[str] = (),
) -> list[str]:
    """Build the isolated child command for one test module."""

    return [
        python_executable,
        "-X",
        "faulthandler",
        "-m",
        "pytest",
        "-q",
        "--tb=short",
        "-p",
        "no:cacheprovider",
        *extra_pytest_args,
        Path(module).as_posix(),
    ]


def describe_returncode(returncode: int) -> str:
    """Render ordinary exits, POSIX signals, and Windows NTSTATUS failures."""

    if returncode < 0:
        return f"{returncode} (signal {-returncode})"
    if returncode > 255:
        return f"{returncode} (0x{returncode & 0xFFFFFFFF:08X})"
    return str(returncode)


def run_test_modules(
    modules: Iterable[Path],
    *,
    cwd: Path = CORE_ROOT,
    python_executable: str = sys.executable,
    extra_pytest_args: Sequence[str] = (),
    process_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    emit: Callable[[str], None] | None = None,
) -> list[ModuleFailure]:
    """Run all modules sequentially and return every child-process failure.

    Output from successful modules is suppressed to keep CI logs compact.
    Failed child output is replayed in full, including faulthandler diagnostics.
    The loop deliberately continues after failures so a native crash cannot
    prevent the remaining modules from being covered.
    """

    ordered = unique_sorted_modules(modules)
    if not ordered:
        raise RuntimeError("No pytest modules were provided")

    launch = process_runner or subprocess.run
    report = emit or (lambda message: print(message, flush=True))
    child_env = os.environ.copy()
    child_env["PYTHONFAULTHANDLER"] = "1"

    failures: list[ModuleFailure] = []
    total = len(ordered)
    for index, module in enumerate(ordered, start=1):
        try:
            display_path = module.relative_to(cwd).as_posix()
        except ValueError:
            display_path = module.as_posix()
        report(f"[{index:03d}/{total:03d}] {display_path}")
        started = time.monotonic()
        completed = launch(
            build_pytest_command(
                Path(display_path),
                python_executable=python_executable,
                extra_pytest_args=extra_pytest_args,
            ),
            cwd=Path(cwd),
            env=child_env,
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
        )
        elapsed = time.monotonic() - started
        if completed.returncode == 0:
            report(f"           pass ({elapsed:.1f}s)")
            continue

        failure = ModuleFailure(
            module=module,
            returncode=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )
        failures.append(failure)
        report(
            f"           FAIL ({elapsed:.1f}s, exit "
            f"{describe_returncode(completed.returncode)})"
        )
        if failure.stdout.strip():
            report(f"--- stdout: {display_path} ---\n{failure.stdout.rstrip()}")
        if failure.stderr.strip():
            report(f"--- stderr: {display_path} ---\n{failure.stderr.rstrip()}")

    return failures


def main() -> int:
    started = time.monotonic()
    modules = discover_test_modules()
    failures = run_test_modules(modules)
    elapsed = time.monotonic() - started
    if failures:
        print(
            f"FAILED: {len(failures)} of {len(modules)} test modules failed "
            f"after {elapsed:.1f}s:",
            flush=True,
        )
        for failure in failures:
            print(
                f"  {failure.module.relative_to(CORE_ROOT).as_posix()}: "
                f"exit {describe_returncode(failure.returncode)}",
                flush=True,
            )
        return 1

    print(
        f"PASS: all {len(modules)} test modules completed in {elapsed:.1f}s.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
