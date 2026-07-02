"""Tests for Story Flow Layer — tension, pacing, scene type, and grid integration."""

from logosforge.db import Database
from logosforge.story_flow import (
    FlowAnalysis,
    PacingWarning,
    SceneTension,
    SceneType,
    _BEAT_TENSION,
    _SCENE_TYPE_ICONS,
    analyze_flow,
    classify_scene_type,
    compute_tension,
    detect_pacing_warnings,
    scene_type_icon,
    tension_color,
)
from PySide6.QtWidgets import QLabel

from logosforge.ui import theme
from logosforge.ui.story_grid_view import StoryGridView, _SceneCard


def _make_project():
    db = Database()
    proj = db.create_project("FlowTest")
    return db, proj


# -- compute_tension ---------------------------------------------------------

def test_tension_manual_override():
    db, proj = _make_project()
    s = db.create_scene(proj.id, "Test", tags="tension:8, thriller")
    scene = db.get_scene_by_id(s.id)
    t = compute_tension(scene)
    assert t.value == 8
    assert t.source == "manual"


def test_tension_manual_clamped():
    db, proj = _make_project()
    s = db.create_scene(proj.id, "Test", tags="tension:15")
    scene = db.get_scene_by_id(s.id)
    t = compute_tension(scene)
    assert t.value == 10


def test_tension_from_beat():
    db, proj = _make_project()
    s = db.create_scene(proj.id, "Test", beat="Climax")
    scene = db.get_scene_by_id(s.id)
    t = compute_tension(scene)
    assert t.value == 9
    assert t.source == "beat"


def test_tension_from_beat_case_insensitive():
    db, proj = _make_project()
    s = db.create_scene(proj.id, "Test", beat="midpoint")
    scene = db.get_scene_by_id(s.id)
    t = compute_tension(scene)
    assert t.value == 7
    assert t.source == "beat"


def test_tension_from_conflict_field():
    db, proj = _make_project()
    s = db.create_scene(proj.id, "Test", conflict="Hero vs villain", content="They stood in silence.")
    scene = db.get_scene_by_id(s.id)
    t = compute_tension(scene)
    assert t.value >= 5
    assert t.source == "conflict"


def test_tension_from_conflict_content_boosts():
    db, proj = _make_project()
    content = "They fought and attacked each other. He screamed and struggled against the enemy. Danger surrounded them."
    s = db.create_scene(proj.id, "Test", conflict="fight", content=content)
    scene = db.get_scene_by_id(s.id)
    t = compute_tension(scene)
    assert t.value > 5


def test_tension_from_content_high_conflict():
    db, proj = _make_project()
    content = "He fought and struggled against the threat. Fear and rage consumed him. The enemy attacked."
    s = db.create_scene(proj.id, "Test", content=content)
    scene = db.get_scene_by_id(s.id)
    t = compute_tension(scene)
    assert t.source == "content"
    assert t.value >= 4


def test_tension_default_for_calm_scene():
    db, proj = _make_project()
    s = db.create_scene(proj.id, "Test", content="The sun shone warmly on the meadow.")
    scene = db.get_scene_by_id(s.id)
    t = compute_tension(scene)
    assert t.value == 2
    assert t.source == "default"


def test_tension_empty_scene():
    db, proj = _make_project()
    s = db.create_scene(proj.id, "Test", content="")
    scene = db.get_scene_by_id(s.id)
    t = compute_tension(scene)
    assert t.value == 2
    assert t.source == "default"


# -- classify_scene_type -----------------------------------------------------

def test_scene_type_dialogue():
    db, proj = _make_project()
    content = '"Hello," she said.\n"Hi," he replied.\n"How are you?"\n"Fine, thanks."\nShe nodded.'
    s = db.create_scene(proj.id, "Test", content=content)
    scene = db.get_scene_by_id(s.id)
    st = classify_scene_type(scene)
    assert st.primary == "dialogue"
    assert st.dialogue_ratio >= 0.4


def test_scene_type_action():
    db, proj = _make_project()
    content = "He ran and jumped over the fence. She sprinted after him. They crashed through the door and dodged the guards."
    s = db.create_scene(proj.id, "Test", content=content)
    scene = db.get_scene_by_id(s.id)
    st = classify_scene_type(scene)
    assert st.primary == "action"
    assert st.action_ratio >= 0.03


