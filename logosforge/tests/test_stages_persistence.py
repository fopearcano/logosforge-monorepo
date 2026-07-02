"""Tests for Stage / StageSnapshot / StageBranch persistence."""

from logosforge.db import Database


def _setup():
    db = Database()
    proj = db.create_project("StagesTest")
    return db, proj


# -- Stage CRUD ---------------------------------------------------------------

def test_create_project_stage():
    db, proj = _setup()
    stage = db.create_stage(
        proj.id, "Draft 1", description="initial draft",
        scope_type="project", status="canonical",
    )
    assert stage.id is not None
    assert stage.name == "Draft 1"
    assert stage.scope_type == "project"
    assert stage.status == "canonical"


def test_create_scene_stage():
    db, proj = _setup()
    scene = db.create_scene(proj.id, "S1", content="x")
    stage = db.create_stage(
        proj.id, "Alt opening", scope_type="scene", scope_id=scene.id,
    )
    assert stage.scope_type == "scene"
    assert stage.scope_id == scene.id


def test_get_stage_returns_record():
    db, proj = _setup()
    stage = db.create_stage(proj.id, "X")
    fetched = db.get_stage(stage.id)
    assert fetched is not None
    assert fetched.name == "X"


def test_get_all_stages_isolated_per_project():
    db = Database()
    p1 = db.create_project("P1")
    p2 = db.create_project("P2")
    db.create_stage(p1.id, "in p1")
    db.create_stage(p2.id, "in p2")
    assert [s.name for s in db.get_all_stages(p1.id)] == ["in p1"]
    assert [s.name for s in db.get_all_stages(p2.id)] == ["in p2"]


def test_update_stage_fields():
    db, proj = _setup()
    stage = db.create_stage(proj.id, "old name")
    db.update_stage(stage.id, name="new name", description="updated")
    fetched = db.get_stage(stage.id)
    assert fetched.name == "new name"
    assert fetched.description == "updated"


def test_set_status_canonical_demotes_others_for_project_scope():
    db, proj = _setup()
    a = db.create_stage(proj.id, "A", scope_type="project", status="canonical")
    b = db.create_stage(proj.id, "B", scope_type="project", status="alternate")
    db.set_stage_status(b.id, "canonical")
    assert db.get_stage(a.id).status == "alternate"
    assert db.get_stage(b.id).status == "canonical"


def test_canonical_per_scene_isolated():
    db, proj = _setup()
    s1 = db.create_scene(proj.id, "S1", content="x")
    s2 = db.create_scene(proj.id, "S2", content="y")
    a = db.create_stage(proj.id, "A", scope_type="scene", scope_id=s1.id, status="canonical")
    b = db.create_stage(proj.id, "B", scope_type="scene", scope_id=s2.id, status="canonical")
    # Both can be canonical because they are different scenes
    assert db.get_stage(a.id).status == "canonical"
    assert db.get_stage(b.id).status == "canonical"


def test_canonical_within_same_scene_demotes_other():
    db, proj = _setup()
    scene = db.create_scene(proj.id, "S1", content="x")
    a = db.create_stage(proj.id, "A", scope_type="scene", scope_id=scene.id, status="canonical")
    b = db.create_stage(proj.id, "B", scope_type="scene", scope_id=scene.id, status="alternate")
    db.set_stage_status(b.id, "canonical")
    assert db.get_stage(a.id).status == "alternate"
    assert db.get_stage(b.id).status == "canonical"


def test_archive_stage():
    db, proj = _setup()
    stage = db.create_stage(proj.id, "to archive")
    db.set_stage_status(stage.id, "archived")
    assert db.get_stage(stage.id).status == "archived"


def test_delete_stage_cascades_to_snapshots_and_branches():
    db, proj = _setup()
    a = db.create_stage(proj.id, "A")
    b = db.create_stage(proj.id, "B")
    db.create_stage_snapshot(a.id, '{"data":{}}', label="snap")
    db.create_stage_branch(a.id, b.id, branch_reason="r")
    db.delete_stage(a.id)
    assert db.get_stage(a.id) is None
    assert db.get_stage_snapshots(a.id) == []
    assert db.get_branches_from(a.id) == []


def test_metadata_round_trip():
    db, proj = _setup()
    stage = db.create_stage(
        proj.id, "X", metadata={"quantum_branch_id": "abc"},
    )
    meta = db.get_stage_metadata(stage.id)
    assert meta == {"quantum_branch_id": "abc"}


# -- Snapshots ---------------------------------------------------------------

def test_snapshot_created_and_listed():
    db, proj = _setup()
    stage = db.create_stage(proj.id, "S")
    db.create_stage_snapshot(stage.id, '{"x":1}', label="v1", reason="why", summary="sum")
    snaps = db.get_stage_snapshots(stage.id)
    assert len(snaps) == 1
    assert snaps[0].label == "v1"
    assert snaps[0].summary == "sum"


def test_multiple_snapshots_ordered():
    db, proj = _setup()
    stage = db.create_stage(proj.id, "S")
    db.create_stage_snapshot(stage.id, '{"x":1}', label="first")
    db.create_stage_snapshot(stage.id, '{"x":2}', label="second")
    snaps = db.get_stage_snapshots(stage.id)
    assert [s.label for s in snaps] == ["first", "second"]


def test_get_snapshot_by_id():
    db, proj = _setup()
    stage = db.create_stage(proj.id, "S")
    snap = db.create_stage_snapshot(stage.id, '{}', label="x")
    fetched = db.get_snapshot(snap.id)
    assert fetched is not None
    assert fetched.label == "x"


# -- Branches ----------------------------------------------------------------

def test_branch_record_created():
    db, proj = _setup()
    a = db.create_stage(proj.id, "A")
    b = db.create_stage(proj.id, "B")
    br = db.create_stage_branch(a.id, b.id, branch_reason="John lies")
    assert br.id is not None
    assert br.source_stage_id == a.id
    assert br.target_stage_id == b.id
    assert br.branch_reason == "John lies"


def test_branches_from_stage():
    db, proj = _setup()
    a = db.create_stage(proj.id, "A")
    b = db.create_stage(proj.id, "B")
    c = db.create_stage(proj.id, "C")
    db.create_stage_branch(a.id, b.id, branch_reason="r1")
    db.create_stage_branch(a.id, c.id, branch_reason="r2")
    targets = {b.target_stage_id for b in db.get_branches_from(a.id)}
    assert targets == {b.id, c.id}


# -- Reload persistence ------------------------------------------------------

def test_stages_persist_in_same_db():
    db, proj = _setup()
    db.create_stage(proj.id, "Persisted")
    # Open a fresh session and re-read
    again = db.get_all_stages(proj.id)
    assert any(s.name == "Persisted" for s in again)


def test_child_stage_query():
    db, proj = _setup()
    parent = db.create_stage(proj.id, "Parent")
    child = db.create_stage(proj.id, "Child", parent_stage_id=parent.id)
    children = db.get_child_stages(parent.id)
    assert [c.id for c in children] == [child.id]
