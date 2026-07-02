"""Tests for PSYKE Outline Templates plugin integration with Outline Mode."""

import pytest

from logosforge.db import Database
from logosforge.outline_templates import (
    OutlineTemplate,
    TemplateBeat,
    all_templates,
    get_template,
    list_templates,
    register_outline_template,
    unregister_outline_template,
)


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    yield
    settings._instance = None


@pytest.fixture
def _plugin_template():
    register_outline_template(
        "kishotenketsu",
        OutlineTemplate(
            name="Kishōtenketsu", description="4-act East Asian structure",
            beats=[TemplateBeat("Ki"), TemplateBeat("Sho"),
                   TemplateBeat("Ten"), TemplateBeat("Ketsu")],
        ),
    )
    yield "kishotenketsu"
    unregister_outline_template("kishotenketsu")


# =========================================================================
# 1. Catalog — built-ins + plugin registration
# =========================================================================

def test_builtin_templates_listed():
    keys = {k for k, _, _ in list_templates()}
    for k in ("save_the_cat", "heros_journey", "three_act", "story_circle",
              "five_act"):
        assert k in keys


def test_register_plugin_template(_plugin_template):
    keys = {k for k, _, _ in list_templates()}
    assert "kishotenketsu" in keys
    assert get_template("kishotenketsu").name == "Kishōtenketsu"
    assert "kishotenketsu" in all_templates()


def test_register_does_not_overwrite_builtin():
    register_outline_template(
        "save_the_cat", OutlineTemplate(name="HACK", description=""),
    )
    assert get_template("save_the_cat").name == "Save the Cat"


def test_unregister_plugin_template():
    register_outline_template("temp_x", OutlineTemplate(name="X", description=""))
    assert get_template("temp_x") is not None
    unregister_outline_template("temp_x")
    assert get_template("temp_x") is None


def test_no_hardcoded_unavailable_templates():
    # list_templates reflects exactly the available catalog (built-ins only
    # when nothing registered) — never an unavailable hardcoded subset.
    keys = {k for k, _, _ in list_templates()}
    assert keys == set(all_templates().keys())


# =========================================================================
# 2. Assistant Outline-Mode template selector
# =========================================================================

def _panel(db, project_id):
    from logosforge.ui.assistant_view import AssistantPanel
    return AssistantPanel(db, project_id)


def test_assistant_template_selector_lists_templates(_plugin_template):
    db = Database()
    p = db.create_project("Novel")
    panel = _panel(db, p.id)
    panel.set_active_section_name("Outline")
    combo = panel._outline_template_combo
    assert combo.findData("save_the_cat") >= 0
    assert combo.findData("kishotenketsu") >= 0   # plugin template visible


def test_assistant_template_row_gated_to_outline_mode():
    db = Database()
    p = db.create_project("Novel")
    panel = _panel(db, p.id)
    panel.set_active_section_name("Manuscript")
    assert panel._is_outline_mode() is False
    panel.set_active_section_name("Outline")
    assert panel._is_outline_mode() is True


def test_selected_outline_template():
    db = Database()
    p = db.create_project("Novel")
    panel = _panel(db, p.id)
    panel.set_active_section_name("Outline")
    idx = panel._outline_template_combo.findData("three_act")
    panel._outline_template_combo.setCurrentIndex(idx)
    assert panel.selected_outline_template() == "three_act"


# =========================================================================
# 3. Template affects the generated prompt
# =========================================================================

def test_template_folds_into_prompt():
    db = Database()
    p = db.create_project("Novel")
    panel = _panel(db, p.id)
    panel.set_active_section_name("Outline")
    idx = panel._outline_template_combo.findData("save_the_cat")
    panel._outline_template_combo.setCurrentIndex(idx)
    folded = panel._outline_template_prompt("Generate the outline for a heist")
    assert "Save the Cat" in folded
    assert "heist" in folded                       # user instruction kept
    # A real template beat is included.
    beat = get_template("save_the_cat").beats[0].title
    assert beat in folded


def test_plugin_template_folds_into_prompt(_plugin_template):
    db = Database()
    p = db.create_project("Novel")
    panel = _panel(db, p.id)
    panel.set_active_section_name("Outline")
    idx = panel._outline_template_combo.findData("kishotenketsu")
    panel._outline_template_combo.setCurrentIndex(idx)
    folded = panel._outline_template_prompt("a quiet drama")
    assert "Kishōtenketsu" in folded
    assert "Ten" in folded


