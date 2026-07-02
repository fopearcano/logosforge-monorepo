"""Tests for Creative Layer — hints, rhythm, review metrics, and UI integration."""

from logosforge.creative_layer import (
    RhythmDot,
    ReviewMetrics,
    SceneHint,
    SceneRhythm,
    _LONG_THRESHOLD,
    _PARA_LONG,
    _PARA_SHORT,
    _SHORT_THRESHOLD,
    analyze_paragraph_rhythm,
    compute_review_metrics,
    generate_scene_hints,
)
from logosforge.db import Database
from logosforge.ui import theme
from logosforge.ui.writing_core_view import WritingCoreView


def _make_project():
    db = Database()
    proj = db.create_project("TestNovel")
    return db, proj


def _make_project_with_scenes():
    db, proj = _make_project()
    s1 = db.create_scene(proj.id, "Opening", content="The storm began. " * 30, act="Act One", chapter="Chapter 1")
    s2 = db.create_scene(proj.id, "Rising", content="She ran quickly. " * 8, act="Act One", chapter="Chapter 1")
    s3 = db.create_scene(proj.id, "Climax", content="They argued fiercely. " * 50, act="Act Two", chapter="Chapter 2")
    return db, proj, s1, s2, s3


# -- analyze_paragraph_rhythm ------------------------------------------------

def test_rhythm_empty_text():
    result = analyze_paragraph_rhythm("", 1)
    assert result.scene_id == 1
    assert result.dots == []
    assert result.variation_score == 0.0


def test_rhythm_whitespace_only():
    result = analyze_paragraph_rhythm("   \n\n  ", 2)
    assert result.dots == []
    assert result.variation_score == 0.0


def test_rhythm_single_paragraph():
    result = analyze_paragraph_rhythm("This is a simple test.", 1)
    assert len(result.dots) == 1
    assert result.dots[0].length == "short"
    assert result.variation_score == 0.0


def test_rhythm_short_classification():
    text = " ".join(["word"] * 10)
    result = analyze_paragraph_rhythm(text, 1)
    assert result.dots[0].length == "short"
    assert result.dots[0].word_count == 10


def test_rhythm_medium_classification():
    text = " ".join(["word"] * 50)
    result = analyze_paragraph_rhythm(text, 1)
    assert result.dots[0].length == "medium"


def test_rhythm_long_classification():
    text = " ".join(["word"] * 100)
    result = analyze_paragraph_rhythm(text, 1)
    assert result.dots[0].length == "long"


def test_rhythm_multiple_paragraphs():
    short = " ".join(["word"] * 10)
    long = " ".join(["word"] * 100)
    text = short + "\n\n" + long
    result = analyze_paragraph_rhythm(text, 1)
    assert len(result.dots) == 2
    assert result.dots[0].length == "short"
    assert result.dots[1].length == "long"


def test_rhythm_variation_score_nonzero():
    short = " ".join(["word"] * 5)
    long = " ".join(["word"] * 100)
    text = short + "\n\n" + long
    result = analyze_paragraph_rhythm(text, 1)
    assert result.variation_score > 0.0


def test_rhythm_uniform_text_low_variation():
    para = " ".join(["word"] * 50)
    text = "\n\n".join([para] * 4)
    result = analyze_paragraph_rhythm(text, 1)
    assert result.variation_score == 0.0


def test_rhythm_variation_capped_at_one():
    short = "a"
    long = " ".join(["word"] * 200)
    text = short + "\n\n" + long
    result = analyze_paragraph_rhythm(text, 1)
    assert result.variation_score <= 1.0


# -- generate_scene_hints ---------------------------------------------------

def test_hints_empty_scene():
    db, proj = _make_project()
    scene = db.create_scene(proj.id, "Blank", content="")
    hints = generate_scene_hints(db, proj.id, scene.id)
    assert any(h.hint_type == "empty" for h in hints)


def test_hints_short_scene():
    db, proj = _make_project()
    content = "Very short."
    scene = db.create_scene(proj.id, "Short", content=content)
    hints = generate_scene_hints(db, proj.id, scene.id)
    assert any(h.hint_type == "short_scene" for h in hints)


def test_hints_long_scene():
    db, proj = _make_project()
    content = " ".join(["word"] * (_LONG_THRESHOLD * 3 + 1))
    scene = db.create_scene(proj.id, "Long", content=content)
    hints = generate_scene_hints(db, proj.id, scene.id)
    assert any(h.hint_type == "long_scene" for h in hints)


def test_hints_normal_scene_no_flags():
    db, proj = _make_project()
    content = "The hero argued against the villain. " * 10
    scene = db.create_scene(proj.id, "Normal", content=content, conflict="villain fight")
    hints = generate_scene_hints(db, proj.id, scene.id)
    type_set = {h.hint_type for h in hints}
    assert "empty" not in type_set
    assert "short_scene" not in type_set
    assert "long_scene" not in type_set


def test_hints_nonexistent_scene():
    db, proj = _make_project()
    hints = generate_scene_hints(db, proj.id, 99999)
    assert hints == []


