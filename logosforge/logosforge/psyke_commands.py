"""PSYKE Console command parser — turns free-form input into structured commands."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from logosforge.psyke_command_registry import CommandRegistry


class CommandType(Enum):
    SEARCH = "search"
    ENTITY = "entity"
    SYSTEM = "system"


_BUILTIN_COMMANDS = frozenset({
    "create",
    "open",
    "go",
    "ai",
    "delete",
    "rename",
    "link",
    "export",
    "help",
    "insert",
})


@dataclass(frozen=True)
class ParsedCommand:
    kind: CommandType
    command: str
    args: list[str]
    raw: str

    @property
    def first_arg(self) -> str:
        return self.args[0] if self.args else ""


def parse(raw_input: str, registry: CommandRegistry | None = None) -> ParsedCommand:
    """Parse console input into a structured command.

    Formats:
        "jean"              → SEARCH for "jean"
        "/create character" → SYSTEM command "create" with args ["character"]
        "/john open"        → ENTITY command "john" with action ["open"]
        "/ai summarize"     → SYSTEM command "ai" with args ["summarize"]

    If a registry is provided, it is used to resolve commands (including
    plugin-registered ones). Otherwise falls back to the builtin set.
    """
    text = raw_input.strip()
    if not text:
        return ParsedCommand(kind=CommandType.SEARCH, command="", args=[], raw=raw_input)

    if not text.startswith("/"):
        return ParsedCommand(kind=CommandType.SEARCH, command=text, args=[], raw=raw_input)

    body = text[1:]
    if not body:
        return ParsedCommand(kind=CommandType.SEARCH, command="", args=[], raw=raw_input)

    parts = body.split()
    head = parts[0].lower()
    tail = parts[1:]

    is_system = (
        (registry.has(head) if registry else False)
        or head in _BUILTIN_COMMANDS
    )

    if is_system:
        return ParsedCommand(
            kind=CommandType.SYSTEM,
            command=head,
            args=tail,
            raw=raw_input,
        )

    return ParsedCommand(
        kind=CommandType.ENTITY,
        command=head,
        args=tail,
        raw=raw_input,
    )
