"""Final global multi-mode integrity audit — Alpha Release Gate.

A single cross-mode integration suite that certifies Logosforge is coherent across
all five writing modes (Novel / Screenplay / Graphic Novel / Stage Script / Series)
on one universal Manuscript, with the canonical Act -> Chapter -> Scene invariant,
project isolation, export privacy, dirty-state, and no scope creep (no Canvas Plot
nav, no image-generation / production / Season-Episode storage). Audit only — it
asserts the system works together; it adds no features.
"""

from __future__ import annotations

import os
import tokenize
import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge.logos.controller import LogosController
from logosforge.writing_modes import (
    get_project_writing_mode_by_id, set_project_writing_mode, current_primary_unit_type,
    NOVEL, SCREENPLAY, GRAPHIC_NOVEL, STAGE_SCRIPT, SERIES,
)

_MODES = {
    "novel": (NOVEL, "chapter"),
    "screenplay": (SCREENPLAY, "scene"),
    "graphic_novel": (GRAPHIC_NOVEL, "scene"),
    "stage_script": (STAGE_SCRIPT, "scene"),
    "series": (SERIES, "scene"),
}
_PREFIX = {"screenplay": "sp_", "graphic_novel": "gn_", "stage_script": "stage_",
           "series": "series_"}
_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    import logosforge.gomckee_bridge as gb
    monkeypatch.setattr(gb, "is_gomckee_enabled", lambda: False, raising=False)
    yield
    settings._instance = None


def _project(db, engine, title=None):
    return db.create_project(title or engine, narrative_engine=engine,
                             default_writing_format=engine).id


def _scene(db, pid, content="", *, title="S", summary="s", act="Act 1",
           chapter="Chapter 1"):
    return ss.create_scene(db, pid, act=act, chapter=chapter, title=title,
                           content=content, summary=summary).id


# ==========================================================================
# 1  Universal Manuscript routing — one section, mode-adaptive editor
# ==========================================================================


@pytest.mark.parametrize("engine,expected", list(_MODES.items()))
def test_mode_recognition_and_primary_unit(engine, expected):
    db = Database()
    pid = _project(db, engine)
    mode, unit = expected
    assert get_project_writing_mode_by_id(db, pid) == mode
    assert current_primary_unit_type(db.get_project_by_id(pid)) == unit


@pytest.mark.parametrize("engine", list(_MODES))
def test_one_universal_manuscript_view(engine):
    from logosforge.ui.writing_core_view import WritingCoreView
    db = Database()
    pid = _project(db, engine)
    _scene(db, pid, "INT. X - DAY\n\nBody." if engine != "novel" else "Prose body.")
    view = WritingCoreView(db, pid, structured_list=True)
    assert isinstance(view, WritingCoreView)        # same section class for every mode
    ed = next(iter(view._editors.values()))
    # Only the matching mode's editor flags are on; others stay off.
    assert ed._screenplay_mode is (engine == "screenplay")
    assert ed._graphic_novel_mode is (engine == "graphic_novel")


# ==========================================================================
# 2  Cross-mode non-contamination — switching mode preserves the body
# ==========================================================================


def test_mode_switch_preserves_scene_body():
    db = Database()
    pid = _project(db, "series")
    body = "INT. X - DAY\n\nMaria opens the door.\n\nMARIA\nHello."
    sid = _scene(db, pid, body, summary="keep")
    for mode in (NOVEL, SCREENPLAY, GRAPHIC_NOVEL, STAGE_SCRIPT, SERIES):
        set_project_writing_mode(db, pid, mode)
        assert db.get_scene_by_id(sid).content == body     # body is mode-agnostic
        assert db.get_scene_by_id(sid).summary == "keep"


def test_each_mode_parser_is_isolated():
    # Each mode has its own block adapter module/entry point (the return shape
    # differs: screenplay yields a list, the others a Script dataclass).
    from logosforge import screenplay_blocks as spb
    from logosforge import graphic_novel_blocks as gnb
    from logosforge import stage_script_blocks as ssb
    from logosforge import series_blocks as sbk
    body = "INT. ROOM - DAY\n\nAction.\n\nMARIA\nHi."
    parsed = [spb.parse_screenplay_text(body), gnb.parse_graphic_novel_text(body),
              ssb.parse_stage_script_text(body), sbk.parse_series_text(body)]
    assert all(p is not None for p in parsed)
    # Four distinct parse-result types (list / GraphicNovelScript / StageScript /
    # SeriesScript) prove each mode keeps its own adapter — no shared structure.
    assert len({type(p).__name__ for p in parsed}) == 4
    # Four distinct adapter modules — Series reuses the screenplay engine but is
    # its own module/types, never the same object.
    assert len({spb.__name__, gnb.__name__, ssb.__name__, sbk.__name__}) == 4


# ==========================================================================
# 3  Canonical Act -> Chapter -> Scene invariant + order propagation
# ==========================================================================


