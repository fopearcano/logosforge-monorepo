"""Tests for style_analysis — ParagraphStyle model and metric computation."""

from unittest.mock import patch

from logosforge.style_analysis import (
    STYLE_SENSITIVITY_LEVELS,
    ParagraphStyle,
    StyleContext,
    StyleHint,
    StyleSuggestion,
    _STYLE_PSYKE_WEIGHT,
    _parse_style_metrics,
    analyze_paragraph,
    analyze_paragraphs,
    analyze_style,
    apply_style_context,
    build_style_context,
    clear_cache,
    detect_style_hints,
    generate_style_suggestions,
)


# -- ParagraphStyle model -----------------------------------------------------

def test_model_creation():
    ps = ParagraphStyle(paragraph_id=0, metrics={"clarity": 0.9}, notes=[])
    assert ps.paragraph_id == 0
    assert ps.metrics == {"clarity": 0.9}
    assert ps.notes == []
    assert ps.last_updated > 0


def test_model_defaults():
    ps = ParagraphStyle(paragraph_id=5)
    assert ps.paragraph_id == 5
    assert ps.metrics == {}
    assert ps.notes == []
    assert ps.last_updated > 0


def test_model_with_notes():
    ps = ParagraphStyle(
        paragraph_id=1,
        metrics={"clarity": 0.4},
        notes=["Sentences may be too complex or long"],
    )
    assert len(ps.notes) == 1
    assert "complex" in ps.notes[0]


def test_model_custom_timestamp():
    ps = ParagraphStyle(paragraph_id=0, last_updated=1000.0)
    assert ps.last_updated == 1000.0


def test_model_auto_timestamp():
    import time
    before = time.time()
    ps = ParagraphStyle(paragraph_id=0)
    after = time.time()
    assert before <= ps.last_updated <= after


# -- analyze_paragraph -------------------------------------------------------

def test_analyze_returns_paragraph_style():
    result = analyze_paragraph(0, "The dog ran across the field.")
    assert isinstance(result, ParagraphStyle)
    assert result.paragraph_id == 0


def test_analyze_has_all_base_metrics():
    result = analyze_paragraph(0, "The dog ran across the field quickly.")
    assert "clarity" in result.metrics
    assert "concision" in result.metrics
    assert "rhythm" in result.metrics
    assert "tone_consistency" in result.metrics


def test_analyze_metrics_in_range():
    result = analyze_paragraph(0, "She walked home. The rain fell softly.")
    for key, val in result.metrics.items():
        assert 0.0 <= val <= 1.0, f"{key} = {val} out of range"


def test_analyze_clean_prose_high_scores():
    text = (
        "The old man sat by the window. Rain tapped against the glass. "
        "He sipped his coffee and watched the street below."
    )
    result = analyze_paragraph(0, text)
    assert result.metrics["clarity"] >= 0.7
    assert result.metrics["concision"] >= 0.7
    assert result.metrics["tone_consistency"] >= 0.7


def test_analyze_wordy_prose_low_concision():
    text = (
        "He was very really quite honestly just basically totally completely "
        "absolutely definitely certainly perhaps maybe somewhat rather actually "
        "going to the store."
    )
    result = analyze_paragraph(0, text)
    assert result.metrics["concision"] < 0.6


def test_analyze_long_sentences_low_clarity():
    text = (
        "The man who was standing by the door which was old and creaky and "
        "which had been painted several times over the years although it was "
        "still showing signs of wear and tear from the weather and the many "
        "people who had passed through it on their way to the garden that "
        "stretched out behind the house and which was full of flowers and "
        "trees that had been planted by his grandmother many years ago."
    )
    result = analyze_paragraph(0, text)
    assert result.metrics["clarity"] < 0.7


def test_analyze_uniform_sentences_low_rhythm():
    text = (
        "The dog ran fast. The cat sat down. The man walked home. "
        "The bird flew high. The sun went down. The moon came out."
    )
    result = analyze_paragraph(0, text)
    assert result.metrics["rhythm"] <= 0.7


def test_analyze_varied_rhythm_high_score():
    text = (
        "She stopped. The long, winding road stretched out before her, "
        "disappearing into the mist that clung to the distant hills. "
        "She breathed. Then she walked on."
    )
    result = analyze_paragraph(0, text)
    assert result.metrics["rhythm"] >= 0.7


# -- Dialogue ----------------------------------------------------------------

def test_dialogue_detected():
    text = '"I don\'t think so," he said. "Not today."'
    result = analyze_paragraph(0, text)
    assert "dialogue_naturalness" in result.metrics


def test_no_dialogue_no_metric():
    text = "The sun set behind the mountains."
    result = analyze_paragraph(0, text)
    assert "dialogue_naturalness" not in result.metrics


def test_natural_dialogue_high_score():
    text = '"Hey, what\'s going on?" she asked. "Nothing much," he said.'
    result = analyze_paragraph(0, text)
    assert result.metrics["dialogue_naturalness"] >= 0.7


def test_stilted_dialogue_lower_score():
    text = (
        '"I must confess that the preponderance of evidence which has been '
        'accumulated over the course of our extraordinarily comprehensive '
        'investigation leads me to the inescapable conclusion that the '
        'perpetrator of these unconscionable acts is none other than the '
        'individual who has been systematically undermining our institutional '
        'frameworks," he declared solemnly.'
    )
    result = analyze_paragraph(0, text)
    dn = result.metrics.get("dialogue_naturalness", 1.0)
    assert dn <= 0.8


# -- Notes -------------------------------------------------------------------