def test_no_template_is_passthrough():
    db = Database()
    p = db.create_project("Novel")
    panel = _panel(db, p.id)
    panel.set_active_section_name("Outline")
    panel._outline_template_combo.setCurrentIndex(0)   # "No template"
    assert panel._outline_template_prompt("X") == "X"


def test_non_outline_mode_is_passthrough():
    db = Database()
    p = db.create_project("Novel")
    panel = _panel(db, p.id)
    panel.set_active_section_name("Outline")
    idx = panel._outline_template_combo.findData("three_act")
    panel._outline_template_combo.setCurrentIndex(idx)
    panel.set_active_section_name("Manuscript")        # leave Outline Mode
    assert panel._outline_template_prompt("Y") == "Y"


def test_template_prompt_engine_aware():
    db = Database()
    p = db.create_project("Screenplay", narrative_engine="screenplay",
                          default_writing_format="screenplay")
    panel = _panel(db, p.id)
    panel.set_active_section_name("Outline")
    idx = panel._outline_template_combo.findData("three_act")
    panel._outline_template_combo.setCurrentIndex(idx)
    folded = panel._outline_template_prompt("a thriller")
    assert "Sequence" in folded                       # screenplay vocabulary


# =========================================================================
# 4. OutlineView combo also sees plugin templates
# =========================================================================

def test_outline_view_combo_lists_plugin_template(_plugin_template):
    from logosforge.ui.outline_view import OutlineView
    db = Database()
    p = db.create_project("Novel")
    view = OutlineView(db, p.id)
    assert view._template_combo.findData("kishotenketsu") >= 0


def test_outline_view_generation_uses_plugin_template(_plugin_template):
    from logosforge.ui.outline_view import OutlineView
    db = Database()
    p = db.create_project("Novel")
    view = OutlineView(db, p.id)
    idx = view._template_combo.findData("kishotenketsu")
    view._template_combo.setCurrentIndex(idx)
    prompt = view.build_generation_prompt("full", None)
    assert "Kishōtenketsu" in prompt
    assert "Ten" in prompt


# =========================================================================
# 5. PSYKE Outline Templates plugin contributes its templates to the catalog
# =========================================================================

def _load_psyke_outline_templates_plugin():
    """Load plugins/psyke_outline_templates/plugin.py the way PluginManager does."""
    import importlib.util
    import sys
    from pathlib import Path
    path = (Path(__file__).resolve().parents[1]
            / "plugins" / "psyke_outline_templates" / "plugin.py")
    spec = importlib.util.spec_from_file_location("psyke_ot_plugin_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod          # dataclasses needs the module registered
    spec.loader.exec_module(mod)
    return mod


def test_psyke_outline_templates_plugin_registers_into_catalog():
    # The plugin was inert (it called a non-existent register_plugin API); it must
    # now contribute its structures to the shared catalog so they're usable.
    from logosforge.outline_templates import (
        get_template, list_templates, unregister_outline_template,
    )

    class _Api:
        def log(self, *_a, **_k):
            pass

    mod = _load_psyke_outline_templates_plugin()
    plugin = mod.register(_Api())
    try:
        keys = {k for k, _, _ in list_templates()}
        # Plugin-unique structures are contributed.
        for k in ("mystery", "kishotenketsu", "fichtean_curve", "seven_point",
                  "quest", "heroine_journey"):
            assert k in keys, f"plugin template {k} not in catalog"
        t = get_template("mystery")
        assert t is not None and t.beats          # real, applyable template
        # Built-in keys are never overwritten by the plugin.
        assert get_template("save_the_cat").name == "Save the Cat"
        # Structures a richer built-in already covers are NOT duplicated: the
        # plugin doesn't register hero_journey / freytag (kept heros_journey /
        # five_act), so no redundant combo entries.
        assert "hero_journey" not in keys and "freytag" not in keys
        assert get_template("heros_journey").name == "Hero's Journey"
        assert "Freytag" in get_template("five_act").name
    finally:
        for k in list(plugin.templates):
            unregister_outline_template(k)
