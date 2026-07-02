"""Semantic Continuity Engine (Phase 10Q).

Detects continuity problems, contradictions, missing transitions and unresolved
narrative commitments across the whole project — deterministically, with
evidence and confidence, and **without** mutating content, calling an LLM, or
auto-fixing anything. Builds on the Narrative Knowledge Graph (10P), PSYKE,
scenes, outline/plot/timeline and notes; validates proposed rewrite / controlled
-apply changes before they become canonical.

Facts and states are rebuilt each run; only issue *status* (dismiss/resolve/
defer) and check-run summaries persist. Inferred signals are never presented as
confirmed truth.
"""

from __future__ import annotations

from logosforge.continuity.collector import (
    build_continuity_report,
    check_scene_continuity,
    get_continuity_issues,
    persist_check_run,
    set_issue_status,
)
from logosforge.continuity.models import (
    ContinuityChangeValidation,
    ContinuityFact,
    ContinuityIssueData,
    ContinuityReport,
    ContinuityState,
)
from logosforge.continuity.recommendations import build_continuity_decision_cards
from logosforge.continuity.rewrite_validator import validate_continuity_change
from logosforge.continuity.scoring import issues_by_dimension, most_affected_scenes
from logosforge.continuity.serializers import (
    explain_issue,
    get_continuity_summary_for_assistant,
)

__all__ = [
    "ContinuityReport",
    "ContinuityIssueData",
    "ContinuityFact",
    "ContinuityState",
    "ContinuityChangeValidation",
    "build_continuity_report",
    "check_scene_continuity",
    "validate_continuity_change",
    "get_continuity_issues",
    "get_continuity_summary_for_assistant",
    "build_continuity_decision_cards",
    "explain_issue",
    "persist_check_run",
    "set_issue_status",
    "most_affected_scenes",
    "issues_by_dimension",
]
