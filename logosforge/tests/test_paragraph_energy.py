"""Tests for ParagraphEnergy — per-paragraph writing dynamics."""

import time
from unittest.mock import patch

from logosforge.paragraph_energy import (
    FlowHint,
    ParagraphEnergy,
    StoryContext,
    _EMOTION_WINDOW,
    _FLAT_WINDOW,
    _PACING_SPIKE_DELTA,
    _PSYKE_WEIGHT,
    _parse_llm_metrics,
    analyze_paragraph,
    analyze_scene_energy,
    apply_story_context,
    build_story_context,
    clear_cache,
    compute_paragraph_energy,
    detect_flow_hints,
)


# -- Model creation ------------------------------------------------------------

def test_model_defaults():
    e = ParagraphEnergy(paragraph_id=0, scene_id=1)
    assert e.paragraph_id == 0
    assert e.scene_id == 1
    assert e.metrics == {}
    assert e.last_updated > 0


def test_model_with_metrics():
    m = {"tension": 0.5, "pacing": 0.7, "conflict": 0.3, "emotional_shift": 0.1}
    e = ParagraphEnergy(paragraph_id=2, scene_id=5, metrics=m)
    assert e.metrics == m


def test_model_properties():
    m = {"tension": 0.4, "pacing": 0.6, "conflict": 0.2, "emotional_shift": 0.8}
    e = ParagraphEnergy(paragraph_id=0, scene_id=1, metrics=m)
    assert e.tension == 0.4
    assert e.pacing == 0.6
    assert e.conflict == 0.2
    assert e.emotional_shift == 0.8


def test_model_properties_default_zero():
    e = ParagraphEnergy(paragraph_id=0, scene_id=1)
    assert e.tension == 0.0
    assert e.pacing == 0.0
    assert e.conflict == 0.0
    assert e.emotional_shift == 0.0


def test_last_updated_auto():
    before = time.time()
    e = ParagraphEnergy(paragraph_id=0, scene_id=1)
    after = time.time()
    assert before <= e.last_updated <= after


def test_last_updated_explicit():
    e = ParagraphEnergy(paragraph_id=0, scene_id=1, last_updated=12345.0)
    assert e.last_updated == 12345.0


# -- Compute single paragraph --------------------------------------------------

def test_compute_empty_text():
    e = compute_paragraph_energy(0, 1, "")
    assert e.tension == 0.0
    assert e.conflict == 0.0
    assert e.emotional_shift == 0.0


def test_compute_calm_paragraph():
    text = "The sun set over the quiet village. Birds sang in the trees."
    e = compute_paragraph_energy(0, 1, text)
    assert 0.0 <= e.tension <= 0.3
    assert 0.0 <= e.conflict <= 0.2


def test_compute_tense_paragraph():
    text = (
        "She feared the darkness that lurked in every shadow. "
        "Danger loomed. She trembled, dreading what crept behind her."
    )
    e = compute_paragraph_energy(0, 1, text)
    assert e.tension > 0.3


def test_compute_conflict_paragraph():
    text = (
        "They fought and argued. He attacked and she refused to back down. "
        "The enemy confronted them with rage and fury."
    )
    e = compute_paragraph_energy(0, 1, text)
    assert e.conflict > 0.3


def test_compute_fast_pacing():
    text = "He ran. She jumped. They fled. Explosions crashed around them!"
    e = compute_paragraph_energy(0, 1, text)
    assert e.pacing > 0.5


def test_compute_slow_pacing():
    text = (
        "The long and winding road stretched endlessly through the vast, "
        "rolling countryside, where ancient trees swayed gently in the "
        "warm afternoon breeze that carried the scent of wildflowers "
        "across the meadows and into the distant hills beyond."
    )
    e = compute_paragraph_energy(0, 1, text)
    assert e.pacing < 0.6


def test_compute_emotional_shift():
    text = "She laughed with joy. Then she sobbed, overwhelmed by grief."
    e = compute_paragraph_energy(0, 1, text)
    assert e.emotional_shift > 0.3


def test_compute_no_emotional_shift():
    text = "The table was wooden. The chair was also wooden."
    e = compute_paragraph_energy(0, 1, text)
    assert e.emotional_shift == 0.0


