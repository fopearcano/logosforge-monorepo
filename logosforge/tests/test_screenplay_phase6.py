"""Screenplay Mode — Phase 6 acceptance suite.

Controlled rewrite: targeted revision request → preview (with block diff +
validation) → confirmed apply. The AI never overwrites the body; apply requires
confirmation, touches only Scene.content, and preserves Outline/beat plan/
Timeline/PSYKE/Notes.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import screenplay_pipeline as spp
from logosforge import screenplay_rewrite as srw


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
    return db.create_project("S", narrative_engine="screenplay",
                             default_writing_format="screenplay").id


_CONTENT = ("INT. KITCHEN - NIGHT\n\nMaria stands.\n\n"
            "MARIA\nHello.\n\nJOHN\nGo away.")
_GOOD = ("INT. KITCHEN - NIGHT\n\nMaria slams the drawer shut.\n\n"
         "MARIA\nLook at me.\n\nJOHN\nNo.")


def _scene(db, pid, *, content=_CONTENT, summary="Maria pushes John"):
    sid = ss.create_scene(db, pid, act="Act I", chapter="Seq 1",
                          title="Confront", content=content, summary=summary).id
    return sid


# ==========================================================================
# 1-5  Rewrite request
# ==========================================================================


def test_request_includes_scene_context():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid)
    req = srw.build_rewrite_request(db, pid, sid, instruction="make_more_visual")
    assert req.scene_title == "Confront"
    assert "Maria pushes John" in req.outline_summary
    assert req.original_body == _CONTENT
    assert req.writing_mode == "screenplay"


def test_request_includes_beat_plan_when_available():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid)
    spp.save_beat_plan(db, pid, spp.ScreenplayBeatPlan(scene_id=sid, objective="get John to talk"))
    req = srw.build_rewrite_request(db, pid, sid)
    assert "get John to talk" in req.beat_plan_text


def test_request_includes_counterpart_report():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid)
    req = srw.build_rewrite_request(db, pid, sid, instruction="from_counterpart")
    assert "Internal Character Perspective" in req.counterpart_text


def test_request_includes_selected_text():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid)
    req = srw.build_rewrite_request(db, pid, sid, selected_text="MARIA\nHello.",
                                    target=srw.TARGET_SELECTION)
    assert req.selected_text == "MARIA\nHello." and req.target == srw.TARGET_SELECTION


def test_request_excludes_api_keys():
    db = Database()
    from logosforge.settings import get_manager
    get_manager().set("ai_api_key", "SECRET_KEY_SENTINEL")
    pid = _screenplay(db)
    sid = _scene(db, pid)
    req = srw.build_rewrite_request(db, pid, sid, instruction="from_counterpart")
    blob = str(req.to_dict()) + srw.build_rewrite_prompt(req)
    assert "SECRET_KEY_SENTINEL" not in blob
    assert not any("api" in k.lower() or "secret" in k.lower() or k.lower() == "key"
                   for k in req.to_dict())


# ==========================================================================
# 6-10  Output parsing + validation
# ==========================================================================


def test_valid_block_output_parses():
    blocks = srw.parse_rewrite_output(_GOOD)
    kinds = [b.element_type for b in blocks]
    assert kinds == ["scene_heading", "action", "character", "dialogue",
                     "character", "dialogue"]


def test_plain_text_output_adapts_or_validates():
    blocks = srw.parse_rewrite_output("Maria crosses the room and opens the window.")
    assert blocks and all(b.element_type == "action" for b in blocks)
    assert srw.validate_rewrite_output(blocks, target=srw.TARGET_BLOCK).is_valid


def test_markdown_fences_are_cleaned():
    blocks = srw.parse_rewrite_output("```fountain\nINT. X - DAY\n\nAction.\n```")
    assert srw.validate_rewrite_output(blocks).is_valid
    assert all("```" not in b.text for b in blocks)


def test_unknown_block_type_degrades_safely():
    from logosforge.screenplay_blocks import ScreenplayBlock
    b = ScreenplayBlock("not_a_type", "Some line.")
    assert b.element_type == "action"            # normalized — never corrupt
    assert srw.validate_rewrite_output([b]).is_valid


def test_system_prompt_leakage_is_rejected():
    blocks = srw.parse_rewrite_output(
        "As an AI language model, here is the screenplay you requested.")
    v = srw.validate_rewrite_output(blocks)
    assert not v.is_valid and v.errors


# ==========================================================================
# 11-15  Preview
# ==========================================================================


def test_preview_does_not_mutate_body():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid)
    srw.build_rewrite_preview(db, pid, sid, srw.parse_rewrite_output(_GOOD))
    assert db.get_scene_by_id(sid).content == _CONTENT


def test_preview_shows_original_and_proposed():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid)
    prev = srw.build_rewrite_preview(db, pid, sid, srw.parse_rewrite_output(_GOOD))
    assert prev.original_text == _CONTENT
    assert "slams the drawer" in prev.proposed_text
    assert prev.block_diff and "changed" in prev.block_diff


def test_preview_surfaces_validation_warnings():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid)
    # Whole-scene rewrite that drops the heading -> a warning (still applicable).
    prev = srw.build_rewrite_preview(
        db, pid, sid, srw.parse_rewrite_output("Maria leaves without a word."),
        target=srw.TARGET_SCENE)
    assert prev.can_apply and prev.warnings


def test_cancel_leaves_body_unchanged():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid)
    res = srw.apply_rewrite(db, pid, sid, srw.parse_rewrite_output(_GOOD),
                            mode=srw.MODE_CANCEL, confirmed=True)
    assert res["ok"] is False and res.get("cancelled")
    assert db.get_scene_by_id(sid).content == _CONTENT


def test_copy_only_leaves_body_unchanged():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid)
    res = srw.apply_rewrite(db, pid, sid, srw.parse_rewrite_output(_GOOD),
                            mode=srw.MODE_COPY_ONLY, confirmed=True)
    assert res["ok"] and res["mutated"] is False
    assert db.get_scene_by_id(sid).content == _CONTENT


# ==========================================================================
# 16-25  Apply
# ==========================================================================


def test_apply_selected_block_replaces_only_that_block():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid)
    new = srw.parse_rewrite_output("Maria hurls the glass at the wall.")
    res = srw.apply_rewrite(db, pid, sid, new, target=srw.TARGET_BLOCK,
                            target_block_indices=[1], mode=srw.MODE_REPLACE,
                            confirmed=True)
    body = db.get_scene_by_id(sid).content
    assert res["ok"]
    assert "hurls the glass" in body
    assert "INT. KITCHEN" in body and "Go away" in body      # rest preserved
    assert "Maria stands" not in body


def test_full_scene_replace_requires_confirmation():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid)
    res = srw.apply_rewrite(db, pid, sid, srw.parse_rewrite_output(_GOOD),
                            mode=srw.MODE_REPLACE, confirmed=False)
    assert res["ok"] is False
    assert db.get_scene_by_id(sid).content == _CONTENT


def test_append_alternate_does_not_overwrite_original():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid)
    res = srw.apply_rewrite(db, pid, sid, srw.parse_rewrite_output(_GOOD),
                            mode=srw.MODE_APPEND_ALTERNATE, confirmed=True)
    body = db.get_scene_by_id(sid).content
    assert res["ok"]
    assert body.startswith("INT. KITCHEN - NIGHT") and "Maria stands" in body
    assert "slams the drawer" in body


def test_apply_emits_project_data_changed():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid)
    from logosforge.project_events import get_event_bus
    fired = []
    get_event_bus().project_data_changed.connect(lambda *a: fired.append(1))
    srw.apply_rewrite(db, pid, sid, srw.parse_rewrite_output(_GOOD),
                      mode=srw.MODE_REPLACE, confirmed=True)
    assert fired                                  # marks the project dirty


def test_apply_preserves_outline_summary():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, summary="SUMMARY_KEPT")
    srw.apply_rewrite(db, pid, sid, srw.parse_rewrite_output(_GOOD),
                      mode=srw.MODE_REPLACE, confirmed=True)
    assert db.get_scene_by_id(sid).summary == "SUMMARY_KEPT"


def test_apply_preserves_beat_plan():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid)
    spp.save_beat_plan(db, pid, spp.ScreenplayBeatPlan(scene_id=sid, objective="KEEP_OBJECTIVE"))
    srw.apply_rewrite(db, pid, sid, srw.parse_rewrite_output(_GOOD),
                      mode=srw.MODE_REPLACE, confirmed=True)
    assert spp.get_beat_plan(db, pid, sid).objective == "KEEP_OBJECTIVE"


def test_apply_preserves_timeline_events():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, content="INT. X - DAY\n\nMaria waits.", summary="s")
    db.add_timeline_event(pid, sid)
    before = db.get_timeline_event_ids(pid)
    srw.apply_rewrite(db, pid, sid, srw.parse_rewrite_output(_GOOD),
                      mode=srw.MODE_REPLACE, confirmed=True)
    assert db.get_timeline_event_ids(pid) == before


def test_apply_preserves_psyke_data():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid)
    db.create_psyke_entry(pid, "Maria", "character")
    before = len(db.get_all_psyke_entries(pid))
    srw.apply_rewrite(db, pid, sid, srw.parse_rewrite_output(_GOOD),
                      mode=srw.MODE_REPLACE, confirmed=True)
    assert len(db.get_all_psyke_entries(pid)) == before == 1


def test_apply_preserves_notes():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid)
    db.create_note(pid, "Keep me", "note body")
    before = len(db.get_all_notes(pid))
    srw.apply_rewrite(db, pid, sid, srw.parse_rewrite_output(_GOOD),
                      mode=srw.MODE_REPLACE, confirmed=True)
    assert len(db.get_all_notes(pid)) == before


# ==========================================================================
# 26-29  Logos
# ==========================================================================


def test_logos_dropdown_includes_rewrite_actions():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("S", narrative_engine="screenplay")
    names = [a.name for a in
             LogosController(db).available_actions("Manuscript", writing_mode="screenplay")]
    assert "sp_rewrite_from_counterpart" in names
    assert "rewrite_options" in names              # existing "Rewrite Selection"


def test_rewrite_selection_requires_selected_text():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid)
    ctl = LogosController(db, provider_resolver=lambda: object(),
                          chat_fn=lambda m, p: "x")
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "rewrite_options")          # needs_selection
    assert not res.ok and "Select some text" in (res.error or "")


def test_full_scene_rewrite_action_runs_without_selection():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    calls = []
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid)
    ctl = LogosController(db, provider_resolver=lambda: object(),
                          chat_fn=lambda m, p: calls.append(1) or "INT. X - DAY\n\nNew.")
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "sp_rewrite_from_counterpart")    # no selection
    assert res.ok and calls == [1]
    assert db.get_scene_by_id(sid).content == _CONTENT   # not auto-applied


def test_logos_rewrite_does_not_auto_apply():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid)
    ctl = LogosController(db, provider_resolver=lambda: object(),
                          chat_fn=lambda m, p: "INT. X - DAY\n\nRewritten action.")
    ctx = build_logos_context(db, pid, section_name="Manuscript",
                              current_scene_id=sid, selected_text="Maria stands.")
    res = ctl.run(ctx, "sp_rewrite_from_counterpart")
    # Result carries preview-only proposed operations; nothing is applied.
    assert res.ok
    assert db.get_scene_by_id(sid).content == _CONTENT


# ==========================================================================
# 30-32  Assistant / provider-error safety
# ==========================================================================


def test_assistant_rewrite_produces_preview_without_mutation():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid)
    # The Assistant flow: request -> (LLM) -> parse -> preview (no mutation).
    req = srw.build_rewrite_request(db, pid, sid, instruction="make_more_visual")
    blocks = srw.parse_rewrite_output(_GOOD, scene_id=sid)
    prev = srw.build_rewrite_preview(db, pid, sid, blocks)
    assert prev.proposed_text and db.get_scene_by_id(sid).content == _CONTENT


def test_assistant_does_not_mutate_before_confirmation():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid)
    res = srw.apply_rewrite(db, pid, sid, srw.parse_rewrite_output(_GOOD),
                            mode=srw.MODE_REPLACE, confirmed=False)
    assert res["ok"] is False and db.get_scene_by_id(sid).content == _CONTENT


def test_provider_error_does_not_mutate():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid)
    # Simulate a failed/empty generation: empty output -> invalid -> apply blocked.
    empty_blocks = srw.parse_rewrite_output("")
    res = srw.apply_rewrite(db, pid, sid, empty_blocks, mode=srw.MODE_REPLACE,
                            confirmed=True)
    assert res["ok"] is False
    assert db.get_scene_by_id(sid).content == _CONTENT


# ==========================================================================
# Dialog + isolation
# ==========================================================================


def test_rewrite_dialog_gates_apply_on_validity():
    from logosforge.ui.screenplay_rewrite_dialog import RewritePreviewDialog
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid)
    ok_prev = srw.build_rewrite_preview(db, pid, sid, srw.parse_rewrite_output(_GOOD))
    dlg = RewritePreviewDialog(ok_prev)
    assert dlg._replace_btn.isEnabled()
    dlg._choose(srw.MODE_APPEND_ALTERNATE)
    assert dlg.chosen_mode() == srw.MODE_APPEND_ALTERNATE
    bad_prev = srw.build_rewrite_preview(
        db, pid, sid, srw.parse_rewrite_output("As an AI, I cannot."))
    bad = RewritePreviewDialog(bad_prev)
    assert not bad._replace_btn.isEnabled() and not bad._append_btn.isEnabled()


def test_manuscript_editor_has_rewrite_hook(tmp_path):
    from logosforge.ui.writing_core_view import WritingCoreView
    db = Database(str(tmp_path / "sp.db"))
    pid = _screenplay(db)
    _scene(db, pid)
    view = WritingCoreView(db, pid, structured_list=True)
    ed = next(iter(view._editors.values()))
    assert ed._screenplay_mode is True and ed._on_rewrite_scene is not None


def test_rewrite_isolated_across_projects(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    a = _screenplay(db)
    sid_a = _scene(db, a)
    b = _screenplay(db)
    sid_b = _scene(db, b, content="INT. B - DAY\n\nBob waits.")
    srw.apply_rewrite(db, b, sid_b, srw.parse_rewrite_output("INT. B - DAY\n\nBob runs."),
                      mode=srw.MODE_REPLACE, confirmed=True)
    assert db.get_scene_by_id(sid_a).content == _CONTENT      # project A untouched