def test_notes_generated_for_low_clarity():
    text = (
        "The man who was standing by the door which was old and creaky and "
        "which had been painted several times over the years although it was "
        "still showing signs of wear and tear from the weather and the many "
        "people who had passed through it."
    )
    result = analyze_paragraph(0, text)
    if result.metrics["clarity"] < 0.6:
        assert any("complex" in n.lower() or "long" in n.lower() for n in result.notes)


def test_notes_generated_for_low_concision():
    text = (
        "He was very really quite honestly just basically totally completely "
        "absolutely definitely going to the store."
    )
    result = analyze_paragraph(0, text)
    assert any("filler" in n.lower() for n in result.notes)


def test_clean_prose_no_notes():
    text = "The old man sat by the window. He watched the rain."
    result = analyze_paragraph(0, text)
    assert len(result.notes) == 0


# -- analyze_paragraphs (multi) -----------------------------------------------

def test_analyze_paragraphs_returns_list():
    text = "First paragraph here.\n\nSecond paragraph here."
    results = analyze_paragraphs(text)
    assert isinstance(results, list)
    assert len(results) == 2


def test_analyze_paragraphs_ids_sequential():
    text = "One.\n\nTwo.\n\nThree."
    results = analyze_paragraphs(text)
    assert [r.paragraph_id for r in results] == [0, 1, 2]


def test_analyze_paragraphs_empty_text():
    results = analyze_paragraphs("")
    assert results == []


def test_analyze_paragraphs_blank_lines_skipped():
    text = "Hello.\n\n\n\nWorld."
    results = analyze_paragraphs(text)
    assert len(results) == 2


def test_analyze_paragraphs_single():
    text = "Just one paragraph."
    results = analyze_paragraphs(text)
    assert len(results) == 1
    assert results[0].paragraph_id == 0


# -- Edge cases ---------------------------------------------------------------

def test_empty_paragraph():
    result = analyze_paragraph(0, "")
    assert result.metrics["clarity"] == 1.0
    assert result.metrics["concision"] == 1.0


def test_single_word():
    result = analyze_paragraph(0, "Hello")
    for val in result.metrics.values():
        assert 0.0 <= val <= 1.0


def test_paragraph_id_preserved():
    result = analyze_paragraph(42, "Test text.")
    assert result.paragraph_id == 42


def test_metrics_are_rounded():
    result = analyze_paragraph(0, "She walked home. The rain fell softly.")
    for val in result.metrics.values():
        s = str(val)
        if "." in s:
            decimals = len(s.split(".")[1])
            assert decimals <= 3


# -- analyze_style (cached API) ------------------------------------------------

def test_analyze_style_returns_paragraph_style():
    clear_cache()
    result = analyze_style("The dog ran across the field.")
    assert isinstance(result, ParagraphStyle)
    assert "clarity" in result.metrics


def test_analyze_style_cache_hit():
    clear_cache()
    text = "The fox jumped over the lazy dog."
    first = analyze_style(text)
    second = analyze_style(text)
    assert first is second


def test_analyze_style_different_texts_not_cached():
    clear_cache()
    a = analyze_style("Hello world.")
    b = analyze_style("Goodbye world.")
    assert a is not b


def test_cache_cleared_by_clear_cache():
    clear_cache()
    text = "Cached paragraph text."
    first = analyze_style(text)
    clear_cache()
    second = analyze_style(text)
    assert first is not second


def test_cache_eviction_at_max():
    clear_cache()
    for i in range(520):
        analyze_style(f"Paragraph number {i} unique text here.")
    from logosforge.style_analysis import _style_cache
    assert len(_style_cache) <= 512


# -- Different texts produce different metrics ---------------------------------

def test_different_texts_different_clarity():
    clear_cache()
    clear_text = "She ran. He jumped. They stopped."
    muddy_text = (
        "The individual who was previously situated adjacent to the "
        "antiquated door which had been constructed approximately "
        "forty-seven years previously although the precise date remained "
        "somewhat uncertain among the various inhabitants."
    )
    a = analyze_style(clear_text)
    b = analyze_style(muddy_text)
    assert a.metrics["clarity"] > b.metrics["clarity"]


def test_different_texts_different_concision():
    clear_cache()
    tight = "He sprinted across the field."
    wordy = (
        "He was very really quite basically just honestly totally "
        "completely absolutely definitely running across the field."
    )
    a = analyze_style(tight)
    b = analyze_style(wordy)
    assert a.metrics["concision"] > b.metrics["concision"]


def test_different_texts_different_rhythm():
    clear_cache()
    uniform = (
        "The dog ran fast. The cat sat down. The man went home. "
        "The bird flew up. The sun went down."
    )
    varied = (
        "She stopped. The long winding road stretched out before her, "
        "disappearing into mist. She breathed. Then she walked on."
    )
    a = analyze_style(varied)
    b = analyze_style(uniform)
    assert a.metrics["rhythm"] > b.metrics["rhythm"]


# -- Repeated words → lower clarity -------------------------------------------

def test_repeated_words_lower_clarity():
    clean = "The cat sat on the mat. She looked out the window."
    repetitive = (
        "The castle stood on the castle hill. The castle walls "
        "surrounded the castle grounds near the castle gate."
    )
    a = analyze_paragraph(0, clean)
    b = analyze_paragraph(0, repetitive)
    assert a.metrics["clarity"] > b.metrics["clarity"]


def test_repeated_word_note():
    text = (
        "The castle stood on the castle hill. The castle walls "
        "surrounded the castle grounds near the castle gate."
    )
    result = analyze_paragraph(0, text)
    assert any("repeat" in n.lower() for n in result.notes)


