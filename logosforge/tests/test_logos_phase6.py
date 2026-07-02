"""Logos Phase 6 — Narrative Health Engine."""

from __future__ import annotations

import json
import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.logos.actions import get_action
from logosforge.logos.health import (
    HealthEngine,
    NarrativeHealthMetric,
    NarrativeHealthReport,
    top_risks_text,
)
from logosforge.logos.health import metric as M
from logosforge.logos.proactive.suppression import SuppressionStore


def _empty():
    db = Database()
    pid = db.create_project("Empty", narrative_engine="novel").id
    return db, pid


def _rich():
    db = Database()
    pid = db.create_project("Saga", narrative_engine="novel").id
    db.create_psyke_entry(pid, "Alice", "character")          # no details
    db.create_psyke_entry(pid, "Justice", "theme")            # no manifestations
    db.create_psyke_entry(pid, "Sword", "object", notes="ancient blade")
    texts = ["Alice arrives. Justice.", "Alice fights.", "Bob alone.",
             "Bob walks.", "Bob plans.", "Bob rests.", "Alice returns. Justice."]
    for i, t in enumerate(texts):
        db.create_scene(pid, f"S{i}", act="Act I" if i < 4 else "Act III",
                        content=t, summary="" if i in (2, 3, 4) else t)
    return db, pid


# -- Serialization -----------------------------------------------------------


def test_metric_serializable():
    m = NarrativeHealthMetric(category=M.CAT_CHARACTER, status=M.STATUS_WEAK,
                              evidence="x")
    d = m.to_dict()
    assert d["status_label"] == "Weak Area"
    assert d["id"].startswith("m_")
    json.dumps(d)  # must serialize


def test_report_serializable_json_and_markdown():
    db, pid = _rich()
    rep = HealthEngine(db, pid).generate_report()
    assert isinstance(json.loads(rep.to_json()), dict)
    md = rep.to_markdown()
    assert md.startswith("# Narrative Health")
    assert "Category Status" in md


# -- Aggregation -------------------------------------------------------------


def test_diagnostics_aggregate_into_metrics():
    db, pid = _rich()
    rep = HealthEngine(db, pid).generate_report()
    assert len(rep.metrics) == len(M.ALL_CATEGORIES)
    # Each category appears exactly once.
    assert {m.category for m in rep.metrics} == set(M.ALL_CATEGORIES)


def test_missing_data_is_unknown_not_bad():
    db, pid = _empty()
    rep = HealthEngine(db, pid).generate_report()
    assert rep.overall_status == M.STATUS_UNKNOWN
    assert all(m.status == M.STATUS_UNKNOWN for m in rep.metrics)
    # Crucially: never reported as weak/critical when there's no data.
    assert not any(m.is_problem for m in rep.metrics)


def test_character_diagnostics_affect_character_health():
    db, pid = _rich()
    rep = HealthEngine(db, pid).generate_report()
    char = rep.metric_for(M.CAT_CHARACTER)
    assert char is not None and char.is_problem  # Alice has no details + gaps


def test_theme_diagnostics_affect_theme_health():
    db, pid = _rich()
    rep = HealthEngine(db, pid).generate_report()
    theme = rep.metric_for(M.CAT_THEME)
    assert theme is not None and theme.status_rank >= M.STATUS_RANK[M.STATUS_WATCH]


def test_continuity_unknown_without_progressions():
    db, pid = _rich()  # no progressions
    rep = HealthEngine(db, pid).generate_report()
    cont = rep.metric_for(M.CAT_CONTINUITY)
    assert cont.status == M.STATUS_UNKNOWN


def test_continuity_diagnostics_affect_continuity_health():
    db, pid = _rich()
    e = db.get_all_psyke_entries(pid)[0]
    db.create_psyke_progression(e.id, "starts", scene_id=None)
    db.create_psyke_progression(e.id, "grows", scene_id=None)
    rep = HealthEngine(db, pid).generate_report()
    cont = rep.metric_for(M.CAT_CONTINUITY)
    assert cont.status != M.STATUS_UNKNOWN  # now there is data
    assert cont.related_diagnostics  # the unanchored-progression finding


def test_setup_payoff_diagnostics_affect_setup_payoff_health():
    db, pid = _rich()  # Sword object with notes, appears once
    rep = HealthEngine(db, pid).generate_report()
    sp = rep.metric_for(M.CAT_SETUP_PAYOFF)
    assert sp is not None and sp.is_known


