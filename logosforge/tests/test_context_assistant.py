"""Tests for the proactive context-aware assistant."""

from logosforge.context_assistant import (
    ContextAssistant,
    ContextHint,
    HintRateLimiter,
)
from logosforge.db import Database
from logosforge.temporal_psyke import TemporalGraph


# -- Helpers -----------------------------------------------------------------

def _make_project(db, fmt="novel"):
    return db.create_project("Test Story", format_mode=fmt)


def _add_scene(db, project_id, title, content="", act="", chapter=""):
    return db.create_scene(
        project_id, title=title, content=content, act=act, chapter=chapter,
    )


# -- Writing mode detection ---------------------------------------------------

class TestWritingModeDetection:
    def test_dialogue_no_tension_detected(self):
        db = Database()
        proj = _make_project(db)
        filler = " ".join(["word"] * 30)
        scene = _add_scene(
            db, proj.id, "Talk",
            content=(
                f"The sun set gently over the quiet meadow. {filler}\n\n"
                f"More scene text here for padding. {filler}\n\n"
                'JOHN\n"Good morning, how are you?"\n\n'
                'MARY\n"I am fine, thank you very much."'
            ),
        )
        ca = ContextAssistant(db, proj.id)
        hints = ca.analyze_scene(scene.id)
        types = [h.hint_type for h in hints]
        assert "dialogue_no_tension" in types

    def test_dialogue_with_tension_not_flagged(self):
        db = Database()
        proj = _make_project(db)
        scene = _add_scene(
            db, proj.id, "Confrontation",
            content=(
                "The air crackled with hostility.\n\n"
                'JOHN\n"You betrayed me."\n\n'
                'MARY\n"I refused to play your game."'
            ),
        )
        ca = ContextAssistant(db, proj.id)
        hints = ca.analyze_scene(scene.id)
        types = [h.hint_type for h in hints]
        assert "dialogue_no_tension" not in types

    def test_short_scene_no_dialogue_hint(self):
        db = Database()
        proj = _make_project(db)
        scene = _add_scene(db, proj.id, "Brief", content="Hello world.")
        ca = ContextAssistant(db, proj.id)
        hints = ca.analyze_scene(scene.id)
        types = [h.hint_type for h in hints]
        assert "dialogue_no_tension" not in types

    def test_rhythm_monotone_detected(self):
        db = Database()
        proj = _make_project(db)
        uniform = "Word " * 20
        content = f"{uniform}\n\n{uniform}\n\n{uniform}\n\n{uniform}"
        scene = _add_scene(db, proj.id, "Flat", content=content)
        ca = ContextAssistant(db, proj.id)
        hints = ca.analyze_scene(scene.id)
        types = [h.hint_type for h in hints]
        assert "rhythm_monotone" in types

    def test_rhythm_varied_not_flagged(self):
        db = Database()
        proj = _make_project(db)
        content = (
            "Short.\n\n"
            + "Medium length paragraph with several words in it.\n\n"
            + ("Long paragraph. " * 20)
        )
        scene = _add_scene(db, proj.id, "Varied", content=content)
        ca = ContextAssistant(db, proj.id)
        hints = ca.analyze_scene(scene.id)
        types = [h.hint_type for h in hints]
        assert "rhythm_monotone" not in types


# -- Structural detection ----------------------------------------------------

class TestStructuralDetection:
    def test_empty_body_with_metadata(self):
        db = Database()
        proj = _make_project(db)
        scene = db.create_scene(
            proj.id, "Planned", content="",
            goal="Introduce villain", conflict="Hero ambushed",
        )
        ca = ContextAssistant(db, proj.id)
        hints = ca.analyze_scene(scene.id)
        types = [h.hint_type for h in hints]
        assert "empty_scene_body" in types

    def test_missing_conflict_detected(self):
        db = Database()
        proj = _make_project(db)
        content = " ".join(["word"] * 50)
        scene = _add_scene(db, proj.id, "Peaceful", content=content)
        ca = ContextAssistant(db, proj.id)
        hints = ca.analyze_scene(scene.id)
        types = [h.hint_type for h in hints]
        assert "missing_conflict" in types

    def test_conflict_present_not_flagged(self):
        db = Database()
        proj = _make_project(db)
        content = " ".join(["word"] * 50)
        scene = db.create_scene(
            proj.id, "Battle", content=content,
            conflict="Enemy attacks",
        )
        ca = ContextAssistant(db, proj.id)
        hints = ca.analyze_scene(scene.id)
        types = [h.hint_type for h in hints]
        assert "missing_conflict" not in types

    def test_missing_conflict_with_text_signal_not_flagged(self):
        db = Database()
        proj = _make_project(db)
        content = "He fought against the rising tide. " + " ".join(["word"] * 50)
        scene = _add_scene(db, proj.id, "Fight", content=content)
        ca = ContextAssistant(db, proj.id)
        hints = ca.analyze_scene(scene.id)
        types = [h.hint_type for h in hints]
        assert "missing_conflict" not in types

    def test_long_scene_detected(self):
        db = Database()
        proj = _make_project(db)
        content = " ".join(["word"] * 400)
        scene = _add_scene(db, proj.id, "Epic", content=content)
        ca = ContextAssistant(db, proj.id)
        hints = ca.analyze_scene(scene.id)
        types = [h.hint_type for h in hints]
        assert "long_scene" in types

    def test_short_scene_detected(self):
        db = Database()
        proj = _make_project(db)
        scene = _add_scene(db, proj.id, "Stub", content="A few words here.")
        ca = ContextAssistant(db, proj.id)
        hints = ca.analyze_scene(scene.id)
        types = [h.hint_type for h in hints]
        assert "short_scene" in types

    def test_normal_length_not_flagged(self):
        db = Database()
        proj = _make_project(db)
        content = " ".join(["word"] * 100)
        scene = _add_scene(db, proj.id, "Normal", content=content)
        ca = ContextAssistant(db, proj.id)
        hints = ca.analyze_scene(scene.id)
        types = [h.hint_type for h in hints]
        assert "long_scene" not in types
        assert "short_scene" not in types

    def test_missing_conflict_action_is_focus(self):
        db = Database()
        proj = _make_project(db)
        content = " ".join(["word"] * 50)
        scene = _add_scene(db, proj.id, "Calm", content=content)
        ca = ContextAssistant(db, proj.id)
        hints = ca.analyze_scene(scene.id)
        conflict_hints = [h for h in hints if h.hint_type == "missing_conflict"]
        assert conflict_hints
        assert conflict_hints[0].action == "focus_conflict"


