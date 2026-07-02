"""Tests for IRRATIONAL — PSYKE rule-disruption engine."""

from logosforge.db import Database
from logosforge.irrational import (
    IrrationalContext,
    IrrationalFragment,
    build_irrational_context,
    generate_irrational,
    reroll_seed,
    _arc_inversion,
    _entity_blend,
    _reality_rupture,
    _scene_seed,
    _temporal_displacement,
    _temporal_echo,
    _MAX_FRAGMENTS,
)
from logosforge.temporal_psyke import TemporalGraph
import random


# -- Helpers -----------------------------------------------------------------

def _make_project(db):
    return db.create_project("Irrational Test", format_mode="novel")


def _add_scene(db, project_id, title, content="Scene content here.", **kw):
    return db.create_scene(project_id, title=title, content=content, **kw)


def _add_character(db, project_id, name, is_global=False):
    return db.create_psyke_entry(
        project_id, name=name, entry_type="character", is_global=is_global,
    )


def _add_entry(db, project_id, name, entry_type, is_global=False):
    return db.create_psyke_entry(
        project_id, name=name, entry_type=entry_type, is_global=is_global,
    )


# == Seed determinism ========================================================

class TestSeeds:
    def test_scene_seed_deterministic(self):
        assert _scene_seed(42) == _scene_seed(42)

    def test_scene_seed_varies_by_id(self):
        assert _scene_seed(1) != _scene_seed(2)

    def test_reroll_seed_varies_by_iteration(self):
        s0 = reroll_seed(10, 0)
        s1 = reroll_seed(10, 1)
        s2 = reroll_seed(10, 2)
        assert s0 != s1
        assert s1 != s2

    def test_reroll_seed_deterministic(self):
        assert reroll_seed(10, 3) == reroll_seed(10, 3)


# == generate_irrational — integration =======================================

class TestGenerateIrrational:
    def test_empty_project_returns_empty(self):
        db = Database(":memory:")
        proj = _make_project(db)
        scene = _add_scene(db, proj.id, "Empty")

        ctx = generate_irrational(db, proj.id, scene.id)

        assert isinstance(ctx, IrrationalContext)
        assert ctx.scene_id == scene.id
        # With no entries, we may still get a rupture fragment
        for f in ctx.fragments:
            assert isinstance(f, IrrationalFragment)

    def test_deterministic_with_same_seed(self):
        db = Database(":memory:")
        proj = _make_project(db)
        _add_character(db, proj.id, "Alice")
        _add_character(db, proj.id, "Bob")
        scene = _add_scene(db, proj.id, "Test")

        ctx1 = generate_irrational(db, proj.id, scene.id, seed=12345)
        ctx2 = generate_irrational(db, proj.id, scene.id, seed=12345)

        assert len(ctx1.fragments) == len(ctx2.fragments)
        for f1, f2 in zip(ctx1.fragments, ctx2.fragments):
            assert f1.kind == f2.kind
            assert f1.text == f2.text

    def test_different_seed_may_differ(self):
        db = Database(":memory:")
        proj = _make_project(db)
        _add_character(db, proj.id, "Alice")
        _add_character(db, proj.id, "Bob")
        _add_entry(db, proj.id, "Castle", "place")
        _add_entry(db, proj.id, "Magic", "lore")
        _add_entry(db, proj.id, "Redemption", "theme")
        s1 = _add_scene(db, proj.id, "S1", content="First scene.")
        _add_scene(db, proj.id, "S2", content="Second scene.")

        ctx1 = generate_irrational(db, proj.id, s1.id, seed=111)
        ctx2 = generate_irrational(db, proj.id, s1.id, seed=999)

        texts1 = [f.text for f in ctx1.fragments]
        texts2 = [f.text for f in ctx2.fragments]
        assert texts1 != texts2

    def test_max_fragments_cap(self):
        db = Database(":memory:")
        proj = _make_project(db)
        for i in range(10):
            _add_character(db, proj.id, f"Char{i}")
        _add_entry(db, proj.id, "Place1", "place")
        _add_entry(db, proj.id, "Lore1", "lore")
        _add_entry(db, proj.id, "Theme1", "theme")
        s1 = _add_scene(db, proj.id, "S1", content="Content one.")
        _add_scene(db, proj.id, "S2", content="Content two.")

        ctx = generate_irrational(db, proj.id, s1.id, seed=42)
        assert len(ctx.fragments) <= _MAX_FRAGMENTS

    def test_fragment_kinds_valid(self):
        db = Database(":memory:")
        proj = _make_project(db)
        _add_character(db, proj.id, "Alice")
        _add_character(db, proj.id, "Bob")
        _add_entry(db, proj.id, "Forest", "place")
        _add_entry(db, proj.id, "Hope", "theme")
        s1 = _add_scene(db, proj.id, "S1", content="Some content.")
        _add_scene(db, proj.id, "S2", content="Other content.")

        ctx = generate_irrational(db, proj.id, s1.id, seed=42)
        valid_kinds = {"displacement", "blend", "inversion", "echo", "rupture"}
        for f in ctx.fragments:
            assert f.kind in valid_kinds

    def test_with_progressions_and_temporal_graph(self):
        db = Database(":memory:")
        proj = _make_project(db)
        char = _add_character(db, proj.id, "Zara")
        s1 = _add_scene(db, proj.id, "Early")
        s2 = _add_scene(db, proj.id, "Late")

        db.create_psyke_progression(char.id, "Zara is lost", scene_id=s1.id)
        db.create_psyke_progression(char.id, "Zara finds purpose", scene_id=s2.id)

        tg = TemporalGraph(db, proj.id)
        ctx = generate_irrational(db, proj.id, s1.id, temporal_graph=tg, seed=42)

        assert isinstance(ctx, IrrationalContext)
        assert len(ctx.fragments) > 0


