"""Logos Phase 1 — prompt builder tests.

The prompt builder is an adapter over the existing Assistant context system. It
must produce correct, focused Manuscript and Outline prompts via the shared
``assistant.build_messages`` and ``context_builder`` — without its own context
system, and without leaking secrets.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.logos.actions import get_action
from logosforge.logos.context import build_logos_context
from logosforge.logos.prompt_builder import (
    LOGOS_SYSTEM_PROMPT,
    build_action_prompt,
    build_logos_messages,
)


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path, raising=False)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json", raising=False)
    yield
    settings._instance = None


def _project():
    db = Database()
    pid = db.create_project("Saga", narrative_engine="screenplay").id
    sid = db.create_scene(
        pid, "Opening", act="Act I", chapter="Ch1",
        content="He said nothing. The rain fell.", summary="intro",
    ).id
    return db, pid, sid


def test_manuscript_prompt_includes_selection_and_action():
    db, pid, sid = _project()
    ctx = build_logos_context(
        db, pid, section_name="Manuscript", current_scene_id=sid,
        selected_text="He said nothing.",
    )
    prompt = build_action_prompt(ctx, get_action("rewrite_options"))
    assert "He said nothing." in prompt
    assert "Option" in prompt           # rewrite_options instruction
    assert "screenplay" in prompt       # narrative engine surfaced


def test_manuscript_messages_use_shared_build_messages():
    db, pid, sid = _project()
    ctx = build_logos_context(
        db, pid, section_name="Manuscript", current_scene_id=sid,
        selected_text="He said nothing.",
    )
    msgs = build_logos_messages(db, ctx, get_action("explain_selection"))
    assert [m["role"] for m in msgs] == ["system", "user"]
    assert msgs[0]["content"] == LOGOS_SYSTEM_PROMPT
    assert "He said nothing." in msgs[1]["content"]


def test_outline_prompt_includes_node_and_template():
    db, pid, sid = _project()
    ctx = build_logos_context(
        db, pid, section_name="Outline", current_scene_id=sid,
        outline_node_label="Chapter 1", outline_node_kind="chapter",
        outline_template="save_the_cat",
    )
    prompt = build_action_prompt(ctx, get_action("check_template_fit"))
    assert "Chapter 1" in prompt
    assert "save_the_cat" in prompt


def test_prompt_contains_no_secrets():
    db, pid, sid = _project()
    ctx = build_logos_context(
        db, pid, section_name="Manuscript", current_scene_id=sid,
        selected_text="x",
    )
    msgs = build_logos_messages(db, ctx, get_action("suggest_revision"))
    blob = " ".join(m["content"] for m in msgs).lower()
    assert "api_key" not in blob and "ai_api_key" not in blob


def test_selection_is_capped_in_prompt():
    db, pid, sid = _project()
    ctx = build_logos_context(
        db, pid, section_name="Manuscript", current_scene_id=sid,
        selected_text="z" * 9000,
    )
    prompt = build_action_prompt(ctx, get_action("compress"))
    # Selection is truncated (limit 4000) so prompts stay focused.
    assert prompt.count("z") <= 4000
