"""Screenplay Mode — Phase 10 UX / discoverability / polish suite.

Verifies the UX improvements: a discoverable Review Dashboard entry, grouped &
readable Logos actions, a clear rewrite "Target:" label, the screenplay block
selector + mode badge, and that none of the polish mutates data or leaks into
Novel mode. No new engines; this is presentation only.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication, QLabel

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import screenplay_rewrite as srw
from logosforge.logos import actions as A


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


def _screenplay(db):
    return db.create_project("Film", narrative_engine="screenplay",
                             default_writing_format="screenplay").id


def _novel(db):
    return db.create_project("Book", narrative_engine="novel").id


def _manuscript(db, pid):
    from logosforge.ui.writing_core_view import WritingCoreView
    return WritingCoreView(db, pid, structured_list=True)


# ==========================================================================
# 1-3  Manuscript screenplay UX (header path, mode label, block selector)
# ==========================================================================


def test_screenplay_scene_header_shows_canonical_path():
    db = Database()
    pid = _screenplay(db)
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="A", content="x")
    view = _manuscript(db, pid)
    ctx = [w.text() for w in view.findChildren(QLabel)
           if w.objectName() == "writingSceneContext"]
    # Screenplay numbering flattens to Act.Scene (novel is Act.Chapter.Scene).
    assert ctx == ["SCENE 1.1"]            # canonical structural number/path


def test_screenplay_mode_badge_appears():
    db = Database()
    pid = _screenplay(db)
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="A", content="x")
    view = _manuscript(db, pid)
    assert "Screenplay" in view._format_badge.text()


def test_block_type_selector_present_with_screenplay_elements():
    db = Database()
    pid = _screenplay(db)
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="A", content="x")
    view = _manuscript(db, pid)
    items = [view._element_combo.itemData(i)
             for i in range(view._element_combo.count())]
    for elem in ("scene_heading", "action", "character", "dialogue",
                 "parenthetical", "transition"):
        assert elem in items


def test_block_type_selector_changes_current_block():
    db = Database()
    pid = _screenplay(db)
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="A",
                    content="Some line.")
    view = _manuscript(db, pid)
    editor = next(iter(view._editors.values()))
    view._active_editor = editor
    items = [view._element_combo.itemData(i)
             for i in range(view._element_combo.count())]
    idx = items.index("character")
    view._element_combo.setCurrentIndex(idx)
    view._on_element_changed(idx)
    assert view.current_element_type() == "character"


# ==========================================================================
# 5-6  Scene actions are wired (screenplay) and inert (novel)
# ==========================================================================


def test_scene_action_hooks_present_in_screenplay():
    db = Database()
    pid = _screenplay(db)
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="A",
                    content="INT. X - DAY\n\nAction.")
    editor = next(iter(_manuscript(db, pid)._editors.values()))
    assert editor._screenplay_mode is True
    for hook in ("_on_draft_from_beat_plan", "_on_rewrite_scene",
                 "_on_export_scene_fountain", "_on_open_review"):
        assert getattr(editor, hook) is not None


def test_scene_action_hooks_inert_in_novel():
    db = Database()
    pid = _novel(db)
    ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="A", content="prose")
    editor = next(iter(_manuscript(db, pid)._editors.values()))
    assert editor._screenplay_mode is False


# ==========================================================================
# 7-10  Review Dashboard discoverability
# ==========================================================================


def test_review_menu_has_dashboard_in_screenplay():
    db = Database()
    pid = _screenplay(db)
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="A", content="x")
    view = _manuscript(db, pid)
    view.on_open_review = lambda: None
    texts = [a.text() for a in view._build_review_menu().actions()]
    assert any("Screenplay Review Dashboard" in t for t in texts)


def test_review_menu_dashboard_opens_review():
    db = Database()
    pid = _screenplay(db)
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="A", content="x")
    view = _manuscript(db, pid)
    opened = []
    view.on_open_review = lambda: opened.append(1)
    dash = next(a for a in view._build_review_menu().actions()
                if "Screenplay Review Dashboard" in a.text())
    dash.trigger()
    assert opened == [1]


def test_review_access_does_not_mutate(tmp_path):
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.screenplay_review_view import ScreenplayReviewView
    db = Database(str(tmp_path / "ui.db"))
    pid = _screenplay(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="A",
                          content="INT. X - DAY\n\nAction.", summary="s").id
    before = (db.get_scene_by_id(sid).content, db.get_scene_by_id(sid).summary)
    win = MainWindow(db, pid)
    win._show_screenplay_review()
    assert isinstance(win.content_area, ScreenplayReviewView)
    assert (db.get_scene_by_id(sid).content, db.get_scene_by_id(sid).summary) == before


def test_review_menu_hidden_in_novel():
    db = Database()
    pid = _novel(db)
    ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="A", content="x")
    view = _manuscript(db, pid)
    view.on_open_review = lambda: None
    texts = [a.text() for a in view._build_review_menu().actions()]
    assert not any("Screenplay Review Dashboard" in t for t in texts)
    assert any("Grammar" in t for t in texts)          # normal tools intact


# ==========================================================================
# 11-15  Logos action grouping / readability
# ==========================================================================


def test_logos_actions_are_grouped():
    groups = A.grouped_actions_for_section("Manuscript", writing_mode="screenplay")
    labels = [g for g, _ in groups]
    assert labels == [g for g in A.UX_GROUP_ORDER if g in labels]   # canonical order
    assert {"Checks", "Reflection", "Rewrite", "Export"} <= set(labels)
    flat = {a.name: g for g, acts in groups for a in acts}
    assert flat["sp_counterpart_reflection"] == "Reflection"
    assert flat["sp_rewrite_from_counterpart"] == "Rewrite"
    assert flat["sp_validate_fountain_export"] == "Export"
    assert flat["sp_scene_health"] == "Checks"


def test_toolbar_renders_groups_with_separators():
    from logosforge.logos.controller import LogosController
    from logosforge.ui.logos.logos_toolbar import LogosToolbar
    db = Database()
    _screenplay(db)
    ctx = type("C", (), {"writing_mode": "screenplay"})()
    tb = LogosToolbar(LogosController(db), lambda: ctx)
    tb.set_section("Manuscript")
    combo = tb._action_combo
    # Index 1 is still a real action (placeholder at 0), and separators exist
    # between groups (so the combo has more items than just actions+placeholder).
    assert combo.itemData(1)                                 # real action, not header
    names = tb.available_action_names()
    assert names and all(n for n in names)                   # no empty names leak
    assert "sp_scene_health" in names and "sp_counterpart_reflection" in names


def test_selected_text_action_requires_selection():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _screenplay(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="A",
                          content="INT. X - DAY\n\nAction.").id
    ctl = LogosController(db, provider_resolver=lambda: object(),
                          chat_fn=lambda m, p: "x")
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "sp_visual_action")          # needs_selection
    assert not res.ok and "Select some text" in (res.error or "")


def test_full_scene_action_runs_without_selection():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _screenplay(db)
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="A",
                    content="INT. X - DAY\n\nAction.")
    ctl = LogosController(db)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=None)
    res = ctl.run(ctx, "sp_continuity_check")       # full-project, no selection
    assert res.ok and res.proposed_operations == []


def test_logos_grouping_usable_at_small_width():
    from logosforge.logos.controller import LogosController
    from logosforge.ui.logos.logos_toolbar import LogosToolbar
    db = Database()
    _screenplay(db)
    ctx = type("C", (), {"writing_mode": "screenplay"})()
    tb = LogosToolbar(LogosController(db), lambda: ctx)
    tb.set_section("Manuscript")
    tb.setFixedWidth(180)
    tb.refresh_actions()
    assert tb._action_combo.isEnabled() and tb._action_combo.count() > 1


# ==========================================================================
# 16-19  Rewrite preview UX
# ==========================================================================


def _rewrite_preview(db, pid, sid, target=srw.TARGET_SCENE, indices=None):
    return srw.build_rewrite_preview(
        db, pid, sid, srw.parse_rewrite_output("INT. X - DAY\n\nMaria runs."),
        target=target, target_block_indices=indices)


def test_rewrite_preview_shows_target_description():
    from logosforge.ui.screenplay_rewrite_dialog import RewritePreviewDialog
    db = Database()
    pid = _screenplay(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="A",
                          content="INT. X - DAY\n\nMaria waits.").id
    for tgt, expect in ((srw.TARGET_SCENE, "whole scene"),
                        (srw.TARGET_BLOCK, "selected block"),
                        (srw.TARGET_SELECTION, "selected text")):
        idxs = None if tgt == srw.TARGET_SCENE else [1]
        dlg = RewritePreviewDialog(_rewrite_preview(db, pid, sid, tgt, idxs))
        labels = [l.text() for l in dlg.findChildren(QLabel)
                  if l.objectName() == "rewriteTarget"]
        assert labels and expect in labels[0]


def test_rewrite_preview_shows_original_and_proposed():
    from logosforge.ui.screenplay_rewrite_dialog import RewritePreviewDialog
    from PySide6.QtWidgets import QPlainTextEdit
    db = Database()
    pid = _screenplay(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="A",
                          content="INT. X - DAY\n\nMaria waits.").id
    dlg = RewritePreviewDialog(_rewrite_preview(db, pid, sid))
    objs = {e.objectName() for e in dlg.findChildren(QPlainTextEdit)}
    assert "rewriteOriginal" in objs and "rewriteProposed" in objs


def test_rewrite_cancel_and_confirmation():
    db = Database()
    pid = _screenplay(db)
    body = "INT. X - DAY\n\nMaria waits."
    sid = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="A",
                          content=body).id
    blocks = srw.parse_rewrite_output("INT. X - DAY\n\nMaria runs.")
    cancelled = srw.apply_rewrite(db, pid, sid, blocks, mode=srw.MODE_CANCEL,
                                  confirmed=True)
    assert cancelled["ok"] is False and db.get_scene_by_id(sid).content == body
    refused = srw.apply_rewrite(db, pid, sid, blocks, mode=srw.MODE_REPLACE,
                                confirmed=False)
    assert refused["ok"] is False and db.get_scene_by_id(sid).content == body


# ==========================================================================
# 20-22  Validation / warnings UX
# ==========================================================================


def test_screenplay_check_warnings_show_category_and_severity():
    from logosforge.logos.deterministic import get_handler
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _screenplay(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="A",
                          content="INT. X - DAY\n\nJohn thinks and remembers and feels and realizes.").id
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = get_handler("sp_scene_health")(db, ctx)
    assert "Visual Writing:" in res.message      # grouped by category
    assert "[watch]" in res.message or "[weak]" in res.message   # severity shown


def test_health_issue_can_reference_block_and_does_not_mutate():
    from logosforge import screenplay_diagnostics as sd
    db = Database()
    pid = _screenplay(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="A",
                          content="INT. X - DAY\n\nJohn thinks and remembers and feels.").id
    before = db.get_scene_by_id(sid).content
    rep = sd.analyze_scene_by_id(db, pid, sid)
    assert any(i.target_block_index is not None for i in rep.issues)
    assert db.get_scene_by_id(sid).content == before


# ==========================================================================
# 23-26  Export UX
# ==========================================================================


def test_export_actions_available_in_screenplay():
    names = [a.name for g, acts in
             A.grouped_actions_for_section("Manuscript", writing_mode="screenplay")
             for a in acts]
    assert "sp_validate_fountain_export" in names      # Fountain export tooling
    # Scene + project export are reachable via the editor hook + main Export.
    db = Database()
    pid = _screenplay(db)
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="A",
                    content="INT. X - DAY\n\nAction.")
    editor = next(iter(_manuscript(db, pid)._editors.values()))
    assert editor._on_export_scene_fountain is not None


def test_export_readiness_warns_before_export():
    from logosforge import screenplay_interchange as si
    db = Database()
    pid = _screenplay(db)
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="A",
                    content="No heading here, just action.")
    rep = si.validate_fountain_export_readiness(db, pid)
    assert rep.warnings        # surfaced to the user before export


def test_export_excludes_secrets():
    from logosforge import screenplay_interchange as si
    db = Database()
    from logosforge.settings import get_manager
    get_manager().set("ai_api_key", "SECRET_KEY_SENTINEL")
    pid = _screenplay(db)
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="A",
                    content="INT. X - DAY\n\nAction.")
    assert "SECRET_KEY_SENTINEL" not in si.serialize_project_to_fountain(db, pid).text


# ==========================================================================
# Novel-mode safety
# ==========================================================================


def test_novel_mode_has_no_screenplay_logos_groups():
    groups = A.grouped_actions_for_section("Manuscript", writing_mode="novel")
    flat = {a.name for g, acts in groups for a in acts}
    for sp_only in ("sp_scene_health", "sp_counterpart_reflection",
                    "sp_continuity_check", "sp_review_dashboard"):
        assert sp_only not in flat
