"""Guided Workflow engine (Phase 10O).

Turns a :class:`~logosforge.guided_workflows.models.WorkflowTemplate` into
resumable, persisted run state and advances it deterministically.

Hard safety contract:

* The engine mutates **only workflow state** (``WorkflowRun`` /
  ``WorkflowStepState`` / ``WorkflowEvent``). It never edits scenes, PSYKE,
  outline, production drafts or any project content.
* ``creative`` steps are NEVER auto-completed. Only the user can mark them done
  (``complete_workflow_step``). ``refresh_workflow_run`` may auto-tick only
  ``check`` steps whose deterministic completion check passes.
* No LLM is ever called here. Completion checks read the deterministic Project
  Intelligence report.
* Any real content mutation a step implies (apply a rewrite, accept a merge)
  routes through the existing Controlled Apply / Rewrite Sandbox systems, which
  require their own confirmation — the workflow only points the user at them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from logosforge.guided_workflows import completion_checks as CC
from logosforge.guided_workflows.models import KIND_CHECK, WorkflowStep
from logosforge.guided_workflows.registry import get_template
from logosforge.writing_modes import get_project_writing_mode_by_id, normalize_mode

_ACTIVE_STATUSES = ("active", "paused")


@dataclass
class WorkflowRunView:
    """Read-friendly view of a run: the run row, its step states and template."""

    run: object  # WorkflowRun
    steps: list = field(default_factory=list)  # list[WorkflowStepState] (ordered)
    template: object = None  # WorkflowTemplate | None

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


def _first_open_step_id(steps) -> str:
    for s in steps:
        if s.status in ("pending", "active"):
            return s.step_id
    return ""


# -- Construction -----------------------------------------------------------

def start_workflow(db, project_id: int, template_id: str, *,
                   writing_mode: str | None = None, title: str | None = None,
                   ) -> "WorkflowRunView | None":
    """Create a new active run from a template (mode-aware). No content mutation."""
    template = get_template(template_id)
    if template is None:
        return None
    mode = normalize_mode(writing_mode
                          or get_project_writing_mode_by_id(db, project_id))
    if not template.applies_to(mode):
        return None

    steps = template.steps_for_mode(mode)
    run = db.create_workflow_run(
        project_id, template_id=template_id,
        title=(title or template.title), writing_mode=mode,
        status="active", current_step_id=(steps[0].id if steps else ""),
    )
    for idx, step in enumerate(steps):
        db.create_workflow_step_state(
            project_id, run.id, step_id=step.id, title=step.title,
            status=("active" if idx == 0 else "pending"),
            section_name=(step.section_name or None),
            action_id=(step.action_id or None), sort_index=idx,
        )
    db.create_workflow_event(project_id, run.id, event_type="started",
                             message=f"Started workflow '{run.title}'.")
    return get_workflow_run_view(db, run.id)


# -- Reads ------------------------------------------------------------------

def get_workflow_run_view(db, run_id: int) -> "WorkflowRunView | None":
    run = db.get_workflow_run(run_id)
    if run is None:
        return None
    steps = db.get_workflow_step_states(run_id)
    return WorkflowRunView(run=run, steps=steps, template=get_template(run.template_id))


def get_active_workflows(db, project_id: int) -> list[WorkflowRunView]:
    out: list[WorkflowRunView] = []
    for run in db.get_workflow_runs(project_id):
        if run.status in _ACTIVE_STATUSES:
            out.append(get_workflow_run_view(db, run.id))
    return out


def get_all_workflows(db, project_id: int) -> list[WorkflowRunView]:
    return [get_workflow_run_view(db, run.id)
            for run in db.get_workflow_runs(project_id)]


# -- Advancement ------------------------------------------------------------

def _recompute_pointer(db, run_id: int) -> None:
    """Set current_step_id to the first open step; mark run completed if none."""
    run = db.get_workflow_run(run_id)
    if run is None or run.status == "cancelled":
        return
    steps = db.get_workflow_step_states(run_id)
    open_id = _first_open_step_id(steps)
    if open_id:
        # The first open step becomes active.
        for s in steps:
            if s.step_id == open_id and s.status == "pending":
                db.update_workflow_step_state(s.id, status="active")
        db.update_workflow_run(run_id, current_step_id=open_id)
    else:
        from logosforge.models.models import _now
        db.update_workflow_run(run_id, status="completed", current_step_id="",
                               completed_at=_now())
        db.create_workflow_event(run.project_id, run_id, event_type="completed",
                                 message="Workflow completed.")


def _find_step_state(steps, step_id: str):
    for s in steps:
        if s.step_id == step_id:
            return s
    return None


def complete_workflow_step(db, run_id: int, step_id: str, *, notes: str = "",
                           ) -> "WorkflowRunView | None":
    """Mark a step complete (user action). Works for any step kind."""
    run = db.get_workflow_run(run_id)
    if run is None:
        return None
    st = _find_step_state(db.get_workflow_step_states(run_id), step_id)
    if st is None:
        return get_workflow_run_view(db, run_id)
    db.update_workflow_step_state(st.id, status="completed",
                                  notes=(notes or st.notes))
    db.create_workflow_event(run.project_id, run_id, step_id=step_id,
                             event_type="step_completed",
                             message=f"Completed step '{st.title}'.")
    _recompute_pointer(db, run_id)
    return get_workflow_run_view(db, run_id)


def skip_workflow_step(db, run_id: int, step_id: str, *, notes: str = "",
                       ) -> "WorkflowRunView | None":
    run = db.get_workflow_run(run_id)
    if run is None:
        return None
    st = _find_step_state(db.get_workflow_step_states(run_id), step_id)
    if st is None:
        return get_workflow_run_view(db, run_id)
    db.update_workflow_step_state(st.id, status="skipped",
                                  notes=(notes or st.notes))
    db.create_workflow_event(run.project_id, run_id, step_id=step_id,
                             event_type="step_skipped",
                             message=f"Skipped step '{st.title}'.")
    _recompute_pointer(db, run_id)
    return get_workflow_run_view(db, run_id)


def advance_workflow_step(db, run_id: int) -> "WorkflowRunView | None":
    """Move the active pointer forward without completing (e.g. user defers)."""
    run = db.get_workflow_run(run_id)
    if run is None:
        return None
    steps = db.get_workflow_step_states(run_id)
    cur = _find_step_state(steps, run.current_step_id)
    if cur is not None and cur.status == "active":
        db.update_workflow_step_state(cur.id, status="pending")
    # Pick the next open step after the current sort position.
    cur_sort = cur.sort_index if cur is not None else -1
    nxt = next((s for s in steps
                if s.sort_index > cur_sort and s.status in ("pending", "active")),
               None)
    if nxt is None:
        nxt = next((s for s in steps if s.status in ("pending", "active")), None)
    if nxt is not None:
        db.update_workflow_step_state(nxt.id, status="active")
        db.update_workflow_run(run_id, current_step_id=nxt.step_id)
    return get_workflow_run_view(db, run_id)


# -- Lifecycle --------------------------------------------------------------

def pause_workflow(db, run_id: int) -> "WorkflowRunView | None":
    run = db.get_workflow_run(run_id)
    if run is None:
        return None
    db.update_workflow_run(run_id, status="paused")
    db.create_workflow_event(run.project_id, run_id, event_type="paused",
                             message="Workflow paused.")
    return get_workflow_run_view(db, run_id)


def resume_workflow(db, run_id: int) -> "WorkflowRunView | None":
    run = db.get_workflow_run(run_id)
    if run is None:
        return None
    if run.status in ("completed", "cancelled"):
        return get_workflow_run_view(db, run_id)
    db.update_workflow_run(run_id, status="active")
    db.create_workflow_event(run.project_id, run_id, event_type="resumed",
                             message="Workflow resumed.")
    return get_workflow_run_view(db, run_id)


def cancel_workflow(db, run_id: int) -> "WorkflowRunView | None":
    run = db.get_workflow_run(run_id)
    if run is None:
        return None
    db.update_workflow_run(run_id, status="cancelled", current_step_id="")
    db.create_workflow_event(run.project_id, run_id, event_type="cancelled",
                             message="Workflow cancelled.")
    return get_workflow_run_view(db, run_id)


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

    NEVER auto-completes creative/manual steps. Builds the read-only Project
    Intelligence report once; calls no LLM; mutates only workflow state.
    """
    run = db.get_workflow_run(run_id)
    if run is None or run.status in ("completed", "cancelled"):
        return get_workflow_run_view(db, run_id)
    template = get_template(run.template_id)
    try:
        from logosforge.project_intelligence import build_project_intelligence_report
        report = build_project_intelligence_report(db, run.project_id)
    except Exception:
        return get_workflow_run_view(db, run_id)

    changed = False
    for st in db.get_workflow_step_states(run_id):
        if st.status in ("completed", "skipped"):
            continue
        verdict = check_step_completion(report, template, st)
        if verdict is True:
            db.update_workflow_step_state(st.id, status="completed")
            db.create_workflow_event(run.project_id, run_id, step_id=st.step_id,
                                     event_type="step_auto_completed",
                                     message=f"Auto-completed verifiable step "
                                             f"'{st.title}'.")
            changed = True
    if changed:
        _recompute_pointer(db, run_id)
    return get_workflow_run_view(db, run_id)


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
