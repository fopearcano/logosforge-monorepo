"""Tests for natural language suggestions — commands and entity actions."""

import pytest

from logosforge.db import Database
from logosforge.psyke_command_registry import CommandRegistry
from logosforge.psyke_search import PsykeSearchIndex
from logosforge.psyke_suggestions import Suggestion, suggest


def _noop(ctx):
    pass


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def project(db):
    return db.create_project("Test")


@pytest.fixture
def index(db, project):
    db.create_psyke_entry(project.id, "John", "character", aliases="johnny")
    db.create_psyke_entry(project.id, "Mary", "character")
    db.create_psyke_entry(project.id, "Palazzo", "place")
    db.create_psyke_entry(project.id, "Sword of Light", "object")
    return PsykeSearchIndex(db, project.id)


@pytest.fixture
def registry():
    reg = CommandRegistry()
    reg.register("create", _noop, description="Create a PSYKE entry")
    reg.register("open", _noop, description="Open a scene or entry")
    reg.register("go", _noop, description="Navigate scenes", aliases=["goto"])
    reg.register("ai", _noop, description="AI writing actions", aliases=["ask"])
    return reg


class TestNLCommandSuggestions:
    """Typing command words without '/' suggests completions."""

    def test_open_suggests_subargs(self, index, registry):
        results = suggest("open", index, registry=registry)
        texts = [r.text for r in results]
        assert "open scene" in texts
        assert "open psyke" in texts

    def test_open_partial_filters(self, index, registry):
        results = suggest("open sc", index, registry=registry)
        texts = [r.text for r in results]
        assert "open scene" in texts
        assert "open psyke" not in texts

    def test_create_suggests_types(self, index, registry):
        results = suggest("create", index, registry=registry)
        texts = [r.text for r in results]
        assert "create character" in texts
        assert "create place" in texts
        assert "create object" in texts

    def test_create_filters_subarg(self, index, registry):
        results = suggest("create ch", index, registry=registry)
        texts = [r.text for r in results]
        assert "create character" in texts
        assert "create place" not in texts

    def test_ai_suggests_actions(self, index, registry):
        results = suggest("ai", index, registry=registry)
        texts = [r.text for r in results]
        assert "ai rewrite" in texts
        assert "ai expand" in texts

    def test_go_suggests_directions(self, index, registry):
        results = suggest("go", index, registry=registry)
        texts = [r.text for r in results]
        assert "go scene next" in texts
        assert "go scene previous" in texts

    def test_prefix_suggests_command_name(self, index, registry):
        results = suggest("cr", index, registry=registry)
        texts = [r.text for r in results]
        assert "create" in texts

    def test_nl_commands_have_correct_category(self, index, registry):
        results = suggest("open", index, registry=registry)
        nl_cmds = [r for r in results if r.category == "nl_command"]
        assert len(nl_cmds) >= 2

    def test_nl_commands_sorted_by_score(self, index, registry):
        results = suggest("open", index, registry=registry)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)


class TestNLEntityActions:
    """Typing entity names suggests insert/open actions."""

    def test_john_suggests_actions(self, index, registry):
        results = suggest("john", index, registry=registry)
        texts = [r.text for r in results]
        assert "insert John" in texts
        assert "open John" in texts

    def test_mary_suggests_actions(self, index, registry):
        results = suggest("mary", index, registry=registry)
        texts = [r.text for r in results]
        assert "insert Mary" in texts
        assert "open Mary" in texts

    def test_entity_action_has_description(self, index, registry):
        results = suggest("john", index, registry=registry)
        insert_results = [r for r in results if r.text == "insert John"]
        assert len(insert_results) == 1
        assert "insert" in insert_results[0].description

    def test_entity_action_has_correct_category(self, index, registry):
        results = suggest("john", index, registry=registry)
        action_results = [r for r in results if r.category == "nl_action"]
        assert len(action_results) >= 2

    def test_entity_action_has_entry_id(self, index, registry):
        results = suggest("john", index, registry=registry)
        action_results = [r for r in results if r.category == "nl_action"]
        assert all(r.entry_id > 0 for r in action_results)

    def test_entity_with_action_prefix_filters(self, index, registry):
        results = suggest("john op", index, registry=registry)
        action_results = [r for r in results if r.category == "nl_action"]
        assert any("open" in r.text.lower() for r in action_results)
        assert not any("insert" in r.text.lower() for r in action_results)

    def test_entity_still_shows_in_results(self, index, registry):
        results = suggest("john", index, registry=registry)
        entity_results = [r for r in results if r.category == "entity"]
        assert any(r.text == "John" for r in entity_results)


