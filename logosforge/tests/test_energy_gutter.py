"""Tests for inline energy gutter — visual indicators in manuscript editor."""

from PySide6.QtWidgets import QApplication

from logosforge.db import Database
from logosforge.paragraph_energy import StoryContext
from logosforge.ui.writing_core_view import (
    WritingCoreView,
    _EnergyGutter,
    _GUTTER_WIDTH,
    _SceneEditor,
    _tension_dot_color,
)


def _app():
    return QApplication.instance() or QApplication([])


def _make_view(content="First paragraph.\n\nSecond paragraph.\n\nThird paragraph.", energy=True):
    _app()
    db = Database()
    proj = db.create_project("EnergyTest")
    if energy:
        settings = db.get_project_settings(proj.id)
        settings["energy_enabled"] = True
        db.save_project_settings(proj.id, settings)
    scene = db.create_scene(proj.id, "Scene 1", content=content)
    view = WritingCoreView(db, proj.id)
    return view, scene


# -- Gutter creation ----------------------------------------------------------

def test_gutter_created_for_each_scene():
    view, scene = _make_view()
    assert scene.id in view._energy_gutters
    gutter = view._energy_gutters[scene.id]
    assert isinstance(gutter, _EnergyGutter)


def test_gutter_created_for_multiple_scenes():
    _app()
    db = Database()
    proj = db.create_project("Multi")
    s1 = db.create_scene(proj.id, "S1", content="Line one.")
    s2 = db.create_scene(proj.id, "S2", content="Line two.")
    s3 = db.create_scene(proj.id, "S3", content="Line three.")
    view = WritingCoreView(db, proj.id)
    assert s1.id in view._energy_gutters
    assert s2.id in view._energy_gutters
    assert s3.id in view._energy_gutters


# -- Fixed width (no layout shift) --------------------------------------------

def test_gutter_fixed_width():
    view, scene = _make_view()
    gutter = view._energy_gutters[scene.id]
    assert gutter.width() == _GUTTER_WIDTH
    assert gutter.minimumWidth() == _GUTTER_WIDTH
    assert gutter.maximumWidth() == _GUTTER_WIDTH


def test_gutter_width_constant():
    assert _GUTTER_WIDTH == 8


def test_gutter_width_unchanged_after_recompute():
    view, scene = _make_view("Short.\n\nAnother short.")
    gutter = view._energy_gutters[scene.id]
    w_before = gutter.width()
    gutter._recompute()
    assert gutter.width() == w_before


# -- Energy computation -------------------------------------------------------

def test_gutter_computes_energies():
    view, scene = _make_view()
    gutter = view._energy_gutters[scene.id]
    assert len(gutter._energies) == 3


def test_gutter_energies_match_paragraphs():
    view, scene = _make_view("A.\n\nB.\n\nC.\n\nD.")
    gutter = view._energy_gutters[scene.id]
    assert len(gutter._energies) == 4


def test_gutter_energies_have_metrics():
    view, scene = _make_view()
    gutter = view._energy_gutters[scene.id]
    for e in gutter._energies:
        assert "tension" in e.metrics
        assert "pacing" in e.metrics
        assert "conflict" in e.metrics


def test_gutter_recompute_updates_energies():
    view, scene = _make_view("One paragraph.")
    gutter = view._energy_gutters[scene.id]
    assert len(gutter._energies) == 1
    editor = view._editors[scene.id]
    editor.setPlainText("First.\n\nSecond.")
    gutter._recompute()
    assert len(gutter._energies) == 2


# -- Markers render for multiple paragraphs -----------------------------------

def test_markers_render_multiple_paragraphs():
    view, scene = _make_view(
        "She feared the darkness.\n\n"
        "They fought fiercely.\n\n"
        "The sun rose peacefully."
    )
    gutter = view._energy_gutters[scene.id]
    pairs = list(gutter._block_energy_pairs())
    assert len(pairs) == 3
    for _, energy, _idx in pairs:
        assert "tension" in energy.metrics


def test_markers_skip_blank_blocks():
    view, scene = _make_view("Line A.\n\n\n\nLine B.")
    gutter = view._energy_gutters[scene.id]
    pairs = list(gutter._block_energy_pairs())
    assert len(pairs) == 2


# -- Color mapping -------------------------------------------------------------

def test_tension_color_low():
    c = _tension_dot_color(0.1)
    assert c.alphaF() < 0.5


def test_tension_color_high():
    c = _tension_dot_color(0.9)
    assert c.alphaF() >= 0.5


def test_tension_color_range():
    for t in [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]:
        c = _tension_dot_color(t)
        assert 0.0 < c.alphaF() <= 1.0


# -- Cleanup on refresh -------------------------------------------------------