def test_psyke_completeness_affects_psyke_health():
    db, pid = _rich()
    rep = HealthEngine(db, pid).generate_report()
    psyke = rep.metric_for(M.CAT_PSYKE)
    assert psyke is not None and psyke.is_problem  # Alice/Justice no details


def test_graph_isolation_affects_graph_health():
    db, pid = _empty()
    # Two isolated important entries -> two warnings -> weak.
    db.create_psyke_entry(pid, "Lonely", "character")
    db.create_psyke_entry(pid, "Drifter", "character")
    rep = HealthEngine(db, pid).generate_report()
    graph = rep.metric_for(M.CAT_GRAPH)
    assert graph is not None
    assert graph.status != M.STATUS_STABLE  # isolation registered
    assert graph.related_diagnostics


# -- Overall status ----------------------------------------------------------


def test_overall_status_weak_when_core_weak():
    db, pid = _rich()
    rep = HealthEngine(db, pid).generate_report()
    assert rep.overall_status in (M.STATUS_WEAK, M.STATUS_CRITICAL)


def test_overall_stable_when_only_minor():
    db = Database()
    pid = db.create_project("Tidy", narrative_engine="novel").id
    # A well-formed character + scene, no warnings.
    e = db.create_psyke_entry(pid, "Hero", "character",
                              notes="goals and background filled")
    db.create_scene(pid, "Open", act="Act I", content="Hero acts.",
                    summary="Hero begins", goal="win")
    db.add_psyke_relation(e.id, db.create_psyke_entry(pid, "Foil", "character",
                                                      notes="x").id)
    rep = HealthEngine(db, pid).generate_report()
    assert rep.overall_status in (M.STATUS_STABLE, M.STATUS_WATCH)


# -- Recommendations ---------------------------------------------------------


def test_recommendations_generated_from_diagnostics():
    db, pid = _rich()
    rep = HealthEngine(db, pid).generate_report()
    assert rep.recommendations
    for r in rep.recommendations:
        assert r.problem and r.why and r.evidence
        if r.suggested_action:
            assert get_action(r.suggested_action) is not None


def test_top_risks_and_strengths_populated():
    db, pid = _rich()
    rep = HealthEngine(db, pid).generate_report()
    assert rep.top_risks  # has problems
    # Strengths are stable categories (timeline/graph here).
    assert isinstance(rep.strengths, list)


# -- Safety ------------------------------------------------------------------


def test_health_report_does_not_mutate_db():
    db, pid = _rich()
    before = (len(db.get_all_scenes(pid)), len(db.get_all_psyke_entries(pid)))
    HealthEngine(db, pid).generate_report()
    HealthEngine(db, pid).generate_report()
    after = (len(db.get_all_scenes(pid)), len(db.get_all_psyke_entries(pid)))
    assert before == after


def test_no_llm_calls_during_health_scan(monkeypatch):
    import logosforge.assistant as assistant
    calls = []
    monkeypatch.setattr(assistant, "chat_completion",
                        lambda *a, **k: calls.append(1) or ("", False))
    db, pid = _rich()
    HealthEngine(db, pid).generate_report()
    assert calls == []


def test_suppressed_diagnostics_excluded_from_report():
    db, pid = _rich()
    store = SuppressionStore()
    rep = HealthEngine(db, pid, suppression=store).generate_report()
    # Dismiss the first diagnostic id and confirm it leaves the report.
    assert rep.diagnostic_ids
    # Map diagnostic id -> suggestion id by regenerating with no suppression.
    from logosforge.logos.diagnostics import DiagnosticsEngine
    diags = DiagnosticsEngine(db, pid).scan_project()
    target = diags[0]
    store.dismiss(target.to_suggestion().id)
    rep2 = HealthEngine(db, pid, suppression=store).generate_report()
    assert target.id not in rep2.diagnostic_ids


# -- Assistant context (opt-in) ----------------------------------------------


def test_top_risks_text_compact_block():
    db, pid = _rich()
    rep = HealthEngine(db, pid).generate_report()
    text = top_risks_text(rep)
    assert text.startswith("[Narrative Health]")
    assert "Overall:" in text


def test_top_risks_text_empty_when_stable():
    db, pid = _empty()  # unknown overall, no risks
    rep = HealthEngine(db, pid).generate_report()
    assert top_risks_text(rep) == ""