def test_scene_type_exposition():
    db, proj = _make_project()
    content = "The city had been built centuries ago by settlers from the north. Its walls told stories of trade and prosperity."
    s = db.create_scene(proj.id, "Test", content=content)
    scene = db.get_scene_by_id(s.id)
    st = classify_scene_type(scene)
    assert st.primary == "exposition"


def test_scene_type_empty():
    db, proj = _make_project()
    s = db.create_scene(proj.id, "Test", content="")
    scene = db.get_scene_by_id(s.id)
    st = classify_scene_type(scene)
    assert st.primary == "exposition"
    assert st.dialogue_ratio == 0.0


# -- detect_pacing_warnings --------------------------------------------------

def test_pacing_no_warnings_short():
    tensions = [SceneTension(i, 5, "default") for i in range(3)]
    warnings = detect_pacing_warnings(tensions)
    assert warnings == []


def test_pacing_monotone_low():
    tensions = [SceneTension(i, 2, "default") for i in range(5)]
    warnings = detect_pacing_warnings(tensions)
    assert any(w.reason == "monotone_low" for w in warnings)


def test_pacing_monotone_high():
    tensions = [SceneTension(i, 8, "default") for i in range(5)]
    warnings = detect_pacing_warnings(tensions)
    assert any(w.reason == "monotone_high" for w in warnings)


def test_pacing_no_variation():
    tensions = [SceneTension(i, 5, "default") for i in range(5)]
    warnings = detect_pacing_warnings(tensions)
    assert any(w.reason == "no_variation" for w in warnings)


def test_pacing_varied_no_warnings():
    tensions = [
        SceneTension(0, 3, "default"),
        SceneTension(1, 7, "default"),
        SceneTension(2, 4, "default"),
        SceneTension(3, 8, "default"),
        SceneTension(4, 2, "default"),
    ]
    warnings = detect_pacing_warnings(tensions)
    assert warnings == []


def test_pacing_deduplication():
    tensions = [SceneTension(i, 2, "default") for i in range(6)]
    warnings = detect_pacing_warnings(tensions)
    ids_seen = set()
    for w in warnings:
        key = tuple(w.scene_ids)
        assert key not in ids_seen
        ids_seen.add(key)


# -- tension_color -----------------------------------------------------------

def test_tension_color_low():
    assert tension_color(1) == "#4ade80"
    assert tension_color(2) == "#4ade80"


def test_tension_color_medium():
    assert tension_color(5) == "#facc15"
    assert tension_color(6) == "#facc15"


def test_tension_color_high():
    assert tension_color(9) == "#f87171"
    assert tension_color(10) == "#f87171"


def test_tension_color_orange():
    assert tension_color(7) == "#fb923c"
    assert tension_color(8) == "#fb923c"


# -- scene_type_icon ---------------------------------------------------------

def test_scene_type_icon_dialogue():
    assert scene_type_icon("dialogue") != ""


def test_scene_type_icon_action():
    assert scene_type_icon("action") != ""


def test_scene_type_icon_exposition():
    assert scene_type_icon("exposition") != ""


def test_scene_type_icon_unknown():
    assert scene_type_icon("unknown") == ""


# -- analyze_flow (integration) ----------------------------------------------

def test_analyze_flow_basic():
    db, proj = _make_project()
    db.create_scene(proj.id, "S1", content="The hero fought bravely.", beat="Climax")
    db.create_scene(proj.id, "S2", content='"Hello," she said.\n"Hi."', conflict="argument")
    flow = analyze_flow(db, proj.id)
    assert len(flow.tensions) == 2
    assert len(flow.scene_types) == 2


def test_analyze_flow_empty_project():
    db, proj = _make_project()
    flow = analyze_flow(db, proj.id)
    assert flow.tensions == {}
    assert flow.scene_types == {}
    assert flow.pacing_warnings == []


# -- Grid integration: flow toggle -------------------------------------------

def test_grid_flow_default_off():
    db, proj = _make_project()
    db.create_scene(proj.id, "S1", act="Act 1", content="Calm.")
    view = StoryGridView(db, proj.id)
    assert view.is_flow_visible() is False


