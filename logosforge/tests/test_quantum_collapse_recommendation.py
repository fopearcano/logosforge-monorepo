"""Tests for PSYKE-aware collapse recommendation scoring."""

from unittest.mock import patch

import pytest

from logosforge.db import Database
from logosforge.quantum_outliner import OutlineMode, generate_branches, get_state
from logosforge.quantum_outliner.core import _pick_collapse_candidate
from logosforge.quantum_outliner.psyke_adapter import PsykeSignals, gather_psyke_signals
from logosforge.quantum_outliner.state import Branch, Wavefunction, _STATES
from logosforge.quantum_outliner.writing_methods_rag import reload as rag_reload


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def project(db):
    return db.create_project("Collapse Recommendation Test")


@pytest.fixture(autouse=True)
def _reset():
    _STATES.clear()
    rag_reload()
    yield
    _STATES.clear()


class TestPsykeSignals:
    def test_gather_empty_project(self, db, project):
        signals = gather_psyke_signals(db, project.id)
        assert signals.characters == []
        assert signals.relations == []
        assert signals.unresolved_arcs == []
        assert signals.keywords == frozenset()

    def test_gather_characters(self, db, project):
        db.create_psyke_entry(project.id, "John", "character", notes="Distrusts authority")
        db.create_psyke_entry(project.id, "Mary", "character", notes="Loyal but secretive")
        signals = gather_psyke_signals(db, project.id)
        assert len(signals.characters) == 2
        assert "john" in signals.keywords
        assert "mary" in signals.keywords
        assert "distrusts" in signals.keywords

    def test_gather_relations(self, db, project):
        e1 = db.create_psyke_entry(project.id, "John", "character")
        e2 = db.create_psyke_entry(project.id, "Mary", "character")
        db.add_psyke_relation(e1.id, e2.id)
        signals = gather_psyke_signals(db, project.id)
        assert len(signals.relations) == 1
        assert signals.relations[0]["from"] == "John"
        assert signals.relations[0]["to"] == "Mary"

    def test_gather_unresolved_arcs(self, db, project):
        db.create_psyke_entry(
            project.id, "John", "character",
            notes="Strong leader\n\n[arc] Must overcome fear of betrayal",
        )
        signals = gather_psyke_signals(db, project.id)
        assert len(signals.unresolved_arcs) == 1
        assert signals.unresolved_arcs[0]["name"] == "John"
        assert "betrayal" in signals.unresolved_arcs[0]["arc"]

    def test_ignores_non_character_entries(self, db, project):
        db.create_psyke_entry(project.id, "Tavern", "place", notes="Dark and smoky")
        signals = gather_psyke_signals(db, project.id)
        assert signals.characters == []


