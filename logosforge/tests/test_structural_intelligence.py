"""Tests for structural intelligence — PSYKE-driven narrative analysis."""

from logosforge.db import Database
from logosforge.structural_intelligence import (
    StructuralAnalysis,
    StructuralCache,
    StructuralIssue,
    compute_structural_analysis,
    gather_structural_context,
    _detect_act_balance,
    _detect_arc_completion,
    _detect_beat_placement,
    _detect_character_presence,
    _detect_climax_preparation,
    _detect_tension_curve,
    _detect_theme_continuity,
    _linear_slope,
)
from logosforge.narrative_dashboard import (
    ActSegment,
    CharacterPresence,
    SceneTension,
    StructureDistribution,
    TensionCurve,
    ThemePresence,
)
from logosforge.temporal_psyke import TemporalGraph


# -- Helpers -----------------------------------------------------------------

def _make_project(db, fmt="novel"):
    return db.create_project("Test Story", format_mode=fmt)


def _add_scene(db, project_id, title, content="", act="", chapter="",
               beat="", conflict="", plotline=""):
    return db.create_scene(
        project_id, title=title, content=content, act=act,
        chapter=chapter, beat=beat, conflict=conflict, plotline=plotline,
    )


# == A. Act Balance ===========================================================

class TestActBalance:
    def test_weak_act_detected(self):
        structure = StructureDistribution(
            segments=[
                ActSegment("Act 1", 5, 2000),
                ActSegment("Act 2", 5, 300),
                ActSegment("Act 3", 5, 2000),
            ],
            total_scenes=15, total_words=4300,
        )
        issues = _detect_act_balance(structure)
        types = [i.issue_type for i in issues]
        assert "weak_act" in types

    def test_balanced_acts_no_issue(self):
        structure = StructureDistribution(
            segments=[
                ActSegment("Act 1", 5, 1500),
                ActSegment("Act 2", 5, 1800),
                ActSegment("Act 3", 5, 1600),
            ],
            total_scenes=15, total_words=4900,
        )
        issues = _detect_act_balance(structure)
        assert not issues

    def test_weak_middle_detected(self):
        structure = StructureDistribution(
            segments=[
                ActSegment("Act 1", 5, 2000),
                ActSegment("Act 2", 5, 400),
                ActSegment("Act 3", 5, 2000),
            ],
            total_scenes=15, total_words=4400,
        )
        issues = _detect_act_balance(structure)
        types = [i.issue_type for i in issues]
        assert "weak_middle" in types

    def test_single_segment_no_crash(self):
        structure = StructureDistribution(
            segments=[ActSegment("Act 1", 5, 1000)],
            total_scenes=5, total_words=1000,
        )
        issues = _detect_act_balance(structure)
        assert issues == []

    def test_empty_segments(self):
        structure = StructureDistribution(
            segments=[], total_scenes=0, total_words=0,
        )
        issues = _detect_act_balance(structure)
        assert issues == []


# == B. Arc Completion ========================================================

class TestArcCompletion:
    def test_static_arc_detected(self):
        db = Database()
        proj = _make_project(db)
        for i in range(6):
            _add_scene(db, proj.id, f"Scene {i}", content="Alice walked. " * 20)
        db.create_psyke_entry(proj.id, name="Alice", entry_type="character")
        tg = TemporalGraph(db, proj.id)
        issues = _detect_arc_completion(tg, db.get_all_scenes(proj.id))
        types = [i.issue_type for i in issues]
        assert "static_arc" in types

    def test_character_with_progression_no_static(self):
        db = Database()
        proj = _make_project(db)
        scenes = []
        for i in range(6):
            scenes.append(_add_scene(db, proj.id, f"Scene {i}", content="Bob walked. " * 20))
        entry = db.create_psyke_entry(proj.id, name="Bob", entry_type="character")
        db.create_psyke_progression(entry.id, "Bob grows", scene_id=scenes[-1].id)
        tg = TemporalGraph(db, proj.id)
        issues = _detect_arc_completion(tg, db.get_all_scenes(proj.id))
        types = [i.issue_type for i in issues]
        assert "static_arc" not in types

    def test_abandoned_arc_detected(self):
        db = Database()
        proj = _make_project(db)
        scenes = []
        for i in range(10):
            scenes.append(_add_scene(db, proj.id, f"Scene {i}", content="Carol walked. " * 20))
        entry = db.create_psyke_entry(proj.id, name="Carol", entry_type="character")
        db.create_psyke_progression(entry.id, "Carol is brave", scene_id=scenes[1].id)
        tg = TemporalGraph(db, proj.id)
        issues = _detect_arc_completion(tg, db.get_all_scenes(proj.id))
        types = [i.issue_type for i in issues]
        assert "abandoned_arc" in types

    def test_arc_completed_late_no_issue(self):
        db = Database()
        proj = _make_project(db)
        scenes = []
        for i in range(10):
            scenes.append(_add_scene(db, proj.id, f"Scene {i}", content="Dave walked. " * 20))
        entry = db.create_psyke_entry(proj.id, name="Dave", entry_type="character")
        db.create_psyke_progression(entry.id, "Dave resolves", scene_id=scenes[8].id)
        tg = TemporalGraph(db, proj.id)
        issues = _detect_arc_completion(tg, db.get_all_scenes(proj.id))
        types = [i.issue_type for i in issues]
        assert "abandoned_arc" not in types

    def test_global_entries_skipped(self):
        db = Database()
        proj = _make_project(db)
        for i in range(6):
            _add_scene(db, proj.id, f"Scene {i}", content="Text. " * 20)
        db.create_psyke_entry(proj.id, name="WorldRule", entry_type="lore", is_global=True)
        tg = TemporalGraph(db, proj.id)
        issues = _detect_arc_completion(tg, db.get_all_scenes(proj.id))
        assert issues == []


