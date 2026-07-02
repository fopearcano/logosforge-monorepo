"""Screenplay Mode — Phase 4 acceptance suite.

Fountain interchange: scene + project export (canonical order, contamination-
free, file writing), pre-export validation, and a safe import foundation
(parser → grouped scenes → preview → confirmed apply, Act→Chapter→Scene safe).

Deterministic; no LLM. All apply paths require explicit confirmation and never
overwrite an existing body unconfirmed.
"""

from __future__ import annotations

import os
import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import screenplay_interchange as si
from logosforge.screenplay_blocks import ScreenplayBlock
from logosforge.screenplay_fountain import (
    FountainExportOptions, serialize_screenplay_to_fountain,
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


def _screenplay(db):
    return db.create_project("S", narrative_engine="screenplay",
                             default_writing_format="screenplay").id


def _novel(db):
    return db.create_project("N", narrative_engine="novel").id


def _fountain(blocks):
    return serialize_screenplay_to_fountain(
        blocks, options=FountainExportOptions(include_title_page=False)).text


# ==========================================================================
# 1-8  Format mapping (the serializer scene export delegates to)
# ==========================================================================


def test_scene_heading_exports():
    assert "INT. HOUSE - DAY" in _fountain(
        [ScreenplayBlock("scene_heading", "INT. HOUSE - DAY")])


def test_action_exports():
    assert "John opens the door." in _fountain(
        [ScreenplayBlock("action", "John opens the door.")])


def test_character_exports_uppercase():
    assert "JOHN" in _fountain([ScreenplayBlock("character", "john")])


def test_dialogue_exports_under_character():
    out = _fountain([ScreenplayBlock("character", "JOHN"),
                     ScreenplayBlock("dialogue", "Hello.")])
    assert out.index("JOHN") < out.index("Hello.")


def test_parenthetical_exports_with_parentheses():
    out = _fountain([ScreenplayBlock("character", "JOHN"),
                     ScreenplayBlock("parenthetical", "softly"),
                     ScreenplayBlock("dialogue", "Hi.")])
    assert "(softly)" in out


def test_transition_exports():
    assert "CUT TO:" in _fountain([ScreenplayBlock("transition", "cut to:")])


def test_shot_exports():
    assert "ANGLE ON DOOR" in _fountain([ScreenplayBlock("shot", "angle on door")])


def test_unknown_block_handled_safely():
    # Unknown type degrades to action (never a corrupt type in the output).
    b = ScreenplayBlock("not_a_type", "Some line.")
    assert b.element_type == "action"
    assert "Some line." in _fountain([b])


# ==========================================================================
# 9-15  Project export — order + contamination-free
# ==========================================================================


def _two_scene_project(db):
    pid = _screenplay(db)
    b = ss.create_scene(db, pid, act="Act II", chapter="Seq 2", title="Beta",
                        content="INT. BETA - DAY\n\nBeta action.").id
    a = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="Alpha",
                        content="INT. ALPHA - DAY\n\nAlpha action.").id
    db.reorder_scenes(pid, [a, b])
    return pid, a, b


def test_full_export_follows_canonical_order():
    db = Database()
    pid, a, b = _two_scene_project(db)
    text = si.serialize_project_to_fountain(db, pid).text
    assert text.index("ALPHA") < text.index("BETA")


def test_moved_scene_exports_in_updated_order():
    db = Database()
    pid, a, b = _two_scene_project(db)
    db.reorder_scenes(pid, [b, a])           # move Beta first
    text = si.serialize_project_to_fountain(db, pid).text
    assert text.index("BETA") < text.index("ALPHA")


def test_empty_scene_handling_follows_option():
    db = Database()
    pid = _screenplay(db)
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="Real",
                    content="INT. REAL - DAY\n\nReal action.")
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1",
                    title="EmptyPlanning", content="")
    with_empty = si.serialize_project_to_fountain(db, pid,
                                                  include_empty_scenes=True).text
    without_empty = si.serialize_project_to_fountain(db, pid,
                                                     include_empty_scenes=False).text
    assert "EMPTYPLANNING" in with_empty            # heading stub present
    assert "EMPTYPLANNING" not in without_empty       # skipped
    assert "Real action." in without_empty            # real scene kept


