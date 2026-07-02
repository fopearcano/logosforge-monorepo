"""Tests for PSYKE-progression and structure-beat sensitivity in scoring.

Demonstrates that the same branches yield different rankings when PSYKE
character state (progressions) or current structural beat changes.
"""

import pytest

from logosforge.quantum_outliner.psyke_adapter import PsykeSignals
from logosforge.quantum_outliner.scoring import (
    _score_psyke_consistency,
    _score_structure_fit,
    apply_scores,
    compute_factors,
    score_branches,
)
from logosforge.quantum_outliner.state import Branch, Wavefunction


def _branch(**kw) -> Branch:
    defaults = {"title": "Test", "description": "Desc"}
    defaults.update(kw)
    return Branch.new(**defaults)


def _wf(*branches, **kw) -> Wavefunction:
    wf = Wavefunction.new(anchor="Test", branches=list(branches))
    for k, v in kw.items():
        setattr(wf, k, v)
    return wf


# ---------------------------------------------------------------------------
# PSYKE Progressions shift scoring
# ---------------------------------------------------------------------------


class TestProgressionSensitivity:
    """Same branches, different PSYKE progressions → different ranking."""

    def test_progression_boosts_matching_branch(self):
        b_fight = _branch(
            title="Marcus fights back",
            description="Marcus confronts the betrayer in a desperate battle",
            stakes="survival",
            consequence="Marcus wounded",
        )
        b_flee = _branch(
            title="Elena escapes north",
            description="Elena flees through the forest toward safety",
            stakes="freedom",
            consequence="Elena reaches the border",
        )

        psyke_marcus = PsykeSignals(
            characters=[{"name": "Marcus", "notes": "warrior"}],
            keywords=frozenset({"marcus", "warrior", "fights"}),
            progressions=[{"name": "Marcus", "text": "Marcus desperate to fight"}],
        )
        psyke_elena = PsykeSignals(
            characters=[{"name": "Elena", "notes": "scout"}],
            keywords=frozenset({"elena", "scout", "escapes"}),
            progressions=[{"name": "Elena", "text": "Elena flees toward safety"}],
        )

        score_fight_m = _score_psyke_consistency(b_fight, psyke_marcus)
        score_fight_e = _score_psyke_consistency(b_fight, psyke_elena)

        assert score_fight_m > score_fight_e

        score_flee_e = _score_psyke_consistency(b_flee, psyke_elena)
        score_flee_m = _score_psyke_consistency(b_flee, psyke_marcus)

        assert score_flee_e > score_flee_m

    def test_no_progressions_gives_neutral(self):
        b = _branch(
            title="Marcus fights",
            description="A desperate battle",
        )
        psyke_no_prog = PsykeSignals(
            characters=[{"name": "Marcus", "notes": "warrior"}],
            keywords=frozenset({"marcus", "warrior"}),
            progressions=[],
        )
        psyke_with_prog = PsykeSignals(
            characters=[{"name": "Marcus", "notes": "warrior"}],
            keywords=frozenset({"marcus", "warrior"}),
            progressions=[{"name": "Marcus", "text": "Marcus desperate battle"}],
        )

        score_without = _score_psyke_consistency(b, psyke_no_prog)
        score_with = _score_psyke_consistency(b, psyke_with_prog)

        assert score_with > score_without

    def test_progression_changes_ranking(self):
        b_fight = _branch(
            title="Marcus fights back",
            description="Marcus confronts the betrayer in a desperate battle",
            stakes="survival",
            consequence="Marcus wounded",
        )
        b_flee = _branch(
            title="Elena escapes north",
            description="Elena flees through the forest toward safety",
            stakes="freedom",
            consequence="Elena reaches the border",
        )

        wf = _wf(b_fight, b_flee)

        psyke_marcus = PsykeSignals(
            characters=[{"name": "Marcus", "notes": "warrior"}],
            keywords=frozenset({"marcus", "warrior", "fights", "battle"}),
            progressions=[{"name": "Marcus", "text": "Marcus desperate to fight"}],
        )

        scored_m = score_branches(wf, psyke=psyke_marcus)
        fight_first = scored_m[0].branch_id == b_fight.id

        psyke_elena = PsykeSignals(
            characters=[{"name": "Elena", "notes": "scout"}],
            keywords=frozenset({"elena", "scout", "escapes", "flees"}),
            progressions=[{"name": "Elena", "text": "Elena flees toward safety"}],
        )

        scored_e = score_branches(wf, psyke=psyke_elena)
        flee_first = scored_e[0].branch_id == b_flee.id

        assert fight_first and flee_first

    def test_progression_adds_to_score(self):
        b = _branch(
            title="Marcus betrays the council",
            description="Marcus reveals the secret and confronts danger",
            stakes="trust",
            consequence="war erupts",
        )
        no_prog = PsykeSignals(
            characters=[{"name": "Marcus", "notes": "warrior"}],
            keywords=frozenset({"marcus"}),
            progressions=[],
        )
        with_prog = PsykeSignals(
            characters=[{"name": "Marcus", "notes": "warrior"}],
            keywords=frozenset({"marcus"}),
            progressions=[{"name": "Marcus", "text": "Marcus reveals secret"}],
        )
        score_no = _score_psyke_consistency(b, no_prog)
        score_with = _score_psyke_consistency(b, with_prog)
        assert score_with > score_no


