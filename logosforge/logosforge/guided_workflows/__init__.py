"""Guided Workflows / Project Operating System (Phase 10O).

Resumable, writing-mode-aware, step-by-step workflows that thread the existing
systems (Project Intelligence, Decision Radar, Writing Modes, PSYKE, Assistant,
Logos, Rewrite Sandbox, Controlled Apply, Revision Intelligence, Export,
Production Draft) into a guided path.

Safety: the engine mutates **only workflow state**; creative steps are never
auto-completed; no LLM runs here; any real content change a step implies routes
through Controlled Apply / Rewrite Sandbox with their own confirmation.
"""

from __future__ import annotations

from logosforge.guided_workflows.engine import (
    WorkflowRunView,
    advance_workflow_step,
    cancel_workflow,
    check_step_completion,
    complete_workflow_step,
    get_active_workflows,
    get_all_workflows,
    get_workflow_run_view,
    pause_workflow,
    refresh_workflow_run,
    resume_workflow,
    skip_workflow_step,
    start_workflow,
    workflow_status_summary,
)
from logosforge.guided_workflows.models import (
    WorkflowStep,
    WorkflowTemplate,
)
from logosforge.guided_workflows.recommendations import (
    WorkflowRecommendation,
    build_workflow_recommendations,
)
from logosforge.guided_workflows.registry import (
    all_templates,
    get_template,
    list_workflow_templates,
)

__all__ = [
    "WorkflowTemplate",
    "WorkflowStep",
    "WorkflowRunView",
    "WorkflowRecommendation",
    "all_templates",
    "get_template",
    "list_workflow_templates",
    "build_workflow_recommendations",
    "start_workflow",
    "get_active_workflows",
    "get_all_workflows",
    "get_workflow_run_view",
    "complete_workflow_step",
    "skip_workflow_step",
    "advance_workflow_step",
    "pause_workflow",
    "resume_workflow",
    "cancel_workflow",
    "refresh_workflow_run",
    "check_step_completion",
    "workflow_status_summary",
]