# -- Adverb detection ---------------------------------------------------------

def test_excessive_adverbs_lower_concision():
    clean = "He walked to the door and opened it."
    adverby = (
        "He extremely quickly walked to the incredibly enormous door "
        "and very slowly, deeply, completely opened it."
    )
    a = analyze_paragraph(0, clean)
    b = analyze_paragraph(0, adverby)
    assert a.metrics["concision"] > b.metrics["concision"]


def test_adverb_note():
    text = (
        "She very slowly and extremely carefully and incredibly "
        "thoroughly and deeply completely examined the room."
    )
    result = analyze_paragraph(0, text)
    assert any("adverb" in n.lower() for n in result.notes)


# -- Dialogue punctuation -----------------------------------------------------

def test_dialogue_excessive_exclamation():
    normal = '"Hey," she said. "What happened?"'
    loud = '"Hey!!! What!!! Is!!! Going!!!! On!!!!" she screamed.'
    a = analyze_paragraph(0, normal)
    b = analyze_paragraph(0, loud)
    dn_a = a.metrics.get("dialogue_naturalness", 1.0)
    dn_b = b.metrics.get("dialogue_naturalness", 1.0)
    assert dn_a >= dn_b


def test_dialogue_semicolons_lower_naturalness():
    natural = '"I think we should go," he said.'
    stilted = '"I think; however, we should consider; perhaps, going," he said.'
    a = analyze_paragraph(0, natural)
    b = analyze_paragraph(0, stilted)
    dn_a = a.metrics.get("dialogue_naturalness", 1.0)
    dn_b = b.metrics.get("dialogue_naturalness", 1.0)
    assert dn_a > dn_b


# -- Long sentences → lower concision -----------------------------------------

def test_long_sentences_lower_concision():
    short = "He sat. She stood. The door opened."
    long_sent = (
        "The man who was standing by the ancient and weathered door which "
        "had been built many decades ago opened it with a slow and careful "
        "motion of his hand while glancing nervously over his shoulder at "
        "the crowd that had gathered behind him in the narrow hallway."
    )
    a = analyze_paragraph(0, short)
    b = analyze_paragraph(0, long_sent)
    assert a.metrics["concision"] > b.metrics["concision"]


# -- LLM metric parsing -------------------------------------------------------

def test_parse_style_metrics_valid():
    raw = '{"clarity": 0.8, "concision": 0.7, "rhythm": 0.9, "tone_consistency": 0.85}'
    result = _parse_style_metrics(raw)
    assert result is not None
    assert result["clarity"] == 0.8
    assert result["rhythm"] == 0.9


def test_parse_style_metrics_with_dialogue():
    raw = '{"clarity": 0.8, "concision": 0.7, "rhythm": 0.9, "tone_consistency": 0.85, "dialogue_naturalness": 0.6}'
    result = _parse_style_metrics(raw)
    assert result is not None
    assert "dialogue_naturalness" in result


def test_parse_style_metrics_clamps():
    raw = '{"clarity": 1.5, "concision": -0.3, "rhythm": 0.5, "tone_consistency": 0.8}'
    result = _parse_style_metrics(raw)
    assert result["clarity"] == 1.0
    assert result["concision"] == 0.0


def test_parse_style_metrics_missing_keys():
    raw = '{"clarity": 0.8, "concision": 0.7}'
    result = _parse_style_metrics(raw)
    assert result is None


def test_parse_style_metrics_invalid_json():
    assert _parse_style_metrics("not json") is None


def test_parse_style_metrics_empty():
    assert _parse_style_metrics("") is None


def test_parse_style_metrics_with_surrounding_text():
    raw = 'Here are the metrics: {"clarity": 0.9, "concision": 0.8, "rhythm": 0.7, "tone_consistency": 0.6} done.'
    result = _parse_style_metrics(raw)
    assert result is not None
    assert result["clarity"] == 0.9


# -- StyleRefineWorker ---------------------------------------------------------

def test_refine_worker_exists():
    from logosforge.style_analysis import StyleRefineWorker
    assert StyleRefineWorker is not None


def test_refine_worker_blends_on_success():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])

    from logosforge.style_analysis import StyleRefineWorker

    heuristic = ParagraphStyle(
        paragraph_id=0,
        metrics={"clarity": 0.4, "concision": 0.6, "rhythm": 0.8, "tone_consistency": 0.5},
    )
    llm_response = '{"clarity": 0.8, "concision": 0.4, "rhythm": 0.6, "tone_consistency": 0.9}'

    results = []

    def mock_chat(messages, **kwargs):
        return llm_response, False

    worker = StyleRefineWorker(heuristic, "some text")
    worker.completed.connect(results.append)

    with patch("logosforge.assistant.chat_completion", mock_chat), \
         patch("logosforge.style_analysis._build_provider"):
        worker.run()

    assert len(results) == 1
    blended = results[0]
    assert blended.metrics["clarity"] == round(0.4 * 0.4 + 0.8 * 0.6, 3)
    assert blended.metrics["concision"] == round(0.6 * 0.4 + 0.4 * 0.6, 3)


def test_refine_worker_emits_failed_on_bad_response():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])

    from logosforge.style_analysis import StyleRefineWorker

    heuristic = ParagraphStyle(
        paragraph_id=0,
        metrics={"clarity": 0.5, "concision": 0.5, "rhythm": 0.5, "tone_consistency": 0.5},
    )

    errors = []

    def mock_chat(messages, **kwargs):
        return "I can't do that.", False

    worker = StyleRefineWorker(heuristic, "text")
    worker.failed.connect(errors.append)

    with patch("logosforge.assistant.chat_completion", mock_chat), \
         patch("logosforge.style_analysis._build_provider"):
        worker.run()

    assert len(errors) == 1


