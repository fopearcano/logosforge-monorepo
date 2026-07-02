"""Tests for QUANTUM Outliner — narrative plotting agent."""

import json
from unittest.mock import patch

import pytest

from logosforge.db import Database
from logosforge.quantum_outliner import (
    Branch,
    OutlineMode,
    StateDelta,
    Wavefunction,
    collapse_branch,
    detect_weak_scenes,
    generate_branches,
    generate_outline,
    get_state,
    list_active_wavefunctions,
    reframe,
    reset_state,
)
from logosforge.quantum_outliner.collapse import CollapseError, collapse, load_archive
from logosforge.quantum_outliner.possibilities import (
    _parse_branches,
    _stub_branches,
    generate_possibilities,
)
from logosforge.quantum_outliner.psyke_adapter import (
    apply_collapse,
    find_entry_by_name,
    gather_psyke_brief,
)
from logosforge.quantum_outliner.state import NarrativeState
from logosforge.quantum_outliner.uncertainty import (
    find_uncertainty_zones,
    score_scene,
)


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def project(db):
    return db.create_project("Quantum Test")


@pytest.fixture(autouse=True)
def _reset_state(project):
    reset_state(project.id)
    yield
    reset_state(project.id)


# --- State engine ---

class TestState:
    def test_branch_new_assigns_id(self):
        b = Branch.new(title="Conflict", description="They fight.")
        assert len(b.id) == 8
        assert b.title == "Conflict"
        assert isinstance(b.state_delta, StateDelta)

    def test_wavefunction_new(self):
        wf = Wavefunction.new(anchor="Hero meets enemy")
        assert wf.anchor == "Hero meets enemy"
        assert wf.branches == []
        assert wf.collapsed_branch_id is None
        assert not wf.is_collapsed()

    def test_get_branch_by_id(self):
        b = Branch.new(title="A", description="x")
        wf = Wavefunction.new(anchor="x", branches=[b])
        assert wf.get_branch(b.id) is b
        assert wf.get_branch("nope") is None

    def test_narrative_state_active_collapsed(self):
        ns = NarrativeState(project_id=1)
        wf1 = Wavefunction.new(anchor="a")
        wf2 = Wavefunction.new(anchor="b")
        wf2.collapsed_branch_id = "x"
        ns.add(wf1)
        ns.add(wf2)
        assert wf1 in ns.active()
        assert wf2 in ns.collapsed()

    def test_get_state_per_project(self, project):
        s1 = get_state(project.id)
        s2 = get_state(project.id)
        assert s1 is s2
        assert s1.project_id == project.id


# --- Possibility generator ---

class TestPossibilities:
    def test_parse_valid_response(self):
        resp = json.dumps({
            "branches": [
                {
                    "title": "Betrayal", "description": "They betray.",
                    "stakes": "Trust", "consequence": "Severed",
                    "state_delta": {
                        "character_changes": [{"name": "Alice", "note": "becomes wary"}],
                        "new_relations": [],
                        "arc_updates": [],
                    },
                },
            ]
        })
        branches = _parse_branches(resp)
        assert len(branches) == 1
        assert branches[0].title == "Betrayal"
        assert branches[0].state_delta.character_changes[0]["name"] == "Alice"

    def test_parse_strips_code_block(self):
        resp = '```json\n{"branches": [{"title": "A", "description": "x"}]}\n```'
        branches = _parse_branches(resp)
        assert len(branches) == 1

    def test_parse_invalid_json_returns_empty(self):
        assert _parse_branches("not json") == []

    def test_parse_skips_incomplete_branch(self):
        resp = json.dumps({"branches": [{"title": "Only title"}]})
        assert _parse_branches(resp) == []

    def test_stub_branches_count(self):
        assert len(_stub_branches("Hero meets enemy", 4)) == 4
        assert len(_stub_branches("Hero meets enemy", 3)) == 3

    def test_generate_falls_back_to_stub_on_error(self, db, project):
        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            wf = generate_possibilities("Hero meets enemy", db, project.id)
        assert len(wf.branches) >= 3
        assert wf.anchor == "Hero meets enemy"

    def test_generate_uses_llm_response(self, db, project):
        resp = json.dumps({"branches": [
            {"title": "Alliance", "description": "They unite.",
             "stakes": "freedom", "consequence": "joined"},
            {"title": "Betrayal", "description": "Trust breaks.",
             "stakes": "trust", "consequence": "split"},
            {"title": "Retreat", "description": "Both withdraw.",
             "stakes": "momentum", "consequence": "delayed"},
        ]})
        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.return_value = (resp, False)
            wf = generate_possibilities("Hero meets enemy", db, project.id)
        titles = [b.title for b in wf.branches]
        assert "Alliance" in titles and "Betrayal" in titles