def test_grid_flow_toggle_on():
    db, proj = _make_project()
    db.create_scene(proj.id, "S1", act="Act 1", content="They fought.", conflict="fight")
    view = StoryGridView(db, proj.id)
    view._flow_check.setChecked(True)
    assert view.is_flow_visible() is True
    assert view._flow_analysis is not None


def test_grid_flow_toggle_off():
    db, proj = _make_project()
    db.create_scene(proj.id, "S1", act="Act 1", content="Peace.")
    view = StoryGridView(db, proj.id)
    view._flow_check.setChecked(True)
    view._flow_check.setChecked(False)
    assert view.is_flow_visible() is False
    assert view._flow_analysis is None


def test_grid_card_tension_bar_visible_when_flow():
    db, proj = _make_project()
    s = db.create_scene(proj.id, "S1", act="Act 1", beat="Climax", content="Fight!")
    scene = db.get_scene_by_id(s.id)
    tension = SceneTension(scene.id, 9, "beat")
    card = _SceneCard(scene, zoom=2, flow_visible=True, tension=tension)
    assert not card._tension_bar.isHidden()


def test_grid_card_tension_bar_hidden_no_flow():
    db, proj = _make_project()
    s = db.create_scene(proj.id, "S1", act="Act 1", beat="Climax", content="Fight!")
    scene = db.get_scene_by_id(s.id)
    tension = SceneTension(scene.id, 9, "beat")
    card = _SceneCard(scene, zoom=2, flow_visible=False, tension=tension)
    assert card._tension_bar.isHidden()


def test_grid_card_type_label_visible_when_flow():
    db, proj = _make_project()
    s = db.create_scene(proj.id, "S1", act="Act 1", content='"Hi," she said.\n"Hello."')
    scene = db.get_scene_by_id(s.id)
    stype = SceneType(scene.id, "dialogue", 0.5, 0.0)
    card = _SceneCard(scene, zoom=2, flow_visible=True, scene_type=stype)
    assert card._type_label.text() != ""


def test_grid_card_char_dots_visible():
    db, proj = _make_project()
    s = db.create_scene(proj.id, "S1", act="Act 1", content="Story.")
    scene = db.get_scene_by_id(s.id)
    card = _SceneCard(scene, zoom=2, flow_visible=True, char_colors=["#3498db", "#e74c3c"])
    dots = [w for w in card._char_row.findChildren(QLabel) if w.objectName() == "gridCharDot"]
    assert len(dots) == 2


def test_grid_card_pacing_warning_objectname():
    db, proj = _make_project()
    s = db.create_scene(proj.id, "S1", act="Act 1", content="Calm.")
    scene = db.get_scene_by_id(s.id)
    card = _SceneCard(scene, zoom=2, flow_visible=True, pacing_warning=True)
    assert card.objectName() == "gridSceneCardWarning"


def test_grid_card_no_warning_normal_name():
    db, proj = _make_project()
    s = db.create_scene(proj.id, "S1", act="Act 1", content="Normal.")
    scene = db.get_scene_by_id(s.id)
    card = _SceneCard(scene, zoom=2, flow_visible=True, pacing_warning=False)
    assert card.objectName() == "gridSceneCard"


# -- Theme includes flow styles -----------------------------------------------

def test_theme_has_tension_bar_rule():
    ss = theme.build_stylesheet()
    assert "#gridTensionBar" in ss


def test_theme_has_card_warning_rule():
    ss = theme.build_stylesheet()
    assert "#gridSceneCardWarning" in ss


def test_theme_has_char_row_rule():
    ss = theme.build_stylesheet()
    assert "#gridCharRow" in ss


# -- Dataclass construction ---------------------------------------------------

def test_scene_tension_dataclass():
    t = SceneTension(scene_id=1, value=7, source="beat")
    assert t.scene_id == 1
    assert t.value == 7


def test_scene_type_dataclass():
    st = SceneType(scene_id=1, primary="dialogue", dialogue_ratio=0.5, action_ratio=0.0)
    assert st.primary == "dialogue"


def test_pacing_warning_dataclass():
    pw = PacingWarning(start_scene_id=1, end_scene_id=4, scene_ids=[1, 2, 3, 4], reason="monotone_low")
    assert pw.reason == "monotone_low"
    assert len(pw.scene_ids) == 4


def test_flow_analysis_dataclass():
    fa = FlowAnalysis(tensions={}, scene_types={}, pacing_warnings=[])
    assert fa.tensions == {}