def test_refine_worker_emits_failed_on_exception():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])

    from logosforge.style_analysis import StyleRefineWorker

    heuristic = ParagraphStyle(
        paragraph_id=0,
        metrics={"clarity": 0.5, "concision": 0.5, "rhythm": 0.5, "tone_consistency": 0.5},
    )

    errors = []

    def mock_chat(messages, **kwargs):
        raise ConnectionError("no server")

    worker = StyleRefineWorker(heuristic, "text")
    worker.failed.connect(errors.append)

    with patch("logosforge.assistant.chat_completion", mock_chat), \
         patch("logosforge.style_analysis._build_provider"):
        worker.run()

    assert len(errors) == 1
    assert "no server" in errors[0]


# -- detect_style_hints -------------------------------------------------------

def test_hints_empty_text():
    assert detect_style_hints("") == []


def test_hints_clean_prose_no_hints():
    text = "She walked home. The rain fell softly. He opened the door."
    hints = detect_style_hints(text)
    assert len(hints) == 0


def test_hints_long_sentence_detected():
    text = (
        "The man who was standing by the ancient and weathered door which "
        "had been built many decades ago opened it with a slow and careful "
        "motion of his hand while glancing nervously over his shoulder at "
        "the crowd that had gathered behind him in the narrow hallway "
        "leading to the old abandoned wing of the enormous building."
    )
    hints = detect_style_hints(text)
    clarity = [h for h in hints if h.hint_type == "clarity"]
    assert len(clarity) >= 1
    assert clarity[0].message == "Sentence may be too long"


def test_hints_long_sentence_positions():
    text = "Short. " + "word " * 35 + "end."
    hints = detect_style_hints(text)
    clarity = [h for h in hints if h.hint_type == "clarity"]
    assert len(clarity) >= 1
    assert clarity[0].start >= 0
    assert clarity[0].end <= len(text)


def test_hints_repetition_detected():
    text = (
        "The castle stood on the castle hill near the castle walls "
        "surrounding the castle grounds."
    )
    hints = detect_style_hints(text)
    reps = [h for h in hints if h.hint_type == "repetition"]
    assert len(reps) >= 1
    assert reps[0].message == "Repetition detected"


def test_hints_no_repetition_for_normal_text():
    text = "The cat sat on the mat. The dog ran in the park."
    hints = detect_style_hints(text)
    reps = [h for h in hints if h.hint_type == "repetition"]
    assert len(reps) == 0


def test_hints_rhythm_detected():
    text = (
        "The dog ran fast. The cat sat down. The man went home. "
        "The bird flew up. The sun went down."
    )
    hints = detect_style_hints(text)
    rhythm = [h for h in hints if h.hint_type == "rhythm"]
    assert len(rhythm) >= 1
    assert rhythm[0].message == "Rhythm feels monotonous"


def test_hints_no_rhythm_for_varied_text():
    text = (
        "She stopped. The long winding road stretched out before her, "
        "disappearing into the mist that clung to the distant hills. "
        "She breathed deeply. Then she walked on, determined and resolute."
    )
    hints = detect_style_hints(text)
    rhythm = [h for h in hints if h.hint_type == "rhythm"]
    assert len(rhythm) == 0


def test_hints_dialogue_stiff():
    long_quote = "word " * 55
    text = f'"{long_quote.strip()}," he said.'
    hints = detect_style_hints(text)
    dlg = [h for h in hints if h.hint_type == "dialogue"]
    assert len(dlg) >= 1
    assert dlg[0].message == "Dialogue feels stiff"


def test_hints_dialogue_ok():
    text = '"Hey, how are you?" she asked. "Fine," he said.'
    hints = detect_style_hints(text)
    dlg = [h for h in hints if h.hint_type == "dialogue"]
    assert len(dlg) == 0


def test_hints_max_capped():
    long_sent = "word " * 35 + "end. "
    text = long_sent * 6
    hints = detect_style_hints(text)
    assert len(hints) <= 3


def test_hints_are_style_hint_instances():
    text = "word " * 35 + "end."
    hints = detect_style_hints(text)
    for h in hints:
        assert isinstance(h, StyleHint)
        assert isinstance(h.start, int)
        assert isinstance(h.end, int)
        assert isinstance(h.message, str)


def test_hints_positions_within_text():
    text = "Short sentence. " + "word " * 35 + "end."
    hints = detect_style_hints(text)
    for h in hints:
        assert 0 <= h.start < len(text)
        assert h.start < h.end <= len(text)


# -- Style hints UI integration -----------------------------------------------

def test_style_hints_toggle():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from logosforge.db import Database
    from logosforge.ui.writing_core_view import WritingCoreView

    db = Database()
    proj = db.create_project("StyleToggle")
    db.create_scene(proj.id, "S", content="Hello.")
    view = WritingCoreView(db, proj.id)
    assert not view._style_hints_checking
    view._toggle_style_hints()
    assert view._style_hints_checking
    view._toggle_style_hints()
    assert not view._style_hints_checking


def test_style_hints_persist():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from logosforge.db import Database
    from logosforge.ui.writing_core_view import WritingCoreView

    db = Database()
    proj = db.create_project("StylePersist")
    db.create_scene(proj.id, "S", content="Hello.")
    view = WritingCoreView(db, proj.id)
    view._toggle_style_hints()
    saved = db.get_project_settings(proj.id)
    assert saved["style_hints"] is True