# --- PSYKE adapter ---

class TestPsykeAdapter:
    def test_gather_psyke_brief_empty(self, db, project):
        assert gather_psyke_brief(db, project.id) == ""

    def test_gather_psyke_brief_lists_chars(self, db, project):
        db.create_psyke_entry(project.id, "Alice", "character", notes="The hero")
        db.create_psyke_entry(project.id, "Bob", "character")
        brief = gather_psyke_brief(db, project.id)
        assert "Alice" in brief and "Bob" in brief
        assert "The hero" in brief

    def test_find_entry_by_name(self, db, project):
        db.create_psyke_entry(project.id, "Alice", "character")
        e = find_entry_by_name(db, project.id, "alice")
        assert e is not None and e.name == "Alice"
        assert find_entry_by_name(db, project.id, "nobody") is None

    def test_apply_creates_new_character(self, db, project):
        branch = Branch.new(
            title="t", description="d",
            state_delta=StateDelta(
                character_changes=[{"name": "Hero", "note": "trained as a knight"}],
            ),
        )
        summary = apply_collapse(db, project.id, branch)
        assert len(summary["characters_created"]) == 1
        e = find_entry_by_name(db, project.id, "Hero")
        assert e is not None
        assert "trained as a knight" in e.notes

    def test_apply_updates_existing_character(self, db, project):
        db.create_psyke_entry(project.id, "Alice", "character", notes="Original.")
        branch = Branch.new(
            title="t", description="d",
            state_delta=StateDelta(
                character_changes=[{"name": "Alice", "note": "Now wary."}],
            ),
        )
        summary = apply_collapse(db, project.id, branch)
        assert len(summary["characters_updated"]) == 1
        e = find_entry_by_name(db, project.id, "Alice")
        assert "Original." in e.notes
        assert "Now wary." in e.notes

    def test_apply_adds_relation(self, db, project):
        db.create_psyke_entry(project.id, "Alice", "character")
        db.create_psyke_entry(project.id, "Bob", "character")
        branch = Branch.new(
            title="t", description="d",
            state_delta=StateDelta(
                new_relations=[{"from": "Alice", "to": "Bob"}],
            ),
        )
        summary = apply_collapse(db, project.id, branch)
        assert len(summary["relations_added"]) == 1
        alice = find_entry_by_name(db, project.id, "Alice")
        related = db.get_related_psyke_entries(alice.id)
        assert any(r.name == "Bob" for r in related)

    def test_apply_skips_relation_with_missing_entry(self, db, project):
        db.create_psyke_entry(project.id, "Alice", "character")
        branch = Branch.new(
            title="t", description="d",
            state_delta=StateDelta(
                new_relations=[{"from": "Alice", "to": "Ghost"}],
            ),
        )
        summary = apply_collapse(db, project.id, branch)
        assert len(summary["relations_added"]) == 0
        assert len(summary["skipped"]) == 1

    def test_apply_skips_malformed(self, db, project):
        branch = Branch.new(
            title="t", description="d",
            state_delta=StateDelta(
                character_changes=[{"name": "", "note": "no name"}],
            ),
        )
        summary = apply_collapse(db, project.id, branch)
        assert len(summary["characters_created"]) == 0
        assert len(summary["skipped"]) == 1


