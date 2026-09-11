"""Tests for chat context builder — PSYKE awareness, scene awareness."""

from logosforge.chat_context import build_chat_context, context_summary
from logosforge.db import Database


def _setup_with_world():
    db = Database()
    proj = db.create_project("World", format_mode="novel")
    char = db.create_character(proj.id, "Mara", description="A wandering scholar")
    db.create_psyke_entry(
        proj.id, "Mara", entry_type="character",
        details={"personality": "curious"},
    )
    scene = db.create_scene(
        proj.id, "Opening",
        content="Mara stepped onto the road.",
        character_ids=[char.id],
    )
    return db, proj, char, scene


def test_context_includes_project_title():
    db, proj, _, _ = _setup_with_world()
    ctx = build_chat_context(db, proj.id)
    assert "World" in ctx


def test_context_includes_psyke_entries():
    db, proj, _, _ = _setup_with_world()
    ctx = build_chat_context(db, proj.id)
    assert "Mara" in ctx


def test_context_includes_active_scene():
    db, proj, _, scene = _setup_with_world()
    ctx = build_chat_context(db, proj.id, active_scene_id=scene.id)
    assert "Opening" in ctx or "Mara stepped" in ctx


def test_context_prefers_real_planning_outline_and_preserves_hierarchy():
    db, proj, _, scene = _setup_with_world()
    act = db.create_outline_node(
        proj.id, "Act Two", description="Pressure closes in", sort_order=0,
    )
    db.create_outline_node(
        proj.id,
        "The Observatory",
        description="Mara finds the false chart",
        parent_id=act.id,
        sort_order=0,
        scene_id=scene.id,
    )

    ctx = build_chat_context(db, proj.id)

    assert "[Planned Story Outline — authoritative]" in ctx
    assert "\n- Act Two" in ctx
    assert "\n  - The Observatory" in ctx
    assert "Mara finds the false chart" in ctx
    assert "[linked scene: Opening]" in ctx
    assert "[Drafted Scenes]" in ctx


def test_context_falls_back_to_scene_outline_when_no_plan_exists():
    db, proj, _, _ = _setup_with_world()
    ctx = build_chat_context(db, proj.id)
    assert "[Story Outline]" in ctx


def test_one_broken_context_source_does_not_erase_the_others(monkeypatch):
    import logosforge.chat_context as chat_context

    db, proj, _, _ = _setup_with_world()
    monkeypatch.setattr(
        chat_context,
        "gather_psyke_context",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("broken bible")),
    )

    ctx = build_chat_context(db, proj.id)

    assert "[Project] World" in ctx
    assert "[Story Outline]" in ctx
    assert "[Context Warning] PSYKE context unavailable" in ctx


def test_context_skips_scene_when_none():
    db, proj, _, _ = _setup_with_world()
    ctx = build_chat_context(db, proj.id, active_scene_id=None)
    # Without a scene, scene-specific blocks are omitted
    assert "[Scene Context]" not in ctx


def test_context_can_disable_psyke():
    db, proj, _, _ = _setup_with_world()
    ctx = build_chat_context(db, proj.id, include_psyke=False)
    assert "Mara" not in ctx or "PSYKE" not in ctx


def test_context_truncates_when_too_long():
    db, proj, _, scene = _setup_with_world()
    # Add huge content to force truncation
    long_scene = db.create_scene(
        proj.id, "Long",
        content=("x " * 10000),
    )
    ctx = build_chat_context(db, proj.id, active_scene_id=long_scene.id)
    assert len(ctx) < 7000


def test_long_sources_keep_scene_outline_psyke_and_memory(monkeypatch):
    """Global bounding must trim each source, never erase later sources."""
    import logosforge.chat_context as chat_context

    db = Database()
    proj = db.create_project("Budgeted World")
    monkeypatch.setattr(
        chat_context, "gather_scene_context",
        lambda *_args, **_kwargs: "[Scene Context]\nSCENE_SENTINEL\n" + ("s" * 8000),
    )
    monkeypatch.setattr(
        chat_context, "gather_outline_context",
        lambda *_args, **_kwargs: "[Planned Story Outline]\nOUTLINE_SENTINEL\n" + ("o" * 8000),
    )
    monkeypatch.setattr(
        chat_context, "gather_psyke_context",
        lambda *_args, **_kwargs: "[PSYKE Context]\nPSYKE_SENTINEL\n" + ("p" * 8000),
    )
    monkeypatch.setattr(
        chat_context, "gather_story_memory",
        lambda *_args, **_kwargs: "[Global Story Memory]\nMEMORY_SENTINEL\n" + ("m" * 8000),
    )

    ctx = chat_context.build_chat_context(db, proj.id, active_scene_id=999)

    assert len(ctx) <= chat_context.CONTEXT_MAX_CHARS
    for sentinel in (
        "SCENE_SENTINEL", "OUTLINE_SENTINEL", "PSYKE_SENTINEL", "MEMORY_SENTINEL",
    ):
        assert sentinel in ctx
    assert ctx.count("[...source truncated]") == 4


def test_context_summary_includes_project():
    db, proj, _, _ = _setup_with_world()
    summary = context_summary(db, proj.id)
    assert "World" in summary


def test_context_summary_with_scene():
    db, proj, _, scene = _setup_with_world()
    summary = context_summary(db, proj.id, active_scene_id=scene.id)
    assert "Opening" in summary


def test_context_summary_counts_psyke():
    db, proj, _, _ = _setup_with_world()
    summary = context_summary(db, proj.id)
    assert "PSYKE" in summary or "1" in summary


def test_empty_project_context_summary():
    db = Database()
    proj = db.create_project("Empty")
    summary = context_summary(db, proj.id)
    assert "Empty" in summary