def test_gutters_cleared_on_refresh():
    _app()
    db = Database()
    proj = db.create_project("Refresh")
    s = db.create_scene(proj.id, "S", content="Text.")
    view = WritingCoreView(db, proj.id)
    assert s.id in view._energy_gutters
    view.refresh()
    assert s.id in view._energy_gutters


def test_gutters_match_editors():
    _app()
    db = Database()
    proj = db.create_project("Match")
    db.create_scene(proj.id, "A", content="Hello.")
    db.create_scene(proj.id, "B", content="World.")
    view = WritingCoreView(db, proj.id)
    assert set(view._energy_gutters.keys()) == set(view._editors.keys())


# -- No layout shift -----------------------------------------------------------

def test_no_layout_shift_on_empty_content():
    view, scene = _make_view("")
    gutter = view._energy_gutters[scene.id]
    assert gutter.width() == _GUTTER_WIDTH
    assert len(gutter._energies) == 0


def test_editor_row_has_gutter_and_editor():
    view, scene = _make_view("Content.")
    gutter = view._energy_gutters[scene.id]
    editor = view._editors[scene.id]
    row = gutter.parent()
    assert row is not None
    assert row.objectName() == "writingEditorRow"
    layout = row.layout()
    widgets = [layout.itemAt(i).widget() for i in range(layout.count())]
    assert gutter in widgets
    assert editor in widgets


# -- Flow hint integration -----------------------------------------------------

def test_gutter_stores_hints():
    calm = "The table was wooden.\n\n" * 5
    view, scene = _make_view(calm.strip())
    gutter = view._energy_gutters[scene.id]
    assert isinstance(gutter._hints, list)


def test_gutter_flat_content_generates_hints():
    lines = "\n\n".join([
        "The table stood still.",
        "The chair was wooden.",
        "The floor was clean.",
        "The window was open.",
        "The curtain was white.",
    ])
    view, scene = _make_view(lines)
    gutter = view._energy_gutters[scene.id]
    flat = [h for h in gutter._hints if h.kind == "flat"]
    assert len(flat) >= 1


def test_gutter_varied_content_no_flat_hint():
    lines = "\n\n".join([
        "She feared the lurking darkness.",
        "They fought and attacked fiercely.",
        "He laughed then sobbed with grief.",
        "She ran and jumped and fled!",
    ])
    view, scene = _make_view(lines)
    gutter = view._energy_gutters[scene.id]
    flat = [h for h in gutter._hints if h.kind == "flat"]
    assert len(flat) == 0


def test_gutter_hinted_paragraph_has_message():
    lines = "\n\n".join([
        "The table stood still.",
        "The chair was wooden.",
        "The floor was clean.",
        "The window was open.",
        "The curtain was white.",
    ])
    view, scene = _make_view(lines)
    gutter = view._energy_gutters[scene.id]
    assert len(gutter._hinted_paragraphs) > 0
    for msg in gutter._hinted_paragraphs.values():
        assert len(msg) > 0


def test_gutter_no_layout_shift_with_hints():
    lines = "\n\n".join(["Calm line." for _ in range(6)])
    view, scene = _make_view(lines)
    gutter = view._energy_gutters[scene.id]
    assert gutter.width() == _GUTTER_WIDTH


# -- Toggle on/off -------------------------------------------------------------

def test_toggle_off_clears_energies():
    view, scene = _make_view("Some text.\n\nMore text.")
    gutter = view._energy_gutters[scene.id]
    assert len(gutter._energies) == 2
    view._toggle_energy()
    assert len(gutter._energies) == 0
    assert not gutter._enabled


def test_toggle_on_computes_energies():
    view, scene = _make_view("Line one.\n\nLine two.", energy=False)
    gutter = view._energy_gutters[scene.id]
    assert len(gutter._energies) == 0
    view._toggle_energy()
    assert gutter._enabled
    assert len(gutter._energies) == 2


def test_toggle_off_stops_timer():
    view, scene = _make_view("Text.")
    gutter = view._energy_gutters[scene.id]
    gutter._schedule()
    assert gutter._timer.isActive()
    view._toggle_energy()
    assert not gutter._timer.isActive()


def test_toggle_persists_to_settings():
    _app()
    db = Database()
    proj = db.create_project("Persist")
    db.create_scene(proj.id, "S", content="Hello.")
    view = WritingCoreView(db, proj.id)
    assert not view._energy_enabled
    view._toggle_energy()
    saved = db.get_project_settings(proj.id)
    assert saved["energy_enabled"] is True


def test_toggle_restores_from_settings():
    _app()
    db = Database()
    proj = db.create_project("Restore")
    settings = db.get_project_settings(proj.id)
    settings["energy_enabled"] = True
    db.save_project_settings(proj.id, settings)
    scene = db.create_scene(proj.id, "S", content="Content.")
    view = WritingCoreView(db, proj.id)
    assert view._energy_enabled
    gutter = view._energy_gutters[scene.id]
    assert gutter._enabled
    assert len(gutter._energies) > 0