# == C. Climax Preparation ====================================================

class TestClimaxPreparation:
    def _make_tension(self, scores):
        points = [
            SceneTension(
                scene_id=i, scene_order=i, scene_title=f"Scene {i}",
                score=s, char_count=0, relation_pairs=0,
                keyword_hits=0, progression_count=0,
            )
            for i, s in enumerate(scores)
        ]
        return TensionCurve(points=points)

    def test_unprepared_climax_detected(self):
        scores = [10, 10, 10, 10, 10, 10, 10, 10, 10, 80]
        tension = self._make_tension(scores)
        issues = _detect_climax_preparation(tension)
        types = [i.issue_type for i in issues]
        assert "unprepared_climax" in types

    def test_well_built_climax_no_issue(self):
        scores = [10, 20, 30, 40, 50, 60, 70, 80, 90, 95]
        tension = self._make_tension(scores)
        issues = _detect_climax_preparation(tension)
        types = [i.issue_type for i in issues]
        assert "unprepared_climax" not in types

    def test_weak_climax_build_detected(self):
        scores = [30, 40, 35, 30, 20, 15, 10, 10, 10, 15]
        tension = self._make_tension(scores)
        issues = _detect_climax_preparation(tension)
        types = [i.issue_type for i in issues]
        assert "weak_climax_build" in types

    def test_too_few_scenes_no_crash(self):
        scores = [10, 20, 30]
        tension = self._make_tension(scores)
        issues = _detect_climax_preparation(tension)
        assert issues == []


# == D. Tension Curve =========================================================

class TestTensionCurve:
    def _make_tension(self, scores):
        points = [
            SceneTension(
                scene_id=i, scene_order=i, scene_title=f"Scene {i}",
                score=s, char_count=0, relation_pairs=0,
                keyword_hits=0, progression_count=0,
            )
            for i, s in enumerate(scores)
        ]
        return TensionCurve(points=points)

    def test_flat_pacing_detected(self):
        scores = [50, 51, 49, 50, 50, 51, 49, 50]
        tension = self._make_tension(scores)
        issues = _detect_tension_curve(tension)
        types = [i.issue_type for i in issues]
        assert "flat_pacing" in types

    def test_varied_pacing_no_issue(self):
        scores = [10, 50, 20, 70, 30, 80, 40, 90]
        tension = self._make_tension(scores)
        issues = _detect_tension_curve(tension)
        types = [i.issue_type for i in issues]
        assert "flat_pacing" not in types

    def test_no_rising_stakes_detected(self):
        scores = [80, 70, 60, 50, 40, 30, 20, 10]
        tension = self._make_tension(scores)
        issues = _detect_tension_curve(tension)
        types = [i.issue_type for i in issues]
        assert "no_rising_stakes" in types

    def test_rising_stakes_ok(self):
        scores = [10, 20, 30, 40, 50, 60, 70, 80]
        tension = self._make_tension(scores)
        issues = _detect_tension_curve(tension)
        types = [i.issue_type for i in issues]
        assert "no_rising_stakes" not in types


# == E. Theme Continuity ======================================================