# --- Collapse mechanism ---

class TestCollapse:
    def test_collapse_marks_wavefunction(self, db, project):
        wf = Wavefunction.new(anchor="x", branches=[
            Branch.new(title="A", description="a"),
            Branch.new(title="B", description="b"),
        ])
        get_state(project.id).add(wf)
        result = collapse(db, project.id, wf.id, wf.branches[0].id, archive=False)
        assert wf.is_collapsed()
        assert wf.collapsed_branch_id == wf.branches[0].id
        assert result["chosen"]["title"] == "A"

    def test_collapse_archives_other_branches(self, db, project):
        wf = Wavefunction.new(anchor="x", branches=[
            Branch.new(title="A", description="a"),
            Branch.new(title="B", description="b"),
            Branch.new(title="C", description="c"),
        ])
        get_state(project.id).add(wf)
        result = collapse(db, project.id, wf.id, wf.branches[0].id, archive=False)
        assert len(result["archived"]) == 2

    def test_collapse_unknown_wavefunction(self, db, project):
        with pytest.raises(CollapseError, match="not found"):
            collapse(db, project.id, "nope", "nope", archive=False)

    def test_collapse_unknown_branch(self, db, project):
        wf = Wavefunction.new(anchor="x", branches=[Branch.new(title="A", description="a")])
        get_state(project.id).add(wf)
        with pytest.raises(CollapseError, match="Branch"):
            collapse(db, project.id, wf.id, "nope", archive=False)

    def test_collapse_already_collapsed(self, db, project):
        wf = Wavefunction.new(anchor="x", branches=[Branch.new(title="A", description="a")])
        wf.collapsed_branch_id = wf.branches[0].id
        get_state(project.id).add(wf)
        with pytest.raises(CollapseError, match="already collapsed"):
            collapse(db, project.id, wf.id, wf.branches[0].id, archive=False)

    def test_collapse_writes_to_psyke(self, db, project):
        db.create_psyke_entry(project.id, "Alice", "character")
        branch = Branch.new(
            title="Alliance", description="They unite.",
            state_delta=StateDelta(
                character_changes=[{"name": "Alice", "note": "trusts Bob"}],
            ),
        )
        wf = Wavefunction.new(anchor="x", branches=[branch])
        get_state(project.id).add(wf)
        result = collapse(db, project.id, wf.id, branch.id, archive=False)
        assert len(result["psyke_summary"]["characters_updated"]) == 1
        e = find_entry_by_name(db, project.id, "Alice")
        assert "trusts Bob" in e.notes

    def test_collapse_archive_persists(self, db, project, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "logosforge.quantum_outliner.collapse.CONFIG_DIR", tmp_path
        )
        wf = Wavefunction.new(anchor="x", branches=[
            Branch.new(title="A", description="a"),
            Branch.new(title="B", description="b"),
        ])
        get_state(project.id).add(wf)
        collapse(db, project.id, wf.id, wf.branches[0].id, archive=True)
        archived = load_archive(project.id)
        assert len(archived) == 1
        assert archived[0]["anchor"] == "x"


# --- Relativity ---

