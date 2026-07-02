"""Tests for intent-to-command mapping and integration with command system."""

import pytest

from logosforge.psyke_commands import CommandType, parse as parse_command
from logosforge.psyke_intents import Intent, detect_intent, intent_to_command


class TestIntentToCommand:
    """Verify intent_to_command produces valid slash-command strings."""

    def test_open_scene(self):
        intent = Intent("open_scene", {"id": 3})
        assert intent_to_command(intent) == "/open scene 3"

    def test_open_entry(self):
        intent = Intent("open_entry", {"name": "John"})
        assert intent_to_command(intent) == "/open psyke John"

    def test_create_entry_with_name(self):
        intent = Intent("create_entry", {"entry_type": "character", "name": "john"})
        assert intent_to_command(intent) == "/create character john"

    def test_create_entry_no_name(self):
        intent = Intent("create_entry", {"entry_type": "place", "name": ""})
        assert intent_to_command(intent) == "/create place"

    def test_go_scene_direction(self):
        intent = Intent("go_scene", {"direction": "next"})
        assert intent_to_command(intent) == "/go scene next"

    def test_go_scene_previous(self):
        intent = Intent("go_scene", {"direction": "previous"})
        assert intent_to_command(intent) == "/go scene previous"

    def test_go_scene_by_id(self):
        intent = Intent("go_scene", {"id": 7})
        assert intent_to_command(intent) == "/go scene 7"

    def test_insert_entity(self):
        intent = Intent("insert_entity", {"name": "john"})
        assert intent_to_command(intent) == "/insert john"

    def test_ai_action(self):
        intent = Intent("ai_action", {"action": "rewrite"})
        assert intent_to_command(intent) == "/ai rewrite"

    def test_delete_entry(self):
        intent = Intent("delete_entry", {"name": "John"})
        assert intent_to_command(intent) == "/delete John"

    def test_rename_entry(self):
        intent = Intent("rename_entry", {"name": "John", "new_name": "Jonathan"})
        assert intent_to_command(intent) == "/rename John to Jonathan"

    def test_unknown_action_returns_none(self):
        intent = Intent("unknown_thing", {"foo": "bar"})
        assert intent_to_command(intent) is None


class TestIntentProducesSameParseResult:
    """Verify that NL input → intent → command string → parse
    gives the same result as typing the slash command directly."""

    @pytest.mark.parametrize("nl_input,slash_command", [
        ("open scene 3", "/open scene 3"),
        ("open scene 142", "/open scene 142"),
        ("create character john", "/create character john"),
        ("new place The Dark Forest", "/create place The Dark Forest"),
        ("go to next scene", "/go scene next"),
        ("goto previous scene", "/go scene previous"),
        ("go to scene 5", "/go scene 5"),
        ("rewrite", "/ai rewrite"),
        ("expand", "/ai expand"),
        ("summarize", "/ai summarize"),
        ("ai rewrite", "/ai rewrite"),
        ("insert john", "/insert john"),
        ("delete John", "/delete John"),
    ])
    def test_nl_matches_slash(self, nl_input, slash_command):
        intent = detect_intent(nl_input)
        assert intent is not None, f"No intent detected for: {nl_input}"

        cmd_str = intent_to_command(intent)
        assert cmd_str is not None, f"No command mapping for intent: {intent}"

        parsed_from_intent = parse_command(cmd_str)
        parsed_from_slash = parse_command(slash_command)

        assert parsed_from_intent.kind == parsed_from_slash.kind
        assert parsed_from_intent.command == parsed_from_slash.command
        assert parsed_from_intent.args == parsed_from_slash.args


class TestEndToEndWithHandlers:
    """Verify that intents route through the same system command handlers."""

    @pytest.fixture
    def db(self, tmp_path):
        from logosforge.db import Database
        return Database(str(tmp_path / "test.db"))

    @pytest.fixture
    def project(self, db):
        return db.create_project("Test")

    @pytest.fixture
    def handlers(self, db, project):
        from logosforge.psyke_command_registry import CommandContext, CommandRegistry
        from logosforge.psyke_system_commands import SystemCommandHandlers

        registry = CommandRegistry()
        h = SystemCommandHandlers(db, project.id)
        h.register_all(registry)
        return registry

    def _execute_nl(self, text: str, registry):
        """Simulate: NL → intent → command → parse → dispatch."""
        from logosforge.psyke_command_registry import CommandContext

        intent = detect_intent(text)
        assert intent is not None
        cmd_str = intent_to_command(intent)
        assert cmd_str is not None
        parsed = parse_command(cmd_str)
        assert parsed.kind == CommandType.SYSTEM

        entry = registry.resolve(parsed.command)
        assert entry is not None
        ctx = CommandContext(command=parsed.command, args=parsed.args)
        return entry.handler(ctx)

    def _execute_slash(self, text: str, registry):
        """Simulate: slash command → parse → dispatch."""
        from logosforge.psyke_command_registry import CommandContext

        parsed = parse_command(text)
        assert parsed.kind == CommandType.SYSTEM

        entry = registry.resolve(parsed.command)
        assert entry is not None
        ctx = CommandContext(command=parsed.command, args=parsed.args)
        return entry.handler(ctx)

    def test_create_character_same_result(self, handlers):
        nl_result = self._execute_nl("create character Alice", handlers)
        slash_result = self._execute_slash("/create character Bob", handlers)

        assert nl_result["ok"] == slash_result["ok"]
        assert nl_result["type"] == "character"
        assert slash_result["type"] == "character"
        assert nl_result["name"] == "Alice"
        assert slash_result["name"] == "Bob"

    def test_create_place_same_result(self, handlers):
        nl_result = self._execute_nl("new place Castle", handlers)
        assert nl_result["ok"] is True
        assert nl_result["type"] == "place"
        assert nl_result["name"] == "Castle"

    def test_go_scene_no_scenes(self, handlers):
        nl_result = self._execute_nl("go to next scene", handlers)
        slash_result = self._execute_slash("/go scene next", handlers)
        assert nl_result == slash_result

    def test_open_scene_not_found(self, handlers):
        nl_result = self._execute_nl("open scene 999", handlers)
        slash_result = self._execute_slash("/open scene 999", handlers)
        assert nl_result["ok"] is False
        assert slash_result["ok"] is False

    def test_ai_no_handler(self, handlers):
        nl_result = self._execute_nl("rewrite", handlers)
        slash_result = self._execute_slash("/ai rewrite", handlers)
        assert nl_result == slash_result


class TestInsertEntityIntent:
    """Insert maps to /insert which is a SYSTEM command in the parser."""

    def test_insert_parses_as_system(self):
        intent = detect_intent("insert john")
        cmd_str = intent_to_command(intent)
        parsed = parse_command(cmd_str)
        assert parsed.kind == CommandType.SYSTEM
        assert parsed.command == "insert"
        assert parsed.args == ["john"]

    def test_insert_multiword(self):
        intent = detect_intent("insert Sword of Light")
        cmd_str = intent_to_command(intent)
        parsed = parse_command(cmd_str)
        assert parsed.command == "insert"
        assert parsed.args == ["Sword", "of", "Light"]
