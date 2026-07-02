"""Tests for Quantum Outliner timeline/scene integration."""

import json
from unittest.mock import patch

import pytest

from logosforge.db import Database
from logosforge.quantum_outliner import (
    OutlineMode,
    Branch,
    StateDelta,
    Wavefunction,
    apply_proposal,
    collapse_branch,
    generate_branches,
    generate_outline,
    get_state,
    reset_state,
)
from logosforge.quantum_outliner.collapse import collapse, _build_proposals
from logosforge.quantum_outliner.state import _STATES


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def project(db):
    return db.create_project("Timeline Test")


@pytest.fixture(autouse=True)
def _reset():
    _STATES.clear()
    yield
    _STATES.clear()


# --- Scene anchoring ---

class TestSceneAnchoring:
    def test_generate_branches_records_source_scene(self, db, project):
        scene = db.create_scene(project.id, title="Scene 5", content="Hero enters the cave.")
        get_state(project.id).outline_mode = OutlineMode.LAMBDA
        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_branches(
                db, project.id, "Hero enters the cave",
                source_scene_id=scene.id,
            )
        assert result.payload["source_scene_id"] == scene.id
        assert result.payload["source_scene_order"] == scene.sort_order

        state = get_state(project.id)
        wf = list(state.wavefunctions.values())[0]
        assert wf.source_scene_id == scene.id
        assert wf.source_scene_order == scene.sort_order

    def test_generate_outline_records_source_scene(self, db, project):
        scene = db.create_scene(project.id, title="Prologue")
        get_state(project.id).outline_mode = OutlineMode.LAMBDA
        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_outline(
                db, project.id, "A knight and a curse",
                source_scene_id=scene.id,
            )
        assert result.payload["source_scene_id"] == scene.id

    def test_generate_without_scene_has_null_source(self, db, project):
        get_state(project.id).outline_mode = OutlineMode.LAMBDA
        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_branches(db, project.id, "Free-floating situation")
        assert result.payload["source_scene_id"] is None
        assert result.payload["source_scene_order"] is None

    def test_source_scene_order_reflects_position(self, db, project):
        s1 = db.create_scene(project.id, title="Scene 1")
        s2 = db.create_scene(project.id, title="Scene 2")
        s3 = db.create_scene(project.id, title="Scene 3")

        get_state(project.id).outline_mode = OutlineMode.LAMBDA
        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_branches(
                db, project.id, "After scene 2",
                source_scene_id=s2.id,
            )
        assert result.payload["source_scene_order"] == s2.sort_order

    def test_invalid_scene_id_gives_null_order(self, db, project):
        get_state(project.id).outline_mode = OutlineMode.LAMBDA
        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_branches(
                db, project.id, "Orphan branch",
                source_scene_id=99999,
            )
        assert result.payload["source_scene_id"] == 99999
        assert result.payload["source_scene_order"] is None


# --- Collapse proposals ---

