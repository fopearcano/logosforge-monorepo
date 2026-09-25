#!/usr/bin/env python3
"""Verify that every Mach-O deployment target fits a macOS floor."""

from __future__ import annotations

import argparse
import re
import struct
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO


Version = tuple[int, int, int]
VERSION_PATTERN = re.compile(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?")

LC_VERSION_MIN_MACOSX = 0x24
LC_BUILD_VERSION = 0x32
PLATFORM_MACOS = 1
_MAX_FAT_ARCHITECTURES = 4096
_MAX_LOAD_COMMANDS = 65536
_MAX_LOAD_COMMAND_BYTES = 64 * 1024 * 1024

_THIN_MAGICS: dict[bytes, tuple[str, bool]] = {
    b"\xfe\xed\xfa\xce": (">", False),
    b"\xce\xfa\xed\xfe": ("<", False),
    b"\xfe\xed\xfa\xcf": (">", True),
    b"\xcf\xfa\xed\xfe": ("<", True),
}
_FAT_MAGICS: dict[bytes, tuple[str, bool]] = {
    b"\xca\xfe\xba\xbe": (">", False),
    b"\xbe\xba\xfe\xca": ("<", False),
    b"\xca\xfe\xba\xbf": (">", True),
    b"\xbf\xba\xfe\xca": ("<", True),
}


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


class _BinaryReader:
    """Bounds-checked random access to one file without loading it into memory."""

    def __init__(self, stream: BinaryIO, size: int) -> None:
        self.stream = stream
        self.size = size

    def read(self, offset: int, size: int, description: str) -> bytes:
        if offset < 0 or size < 0 or offset > self.size - size:
            raise ValueError(
                f"{description} extends beyond the file "
                f"(offset {offset}, size {size}, file size {self.size})"
            )
        self.stream.seek(offset)
        value = self.stream.read(size)
        if len(value) != size:
            raise ValueError(f"could not read complete {description}")
        return value


def parse_version(value: str) -> Version:
    match = VERSION_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError(f"unparseable macOS deployment target: {value!r}")
    major, minor, patch = (int(piece or 0) for piece in match.groups())
    return major, minor, patch


def format_version(version: Version) -> str:
    return ".".join(str(piece) for piece in version)


def _decode_packed_version(value: int) -> Version:
    return value >> 16, (value >> 8) & 0xFF, value & 0xFF


def _is_structurally_valid_java_class(reader: _BinaryReader) -> bool:
    """Disambiguate Java's CAFEBABE magic from a big-endian fat Mach-O."""

    def unsigned(offset: int, size: int, description: str) -> int:
        return int.from_bytes(reader.read(offset, size, description), "big")

    def advance(offset: int, size: int) -> int:
        if size < 0 or offset > reader.size - size:
            raise ValueError("Java class structure extends beyond the file")
        return offset + size

    def attributes(offset: int, count: int) -> int:
        for _ in range(count):
            attribute_length = unsigned(offset + 2, 4, "Java attribute header")
            offset = advance(offset, 6)
            offset = advance(offset, attribute_length)
        return offset

    def members(offset: int, count: int) -> int:
        for _ in range(count):
            attribute_count = unsigned(offset + 6, 2, "Java member header")
            offset = advance(offset, 8)
            offset = attributes(offset, attribute_count)
        return offset

    try:
        if reader.size < 10:
            return False
        minor_version = unsigned(4, 2, "Java minor version")
        major_version = unsigned(6, 2, "Java major version")
        # Java class-file versions begin at 45. Preview classes use minor 65535.
        if not 45 <= major_version <= 100:
            return False
        if minor_version not in (0, 3, 65535) and major_version >= 56:
            return False

        pool_count = unsigned(8, 2, "Java constant-pool count")
        if pool_count == 0:
            return False
        cursor = 10
        pool_index = 1
        while pool_index < pool_count:
            tag = unsigned(cursor, 1, "Java constant-pool tag")
            cursor = advance(cursor, 1)
            if tag == 1:  # CONSTANT_Utf8
                length = unsigned(cursor, 2, "Java UTF-8 constant length")
                cursor = advance(cursor, 2)
                cursor = advance(cursor, length)
            elif tag in (3, 4):  # Integer, Float
                cursor = advance(cursor, 4)
            elif tag in (5, 6):  # Long, Double (occupy two pool slots)
                cursor = advance(cursor, 8)
                pool_index += 1
                if pool_index >= pool_count:
                    return False
            elif tag in (7, 8, 16, 19, 20):
                cursor = advance(cursor, 2)
            elif tag in (9, 10, 11, 12, 17, 18):
                cursor = advance(cursor, 4)
            elif tag == 15:
                cursor = advance(cursor, 3)
            else:
                return False
            pool_index += 1

        cursor = advance(cursor, 6)  # access_flags, this_class, super_class
        interface_count = unsigned(cursor, 2, "Java interface count")
        cursor = advance(cursor, 2)
        cursor = advance(cursor, interface_count * 2)
        field_count = unsigned(cursor, 2, "Java field count")
        cursor = advance(cursor, 2)
        cursor = members(cursor, field_count)
        method_count = unsigned(cursor, 2, "Java method count")
        cursor = advance(cursor, 2)
        cursor = members(cursor, method_count)
        attribute_count = unsigned(cursor, 2, "Java class attribute count")
        cursor = advance(cursor, 2)
        cursor = attributes(cursor, attribute_count)
        return cursor == reader.size
    except ValueError:
        return False


def _parse_thin_slice(
    reader: _BinaryReader,
    offset: int,
    size: int,
    *,
    label: str,
) -> list[Version]:
    if size < 4:
        raise ValueError(f"{label} is too small for a Mach-O magic")
    magic = reader.read(offset, 4, f"{label} magic")
    encoding = _THIN_MAGICS.get(magic)
    if encoding is None:
        if magic in _FAT_MAGICS:
            raise ValueError(f"{label} contains a nested fat Mach-O wrapper")
        raise ValueError(f"{label} is not a thin Mach-O image")

    endian, is_64_bit = encoding
    header_size = 32 if is_64_bit else 28
    if size < header_size:
        raise ValueError(f"{label} has a truncated Mach-O header")
    header = struct.unpack(
        f"{endian}{'8I' if is_64_bit else '7I'}",
        reader.read(offset, header_size, f"{label} header"),
    )
    command_count = header[4]
    command_bytes = header[5]
    command_start = offset + header_size
    slice_end = offset + size
    if command_bytes > slice_end - command_start:
        raise ValueError(f"{label} load-command region extends beyond the slice")
    if command_count > _MAX_LOAD_COMMANDS:
        raise ValueError(
            f"{label} declares an unreasonable number of load commands: "
            f"{command_count}"
        )
    if command_bytes > _MAX_LOAD_COMMAND_BYTES:
        raise ValueError(
            f"{label} declares an unreasonable load-command region: "
            f"{command_bytes} bytes"
        )
    if command_count > command_bytes // 8:
        raise ValueError(
            f"{label} declares {command_count} load commands in only "
            f"{command_bytes} bytes"
        )

    command_end = command_start + command_bytes
    cursor = command_start
    targets: list[Version] = []
    command_alignment = 8 if is_64_bit else 4
    for index in range(command_count):
        if cursor > command_end - 8:
            raise ValueError(f"{label} load command {index} has no complete header")
        command, command_size = struct.unpack(
            f"{endian}2I",
            reader.read(cursor, 8, f"{label} load command {index} header"),
        )
        if command_size < 8:
            raise ValueError(
                f"{label} load command {index} has invalid size {command_size}"
            )
        if command_size % command_alignment:
            raise ValueError(
                f"{label} load command {index} size {command_size} is not "
                f"{command_alignment}-byte aligned"
            )
        if command_size > command_end - cursor:
            raise ValueError(f"{label} load command {index} extends beyond its region")

        if command == LC_BUILD_VERSION:
            if command_size < 24:
                raise ValueError(f"{label} LC_BUILD_VERSION command is truncated")
            fields = struct.unpack(
                f"{endian}6I",
                reader.read(cursor, 24, f"{label} LC_BUILD_VERSION command"),
            )
            platform, minimum_os, tool_count = fields[2], fields[3], fields[5]
            expected_size = 24 + tool_count * 8
            if command_size != expected_size:
                raise ValueError(
                    f"{label} LC_BUILD_VERSION has size {command_size}, "
                    f"expected {expected_size} for {tool_count} tools"
                )
            if platform == PLATFORM_MACOS:
                targets.append(_decode_packed_version(minimum_os))
        elif command == LC_VERSION_MIN_MACOSX:
            if command_size != 16:
                raise ValueError(
                    f"{label} LC_VERSION_MIN_MACOSX has size {command_size}, "
                    "expected 16"
                )
            fields = struct.unpack(
                f"{endian}4I",
                reader.read(cursor, 16, f"{label} LC_VERSION_MIN_MACOSX command"),
            )
            targets.append(_decode_packed_version(fields[2]))

        cursor += command_size

    if cursor != command_end:
        raise ValueError(
            f"{label} load commands consume {cursor - command_start} bytes, "
            f"but the header declares {command_bytes}"
        )
    if not targets:
        raise ValueError(f"{label} has no macOS deployment-target load command")
    return targets


def _parse_fat_file(
    reader: _BinaryReader,
    *,
    endian: str,
    is_64_bit: bool,
) -> list[Version]:
    if reader.size < 8:
        raise ValueError("fat Mach-O header is truncated")
    architecture_count = struct.unpack(
        f"{endian}I", reader.read(4, 4, "fat Mach-O architecture count")
    )[0]
    if architecture_count == 0:
        raise ValueError("fat Mach-O contains no architecture slices")
    if architecture_count > _MAX_FAT_ARCHITECTURES:
        raise ValueError(
            "fat Mach-O declares an unreasonable number of architecture slices: "
            f"{architecture_count}"
        )

    entry_size = 32 if is_64_bit else 20
    if architecture_count > (reader.size - 8) // entry_size:
        raise ValueError("fat Mach-O architecture table extends beyond the file")
    table_end = 8 + architecture_count * entry_size
    slices: list[tuple[int, int, int]] = []
    for index in range(architecture_count):
        entry_offset = 8 + index * entry_size
        entry = reader.read(entry_offset, entry_size, f"fat architecture {index}")
        if is_64_bit:
            _, _, slice_offset, slice_size, alignment, reserved = struct.unpack(
                f"{endian}IIQQII", entry
            )
            if reserved != 0:
                raise ValueError(f"fat architecture {index} has nonzero reserved data")
            maximum_alignment = 63
        else:
            _, _, slice_offset, slice_size, alignment = struct.unpack(
                f"{endian}IIIII", entry
            )
            maximum_alignment = 31

        if slice_size == 0:
            raise ValueError(f"fat architecture {index} has an empty slice")
        if slice_offset < table_end:
            raise ValueError(f"fat architecture {index} overlaps its architecture table")
        if slice_offset > reader.size - slice_size:
            raise ValueError(f"fat architecture {index} extends beyond the file")
        if alignment > maximum_alignment:
            raise ValueError(
                f"fat architecture {index} has invalid alignment exponent {alignment}"
            )
        if slice_offset % (1 << alignment):
            raise ValueError(
                f"fat architecture {index} offset {slice_offset} does not satisfy "
                f"its 2^{alignment} alignment"
            )
        slices.append((slice_offset, slice_size, index))

    previous_end = table_end
    for slice_offset, slice_size, index in sorted(slices):
        if slice_offset < previous_end:
            raise ValueError(f"fat architecture {index} overlaps another slice")
        previous_end = slice_offset + slice_size

    targets: list[Version] = []
    for slice_offset, slice_size, index in slices:
        targets.extend(
            _parse_thin_slice(
                reader,
                slice_offset,
                slice_size,
                label=f"fat architecture {index}",
            )
        )
    return targets


def _read_macho_targets(path: Path) -> list[Version] | None:
    size = path.stat().st_size
    if size < 4:
        return None
    with path.open("rb") as stream:
        reader = _BinaryReader(stream, size)
        magic = reader.read(0, 4, "file magic")
        if magic in _THIN_MAGICS:
            return _parse_thin_slice(reader, 0, size, label="Mach-O image")
        fat_encoding = _FAT_MAGICS.get(magic)
        if fat_encoding is None:
            return None
        endian, is_64_bit = fat_encoding
        try:
            return _parse_fat_file(reader, endian=endian, is_64_bit=is_64_bit)
        except ValueError:
            if magic == b"\xca\xfe\xba\xbe" and _is_structurally_valid_java_class(
                reader
            ):
                return None
            raise


def scan_bundle(root: Path, maximum_supported: Version) -> DeploymentTargetScan:
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
        relative = str(candidate.relative_to(root))
        try:
            targets = _read_macho_targets(candidate)
        except ValueError as exc:
            raise ValueError(f"malformed Mach-O file {relative}: {exc}") from exc
        if targets is None:
            continue

        macho_count += 1
        for parsed in targets:
            value = format_version(parsed)
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


def _packed_version(version: Version) -> int:
    major, minor, patch = version
    return (major << 16) | (minor << 8) | patch


def _thin_fixture(
    version: Version,
    *,
    endian: str,
    is_64_bit: bool,
    legacy: bool = False,
    platform: int = PLATFORM_MACOS,
    leading_commands: Sequence[bytes] = (),
) -> bytes:
    magic = 0xFEEDFACF if is_64_bit else 0xFEEDFACE
    if legacy:
        target_command = struct.pack(
            f"{endian}4I",
            LC_VERSION_MIN_MACOSX,
            16,
            _packed_version(version),
            _packed_version((15, 0, 0)),
        )
    else:
        target_command = struct.pack(
            f"{endian}6I",
            LC_BUILD_VERSION,
            24,
            platform,
            _packed_version(version),
            _packed_version((15, 0, 0)),
            0,
        )
    commands = b"".join((*leading_commands, target_command))
    header_values = [
        magic,
        0x01000007 if is_64_bit else 7,
        3,
        2,
        len(leading_commands) + 1,
        len(commands),
        0,
    ]
    if is_64_bit:
        header_values.append(0)
    header = struct.pack(
        f"{endian}{'8I' if is_64_bit else '7I'}", *header_values
    )
    return header + commands


def _java_class_fixture() -> bytes:
    utf_name = b"Fixture"
    utf_object = b"java/lang/Object"
    constant_pool = b"".join(
        (
            b"\x01" + struct.pack(">H", len(utf_name)) + utf_name,
            b"\x07" + struct.pack(">H", 1),
            b"\x01" + struct.pack(">H", len(utf_object)) + utf_object,
            b"\x07" + struct.pack(">H", 3),
        )
    )
    return b"".join(
        (
            b"\xca\xfe\xba\xbe",
            struct.pack(">HHH", 0, 61, 5),
            constant_pool,
            struct.pack(">HHHHHHH", 0x21, 2, 4, 0, 0, 0, 0),
        )
    )


def _fat_fixture(
    slices: Sequence[bytes],
    *,
    endian: str,
    is_64_bit: bool,
) -> bytes:
    magic = 0xCAFEBABF if is_64_bit else 0xCAFEBABE
    entry_size = 32 if is_64_bit else 20
    cursor = 8 + len(slices) * entry_size
    entries: list[bytes] = []
    payload = bytearray()
    for index, slice_data in enumerate(slices):
        slice_offset = cursor + len(payload)
        if is_64_bit:
            entry = struct.pack(
                f"{endian}IIQQII",
                0x01000007,
                index + 3,
                slice_offset,
                len(slice_data),
                0,
                0,
            )
        else:
            entry = struct.pack(
                f"{endian}IIIII",
                0x01000007,
                index + 3,
                slice_offset,
                len(slice_data),
                0,
            )
        entries.append(entry)
        payload.extend(slice_data)
    return (
        struct.pack(f"{endian}2I", magic, len(slices))
        + b"".join(entries)
        + bytes(payload)
    )


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _expect_scan_error(root: Path, fragment: str) -> None:
    try:
        scan_bundle(root, (12, 0, 0))
    except ValueError as exc:
        _expect(fragment in str(exc), f"error omitted {fragment!r}: {exc}")
    else:
        raise AssertionError(f"invalid Mach-O fixture was accepted ({fragment})")


def run_self_test() -> None:
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
        contents = root / "Contents"
        contents.mkdir(parents=True)

        thin_encodings = (("<", False), (">", False), ("<", True), (">", True))
        for index, (endian, is_64_bit) in enumerate(thin_encodings):
            leading_commands: tuple[bytes, ...] = ()
            if index == 0:
                leading_commands = (
                    struct.pack(f"{endian}4I", 0x80000033, 16, 0, 0),
                    struct.pack(f"{endian}4I", 0x80000034, 16, 0, 0),
                )
            (contents / f"thin-{index}").write_bytes(
                _thin_fixture(
                    (12, 0, 0),
                    endian=endian,
                    is_64_bit=is_64_bit,
                    legacy=index % 2 == 1,
                    leading_commands=leading_commands,
                )
            )

        fat_encodings = (("<", False), (">", False), ("<", True), (">", True))
        for index, (endian, is_64_bit) in enumerate(fat_encodings):
            (contents / f"fat-{index}").write_bytes(
                _fat_fixture(
                    (
                        _thin_fixture(
                            (11, 7, 0), endian="<", is_64_bit=True
                        ),
                        _thin_fixture(
                            (12, 0, 0),
                            endian=">",
                            is_64_bit=False,
                            legacy=True,
                        ),
                    ),
                    endian=endian,
                    is_64_bit=is_64_bit,
                )
            )

        notice = contents / "notice.txt"
        notice.write_text("not a Mach-O file", encoding="utf-8")
        (contents / "Fixture.class").write_bytes(_java_class_fixture())
        link = contents / "thin-link"
        try:
            link.symlink_to(contents / "thin-0")
        except OSError:
            link = None

        scan = scan_bundle(root, (12, 0, 0))
        _expect(scan.macho_count == 8, "Mach-O file count is incorrect")
        _expect(scan.target_count == 12, "Mach-O slice/target count is incorrect")
        _expect(scan.highest_target == (12, 0, 0), "highest target is incorrect")
        _expect(not scan.too_new, "supported target was reported as too new")
        validate_scan(scan, (12, 0, 0))
        if link is not None:
            _expect(scan.macho_count == 8, "symbolic link was followed")

    with tempfile.TemporaryDirectory(prefix="logosforge-macho-too-new-") as temp:
        root = Path(temp) / "Too New.app"
        binary = root / "Contents" / "MacOS" / "Too New"
        binary.parent.mkdir(parents=True)
        binary.write_bytes(
            _fat_fixture(
                (
                    _thin_fixture((12, 0, 0), endian="<", is_64_bit=True),
                    _thin_fixture((13, 1, 2), endian=">", is_64_bit=False),
                ),
                endian=">",
                is_64_bit=False,
            )
        )
        scan = scan_bundle(root, (12, 0, 0))
        expected_path = str(binary.relative_to(root))
        _expect(
            scan.too_new
            == (DeploymentTargetViolation(expected_path, "13.1.2"),),
            "newer target or relative path was not reported correctly",
        )
        try:
            validate_scan(scan, (12, 0, 0))
        except ValueError as exc:
            _expect("13.1.2" in str(exc), "validation error omitted target")
        else:
            raise AssertionError("newer deployment target was accepted")

    zero_size_command = bytearray(
        _thin_fixture((12, 0, 0), endian="<", is_64_bit=True)
    )
    struct.pack_into("<I", zero_size_command, 36, 0)
    malformed_fixtures = (
        (b"\xcf\xfa\xed\xfe", "truncated Mach-O header"),
        (bytes(zero_size_command), "invalid size 0"),
        (
            _thin_fixture((12, 0, 0), endian="<", is_64_bit=True)[:-1],
            "load-command region extends beyond the slice",
        ),
        (
            _fat_fixture(
                (_thin_fixture((12, 0, 0), endian="<", is_64_bit=True),),
                endian=">",
                is_64_bit=False,
            )[:-1],
            "extends beyond the file",
        ),
    )
    for index, (fixture, fragment) in enumerate(malformed_fixtures):
        with tempfile.TemporaryDirectory(prefix="logosforge-macho-malformed-") as temp:
            root = Path(temp) / "Malformed.app"
            binary = root / "Contents" / f"bad-{index}"
            binary.parent.mkdir(parents=True)
            binary.write_bytes(fixture)
            _expect_scan_error(root, fragment)

    with tempfile.TemporaryDirectory(prefix="logosforge-macho-missing-target-") as temp:
        root = Path(temp) / "Missing Target.app"
        binary = root / "Contents" / "foreign-platform"
        binary.parent.mkdir(parents=True)
        binary.write_bytes(
            _thin_fixture(
                (12, 0, 0),
                endian="<",
                is_64_bit=True,
                platform=2,
            )
        )
        _expect_scan_error(root, "has no macOS deployment-target load command")


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
        help="exercise the pure-Python parser without macOS tools",
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
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    print(
        f"verified {scan.macho_count} Mach-O files "
        f"({scan.target_count} target declarations); highest deployment target "
        f"{format_version(scan.highest_target)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