class TestProgressionKeywordEnrichment:
    """Progressions enrich the keyword pool via gather_psyke_signals."""

    def test_progression_words_become_keywords(self):
        psyke = PsykeSignals(
            characters=[{"name": "Kai", "notes": "thief"}],
            keywords=frozenset({"kai", "thief", "betrayal", "desperate"}),
            progressions=[{"name": "Kai", "text": "Kai desperate after betrayal"}],
        )

        b = _branch(
            title="Kai runs", description="Desperate escape after betrayal",
        )
        score = _score_psyke_consistency(b, psyke)
        assert score > 0.5


# ---------------------------------------------------------------------------
# Structure beat sensitivity
# ---------------------------------------------------------------------------


class TestStructureBeatSensitivity:
    def test_exact_beat_match_scores_highest(self):
        b = _branch(structure_beat="midpoint reversal")
        wf = _wf(b, structure_beat="midpoint reversal")
        score = _score_structure_fit(b, wf)
        assert score >= 0.5

    def test_partial_beat_overlap_scores_mid(self):
        b = _branch(structure_beat="midpoint reversal")
        wf = _wf(b, structure_beat="midpoint crisis")
        score = _score_structure_fit(b, wf)
        assert 0.0 < score < 0.5

    def test_no_beat_overlap_scores_zero_from_beat(self):
        b = _branch(structure_beat="inciting incident")
        wf = _wf(b, structure_beat="climax resolution")
        score_beat_only = _score_structure_fit(b, wf)
        b_none = _branch()
        score_none = _score_structure_fit(b_none, wf)
        assert score_beat_only <= score_none + 0.01

    def test_beat_change_shifts_ranking(self):
        b_mid = _branch(
            title="Midpoint turn",
            description="Everything reverses",
            structure_beat="midpoint reversal",
            branch_type="intensification",
        )
        b_climax = _branch(
            title="Climax battle",
            description="Final confrontation",
            structure_beat="climax",
            branch_type="resolution",
        )

        wf_mid = _wf(b_mid, b_climax, structure_beat="midpoint reversal")
        scored_mid = score_branches(wf_mid)
        mid_first = scored_mid[0].branch_id == b_mid.id

        wf_climax = _wf(b_mid, b_climax, structure_beat="climax")
        scored_climax = score_branches(wf_climax)
        climax_first = scored_climax[0].branch_id == b_climax.id

        assert mid_first and climax_first

    def test_partial_method_match_scores_mid(self):
        b = _branch(structure_method="hero")
        wf = _wf(b, structure_method="hero's journey")
        score = _score_structure_fit(b, wf)
        assert score >= 0.15

    def test_exact_method_match_scores_full(self):
        b = _branch(structure_method="save the cat")
        wf = _wf(b, structure_method="save the cat")
        score = _score_structure_fit(b, wf)
        assert score >= 0.3

    def test_no_method_no_beat_only_type(self):
        b = _branch(branch_type="intensification")
        wf = _wf(b)
        score = _score_structure_fit(b, wf)
        assert score == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# Combined: different PSYKE + structure → different ranking
# ---------------------------------------------------------------------------


class TestCombinedSensitivity:
    def test_psyke_and_beat_together_shift_ranking(self):
        b_fight = _branch(
            title="Marcus fights",
            description="Marcus desperate battle confrontation",
            stakes="survival",
            consequence="wounded",
            structure_beat="midpoint reversal",
            branch_type="intensification",
        )
        b_peace = _branch(
            title="Elena negotiates peace",
            description="Elena diplomatic resolution talks",
            stakes="alliance",
            consequence="treaty",
            structure_beat="climax",
            branch_type="resolution",
        )

        psyke_fight = PsykeSignals(
            characters=[{"name": "Marcus", "notes": "warrior"}],
            keywords=frozenset({"marcus", "warrior", "battle", "desperate"}),
            progressions=[{"name": "Marcus", "text": "Marcus desperate for battle"}],
        )
        wf_mid = _wf(b_fight, b_peace, structure_beat="midpoint reversal")
        scored = score_branches(wf_mid, psyke=psyke_fight)
        assert scored[0].branch_id == b_fight.id

        psyke_peace = PsykeSignals(
            characters=[{"name": "Elena", "notes": "diplomat"}],
            keywords=frozenset({"elena", "diplomat", "peace", "negotiates"}),
            progressions=[{"name": "Elena", "text": "Elena seeks diplomatic resolution"}],
        )
        wf_climax = _wf(b_fight, b_peace, structure_beat="climax")
        scored2 = score_branches(wf_climax, psyke=psyke_peace)
        assert scored2[0].branch_id == b_peace.id