class TestCollapseProposals:
    def test_collapse_proposes_new_scene_after_source(self, db, project):
        s1 = db.create_scene(project.id, title="Scene 1", content="Start.")
        s2 = db.create_scene(project.id, title="Scene 2", content="Middle.")

        branch = Branch.new(
            title="The Betrayal",
            description="Alice betrays Bob at the crossroads.",
            consequence="Trust is broken forever.",
        )
        wf = Wavefunction.new(
            anchor="After scene 1",
            branches=[branch],
            source_scene_id=s1.id,
            source_scene_order=s1.sort_order,
        )
        get_state(project.id).add(wf)

        result = collapse(db, project.id, wf.id, branch.id, archive=False)
        proposals = result["proposals"]

        scene_proposals = [p for p in proposals if p["type"] == "create_scene"]
        assert len(scene_proposals) == 1
        assert scene_proposals[0]["after_scene_id"] == s1.id
        assert scene_proposals[0]["title"] == "The Betrayal"
        assert "Alice betrays Bob" in scene_proposals[0]["summary"]

    def test_collapse_proposes_consequence_note(self, db, project):
        scene = db.create_scene(project.id, title="Scene 1")
        branch = Branch.new(
            title="X", description="d",
            consequence="Everything changes.",
        )
        wf = Wavefunction.new(
            anchor="test", branches=[branch],
            source_scene_id=scene.id, source_scene_order=scene.sort_order,
        )
        get_state(project.id).add(wf)

        result = collapse(db, project.id, wf.id, branch.id, archive=False)
        note_proposals = [p for p in result["proposals"] if p["type"] == "update_scene_note"]
        assert len(note_proposals) == 1
        assert "Everything changes" in note_proposals[0]["note"]

    def test_collapse_proposes_progression(self, db, project):
        scene = db.create_scene(project.id, title="Scene 1")
        db.create_psyke_entry(project.id, "Alice", "character", notes="The hero")

        branch = Branch.new(
            title="X", description="d",
            state_delta=StateDelta(
                character_changes=[{"name": "Alice", "note": "becomes ruthless"}],
            ),
        )
        wf = Wavefunction.new(
            anchor="test", branches=[branch],
            source_scene_id=scene.id, source_scene_order=scene.sort_order,
        )
        get_state(project.id).add(wf)

        result = collapse(db, project.id, wf.id, branch.id, archive=False)
        prog_proposals = [p for p in result["proposals"] if p["type"] == "add_progression"]
        assert len(prog_proposals) == 1
        assert prog_proposals[0]["text"] == "becomes ruthless"
        assert prog_proposals[0]["scene_id"] == scene.id

    def test_collapse_without_source_scene_has_no_proposals(self, db, project):
        branch = Branch.new(title="X", description="d", consequence="things")
        wf = Wavefunction.new(anchor="floating", branches=[branch])
        get_state(project.id).add(wf)

        result = collapse(db, project.id, wf.id, branch.id, archive=False)
        assert result["proposals"] == []

    def test_collapse_result_includes_source_scene(self, db, project):
        scene = db.create_scene(project.id, title="Scene 5")
        branch = Branch.new(title="X", description="d")
        wf = Wavefunction.new(
            anchor="test", branches=[branch],
            source_scene_id=scene.id, source_scene_order=scene.sort_order,
        )
        get_state(project.id).add(wf)

        result = collapse(db, project.id, wf.id, branch.id, archive=False)
        assert result["source_scene_id"] == scene.id
        assert result["source_scene_order"] == scene.sort_order


# --- Apply proposals ---

class TestApplyProposal:
    def test_apply_create_scene_inserts_after_source(self, db, project):
        s1 = db.create_scene(project.id, title="Scene 1")
        s2 = db.create_scene(project.id, title="Scene 2")
        s3 = db.create_scene(project.id, title="Scene 3")

        proposal = {
            "type": "create_scene",
            "after_scene_id": s1.id,
            "title": "New Scene",
            "summary": "Something happens.",
            "content": "",
            "description": "...",
        }
        result = apply_proposal(db, project.id, proposal)
        assert result["type"] == "create_scene"
        assert result["title"] == "New Scene"

        scenes = db.get_all_scenes(project.id)
        titles = [s.title for s in scenes]
        assert titles.index("New Scene") == 1
        assert titles.index("Scene 2") == 2
        assert titles.index("Scene 3") == 3

    def test_apply_create_scene_sets_target_on_wavefunction(self, db, project):
        s1 = db.create_scene(project.id, title="Scene 1")
        branch = Branch.new(title="X", description="d")
        wf = Wavefunction.new(
            anchor="test", branches=[branch],
            source_scene_id=s1.id, source_scene_order=s1.sort_order,
        )
        wf.collapsed_branch_id = branch.id
        get_state(project.id).add(wf)

        proposal = {
            "type": "create_scene",
            "after_scene_id": s1.id,
            "title": "Created",
            "summary": "",
            "content": "",
            "description": "...",
        }
        result = apply_proposal(db, project.id, proposal)
        assert wf.target_scene_id == result["scene_id"]

    def test_apply_update_scene_note(self, db, project):
        scene = db.create_scene(project.id, title="Scene 1", summary="Original.")
        proposal = {
            "type": "update_scene_note",
            "scene_id": scene.id,
            "note": "[quantum] Trust shattered.",
            "description": "...",
        }
        result = apply_proposal(db, project.id, proposal)
        assert result["type"] == "update_scene_note"

        updated = db.get_scene_by_id(scene.id)
        assert "[quantum] Trust shattered" in updated.summary
        assert "Original" in updated.summary

    def test_apply_add_progression(self, db, project):
        scene = db.create_scene(project.id, title="Scene 1")
        entry = db.create_psyke_entry(project.id, "Alice", "character")
        proposal = {
            "type": "add_progression",
            "entry_id": entry.id,
            "text": "Becomes ruthless after betrayal",
            "scene_id": scene.id,
            "description": "...",
        }
        result = apply_proposal(db, project.id, proposal)
        assert result["type"] == "add_progression"

        progs = db.get_psyke_progressions(entry.id)
        assert len(progs) == 1
        assert progs[0].text == "Becomes ruthless after betrayal"
        assert progs[0].scene_id == scene.id

    def test_apply_unknown_proposal_type(self, db, project):
        result = apply_proposal(db, project.id, {"type": "unknown_thing"})
        assert result["type"] == "unknown"