# -- PSYKE temporal detection -------------------------------------------------

class TestPsykeTemporalDetection:
    def test_stale_progression_detected(self):
        db = Database()
        proj = _make_project(db)

        entry = db.create_psyke_entry(proj.id, name="Alice", entry_type="character")

        for i in range(8):
            _add_scene(db, proj.id, f"Scene {i}", content="Alice walked. Word " * 10)

        scenes = db.get_all_scenes(proj.id)
        db.create_psyke_progression(entry.id, "Alice is hopeful", scene_id=scenes[0].id)

        last_scene = scenes[-1]
        tg = TemporalGraph(db, proj.id)
        ca = ContextAssistant(db, proj.id)
        hints = ca.analyze_scene(last_scene.id, temporal_graph=tg)
        types = [h.hint_type for h in hints]
        assert "character_state_stale" in types

    def test_recent_progression_not_flagged(self):
        db = Database()
        proj = _make_project(db)

        entry = db.create_psyke_entry(proj.id, name="Bob", entry_type="character")

        for i in range(4):
            _add_scene(db, proj.id, f"Scene {i}", content="Bob walked. Word " * 10)

        scenes = db.get_all_scenes(proj.id)
        db.create_psyke_progression(entry.id, "Bob is determined", scene_id=scenes[2].id)

        tg = TemporalGraph(db, proj.id)
        ca = ContextAssistant(db, proj.id)
        hints = ca.analyze_scene(scenes[3].id, temporal_graph=tg)
        types = [h.hint_type for h in hints]
        assert "character_state_stale" not in types

    def test_stale_progression_action_is_open(self):
        db = Database()
        proj = _make_project(db)

        entry = db.create_psyke_entry(proj.id, name="Carol", entry_type="character")

        for i in range(8):
            _add_scene(db, proj.id, f"Scene {i}", content="Carol spoke. Word " * 10)

        scenes = db.get_all_scenes(proj.id)
        db.create_psyke_progression(entry.id, "Carol is lost", scene_id=scenes[0].id)

        last_scene = scenes[-1]
        tg = TemporalGraph(db, proj.id)
        ca = ContextAssistant(db, proj.id)
        hints = ca.analyze_scene(last_scene.id, temporal_graph=tg)
        stale_hints = [h for h in hints if h.hint_type == "character_state_stale"]
        assert stale_hints
        assert stale_hints[0].action == "open_progression"
        assert stale_hints[0].data["entry_id"] == entry.id

    def test_character_not_mentioned_not_flagged(self):
        db = Database()
        proj = _make_project(db)

        db.create_psyke_entry(proj.id, name="Zara", entry_type="character")

        for i in range(8):
            _add_scene(db, proj.id, f"Scene {i}", content="The wind blew. " * 10)

        last_scene = db.get_all_scenes(proj.id)[-1]
        tg = TemporalGraph(db, proj.id)
        ca = ContextAssistant(db, proj.id)
        hints = ca.analyze_scene(last_scene.id, temporal_graph=tg)
        types = [h.hint_type for h in hints]
        assert "character_state_stale" not in types

    def test_no_temporal_graph_skips_psyke(self):
        db = Database()
        proj = _make_project(db)
        scene = _add_scene(db, proj.id, "Alone", content="Word " * 50)
        ca = ContextAssistant(db, proj.id)
        hints = ca.analyze_scene(scene.id, temporal_graph=None)
        psyke_types = {"character_state_stale", "related_entries_absent"}
        assert not any(h.hint_type in psyke_types for h in hints)