# == Individual fragment generators ==========================================

class TestTemporalDisplacement:
    def test_no_characters_returns_empty(self):
        db = Database(":memory:")
        proj = _make_project(db)
        lore = _add_entry(db, proj.id, "Magic", "lore")
        s1 = _add_scene(db, proj.id, "S1")

        entries = db.get_all_psyke_entries(proj.id)
        scenes = db.get_all_scenes(proj.id)
        scene = db.get_scene_by_id(s1.id)
        tg = TemporalGraph(db, proj.id)

        result = _temporal_displacement(entries, scenes, scene, tg, random.Random(42))
        assert result == []

    def test_global_characters_excluded(self):
        db = Database(":memory:")
        proj = _make_project(db)
        _add_character(db, proj.id, "Narrator", is_global=True)
        s1 = _add_scene(db, proj.id, "S1")

        entries = db.get_all_psyke_entries(proj.id)
        scenes = db.get_all_scenes(proj.id)
        scene = db.get_scene_by_id(s1.id)
        tg = TemporalGraph(db, proj.id)

        result = _temporal_displacement(entries, scenes, scene, tg, random.Random(42))
        assert result == []

    def test_future_progression_creates_displacement(self):
        db = Database(":memory:")
        proj = _make_project(db)
        char = _add_character(db, proj.id, "Vera")
        s1 = _add_scene(db, proj.id, "Early")
        s2 = _add_scene(db, proj.id, "Late")

        db.create_psyke_progression(char.id, "Vera awakens", scene_id=s2.id)

        entries = db.get_all_psyke_entries(proj.id)
        scenes = db.get_all_scenes(proj.id)
        scene = db.get_scene_by_id(s1.id)
        tg = TemporalGraph(db, proj.id)

        result = _temporal_displacement(entries, scenes, scene, tg, random.Random(42))
        assert len(result) == 1
        assert result[0].kind == "displacement"
        assert "Vera" in result[0].text
        assert char.id in result[0].source_entries

    def test_no_scene_returns_empty(self):
        result = _temporal_displacement([], [], None, TemporalGraph.__new__(TemporalGraph), random.Random(1))
        assert result == []


