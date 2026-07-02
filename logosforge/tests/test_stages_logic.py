"""Tests for stages.py: capture, save, restore, branch, diff."""

import json

from logosforge.db import Database
from logosforge.stages import (
    SAFETY_STAGE_NAME,
    branch_from,
    capture_scope,
    create_from_quantum_collapse,
    diff_payloads,
    load_snapshot,
    restore_snapshot,
    save_snapshot,
    snapshot_summary,
)


def _setup_world():
    db = Database()
    proj = db.create_project("World")
    char = db.create_character(proj.id, "Mara")
    scene = db.create_scene(
        proj.id, "Opening",
        content="Mara walked into the inn.",
        synopsis="Arrival",
        character_ids=[char.id],
    )
    return db, proj, char, scene


# -- Capture -----------------------------------------------------------------

def test_capture_scene_returns_content():
    db, proj, char, scene = _setup_world()
    captured = capture_scope(db, proj.id, "scene", scene.id)
    assert captured["scope_type"] == "scene"
    assert captured["data"]["content"] == "Mara walked into the inn."
    assert captured["data"]["title"] == "Opening"
    assert char.id in captured["data"]["character_ids"]


def test_capture_outline_returns_nodes():
    db, proj, _, _ = _setup_world()
    db.create_outline_node(proj.id, title="Act I", description="setup")
    captured = capture_scope(db, proj.id, "outline", None)
    assert captured["scope_type"] == "outline"
    assert len(captured["data"]["nodes"]) == 1
    assert captured["data"]["nodes"][0]["title"] == "Act I"


def test_capture_psyke_returns_entries():
    db, proj, _, _ = _setup_world()
    db.create_psyke_entry(
        proj.id, "Mara", entry_type="character",
        details={"personality": "curious"},
    )
    captured = capture_scope(db, proj.id, "psyke", None)
    assert captured["scope_type"] == "psyke"
    assert len(captured["data"]["entries"]) == 1


def test_capture_project_includes_all():
    db, proj, _, _ = _setup_world()
    captured = capture_scope(db, proj.id, "project", None)
    assert "scenes" in captured["data"]
    assert "outline" in captured["data"]
    assert "psyke" in captured["data"]


def test_capture_unknown_scope_returns_empty():
    db, proj, _, _ = _setup_world()
    captured = capture_scope(db, proj.id, "made_up", None)
    assert captured["data"] == {}


def test_snapshot_summary_describes_scene():
    db, proj, _, scene = _setup_world()
    captured = capture_scope(db, proj.id, "scene", scene.id)
    assert "Opening" in snapshot_summary(captured)
    assert "words" in snapshot_summary(captured)


# -- Save / load -------------------------------------------------------------

def test_save_and_load_round_trip():
    db, proj, _, scene = _setup_world()
    stage = db.create_stage(proj.id, "St", scope_type="scene", scope_id=scene.id)
    captured = capture_scope(db, proj.id, "scene", scene.id)
    snap = save_snapshot(db, stage.id, captured, label="v1")
    payload = load_snapshot(db, snap.id)
    assert payload is not None
    assert payload.scope_type == "scene"
    assert payload.data["content"] == "Mara walked into the inn."


def test_load_missing_snapshot_returns_none():
    db, proj, _, _ = _setup_world()
    assert load_snapshot(db, 9999) is None


# -- Restore -----------------------------------------------------------------

def test_restore_scene_writes_back():
    db, proj, _, scene = _setup_world()
    stage = db.create_stage(proj.id, "St", scope_type="scene", scope_id=scene.id)
    snap = save_snapshot(
        db, stage.id, capture_scope(db, proj.id, "scene", scene.id),
    )
    db.update_scene_content(scene.id, "totally different content")
    result = restore_snapshot(db, proj.id, snap.id)
    assert result["ok"]
    assert db.get_scene_by_id(scene.id).content == "Mara walked into the inn."


def test_restore_takes_safety_snapshot():
    db, proj, _, scene = _setup_world()
    stage = db.create_stage(proj.id, "St", scope_type="scene", scope_id=scene.id)
    snap = save_snapshot(db, stage.id, capture_scope(db, proj.id, "scene", scene.id))
    db.update_scene_content(scene.id, "to be replaced")
    result = restore_snapshot(db, proj.id, snap.id)
    assert result["safety_snapshot_id"] is not None
    safety = db.get_snapshot(result["safety_snapshot_id"])
    assert "to be replaced" in safety.data_json


def test_safety_stage_created_lazily_and_reused():
    db, proj, _, scene = _setup_world()
    stage = db.create_stage(proj.id, "St", scope_type="scene", scope_id=scene.id)
    snap = save_snapshot(db, stage.id, capture_scope(db, proj.id, "scene", scene.id))
    restore_snapshot(db, proj.id, snap.id)
    restore_snapshot(db, proj.id, snap.id)
    safety_stages = [
        s for s in db.get_all_stages(proj.id) if s.name == SAFETY_STAGE_NAME
    ]
    assert len(safety_stages) == 1
    assert len(db.get_stage_snapshots(safety_stages[0].id)) == 2