def test_metrics_in_range():
    text = (
        "He screamed and fought the enemy who lurked in the darkness. "
        "She laughed, then sobbed. They ran, crashed, and fled!"
    )
    e = compute_paragraph_energy(0, 1, text)
    for key in ("tension", "pacing", "conflict", "emotional_shift"):
        assert 0.0 <= e.metrics[key] <= 1.0, f"{key} out of range"


def test_compute_returns_all_four_metrics():
    e = compute_paragraph_energy(0, 1, "Hello world.")
    assert set(e.metrics.keys()) == {"tension", "pacing", "conflict", "emotional_shift"}


def test_compute_preserves_ids():
    e = compute_paragraph_energy(3, 7, "Some text.")
    assert e.paragraph_id == 3
    assert e.scene_id == 7


# -- Dialogue heuristic -------------------------------------------------------

def test_dialogue_boosts_tension():
    without = compute_paragraph_energy(0, 1, "She walked to the door and opened it.")
    with_dlg = compute_paragraph_energy(
        0, 1, '“Get out!” she screamed. “I feared this,” he whispered.',
    )
    assert with_dlg.tension >= without.tension


def test_dialogue_boosts_pacing():
    without = compute_paragraph_energy(0, 1, "The room was empty and still.")
    with_dlg = compute_paragraph_energy(
        0, 1, '“Run!” he shouted. “Now!” she yelled back.',
    )
    assert with_dlg.pacing >= without.pacing


# -- Contrast words heuristic -------------------------------------------------

def test_contrast_words_boost_emotional_shift():
    without = compute_paragraph_energy(0, 1, "He walked. He sat. He stood.")
    with_contrast = compute_paragraph_energy(
        0, 1, "He smiled. But suddenly he wept. However, he laughed again.",
    )
    assert with_contrast.emotional_shift > without.emotional_shift


def test_contrast_alone_gives_small_shift():
    e = compute_paragraph_energy(
        0, 1, "The sky was blue. But suddenly it turned grey.",
    )
    assert e.emotional_shift > 0.0


# -- Cache (analyze_paragraph API) --------------------------------------------

def test_analyze_paragraph_returns_energy():
    clear_cache()
    e = analyze_paragraph("A simple sentence.")
    assert isinstance(e, ParagraphEnergy)
    assert set(e.metrics.keys()) == {"tension", "pacing", "conflict", "emotional_shift"}


def test_analyze_paragraph_cache_hit():
    clear_cache()
    text = "The fox jumped over the lazy dog."
    first = analyze_paragraph(text)
    second = analyze_paragraph(text)
    assert first is second


def test_analyze_paragraph_different_texts_not_cached():
    clear_cache()
    a = analyze_paragraph("Hello world.")
    b = analyze_paragraph("Goodbye world.")
    assert a is not b


def test_cache_cleared_by_clear_cache():
    clear_cache()
    text = "Cached paragraph."
    first = analyze_paragraph(text)
    clear_cache()
    second = analyze_paragraph(text)
    assert first is not second


def test_cache_eviction_at_max():
    clear_cache()
    for i in range(520):
        analyze_paragraph(f"Paragraph number {i} unique text here.")
    from logosforge.paragraph_energy import _energy_cache
    assert len(_energy_cache) <= 512


def test_analyze_scene_uses_cache():
    clear_cache()
    content = "Shared line.\nAnother line."
    analyze_scene_energy(1, content)

    from logosforge.paragraph_energy import _cache_get
    assert _cache_get("Shared line.") is not None
    assert _cache_get("Another line.") is not None


def test_analyze_scene_reuses_cache():
    clear_cache()
    text = "Reusable paragraph."
    analyze_paragraph(text)

    from logosforge.paragraph_energy import _energy_cache
    cache_size_before = len(_energy_cache)
    analyze_scene_energy(5, text)
    assert len(_energy_cache) == cache_size_before


# -- Analyze scene energy (attach to paragraphs) ------------------------------

def test_analyze_scene_empty():
    result = analyze_scene_energy(1, "")
    assert result == []


def test_analyze_scene_single_paragraph():
    result = analyze_scene_energy(1, "A single paragraph of text.")
    assert len(result) == 1
    assert result[0].paragraph_id == 0
    assert result[0].scene_id == 1