def test_outline_summaries_not_exported_as_body():
    db = Database()
    pid = _screenplay(db)
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="S",
                    content="INT. HOUSE - DAY\n\nReal action.",
                    summary="OUTLINE_SUMMARY_SENTINEL")
    text = si.serialize_project_to_fountain(db, pid).text
    assert "Real action." in text
    assert "OUTLINE_SUMMARY_SENTINEL" not in text


def test_timeline_notes_not_exported_as_body():
    db = Database()
    pid = _screenplay(db)
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="S",
                    content="INT. HOUSE - DAY\n\nReal action.")
    db.create_timeline_lane(pid, "TIMELINE_LANE_SENTINEL", "green")
    text = si.serialize_project_to_fountain(db, pid).text
    assert "TIMELINE_LANE_SENTINEL" not in text


def test_psyke_metadata_not_exported_as_body():
    db = Database()
    pid = _screenplay(db)
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="S",
                    content="INT. HOUSE - DAY\n\nReal action.")
    db.create_psyke_entry(pid, "PSYKE_SECRET_SENTINEL", "character")
    text = si.serialize_project_to_fountain(db, pid).text
    assert "PSYKE_SECRET_SENTINEL" not in text


def test_api_keys_never_exported():
    db = Database()
    from logosforge.settings import get_manager
    get_manager().set("ai_api_key", "SECRET_API_KEY_SENTINEL")
    pid = _screenplay(db)
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="S",
                    content="INT. HOUSE - DAY\n\nReal action.")
    text = si.serialize_project_to_fountain(db, pid).text
    assert "SECRET_API_KEY_SENTINEL" not in text


# ==========================================================================
# Scene export + file writing
# ==========================================================================


def test_serialize_scene_only_that_scene(tmp_path):
    db = Database()
    pid, a, b = _two_scene_project(db)
    text = si.serialize_scene_to_fountain(db, pid, a).text
    assert "ALPHA" in text and "BETA" not in text


def test_export_scene_and_project_write_files(tmp_path):
    db = Database()
    pid, a, b = _two_scene_project(db)
    sc = si.export_scene_fountain(db, pid, a, str(tmp_path / "scene"))
    assert sc["ok"] and sc["path"].endswith(".fountain") and os.path.exists(sc["path"])
    pr = si.export_project_fountain(db, pid, str(tmp_path / "proj.fountain"))
    assert pr["ok"] and os.path.exists(pr["path"])
    body = open(pr["path"], encoding="utf-8").read()
    assert body.index("ALPHA") < body.index("BETA")


# ==========================================================================
# 16-20  Pre-export validation
# ==========================================================================


def test_missing_scene_heading_warns():
    db = Database()
    pid = _screenplay(db)
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="NoHead",
                    content="Just an action line with no heading.")
    rep = si.validate_fountain_export_readiness(db, pid)
    assert any("scene heading" in w.lower() for w in rep.warnings)


def test_dialogue_without_character_warns():
    rep = si.validate_export_blocks([ScreenplayBlock("action", "Beat."),
                                     ScreenplayBlock("dialogue", "Orphan line.")])
    assert any("without a character" in w for w in rep.warnings)


def test_parenthetical_orphan_warns():
    rep = si.validate_export_blocks([ScreenplayBlock("action", "Beat."),
                                     ScreenplayBlock("parenthetical", "(softly)")])
    assert any("parenthetical" in w.lower() for w in rep.warnings)


def test_unknown_block_type_handled_as_warning_or_safe():
    # Unknown degrades to action; export still safe (no corrupt type).
    rep = si.validate_export_blocks([ScreenplayBlock("scene_heading", "INT. X - DAY"),
                                     ScreenplayBlock("???", "Mystery.")])
    assert rep.is_ready  # safe — degraded, not corrupt
    # Markdown-fence leak is surfaced as a warning.
    rep2 = si.validate_export_blocks([ScreenplayBlock("action", "```fountain")])
    assert any("code fence" in w.lower() for w in rep2.warnings)


def test_outline_summary_in_body_warns():
    db = Database()
    pid = _screenplay(db)
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="Bad",
                    content="INT. X - DAY\n\nAction.\n\nLEAKED SUMMARY TEXT HERE",
                    summary="LEAKED SUMMARY TEXT HERE")
    rep = si.validate_fountain_export_readiness(db, pid)
    assert any("Outline summary" in w for w in rep.warnings)