def test_restore_can_skip_safety():
    db, proj, _, scene = _setup_world()
    stage = db.create_stage(proj.id, "St", scope_type="scene", scope_id=scene.id)
    snap = save_snapshot(db, stage.id, capture_scope(db, proj.id, "scene", scene.id))
    result = restore_snapshot(db, proj.id, snap.id, take_safety=False)
    assert result["ok"]
    assert result["safety_snapshot_id"] is None


def test_restore_outline_replaces_tree():
    db, proj, _, _ = _setup_world()
    db.create_outline_node(proj.id, title="Original")
    captured = capture_scope(db, proj.id, "outline", None)
    stage = db.create_stage(proj.id, "OL", scope_type="outline")
    snap = save_snapshot(db, stage.id, captured)
    db.delete_all_outline_nodes(proj.id)
    db.create_outline_node(proj.id, title="Replacement")
    result = restore_snapshot(db, proj.id, snap.id)
    assert result["ok"]
    nodes = db.get_outline_nodes(proj.id)
    assert any(n.title == "Original" for n in nodes)
    assert not any(n.title == "Replacement" for n in nodes)


def test_restore_unknown_snapshot_fails_gracefully():
    db, proj, _, _ = _setup_world()
    result = restore_snapshot(db, proj.id, 99999)
    assert not result["ok"]
    assert "not found" in (result.get("error") or "").lower()


# -- Branch ------------------------------------------------------------------

def test_branch_creates_alternate_with_parent():
    db, proj, _, scene = _setup_world()
    source = db.create_stage(proj.id, "Original", scope_type="scene", scope_id=scene.id)
    save_snapshot(db, source.id, capture_scope(db, proj.id, "scene", scene.id))
    new_stage = branch_from(
        db, source.id, name="Alt", branch_reason="John lies instead",
    )
    assert new_stage is not None
    assert new_stage.parent_stage_id == source.id
    assert new_stage.scope_type == "scene"
    assert new_stage.status == "alternate"


def test_branch_records_edge():
    db, proj, _, _ = _setup_world()
    source = db.create_stage(proj.id, "Original")
    new_stage = branch_from(db, source.id, name="Alt", branch_reason="why")
    edges = db.get_branches_from(source.id)
    assert any(e.target_stage_id == new_stage.id for e in edges)


def test_branch_copies_latest_snapshot_when_requested():
    db, proj, _, scene = _setup_world()
    source = db.create_stage(proj.id, "Original", scope_type="scene", scope_id=scene.id)
    save_snapshot(db, source.id, capture_scope(db, proj.id, "scene", scene.id), label="v1")
    new_stage = branch_from(db, source.id, name="Alt", copy_data=True)
    snaps = db.get_stage_snapshots(new_stage.id)
    assert len(snaps) == 1
    assert "Original" in snaps[0].label or snaps[0].summary != ""


def test_branch_no_copy_when_disabled():
    db, proj, _, scene = _setup_world()
    source = db.create_stage(proj.id, "Original")
    save_snapshot(db, source.id, capture_scope(db, proj.id, "project", None))
    new_stage = branch_from(db, source.id, name="Alt", copy_data=False)
    assert db.get_stage_snapshots(new_stage.id) == []


def test_branch_from_missing_source_returns_none():
    db, proj, _, _ = _setup_world()
    assert branch_from(db, 99999, name="X") is None


# -- Diff --------------------------------------------------------------------

def test_diff_detects_content_change():
    db, proj, _, scene = _setup_world()
    before = capture_scope(db, proj.id, "scene", scene.id)
    db.update_scene_content(scene.id, "She left without speaking.")
    after = capture_scope(db, proj.id, "scene", scene.id)
    diff = diff_payloads(before, after)
    assert "content" in [c[0] for c in diff.changed]


def test_diff_unified_text_present():
    db, proj, _, scene = _setup_world()
    before = capture_scope(db, proj.id, "scene", scene.id)
    db.update_scene_content(scene.id, "Different.")
    after = capture_scope(db, proj.id, "scene", scene.id)
    diff = diff_payloads(before, after)
    assert "Mara walked" in diff.unified
    assert "Different" in diff.unified


def test_diff_no_change_empty_unified():
    db, proj, _, scene = _setup_world()
    p1 = capture_scope(db, proj.id, "scene", scene.id)
    p2 = capture_scope(db, proj.id, "scene", scene.id)
    diff = diff_payloads(p1, p2)
    assert diff.changed == []


# -- Quantum integration helper ----------------------------------------------

def test_quantum_collapse_creates_stage_with_metadata():
    db, proj, _, _ = _setup_world()
    stage = create_from_quantum_collapse(
        db, proj.id,
        wavefunction_id="wf-1",
        branch_id="b-7",
        branch_title="Mary discovers truth",
        reason="user collapse",
    )
    assert stage is not None
    meta = db.get_stage_metadata(stage.id)
    assert meta["quantum_wavefunction_id"] == "wf-1"
    assert meta["quantum_branch_id"] == "b-7"


def test_quantum_collapse_with_payload_creates_snapshot():
    db, proj, _, _ = _setup_world()
    captured = capture_scope(db, proj.id, "project", None)
    stage = create_from_quantum_collapse(
        db, proj.id,
        wavefunction_id="wf-1",
        branch_id="b-7",
        branch_title="X",
        reason="r",
        captured=captured,
    )
    assert len(db.get_stage_snapshots(stage.id)) == 1