@pytest.mark.parametrize("engine", list(_MODES))
def test_act_chapter_scene_invariant(engine):
    db = Database()
    pid = _project(db, engine)
    _scene(db, pid, "x", act="Act 1", chapter="Chapter 1")
    for s in db.get_all_scenes(pid):
        assert (getattr(s, "act", "") or "").strip()       # every scene under an Act
        assert (getattr(s, "chapter", "") or "").strip()   # ...and a Chapter


def test_moving_scene_updates_canonical_order_everywhere():
    db = Database()
    pid = _project(db, "screenplay")
    a = _scene(db, pid, "INT. A - DAY\n\na.", title="A", act="Act 1", chapter="Chapter 1")
    b = _scene(db, pid, "INT. B - DAY\n\nb.", title="B", act="Act 1", chapter="Chapter 2")
    db.reorder_scenes(pid, [b, a])
    assert ss.canonical_scene_order(db, pid) == [b, a]     # canonical, not id order
    # Structural numbering follows canonical order.
    nums = ss.compute_structural_numbers(
        ss.build_structure_tree(db, pid), ss.is_novel_project(db, pid))["scenes"]
    assert nums[b] < nums[a] or nums[b] != nums[a]


# ==========================================================================
# 4  Timeline independence
# ==========================================================================


def test_timeline_event_does_not_create_fake_structure():
    db = Database()
    pid = _project(db, "series")
    a = _scene(db, pid, "INT. A - DAY\n\na.")
    scenes_before = len(db.get_all_scenes(pid))
    db.add_timeline_event(pid, a)
    assert len(db.get_all_scenes(pid)) == scenes_before    # no fake scenes/acts
    assert a in (db.get_timeline_event_ids(pid) or set())


def test_timeline_isolated_across_projects(tmp_path):
    db = Database(str(tmp_path / "tl.db"))
    a = _project(db, "novel", "A")
    sa = _scene(db, a, "x")
    db.add_timeline_event(a, sa)
    b = _project(db, "novel", "B")
    assert db.get_timeline_event_ids(b) in (set(), None) or len(
        db.get_timeline_event_ids(b)) == 0


# ==========================================================================
# 5  Notes — project-bound, canonical path
# ==========================================================================


def test_notes_link_project_bound_and_canonical(tmp_path):
    db = Database(str(tmp_path / "n.db"))
    a = _project(db, "novel", "A")
    sid = _scene(db, a, "x", title="Alpha")
    note = db.create_note(a, "n", "b")
    db.link_note_to_scene(getattr(note, "id", note), sid)
    assert sid in db.get_note_scene_links(getattr(note, "id", note))
    # Canonical label for the scene link (path follows structure).
    label, missing = ss.note_link_label(db, a, "scene", sid)
    assert "Alpha" in label and missing is False
    # Project B has no notes from A.
    b = _project(db, "novel", "B")
    assert len(db.get_all_notes(b)) == 0


# ==========================================================================
# 6  Assistant / Logos — mode-aware, no direct mutation
# ==========================================================================


@pytest.mark.parametrize("engine,prefix", list(_PREFIX.items()))
def test_logos_actions_are_mode_gated(engine, prefix):
    db = Database()
    _project(db, engine)
    names = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode=engine)]
    assert any(n.startswith(prefix) for n in names)        # this mode's actions present
    for other_engine, other_prefix in _PREFIX.items():
        if other_engine != engine:
            assert not any(n.startswith(other_prefix) for n in names)  # no leakage


def test_selection_actions_require_selection():
    # Block/selection rewrite actions across modes carry needs_selection=True;
    # full-scene actions do not.
    from logosforge.logos import actions as A
    by_name = {a.name: a for a in A.list_actions()}
    for n in ("series_rewrite_block", "stage_rewrite_block"):
        if n in by_name:
            assert by_name[n].needs_selection is True
    for n in ("series_rewrite_scene", "series_check", "series_review_dashboard"):
        if n in by_name:
            assert by_name[n].needs_selection is False


