"""Tests for Writing Methods RAG adapter."""

import pytest

from logosforge.quantum_outliner.writing_methods_rag import (
    MethodResult,
    _load_sections,
    get_relevant_writing_methods,
    reload,
)


@pytest.fixture(autouse=True)
def _fresh_cache():
    reload()
    yield
    reload()


class TestFileLoading:
    def test_file_loads_and_has_sections(self):
        sections = _load_sections()
        assert len(sections) >= 10

    def test_each_section_has_title_and_body(self):
        sections = _load_sections()
        for sec in sections:
            assert sec.title
            assert sec.body
            assert len(sec.keywords) > 0

    def test_missing_file_returns_empty(self, tmp_path):
        sections = _load_sections(tmp_path / "nonexistent.md")
        assert sections == []


class TestSearchSaveTheCat:
    def test_exact_match(self):
        results = get_relevant_writing_methods("Save the Cat")
        assert len(results) >= 1
        assert results[0].title == "Save the Cat"
        assert results[0].score > 0.3

    def test_contains_beat_info(self):
        results = get_relevant_writing_methods("Save the Cat")
        assert "Midpoint" in results[0].snippet or "beats" in results[0].snippet.lower()


class TestSearchHerosJourney:
    def test_exact_match(self):
        results = get_relevant_writing_methods("Hero's Journey")
        assert len(results) >= 1
        assert results[0].title == "Hero's Journey"
        assert results[0].score > 0.3

    def test_partial_match(self):
        results = get_relevant_writing_methods("hero journey monomyth")
        assert len(results) >= 1
        assert results[0].title == "Hero's Journey"

    def test_contains_stages(self):
        results = get_relevant_writing_methods("Hero's Journey")
        assert "Ordinary World" in results[0].snippet or "Call to Adventure" in results[0].snippet


class TestSearchKishotenketsu:
    def test_exact_match(self):
        results = get_relevant_writing_methods("Kishōtenketsu")
        assert len(results) >= 1
        assert results[0].title == "Kishōtenketsu"
        assert results[0].score > 0.3

    def test_partial_romanized(self):
        results = get_relevant_writing_methods("kishotenketsu four act")
        assert len(results) >= 1
        assert "Kishōtenketsu" in results[0].title

    def test_twist_concept(self):
        results = get_relevant_writing_methods("Kishōtenketsu")
        assert "twist" in results[0].snippet.lower() or "ten" in results[0].snippet.lower()


class TestUnknownQuery:
    def test_nonsense_returns_empty(self):
        results = get_relevant_writing_methods("xyzzy foobar blargh")
        assert results == []

    def test_empty_query_returns_empty(self):
        results = get_relevant_writing_methods("")
        assert results == []

    def test_punctuation_only_returns_empty(self):
        results = get_relevant_writing_methods("!!! ???")
        assert results == []


class TestResultFormat:
    def test_result_has_required_fields(self):
        results = get_relevant_writing_methods("three act structure")
        assert len(results) >= 1
        r = results[0]
        assert isinstance(r, MethodResult)
        assert isinstance(r.title, str)
        assert isinstance(r.snippet, str)
        assert isinstance(r.score, float)
        assert 0.0 < r.score <= 1.0

    def test_max_results_respected(self):
        results = get_relevant_writing_methods("story structure", max_results=2)
        assert len(results) <= 2

    def test_snippet_length_capped(self):
        results = get_relevant_writing_methods("Snowflake Method")
        for r in results:
            assert len(r.snippet) <= 303

    def test_results_ordered_by_score(self):
        results = get_relevant_writing_methods("scene conflict goal", max_results=5)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)


class TestVariousQueries:
    def test_scene_sequel(self):
        results = get_relevant_writing_methods("scene sequel Swain")
        assert len(results) >= 1
        assert results[0].title == "Scene-Sequel"

    def test_story_circle(self):
        results = get_relevant_writing_methods("Story Circle Dan Harmon")
        assert len(results) >= 1
        assert results[0].title == "Story Circle"

    def test_mice_quotient(self):
        results = get_relevant_writing_methods("MICE Quotient")
        assert len(results) >= 1
        assert results[0].title == "MICE Quotient"

    def test_try_fail_cycles(self):
        results = get_relevant_writing_methods("try fail cycles")
        assert len(results) >= 1
        assert results[0].title == "Try-Fail Cycles"

    def test_fichtean_curve(self):
        results = get_relevant_writing_methods("Fichtean Curve rising action")
        assert len(results) >= 1
        assert results[0].title == "Fichtean Curve"
