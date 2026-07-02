"""Logos Phase 5 — PSYKE narrative diagnostics (engine + detectors)."""

from __future__ import annotations

import json
import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.logos.actions import get_action
from logosforge.logos.diagnostics import (
    DiagnosticsEngine,
    NarrativeDiagnostic,
    build_facts,
)
from logosforge.logos.diagnostics.diagnostic import (
    CAT_CHARACTER,
    SEVERITY_IMPORTANT,
    SEVERITY_WARNING,
)
from logosforge.logos.proactive.suppression import SuppressionStore


def _diag(**kw):
    base = dict(category=CAT_CHARACTER, title="t", message="m", evidence="e",
                confidence=0.9, severity=SEVERITY_WARNING,
                target_type="psyke_entry", target_id="1")
    base.update(kw)
    return NarrativeDiagnostic(**base)


# -- Value object ------------------------------------------------------------


def test_diagnostic_serializable_no_secrets():
    d = _diag()
    blob = json.dumps(d.to_dict())
    assert "api_key" not in blob.lower()
    assert d.to_dict()["id"] == d.id


def test_diagnostic_id_stable_and_evidence_sensitive():
    a = _diag(title="X", confidence=0.5)
    b = _diag(title="Y", confidence=0.9)
    assert a.id == b.id                      # cosmetic change -> same id
    assert a.id != _diag(evidence="other").id
    assert a.id != _diag(target_id="2").id


def test_diagnostic_to_suggestion_preserves_target():
    d = _diag(severity=SEVERITY_IMPORTANT, suggested_actions=["suggest_details"])
    sug = d.to_suggestion()
    assert sug.target_type == "psyke_entry" and sug.target_id == "1"
    assert sug.suggested_actions == ["suggest_details"]


# -- Detectors ---------------------------------------------------------------


def _char_project():
    db = Database()
    pid = db.create_project("Saga", narrative_engine="novel").id
    return db, pid


def test_character_missing_details_diagnostic():
    db, pid = _char_project()
    alice = db.create_psyke_entry(pid, "Alice", "character")  # no details/notes
    db.create_scene(pid, "S1", content="Alice arrives.", summary="Alice")
    db.create_scene(pid, "S2", content="Alice fights.", summary="Alice")
    diags = DiagnosticsEngine(db, pid).scan_project()
    assert any(d.category == CAT_CHARACTER and "goals/background" in d.title
               and d.target_id == str(alice.id) for d in diags)


def test_character_disappearance_diagnostic():
    db, pid = _char_project()
    db.create_psyke_entry(pid, "Alice", "character")
    texts = ["Alice arrives", "Alice fights", "Bob alone", "Bob walks",
             "Bob plans", "Bob rests", "Alice returns"]
    for i, t in enumerate(texts):
        db.create_scene(pid, f"S{i}", act="Act I", content=t, summary=t)
    diags = DiagnosticsEngine(db, pid).scan_project()
    assert any("disappears" in d.title.lower() for d in diags)


def test_theme_missing_manifestations_diagnostic():
    db, pid = _char_project()
    db.create_psyke_entry(pid, "Justice", "theme")  # no details
    db.create_scene(pid, "S1", content="Justice matters.", summary="x")
    diags = DiagnosticsEngine(db, pid).scan_project()
    assert any(d.category == "theme" and "manifestations" in d.title.lower()
               for d in diags)


def test_relationless_important_entry_diagnostic():
    db, pid = _char_project()
    db.create_psyke_entry(pid, "Alice", "character", notes="hero")  # has details
    db.create_scene(pid, "S1", content="Alice arrives.", summary="Alice")
    db.create_scene(pid, "S2", content="Alice fights.", summary="Alice")
    diags = DiagnosticsEngine(db, pid).scan_project()
    assert any(d.category == "relationship" and "no relations" in d.title.lower()
               for d in diags)


def test_relation_without_shared_scene_diagnostic():
    db, pid = _char_project()
    a = db.create_psyke_entry(pid, "Alice", "character", notes="x")
    b = db.create_psyke_entry(pid, "Bob", "character", notes="y")
    db.add_psyke_relation(a.id, b.id, relation_type="thematic_echo")
    db.create_scene(pid, "S1", content="Alice alone.", summary="Alice")
    db.create_scene(pid, "S2", content="Bob alone.", summary="Bob")
    diags = DiagnosticsEngine(db, pid).scan_project()
    assert any(d.category == "relationship" and "never share a scene" in d.title.lower()
               for d in diags)


def test_setup_without_payoff_diagnostic():
    db, pid = _char_project()
    db.create_psyke_entry(pid, "Sword", "object", notes="ancient blade")  # appears <=1
    db.create_scene(pid, "S1", content="A Sword on the wall.", summary="intro")
    diags = DiagnosticsEngine(db, pid).scan_project()
    assert any(d.category == "setup_payoff" for d in diags)