def test_analyze_scene_multiple_paragraphs():
    content = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    result = analyze_scene_energy(1, content)
    assert len(result) == 3
    for i, e in enumerate(result):
        assert e.paragraph_id == i
        assert e.scene_id == 1


def test_analyze_scene_blank_lines_skipped():
    content = "Para one.\n\n\n\nPara two."
    result = analyze_scene_energy(1, content)
    assert len(result) == 2


def test_analyze_scene_preserves_scene_id():
    result = analyze_scene_energy(42, "Some content.\nMore content.")
    for e in result:
        assert e.scene_id == 42


def test_analyze_scene_sequential_ids():
    content = "A.\nB.\nC.\nD."
    result = analyze_scene_energy(1, content)
    assert [e.paragraph_id for e in result] == [0, 1, 2, 3]


def test_analyze_scene_each_has_metrics():
    content = "First line.\nSecond line."
    result = analyze_scene_energy(1, content)
    for e in result:
        assert "tension" in e.metrics
        assert "pacing" in e.metrics
        assert "conflict" in e.metrics
        assert "emotional_shift" in e.metrics


# -- Flow hint detection -------------------------------------------------------

def _make_energy(tension=0.0, pacing=0.5, conflict=0.0, emotional_shift=0.0, idx=0):
    return ParagraphEnergy(
        paragraph_id=idx, scene_id=1,
        metrics={
            "tension": tension, "pacing": pacing,
            "conflict": conflict, "emotional_shift": emotional_shift,
        },
    )


def test_no_hints_on_empty():
    assert detect_flow_hints([]) == []


def test_no_hints_on_short_sequence():
    energies = [_make_energy(idx=i) for i in range(2)]
    assert detect_flow_hints(energies) == []


def test_flat_detected():
    energies = [_make_energy(tension=0.05, conflict=0.0, idx=i) for i in range(_FLAT_WINDOW)]
    hints = detect_flow_hints(energies)
    flat = [h for h in hints if h.kind == "flat"]
    assert len(flat) == 1
    assert flat[0].start == 0
    assert flat[0].end == _FLAT_WINDOW - 1
    assert "flat" in flat[0].message.lower()


def test_flat_not_triggered_below_window():
    energies = [_make_energy(tension=0.05, conflict=0.0, idx=i) for i in range(_FLAT_WINDOW - 1)]
    hints = detect_flow_hints(energies)
    assert not any(h.kind == "flat" for h in hints)


def test_flat_not_triggered_with_tension():
    energies = [_make_energy(tension=0.3, conflict=0.0, idx=i) for i in range(_FLAT_WINDOW + 2)]
    hints = detect_flow_hints(energies)
    assert not any(h.kind == "flat" for h in hints)


def test_flat_broken_by_mid_tension():
    energies = [_make_energy(tension=0.05, idx=i) for i in range(3)]
    energies.append(_make_energy(tension=0.5, idx=3))
    energies += [_make_energy(tension=0.05, idx=i) for i in range(4, 7)]
    hints = detect_flow_hints(energies)
    assert not any(h.kind == "flat" for h in hints)


def test_pacing_spike_detected():
    energies = [
        _make_energy(pacing=0.2, idx=0),
        _make_energy(pacing=0.2, idx=1),
        _make_energy(pacing=0.8, idx=2),
    ]
    hints = detect_flow_hints(energies)
    spikes = [h for h in hints if h.kind == "pacing_spike"]
    assert len(spikes) == 1
    assert spikes[0].start == 2
    assert "spike" in spikes[0].message.lower()


def test_pacing_drop_detected():
    energies = [
        _make_energy(pacing=0.8, idx=0),
        _make_energy(pacing=0.8, idx=1),
        _make_energy(pacing=0.2, idx=2),
    ]
    hints = detect_flow_hints(energies)
    drops = [h for h in hints if h.kind == "pacing_drop"]
    assert len(drops) == 1
    assert "drop" in drops[0].message.lower()


def test_pacing_no_spike_on_small_delta():
    energies = [
        _make_energy(pacing=0.4, idx=0),
        _make_energy(pacing=0.4, idx=1),
        _make_energy(pacing=0.5, idx=2),
    ]
    hints = detect_flow_hints(energies)
    assert not any("pacing" in h.kind for h in hints)


