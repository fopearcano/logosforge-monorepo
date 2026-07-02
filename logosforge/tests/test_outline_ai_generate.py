"""Tests for AI generation buttons in the Outline section."""

import pytest

from logosforge.db import Database
from logosforge.outline_actions import build_outline_generation_prompt


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    yield
    settings._instance = None


def _view(db, project_id):
    from logosforge.ui.outline_view import OutlineView
    return OutlineView(db, project_id)


# =========================================================================
# 1. Prompt builder — scope / engine / template / PSYKE
# =========================================================================

def test_prompt_full_scope():
    p = build_outline_generation_prompt("full", engine="novel")
    assert "complete story outline" in p.lower()
    # Engine-derived vocabulary (Novel: Part/Chapter/Scene).
    assert "Part" in p and "Chapter" in p and "Scene" in p


def test_prompt_scope_variants():
    # Default engine is novel -> tiers are Part / Chapter / Scene.
    assert "ONE Part" in build_outline_generation_prompt("act")
    assert "ONE Chapter" in build_outline_generation_prompt("chapter")
    assert "Scene" in build_outline_generation_prompt("scene")


def test_prompt_engine_specific_vocabulary():
    assert "Sequence" in build_outline_generation_prompt("full", engine="screenplay")
    assert "Episode" in build_outline_generation_prompt("full", engine="series")
    assert "Page" in build_outline_generation_prompt("full", engine="graphic_novel")


def test_prompt_includes_template_and_psyke():
    p = build_outline_generation_prompt(
        "full", template_name="Save the Cat",
        template_beats=["Opening Image", "Theme Stated"],
        psyke_context="[PSYKE] Hero: a weary detective",
    )
    assert "Save the Cat" in p
    assert "Opening Image" in p
    assert "weary detective" in p


def test_prompt_includes_target_title():
    p = build_outline_generation_prompt("act", target_title="Act 2")
    assert "Act 2" in p


# =========================================================================
# 2. Buttons present + engine-aware
# =========================================================================

def test_ai_buttons_present():
    db = Database()
    p = db.create_project("Novel")
    view = _view(db, p.id)
    assert hasattr(view, "_ai_outline_btn")
    assert hasattr(view, "_ai_node_btn")
    assert "AI Generate Outline" in view._ai_outline_btn.text()


def test_engine_detected():
    db = Database()
    p = db.create_project("Screenplay", narrative_engine="screenplay",
                          default_writing_format="screenplay")
    view = _view(db, p.id)
    assert view._engine == "screenplay"


# =========================================================================
# 3. Contextual button relabels by selection depth
# =========================================================================

def test_contextual_button_disabled_without_selection():
    db = Database()
    p = db.create_project("Novel")
    view = _view(db, p.id)
    assert view._ai_node_btn.isEnabled() is False


def test_contextual_button_labels_act_and_chapter():
    db = Database()
    p = db.create_project("Novel")
    act = db.create_outline_node(p.id, "Act 1", parent_id=None)
    ch = db.create_outline_node(p.id, "Chapter 1", parent_id=act.id)
    view = _view(db, p.id)
    view._load_outline()
    view._select_node(act.id)
    # Novel engine units: Part / Chapter / Scene.
    assert view._ai_node_btn.text() == "✨ AI Generate Part"
    assert view._ai_node_btn.isEnabled() is True
    view._select_node(ch.id)
    assert view._ai_node_btn.text() == "✨ AI Generate Chapter"


def test_contextual_button_scene_level_for_deep_node():
    db = Database()
    p = db.create_project("Novel")
    act = db.create_outline_node(p.id, "Act 1", parent_id=None)
    ch = db.create_outline_node(p.id, "Chapter 1", parent_id=act.id)
    sc = db.create_outline_node(p.id, "Scene 1", parent_id=ch.id)
    view = _view(db, p.id)
    view._load_outline()
    view._select_node(sc.id)
    # Deepest novel unit is Scene.
    assert view._ai_node_btn.text() == "✨ AI Generate Scene"