def test_style_hints_restore():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from logosforge.db import Database
    from logosforge.ui.writing_core_view import WritingCoreView

    db = Database()
    proj = db.create_project("StyleRestore")
    settings = db.get_project_settings(proj.id)
    settings["style_hints"] = True
    db.save_project_settings(proj.id, settings)
    db.create_scene(proj.id, "S", content="Hello.")
    view = WritingCoreView(db, proj.id)
    assert view._style_hints_checking


def test_style_hints_default_off():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from logosforge.db import Database
    from logosforge.ui.writing_core_view import WritingCoreView

    db = Database()
    proj = db.create_project("StyleDefault")
    db.create_scene(proj.id, "S", content="Hello.")
    view = WritingCoreView(db, proj.id)
    assert not view._style_hints_checking
    editor = list(view._editors.values())[0]
    assert not editor._style_hints_enabled


def test_style_hints_toggle_clears_hints():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from logosforge.db import Database
    from logosforge.ui.writing_core_view import WritingCoreView

    db = Database()
    proj = db.create_project("StyleClear")
    scene = db.create_scene(proj.id, "S", content="Hello.")
    view = WritingCoreView(db, proj.id)
    editor = view._editors[scene.id]
    editor._style_hints = [StyleHint(0, 5, "clarity", "Test")]
    view._toggle_style_hints()
    view._toggle_style_hints()
    assert editor._style_hints == []


# -- generate_style_suggestions -----------------------------------------------

def test_suggestions_empty_text():
    suggestions, rewrite = generate_style_suggestions("")
    assert suggestions == []
    assert rewrite is None


def test_suggestions_clean_prose():
    text = "She walked home. The rain fell softly. He opened the door."
    suggestions, rewrite = generate_style_suggestions(text)
    assert len(suggestions) <= 3
    assert rewrite is None or isinstance(rewrite, str)


def test_suggestions_returns_style_suggestion_instances():
    text = (
        "The man who was standing by the really very ancient and weathered door "
        "which had been basically built many decades ago really just opened it."
    )
    suggestions, _ = generate_style_suggestions(text)
    for s in suggestions:
        assert isinstance(s, StyleSuggestion)
        assert isinstance(s.category, str)
        assert isinstance(s.message, str)


def test_suggestions_filler_words_trigger_concision():
    text = (
        "He was really very just basically totally completely honestly "
        "simply absolutely definitely standing there."
    )
    suggestions, _ = generate_style_suggestions(text)
    categories = [s.category for s in suggestions]
    assert "concision" in categories


def test_suggestions_long_sentences_trigger_clarity():
    text = (
        "The man who was standing by the ancient and weathered door which "
        "had been built many decades ago opened it with a slow and careful "
        "motion of his hand while glancing nervously over his shoulder at "
        "the crowd that had gathered behind him in the narrow hallway."
    )
    suggestions, _ = generate_style_suggestions(text)
    categories = [s.category for s in suggestions]
    assert "clarity" in categories


def test_suggestions_monotonous_rhythm():
    text = (
        "The dog ran fast. The cat sat down. The man went home. "
        "The bird flew up. The sun went down."
    )
    suggestions, _ = generate_style_suggestions(text)
    categories = [s.category for s in suggestions]
    assert "rhythm" in categories


def test_suggestions_max_three():
    text = (
        "He was really very basically standing by the quite totally honestly "
        "extremely absolutely completely ancient door which had been simply "
        "definitely certainly built. He was really very basically standing. "
        "He was really very basically standing. He was really very basically "
        "standing. He was really very basically standing."
    )
    suggestions, _ = generate_style_suggestions(text)
    assert len(suggestions) <= 3


def test_suggestions_rewrite_removes_fillers():
    text = "He very really just basically walked to the store."
    suggestions, rewrite = generate_style_suggestions(text)
    if rewrite is not None:
        assert "very" not in rewrite.lower().split()
        assert "really" not in rewrite.lower().split()
        assert "basically" not in rewrite.lower().split()


def test_suggestions_rewrite_none_when_clean():
    text = "She walked home. The rain fell softly."
    _, rewrite = generate_style_suggestions(text)
    assert rewrite is None


# -- Style suggestions UI integration -----------------------------------------

def test_style_suggestion_popup_shows():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from logosforge.ui.writing_core_view import _StyleSuggestionPopup

    popup = _StyleSuggestionPopup()
    suggestions = [
        StyleSuggestion("clarity", "Break long sentences"),
        StyleSuggestion("concision", "Remove filler words"),
    ]
    popup.show_suggestions(suggestions, "Rewritten text.", popup.pos())
    assert len(popup._suggestion_labels) == 2
    assert popup._rewrite_btn is not None
    assert popup._rewrite_text == "Rewritten text."
    popup.hide()


def test_style_suggestion_popup_no_rewrite():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from logosforge.ui.writing_core_view import _StyleSuggestionPopup

    popup = _StyleSuggestionPopup()
    suggestions = [StyleSuggestion("rhythm", "Vary sentence lengths")]
    popup.show_suggestions(suggestions, None, popup.pos())
    assert len(popup._suggestion_labels) == 1
    assert popup._rewrite_btn is None
    popup.hide()


def test_style_suggestion_popup_empty():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from logosforge.ui.writing_core_view import _StyleSuggestionPopup

    popup = _StyleSuggestionPopup()
    popup.show_suggestions([], None, popup.pos())
    assert len(popup._suggestion_labels) == 0
    assert popup._rewrite_btn is None
    popup.hide()