def test_no_emotion_detected():
    energies = [_make_energy(emotional_shift=0.0, idx=i) for i in range(_EMOTION_WINDOW)]
    hints = detect_flow_hints(energies)
    emotion = [h for h in hints if h.kind == "no_emotion"]
    assert len(emotion) == 1
    assert "constant" in emotion[0].message.lower()


def test_no_emotion_not_triggered_below_window():
    energies = [_make_energy(emotional_shift=0.0, idx=i) for i in range(_EMOTION_WINDOW - 1)]
    hints = detect_flow_hints(energies)
    assert not any(h.kind == "no_emotion" for h in hints)


def test_no_emotion_broken_by_shift():
    energies = [_make_energy(emotional_shift=0.0, idx=i) for i in range(3)]
    energies.append(_make_energy(emotional_shift=0.5, idx=3))
    energies += [_make_energy(emotional_shift=0.0, idx=i) for i in range(4, 7)]
    hints = detect_flow_hints(energies)
    assert not any(h.kind == "no_emotion" for h in hints)


def test_mixed_text_no_false_positives():
    texts = [
        "She feared the darkness that lurked in every shadow.",
        "They fought and argued over the plan.",
        "He laughed, then sobbed with grief.",
        "The sun rose quietly over the hills.",
        "She ran and jumped over the fence!",
    ]
    energies = [compute_paragraph_energy(i, 1, t) for i, t in enumerate(texts)]
    hints = detect_flow_hints(energies)
    assert not any(h.kind == "flat" for h in hints)


def test_all_calm_text_triggers_flat():
    texts = [
        "The table was wooden.",
        "The chair was also wooden.",
        "The floor was clean.",
        "The window was open.",
        "The curtain was white.",
    ]
    energies = [compute_paragraph_energy(i, 1, t) for i, t in enumerate(texts)]
    hints = detect_flow_hints(energies)
    flat = [h for h in hints if h.kind == "flat"]
    assert len(flat) >= 1


# -- LLM metric parsing -------------------------------------------------------

def test_parse_llm_metrics_valid():
    raw = '{"tension": 0.7, "pacing": 0.5, "conflict": 0.3, "emotional_shift": 0.2}'
    result = _parse_llm_metrics(raw)
    assert result == {"tension": 0.7, "pacing": 0.5, "conflict": 0.3, "emotional_shift": 0.2}


def test_parse_llm_metrics_with_surrounding_text():
    raw = 'Here are the metrics: {"tension": 0.8, "pacing": 0.4, "conflict": 0.1, "emotional_shift": 0.9} done.'
    result = _parse_llm_metrics(raw)
    assert result is not None
    assert result["tension"] == 0.8


def test_parse_llm_metrics_clamps_values():
    raw = '{"tension": 1.5, "pacing": -0.3, "conflict": 0.5, "emotional_shift": 0.0}'
    result = _parse_llm_metrics(raw)
    assert result["tension"] == 1.0
    assert result["pacing"] == 0.0


def test_parse_llm_metrics_missing_keys():
    raw = '{"tension": 0.5, "pacing": 0.3}'
    result = _parse_llm_metrics(raw)
    assert result is None


def test_parse_llm_metrics_invalid_json():
    result = _parse_llm_metrics("not json at all")
    assert result is None


def test_parse_llm_metrics_empty():
    result = _parse_llm_metrics("")
    assert result is None


# -- EnergyRefineWorker --------------------------------------------------------

def test_refine_worker_exists():
    from logosforge.paragraph_energy import EnergyRefineWorker
    assert EnergyRefineWorker is not None


def test_refine_worker_blends_on_success():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])

    from logosforge.paragraph_energy import EnergyRefineWorker

    heuristic = ParagraphEnergy(
        paragraph_id=0, scene_id=1,
        metrics={"tension": 0.2, "pacing": 0.4, "conflict": 0.6, "emotional_shift": 0.0},
    )
    llm_response = '{"tension": 0.8, "pacing": 0.6, "conflict": 0.4, "emotional_shift": 1.0}'

    results = []

    def mock_chat_completion(messages, **kwargs):
        return llm_response, False

    worker = EnergyRefineWorker(heuristic, "some text")
    worker.completed.connect(results.append)

    with patch("logosforge.assistant.chat_completion", mock_chat_completion), \
         patch("logosforge.paragraph_energy._build_provider"):
        worker.run()

    assert len(results) == 1
    blended = results[0]
    assert blended.metrics["tension"] == round(0.2 * 0.4 + 0.8 * 0.6, 3)
    assert blended.metrics["pacing"] == round(0.4 * 0.4 + 0.6 * 0.6, 3)


