#!/usr/bin/env python3
"""Verify that every declared Mach-O deployment target fits a macOS floor."""

from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path


Version = tuple[int, int, int]
DescribeFile = Callable[[Path], str]
ReadLoadCommands = Callable[[Path], str]
VERSION_PATTERN = re.compile(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?")


@dataclass(frozen=True)
class DeploymentTargetViolation:
    path: str
    version: str


@dataclass(frozen=True)
class DeploymentTargetScan:
    macho_count: int
    target_count: int
    highest_target: Version
    too_new: tuple[DeploymentTargetViolation, ...]


def deployment_targets(load_commands: str) -> list[str]:
    """Extract macOS targets without mistaking linker tool versions for them."""
    current_command: str | None = None
    targets: list[str] = []
    for raw_line in load_commands.splitlines():
        line = raw_line.strip()
        if line.startswith("Load command "):
            current_command = None
        elif line.startswith("cmd "):
            current_command = line.split(maxsplit=1)[1]
        elif current_command == "LC_BUILD_VERSION" and line.startswith("minos "):
            targets.append(line.split(maxsplit=1)[1])
        elif current_command == "LC_VERSION_MIN_MACOSX" and line.startswith("version "):
            targets.append(line.split(maxsplit=1)[1])
    return targets


def parse_version(value: str) -> Version:
    match = VERSION_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError(f"unparseable macOS deployment target: {value!r}")
    major, minor, patch = (int(piece or 0) for piece in match.groups())
    return major, minor, patch


def format_version(version: Version) -> str:
    return ".".join(str(piece) for piece in version)


def _describe_file(path: Path) -> str:
    return subprocess.run(
        ["file", "-b", str(path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _read_load_commands(path: Path) -> str:
    return subprocess.run(
        ["otool", "-l", str(path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def scan_bundle(
    root: Path,
    maximum_supported: Version,
    *,
    describe_file: DescribeFile = _describe_file,
    read_load_commands: ReadLoadCommands = _read_load_commands,
) -> DeploymentTargetScan:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"application bundle is not a directory: {root}")

    macho_count = 0
    target_count = 0
    highest_target: Version = (0, 0, 0)
    too_new: list[DeploymentTargetViolation] = []

    for candidate in sorted(root.rglob("*")):
        if candidate.is_symlink() or not candidate.is_file():
            continue
        if "Mach-O" not in describe_file(candidate):
            continue

        macho_count += 1
        relative = str(candidate.relative_to(root))
        for value in deployment_targets(read_load_commands(candidate)):
            try:
                parsed = parse_version(value)
            except ValueError as exc:
                raise ValueError(f"{exc} in {relative}") from exc
            highest_target = max(highest_target, parsed)
            target_count += 1
            if parsed > maximum_supported:
                too_new.append(DeploymentTargetViolation(relative, value))

    return DeploymentTargetScan(
        macho_count=macho_count,
        target_count=target_count,
        highest_target=highest_target,
        too_new=tuple(too_new),
    )


def validate_scan(scan: DeploymentTargetScan, maximum_supported: Version) -> None:
    if scan.macho_count == 0:
        raise ValueError("no Mach-O files were found in the packaged application")
    if scan.target_count == 0:
        raise ValueError("no Mach-O deployment targets could be verified")
    if scan.too_new:
        details = "\n".join(
            f"  - {violation.path}: macOS {violation.version}"
            for violation in scan.too_new
        )
        raise ValueError(
            "Mach-O deployment targets newer than macOS "
            f"{format_version(maximum_supported)}:\n{details}"
        )


def _fixture(target: str, *, legacy: bool = False) -> str:
    if legacy:
        return f"""
Load command 1
          cmd LC_VERSION_MIN_MACOSX
      cmdsize 16
      version {target}
          sdk 13.3
"""
    return f"""
Load command 1
          cmd LC_BUILD_VERSION
      cmdsize 32
       platform MACOS
          minos {target}
            sdk 15.0
         ntools 1
           tool LD
        version 820.1
"""


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_self_test() -> None:
    parser_fixture = _fixture("13.0") + _fixture("12.6", legacy=True)
    _expect(
        deployment_targets(parser_fixture) == ["13.0", "12.6"],
        "load-command parser confused a linker version with a macOS target",
    )
    _expect(parse_version("12") == (12, 0, 0), "major-only version failed")
    _expect(parse_version("12.6") == (12, 6, 0), "two-part version failed")
    _expect(parse_version("12.6.1") == (12, 6, 1), "three-part version failed")
    try:
        parse_version("12.0-beta")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid deployment target was accepted")

    with tempfile.TemporaryDirectory(prefix="logosforge-macho-scan-self-test-") as temp:
        root = (Path(temp) / "LogosForge Whiteboard.app").resolve()
        executable = root / "Contents" / "MacOS" / "LogosForge Whiteboard"
        helper = root / "Contents" / "Frameworks" / "Helper"
        text_file = root / "Contents" / "Resources" / "notice.txt"
        for path in (executable, helper, text_file):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture")

        linked_helper = root / "Contents" / "Frameworks" / "Helper Link"
        try:
            linked_helper.symlink_to(helper)
        except OSError:
            linked_helper = None

        descriptions = {
            executable: "Mach-O 64-bit executable x86_64",
            helper: "Mach-O 64-bit executable x86_64",
            text_file: "ASCII text",
        }
        commands = {
            executable: _fixture("12.0.0"),
            helper: _fixture("12.1", legacy=True),
        }
        described: list[Path] = []

        def describe(path: Path) -> str:
            described.append(path)
            return descriptions[path]

        scan = scan_bundle(
            root,
            (12, 0, 0),
            describe_file=describe,
            read_load_commands=commands.__getitem__,
        )
        _expect(scan.macho_count == 2, "Mach-O file count is incorrect")
        _expect(scan.target_count == 2, "deployment-target count is incorrect")
        _expect(scan.highest_target == (12, 1, 0), "highest target is incorrect")
        _expect(
            scan.too_new
            == (
                DeploymentTargetViolation(
                    str(helper.relative_to(root)),
                    "12.1",
                ),
            ),
            "newer target or relative path was not reported correctly",
        )
        _expect(text_file in described, "regular non-Mach-O file was not inspected")
        if linked_helper is not None:
            _expect(linked_helper not in described, "symbolic link was followed")

        try:
            validate_scan(scan, (12, 0, 0))
        except ValueError as exc:
            _expect(
                str(helper.relative_to(root)) in str(exc),
                "validation error omitted the relative path",
            )
        else:
            raise AssertionError("newer deployment target was accepted")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", nargs="?", type=Path, help="unpacked macOS .app bundle")
    parser.add_argument(
        "--maximum",
        default="12.0.0",
        help="newest allowed deployment target (default: 12.0.0)",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="exercise parser and path handling without macOS tools",
    )
    args = parser.parse_args(argv)
    if args.self_test and args.app is not None:
        parser.error("app cannot be supplied with --self-test")
    if not args.self_test and args.app is None:
        parser.error("app is required unless --self-test is used")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.self_test:
        run_self_test()
        print("Mach-O deployment-target scanner self-test passed.")
        return 0

    try:
        maximum = parse_version(args.maximum)
        scan = scan_bundle(args.app, maximum)
        validate_scan(scan, maximum)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    print(
        f"verified {scan.macho_count} Mach-O files "
        f"({scan.target_count} target declarations); highest deployment target "
        f"{format_version(scan.highest_target)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
