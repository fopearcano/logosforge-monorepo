"""Tests for PSYKE search index."""

import pytest
from logosforge.db import Database
from logosforge.psyke_search import PsykeSearchIndex, _score


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def project(db):
    return db.create_project("Test Project")


@pytest.fixture
def index(db, project):
    db.create_psyke_entry(project.id, "Jean Moreau", "character", aliases="Jean, JM")
    db.create_psyke_entry(project.id, "Palazzo Vecchio", "place", aliases="The Palazzo, PV")
    db.create_psyke_entry(project.id, "The Ancient Prophecy", "lore")
    db.create_psyke_entry(project.id, "Redemption", "theme")
    db.create_psyke_entry(project.id, "Sword of Light", "object", aliases="the sword, SoL")
    db.create_psyke_entry(project.id, "Jeanette", "character")
    return PsykeSearchIndex(db, project.id)


class TestScoreFunction:
    def test_exact_match(self):
        assert _score("jean", "jean") == 1.0

    def test_starts_with(self):
        s = _score("jea", "jean")
        assert 0.9 < s < 1.0

    def test_contains(self):
        s = _score("ancien", "the ancient prophecy")
        assert 0.6 < s < 0.8

    def test_fuzzy_subsequence(self):
        s = _score("jnm", "jean moreau")
        assert 0.3 < s < 0.6

    def test_no_match(self):
        assert _score("xyz", "jean") == 0.0

    def test_empty_query(self):
        assert _score("", "jean") == 0.0


class TestResolveEntity:
    def test_exact_name_resolves(self, index):
        r = index.resolve_entity("jean moreau")
        assert r is not None
        assert r.name == "Jean Moreau"

    def test_alias_resolves(self, index):
        r = index.resolve_entity("jm")
        assert r is not None
        assert r.name == "Jean Moreau"

    def test_partial_resolves(self, index):
        r = index.resolve_entity("redemp")
        assert r is not None
        assert r.name == "Redemption"

    def test_low_score_returns_none(self, index):
        assert index.resolve_entity("zxy") is None

    def test_empty_returns_none(self, index):
        assert index.resolve_entity("") is None

    def test_case_insensitive(self, index):
        r = index.resolve_entity("PALAZZO")
        assert r is not None
        assert r.name == "Palazzo Vecchio"


class TestPsykeSearchIndex:
    def test_exact_name(self, index):
        results = index.search("Jean Moreau")
        assert len(results) >= 1
        assert results[0].name == "Jean Moreau"
        assert results[0].score == 1.0

    def test_partial_name(self, index):
        results = index.search("jean")
        names = [r.name for r in results]
        assert "Jean Moreau" in names
        assert "Jeanette" in names

    def test_alias_match(self, index):
        results = index.search("JM")
        assert len(results) >= 1
        assert results[0].name == "Jean Moreau"
        assert results[0].matched_on == "jm"

    def test_alias_match_palazzo(self, index):
        results = index.search("PV")
        assert len(results) >= 1
        assert results[0].name == "Palazzo Vecchio"

    def test_case_insensitive(self, index):
        r1 = index.search("JEAN")
        r2 = index.search("jean")
        assert [r.entry_id for r in r1] == [r.entry_id for r in r2]

    def test_fuzzy_match(self, index):
        results = index.search("swrd")
        names = [r.name for r in results]
        assert "Sword of Light" in names

    def test_empty_query(self, index):
        assert index.search("") == []

    def test_whitespace_query(self, index):
        assert index.search("   ") == []

    def test_no_match(self, index):
        assert index.search("zzzzzzz") == []

    def test_max_results(self, index):
        results = index.search("e", max_results=3)
        assert len(results) <= 3

    def test_results_sorted_by_score(self, index):
        results = index.search("jean")
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_entry_type_in_results(self, index):
        results = index.search("Redemption")
        assert results[0].entry_type == "theme"

    def test_rebuild(self, db, project, index):
        db.create_psyke_entry(project.id, "New Entry", "other")
        assert index.search("New Entry") == []
        index.rebuild()
        results = index.search("New Entry")
        assert len(results) == 1
        assert results[0].name == "New Entry"