def test_refine_worker_emits_failed_on_bad_response():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])

    from logosforge.paragraph_energy import EnergyRefineWorker

    heuristic = ParagraphEnergy(
        paragraph_id=0, scene_id=1,
        metrics={"tension": 0.5, "pacing": 0.5, "conflict": 0.5, "emotional_shift": 0.5},
    )

    errors = []

    def mock_chat_completion(messages, **kwargs):
        return "I can't do that.", False

    worker = EnergyRefineWorker(heuristic, "text")
    worker.failed.connect(errors.append)

    with patch("logosforge.assistant.chat_completion", mock_chat_completion), \
         patch("logosforge.paragraph_energy._build_provider"):
        worker.run()

    assert len(errors) == 1


def test_refine_worker_emits_failed_on_exception():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])

    from logosforge.paragraph_energy import EnergyRefineWorker

    heuristic = ParagraphEnergy(
        paragraph_id=0, scene_id=1,
        metrics={"tension": 0.5, "pacing": 0.5, "conflict": 0.5, "emotional_shift": 0.5},
    )

    errors = []

    def mock_chat_completion(messages, **kwargs):
        raise ConnectionError("no server")

    worker = EnergyRefineWorker(heuristic, "text")
    worker.failed.connect(errors.append)

    with patch("logosforge.assistant.chat_completion", mock_chat_completion), \
         patch("logosforge.paragraph_energy._build_provider"):
        worker.run()

    assert len(errors) == 1
    assert "no server" in errors[0]


# -- StoryContext & PSYKE integration ------------------------------------------

def test_story_context_defaults():
    ctx = StoryContext()
    assert ctx.tension_boost == 0.0
    assert ctx.conflict_boost == 0.0
    assert ctx.emotional_boost == 0.0


def test_apply_story_context_no_boost_returns_same():
    e = ParagraphEnergy(paragraph_id=0, scene_id=1, metrics={"tension": 0.3, "conflict": 0.1, "emotional_shift": 0.0, "pacing": 0.5})
    ctx = StoryContext()
    result = apply_story_context(e, ctx)
    assert result is e


def test_apply_story_context_adjusts_tension():
    e = ParagraphEnergy(paragraph_id=0, scene_id=1, metrics={"tension": 0.3, "conflict": 0.1, "emotional_shift": 0.0, "pacing": 0.5})
    ctx = StoryContext(tension_boost=1.0)
    result = apply_story_context(e, ctx)
    assert result.tension == round(0.3 + 1.0 * _PSYKE_WEIGHT, 3)
    assert result.pacing == 0.5


def test_apply_story_context_adjusts_conflict():
    e = ParagraphEnergy(paragraph_id=0, scene_id=1, metrics={"tension": 0.0, "conflict": 0.2, "emotional_shift": 0.0, "pacing": 0.5})
    ctx = StoryContext(conflict_boost=0.5)
    result = apply_story_context(e, ctx)
    assert result.conflict == round(0.2 + 0.5 * _PSYKE_WEIGHT, 3)


def test_apply_story_context_adjusts_emotional():
    e = ParagraphEnergy(paragraph_id=0, scene_id=1, metrics={"tension": 0.0, "conflict": 0.0, "emotional_shift": 0.1, "pacing": 0.5})
    ctx = StoryContext(emotional_boost=1.0)
    result = apply_story_context(e, ctx)
    assert result.emotional_shift == round(0.1 + 1.0 * _PSYKE_WEIGHT, 3)


def test_apply_story_context_caps_at_one():
    e = ParagraphEnergy(paragraph_id=0, scene_id=1, metrics={"tension": 0.95, "conflict": 0.0, "emotional_shift": 0.0, "pacing": 0.5})
    ctx = StoryContext(tension_boost=1.0)
    result = apply_story_context(e, ctx)
    assert result.tension <= 1.0


