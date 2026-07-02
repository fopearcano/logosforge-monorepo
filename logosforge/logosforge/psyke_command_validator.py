"""PSYKE command safety validation — runs before execution.

Checks that a command exists, its arguments are well-formed, and
destructive operations are flagged for user confirmation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from logosforge.psyke_command_registry import CommandRegistry


class ValidationStatus(Enum):
    OK = "ok"
    ERROR = "error"
    CONFIRM = "confirm"


@dataclass(frozen=True)
class ValidationResult:
    status: ValidationStatus
    command: str = ""
    args: list[str] = field(default_factory=list)
    error: str = ""
    confirm_message: str = ""


_DESTRUCTIVE_COMMANDS = frozenset({"delete", "rename"})

_ARG_RULES: dict[str, dict] = {
    "create": {
        "min_args": 1,
        "usage": "/create <type> [name]",
        "valid_first": ("character", "place", "object", "lore", "theme", "other"),
    },
    "open": {
        "min_args": 1,
        "usage": "/open scene <id> | /open psyke <name>",
        "valid_first": ("scene", "psyke"),
    },
    "go": {
        "min_args": 1,
        "usage": "/go scene next|previous|<id>",
        "valid_first": ("scene",),
    },
    "ai": {
        "min_args": 1,
        "usage": "/ai <action>",
    },
    "delete": {
        "min_args": 1,
        "usage": "/delete <name>",
    },
    "rename": {
        "min_args": 1,
        "usage": "/rename <old> to <new>",
    },
    "insert": {
        "min_args": 1,
        "usage": "/insert <name>",
    },
}

_SCENE_ARG_VALID_SECOND = frozenset({"next", "previous", "prev"})


def validate_command(
    command: str,
    args: list[str],
    registry: CommandRegistry | None = None,
) -> ValidationResult:
    """Validate a parsed command before execution.

    Returns ValidationResult with:
    - OK: safe to execute
    - ERROR: blocked, includes error message
    - CONFIRM: destructive, includes confirmation prompt
    """
    command = command.lower()

    known = (registry.has(command) if registry else False) or command in _ARG_RULES
    if not known:
        return ValidationResult(
            status=ValidationStatus.ERROR,
            command=command,
            args=args,
            error=f"Unknown command '/{command}'.",
        )

    rule = _ARG_RULES.get(command)
    if rule:
        result = _check_args(command, args, rule)
        if result is not None:
            return result

    if command in _DESTRUCTIVE_COMMANDS:
        return _build_confirmation(command, args)

    return ValidationResult(
        status=ValidationStatus.OK,
        command=command,
        args=args,
    )


def _check_args(command: str, args: list[str], rule: dict) -> ValidationResult | None:
    min_args = rule.get("min_args", 0)
    if len(args) < min_args:
        return ValidationResult(
            status=ValidationStatus.ERROR,
            command=command,
            args=args,
            error=f"Missing arguments. Usage: {rule['usage']}",
        )

    valid_first = rule.get("valid_first")
    if valid_first and args:
        first = args[0].lower()
        if first not in valid_first:
            options = ", ".join(valid_first)
            return ValidationResult(
                status=ValidationStatus.ERROR,
                command=command,
                args=args,
                error=f"Invalid argument '{args[0]}'. Expected: {options}",
            )

    if command == "open" and args:
        return _validate_open_args(args)

    if command == "go" and args:
        return _validate_go_args(args)

    if command == "rename" and args:
        return _validate_rename_args(args)

    return None


def _validate_open_args(args: list[str]) -> ValidationResult | None:
    target = args[0].lower()
    rest = args[1:]

    if target == "scene":
        if not rest:
            return ValidationResult(
                status=ValidationStatus.ERROR,
                command="open",
                args=args,
                error="Missing scene id. Usage: /open scene <id>",
            )
        try:
            scene_id = int(rest[0])
        except ValueError:
            return ValidationResult(
                status=ValidationStatus.ERROR,
                command="open",
                args=args,
                error=f"Invalid scene id '{rest[0]}'. Must be a number.",
            )
        if scene_id < 1:
            return ValidationResult(
                status=ValidationStatus.ERROR,
                command="open",
                args=args,
                error="Scene id must be positive.",
            )

    if target == "psyke" and not rest:
        return ValidationResult(
            status=ValidationStatus.ERROR,
            command="open",
            args=args,
            error="Missing entry name. Usage: /open psyke <name>",
        )

    return None


def _validate_go_args(args: list[str]) -> ValidationResult | None:
    target = args[0].lower()
    rest = args[1:]

    if target == "scene":
        if not rest:
            return ValidationResult(
                status=ValidationStatus.ERROR,
                command="go",
                args=args,
                error="Missing direction. Usage: /go scene next|previous|<id>",
            )
        direction = rest[0].lower()
        if direction not in _SCENE_ARG_VALID_SECOND:
            try:
                scene_id = int(direction)
            except ValueError:
                return ValidationResult(
                    status=ValidationStatus.ERROR,
                    command="go",
                    args=args,
                    error=f"Invalid direction '{rest[0]}'. Use: next, previous, or a scene id.",
                )
            if scene_id < 1:
                return ValidationResult(
                    status=ValidationStatus.ERROR,
                    command="go",
                    args=args,
                    error="Scene id must be positive.",
                )

    return None


def _validate_rename_args(args: list[str]) -> ValidationResult | None:
    try:
        to_idx = [a.lower() for a in args].index("to")
    except ValueError:
        return ValidationResult(
            status=ValidationStatus.ERROR,
            command="rename",
            args=args,
            error="Missing 'to' keyword. Usage: /rename <old> to <new>",
        )

    old_name = " ".join(args[:to_idx]).strip()
    new_name = " ".join(args[to_idx + 1:]).strip()

    if not old_name:
        return ValidationResult(
            status=ValidationStatus.ERROR,
            command="rename",
            args=args,
            error="Missing original name. Usage: /rename <old> to <new>",
        )
    if not new_name:
        return ValidationResult(
            status=ValidationStatus.ERROR,
            command="rename",
            args=args,
            error="Missing new name. Usage: /rename <old> to <new>",
        )

    return None


def _build_confirmation(command: str, args: list[str]) -> ValidationResult:
    if command == "delete":
        name = " ".join(args)
        return ValidationResult(
            status=ValidationStatus.CONFIRM,
            command=command,
            args=args,
            confirm_message=f"Delete '{name}'? This cannot be undone.",
        )

    if command == "rename":
        try:
            to_idx = [a.lower() for a in args].index("to")
        except ValueError:
            to_idx = len(args)
        old_name = " ".join(args[:to_idx])
        new_name = " ".join(args[to_idx + 1:])
        return ValidationResult(
            status=ValidationStatus.CONFIRM,
            command=command,
            args=args,
            confirm_message=f"Rename '{old_name}' to '{new_name}'?",
        )

    return ValidationResult(
        status=ValidationStatus.CONFIRM,
        command=command,
        args=args,
        confirm_message=f"Execute /{command} {' '.join(args)}?",
    )