def test_selection_triggers_suggestions():
    from PySide6.QtGui import QTextCursor
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from logosforge.db import Database
    from logosforge.ui.writing_core_view import WritingCoreView

    db = Database()
    proj = db.create_project("StyleSuggest")
    content = (
        "He was really very just basically totally completely honestly "
        "simply absolutely definitely standing there by the door."
    )
    scene = db.create_scene(proj.id, "S", content=content)
    view = WritingCoreView(db, proj.id)
    editor = view._editors[scene.id]

    cursor = editor.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    editor.setTextCursor(cursor)

    gpos = editor.mapToGlobal(editor.cursorRect().bottomLeft())
    editor._show_style_suggestions(gpos)

    assert editor._style_suggestion_popup.isVisible()
    assert len(editor._style_suggestion_popup._suggestion_labels) >= 1
    editor._style_suggestion_popup.hide()


# -- StyleContext & PSYKE-aware style -----------------------------------------

def test_style_context_defaults():
    ctx = StyleContext()
    assert ctx.stress_level == 0.0
    assert ctx.formality_level == 0.0
    assert ctx.emotional_intensity == 0.0


def test_apply_style_context_no_change_when_neutral():
    style = analyze_paragraph(0, "She walked home quickly.")
    ctx = StyleContext()
    adjusted = apply_style_context(style, ctx)
    assert adjusted.metrics == style.metrics


def test_apply_style_context_stress_boosts_rhythm():
    text = "Run. Hide. Go. Now. Fast. Move. Run. Hide."
    style = analyze_paragraph(0, text)
    ctx = StyleContext(stress_level=1.0)
    adjusted = apply_style_context(style, ctx)
    assert adjusted.metrics["rhythm"] >= style.metrics["rhythm"]


def test_apply_style_context_formality_boosts_tone():
    text = (
        "The ambassador addressed the assembly with measured eloquence. "
        "Yo that's wild right?"
    )
    style = analyze_paragraph(0, text)
    ctx = StyleContext(formality_level=1.0)
    adjusted = apply_style_context(style, ctx)
    assert adjusted.metrics["tone_consistency"] >= style.metrics["tone_consistency"]


def test_apply_style_context_formality_boosts_dialogue():
    text = (
        '"I must inform the committee that the resolution has been ratified '
        'by the governing body and shall henceforth be considered binding '
        'upon all signatories to the agreement," he declared.'
    )
    style = analyze_paragraph(0, text)
    if "dialogue_naturalness" in style.metrics:
        ctx = StyleContext(formality_level=1.0)
        adjusted = apply_style_context(style, ctx)
        assert adjusted.metrics["dialogue_naturalness"] >= style.metrics["dialogue_naturalness"]


def test_apply_style_context_emotion_boosts_tone():
    text = (
        "She screamed at the heavens! Then whispered a prayer. "
        "The fury subsided into quiet tears."
    )
    style = analyze_paragraph(0, text)
    ctx = StyleContext(emotional_intensity=1.0)
    adjusted = apply_style_context(style, ctx)
    assert adjusted.metrics["tone_consistency"] >= style.metrics["tone_consistency"]


def test_apply_style_context_caps_at_one():
    style = ParagraphStyle(
        paragraph_id=0,
        metrics={"rhythm": 0.99, "tone_consistency": 0.99, "dialogue_naturalness": 0.99},
    )
    ctx = StyleContext(stress_level=1.0, formality_level=1.0, emotional_intensity=1.0)
    adjusted = apply_style_context(style, ctx)
    assert adjusted.metrics["rhythm"] <= 1.0
    assert adjusted.metrics["tone_consistency"] <= 1.0
    assert adjusted.metrics["dialogue_naturalness"] <= 1.0


def test_apply_style_context_preserves_id_and_notes():
    style = ParagraphStyle(
        paragraph_id=42,
        metrics={"rhythm": 0.5, "clarity": 0.8},
        notes=["Test note"],
    )
    ctx = StyleContext(stress_level=0.5)
    adjusted = apply_style_context(style, ctx)
    assert adjusted.paragraph_id == 42
    assert adjusted.notes == ["Test note"]


def test_build_style_context_empty_db():
    from logosforge.db import Database
    db = Database()
    proj = db.create_project("StyleCtx")
    scene = db.create_scene(proj.id, "S", content="Hello.")
    ctx = build_style_context(db, proj.id, scene.id)
    assert ctx.stress_level == 0.0
    assert ctx.formality_level == 0.0
    assert ctx.emotional_intensity == 0.0


def test_build_style_context_from_character_states():
    from logosforge.db import Database
    db = Database()
    proj = db.create_project("StyleCtxChar")
    char = db.create_character(proj.id, "Hero")
    scene = db.create_scene(
        proj.id, "S", content="Hello.",
        character_ids=[char.id],
        character_states=[(char.id, "anxious and terrified, desperate")],
    )
    ctx = build_style_context(db, proj.id, scene.id)
    assert ctx.stress_level > 0.0


def test_build_style_context_from_memories():
    from logosforge.db import Database
    db = Database()
    proj = db.create_project("StyleCtxMem")
    scene = db.create_scene(proj.id, "S", content="Hello.")
    db.add_memory(proj.id, scene.id, "state", "character", "formal and dignified")
    ctx = build_style_context(db, proj.id, scene.id)
    assert ctx.formality_level > 0.0