def test_validation_does_not_mutate_project():
    db = Database()
    pid = _screenplay(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="S",
                          content="INT. X - DAY\n\nAction.", summary="keep").id
    before = (db.get_scene_by_id(sid).content, db.get_scene_by_id(sid).summary)
    si.validate_fountain_export_readiness(db, pid)
    after = (db.get_scene_by_id(sid).content, db.get_scene_by_id(sid).summary)
    assert before == after


def test_empty_project_export_not_ready():
    db = Database()
    pid = _screenplay(db)
    rep = si.validate_fountain_export_readiness(db, pid)
    assert not rep.is_ready and rep.blocking_errors


# ==========================================================================
# 21-28  Import parser + preview
# ==========================================================================

_IMPORT_TEXT = (
    "Title: My Script\n\n"
    "INT. KITCHEN - NIGHT\n\n"
    "She enters and freezes.\n\n"
    "MARY\n(softly)\nIs anyone home?\n\n"
    "CUT TO:\n\n"
    "EXT. STREET - DAY\n\n"
    "He runs."
)


def test_parser_detects_scene_headings():
    prev = si.parse_fountain_to_scenes(_IMPORT_TEXT)
    headings = [s.heading.upper() for s in prev.scenes]
    assert any(h.startswith("INT. KITCHEN") for h in headings)
    assert any(h.startswith("EXT. STREET") for h in headings)


def test_parser_detects_action():
    prev = si.parse_fountain_to_scenes(_IMPORT_TEXT)
    kinds = [b.element_type for b in prev.scenes[0].blocks]
    assert "action" in kinds


def test_parser_detects_character_and_dialogue():
    prev = si.parse_fountain_to_scenes(_IMPORT_TEXT)
    kinds = [b.element_type for b in prev.scenes[0].blocks]
    assert "character" in kinds and "dialogue" in kinds


def test_parser_detects_parenthetical():
    prev = si.parse_fountain_to_scenes(_IMPORT_TEXT)
    kinds = [b.element_type for b in prev.scenes[0].blocks]
    assert "parenthetical" in kinds


def test_parser_detects_transition():
    prev = si.parse_fountain_to_scenes(_IMPORT_TEXT)
    kinds = [b.element_type for s in prev.scenes for b in s.blocks]
    assert "transition" in kinds


def test_parser_preserves_block_order():
    prev = si.parse_fountain_to_scenes(_IMPORT_TEXT)
    kinds = [b.element_type for b in prev.scenes[0].blocks]
    assert kinds == ["scene_heading", "action", "character",
                     "parenthetical", "dialogue", "transition"]


def test_parser_groups_scenes_correctly():
    prev = si.parse_fountain_to_scenes(_IMPORT_TEXT)
    assert prev.scene_count == 2
    assert prev.title_page.get("title") == "My Script"


