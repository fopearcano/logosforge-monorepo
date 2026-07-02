"""Logos Phase 4 — proactive contextual suggestions.

Covers: suggestion serialization + stable id, confidence-threshold and severity
filtering, dismiss/snooze/hide-type suppression, dedup, rule detectors per
section, suggested-action mapping to real Logos actions, scan-does-not-mutate,
disabled-setting suppression, and that Assistant stays untouched. Prior Logos
phases run separately and must stay green.
"""

from __future__ import annotations

import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.logos.actions import get_action
from logosforge.logos.context import build_logos_context
from logosforge.logos.proactive import (
    ProactiveConfig,
    ProactiveEngine,
    SuppressionStore,
)
from logosforge.logos.proactive.detectors import SECTION_DETECTORS
from logosforge.logos.proactive.suggestion import (
    SEVERITY_IMPORTANT,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    TYPE_PSYKE,
    LogosSuggestion,
)


def _suggestion(**kw):
    base = dict(type=TYPE_PSYKE, title="t", message="m", section_name="PSYKE",
                evidence="e", confidence=0.9, severity=SEVERITY_WARNING,
                target_type="psyke_entry", target_id="1")
    base.update(kw)
    return LogosSuggestion(**base)


# -- Suggestion value object -------------------------------------------------


def test_suggestion_serializable():
    import json
    s = _suggestion()
    blob = json.dumps(s.to_dict())
    assert "api_key" not in blob.lower()
    d = s.to_dict()
    assert d["id"] == s.id and d["type"] == TYPE_PSYKE


def test_suggestion_id_stable_across_cosmetic_changes():
    a = _suggestion(title="X", message="one", confidence=0.7)
    b = _suggestion(title="Y", message="two", confidence=0.9)
    assert a.id == b.id  # same type/target/evidence


def test_suggestion_id_changes_with_evidence_or_target():
    a = _suggestion(evidence="e1")
    assert a.id != _suggestion(evidence="e2").id
    assert a.id != _suggestion(target_id="2").id


def test_is_active_respects_dismiss_and_snooze():
    import time
    assert _suggestion().is_active()
    assert not _suggestion(dismissed=True).is_active()
    assert not _suggestion(snoozed_until=time.time() + 1000).is_active()
    assert _suggestion(snoozed_until=time.time() - 10).is_active()


# -- Engine filtering --------------------------------------------------------


def _engine(db, pid, **cfg):
    return ProactiveEngine(db, pid, config=ProactiveConfig(**cfg),
                           suppression=SuppressionStore())


def test_threshold_filters_low_confidence():
    db = Database(); pid = db.create_project("P").id
    db.create_psyke_entry(pid, "Alice", "character")
    assert _engine(db, pid, threshold=0.99).scan_section("PSYKE") == []
    assert _engine(db, pid, threshold=0.5).scan_section("PSYKE")  # shows


def test_severity_setting_filters():
    db = Database(); pid = db.create_project("P").id
    db.create_psyke_entry(pid, "Alice", "character")
    # All PSYKE detail-less findings here are warning/important; turning warnings
    # off should drop the warning-level ones.
    eng = _engine(db, pid, show_warning=False, show_info=False, threshold=0.5)
    out = eng.scan_section("PSYKE")
    assert all(s.severity == SEVERITY_IMPORTANT for s in out)


def test_disabled_engine_returns_nothing():
    db = Database(); pid = db.create_project("P").id
    db.create_psyke_entry(pid, "Alice", "character")
    assert _engine(db, pid, enabled=False).scan_section("PSYKE") == []


def test_dedup_same_id():
    db = Database(); pid = db.create_project("P").id
    eng = _engine(db, pid)
    dup = [_suggestion(), _suggestion()]  # identical id
    filtered = eng._filter(dup)
    assert len(filtered) == 1


# -- Suppression -------------------------------------------------------------


def test_dismiss_hides_suggestion():
    db = Database(); pid = db.create_project("P").id
    db.create_psyke_entry(pid, "Alice", "character")
    store = SuppressionStore()
    eng = ProactiveEngine(db, pid, config=ProactiveConfig(threshold=0.5), suppression=store)
    first = eng.scan_section("PSYKE")[0]
    store.dismiss(first.id)
    assert first.id not in {s.id for s in eng.scan_section("PSYKE")}


def test_snooze_then_active_again():
    store = SuppressionStore()
    s = _suggestion()
    store.snooze(s.id, seconds=1000)
    assert store.is_suppressed(s)
    store.snooze(s.id, seconds=-1)  # already elapsed
    assert not store.is_suppressed(s)