def test_build_style_context_emotional():
    from logosforge.db import Database
    db = Database()
    proj = db.create_project("StyleCtxEmo")
    scene = db.create_scene(proj.id, "S", content="Hello.")
    db.add_memory(proj.id, scene.id, "state", "character", "grief and despair and anguish")
    ctx = build_style_context(db, proj.id, scene.id)
    assert ctx.emotional_intensity > 0.0


def test_same_text_different_psyke_different_suggestions():
    """Core test: same text, different PSYKE → different feedback."""
    text = (
        "The dog ran fast. The cat sat down. The man went home. "
        "The bird flew up. The sun went down."
    )
    neutral_suggestions, _ = generate_style_suggestions(text)
    stressed_suggestions, _ = generate_style_suggestions(
        text, context=StyleContext(stress_level=1.0),
    )
    neutral_cats = [s.category for s in neutral_suggestions]
    stressed_cats = [s.category for s in stressed_suggestions]
    assert "rhythm" in neutral_cats
    assert "rhythm" not in stressed_cats


def test_stressed_context_changes_rhythm_suggestion():
    text = "Run. Stop. Go. Now. Fast. Move. Run. Stop."
    neutral, _ = generate_style_suggestions(text)
    stressed, _ = generate_style_suggestions(
        text, context=StyleContext(stress_level=1.0),
    )
    neutral_rhythm = [s for s in neutral if s.category == "rhythm"]
    stressed_rhythm = [s for s in stressed if s.category == "rhythm"]
    assert len(neutral_rhythm) > 0
    assert len(stressed_rhythm) == 0


def test_formal_context_changes_dialogue_suggestion():
    text = (
        '"The matter; having been discussed; at length; requires further '
        'deliberation; before any conclusion can be drawn; from the evidence '
        'presented; to the committee; in its entirety," he said.'
    )
    neutral, _ = generate_style_suggestions(text)
    formal, _ = generate_style_suggestions(
        text, context=StyleContext(formality_level=1.0),
    )
    neutral_dlg = [s for s in neutral if s.category == "dialogue"]
    formal_dlg = [s for s in formal if s.category == "dialogue"]
    assert len(neutral_dlg) > 0
    assert len(formal_dlg) > 0
    assert neutral_dlg[0].message != formal_dlg[0].message


def test_emotional_context_changes_tone_suggestion():
    text = (
        "The ambassador deliberated with extraordinary circumspection. "
        "Yo that was totally wild bro! "
        "The proceedings concluded satisfactorily. "
        "Man what a crazy day!"
    )
    neutral, _ = generate_style_suggestions(text)
    emotional, _ = generate_style_suggestions(
        text, context=StyleContext(emotional_intensity=1.0),
    )
    neutral_tone = [s for s in neutral if s.category == "tone"]
    emotional_tone = [s for s in emotional if s.category == "tone"]
    assert len(neutral_tone) > 0
    assert len(emotional_tone) > 0
    assert neutral_tone[0].message != emotional_tone[0].message


def test_psyke_context_can_suppress_rhythm_suggestion():
    text = (
        "The dog ran fast. The cat sat down. The man went home. "
        "The bird flew up. The sun went down."
    )
    neutral, _ = generate_style_suggestions(text)
    stressed, _ = generate_style_suggestions(
        text, context=StyleContext(stress_level=1.0),
    )
    assert any(s.category == "rhythm" for s in neutral)
    assert not any(s.category == "rhythm" for s in stressed)


def test_editor_has_style_context():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from logosforge.db import Database
    from logosforge.ui.writing_core_view import WritingCoreView

    db = Database()
    proj = db.create_project("StyleCtxUI")
    scene = db.create_scene(proj.id, "S", content="Hello.")
    view = WritingCoreView(db, proj.id)
    editor = view._editors[scene.id]
    assert editor._style_context is not None
    assert isinstance(editor._style_context, StyleContext)


# -- Style sensitivity levels --------------------------------------------------

def test_sensitivity_levels_defined():
    assert STYLE_SENSITIVITY_LEVELS == ("low", "medium", "high")


def test_detect_hints_low_sensitivity_fewer_hints():
    text = (
        "The dog ran fast and the dog ran far and the dog ran well and "
        "the dog ran home and the dog ran back. "
        "She walked through the incredibly ancient and extraordinarily "
        "weathered door which had been painstakingly and meticulously built "
        "many many decades ago by the remarkably skilled craftsmen."
    )
    low_hints = detect_style_hints(text, sensitivity="low")
    high_hints = detect_style_hints(text, sensitivity="high")
    assert len(low_hints) <= len(high_hints)


def test_detect_hints_high_sensitivity_catches_more():
    text = (
        "He walked to the store. He walked to the park. "
        "He walked to the school. He walked to the car."
    )
    low_hints = detect_style_hints(text, sensitivity="low")
    high_hints = detect_style_hints(text, sensitivity="high")
    assert len(high_hints) >= len(low_hints)


def test_detect_hints_low_long_sentence_threshold():
    words = " ".join(f"word{i}" for i in range(35))
    text = f"{words}."
    low_hints = [h for h in detect_style_hints(text, sensitivity="low") if h.hint_type == "clarity"]
    medium_hints = [h for h in detect_style_hints(text, sensitivity="medium") if h.hint_type == "clarity"]
    assert len(low_hints) == 0
    assert len(medium_hints) >= 1


