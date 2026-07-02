"""Tests for dual input mode: both /commands and natural language."""

import pytest

from logosforge.db import Database
from logosforge.psyke_command_registry import CommandContext, CommandRegistry
from logosforge.psyke_commands import CommandType, parse as parse_command
from logosforge.psyke_intents import detect_intent, intent_to_command
from logosforge.psyke_search import PsykeSearchIndex
from logosforge.psyke_suggestions import Suggestion, suggest
from logosforge.psyke_system_commands import SystemCommandHandlers


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def project(db):
    return db.create_project("Test")


@pytest.fixture
def registry(db, project):
    reg = CommandRegistry()
    handlers = SystemCommandHandlers(db, project.id)
    handlers.register_all(reg)
    return reg


@pytest.fixture
def index(db, project):
    db.create_psyke_entry(project.id, "John", "character")
    db.create_psyke_entry(project.id, "Castle", "place")
    return PsykeSearchIndex(db, project.id)


def _dispatch(text: str, registry: CommandRegistry) -> dict | None:
    """Simulate full console dispatch for any input format."""
    parsed = parse_command(text)

    if parsed.kind == CommandType.SYSTEM:
        entry = registry.resolve(parsed.command)
        if entry is None:
            return None
        ctx = CommandContext(command=parsed.command, args=parsed.args)
        return entry.handler(ctx)

    if parsed.kind == CommandType.SEARCH:
        intent = detect_intent(text)
        if intent is None:
            return None
        cmd_str = intent_to_command(intent)
        if cmd_str is None:
            return None
        return _dispatch(cmd_str, registry)

    return None


class TestBothFormatsIdentical:
    """Slash commands and natural language produce the same handler result."""

    def test_create_character(self, registry):
        slash_result = _dispatch("/create character Alice", registry)
        nl_result = _dispatch("create character Alice", registry)
        assert slash_result["ok"] == nl_result["ok"]
        assert slash_result["type"] == nl_result["type"]
        assert slash_result["name"] == nl_result["name"]

    def test_create_place(self, registry):
        slash_result = _dispatch("/create place Forest", registry)
        nl_result = _dispatch("new place Forest", registry)
        assert slash_result["ok"] == nl_result["ok"]
        assert slash_result["type"] == nl_result["type"]
        assert slash_result["name"] == nl_result["name"]

    def test_open_scene_not_found(self, registry):
        slash_result = _dispatch("/open scene 999", registry)
        nl_result = _dispatch("open scene 999", registry)
        assert slash_result == nl_result

    def test_go_scene_next(self, registry):
        slash_result = _dispatch("/go scene next", registry)
        nl_result = _dispatch("go to next scene", registry)
        assert slash_result == nl_result

    def test_go_scene_previous(self, registry):
        slash_result = _dispatch("/go scene previous", registry)
        nl_result = _dispatch("goto previous scene", registry)
        assert slash_result == nl_result

    def test_go_scene_by_id(self, registry):
        slash_result = _dispatch("/go scene 5", registry)
        nl_result = _dispatch("go to scene 5", registry)
        assert slash_result == nl_result

    def test_ai_rewrite(self, registry):
        slash_result = _dispatch("/ai rewrite", registry)
        nl_result = _dispatch("rewrite", registry)
        assert slash_result == nl_result

    def test_ai_expand(self, registry):
        slash_result = _dispatch("/ai expand", registry)
        nl_result = _dispatch("expand", registry)
        assert slash_result == nl_result

    def test_ai_summarize(self, registry):
        slash_result = _dispatch("/ai summarize", registry)
        nl_result = _dispatch("summarize", registry)
        assert slash_result == nl_result


class TestSlashCommandStillWorks:
    """Existing slash command behavior is not broken."""

    def test_create_returns_ok(self, registry):
        result = _dispatch("/create character Hero", registry)
        assert result["ok"] is True
        assert result["type"] == "character"
        assert result["name"] == "Hero"

    def test_unknown_type_returns_error(self, registry):
        result = _dispatch("/create alien Bob", registry)
        assert result["ok"] is False
        assert "Unknown type" in result["error"]

    def test_open_invalid_scene(self, registry):
        result = _dispatch("/open scene abc", registry)
        assert result["ok"] is False

    def test_go_unknown_direction(self, registry):
        result = _dispatch("/go scene sideways", registry)
        assert result["ok"] is False

    def test_unregistered_command(self, registry):
        result = _dispatch("/unknown thing", registry)
        assert result is None


class TestNaturalLanguageFallback:
    """When no intent matches, returns None (search mode)."""

    def test_random_text(self, registry):
        result = _dispatch("hello world", registry)
        assert result is None

    def test_partial_keyword(self, registry):
        result = _dispatch("ope scene", registry)
        assert result is None

    def test_empty(self, registry):
        result = _dispatch("", registry)
        assert result is None


class TestSuggestionsShowIntents:
    """Dropdown suggestions include detected intents for NL input."""

    def test_open_scene_shows_intent(self, index, registry):
        results = suggest("open scene 3", index, registry=registry)
        intent_results = [r for r in results if r.category == "intent"]
        assert len(intent_results) == 1
        assert intent_results[0].text == "/open scene 3"

    def test_create_character_shows_intent(self, index, registry):
        results = suggest("create character Alice", index, registry=registry)
        intent_results = [r for r in results if r.category == "intent"]
        assert len(intent_results) == 1
        assert intent_results[0].text == "/create character Alice"

    def test_go_next_shows_intent(self, index, registry):
        results = suggest("go to next scene", index, registry=registry)
        intent_results = [r for r in results if r.category == "intent"]
        assert len(intent_results) == 1
        assert intent_results[0].text == "/go scene next"

    def test_intent_ranked_first(self, index, registry):
        results = suggest("open scene 3", index, registry=registry)
        assert results[0].category == "intent"

    def test_no_intent_for_random_text(self, index, registry):
        results = suggest("zzzzz", index, registry=registry)
        intent_results = [r for r in results if r.category == "intent"]
        assert len(intent_results) == 0

    def test_slash_command_no_double_intent(self, index, registry):
        results = suggest("/open scene 3", index, registry=registry)
        intent_results = [r for r in results if r.category == "intent"]
        assert len(intent_results) == 0

    def test_entity_search_still_works(self, index, registry):
        results = suggest("john", index, registry=registry)
        entity_results = [r for r in results if r.category == "entity"]
        assert len(entity_results) >= 1
        assert entity_results[0].text == "John"