# =========================================================================
# 4. build_generation_prompt on the view uses engine + template + PSYKE
# =========================================================================

def test_view_prompt_uses_engine_and_template():
    db = Database()
    p = db.create_project("Screenplay", narrative_engine="screenplay",
                          default_writing_format="screenplay")
    db.create_psyke_entry(p.id, "Cooper", entry_type="character",
                          notes="a detective")
    view = _view(db, p.id)
    # Select the first real template (index 0 is the placeholder).
    view._template_combo.setCurrentIndex(1)
    prompt = view.build_generation_prompt("full", None)
    assert "Sequence" in prompt           # screenplay engine guide
    assert len(prompt) > 50


def test_view_prompt_target_title_for_node():
    db = Database()
    p = db.create_project("Novel")
    act = db.create_outline_node(p.id, "Act 1", parent_id=None)
    view = _view(db, p.id)
    prompt = view.build_generation_prompt("act", act.id)
    assert "Act 1" in prompt


# =========================================================================
# 5. Apply generated outline — additive, confirmed, events
# =========================================================================

def test_apply_generated_outline_additive():
    db = Database()
    p = db.create_project("Novel")
    db.create_outline_node(p.id, "Existing", parent_id=None)
    view = _view(db, p.id)
    created = view.apply_generated_outline(
        "# Act 1\n## Chapter 1\n- Scene: opening", "full", None, confirm=False,
    )
    assert len(created) == 3
    roots = db.get_outline_children(p.id, None)
    assert [n.title for n in roots] == ["Existing", "Act 1"]


def test_apply_generated_outline_under_parent():
    db = Database()
    p = db.create_project("Novel")
    act = db.create_outline_node(p.id, "Act 1", parent_id=None)
    view = _view(db, p.id)
    view.apply_generated_outline("## Chapter 1\n## Chapter 2", "act", act.id,
                                 confirm=False)
    assert [c.title for c in db.get_outline_children(p.id, act.id)] == [
        "Chapter 1", "Chapter 2",
    ]


def test_apply_emits_events_and_refreshes():
    from logosforge.project_events import get_event_bus
    db = Database()
    p = db.create_project("Novel")
    seen = {"o": 0, "d": 0}
    bus = get_event_bus()
    bus.outline_changed.connect(lambda: seen.__setitem__("o", seen["o"] + 1))
    bus.project_data_changed.connect(lambda: seen.__setitem__("d", seen["d"] + 1))
    fired = []
    from logosforge.ui.outline_view import OutlineView
    view = OutlineView(db, p.id, on_data_changed=lambda: fired.append(1))
    view.apply_generated_outline("# Act 1\n## Chapter 1", "full", None,
                                 confirm=False)
    assert seen["o"] >= 1
    assert seen["d"] >= 1
    assert fired
    # Tree refreshed to show the new nodes.
    assert view._tree.topLevelItemCount() == 1


def test_apply_empty_text_is_noop():
    db = Database()
    p = db.create_project("Novel")
    view = _view(db, p.id)
    assert view.apply_generated_outline("", "full", None, confirm=False) == []
    assert db.get_outline_nodes(p.id) == []


# =========================================================================
# 6. Generation gating — no provider configured
# =========================================================================

def test_generate_without_provider_returns_false():
    from logosforge.settings import get_manager
    db = Database()
    p = db.create_project("Novel")
    view = _view(db, p.id)
    # Explicitly clear the provider (default settings ship "LM Studio").
    mgr = get_manager()
    mgr.set("ai_provider", "")
    mgr.set("ai_base_url", "")
    assert view._ai_generate("full") is False
    assert view._gen_worker is None


def test_generate_busy_returns_false():
    db = Database()
    p = db.create_project("Novel")
    view = _view(db, p.id)
    # Simulate an in-flight worker — a second request must be rejected.
    view._gen_worker = object()
    try:
        assert view._ai_generate("full") is False
    finally:
        view._gen_worker = None