def test_import_preview_does_not_mutate(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    pid = _screenplay(db)
    before = len(db.get_all_scenes(pid))
    prev = si.build_import_preview(db, pid, _IMPORT_TEXT, mode=si.IMPORT_INTO_PROJECT)
    assert prev.scene_count == 2
    assert len(db.get_all_scenes(pid)) == before     # no mutation


# ==========================================================================
# 29-32  Import apply
# ==========================================================================


def test_import_into_scene_requires_confirmation():
    db = Database()
    pid = _screenplay(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="S",
                          content="ORIGINAL").id
    res = si.apply_fountain_import(db, pid, _IMPORT_TEXT, mode=si.IMPORT_INTO_SCENE,
                                  confirmed=False, target_scene_id=sid)
    assert res["ok"] is False
    assert db.get_scene_by_id(sid).content == "ORIGINAL"   # untouched


def test_replace_scene_preserves_old_body_if_cancelled():
    db = Database()
    pid = _screenplay(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="S",
                          content="KEEP THIS BODY").id
    cancelled = si.apply_fountain_import(db, pid, _IMPORT_TEXT,
                                         mode=si.IMPORT_REPLACE_SCENE,
                                         confirmed=False, target_scene_id=sid)
    assert cancelled["ok"] is False
    assert db.get_scene_by_id(sid).content == "KEEP THIS BODY"
    confirmed = si.apply_fountain_import(db, pid, _IMPORT_TEXT,
                                         mode=si.IMPORT_REPLACE_SCENE,
                                         confirmed=True, target_scene_id=sid)
    assert confirmed["ok"]
    body = db.get_scene_by_id(sid).content
    assert "KITCHEN" in body and "KEEP THIS BODY" not in body


def test_import_into_project_creates_valid_parents():
    db = Database()
    pid = _screenplay(db)
    res = si.apply_fountain_import(db, pid, _IMPORT_TEXT,
                                  mode=si.IMPORT_INTO_PROJECT, confirmed=True)
    assert res["ok"] and res["scenes_created"] == 2
    for sid in res["scene_ids"]:
        sc = db.get_scene_by_id(sid)
        assert (sc.act or "").strip() and (sc.chapter or "").strip()


def test_import_creates_no_orphan_scenes():
    db = Database()
    pid = _screenplay(db)
    si.apply_fountain_import(db, pid, _IMPORT_TEXT,
                             mode=si.IMPORT_INTO_PROJECT, confirmed=True)
    from logosforge.story_structure import is_orphan_scene, build_structure_tree
    # Every scene resolves under a valid Act + Chapter (no orphans).
    for sc in db.get_all_scenes(pid):
        assert (sc.act or "").strip() and (sc.chapter or "").strip()
    # Structure tree builds without raising (invariant intact).
    assert build_structure_tree(db, pid) is not None


def test_import_new_project_is_isolated():
    db = Database()
    pid = _screenplay(db)
    res = si.apply_fountain_import(db, pid, _IMPORT_TEXT,
                                  mode=si.IMPORT_NEW_PROJECT, confirmed=True)
    assert res["ok"] and res["project_id"] != pid
    # Original project untouched; new project has the imported scenes.
    assert len(db.get_all_scenes(pid)) == 0
    assert len(db.get_all_scenes(res["project_id"])) == 2


def test_import_into_scene_appends():
    db = Database()
    pid = _screenplay(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="S",
                          content="EXISTING BODY").id
    res = si.apply_fountain_import(db, pid, _IMPORT_TEXT, mode=si.IMPORT_INTO_SCENE,
                                  confirmed=True, target_scene_id=sid)
    body = db.get_scene_by_id(sid).content
    assert res["ok"] and body.startswith("EXISTING BODY") and "KITCHEN" in body


# ==========================================================================
# UI surfaces (mode-gated, non-mutating)
# ==========================================================================


def test_import_dialog_mode_gating():
    from logosforge.ui.screenplay_import_dialog import FountainImportDialog
    prev = si.parse_fountain_to_scenes(_IMPORT_TEXT)
    no_target = FountainImportDialog(prev, has_target_scene=False)
    modes = [no_target._mode_combo.itemData(i)
             for i in range(no_target._mode_combo.count())]
    assert si.IMPORT_INTO_PROJECT in modes and si.IMPORT_NEW_PROJECT in modes
    assert si.IMPORT_INTO_SCENE not in modes        # hidden without a target
    with_target = FountainImportDialog(prev, has_target_scene=True)
    modes2 = [with_target._mode_combo.itemData(i)
              for i in range(with_target._mode_combo.count())]
    assert si.IMPORT_INTO_SCENE in modes2 and si.IMPORT_REPLACE_SCENE in modes2
    with_target._on_import()
    assert with_target.chosen_mode() in si.IMPORT_MODES


def test_manuscript_editor_has_scene_export_hook_in_screenplay(tmp_path):
    from logosforge.ui.writing_core_view import WritingCoreView
    db = Database(str(tmp_path / "sp.db"))
    pid = _screenplay(db)
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="S",
                    content="INT. X - DAY\n\nAction.")
    view = WritingCoreView(db, pid, structured_list=True)
    ed = next(iter(view._editors.values()))
    assert ed._screenplay_mode is True
    assert ed._on_export_scene_fountain is not None


def test_novel_editor_has_no_scene_export_hook(tmp_path):
    from logosforge.ui.writing_core_view import WritingCoreView
    db = Database(str(tmp_path / "n.db"))
    pid = _novel(db)
    ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S", content="prose")
    view = WritingCoreView(db, pid, structured_list=True)
    ed = next(iter(view._editors.values()))
    assert ed._screenplay_mode is False