class TestRelativity:
    def test_reframe_returns_text(self, db, project):
        with patch(
            "logosforge.quantum_outliner.relativity.chat_completion"
        ) as mock:
            mock.return_value = (
                "PERSPECTIVE: Alice\nMEANING: She sees mercy.\nSTAKES: trust\nSHIFT: less hostile",
                False,
            )
            result = reframe("They fought.", "Alice", db, project.id)
        assert result.kind == "reframe"
        assert "Alice" in result.title
        assert "MEANING" in result.body

    def test_reframe_offline_fallback(self, db, project):
        with patch(
            "logosforge.quantum_outliner.relativity.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = reframe("They fought.", "Alice", db, project.id)
        assert "LLM unavailable" in result.body

    def test_reframe_empty_scene(self):
        result = reframe("", "Alice")
        assert "no scene text" in result.body.lower()

    def test_reframe_uses_psyke_for_pov_brief(self, db, project):
        db.create_psyke_entry(
            project.id, "Alice", "character", notes="A loyal knight.",
        )
        with patch(
            "logosforge.quantum_outliner.relativity.chat_completion"
        ) as mock:
            mock.return_value = ("PERSPECTIVE: Alice\nMEANING: x", False)
            reframe("They fought.", "Alice", db, project.id)
        sent_messages = mock.call_args[0][0]
        user_content = sent_messages[1]["content"]
        assert "loyal knight" in user_content


# --- Uncertainty ---

class TestUncertainty:
    def test_score_empty(self):
        score, reasons = score_scene("")
        assert score == 1.0
        assert "empty" in reasons[0]

    def test_score_short_no_tension(self):
        score, _reasons = score_scene("They walked. Then they sat. Then they slept.")
        assert score >= 0.5

    def test_score_strong_with_tension(self):
        text = (
            "Alice argued with Bob, but he refused to listen. " * 30
            + '"You betray me," she shouted, afraid of what came next.'
        )
        score, _reasons = score_scene(text)
        assert score < 0.4

    def test_find_weak_scenes(self, db, project):
        db.create_scene(project.id, title="Bad", content="Short.")
        db.create_scene(
            project.id, title="Good",
            content=(
                "Alice argued with Bob, but he refused to listen. " * 30
                + '"You betray me," she shouted.'
            ),
        )
        weak = find_uncertainty_zones(db, project.id, threshold=0.3)
        titles = [w.title for w in weak]
        assert "Bad" in titles
        assert "Good" not in titles

    def test_weak_scenes_sorted_by_weakness(self, db, project):
        db.create_scene(project.id, title="Empty", content="")
        db.create_scene(project.id, title="Short", content="A short scene with no tension.")
        weak = find_uncertainty_zones(db, project.id, threshold=0.1)
        assert weak[0].weakness >= weak[-1].weakness


# --- Core agent end-to-end ---

class TestCoreAgent:
    def test_generate_outline_creates_wavefunction(self, db, project):
        get_state(project.id).outline_mode = OutlineMode.LAMBDA
        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_outline(db, project.id, "A knight discovers a curse.")
        assert result.kind == "possibilities"
        assert "Wavefunction" in result.body
        assert len(get_state(project.id).active()) == 1

    def test_generate_outline_empty_premise(self, db, project):
        result = generate_outline(db, project.id, "")
        assert result.kind == "error"

    def test_generate_branches_creates_options(self, db, project):
        get_state(project.id).outline_mode = OutlineMode.LAMBDA
        get_state(project.id).structure_mode = "quantum"
        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_branches(db, project.id, "Hero meets enemy")
        assert result.kind == "possibilities"
        assert "Option 1" in result.body
        wfs = list_active_wavefunctions(project.id)
        assert len(wfs) == 1
        assert len(wfs[0]["branches"]) >= 3

    def test_collapse_branch_returns_summary(self, db, project):
        db.create_psyke_entry(project.id, "Hero", "character")
        get_state(project.id).outline_mode = OutlineMode.LAMBDA
        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            gen = generate_branches(db, project.id, "Hero meets enemy")
        wf_id = gen.payload["wavefunction_id"]
        branch_id = gen.payload["branches"][0]["id"]

        result = collapse_branch(db, project.id, wf_id, branch_id)
        assert result.kind == "collapse"
        assert "COLLAPSED" in result.body
        assert "Archived" in result.body

    def test_collapse_unknown_returns_error_result(self, db, project):
        result = collapse_branch(db, project.id, "nope", "nope")
        assert result.kind == "error"

    def test_detect_weak_scenes_no_scenes(self, db, project):
        result = detect_weak_scenes(db, project.id)
        assert result.kind == "uncertainty"
        assert "No weak scenes" in result.body

    def test_detect_weak_scenes_with_weak(self, db, project):
        db.create_scene(project.id, title="Empty", content="")
        result = detect_weak_scenes(db, project.id, threshold=0.3)
        assert "Empty" in result.body

    def test_collapse_marks_wavefunction_in_state(self, db, project):
        get_state(project.id).outline_mode = OutlineMode.LAMBDA
        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            gen = generate_branches(db, project.id, "Hero meets enemy")
        wf_id = gen.payload["wavefunction_id"]
        branch_id = gen.payload["branches"][0]["id"]
        collapse_branch(db, project.id, wf_id, branch_id)
        active = list_active_wavefunctions(project.id)
        assert len(active) == 0


# --- Required test scenarios from spec ---

class TestSpecScenarios:
    """The five required scenarios from the spec."""

    def test_scenario_1_outline_multiple_branches(self, db, project):
        get_state(project.id).outline_mode = OutlineMode.LAMBDA
        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_outline(db, project.id, "Knight finds a cursed sword.")
        assert len(result.payload["branches"]) >= 3

    def test_scenario_2_select_branch_collapses(self, db, project):
        get_state(project.id).outline_mode = OutlineMode.LAMBDA
        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            gen = generate_branches(db, project.id, "Hero meets enemy")
        wf_id = gen.payload["wavefunction_id"]
        chosen_id = gen.payload["branches"][0]["id"]
        result = collapse_branch(db, project.id, wf_id, chosen_id)
        assert result.kind == "collapse"
        wf = get_state(project.id).get(wf_id)
        assert wf.is_collapsed()
        assert wf.collapsed_branch_id == chosen_id

    def test_scenario_3_switch_pov_different_interpretation(self, db, project):
        responses = iter([
            ("PERSPECTIVE: protagonist\nMEANING: A heroic stand.\nSTAKES: honor\nSHIFT: ennobling", False),
            ("PERSPECTIVE: antagonist\nMEANING: A foolish defiance.\nSTAKES: power\nSHIFT: belittling", False),
        ])
        with patch(
            "logosforge.quantum_outliner.relativity.chat_completion"
        ) as mock:
            mock.side_effect = lambda *_a, **_kw: next(responses)
            r1 = reframe("They fought.", "protagonist", db, project.id)
            r2 = reframe("They fought.", "antagonist", db, project.id)
        assert "heroic" in r1.body
        assert "foolish" in r2.body
        assert r1.body != r2.body

    def test_scenario_4_weak_scene_alternatives_suggested(self, db, project):
        db.create_scene(project.id, title="Filler", content="Then they walked. Then they sat.")
        weak_result = detect_weak_scenes(db, project.id, threshold=0.3)
        assert "Filler" in weak_result.body

        get_state(project.id).outline_mode = OutlineMode.LAMBDA
        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            alt = generate_branches(db, project.id, "Replace filler scene")
        assert len(alt.payload["branches"]) >= 3

    def test_scenario_5_psyke_updated_after_collapse(self, db, project):
        db.create_psyke_entry(project.id, "Alice", "character", notes="Original.")
        db.create_psyke_entry(project.id, "Bob", "character")

        branch = Branch.new(
            title="Alliance",
            description="They join forces.",
            state_delta=StateDelta(
                character_changes=[{"name": "Alice", "note": "now allied with Bob"}],
                new_relations=[{"from": "Alice", "to": "Bob"}],
            ),
        )
        wf = Wavefunction.new(anchor="x", branches=[branch])
        get_state(project.id).add(wf)

        result = collapse_branch(db, project.id, wf.id, branch.id)
        assert result.kind == "collapse"

        alice = find_entry_by_name(db, project.id, "Alice")
        assert "now allied with Bob" in alice.notes
        related = db.get_related_psyke_entries(alice.id)
        assert any(r.name == "Bob" for r in related)