def test_hints_no_conflict_detected():
    db, proj = _make_project()
    content = "The sun shone brightly on the meadow and flowers swayed gently. " * 5
    scene = db.create_scene(proj.id, "Peaceful", content=content)
    hints = generate_scene_hints(db, proj.id, scene.id)
    assert any(h.hint_type == "no_conflict" for h in hints)


def test_hints_conflict_words_suppress_hint():
    db, proj = _make_project()
    content = "She refused to accept the offer and argued her case. " * 5
    scene = db.create_scene(proj.id, "Conflict", content=content)
    hints = generate_scene_hints(db, proj.id, scene.id)
    assert not any(h.hint_type == "no_conflict" for h in hints)


# -- compute_review_metrics --------------------------------------------------

def test_review_metrics_empty_project():
    db, proj = _make_project()
    metrics = compute_review_metrics(db, proj.id)
    assert metrics.total_words == 0
    assert metrics.total_scenes == 0
    assert metrics.pacing_balance == {"short": 0, "medium": 0, "long": 0}


def test_review_metrics_counts():
    db, proj, s1, s2, s3 = _make_project_with_scenes()
    metrics = compute_review_metrics(db, proj.id)
    assert metrics.total_scenes == 3
    assert metrics.total_words > 0
    assert metrics.avg_scene_words > 0


def test_review_metrics_shortest_longest():
    db, proj, s1, s2, s3 = _make_project_with_scenes()
    metrics = compute_review_metrics(db, proj.id)
    short_id, short_wc = metrics.shortest_scene
    long_id, long_wc = metrics.longest_scene
    assert short_wc <= long_wc


def test_review_metrics_pacing():
    db, proj, s1, s2, s3 = _make_project_with_scenes()
    metrics = compute_review_metrics(db, proj.id)
    total_pacing = sum(metrics.pacing_balance.values())
    assert total_pacing == metrics.total_scenes


def test_review_metrics_flagged_scenes():
    db, proj = _make_project()
    db.create_scene(proj.id, "Empty", content="")
    db.create_scene(proj.id, "Tiny", content="Short.")
    metrics = compute_review_metrics(db, proj.id)
    assert len(metrics.flagged_scenes) >= 2




# -- WritingCoreView integration: PSYKE highlighting -----------------------

def test_view_has_highlighters():
    db, proj, s1, s2, s3 = _make_project_with_scenes()
    view = WritingCoreView(db, proj.id)
    assert s1.id in view._highlighters
    assert s2.id in view._highlighters


def test_psyke_refresh_terms():
    db, proj, s1, s2, s3 = _make_project_with_scenes()
    db.create_psyke_entry(proj.id, "Alice", entry_type="character")
    view = WritingCoreView(db, proj.id)
    view.refresh_psyke_terms()
    hl = view._highlighters[s1.id]
    assert hl._pattern is not None


def test_psyke_no_entries_no_pattern():
    db, proj, s1, *_ = _make_project_with_scenes()
    view = WritingCoreView(db, proj.id)
    hl = view._highlighters[s1.id]
    assert hl._pattern is None


# -- WritingCoreView integration: Review mode ------------------------------

def test_review_mode_default_off():
    db, proj, *_ = _make_project_with_scenes()
    view = WritingCoreView(db, proj.id)
    assert view.is_review_mode() is False
    assert view._review_overlay is None


def test_review_mode_toggle_on():
    db, proj, *_ = _make_project_with_scenes()
    view = WritingCoreView(db, proj.id)
    view.toggle_review_mode()
    assert view.is_review_mode() is True
    assert view._review_overlay is not None
    assert view._review_btn.text() == "Close Review"


def test_review_mode_toggle_off():
    db, proj, *_ = _make_project_with_scenes()
    view = WritingCoreView(db, proj.id)
    view.toggle_review_mode()
    view.toggle_review_mode()
    assert view.is_review_mode() is False
    assert view._review_overlay is None
    assert view._review_btn.text() == "Review"


def test_review_overlay_object_name():
    db, proj, *_ = _make_project_with_scenes()
    view = WritingCoreView(db, proj.id)
    view.toggle_review_mode()
    assert view._review_overlay.objectName() == "reviewOverlay"


# -- Theme includes creative layer styles ----------------------------------



def test_theme_has_review_overlay_rules():
    ss = theme.build_stylesheet()
    assert "#reviewOverlay" in ss
    assert "#reviewOverlayTitle" in ss


# -- Dataclass construction ------------------------------------------------

def test_scene_hint_dataclass():
    h = SceneHint(scene_id=1, hint_type="empty", message="Test")
    assert h.scene_id == 1
    assert h.hint_type == "empty"
    assert h.message == "Test"


def test_rhythm_dot_dataclass():
    d = RhythmDot(length="short", word_count=10)
    assert d.length == "short"
    assert d.word_count == 10


def test_scene_rhythm_dataclass():
    r = SceneRhythm(scene_id=1, dots=[], variation_score=0.5)
    assert r.scene_id == 1
    assert r.variation_score == 0.5


def test_review_metrics_dataclass():
    m = ReviewMetrics(
        total_words=100, total_scenes=2, avg_scene_words=50,
        shortest_scene=(1, 30), longest_scene=(2, 70),
        pacing_balance={"short": 1, "medium": 0, "long": 1},
        flagged_scenes=[],
    )
    assert m.total_words == 100
    assert m.total_scenes == 2
