"""Outline generation must stay isolated from Manuscript, and produce a
structured, complete outline (no empty placeholder blocks, no prose).

Covers the fix pass:
  * Assistant Replace/Insert/Append in Outline Mode never write manuscript prose
    (Scene.content); they route through the outline pipeline.
  * Applying a generated outline never touches existing manuscript prose.
  * repair_outline_ops fills missing descriptions and trims prose.
  * validate_outline_ops rejects empty / prose-masquerading output.
  * Generated acts/chapters/scenes all carry non-empty descriptions.
  * The confirmation dialog can surface quality warnings.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.outline_actions import (
    OutlineOp,
    apply_outline_as_scenes,
    count_ops,
    parse_outline_response,
    repair_outline_ops,
    validate_outline_ops,
)

_OUTLINE = """# Act 1: Setup
## Chapter 1: The Call
- Scene: Opening
- Scene: The summons
# Act 2: Confrontation
## Chapter 2: Trials
- Scene: First test
"""

_MANUSCRIPT_PROSE = "THIS IS MANUSCRIPT PROSE — MUST NOT CHANGE"


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
    import logosforge.gomckee_bridge as gb
    monkeypatch.setattr(gb, "is_gomckee_enabled", lambda: False, raising=False)
    yield
    settings._instance = None


def _project():
    db = Database()
    return db, db.create_project("Saga", narrative_engine="novel").id


def _panel(db, pid):
    from logosforge.ui.assistant_view import AssistantPanel
    return AssistantPanel(db, pid)


# ==========================================================================
# repair_outline_ops — fill empty descriptions, trim prose
# ==========================================================================


def test_repair_fills_empty_descriptions():
    ops = parse_outline_response(_OUTLINE)
    before = count_ops(ops)
    ops, repair_warnings = repair_outline_ops(ops)
    # No nodes added or removed.
    assert count_ops(ops) == before
    # Every node now has a non-empty description.
    def _all(nodes):
        for o in nodes:
            assert o.description.strip(), f"{o.title!r} has no description"
            _all(o.children)
    _all(ops)
    assert repair_warnings  # it reported that placeholders were added


def test_repair_descriptions_are_kind_aware():
    ops, _ = repair_outline_ops([OutlineOp(title="Act 1", kind="act")])
    assert "dramatic purpose" in ops[0].description.lower()
    ops, _ = repair_outline_ops([OutlineOp(title="Hook", kind="scene")])
    assert "conflict" in ops[0].description.lower()


def test_repair_trims_prose_like_description():
    long_prose = "word " * 200  # ~1000 chars
    ops, repair_warnings = repair_outline_ops(
        [OutlineOp(title="Scene", description=long_prose, kind="scene")]
    )
    assert len(ops[0].description) <= 320
    assert ops[0].description.endswith("…")
    assert any("prose" in w for w in repair_warnings)


def test_repair_preserves_good_descriptions():
    ops, repair_warnings = repair_outline_ops(
        [OutlineOp(title="Act 1", description="A solid one-liner.", kind="act")]
    )
    assert ops[0].description == "A solid one-liner."
    assert repair_warnings == []


# ==========================================================================
# validate_outline_ops — reject empty / prose
# ==========================================================================


def test_validate_accepts_real_outline():
    ok, errors = validate_outline_ops(parse_outline_response(_OUTLINE))
    assert ok is True and errors == []


def test_validate_rejects_empty():
    ok, errors = validate_outline_ops([])
    assert ok is False and errors


def test_validate_rejects_prose_masquerading_as_title():
    prose = "It was a dark and stormy night, " * 20  # > 200 chars, no structure
    ops = parse_outline_response(prose)
    ok, errors = validate_outline_ops(ops)
    assert ok is False
    assert any("prose" in e.lower() for e in errors)


# ==========================================================================
# Assistant Outline Mode — Replace/Insert/Append never touch Manuscript
# ==========================================================================


@pytest.mark.parametrize("handler", ["_apply_replace", "_apply_insert", "_apply_append"])
def test_apply_buttons_in_outline_mode_do_not_pollute_manuscript(handler, monkeypatch):
    db, pid = _project()
    # A single existing scene with real manuscript prose (auto-scene target).
    sid = db.create_scene(pid, title="S1", content=_MANUSCRIPT_PROSE).id
    panel = _panel(db, pid)
    panel.set_active_section_name("Outline")
    panel._response_output.setPlainText(_OUTLINE)

    # Record any attempt to write manuscript prose.
    calls = []
    monkeypatch.setattr(
        panel._db, "update_scene_content",
        lambda *a, **k: calls.append(a), raising=True,
    )
    # Cancel the outline confirm dialog so we isolate the *routing* decision.
    monkeypatch.setattr(
        "logosforge.ui.outline_confirm_dialog.OutlineConfirmDialog.confirm",
        staticmethod(lambda *a, **k: False),
    )
    getattr(panel, handler)()

    # The manuscript field was never written, and the prose is intact.
    assert calls == [], f"{handler} wrote to manuscript content in Outline Mode"
    assert db.get_scene_by_id(sid).content == _MANUSCRIPT_PROSE


def test_outline_mode_hides_prose_actions():
    db, pid = _project()
    panel = _panel(db, pid)
    panel.set_active_section_name("Manuscript")
    assert not panel._replace_content_btn.isHidden()
    panel.set_active_section_name("Outline")
    # Prose-targeting actions are hidden so they can't pollute Manuscript.
    assert panel._replace_content_btn.isHidden()
    assert panel._insert_cursor_btn.isHidden()
    assert panel._append_btn.isHidden()


def test_apply_to_outline_creates_structure_without_touching_manuscript():
    db, pid = _project()
    sid = db.create_scene(pid, title="Existing", content=_MANUSCRIPT_PROSE).id
    panel = _panel(db, pid)
    panel.set_active_section_name("Outline")
    panel._response_output.setPlainText(_OUTLINE)
    created = panel._apply_to_outline(confirm=False)
    assert created  # new outline scenes were created
    # Existing manuscript prose is untouched.
    assert db.get_scene_by_id(sid).content == _MANUSCRIPT_PROSE
    # New scenes carry planning summaries, NOT manuscript prose.
    new = [s for s in db.get_all_scenes(pid) if s.id != sid]
    assert new
    assert all((s.content or "") == "" for s in new)
    assert all((s.summary or "").strip() for s in new)


def test_apply_to_outline_rejects_prose_safely():
    db, pid = _project()
    panel = _panel(db, pid)
    panel.set_active_section_name("Outline")
    panel._response_output.setPlainText("It was a dark and stormy night, " * 20)
    # Invalid (prose) output is not applied — no scenes created, no crash.
    assert panel._apply_to_outline(confirm=False) == []
    assert db.get_all_scenes(pid) == []


# ==========================================================================
# apply_outline_as_scenes writes planning summaries, never manuscript content
# ==========================================================================


def test_apply_as_scenes_writes_summary_not_content():
    db, pid = _project()
    ops, _ = repair_outline_ops(parse_outline_response(_OUTLINE))
    created = apply_outline_as_scenes(db, pid, ops)
    assert created
    for sid in created:
        s = db.get_scene_by_id(sid)
        assert (s.content or "") == ""        # never manuscript prose
        assert (s.summary or "").strip()      # planning summary present


# ==========================================================================
# Confirmation dialog surfaces warnings
# ==========================================================================


def test_confirm_dialog_shows_warnings():
    from logosforge.ui.outline_confirm_dialog import OutlineConfirmDialog
    dlg = OutlineConfirmDialog(
        "• Act 1", 1, warnings=["2 item(s) had no description"],
    )
    assert hasattr(dlg, "_warnings_label")
    assert "no description" in dlg._warnings_label.text()
