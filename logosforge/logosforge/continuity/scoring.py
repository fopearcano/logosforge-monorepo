"""Continuity scoring helpers (Phase 10Q): most-affected scenes / dimensions."""

from __future__ import annotations

from collections import Counter

from logosforge.continuity.models import ContinuityReport


def most_affected_scenes(report: ContinuityReport, *, top: int = 5) -> list[tuple[int, int]]:
    counter: Counter = Counter()
    for issue in report.open_issues():
        for sid in issue.related_scene_ids:
            if sid is not None:
                counter[sid] += 1
    return counter.most_common(top)


def issues_by_dimension(report: ContinuityReport) -> dict[str, int]:
    counter: Counter = Counter()
    for issue in report.open_issues():
        counter[issue.dimension] += 1
    return dict(counter)