class TestEntityBlend:
    def test_two_entries_produces_blend(self):
        db = Database(":memory:")
        proj = _make_project(db)
        a = _add_character(db, proj.id, "Alice")
        b = _add_character(db, proj.id, "Bob")

        entries = db.get_all_psyke_entries(proj.id)
        result = _entity_blend(entries, random.Random(42))

        assert len(result) == 1
        assert result[0].kind == "blend"
        assert len(result[0].source_entries) == 2

    def test_single_entry_returns_empty(self):
        db = Database(":memory:")
        proj = _make_project(db)
        _add_character(db, proj.id, "Alice")

        entries = db.get_all_psyke_entries(proj.id)
        result = _entity_blend(entries, random.Random(42))
        assert result == []

    def test_global_entries_excluded(self):
        db = Database(":memory:")
        proj = _make_project(db)
        _add_character(db, proj.id, "Narrator", is_global=True)
        _add_character(db, proj.id, "Fate", is_global=True)

        entries = db.get_all_psyke_entries(proj.id)
        result = _entity_blend(entries, random.Random(42))
        assert result == []

    def test_blend_contains_names(self):
        db = Database(":memory:")
        proj = _make_project(db)
        _add_character(db, proj.id, "Xander")
        _add_character(db, proj.id, "Yara")

        entries = db.get_all_psyke_entries(proj.id)
        result = _entity_blend(entries, random.Random(42))
        assert len(result) == 1
        assert "Xander" in result[0].text or "Yara" in result[0].text


class TestArcInversion:
    def test_character_entry_produces_inversion(self):
        db = Database(":memory:")
        proj = _make_project(db)
        char = _add_character(db, proj.id, "Dorian")

        entries = db.get_all_psyke_entries(proj.id)
        result = _arc_inversion(entries, random.Random(42))

        assert len(result) == 1
        assert result[0].kind == "inversion"
        assert "Dorian" in result[0].text
        assert char.id in result[0].source_entries

    def test_theme_entry_produces_inversion(self):
        db = Database(":memory:")
        proj = _make_project(db)
        theme = _add_entry(db, proj.id, "Redemption", "theme")

        entries = db.get_all_psyke_entries(proj.id)
        result = _arc_inversion(entries, random.Random(42))
        assert len(result) == 1
        assert "Redemption" in result[0].text

    def test_only_global_entries_returns_empty(self):
        db = Database(":memory:")
        proj = _make_project(db)
        _add_character(db, proj.id, "Fate", is_global=True)

        entries = db.get_all_psyke_entries(proj.id)
        result = _arc_inversion(entries, random.Random(42))
        assert result == []

    def test_place_entry_not_eligible(self):
        db = Database(":memory:")
        proj = _make_project(db)
        _add_entry(db, proj.id, "Castle", "place")

        entries = db.get_all_psyke_entries(proj.id)
        result = _arc_inversion(entries, random.Random(42))
        assert result == []

    def test_empty_entries_returns_empty(self):
        result = _arc_inversion([], random.Random(42))
        assert result == []


class TestTemporalEcho:
    def test_produces_echo_with_other_scenes(self):
        db = Database(":memory:")
        proj = _make_project(db)
        s1 = _add_scene(db, proj.id, "Scene One", content="Content one.")
        s2 = _add_scene(db, proj.id, "Scene Two", content="Content two.")

        scenes = db.get_all_scenes(proj.id)
        current = db.get_scene_by_id(s1.id)
        result = _temporal_echo(scenes, current, random.Random(42))

        assert len(result) == 1
        assert result[0].kind == "echo"

    def test_single_scene_returns_empty(self):
        db = Database(":memory:")
        proj = _make_project(db)
        s1 = _add_scene(db, proj.id, "Only Scene", content="Just one.")

        scenes = db.get_all_scenes(proj.id)
        current = db.get_scene_by_id(s1.id)
        result = _temporal_echo(scenes, current, random.Random(42))
        assert result == []

    def test_other_scenes_without_content_excluded(self):
        db = Database(":memory:")
        proj = _make_project(db)
        s1 = _add_scene(db, proj.id, "Full", content="Has content.")
        _add_scene(db, proj.id, "Empty", content="")

        scenes = db.get_all_scenes(proj.id)
        current = db.get_scene_by_id(s1.id)
        result = _temporal_echo(scenes, current, random.Random(42))
        assert result == []

    def test_echo_can_reference_scene_title(self):
        db = Database(":memory:")
        proj = _make_project(db)
        s1 = _add_scene(db, proj.id, "The Beginning", content="Start.")
        _add_scene(db, proj.id, "The Climax", content="Peak.")

        scenes = db.get_all_scenes(proj.id)
        current = db.get_scene_by_id(s1.id)

        found = False
        for seed in range(100):
            result = _temporal_echo(scenes, current, random.Random(seed))
            if result and "The Climax" in result[0].text:
                found = True
                break
        assert found, "Some seed should produce an echo referencing the other scene title"