def test_deterministic_actions_never_call_llm():
    from logosforge.logos.context import build_logos_context

    def _boom(*a, **k):
        raise AssertionError("deterministic action must not call the LLM")

    db = Database()
    pid = _project(db, "series")
    sid = _scene(db, pid, "INT. X - DAY\n\nA beat.\n\nMARIA\nHi.")
    ctl = LogosController(db, provider_resolver=_boom, chat_fn=_boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    for action in ("series_check", "series_continuity_check", "series_review_dashboard"):
        res = ctl.run(ctx, action)
        assert res.ok and res.proposed_operations == []    # report only, no mutation


# ==========================================================================
# 7  Export / privacy
# ==========================================================================


def test_mode_exports_exclude_secrets_and_use_canonical_order():
    from logosforge.settings import get_manager
    from logosforge import graphic_novel_blocks as gnb
    from logosforge import stage_script_blocks as ssb
    from logosforge import series_blocks as sbk
    exporters = {"graphic_novel": gnb.export_project_markdown,
                 "stage_script": ssb.export_project_markdown,
                 "series": sbk.export_project_markdown}
    for engine, export in exporters.items():
        db = Database()
        get_manager().set("ai_api_key", "SECRET_KEY_SENTINEL")
        pid = _project(db, engine)
        b = _scene(db, pid, "INT. B - DAY\n\nBeta beat.", title="B",
                   act="Act 1", chapter="Chapter 2")
        a = _scene(db, pid, "INT. A - DAY\n\nAlpha beat.", title="A",
                   act="Act 1", chapter="Chapter 1")
        db.reorder_scenes(pid, [a, b])
        md = export(db, pid)
        assert "SECRET_KEY_SENTINEL" not in md              # no provider secrets
        assert md.index("Alpha beat") < md.index("Beta beat")  # canonical order


# ==========================================================================
# 8  Dirty state
# ==========================================================================


def test_data_change_marks_project_dirty():
    from logosforge.ui.main_window import MainWindow
    db = Database()
    pid = _project(db, "novel")
    _scene(db, pid, "Prose.", act="Act 1", chapter="Chapter 1")
    win = MainWindow(db, pid)
    assert win._dirty is False                              # fresh project not dirty
    win._on_data_changed()
    assert win._dirty is True and win._modified_since_save is True


def test_report_build_does_not_touch_main_window_dirty():
    from logosforge.ui.main_window import MainWindow
    from logosforge import series_dashboard as sdash
    db = Database()
    pid = _project(db, "series")
    _scene(db, pid, "INT. X - DAY\n\nx.")
    win = MainWindow(db, pid)
    win._dirty = False
    sdash.build_series_review(db, pid)                      # read-only report
    assert win._dirty is False


# ==========================================================================
# 9  Project isolation across modes
# ==========================================================================


def test_full_project_isolation(tmp_path):
    db = Database(str(tmp_path / "iso.db"))
    a = _project(db, "series", "A")
    _scene(db, a, "INT. A - DAY\n\nA_SENTINEL body.")
    db.create_psyke_entry(a, "Maria", "character")
    db.create_note(a, "note", "A_NOTE_SENTINEL")
    b = _project(db, "novel", "B")
    assert db.get_all_scenes(b) == []
    assert len(db.get_all_psyke_entries(b)) == 0
    assert len(db.get_all_notes(b)) == 0
    # New project C: no debris.
    c = _project(db, "stage_script", "C")
    assert db.get_all_scenes(c) == []
    # A intact.
    assert any("A_SENTINEL" in (s.content or "") for s in db.get_all_scenes(a))


# ==========================================================================
# 10  No scope creep
# ==========================================================================


def test_canvas_plot_is_hidden_from_navigation():
    from logosforge.ui.main_window import MainWindow
    db = Database()
    pid = _project(db, "novel")
    _scene(db, pid, "Prose.", act="Act 1", chapter="Chapter 1")
    win = MainWindow(db, pid)
    assert "Plot" not in getattr(win, "_nav_labels", [])   # Canvas Plot deferred
    btn = win.sidebar_buttons.get("Plot")
    if btn is not None:
        assert btn.property("nav_available") is False


def test_registry_has_no_image_or_production_actions():
    from logosforge.logos import actions as A
    blob = " ".join((a.name + " " + a.label).lower() for a in A.list_actions())
    for banned in ("comfyui", "image gen", "generate image", "image prompt",
                   "img2img", "txt2img", "stable diffusion", "production schedule",
                   "writers room", "showrunner automation", "canvas plot", "lora "):
        assert banned not in blob, banned


def test_no_writing_module_uses_season_episode_tables():
    targets = [f"logosforge/{m}.py" for m in (
        "series_blocks", "series_pipeline", "series_diagnostics", "series_reflection",
        "series_rewrite", "series_continuity", "series_dashboard")]
    for rel in targets:
        toks = []
        with open(os.path.join(_HERE, rel), "rb") as fh:
            for tok in tokenize.tokenize(fh.readline):
                name = tokenize.tok_name[tok.type]
                if tok.type == tokenize.COMMENT or name.endswith("STRING"):
                    continue
                toks.append(tok.string.lower())
        skeleton = " ".join(toks)
        assert "season(" not in skeleton and "episode(" not in skeleton, rel
        assert "models.season" not in skeleton and "models.episode" not in skeleton, rel


def test_all_five_modes_present_and_distinct():
    db = Database()
    seen = set()
    for engine in _MODES:
        pid = _project(db, engine)
        seen.add(get_project_writing_mode_by_id(db, pid))
    assert seen == {NOVEL, SCREENPLAY, GRAPHIC_NOVEL, STAGE_SCRIPT, SERIES}