class TestPsykeAwareRecommendation:
    def test_prefers_branch_mentioning_character(self):
        psyke = PsykeSignals(
            characters=[{"name": "John", "notes": "Distrusts Mary"}],
            relations=[],
            unresolved_arcs=[],
            keywords=frozenset({"john", "distrusts", "mary"}),
        )
        b1 = Branch.new(
            title="Escape Route",
            description="The team flees through the tunnels.",
            branch_type="alternative",
        )
        b2 = Branch.new(
            title="John Confronts",
            description="John must face his distrust and choose.",
            branch_type="alternative",
        )
        wf = Wavefunction.new(anchor="Crisis point", branches=[b1, b2])
        rec = _pick_collapse_candidate(wf, psyke=psyke)
        assert rec is not None
        assert rec[0] == "John Confronts"
        assert "John" in rec[3]

    def test_prefers_branch_matching_relationship(self):
        psyke = PsykeSignals(
            characters=[
                {"name": "John", "notes": "Leader"},
                {"name": "Mary", "notes": "Spy"},
            ],
            relations=[{"from": "John", "to": "Mary"}],
            unresolved_arcs=[],
            keywords=frozenset({"john", "mary", "leader", "spy"}),
        )
        b1 = Branch.new(
            title="Solo Mission",
            description="The hero goes alone into the dark.",
            branch_type="deviation",
        )
        b2 = Branch.new(
            title="Trust Test",
            description="John must decide whether to trust Mary.",
            branch_type="alternative",
        )
        wf = Wavefunction.new(anchor="Decision", branches=[b1, b2])
        rec = _pick_collapse_candidate(wf, psyke=psyke)
        assert rec is not None
        assert rec[0] == "Trust Test"
        assert "↔" in rec[3]

    def test_prefers_branch_advancing_arc(self):
        psyke = PsykeSignals(
            characters=[{"name": "John", "notes": ""}],
            relations=[],
            unresolved_arcs=[{"name": "John", "arc": "overcome fear of betrayal"}],
            keywords=frozenset({"john", "overcome", "fear", "betrayal"}),
        )
        b1 = Branch.new(
            title="Market Scene",
            description="The team resupplies at a busy market.",
        )
        b2 = Branch.new(
            title="Betrayal Revealed",
            description="John discovers the betrayal he always feared.",
            stakes="Trust",
            consequence="Must overcome or succumb",
        )
        wf = Wavefunction.new(anchor="Midpoint", branches=[b1, b2])
        rec = _pick_collapse_candidate(wf, psyke=psyke)
        assert rec is not None
        assert rec[0] == "Betrayal Revealed"
        assert "arc" in rec[3]

    def test_recommendation_changes_when_psyke_changes(self, db, project):
        b1 = Branch.new(
            title="Alliance",
            description="John and Mary form an alliance.",
            branch_type="alternative",
        )
        b2 = Branch.new(
            title="Conflict",
            description="Open warfare erupts between factions.",
            branch_type="alternative",
        )
        wf = Wavefunction.new(anchor="test", branches=[b1, b2])

        psyke_v1 = PsykeSignals(
            characters=[{"name": "John", "notes": "Seeks allies"}],
            relations=[],
            unresolved_arcs=[],
            keywords=frozenset({"john", "seeks", "allies"}),
        )
        rec1 = _pick_collapse_candidate(wf, psyke=psyke_v1)
        assert rec1 is not None

        psyke_v2 = PsykeSignals(
            characters=[{"name": "Commander", "notes": "Wants war"}],
            relations=[],
            unresolved_arcs=[],
            keywords=frozenset({"commander", "wants", "warfare"}),
        )
        rec2 = _pick_collapse_candidate(wf, psyke=psyke_v2)
        assert rec2 is not None
        assert rec1[0] != rec2[0]

    def test_no_psyke_still_uses_method_metadata(self):
        b1 = Branch.new(
            title="Intensify",
            description="Push the beat harder.",
            branch_type="intensification",
            structure_beat="Midpoint",
        )
        b2 = Branch.new(
            title="Deviate",
            description="Go off the expected path.",
            branch_type="deviation",
        )
        wf = Wavefunction.new(anchor="test", branches=[b1, b2])
        wf.structure_beat = "Midpoint"
        rec = _pick_collapse_candidate(wf, psyke=None)
        assert rec is not None
        assert rec[0] == "Intensify"
        assert "structural beat" in rec[2]

    def test_signals_field_populated_with_psyke(self):
        psyke = PsykeSignals(
            characters=[{"name": "Hero", "notes": "brave"}],
            relations=[],
            unresolved_arcs=[],
            keywords=frozenset({"hero", "brave"}),
        )
        b1 = Branch.new(
            title="Hero's Choice",
            description="The hero faces a brave decision.",
        )
        wf = Wavefunction.new(anchor="test", branches=[b1])
        rec = _pick_collapse_candidate(wf, psyke=psyke)
        assert rec is not None
        assert rec[3] != ""

    def test_signals_empty_when_no_psyke_match(self):
        b1 = Branch.new(title="Generic", description="Something happens.")
        b2 = Branch.new(title="Other", description="Another thing.")
        wf = Wavefunction.new(anchor="test", branches=[b1, b2])
        rec = _pick_collapse_candidate(wf, psyke=None)
        assert rec is not None
        assert rec[3] == ""


class TestCollapseInOutput:
    def test_psyke_characters_shown_as_pov(self, db, project):
        db.create_psyke_entry(project.id, "John", "character", notes="Distrusts authority")
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        state.structure_mode = "hybrid"

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_branches(
                db, project.id, "Save the Cat midpoint",
            )

        assert "POV Frames:" in result.body
        assert "John" in result.body

    def test_gravity_shown_for_structural_query(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        state.structure_mode = "hybrid"

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_branches(
                db, project.id, "Hero's Journey Ordeal",
            )

        assert "Gravity:" in result.body
        assert "QUANTUM FIELD" in result.body

    def test_psyke_arc_characters_visible(self, db, project):
        db.create_psyke_entry(
            project.id, "Conflict", "character",
            notes="Open hostility\n\n[arc] Must resolve hatred",
        )
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        state.structure_mode = "hybrid"

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_branches(
                db, project.id, "Save the Cat midpoint",
            )

        assert "POV Frames:" in result.body
        assert "Conflict" in result.body


class TestEndToEndPsykeRecommendation:
    def test_psyke_characters_in_pov_frames(self, db, project):
        db.create_psyke_entry(project.id, "John", "character", notes="Leader who distrusts")
        db.create_psyke_entry(project.id, "Mary", "character", notes="Spy for the enemy")
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        state.structure_mode = "hybrid"

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_branches(
                db, project.id, "Save the Cat Midpoint scene",
            )

        assert result.kind == "possibilities"
        assert "POV Frames:" in result.body
        assert "John" in result.body

    def test_no_auto_collapse(self, db, project):
        db.create_psyke_entry(project.id, "Hero", "character", notes="brave warrior")
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        state.structure_mode = "hybrid"

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_branches(
                db, project.id, "Save the Cat midpoint",
            )

        assert result.payload.get("collapsed_branch_id") is None
        assert "/quantum collapse" in result.body