class TestNLVerbEntitySuggestions:
    """Typing 'insert john' or 'open john' suggests matching entries."""

    def test_insert_john(self, index, registry):
        results = suggest("insert john", index, registry=registry)
        nl_results = [r for r in results if r.category == "nl_action"]
        assert len(nl_results) >= 1
        assert any("John" in r.text for r in nl_results)

    def test_open_john(self, index, registry):
        results = suggest("open john", index, registry=registry)
        nl_results = [r for r in results if r.category == "nl_action"]
        assert len(nl_results) >= 1
        assert any("John" in r.text for r in nl_results)
        assert any("open" in r.description.lower() for r in nl_results)

    def test_mention_palazzo(self, index, registry):
        results = suggest("mention pal", index, registry=registry)
        nl_results = [r for r in results if r.category == "nl_action"]
        assert len(nl_results) >= 1
        assert any("Palazzo" in r.text for r in nl_results)

    def test_show_mary(self, index, registry):
        results = suggest("show mary", index, registry=registry)
        nl_results = [r for r in results if r.category == "nl_action"]
        assert any("Mary" in r.text for r in nl_results)
        assert any("open" in r.description.lower() for r in nl_results)

    def test_use_sword(self, index, registry):
        results = suggest("use sword", index, registry=registry)
        nl_results = [r for r in results if r.category == "nl_action"]
        assert len(nl_results) >= 1


class TestMixedNLResults:
    """NL suggestions coexist with entity search and intent results."""

    def test_open_mixes_commands_and_intent(self, index, registry):
        results = suggest("open scene 3", index, registry=registry)
        categories = {r.category for r in results}
        assert "intent" in categories

    def test_john_mixes_entity_and_actions(self, index, registry):
        results = suggest("john", index, registry=registry)
        categories = {r.category for r in results}
        assert "entity" in categories
        assert "nl_action" in categories

    def test_max_results_respected(self, index, registry):
        results = suggest("john", index, registry=registry, max_results=3)
        assert len(results) <= 3

    def test_all_sorted_by_score(self, index, registry):
        results = suggest("john", index, registry=registry)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_no_match_returns_empty(self, index, registry):
        results = suggest("zzzzz", index, registry=registry)
        assert len(results) == 0

    def test_slash_path_unchanged(self, index, registry):
        results = suggest("/open", index, registry=registry)
        texts = [r.text for r in results]
        assert "/open scene" in texts
        assert "/open psyke" in texts


class TestContextBoostWithActions:
    """Scene-context boosting works on NL entity actions."""

    def test_scene_entity_action_boosted(self, db, project, index, registry):
        entries = db.get_all_psyke_entries(project.id)
        john_id = next(e.id for e in entries if e.name == "John")

        results_no_ctx = suggest("john", index, registry=registry)
        results_with_ctx = suggest("john", index, registry=registry, scene_entry_ids={john_id})

        john_action_no = [r for r in results_no_ctx if r.category == "nl_action" and "John" in r.text]
        john_action_ctx = [r for r in results_with_ctx if r.category == "nl_action" and "John" in r.text]

        assert len(john_action_no) > 0
        assert len(john_action_ctx) > 0
        assert john_action_ctx[0].score > john_action_no[0].score