def test_outline_empty_node_diagnostic():
    db, pid = _char_project()
    db.create_scene(pid, "Mystery", act="Act I")  # no summary/goal
    diags = DiagnosticsEngine(db, pid).scan_project()
    assert any(d.category == "structure" and "dramatic function" in d.title.lower()
               for d in diags)


def test_continuity_progression_without_scene_link():
    db, pid = _char_project()
    e = db.create_psyke_entry(pid, "Alice", "character", notes="x")
    db.create_psyke_progression(e.id, "starts naive", scene_id=None)
    db.create_psyke_progression(e.id, "grows", scene_id=None)
    diags = DiagnosticsEngine(db, pid).scan_project()
    assert any(d.category == "continuity" and "no scene link" in d.title.lower()
               for d in diags)


def test_controlling_idea_unaligned_diagnostic():
    db, pid = _char_project()
    from logosforge.controlling_idea import ControllingIdea, save
    ci = ControllingIdea(enabled=True, statement="Love conquers fear.")
    save(db, pid, ci)
    db.create_scene(pid, "S1", content="x", summary="y")
    diags = DiagnosticsEngine(db, pid).scan_project()
    assert any(d.title.startswith("Controlling Idea") for d in diags)


# -- Engine behaviour --------------------------------------------------------


def test_to_suggestions_only_high_severity():
    db, pid = _char_project()
    db.create_psyke_entry(pid, "Alice", "character")
    for i in range(3):
        db.create_scene(pid, f"S{i}", content="Alice acts.", summary="Alice")
    engine = DiagnosticsEngine(db, pid)
    diags = engine.scan_project()
    sugs = engine.to_suggestions(diags)
    assert sugs  # at least the important "no goals/background"
    assert all(s.severity in ("important",) for s in sugs)


def test_all_suggested_actions_are_real():
    db, pid = _char_project()
    a = db.create_psyke_entry(pid, "Alice", "character")
    b = db.create_psyke_entry(pid, "Bob", "character", notes="x")
    db.add_psyke_relation(a.id, b.id, relation_type="")
    db.create_scene(pid, "Empty", act="Act I")
    db.create_scene(pid, "S1", content="Alice.", summary="x", plotline="Sub")
    db.create_scene(pid, "S2", content="Alice.", summary="x", plotline="Sub")
    for d in DiagnosticsEngine(db, pid).scan_project():
        for action_name in d.suggested_actions:
            assert get_action(action_name) is not None, action_name


def test_dismissed_diagnostics_do_not_reappear():
    db, pid = _char_project()
    db.create_psyke_entry(pid, "Alice", "character")
    db.create_scene(pid, "S1", content="Alice acts.", summary="Alice")
    store = SuppressionStore()
    engine = DiagnosticsEngine(db, pid, suppression=store)
    diags = engine.scan_project()
    target = diags[0]
    store.dismiss(target.to_suggestion().id)
    after = engine.scan_project()
    assert target.id not in {d.id for d in after}


def test_scan_does_not_mutate_db():
    db, pid = _char_project()
    db.create_psyke_entry(pid, "Alice", "character")
    db.create_scene(pid, "S1", content="Alice acts.", summary="x")
    before = (len(db.get_all_scenes(pid)), len(db.get_all_psyke_entries(pid)))
    engine = DiagnosticsEngine(db, pid)
    engine.scan_project()
    engine.scan_section("PSYKE")
    engine.scan_section("Graph")
    after = (len(db.get_all_scenes(pid)), len(db.get_all_psyke_entries(pid)))
    assert before == after


def test_no_llm_calls_during_scan(monkeypatch):
    import logosforge.assistant as assistant
    calls = []
    monkeypatch.setattr(assistant, "chat_completion",
                        lambda *a, **k: calls.append(1) or ("", False))
    db, pid = _char_project()
    db.create_psyke_entry(pid, "Alice", "character")
    db.create_scene(pid, "S1", content="Alice.", summary="x")
    DiagnosticsEngine(db, pid).scan_project()
    assert calls == []


def test_facts_snapshot_is_read_only():
    db, pid = _char_project()
    db.create_psyke_entry(pid, "Alice", "character")
    db.create_scene(pid, "S1", content="Alice.", summary="x")
    before = (len(db.get_all_scenes(pid)), len(db.get_all_psyke_entries(pid)))
    facts = build_facts(db, pid)
    assert facts.total_scenes == 1
    assert before == (len(db.get_all_scenes(pid)), len(db.get_all_psyke_entries(pid)))
