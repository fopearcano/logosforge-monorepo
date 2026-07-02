"""Tests for PSYKE Console suggestion engine."""

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
    return db.create_project("Test Project")


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


class TestPlainSearch:
    def test_search_entity(self, index, registry):
        results = suggest("john", index, registry)
        assert len(results) >= 1
        assert results[0].text == "John"
        assert results[0].category == "entity"

    def test_search_partial(self, index, registry):
        results = suggest("pal", index, registry)
        names = [r.text for r in results]
        assert "Palazzo" in names

    def test_empty(self, index, registry):
        assert suggest("", index, registry) == []

    def test_no_match(self, index, registry):
        results = suggest("zzzzz", index, registry)
        assert len(results) == 0


class TestContextBoost:
    def test_scene_entities_ranked_higher(self, db, project, index, registry):
        entries = db.get_all_psyke_entries(project.id)
        john_id = next(e.id for e in entries if e.name == "John")
        results_no_ctx = suggest("j", index, registry)
        results_with_ctx = suggest("j", index, registry, scene_entry_ids={john_id})
        john_score_no = next((r.score for r in results_no_ctx if r.text == "John"), 0)
        john_score_ctx = next((r.score for r in results_with_ctx if r.text == "John"), 0)
        assert john_score_ctx > john_score_no


class TestCommandSuggestions:
    def test_slash_alone_lists_commands(self, index, registry):
        results = suggest("/", index, registry)
        texts = [r.text for r in results]
        assert "/create" in texts
        assert "/open" in texts
        assert "/ai" in texts
        assert all(r.category == "command" for r in results)

    def test_slash_prefix_matches(self, index, registry):
        results = suggest("/cr", index, registry)
        texts = [r.text for r in results]
        assert "/create" in texts

    def test_slash_exact_shows_subargs(self, index, registry):
        results = suggest("/create", index, registry)
        texts = [r.text for r in results]
        assert "/create character" in texts
        assert "/create place" in texts

    def test_slash_subarg_filters(self, index, registry):
        results = suggest("/create ch", index, registry)
        texts = [r.text for r in results]
        assert "/create character" in texts
        assert "/create place" not in texts

    def test_ai_subargs(self, index, registry):
        results = suggest("/ai", index, registry)
        texts = [r.text for r in results]
        assert "/ai rewrite" in texts
        assert "/ai expand" in texts

    def test_go_subargs(self, index, registry):
        results = suggest("/go", index, registry)
        texts = [r.text for r in results]
        assert "/go scene next" in texts
        assert "/go scene previous" in texts

    def test_alias_matches(self, index, registry):
        results = suggest("/as", index, registry)
        texts = [r.text for r in results]
        assert "/ask" in texts


class TestEntityCommands:
    def test_entity_prefix_suggests_actions(self, index, registry):
        results = suggest("/jo", index, registry)
        descs = [r.description for r in results]
        has_entity = any("John" in d for d in descs)
        assert has_entity

    def test_entity_with_action_prefix(self, index, registry):
        results = suggest("/john op", index, registry)
        matches = [r for r in results if "open" in r.description.lower()]
        assert len(matches) >= 1

    def test_entity_insert_and_open(self, index, registry):
        results = suggest("/john", index, registry)
        descs = [r.description for r in results]
        has_insert = any("insert" in d for d in descs)
        has_open = any("open" in d for d in descs)
        assert has_insert
        assert has_open


class TestMixedResults:
    def test_command_and_entity_mixed(self, index, registry):
        results = suggest("/go", index, registry)
        categories = {r.category for r in results}
        assert "command" in categories

    def test_results_sorted_by_score(self, index, registry):
        results = suggest("/jo", index, registry)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_max_results_respected(self, index, registry):
        results = suggest("/", index, registry, max_results=3)
        assert len(results) <= 3