def test_detect_hints_high_long_sentence_threshold():
    words = " ".join(f"word{i}" for i in range(25))
    text = f"{words}."
    medium_hints = [h for h in detect_style_hints(text, sensitivity="medium") if h.hint_type == "clarity"]
    high_hints = [h for h in detect_style_hints(text, sensitivity="high") if h.hint_type == "clarity"]
    assert len(medium_hints) == 0
    assert len(high_hints) >= 1


def test_detect_hints_max_hints_by_sensitivity():
    long_s1 = " ".join(["alpha"] * 45)
    long_s2 = " ".join(["beta"] * 45)
    long_s3 = " ".join(["gamma"] * 45)
    long_s4 = " ".join(["delta"] * 45)
    long_s5 = " ".join(["epsilon"] * 45)
    long_s6 = " ".join(["zeta"] * 45)
    text = f"{long_s1}. {long_s2}. {long_s3}. {long_s4}. {long_s5}. {long_s6}."
    low_hints = detect_style_hints(text, sensitivity="low")
    medium_hints = detect_style_hints(text, sensitivity="medium")
    high_hints = detect_style_hints(text, sensitivity="high")
    assert len(low_hints) <= 1
    assert len(medium_hints) <= 3
    assert len(high_hints) <= 5


def test_detect_hints_default_sensitivity_is_medium():
    text = " ".join(["word"] * 35) + "."
    default_hints = detect_style_hints(text)
    medium_hints = detect_style_hints(text, sensitivity="medium")
    assert len(default_hints) == len(medium_hints)


def test_detect_hints_repetition_threshold_by_sensitivity():
    text = "cat sat on the mat. cat sat on the mat."
    low_hints = detect_style_hints(text, sensitivity="low")
    high_hints = detect_style_hints(text, sensitivity="high")
    low_reps = [h for h in low_hints if h.hint_type == "repetition"]
    high_reps = [h for h in high_hints if h.hint_type == "repetition"]
    assert len(high_reps) >= len(low_reps)


# -- Style toggle & sensitivity UI integration --------------------------------

def test_toggle_style_feedback_works_instantly():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from logosforge.db import Database
    from logosforge.ui.writing_core_view import WritingCoreView

    db = Database()
    proj = db.create_project("ToggleFB")
    scene = db.create_scene(proj.id, "S", content="Hello world.")
    view = WritingCoreView(db, proj.id)
    editor = view._editors[scene.id]

    assert not view._style_hints_checking
    assert not editor._style_hints_enabled

    view._toggle_style_hints()
    assert view._style_hints_checking
    assert editor._style_hints_enabled

    view._toggle_style_hints()
    assert not view._style_hints_checking
    assert not editor._style_hints_enabled


def test_toggle_off_clears_hints():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from logosforge.db import Database
    from logosforge.ui.writing_core_view import WritingCoreView

    db = Database()
    proj = db.create_project("ToggleClear")
    scene = db.create_scene(proj.id, "S", content="Hello.")
    view = WritingCoreView(db, proj.id)
    editor = view._editors[scene.id]
    editor._style_hints = [StyleHint(0, 5, "clarity", "Test")]
    view._toggle_style_hints()
    view._toggle_style_hints()
    assert editor._style_hints == []


def test_style_sensitivity_persisted():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from logosforge.db import Database
    from logosforge.ui.writing_core_view import WritingCoreView

    db = Database()
    proj = db.create_project("SensPersist")
    scene = db.create_scene(proj.id, "S", content="Hello.")
    view = WritingCoreView(db, proj.id)
    assert view._style_sensitivity == "medium"

    view._set_style_sensitivity("high")
    assert view._style_sensitivity == "high"

    settings = db.get_project_settings(proj.id)
    assert settings["style_sensitivity"] == "high"


def test_style_sensitivity_restored():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from logosforge.db import Database
    from logosforge.ui.writing_core_view import WritingCoreView

    db = Database()
    proj = db.create_project("SensRestore")
    scene = db.create_scene(proj.id, "S", content="Hello.")
    settings = db.get_project_settings(proj.id)
    settings["style_sensitivity"] = "low"
    db.save_project_settings(proj.id, settings)

    view = WritingCoreView(db, proj.id)
    assert view._style_sensitivity == "low"


def test_style_sensitivity_invalid_falls_back_to_medium():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from logosforge.db import Database
    from logosforge.ui.writing_core_view import WritingCoreView

    db = Database()
    proj = db.create_project("SensBad")
    scene = db.create_scene(proj.id, "S", content="Hello.")
    settings = db.get_project_settings(proj.id)
    settings["style_sensitivity"] = "extreme"
    db.save_project_settings(proj.id, settings)

    view = WritingCoreView(db, proj.id)
    assert view._style_sensitivity == "medium"


def test_style_toggle_persisted():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from logosforge.db import Database
    from logosforge.ui.writing_core_view import WritingCoreView

    db = Database()
    proj = db.create_project("TogglePersist")
    scene = db.create_scene(proj.id, "S", content="Hello.")
    view = WritingCoreView(db, proj.id)
    assert not view._style_hints_checking

    view._toggle_style_hints()
    settings = db.get_project_settings(proj.id)
    assert settings["style_hints"] is True


def test_sensitivity_affects_hint_frequency():
    """Core test: same text, different sensitivity → different hint count."""
    long_s1 = " ".join(["word"] * 45)
    long_s2 = " ".join(["word"] * 45)
    long_s3 = " ".join(["word"] * 45)
    long_s4 = " ".join(["word"] * 45)
    text = f"{long_s1}. {long_s2}. {long_s3}. {long_s4}."
    low = detect_style_hints(text, sensitivity="low")
    high = detect_style_hints(text, sensitivity="high")
    assert len(low) < len(high)
