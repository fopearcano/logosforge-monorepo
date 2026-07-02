"""Tests for PSYKE Console command registry."""

from logosforge.psyke_command_registry import CommandContext, CommandRegistry
from logosforge.psyke_commands import CommandType, parse


def _noop(ctx: CommandContext) -> None:
    pass


class TestRegistration:
    def test_register_and_resolve(self):
        reg = CommandRegistry()
        reg.register("open", _noop, description="Open entry")
        entry = reg.resolve("open")
        assert entry is not None
        assert entry.name == "open"
        assert entry.handler is _noop

    def test_resolve_missing(self):
        reg = CommandRegistry()
        assert reg.resolve("nope") is None

    def test_has(self):
        reg = CommandRegistry()
        reg.register("create", _noop)
        assert reg.has("create")
        assert not reg.has("destroy")

    def test_case_insensitive(self):
        reg = CommandRegistry()
        reg.register("Open", _noop)
        assert reg.has("open")
        assert reg.resolve("OPEN") is not None

    def test_aliases(self):
        reg = CommandRegistry()
        reg.register("ai", _noop, aliases=["ask", "prompt"])
        assert reg.has("ask")
        assert reg.has("prompt")
        entry = reg.resolve("ask")
        assert entry is not None
        assert entry.name == "ai"

    def test_unregister(self):
        reg = CommandRegistry()
        reg.register("export", _noop, aliases=["save"])
        assert reg.unregister("export")
        assert not reg.has("export")
        assert not reg.has("save")

    def test_unregister_missing(self):
        reg = CommandRegistry()
        assert not reg.unregister("nope")

    def test_all_commands(self):
        reg = CommandRegistry()
        reg.register("a", _noop)
        reg.register("b", _noop)
        reg.register("c", _noop)
        assert len(reg.all_commands()) == 3

    def test_names_sorted(self):
        reg = CommandRegistry()
        reg.register("zebra", _noop)
        reg.register("alpha", _noop)
        assert reg.names == ["alpha", "zebra"]


class TestCategories:
    def test_default_category(self):
        reg = CommandRegistry()
        reg.register("open", _noop)
        entry = reg.resolve("open")
        assert entry.category == "system"

    def test_custom_category(self):
        reg = CommandRegistry()
        reg.register("myplugin", _noop, category="plugin")
        plugins = reg.commands_by_category("plugin")
        assert len(plugins) == 1
        assert plugins[0].name == "myplugin"

    def test_filter_by_category(self):
        reg = CommandRegistry()
        reg.register("open", _noop, category="system")
        reg.register("myplugin", _noop, category="plugin")
        assert len(reg.commands_by_category("system")) == 1
        assert len(reg.commands_by_category("plugin")) == 1


class TestCommandContext:
    def test_first_arg(self):
        ctx = CommandContext(command="create", args=["character", "villain"])
        assert ctx.first_arg == "character"

    def test_first_arg_empty(self):
        ctx = CommandContext(command="help", args=[])
        assert ctx.first_arg == ""

    def test_arg_text(self):
        ctx = CommandContext(command="ai", args=["summarize", "this", "scene"])
        assert ctx.arg_text == "summarize this scene"

    def test_entity_context(self):
        ctx = CommandContext(
            command="open",
            args=[],
            entity_name="Jean Moreau",
            entity_id=42,
        )
        assert ctx.entity_name == "Jean Moreau"
        assert ctx.entity_id == 42


class TestParserWithRegistry:
    def test_plugin_command_recognized(self):
        reg = CommandRegistry()
        reg.register("myplugin", _noop, category="plugin")
        r = parse("/myplugin do-thing", registry=reg)
        assert r.kind == CommandType.SYSTEM
        assert r.command == "myplugin"
        assert r.args == ["do-thing"]

    def test_unknown_still_entity(self):
        reg = CommandRegistry()
        reg.register("open", _noop)
        r = parse("/john open", registry=reg)
        assert r.kind == CommandType.ENTITY
        assert r.command == "john"

    def test_builtin_works_without_registry(self):
        r = parse("/create character")
        assert r.kind == CommandType.SYSTEM

    def test_registry_extends_builtins(self):
        reg = CommandRegistry()
        reg.register("custom", _noop)
        r = parse("/custom arg1", registry=reg)
        assert r.kind == CommandType.SYSTEM
        assert r.command == "custom"
