"""PSYKE Console command registry — central dispatch table for all commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

CommandHandler = Callable[["CommandContext"], Any]


@dataclass
class CommandContext:
    """Passed to every command handler at execution time."""

    command: str
    args: list[str]
    entity_name: str | None = None
    entity_id: int | None = None
    raw: str = ""

    @property
    def first_arg(self) -> str:
        return self.args[0] if self.args else ""

    @property
    def arg_text(self) -> str:
        return " ".join(self.args)

    def arg_text_after(self, index: int) -> str:
        return " ".join(self.args[index:]) if index < len(self.args) else ""


@dataclass
class CommandEntry:
    """A registered command with metadata."""

    name: str
    handler: CommandHandler
    description: str = ""
    category: str = "system"
    aliases: list[str] = field(default_factory=list)


class CommandRegistry:
    """Extensible registry of console commands.

    Usage:
        registry = CommandRegistry()
        registry.register("open", handler, description="Open an entry")
        registry.register("ai", ai_handler, aliases=["ask"])

        # Plugins extend at runtime:
        registry.register("myplugin", plugin_handler, category="plugin")
    """

    def __init__(self) -> None:
        self._commands: dict[str, CommandEntry] = {}
        self._aliases: dict[str, str] = {}

    def register(
        self,
        name: str,
        handler: CommandHandler,
        *,
        description: str = "",
        category: str = "system",
        aliases: list[str] | None = None,
    ) -> None:
        name = name.lower()
        entry = CommandEntry(
            name=name,
            handler=handler,
            description=description,
            category=category,
            aliases=aliases or [],
        )
        self._commands[name] = entry
        for alias in entry.aliases:
            self._aliases[alias.lower()] = name

    def unregister(self, name: str) -> bool:
        name = name.lower()
        entry = self._commands.pop(name, None)
        if entry is None:
            return False
        for alias in entry.aliases:
            self._aliases.pop(alias.lower(), None)
        return True

    def resolve(self, name: str) -> CommandEntry | None:
        name = name.lower()
        if name in self._commands:
            return self._commands[name]
        canonical = self._aliases.get(name)
        if canonical:
            return self._commands.get(canonical)
        return None

    def has(self, name: str) -> bool:
        return self.resolve(name) is not None

    def all_commands(self) -> list[CommandEntry]:
        return list(self._commands.values())

    def commands_by_category(self, category: str) -> list[CommandEntry]:
        return [e for e in self._commands.values() if e.category == category]

    @property
    def names(self) -> list[str]:
        return sorted(self._commands.keys())