def test_default_off():
    view, scene = _make_view("Text.", energy=False)
    gutter = view._energy_gutters[scene.id]
    assert not gutter._enabled
    assert len(gutter._energies) == 0


# -- Sensitivity ---------------------------------------------------------------

def test_sensitivity_default_medium():
    view, scene = _make_view()
    gutter = view._energy_gutters[scene.id]
    assert gutter._sensitivity == "medium"


def test_set_sensitivity_updates_gutters():
    view, scene = _make_view()
    view._set_energy_sensitivity("high")
    gutter = view._energy_gutters[scene.id]
    assert gutter._sensitivity == "high"


def test_set_sensitivity_persists():
    _app()
    db = Database()
    proj = db.create_project("SensPersist")
    settings = db.get_project_settings(proj.id)
    settings["energy_enabled"] = True
    db.save_project_settings(proj.id, settings)
    db.create_scene(proj.id, "S", content="Text.")
    view = WritingCoreView(db, proj.id)
    view._set_energy_sensitivity("low")
    saved = db.get_project_settings(proj.id)
    assert saved["energy_sensitivity"] == "low"


def test_sensitivity_restores_from_settings():
    _app()
    db = Database()
    proj = db.create_project("SensRestore")
    settings = db.get_project_settings(proj.id)
    settings["energy_enabled"] = True
    settings["energy_sensitivity"] = "high"
    db.save_project_settings(proj.id, settings)
    db.create_scene(proj.id, "S", content="Text.")
    view = WritingCoreView(db, proj.id)
    assert view._energy_sensitivity == "high"
    gutter = list(view._energy_gutters.values())[0]
    assert gutter._sensitivity == "high"


def test_sensitivity_invalid_falls_back():
    _app()
    db = Database()
    proj = db.create_project("BadSens")
    settings = db.get_project_settings(proj.id)
    settings["energy_sensitivity"] = "ultra"
    db.save_project_settings(proj.id, settings)
    db.create_scene(proj.id, "S", content="Text.")
    view = WritingCoreView(db, proj.id)
    assert view._energy_sensitivity == "medium"


# -- PSYKE context integration ------------------------------------------------

def test_gutter_has_story_context():
    view, scene = _make_view("Some text.")
    gutter = view._energy_gutters[scene.id]
    assert hasattr(gutter, "_story_context")


def test_gutter_set_story_context():
    view, scene = _make_view("Text here.")
    gutter = view._energy_gutters[scene.id]
    ctx = StoryContext(tension_boost=0.5)
    gutter.set_story_context(ctx)
    assert gutter._story_context is ctx


def test_gutter_context_affects_energies():
    view, scene = _make_view("The table was wooden.")
    gutter = view._energy_gutters[scene.id]
    base_tension = gutter._energies[0].tension

    ctx = StoryContext(tension_boost=1.0)
    gutter.set_story_context(ctx)
    assert gutter._energies[0].tension > base_tension


def test_gutter_neutral_context_no_change():
    view, scene = _make_view("The table was wooden.")
    gutter = view._energy_gutters[scene.id]
    base_tension = gutter._energies[0].tension

    ctx = StoryContext()
    gutter.set_story_context(ctx)
    assert gutter._energies[0].tension == base_tension


def test_psyke_state_changes_gutter_energy():
    _app()
    db = Database()
    proj = db.create_project("PsykeGutter")
    settings = db.get_project_settings(proj.id)
    settings["energy_enabled"] = True
    db.save_project_settings(proj.id, settings)
    char = db.create_character(proj.id, "Alice")
    scene = db.create_scene(
        proj.id, "S1", content="The room was quiet.",
        character_ids=[char.id],
    )
    view = WritingCoreView(db, proj.id)
    gutter = view._energy_gutters[scene.id]
    t_before = gutter._energies[0].tension

    db.update_scene(
        scene.id, "S1", content="The room was quiet.",
        character_ids=[char.id],
        character_states=[(char.id, "Alice is terrified and trapped")],
    )
    view._rebuild_energy_contexts()
    t_after = gutter._energies[0].tension
    assert t_after > t_before


def test_rebuild_energy_contexts_updates_all_gutters():
    _app()
    db = Database()
    proj = db.create_project("RebuildCtx")
    settings = db.get_project_settings(proj.id)
    settings["energy_enabled"] = True
    db.save_project_settings(proj.id, settings)
    s1 = db.create_scene(proj.id, "S1", content="Line one.")
    s2 = db.create_scene(proj.id, "S2", content="Line two.")
    view = WritingCoreView(db, proj.id)
    view._rebuild_energy_contexts()
    for sid in [s1.id, s2.id]:
        gutter = view._energy_gutters[sid]
        assert gutter._story_context is not None