def test_apply_story_context_preserves_ids():
    e = ParagraphEnergy(paragraph_id=5, scene_id=7, metrics={"tension": 0.0, "conflict": 0.0, "emotional_shift": 0.0, "pacing": 0.5})
    ctx = StoryContext(tension_boost=0.5)
    result = apply_story_context(e, ctx)
    assert result.paragraph_id == 5
    assert result.scene_id == 7


def test_analyze_scene_with_context():
    clear_cache()
    ctx = StoryContext(tension_boost=1.0, conflict_boost=1.0)
    without = analyze_scene_energy(1, "The table was wooden.")
    with_ctx = analyze_scene_energy(1, "The table was wooden.", context=ctx)
    assert with_ctx[0].tension > without[0].tension
    assert with_ctx[0].conflict > without[0].conflict


def test_analyze_scene_no_context_unchanged():
    clear_cache()
    a = analyze_scene_energy(1, "Hello world.")
    b = analyze_scene_energy(1, "Hello world.", context=None)
    assert a[0].tension == b[0].tension


def test_build_story_context_empty():
    from logosforge.db import Database
    db = Database()
    proj = db.create_project("CtxEmpty")
    scene = db.create_scene(proj.id, "S1", content="Text.")
    ctx = build_story_context(db, proj.id, scene.id)
    assert ctx.tension_boost == 0.0
    assert ctx.conflict_boost == 0.0
    assert ctx.emotional_boost == 0.0


def test_build_story_context_character_state_tension():
    from logosforge.db import Database
    db = Database()
    proj = db.create_project("CtxTension")
    char = db.create_character(proj.id, "Alice")
    scene = db.create_scene(
        proj.id, "S1", content="Text.",
        character_ids=[char.id],
        character_states=[(char.id, "Alice is terrified and trapped in the dungeon")],
    )
    ctx = build_story_context(db, proj.id, scene.id)
    assert ctx.tension_boost > 0.0


def test_build_story_context_memory_conflict():
    from logosforge.db import Database
    db = Database()
    proj = db.create_project("CtxConflict")
    scene = db.create_scene(proj.id, "S1", content="Text.")
    db.add_memory(proj.id, scene.id, "relationship", "Bob", "Bob is a rival and enemy of Alice")
    ctx = build_story_context(db, proj.id, scene.id)
    assert ctx.conflict_boost > 0.0


def test_build_story_context_memory_emotional():
    from logosforge.db import Database
    db = Database()
    proj = db.create_project("CtxEmotion")
    scene = db.create_scene(proj.id, "S1", content="Text.")
    db.add_memory(proj.id, scene.id, "character_state", "Alice", "Alice feels deep grief and sorrow")
    ctx = build_story_context(db, proj.id, scene.id)
    assert ctx.emotional_boost > 0.0


def test_build_story_context_combined_signals():
    from logosforge.db import Database
    db = Database()
    proj = db.create_project("CtxCombined")
    char = db.create_character(proj.id, "Bob")
    scene = db.create_scene(
        proj.id, "S1", content="Text.",
        character_ids=[char.id],
        character_states=[(char.id, "Bob is scared and hostile, filled with grief")],
    )
    ctx = build_story_context(db, proj.id, scene.id)
    assert ctx.tension_boost > 0.0
    assert ctx.conflict_boost > 0.0
    assert ctx.emotional_boost > 0.0


def test_changing_psyke_changes_energy():
    from logosforge.db import Database
    clear_cache()
    db = Database()
    proj = db.create_project("CtxChange")
    char = db.create_character(proj.id, "Eve")
    scene = db.create_scene(proj.id, "S1", content="The room was quiet.")

    ctx_neutral = build_story_context(db, proj.id, scene.id)
    e_neutral = analyze_scene_energy(scene.id, "The room was quiet.", context=ctx_neutral)

    db.update_scene(
        scene.id, "S1", content="The room was quiet.",
        character_ids=[char.id],
        character_states=[(char.id, "Eve is trapped and fears betrayal from her enemy")],
    )
    ctx_conflict = build_story_context(db, proj.id, scene.id)
    e_conflict = analyze_scene_energy(scene.id, "The room was quiet.", context=ctx_conflict)

    assert e_conflict[0].tension > e_neutral[0].tension
    assert e_conflict[0].conflict > e_neutral[0].conflict
