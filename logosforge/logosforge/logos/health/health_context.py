"""Opt-in Assistant context from a Narrative Health report.

Produces a short, top-risks-only summary string the host can fold into the
Assistant prompt *when the user enables it* (default off). Deliberately compact —
never the whole report — and read-only.
"""

from __future__ import annotations


def top_risks_text(report, *, max_risks: int = 5) -> str:
    """A compact '[Narrative Health]' block, or '' if nothing notable."""
    if report is None:
        return ""
    risks = list(report.top_risks)[:max_risks]
    if not risks and report.overall_status in ("stable", "unknown"):
        return ""
    lines = [f"[Narrative Health] Overall: {report.overall_label}"]
    for r in risks:
        lines.append(f"- {r}")
    return "\n".join(lines)
