"""Guided Workflow engine (Phase 10O).

Turns a :class:`~logosforge.guided_workflows.models.WorkflowTemplate` into
resumable, persisted run state and advances it deterministically.

Hard safety contract:

* The engine mutates **only workflow state** (``WorkflowRun`` /
  ``WorkflowStepState`` / ``WorkflowEvent`` / ``WorkflowCommandReceipt``). It
  never edits scenes, PSYKE, outline, production drafts or any project content.
* ``creative`` steps are NEVER auto-completed. Only the user can mark them done
  (``complete_workflow_step``). ``refresh_workflow_run`` may auto-tick only
  ``check`` steps whose deterministic completion check passes.
* No LLM is ever called here. The canonical refresh command proves supported
  checks in the same SQL transaction; complex aggregate checks fail closed.
* Any real content mutation a step implies (apply a rewrite, accept a merge)
  routes through the existing Controlled Apply / Rewrite Sandbox systems, which
  require their own confirmation — the workflow only points the user at them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from logosforge.guided_workflows import completion_checks as CC
from logosforge.guided_workflows.models import KIND_CHECK, WorkflowStep
from logosforge.guided_workflows.registry import get_template
from logosforge.writing_modes import get_project_writing_mode_by_id, normalize_mode

_ACTIVE_STATUSES = ("active", "paused", "blocked")


@dataclass
class WorkflowRunView:
    """Read-friendly view of a run: the run row, its step states and template."""

    run: object  # WorkflowRun
    steps: list = field(default_factory=list)  # list[WorkflowStepState] (ordered)
    template: object = None  # WorkflowTemplate | None
    revision: str = ""

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def completed_steps(self) -> int:
        return sum(1 for s in self.steps if s.status in ("completed", "skipped"))

    @property
    def is_complete(self) -> bool:
        return self.total_steps > 0 and self.completed_steps == self.total_steps

    @property
    def current_step(self):
        cid = getattr(self.run, "current_step_id", "")
        for s in self.steps:
            if s.step_id == cid:
                return s
        return None

    def progress_line(self) -> str:
        return (f"{getattr(self.run, 'title', '') or 'Workflow'}: "
                f"{self.completed_steps}/{self.total_steps} steps "
                f"({getattr(self.run, 'status', '')}).")


# -- Template step lookup ---------------------------------------------------

def _template_step(template, step_id: str) -> "WorkflowStep | None":
    if template is None:
        return None
    for s in template.steps:
        if s.id == step_id:
            return s
    return None


# -- Construction -----------------------------------------------------------

def start_workflow(db, project_id: int, template_id: str, *,
                   writing_mode: str | None = None, title: str | None = None,
                   ) -> "WorkflowRunView | None":
    """Create a new active run from a template (mode-aware). No content mutation."""
    template = get_template(template_id)
    if template is None:
        return None
    # ``writing_mode`` is retained for source compatibility but deliberately
    # ignored: a run must use the project's authoritative mode. Allowing an
    # override here would create a workflow whose template semantics disagree
    # with every other project-scoped service.
    del writing_mode
    mode = normalize_mode(get_project_writing_mode_by_id(db, project_id))
    if not template.applies_to(mode):
        return None

    from logosforge.db import WorkflowCommandError, WorkflowStateConflict

    try:
        result = db.execute_workflow_command(
            project_id,
            kind="start_workflow",
            idempotency_key=f"workflow-legacy-{uuid4().hex}",
            template_id=template_id,
            title=title,
        )
    except (WorkflowCommandError, WorkflowStateConflict):
        return None
    return workflow_run_view_from_snapshot(result.snapshot)


# -- Reads ------------------------------------------------------------------

def get_workflow_run_view(db, run_id: int) -> "WorkflowRunView | None":
    snapshot = db.read_workflow_run_snapshot_by_id(run_id)
    if snapshot is None:
        return None
    return workflow_run_view_from_snapshot(snapshot)


def workflow_run_view_from_snapshot(snapshot) -> WorkflowRunView:
    """Adapt an atomic Database snapshot to the established read view."""
    return WorkflowRunView(
        run=snapshot.run,
        steps=list(snapshot.steps),
        template=get_template(snapshot.run.template_id),
        revision=snapshot.revision,
    )


def get_active_workflows(db, project_id: int) -> list[WorkflowRunView]:
    snapshots = db.read_workflow_runs_snapshot(project_id) or ()
    return [
        workflow_run_view_from_snapshot(snapshot)
        for snapshot in snapshots
        if snapshot.run.status in _ACTIVE_STATUSES
    ]


def get_all_workflows(db, project_id: int) -> list[WorkflowRunView]:
    snapshots = db.read_workflow_runs_snapshot(project_id) or ()
    return [workflow_run_view_from_snapshot(snapshot) for snapshot in snapshots]


def _execute_legacy_run_command(
    db,
    run_id: int,
    kind: str,
    *,
    allow_noncurrent: bool = False,
    **fields,
) -> "WorkflowRunView | None":
    """Compatibility adapter over the one atomic workflow write boundary."""
    run = db.get_workflow_run(run_id)
    if run is None:
        return None
    snapshot = db.read_workflow_run_snapshot(run.project_id, run_id)
    if snapshot is None:
        return None
    from logosforge.db import (
        WorkflowRevisionConflict,
        WorkflowStateConflict,
        WorkflowStepNotFound,
    )

    try:
        result = db.execute_workflow_command(
            run.project_id,
            kind=kind,
            idempotency_key=f"workflow-legacy-{uuid4().hex}",
            expected_revision=snapshot.revision,
            _legacy_allow_noncurrent=allow_noncurrent,
            run_id=run_id,
            **fields,
        )
    except (
        WorkflowRevisionConflict,
        WorkflowStateConflict,
        WorkflowStepNotFound,
    ):
        stable = db.read_workflow_run_snapshot(run.project_id, run_id)
        return (
            workflow_run_view_from_snapshot(stable)
            if stable is not None
            else None
        )
    return workflow_run_view_from_snapshot(result.snapshot)


# -- Advancement ------------------------------------------------------------

def complete_workflow_step(db, run_id: int, step_id: str, *, notes: str = "",
                           ) -> "WorkflowRunView | None":
    """Mark a step complete through the atomic command boundary."""
    return _execute_legacy_run_command(
        db,
        run_id,
        "complete_step",
        allow_noncurrent=True,
        step_id=step_id,
        notes=notes,
    )


def skip_workflow_step(db, run_id: int, step_id: str, *, notes: str = "",
                       ) -> "WorkflowRunView | None":
    return _execute_legacy_run_command(
        db,
        run_id,
        "skip_step",
        allow_noncurrent=True,
        step_id=step_id,
        notes=notes,
    )


def advance_workflow_step(db, run_id: int) -> "WorkflowRunView | None":
    """Move the active pointer forward without completing (e.g. user defers)."""
    return _execute_legacy_run_command(db, run_id, "advance")


# -- Lifecycle --------------------------------------------------------------

def pause_workflow(db, run_id: int) -> "WorkflowRunView | None":
    return _execute_legacy_run_command(db, run_id, "pause")


def resume_workflow(db, run_id: int) -> "WorkflowRunView | None":
    run = db.get_workflow_run(run_id)
    if run is None:
        return None
    if run.status in ("completed", "cancelled"):
        return get_workflow_run_view(db, run_id)
    return _execute_legacy_run_command(db, run_id, "resume")


def cancel_workflow(db, run_id: int) -> "WorkflowRunView | None":
    return _execute_legacy_run_command(db, run_id, "cancel")


# -- Deterministic refresh --------------------------------------------------

def check_step_completion(report, template, step_state) -> "bool | None":
    """Deterministic 'is this step verifiably done?' — None when not checkable.

    Returns None for creative steps and for steps with no/unknown check, so the
    caller knows it must not auto-complete them.
    """
    tstep = _template_step(template, step_state.step_id)
    if tstep is None or tstep.kind != KIND_CHECK or not tstep.completion_check:
        return None
    return CC.evaluate(tstep.completion_check, report)


def refresh_workflow_run(db, run_id: int) -> "WorkflowRunView | None":
    """Re-evaluate deterministic checks and auto-complete passing ``check`` steps.

    NEVER auto-completes creative/manual steps. Delegates to the canonical
    transaction-bound command, calls no LLM, and mutates only workflow state.
    """
    run = db.get_workflow_run(run_id)
    if run is None or run.status in ("completed", "cancelled"):
        return get_workflow_run_view(db, run_id)
    return _execute_legacy_run_command(db, run_id, "refresh")


def workflow_status_summary(db, project_id: int) -> str:
    """One-paragraph deterministic summary of active workflows (for Logos/context)."""
    views = get_active_workflows(db, project_id)
    if not views:
        return "No active guided workflows."
    lines = []
    for v in views:
        cur = v.current_step
        cur_txt = f" — current: {cur.title}" if cur is not None else ""
        lines.append(v.progress_line() + cur_txt)
    return "\n".join(lines)