def test_hide_type_suppresses_whole_type():
    store = SuppressionStore()
    store.hide_type(TYPE_PSYKE)
    assert store.is_suppressed(_suggestion(type=TYPE_PSYKE))
    assert not store.is_suppressed(_suggestion(type="structure", target_id="9"))


def test_suppression_persists_in_project_settings():
    db = Database(); pid = db.create_project("P").id
    s = _suggestion()
    store = SuppressionStore(db, pid)
    store.dismiss(s.id)
    # A fresh store for the same project reloads the dismissed id.
    store2 = SuppressionStore(db, pid)
    assert store2.is_suppressed(s)


# -- Rule detectors ----------------------------------------------------------


def test_detector_empty_psyke_character_details():
    db = Database(); pid = db.create_project("P").id
    alice = db.create_psyke_entry(pid, "Alice", "character")
    db.create_scene(pid, "Opening", content="Alice walks. " * 10, summary="Alice")
    out = _engine(db, pid, threshold=0.5).scan_section("PSYKE")
    assert any(s.target_id == str(alice.id) and "no details" in s.title for s in out)


def test_detector_isolated_graph_node():
    db = Database(); pid = db.create_project("P").id
    db.create_psyke_entry(pid, "Lonely", "character")  # no links, no relations
    out = _engine(db, pid).scan_section("Graph")
    assert any("isolated" in s.title.lower() for s in out)


def test_detector_empty_outline_node():
    db = Database(); pid = db.create_project("P").id
    db.create_scene(pid, "Mystery Scene", act="Act I")  # no summary/goal
    out = _engine(db, pid, threshold=0.5).scan_section("Outline")
    assert any("dramatic function" in s.title.lower() for s in out)


def test_detector_timeline_gap_between_acts():
    db = Database(); pid = db.create_project("P").id
    db.create_scene(pid, "End of Act I", act="Act I")
    db.create_scene(pid, "Start of Act II", act="Act II")
    out = _engine(db, pid).scan_section("Timeline")
    assert any("timeline gap" in s.title.lower() for s in out)


def test_detector_plot_block_without_conflict():
    db = Database(); pid = db.create_project("P").id
    db.create_scene(pid, "S1", plotline="Subplot")
    db.create_scene(pid, "S2", plotline="Subplot")  # both no conflict/summary
    out = _engine(db, pid).scan_section("Plot")
    assert any("no stated conflict" in s.title.lower() for s in out)


def test_manuscript_detector_uses_current_scene():
    db = Database(); pid = db.create_project("P").id
    sid = db.create_scene(pid, "Tiny", content="short").id  # short, no summary
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    out = _engine(db, pid).scan_section("Manuscript", ctx)
    assert any(s.target_id == str(sid) for s in out)


# -- Action mapping ----------------------------------------------------------


def test_all_suggested_actions_are_real_logos_actions():
    db = Database(); pid = db.create_project("P").id
    alice = db.create_psyke_entry(pid, "Alice", "character")
    db.create_scene(pid, "Opening", content="Alice " * 30, summary="x", act="Act I")
    db.create_scene(pid, "Next", act="Act II", plotline="Sub")
    eng = _engine(db, pid, threshold=0.4)
    for section in ("PSYKE", "Graph", "Outline", "Timeline", "Plot"):
        for s in eng.scan_section(section):
            for action_name in s.suggested_actions:
                assert get_action(action_name) is not None, action_name


# -- No mutation -------------------------------------------------------------


def test_scan_does_not_mutate_db():
    db = Database(); pid = db.create_project("P").id
    db.create_psyke_entry(pid, "Alice", "character")
    db.create_scene(pid, "S1", act="Act I", plotline="Sub")
    db.create_scene(pid, "S2", act="Act II", plotline="Sub")
    before = (len(db.get_all_scenes(pid)), len(db.get_all_psyke_entries(pid)))
    eng = _engine(db, pid, threshold=0.4)
    for section in SECTION_DETECTORS:
        eng.scan_section(section, build_logos_context(db, pid, section_name=section))
    after = (len(db.get_all_scenes(pid)), len(db.get_all_psyke_entries(pid)))
    assert before == after


# -- Config from settings ----------------------------------------------------


def test_config_defaults_from_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path, raising=False)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "s.json", raising=False)
    cfg = ProactiveConfig.from_settings()
    assert cfg.enabled is True
    assert cfg.threshold == 0.65
    assert cfg.ai_scan_enabled is False  # AI scan off by default
    settings._instance = None