# --- End-to-end: branch from scene, collapse, apply ---

class TestEndToEnd:
    def test_branch_from_scene_5_collapse_into_next(self, db, project):
        """Full flow: scenes exist → branch from scene 5 → collapse → create scene 6."""
        for i in range(1, 8):
            db.create_scene(project.id, title=f"Scene {i}", content=f"Content {i}.")

        scenes = db.get_all_scenes(project.id)
        scene_5 = next(s for s in scenes if s.title == "Scene 5")

        get_state(project.id).outline_mode = OutlineMode.LAMBDA
        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_branches(
                db, project.id, "After the cave collapse",
                source_scene_id=scene_5.id,
            )

        assert result.payload["source_scene_id"] == scene_5.id
        wf_id = result.payload["wavefunction_id"]
        branch_id = result.payload["branches"][0]["id"]

        collapse_result = collapse_branch(db, project.id, wf_id, branch_id)
        assert collapse_result.kind == "collapse"

        proposals = collapse_result.payload["proposals"]
        scene_proposal = next(
            (p for p in proposals if p["type"] == "create_scene"), None,
        )
        assert scene_proposal is not None
        assert scene_proposal["after_scene_id"] == scene_5.id

        apply_result = apply_proposal(db, project.id, scene_proposal)
        assert apply_result["type"] == "create_scene"
        new_scene_id = apply_result["scene_id"]

        final_scenes = db.get_all_scenes(project.id)
        titles = [s.title for s in final_scenes]
        new_scene_idx = next(i for i, s in enumerate(final_scenes) if s.id == new_scene_id)
        scene_5_idx = next(i for i, s in enumerate(final_scenes) if s.id == scene_5.id)
        scene_6_idx = next(i for i, s in enumerate(final_scenes) if s.title == "Scene 6")

        assert new_scene_idx == scene_5_idx + 1
        assert scene_6_idx == new_scene_idx + 1

    def test_scene_linkage_persists_through_serialization(self, db, project):
        """source_scene_id and target_scene_id survive serialize/deserialize."""
        from logosforge.quantum_outliner.state import deserialize_state, serialize_state

        scene = db.create_scene(project.id, title="Scene 1")
        state = get_state(project.id)
        wf = Wavefunction.new(
            anchor="test",
            branches=[Branch.new(title="X", description="d")],
            source_scene_id=scene.id,
            source_scene_order=scene.sort_order,
        )
        wf.target_scene_id = 42
        state.add(wf)

        raw = serialize_state(state)
        restored = deserialize_state(raw, project.id)
        rwf = list(restored.wavefunctions.values())[0]
        assert rwf.source_scene_id == scene.id
        assert rwf.source_scene_order == scene.sort_order
        assert rwf.target_scene_id == 42
