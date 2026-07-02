"""Writer QA evaluation — run each scenario through the real Assistant contract
(route → fake provider → validate) and judge it like a writer would: did the
output match the section/mode/action, is it usable, is it safely (un)applyable?
Mismatches become BugReports. No real provider/network/DB calls.
"""

from __future__ import annotations

import re

from logosforge.assistant_contract import (
    DIRECT_CONTENT, route, validate,
)
from tools.writer_qa.fake_provider import FakeProvider, FakeProviderError
from tools.writer_qa.reporting import BugReport
from tools.writer_qa.scenarios import Scenario

_UPPER_CUE = re.compile(r"(?m)^[A-Z][A-Z0-9 .'\-]{1,30}$")
_SLUG = re.compile(r"(?m)^(INT\.|EXT\.)")
_PANEL = re.compile(r"(?i)\bpanel\b|visual:|caption:|sfx:")


def mode_format_ok(text: str, writing_mode: str) -> bool:
    """Heuristic: does the text look like the requested writing mode? Used to
    catch wrong-mode output that the marker validator alone does not detect."""
    t = text or ""
    if not t.strip():
        return False
    if writing_mode == "screenplay":
        return bool(_SLUG.search(t) or _UPPER_CUE.search(t))
    if writing_mode == "graphic_novel":
        return bool(_PANEL.search(t))
    if writing_mode == "stage_script":
        return bool(_UPPER_CUE.search(t) or "(" in t)
    if writing_mode == "novel":
        # Wrong if it is clearly a screenplay (slug + character cues).
        return not (bool(_SLUG.search(t)) and bool(_UPPER_CUE.search(t)))
    return True


def _bug(sc: Scenario, contract, severity, *, expected, actual, validator,
         cache, apply, root, fix, excerpt="") -> BugReport:
    return BugReport(
        bug_id=f"WQA-{sc.name}", severity=severity, area=sc.area,
        writing_mode=sc.writing_mode, section=sc.section, action=sc.action,
        target=sc.target, scenario_name=sc.name,
        expected_behavior=expected, actual_behavior=actual,
        validator_result=validator, cache_result=cache, apply_state=apply,
        reproduction_steps=[
            f"Open a {sc.writing_mode} project; go to {sc.section}.",
            f"Select target: {sc.target}.",
            f"Action: {sc.action} — instruction: \"{sc.instruction}\".",
            f"Provider returns the '{sc.provider_profile}' output profile.",
            "Observe the Assistant response, validation, and Apply state.",
        ],
        relevant_response_excerpt=excerpt,
        suspected_root_cause=root, suggested_fix_area=fix,
        test_name="tools/writer_qa/run_writer_qa.py")


def evaluate_scenario(sc: Scenario, provider: FakeProvider | None = None
                      ) -> BugReport | None:
    """Return a BugReport if the system mis-handles the scenario, else None."""
    provider = provider or FakeProvider()
    contract = route(
        entry_point=sc.entry_point, section=sc.section,
        writing_mode=sc.writing_mode, action=sc.action, target=sc.target,
        user_instruction=sc.instruction, has_target=(sc.target != "no_target"))

    # Clarification path (no provider call).
    if sc.expect_clarification:
        if contract.needs_clarification:
            return None
        return _bug(sc, contract, sc.severity,
                    expected="ask a short clarification (no content/planning)",
                    actual=f"did not clarify (output_kind={contract.output_kind})",
                    validator="n/a", cache="n/a", apply="n/a",
                    root="route() did not flag a missing target for direct writing",
                    fix="assistant_contract.route (needs_clarification)")

    # Routing check.
    if sc.expected_output_kind and contract.output_kind != sc.expected_output_kind:
        return _bug(sc, contract, sc.severity,
                    expected=f"output_kind={sc.expected_output_kind}",
                    actual=f"output_kind={contract.output_kind}",
                    validator="n/a", cache="n/a", apply="n/a",
                    root="route() classified section/mode/action/intent wrongly",
                    fix="assistant_contract.route / infer_intent")

    # Provider + validation.
    try:
        response = provider.respond(sc.provider_profile, contract)
    except FakeProviderError:
        # A provider failure must be handled gracefully (no crash, no apply).
        if sc.provider_profile == "provider_error":
            return None
        return _bug(sc, contract, sc.severity,
                    expected="graceful handling of provider output",
                    actual="unexpected provider error",
                    validator="n/a", cache="n/a", apply="n/a",
                    root="provider error not handled", fix="assistant runtime")

    res = validate(response, contract)
    observed_status = res.status
    observed_apply = res.apply_allowed
    if observed_status == sc.expected_status and observed_apply == sc.expected_apply:
        return None

    # Mismatch → a real finding.
    wrong_mode = (contract.output_kind == DIRECT_CONTENT
                  and not mode_format_ok(response, contract.writing_mode))
    severity = sc.severity
    # Anything that SHOULD be blocked but is applyable is a BLOCKER
    # (invalid/wrong-mode output can be inserted/replaced/appended) — except
    # empty output, which is HIGH.
    if (not sc.expected_apply and observed_apply
            and sc.provider_profile != "invalid_empty"):
        severity = "BLOCKER"
    note = ""
    if sc.provider_profile == "invalid_empty":
        note = " (empty output)"
    elif wrong_mode:
        note = " (wrong-mode: lacks the expected mode formatting)"
    return _bug(
        sc, contract, severity,
        expected=f"status={sc.expected_status}, apply_allowed={sc.expected_apply}",
        actual=f"status={observed_status}, apply_allowed={observed_apply}{note}",
        validator=(res.status
                   + ("; " + "; ".join(res.reasons[:3]) if res.reasons else "")),
        cache=f"cache_allowed={res.cache_allowed}",
        apply=f"apply_allowed={observed_apply}",
        excerpt=response,
        root=("validator did not block unsafe/wrong-mode/empty output"
              if observed_apply else "validator status/apply mismatch"),
        fix="assistant_contract.validate (validator profile)")


def run_suite(scenarios: list[Scenario], provider: FakeProvider | None = None
              ) -> tuple[list[BugReport], int]:
    provider = provider or FakeProvider()
    bugs = [b for b in (evaluate_scenario(s, provider) for s in scenarios)
            if b is not None]
    return bugs, len(scenarios)
