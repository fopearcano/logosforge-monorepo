"""Tests for the Writer QA harness (headless, deterministic, no real provider).

Proves the harness loads scenarios, runs the fake provider, evaluates against
the real Assistant contract layer, correctly classifies safe vs unsafe behavior,
emits JSON/Markdown reports, and gates CI via exit code — touching no real
provider, cloud, GitHub, or files outside the chosen report path.
"""

from __future__ import annotations

import json
import warnings

warnings.filterwarnings("ignore")

from logosforge.assistant_contract import route, validate
from tools.writer_qa import run_writer_qa
from tools.writer_qa.fake_provider import (
    FakeProvider, FakeProviderError, RESPONSES,
)
from tools.writer_qa.reporting import summarize, write_reports
from tools.writer_qa.scenarios import core_scenarios, get_suite
from tools.writer_qa.validators import evaluate_scenario, run_suite


def _by_name(name):
    for s in core_scenarios():
        if s.name == name:
            return s
    raise KeyError(name)


# 1. Scenarios load (and suites filter).
def test_scenarios_load():
    assert len(get_suite("all")) > 30
    man = get_suite("manuscript")
    assert man and all(s.section == "Manuscript" for s in man)


# 2. Fake provider is deterministic and offline; provider_error raises.
def test_fake_provider_deterministic():
    fp = FakeProvider()
    assert fp.respond("valid_novel_prose") == fp.respond("valid_novel_prose")
    assert "valid_screenplay_dialogue" in RESPONSES
    try:
        fp.respond("provider_error")
        assert False, "expected error"
    except FakeProviderError:
        pass


# 3-4. JSON + Markdown reports are written and parseable.
def test_reports_written(tmp_path):
    bugs, total = run_suite(get_suite("all"))
    summary = summarize(bugs, total)
    jp, mp = write_reports(bugs, summary, str(tmp_path / "latest"))
    assert jp.endswith(".json") and mp.endswith(".md")
    data = json.loads((tmp_path / "latest.json").read_text())
    assert data["summary"]["scenarios_run"] == total
    assert "# Writer QA Report" in (tmp_path / "latest.md").read_text()


# 5. A valid screenplay direct scenario passes (no bug).
def test_valid_screenplay_passes():
    assert evaluate_scenario(
        _by_name("screenplay.manuscript.Dialogue.valid")) is None


# 6-7. Planning leakage is correctly blocked by the system → no bug.
def test_planning_is_blocked_no_bug():
    assert evaluate_scenario(
        _by_name("screenplay.manuscript.dialogue.planning_blocked")) is None
    # And the underlying contract really blocks it:
    c = route(section="Manuscript", writing_mode="screenplay", action="Dialogue")
    res = validate(RESPONSES["invalid_planning_markdown"], c)
    assert res.status == "invalid" and res.apply_allowed is False


# 8. Invalid output is not cache-allowed.
def test_invalid_not_cacheable():
    c = route(section="Manuscript", writing_mode="novel", action="generate")
    assert validate(RESPONSES["invalid_planning_markdown"], c).cache_allowed is False


# 9 + 12. Wrong-mode output is surfaced as a BLOCKER (a real validator gap).
def test_wrong_mode_is_blocker():
    bug = evaluate_scenario(_by_name("screenplay.manuscript.dialogue.wrong_mode"))
    assert bug is not None and bug.severity == "BLOCKER"
    assert "wrong-mode" in bug.actual_behavior


# 10. Hidden-context dumps are detected (blocked) by the validator.
def test_hidden_context_detected():
    c = route(section="Manuscript", writing_mode="novel", action="Dialogue")
    assert validate(RESPONSES["invalid_context_dump"], c).status == "invalid"


# 11. Missing target for direct writing → clarification (no bug).
def test_missing_target_clarifies():
    sc = _by_name("screenplay.manuscript.dialogue.no_target")
    assert evaluate_scenario(sc) is None
    c = route(section="Manuscript", writing_mode="screenplay", action="Dialogue",
              has_target=False)
    assert c.needs_clarification is True


# 12b. Empty output is flagged HIGH (usability gap), not BLOCKER.
def test_empty_output_is_high():
    bug = evaluate_scenario(_by_name("novel.manuscript.dialogue.empty"))
    assert bug is not None and bug.severity == "HIGH"
    assert "empty" in bug.actual_behavior


# 13-14. Bugs carry reproduction steps + expected/actual.
def test_bug_has_repro_and_expected_actual():
    bug = evaluate_scenario(_by_name("screenplay.manuscript.dialogue.wrong_mode"))
    assert len(bug.reproduction_steps) >= 3
    assert bug.expected_behavior and bug.actual_behavior
    assert bug.suggested_fix_area


# 15. Exit code fails on BLOCKER (the full suite finds wrong-mode blockers).
def test_exit_code_fails_on_blocker(tmp_path):
    rc = run_writer_qa.main(["--suite", "all",
                             "--report", str(tmp_path / "r")])
    assert rc == 1
    assert (tmp_path / "r.json").exists()


# 16. Exit code passes when a suite has no blockers (outline-only).
def test_exit_code_passes_without_blockers(tmp_path):
    rc = run_writer_qa.main(["--suite", "outline",
                             "--report", str(tmp_path / "o")])
    assert rc == 0


# 17-18. No real provider / cloud / GitHub call during a run.
def test_no_external_calls(monkeypatch):
    from logosforge import assistant
    from logosforge.memory_arch import github_export, sync

    def boom(*a, **k):
        raise AssertionError("no external call allowed in Writer QA")

    monkeypatch.setattr(assistant, "chat_completion", boom)
    monkeypatch.setattr(sync.MemorySyncService, "sync_memory_to_cloud", boom)
    monkeypatch.setattr(github_export.GitHubMemoryExportService,
                        "optional_sync_memory_to_github", boom)
    bugs, total = run_suite(get_suite("all"))   # no raise → no external calls
    assert total > 0


# 19. Reports are written only under the chosen path (temp dir).
def test_reports_stay_in_tmp(tmp_path):
    run_writer_qa.main(["--suite", "manuscript", "--report", str(tmp_path / "x")])
    written = {p.name for p in tmp_path.iterdir()}
    assert written == {"x.json", "x.md"}


# 20. Every scenario yields a well-formed contract (no crashes across matrix).
def test_every_scenario_evaluates():
    for sc in core_scenarios():
        evaluate_scenario(sc)        # must never raise
