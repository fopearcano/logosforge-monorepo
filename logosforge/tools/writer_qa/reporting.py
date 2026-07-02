"""Writer QA bug-report model + machine/human-readable report writers."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

SEVERITIES = ("BLOCKER", "HIGH", "MEDIUM", "LOW")


@dataclass
class BugReport:
    bug_id: str
    severity: str
    area: str
    writing_mode: str
    section: str
    action: str
    target: str
    scenario_name: str
    expected_behavior: str
    actual_behavior: str
    validator_result: str
    cache_result: str
    apply_state: str
    reproduction_steps: list[str]
    relevant_response_excerpt: str
    suspected_root_cause: str
    suggested_fix_area: str
    test_name: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat())


def summarize(bugs: list[BugReport], total: int) -> dict:
    counts = {s: sum(1 for b in bugs if b.severity == s) for s in SEVERITIES}
    return {
        "scenarios_run": total,
        "scenarios_passed": total - len(bugs),
        "bugs": len(bugs),
        "by_severity": counts,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def write_reports(bugs: list[BugReport], summary: dict,
                  path_prefix: str) -> tuple[str, str]:
    """Write `<prefix>.json` and `<prefix>.md`; returns the two paths."""
    os.makedirs(os.path.dirname(path_prefix) or ".", exist_ok=True)
    json_path, md_path = path_prefix + ".json", path_prefix + ".md"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump({"summary": summary, "bugs": [asdict(b) for b in bugs]},
                  fh, indent=2)
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(_markdown(bugs, summary))
    return json_path, md_path


def _markdown(bugs: list[BugReport], summary: dict) -> str:
    sev = summary["by_severity"]
    lines = [
        "# Writer QA Report", "",
        f"Generated: {summary['generated_at']}", "",
        f"- Scenarios run: **{summary['scenarios_run']}**",
        f"- Passed: **{summary['scenarios_passed']}**",
        f"- Bugs: **{summary['bugs']}** "
        f"(BLOCKER {sev['BLOCKER']} · HIGH {sev['HIGH']} · "
        f"MEDIUM {sev['MEDIUM']} · LOW {sev['LOW']})", "",
    ]
    if not bugs:
        lines.append("No Writer QA bugs found. ✅")
        return "\n".join(lines) + "\n"
    for b in sorted(bugs, key=lambda x: SEVERITIES.index(x.severity)):
        lines += [
            f"## [{b.severity}] {b.scenario_name} — {b.area}", "",
            f"- **Mode / Section / Action / Target:** {b.writing_mode} / "
            f"{b.section} / {b.action} / {b.target}",
            f"- **Expected:** {b.expected_behavior}",
            f"- **Actual:** {b.actual_behavior}",
            f"- **Validator:** {b.validator_result}",
            f"- **Cache:** {b.cache_result}",
            f"- **Apply state:** {b.apply_state}",
            f"- **Suspected root cause:** {b.suspected_root_cause}",
            f"- **Suggested fix area:** {b.suggested_fix_area}",
            "- **Reproduction:**",
        ]
        lines += [f"  {i+1}. {step}" for i, step in enumerate(b.reproduction_steps)]
        if b.relevant_response_excerpt:
            excerpt = b.relevant_response_excerpt.replace("\n", " ")[:200]
            lines += ["", f"  > {excerpt}", ""]
        lines.append("")
    return "\n".join(lines) + "\n"
