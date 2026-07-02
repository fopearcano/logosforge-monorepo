"""Tests for PSYKE Console command parser."""

from logosforge.psyke_commands import CommandType, ParsedCommand, parse


class TestPlainSearch:
    def test_plain_text_is_search(self):
        r = parse("jean")
        assert r.kind == CommandType.SEARCH
        assert r.command == "jean"
        assert r.args == []

    def test_multi_word_search(self):
        r = parse("sword of light")
        assert r.kind == CommandType.SEARCH
        assert r.command == "sword of light"

    def test_empty_string(self):
        r = parse("")
        assert r.kind == CommandType.SEARCH
        assert r.command == ""

    def test_whitespace_only(self):
        r = parse("   ")
        assert r.kind == CommandType.SEARCH
        assert r.command == ""

    def test_slash_alone(self):
        r = parse("/")
        assert r.kind == CommandType.SEARCH
        assert r.command == ""


class TestSystemCommands:
    def test_create(self):
        r = parse("/create character")
        assert r.kind == CommandType.SYSTEM
        assert r.command == "create"
        assert r.args == ["character"]

    def test_open(self):
        r = parse("/open")
        assert r.kind == CommandType.SYSTEM
        assert r.command == "open"
        assert r.args == []

    def test_go_with_target(self):
        r = parse("/go scenes")
        assert r.kind == CommandType.SYSTEM
        assert r.command == "go"
        assert r.args == ["scenes"]

    def test_ai_with_prompt(self):
        r = parse("/ai summarize this chapter")
        assert r.kind == CommandType.SYSTEM
        assert r.command == "ai"
        assert r.args == ["summarize", "this", "chapter"]

    def test_help(self):
        r = parse("/help")
        assert r.kind == CommandType.SYSTEM
        assert r.command == "help"

    def test_case_insensitive(self):
        r = parse("/CREATE character")
        assert r.kind == CommandType.SYSTEM
        assert r.command == "create"

    def test_delete(self):
        r = parse("/delete")
        assert r.kind == CommandType.SYSTEM
        assert r.command == "delete"

    def test_rename(self):
        r = parse("/rename New Name")
        assert r.kind == CommandType.SYSTEM
        assert r.command == "rename"
        assert r.args == ["New", "Name"]

    def test_link(self):
        r = parse("/link scene-3")
        assert r.kind == CommandType.SYSTEM
        assert r.command == "link"
        assert r.args == ["scene-3"]

    def test_export(self):
        r = parse("/export pdf")
        assert r.kind == CommandType.SYSTEM
        assert r.command == "export"
        assert r.args == ["pdf"]


class TestEntityCommands:
    def test_entity_with_action(self):
        r = parse("/john open")
        assert r.kind == CommandType.ENTITY
        assert r.command == "john"
        assert r.args == ["open"]

    def test_entity_alone(self):
        r = parse("/mary")
        assert r.kind == CommandType.ENTITY
        assert r.command == "mary"
        assert r.args == []

    def test_entity_multiple_args(self):
        r = parse("/palazzo link scene-5")
        assert r.kind == CommandType.ENTITY
        assert r.command == "palazzo"
        assert r.args == ["link", "scene-5"]

    def test_entity_is_lowercased(self):
        r = parse("/Jean")
        assert r.kind == CommandType.ENTITY
        assert r.command == "jean"

    def test_entity_default_action_is_insert(self):
        r = parse("/john")
        assert r.kind == CommandType.ENTITY
        assert r.args == []

    def test_entity_open_action(self):
        r = parse("/john open")
        assert r.kind == CommandType.ENTITY
        assert r.command == "john"
        assert r.first_arg == "open"

    def test_entity_insert_action(self):
        r = parse("/john insert")
        assert r.kind == CommandType.ENTITY
        assert r.command == "john"
        assert r.first_arg == "insert"

    def test_insert_is_system_command(self):
        r = parse("/insert")
        assert r.kind == CommandType.SYSTEM
        assert r.command == "insert"


class TestParsedCommand:
    def test_first_arg_present(self):
        r = parse("/create character")
        assert r.first_arg == "character"

    def test_first_arg_missing(self):
        r = parse("/help")
        assert r.first_arg == ""

    def test_raw_preserved(self):
        r = parse("  /ai hello  ")
        assert r.raw == "  /ai hello  "