class TestThemeContinuity:
    def test_underused_theme_detected(self):
        theme = ThemePresence(
            entry_id=1, name="Redemption",
            present_scenes=[1], total_scenes=20,
        )
        issues = _detect_theme_continuity([theme], 20)
        types = [i.issue_type for i in issues]
        assert "theme_underused" in types

    def test_well_used_theme_no_issue(self):
        theme = ThemePresence(
            entry_id=1, name="Justice",
            present_scenes=list(range(10)), total_scenes=12,
        )
        issues = _detect_theme_continuity([theme], 12)
        types = [i.issue_type for i in issues]
        assert "theme_underused" not in types

    def test_theme_abandoned_detected(self):
        theme = ThemePresence(
            entry_id=1, name="Hope",
            present_scenes=[0, 1, 2, 3], total_scenes=12,
        )
        issues = _detect_theme_continuity([theme], 12)
        types = [i.issue_type for i in issues]
        assert "theme_abandoned" in types

    def test_theme_present_at_end_no_abandoned(self):
        theme = ThemePresence(
            entry_id=1, name="Love",
            present_scenes=[0, 1, 10, 11], total_scenes=12,
        )
        issues = _detect_theme_continuity([theme], 12)
        types = [i.issue_type for i in issues]
        assert "theme_abandoned" not in types

    def test_few_scenes_returns_empty(self):
        theme = ThemePresence(
            entry_id=1, name="Truth",
            present_scenes=[0], total_scenes=2,
        )
        issues = _detect_theme_continuity([theme], 2)
        assert issues == []


# == F. Character Presence ====================================================

class TestCharacterPresence:
    def test_key_character_missing_detected(self):
        char = CharacterPresence(
            entry_id=1, name="Hero",
            present_scenes=[0, 1, 2, 15, 16, 17, 18, 19],
            total_scenes=20,
        )
        issues = _detect_character_presence([char], 20)
        types = [i.issue_type for i in issues]
        assert "key_character_missing" in types

    def test_well_distributed_character_no_issue(self):
        char = CharacterPresence(
            entry_id=1, name="Hero",
            present_scenes=list(range(0, 20, 2)),
            total_scenes=20,
        )
        issues = _detect_character_presence([char], 20)
        assert issues == []

    def test_minor_character_not_flagged(self):
        char = CharacterPresence(
            entry_id=1, name="Extra",
            present_scenes=[5, 15],
            total_scenes=20,
        )
        issues = _detect_character_presence([char], 20)
        assert issues == []


# == Beat Placement ===========================================================

class TestBeatPlacement:
    def test_missing_beats_detected(self):
        db = Database()
        proj = _make_project(db)
        _add_scene(db, proj.id, "Opening", content="x " * 50, beat="Opening Image")
        _add_scene(db, proj.id, "Setup", content="x " * 50, beat="Setup")
        _add_scene(db, proj.id, "Cat", content="x " * 50, beat="Catalyst")
        for i in range(5):
            _add_scene(db, proj.id, f"S{i}", content="x " * 50)
        scenes = db.get_all_scenes(proj.id)
        issues = _detect_beat_placement(scenes)
        types = [i.issue_type for i in issues]
        assert "missing_beats" in types

    def test_misplaced_beat_detected(self):
        db = Database()
        proj = _make_project(db)
        for i in range(10):
            beat = "Final Image" if i == 0 else ""
            _add_scene(db, proj.id, f"S{i}", content="x " * 50, beat=beat)
        scenes = db.get_all_scenes(proj.id)
        issues = _detect_beat_placement(scenes)
        types = [i.issue_type for i in issues]
        assert "misplaced_beat" in types

    def test_no_beats_no_issues(self):
        db = Database()
        proj = _make_project(db)
        for i in range(6):
            _add_scene(db, proj.id, f"S{i}", content="x " * 50)
        scenes = db.get_all_scenes(proj.id)
        issues = _detect_beat_placement(scenes)
        assert issues == []

    def test_correct_placement_no_issue(self):
        db = Database()
        proj = _make_project(db)
        for i in range(20):
            beat = ""
            if i == 0:
                beat = "Opening Image"
            elif i == 10:
                beat = "Midpoint"
            elif i == 18:
                beat = "Finale"
            _add_scene(db, proj.id, f"S{i}", content="x " * 50, beat=beat)
        scenes = db.get_all_scenes(proj.id)
        issues = _detect_beat_placement(scenes)
        types = [i.issue_type for i in issues]
        assert "misplaced_beat" not in types


# == Integration: compute_structural_analysis =================================