# -- Empty / missing scene ---------------------------------------------------

class TestEdgeCases:
    def test_nonexistent_scene(self):
        db = Database()
        proj = _make_project(db)
        ca = ContextAssistant(db, proj.id)
        hints = ca.analyze_scene(99999)
        assert hints == []

    def test_empty_scene_no_crash(self):
        db = Database()
        proj = _make_project(db)
        scene = _add_scene(db, proj.id, "Empty", content="")
        ca = ContextAssistant(db, proj.id)
        hints = ca.analyze_scene(scene.id)
        assert isinstance(hints, list)

    def test_hints_sorted_by_priority(self):
        db = Database()
        proj = _make_project(db)
        scene = _add_scene(db, proj.id, "Short", content="Three words only.")
        ca = ContextAssistant(db, proj.id)
        hints = ca.analyze_scene(scene.id)
        for i in range(len(hints) - 1):
            assert hints[i].priority <= hints[i + 1].priority


# -- Rate limiter -------------------------------------------------------------

class TestHintRateLimiter:
    def test_first_hint_passes(self):
        rl = HintRateLimiter()
        hint = ContextHint(
            hint_type="test", message="Hello", priority=1,
            scene_id=1, data={"_dedup": "a"},
        )
        result = rl.filter([hint])
        assert result is hint

    def test_global_cooldown_blocks(self):
        rl = HintRateLimiter()
        h1 = ContextHint(hint_type="a", message="X", priority=1, scene_id=1, data={"_dedup": "x"})
        h2 = ContextHint(hint_type="b", message="Y", priority=1, scene_id=1, data={"_dedup": "y"})
        rl.filter([h1])
        rl.mark_shown(h1)
        result = rl.filter([h2])
        assert result is None

    def test_type_cooldown_blocks_same_type(self):
        rl = HintRateLimiter()
        h1 = ContextHint(hint_type="a", message="X", priority=1, scene_id=1, data={"_dedup": "x"})
        rl.mark_shown(h1)
        rl._last_shown = 0.0  # bypass global cooldown
        result = rl.filter([h1])
        assert result is None

    def test_different_type_passes_after_global_cooldown(self):
        rl = HintRateLimiter()
        h1 = ContextHint(hint_type="a", message="X", priority=1, scene_id=1, data={"_dedup": "x"})
        h2 = ContextHint(hint_type="b", message="Y", priority=1, scene_id=1, data={"_dedup": "y"})
        rl.mark_shown(h1)
        rl._last_shown = 0.0  # bypass global cooldown
        result = rl.filter([h2])
        assert result is h2

    def test_dedup_blocks_seen_key(self):
        rl = HintRateLimiter()
        hint = ContextHint(hint_type="a", message="X", priority=1, scene_id=1, data={"_dedup": "x"})
        rl.mark_shown(hint)
        rl._last_shown = 0.0
        rl._type_shown.clear()
        result = rl.filter([hint])
        assert result is None

    def test_scene_change_resets(self):
        rl = HintRateLimiter()
        hint = ContextHint(hint_type="a", message="X", priority=1, scene_id=1, data={"_dedup": "x"})
        rl.mark_shown(hint)
        rl.on_scene_changed(1)
        result = rl.filter([hint])
        assert result is hint

    def test_reset_clears_all(self):
        rl = HintRateLimiter()
        hint = ContextHint(hint_type="a", message="X", priority=1, scene_id=1, data={"_dedup": "x"})
        rl.mark_shown(hint)
        rl.reset()
        result = rl.filter([hint])
        assert result is hint

    def test_empty_list_returns_none(self):
        rl = HintRateLimiter()
        result = rl.filter([])
        assert result is None

    def test_priority_ordering_respected(self):
        rl = HintRateLimiter()
        low = ContextHint(hint_type="low", message="L", priority=3, scene_id=1, data={"_dedup": "l"})
        high = ContextHint(hint_type="high", message="H", priority=1, scene_id=1, data={"_dedup": "h"})
        result = rl.filter([high, low])
        assert result is high


# -- ContextHint dataclass ----------------------------------------------------

class TestContextHint:
    def test_dedup_key_format(self):
        hint = ContextHint(
            hint_type="test", message="msg", priority=1,
            scene_id=42, data={"_dedup": "foo"},
        )
        assert hint.dedup_key == "test:42:foo"

    def test_dedup_key_missing_data(self):
        hint = ContextHint(
            hint_type="test", message="msg", priority=1,
            scene_id=1,
        )
        assert hint.dedup_key == "test:1:"

    def test_frozen(self):
        hint = ContextHint(hint_type="a", message="b", priority=1, scene_id=1)
        try:
            hint.hint_type = "c"  # type: ignore[misc]
            assert False, "Should be frozen"
        except AttributeError:
            pass
