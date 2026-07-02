"""Aggregate Logos diagnostics into per-category health metrics.

Each of the 12 health categories maps to one or more diagnostic categories. A
metric's status is derived from the diagnostics that landed in it:

* critical diagnostic            -> critical
* >=1 important or >=2 warnings   -> weak
* >=1 warning                     -> watch
* only info / none, data present  -> stable
* category data absent            -> unknown  (never a false negative)

No fake percentages: a metric's ``confidence`` is just the strongest supporting
diagnostic's confidence, shown as detail.
"""

from __future__ import annotations

from logosforge.logos.diagnostics.diagnostic import (
    CAT_CHARACTER as D_CHARACTER,
    CAT_CONTINUITY as D_CONTINUITY,
    CAT_GRAPH as D_GRAPH,
    CAT_PSYKE as D_PSYKE,
    CAT_RELATIONSHIP as D_RELATIONSHIP,
    CAT_SETUP_PAYOFF as D_SETUP_PAYOFF,
    CAT_STRUCTURE as D_STRUCTURE,
    CAT_THEME as D_THEME,
    CAT_TIMELINE as D_TIMELINE,
)
from logosforge.logos.health import metric as M
from logosforge.logos.health.metric import NarrativeHealthMetric

# Health category -> set of diagnostic categories that feed it.
_HEALTH_TO_DIAG = {
    M.CAT_STRUCTURE: {D_STRUCTURE},
    M.CAT_CHARACTER: {D_CHARACTER},
    M.CAT_RELATIONSHIP: {D_RELATIONSHIP},
    M.CAT_THEME: {D_THEME},
    M.CAT_CONTINUITY: {D_CONTINUITY},
    M.CAT_TIMELINE: {D_TIMELINE},
    M.CAT_PACING: {D_STRUCTURE},        # pacing surfaces via structure/turning-point gaps
    M.CAT_SCENE_PURPOSE: {D_STRUCTURE}, # empty outline nodes = weak scene purpose
    M.CAT_SETUP_PAYOFF: {D_SETUP_PAYOFF},
    M.CAT_PSYKE: {D_PSYKE, D_CHARACTER, D_THEME},
    M.CAT_GRAPH: {D_GRAPH},
    M.CAT_NOTES: {D_PSYKE},             # notes diagnostics use the psyke category
}

# Title fragments used to keep pacing/scene-purpose/notes distinct even though
# they share an underlying diagnostic category.
_PACING_HINT = ("turning point", "escalat", "pacing")
_SCENE_PURPOSE_HINT = ("dramatic function", "purpose", "summary")
_NOTES_HINT = ("note", "notes")


def aggregate_metrics(diagnostics, data_presence: dict) -> list[NarrativeHealthMetric]:
    """Build one metric per health category from *diagnostics*.

    *data_presence* maps health category -> bool: whether the project has any
    data to judge that category (else the metric is ``unknown``).
    """
    by_diag_cat: dict[str, list] = {}
    for d in diagnostics:
        by_diag_cat.setdefault(d.category, []).append(d)

    metrics: list[NarrativeHealthMetric] = []
    for hcat in M.ALL_CATEGORIES:
        diag_cats = _HEALTH_TO_DIAG.get(hcat, set())
        relevant: list = []
        for dc in diag_cats:
            relevant.extend(by_diag_cat.get(dc, []))
        relevant = _filter_for_health_category(hcat, relevant)

        if not data_presence.get(hcat, False):
            metrics.append(NarrativeHealthMetric(
                category=hcat, status=M.STATUS_UNKNOWN,
                evidence="Not enough project data to assess.",
            ))
            continue

        metrics.append(_metric_from_diagnostics(hcat, relevant))
    return metrics


def _filter_for_health_category(hcat: str, diags: list) -> list:
    """Disambiguate categories that share a diagnostic origin by title hints."""
    if hcat == M.CAT_PACING:
        return [d for d in diags if _matches(d, _PACING_HINT)]
    if hcat == M.CAT_SCENE_PURPOSE:
        return [d for d in diags if _matches(d, _SCENE_PURPOSE_HINT)]
    if hcat == M.CAT_NOTES:
        return [d for d in diags if d.section_name == "Notes"]
    if hcat == M.CAT_PSYKE:
        # PSYKE completeness = missing-detail / unused-entry findings, not the
        # notes-integration ones (those go to the Notes metric).
        return [d for d in diags if d.section_name != "Notes"]
    if hcat == M.CAT_STRUCTURE:
        # Structure excludes the pacing-specific turning-point findings.
        return [d for d in diags if not _matches(d, _PACING_HINT)]
    return diags


def _matches(diag, hints) -> bool:
    t = (diag.title or "").lower()
    return any(h in t for h in hints)


def _metric_from_diagnostics(hcat: str, diags: list) -> NarrativeHealthMetric:
    if not diags:
        return NarrativeHealthMetric(
            category=hcat, status=M.STATUS_STABLE,
            evidence="No issues detected.",
        )
    n_critical = sum(1 for d in diags if d.severity == "critical")
    n_important = sum(1 for d in diags if d.severity == "important")
    n_warning = sum(1 for d in diags if d.severity == "warning")

    if n_critical:
        status = M.STATUS_CRITICAL
    elif n_important or n_warning >= 2:
        status = M.STATUS_WEAK
    elif n_warning:
        status = M.STATUS_WATCH
    else:
        status = M.STATUS_STABLE

    worst = max(diags, key=lambda d: (d.severity_rank, d.confidence))
    counts = []
    if n_critical:
        counts.append(f"{n_critical} critical")
    if n_important:
        counts.append(f"{n_important} important")
    if n_warning:
        counts.append(f"{n_warning} warning")
    n_info = len(diags) - n_critical - n_important - n_warning
    if n_info:
        counts.append(f"{n_info} info")
    evidence = (", ".join(counts) + ". " if counts else "") + f"e.g. {worst.title}"

    return NarrativeHealthMetric(
        category=hcat, status=status, confidence=worst.confidence,
        evidence=evidence,
        related_diagnostics=[d.id for d in diags],
        target_type=worst.target_type, target_id=worst.target_id,
        suggested_actions=list(worst.suggested_actions),
    )