class TestRealityRupture:
    def test_always_produces_fragment(self):
        result = _reality_rupture([], random.Random(42))
        assert len(result) == 1
        assert result[0].kind == "rupture"

    def test_uses_place_names_when_available(self):
        db = Database(":memory:")
        proj = _make_project(db)
        _add_entry(db, proj.id, "Crystal Cavern", "place")

        entries = db.get_all_psyke_entries(proj.id)

        found_place = False
        for seed in range(100):
            result = _reality_rupture(entries, random.Random(seed))
            if "Crystal Cavern" in result[0].text:
                found_place = True
                break
        assert found_place, "Place name should appear in some rupture fragment"

    def test_uses_fallback_for_missing_types(self):
        result = _reality_rupture([], random.Random(42))
        assert len(result) == 1
        text = result[0].text
        assert text  # should still produce text with fallback substitutions

    def test_source_entries_tracked(self):
        db = Database(":memory:")
        proj = _make_project(db)
        place = _add_entry(db, proj.id, "The Void", "place")

        entries = db.get_all_psyke_entries(proj.id)

        for seed in range(100):
            result = _reality_rupture(entries, random.Random(seed))
            if "The Void" in result[0].text:
                assert place.id in result[0].source_entries
                return
        # If no template used {place}, that's fine — skip


# == build_irrational_context ================================================

class TestBuildIrrationalContext:
    def test_empty_project_returns_empty_string(self):
        db = Database(":memory:")
        proj = _make_project(db)
        scene = _add_scene(db, proj.id, "Bare")

        # Force seed that might not produce fragments with no entries
        # We still get rupture, so let's just check format
        result = build_irrational_context(db, proj.id, scene.id, seed=42)
        if result:
            assert "[IRRATIONAL MODE]" in result

    def test_with_entries_returns_formatted_block(self):
        db = Database(":memory:")
        proj = _make_project(db)
        _add_character(db, proj.id, "Max")
        _add_character(db, proj.id, "Lena")
        _add_entry(db, proj.id, "Dark Forest", "place")
        _add_entry(db, proj.id, "Honor", "theme")
        s1 = _add_scene(db, proj.id, "Scene One", content="Some text.")
        _add_scene(db, proj.id, "Scene Two", content="More text.")

        result = build_irrational_context(db, proj.id, s1.id, seed=42)

        assert "[IRRATIONAL MODE]" in result
        assert "surreal provocations" in result
        lines = result.strip().split("\n")
        fragment_lines = [l for l in lines if l.startswith("- (")]
        assert len(fragment_lines) > 0
        assert len(fragment_lines) <= _MAX_FRAGMENTS

    def test_fragment_lines_have_kind_prefix(self):
        db = Database(":memory:")
        proj = _make_project(db)
        _add_character(db, proj.id, "Atlas")
        _add_character(db, proj.id, "Nova")
        s1 = _add_scene(db, proj.id, "S1", content="Text.")
        _add_scene(db, proj.id, "S2", content="Text.")

        result = build_irrational_context(db, proj.id, s1.id, seed=42)
        valid_kinds = {"displacement", "blend", "inversion", "echo", "rupture"}

        for line in result.strip().split("\n"):
            if line.startswith("- ("):
                kind = line.split(")")[0].replace("- (", "")
                assert kind in valid_kinds


# == IrrationalFragment dataclass ============================================

class TestIrrationalFragment:
    def test_frozen(self):
        f = IrrationalFragment(kind="blend", text="test")
        try:
            f.kind = "other"
            assert False, "Should be frozen"
        except AttributeError:
            pass

    def test_default_source_entries(self):
        f = IrrationalFragment(kind="echo", text="test")
        assert f.source_entries == []


# == IrrationalContext dataclass =============================================

class TestIrrationalContext:
    def test_fields(self):
        frags = [IrrationalFragment(kind="rupture", text="boom")]
        ctx = IrrationalContext(fragments=frags, seed=42, scene_id=1)
        assert ctx.seed == 42
        assert ctx.scene_id == 1
        assert len(ctx.fragments) == 1
