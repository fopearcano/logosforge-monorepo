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