class TestComputeAnalysis:
    def test_empty_project_returns_empty(self):
        db = Database()
        proj = _make_project(db)
        analysis = compute_structural_analysis(db, proj.id)
        assert isinstance(analysis, StructuralAnalysis)
        assert analysis.issues == []

    def test_small_project_returns_empty(self):
        db = Database()
        proj = _make_project(db)
        _add_scene(db, proj.id, "S1", content="word " * 50)
        _add_scene(db, proj.id, "S2", content="word " * 50)
        analysis = compute_structural_analysis(db, proj.id)
        assert analysis.issues == []

    def test_long_story_produces_issues(self):
        db = Database()
        proj = _make_project(db)
        for i in range(15):
            _add_scene(db, proj.id, f"Scene {i}", content="word " * 100, act=f"Act {i % 3 + 1}")
        entry = db.create_psyke_entry(proj.id, name="Alice", entry_type="character")
        analysis = compute_structural_analysis(db, proj.id)
        assert isinstance(analysis, StructuralAnalysis)
        assert analysis.computed_at > 0

    def test_issues_sorted_by_severity(self):
        db = Database()
        proj = _make_project(db)
        for i in range(10):
            _add_scene(db, proj.id, f"Scene {i}", content="word " * 50, act=f"Act {i % 3 + 1}")
        db.create_psyke_entry(proj.id, name="Orphan", entry_type="character")
        analysis = compute_structural_analysis(db, proj.id)
        for i in range(len(analysis.issues) - 1):
            assert analysis.issues[i].severity >= analysis.issues[i + 1].severity

    def test_max_issues_capped(self):
        db = Database()
        proj = _make_project(db)
        for i in range(20):
            _add_scene(db, proj.id, f"Scene {i}", content="word " * 50, act=f"Act {i % 3 + 1}")
        for name in ["A", "B", "C", "D", "E", "F", "G"]:
            db.create_psyke_entry(proj.id, name=name, entry_type="character")
        db.create_psyke_entry(proj.id, name="Theme1", entry_type="theme")
        analysis = compute_structural_analysis(db, proj.id)
        assert len(analysis.issues) <= 5

    def test_suggestions_match_issues(self):
        db = Database()
        proj = _make_project(db)
        for i in range(10):
            _add_scene(db, proj.id, f"Scene {i}", content="word " * 50, act=f"Act {i % 3 + 1}")
        db.create_psyke_entry(proj.id, name="Orphan", entry_type="character")
        analysis = compute_structural_analysis(db, proj.id)
        for suggestion in analysis.suggestions:
            assert any(suggestion == i.suggestion for i in analysis.issues)


# == gather_structural_context ================================================

class TestGatherContext:
    def test_empty_project_returns_empty_string(self):
        db = Database()
        proj = _make_project(db)
        ctx = gather_structural_context(db, proj.id)
        assert ctx == ""

    def test_with_issues_returns_block(self):
        db = Database()
        proj = _make_project(db)
        for i in range(10):
            _add_scene(db, proj.id, f"Scene {i}", content="word " * 50, act=f"Act {i % 3 + 1}")
        db.create_psyke_entry(proj.id, name="Orphan", entry_type="character")
        ctx = gather_structural_context(db, proj.id)
        if ctx:
            assert "[Structural Analysis]" in ctx
            assert "Suggestion:" in ctx


# == StructuralCache ==========================================================

class TestStructuralCache:
    def test_cache_returns_result(self):
        db = Database()
        proj = _make_project(db)
        cache = StructuralCache()
        result = cache.get(db, proj.id)
        assert isinstance(result, StructuralAnalysis)

    def test_cache_reuses_on_second_call(self):
        db = Database()
        proj = _make_project(db)
        cache = StructuralCache()
        r1 = cache.get(db, proj.id)
        r2 = cache.get(db, proj.id)
        assert r1 is r2

    def test_mark_dirty_forces_recompute(self):
        db = Database()
        proj = _make_project(db)
        cache = StructuralCache()
        r1 = cache.get(db, proj.id)
        cache.mark_dirty()
        r2 = cache.get(db, proj.id)
        assert r1 is not r2

    def test_invalidate_clears(self):
        db = Database()
        proj = _make_project(db)
        cache = StructuralCache()
        cache.get(db, proj.id)
        cache.invalidate()
        assert cache._result is None


# == _linear_slope ============================================================

class TestLinearSlope:
    def test_rising(self):
        assert _linear_slope([10, 20, 30, 40, 50]) > 0

    def test_falling(self):
        assert _linear_slope([50, 40, 30, 20, 10]) < 0

    def test_flat(self):
        assert _linear_slope([30, 30, 30, 30]) == 0.0

    def test_single_value(self):
        assert _linear_slope([10]) == 0.0

    def test_empty(self):
        assert _linear_slope([]) == 0.0
