"""Global multi-mode integrity audit suite.

Cross-mode integration checks across Novel / Screenplay / Graphic Novel over the
one universal Manuscript: editor routing, cross-mode non-contamination, mode-aware
Logos actions, no image-generation anywhere, canonical structure, three-project
isolation, export/report privacy, and Assistant mode context. No new features —
this verifies the existing architecture is coherent before Stage Script mode.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge.writing_modes import (
    get_project_writing_mode_by_id, set_project_writing_mode,
    NOVEL, SCREENPLAY, GRAPHIC_NOVEL,
)


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


def _novel(db, title="N"):
    return db.create_project(title, narrative_engine="novel").id


def _screenplay(db, title="S"):
    return db.create_project(title, narrative_engine="screenplay",
                             default_writing_format="screenplay").id


def _gn(db, title="G"):
    return db.create_project(title, narrative_engine="graphic_novel",
                             default_writing_format="graphic_novel").id


def _manuscript(db, pid):
    from logosforge.ui.writing_core_view import WritingCoreView
    return WritingCoreView(db, pid, structured_list=True)


# ==========================================================================
# 1  Universal Manuscript routing — one section, mode-correct editor
# ==========================================================================


def test_one_manuscript_class_for_all_modes():
    from logosforge.ui.writing_core_view import WritingCoreView
    db = Database()
    for mk in (_novel, _screenplay, _gn):
        pid = mk(db, mk.__name__)
        ss.create_scene(db, pid, act="Act I", chapter="Chapter 1", title="S",
                        content="body")
        assert isinstance(_manuscript(db, pid), WritingCoreView)


def test_manuscript_editor_mode_flags_route_by_writing_mode():
    db = Database()
    cases = [(_novel, False, False), (_screenplay, True, False), (_gn, False, True)]
    for mk, want_sp, want_gn in cases:
        pid = mk(db, mk.__name__ + "x")
        ss.create_scene(db, pid, act="Act I", chapter="Chapter 1", title="S",
                        content="some body text")
        view = _manuscript(db, pid)
        ed = next(iter(view._editors.values()))
        assert ed._screenplay_mode is want_sp, mk.__name__
        assert ed._graphic_novel_mode is want_gn, mk.__name__


# ==========================================================================
# 2  Cross-mode non-contamination
# ==========================================================================


def test_body_preserved_across_mode_switch():
    db = Database()
    pid = _novel(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Chapter 1", title="S",
                          content="Original body text.", summary="keep").id
    for mode in (SCREENPLAY, GRAPHIC_NOVEL, NOVEL):
        set_project_writing_mode(db, pid, mode)
        assert db.get_scene_by_id(sid).content == "Original body text."
        assert db.get_scene_by_id(sid).summary == "keep"


def test_parsers_are_independent_and_lossless():
    # Each mode's parser is self-contained; a body authored for one mode is never
    # silently destroyed when parsed by another (round-trip preserves text).
    from logosforge import graphic_novel_blocks as gnb
    from logosforge import screenplay_blocks as sb
    prose = "Just a paragraph of prose with no markers."
    # GN parser keeps unknown prose as a panel visual (lossless).
    gn_script = gnb.parse_graphic_novel_text(prose)
    assert "prose" in gnb.serialize_graphic_novel_script(gn_script).lower()
    # Screenplay parser normalizes unknown lines to action (never corrupts).
    blocks = sb.parse_screenplay_text(prose)
    assert blocks and "prose" in " ".join(b.text for b in blocks).lower()


# ==========================================================================
# 3  Mode-aware Logos actions (no cross-mode leakage)
# ==========================================================================


def test_logos_actions_are_mode_aware():
    from logosforge.logos.controller import LogosController
    db = Database()
    nv, sp, gn = _novel(db), _screenplay(db), _gn(db)
    ctl = LogosController(db)

    def names(pid_mode):
        return [a.name for a in ctl.available_actions("Manuscript", writing_mode=pid_mode)]

    novel_names = names("novel")
    screen_names = names("screenplay")
    gn_names = names("graphic_novel")

    assert not any(n.startswith(("sp_", "gn_")) for n in novel_names)
    assert any(n.startswith("sp_") for n in screen_names)
    assert not any(n.startswith("gn_") for n in screen_names)
    assert any(n.startswith("gn_") for n in gn_names)
    assert not any(n.startswith("sp_") for n in gn_names)


def test_deterministic_actions_never_call_llm():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def _boom(*a, **k):
        raise AssertionError("deterministic action must not call the LLM")

    db = Database()
    sp = _screenplay(db)
    gn = _gn(db)
    ss.create_scene(db, sp, act="Act I", chapter="Seq 1", title="S",
                    content="INT. X - DAY\n\nAction.")
    ss.create_scene(db, gn, act="Act I", chapter="Chapter 1", title="S",
                    content="PAGE 1\n\nPANEL 1\nVisual: In the room, x.")
    ctl = LogosController(db, provider_resolver=_boom, chat_fn=_boom)
    sp_ctx = build_logos_context(db, sp, section_name="Manuscript", current_scene_id=None)
    gn_ctx = build_logos_context(db, gn, section_name="Manuscript", current_scene_id=None)
    assert ctl.run(sp_ctx, "sp_continuity_check").ok
    assert ctl.run(gn_ctx, "gn_continuity_check").ok
    assert ctl.run(gn_ctx, "gn_review_dashboard").ok


# ==========================================================================
# 4  No image generation anywhere in the action registry
# ==========================================================================


def test_no_image_generation_actions_any_mode():
    from logosforge.logos import actions as A
    blob = " ".join(a.name + " " + a.label + " " + a.description
                    for a in A.list_actions()).lower()
    for banned in ("comfyui", "image generation", "image gen", "generate image",
                   "image prompt", "img2img", "txt2img", "stable diffusion",
                   "render image", " lora"):
        assert banned not in blob, banned


# ==========================================================================
# 5  Canonical structure across modes
# ==========================================================================


def test_canonical_structure_all_modes():
    db = Database()
    for mk in (_novel, _screenplay, _gn):
        pid = mk(db, mk.__name__ + "struct")
        b = ss.create_scene(db, pid, act="Act II", chapter="Chapter 2", title="B",
                            content="b").id
        a = ss.create_scene(db, pid, act="Act I", chapter="Chapter 1", title="A",
                            content="a").id
        db.reorder_scenes(pid, [a, b])
        assert ss.canonical_scene_order(db, pid) == [a, b]     # not creation order
        db.reorder_scenes(pid, [b, a])
        assert ss.canonical_scene_order(db, pid) == [b, a]


# ==========================================================================
# 6  Three-project isolation (Novel / Screenplay / Graphic Novel)
# ==========================================================================


def test_three_project_isolation(tmp_path):
    db = Database(str(tmp_path / "multi.db"))
    nv = _novel(db, "NV")
    sp = _screenplay(db, "SP")
    gn = _gn(db, "GN")
    nv_s = ss.create_scene(db, nv, act="Act I", chapter="Chapter 1", title="NVScene",
                           content="NOVEL_SENTINEL prose").id
    sp_s = ss.create_scene(db, sp, act="Act I", chapter="Seq 1", title="SPScene",
                           content="INT. SP - DAY\n\nSCREEN_SENTINEL action.").id
    gn_s = ss.create_scene(db, gn, act="Act I", chapter="Chapter 1", title="GNScene",
                           content="PAGE 1\n\nPANEL 1\nVisual: GN_SENTINEL panel.").id
    db.add_timeline_event(sp, sp_s)
    db.create_psyke_entry(nv, "NovelOnly", "character")
    note = db.create_note(gn, "GNNote", "gn note body")
    db.link_note_to_scene(getattr(note, "id", note), gn_s)

    # Scenes do not cross projects.
    assert [s.id for s in db.get_all_scenes(nv)] == [nv_s]
    assert [s.id for s in db.get_all_scenes(sp)] == [sp_s]
    assert [s.id for s in db.get_all_scenes(gn)] == [gn_s]
    # Timeline events, PSYKE, Notes are project-bound.
    assert db.get_timeline_event_ids(nv) in (set(), [], None) or sp_s not in db.get_timeline_event_ids(nv)
    assert all(getattr(e, "name", "") != "NovelOnly"
               for e in db.get_all_psyke_entries(sp))
    assert all(getattr(e, "name", "") != "NovelOnly"
               for e in db.get_all_psyke_entries(gn))
    assert len(db.get_all_notes(nv)) == 0 and len(db.get_all_notes(sp)) == 0
    assert len(db.get_all_notes(gn)) == 1


def test_project_switch_clears_review_dashboards(tmp_path):
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.graphic_novel_review_view import GraphicNovelReviewView
    db = Database(str(tmp_path / "multi.db"))
    gn_a = _gn(db, "GNA")
    ss.create_scene(db, gn_a, act="Act I", chapter="Chapter 1", title="OnlyAScene",
                    content="PAGE 1\n\nPANEL 1\nVisual: a panel.")
    gn_b = _gn(db, "GNB")
    win = MainWindow(db, gn_a)
    win._show_graphic_novel_review()
    assert isinstance(win.content_area, GraphicNovelReviewView)
    # The dashboard table lists scene titles (status roll-up, not body content).
    assert "OnlyAScene" in win.content_area.report_markdown()
    win._switch_project(gn_b)
    win._show_graphic_novel_review()
    assert "OnlyAScene" not in win.content_area.report_markdown()


# ==========================================================================
# 7  Export / report privacy
# ==========================================================================


def test_exports_and_reports_exclude_secrets():
    from logosforge.settings import get_manager
    from logosforge import graphic_novel_blocks as gnb
    from logosforge import graphic_novel_dashboard as gnd
    from logosforge.screenplay_review import build_screenplay_review
    db = Database()
    get_manager().set("ai_api_key", "SECRET_KEY_SENTINEL")
    gn = _gn(db)
    ss.create_scene(db, gn, act="Act I", chapter="Chapter 1", title="S",
                    content="PAGE 1\n\nPANEL 1\nVisual: In the room, x.")
    sp = _screenplay(db)
    ss.create_scene(db, sp, act="Act I", chapter="Seq 1", title="S",
                    content="INT. X - DAY\n\nAction.")
    texts = [
        gnb.export_project_markdown(db, gn),
        gnd.build_graphic_novel_review(db, gn).to_markdown(),
        build_screenplay_review(db, sp).to_markdown(),
    ]
    for t in texts:
        assert "SECRET_KEY_SENTINEL" not in t


# ==========================================================================
# 8  Assistant mode context is mode-aware
# ==========================================================================


def test_assistant_context_is_mode_aware():
    from logosforge.assistant_context_policy import _project_mode_block
    db = Database()
    nv, sp, gn = _novel(db), _screenplay(db), _gn(db)
    assert "Novel" in _project_mode_block(db, nv)
    assert "Screenplay" in _project_mode_block(db, sp)
    gn_block = _project_mode_block(db, gn)
    assert "Graphic" in gn_block or "graphic" in gn_block.lower()


def test_writing_mode_source_of_truth():
    db = Database()
    nv, sp, gn = _novel(db), _screenplay(db), _gn(db)
    assert get_project_writing_mode_by_id(db, nv) == NOVEL
    assert get_project_writing_mode_by_id(db, sp) == SCREENPLAY
    assert get_project_writing_mode_by_id(db, gn) == GRAPHIC_NOVEL
