import type {
  WorkflowCommandDTO,
  WorkflowCommandReceiptDTO,
  WorkflowEventDTO,
  WorkflowRunDTO,
  WorkflowStepDTO,
} from "@logosforge/ui-contracts";

export type WorkflowRunAction = Exclude<WorkflowCommandDTO["kind"], "start_workflow">;

export interface WorkflowRunIntent {
  kind: WorkflowRunAction;
  stepId?: string;
  notes?: string;
}

export type WorkflowCommandPlan =
  | { command: WorkflowCommandDTO; step: WorkflowStepDTO | null; error?: never }
  | { command?: never; step?: never; error: string };

const TERMINAL_RUN_STATUSES = new Set(["completed", "cancelled"]);

/**
 * Bind a UI intent to one authoritative run revision.
 *
 * The client never invents a run id, step id, or revision: all three come from
 * the latest validated DTO. The API remains authoritative and can reject a
 * stale plan with a conflict if another surface advanced the run first.
 */
export function planWorkflowCommand(
  run: WorkflowRunDTO,
  intent: WorkflowRunIntent,
): WorkflowCommandPlan {
  if (!run.revision) return { error: "This workflow has no revision token. Refresh it before changing state." };
  if (TERMINAL_RUN_STATUSES.has(run.status)) {
    return { error: `This workflow is already ${run.status}.` };
  }

  if (intent.kind === "resume") {
    if (run.status !== "paused" && run.status !== "blocked") {
      return { error: "Only a paused or blocked workflow can be resumed." };
    }
    return {
      command: { kind: "resume", run_id: run.id, expected_revision: run.revision },
      step: null,
    };
  }

  if (intent.kind === "pause") {
    if (run.status !== "active") return { error: "Only an active workflow can be paused." };
    return {
      command: { kind: "pause", run_id: run.id, expected_revision: run.revision },
      step: null,
    };
  }

  if (intent.kind === "cancel" || intent.kind === "refresh" || intent.kind === "advance") {
    if (intent.kind !== "cancel" && run.status !== "active") {
      return { error: `Resume this ${run.status} workflow before ${intent.kind === "refresh" ? "verifying" : "advancing"} it.` };
    }
    return {
      command: {
        kind: intent.kind,
        run_id: run.id,
        expected_revision: run.revision,
      },
      step: null,
    };
  }

  const stepId = intent.stepId || run.current_step_id;
  const step = run.steps.find((candidate) => candidate.step_id === stepId);
  if (!step) return { error: "That workflow step is no longer present." };
  if (run.status !== "active") {
    return { error: `Resume this ${run.status} workflow before changing a step.` };
  }
  if (step.step_id !== run.current_step_id || step.status !== "active") {
    return { error: "Only the current active workflow step can be completed or skipped." };
  }

  return {
    command: {
      kind: intent.kind,
      run_id: run.id,
      step_id: step.step_id,
      expected_revision: run.revision,
      ...(intent.notes?.trim() ? { notes: intent.notes.trim().slice(0, 2000) } : {}),
    },
    step,
  };
}

/** A mode-filtered template start stays explicit and never invokes Logos. */
export function planWorkflowStart(templateId: string, title?: string): WorkflowCommandDTO {
  const cleanTitle = title?.trim();
  return {
    kind: "start_workflow",
    template_id: templateId,
    ...(cleanTitle ? { title: cleanTitle.slice(0, 200) } : {}),
  };
}

let fallbackSequence = 0;

/** One fresh capability key per explicit command; retries reuse the captured key. */
export function createWorkflowIdempotencyKey(): string {
  const randomUuid = globalThis.crypto?.randomUUID?.();
  if (randomUuid) return `workflow-ui-${randomUuid}`;
  fallbackSequence += 1;
  return `workflow-ui-${Date.now().toString(36)}-${fallbackSequence.toString(36)}-${Math.random().toString(36).slice(2, 14)}`;
}

/** Only known Studio panels can be opened from core-provided section labels. */
const SECTION_PANELS: Readonly<Record<string, string>> = {
  projects: "projects",
  dashboard: "dashboard",
  manuscript: "manuscript",
  outline: "outline",
  structure: "structure",
  plot: "canvas-plot",
  timeline: "timeline",
  psyke: "psyke",
  graph: "graph",
  "knowledge graph": "graph",
  continuity: "continuity",
  review: "review",
  export: "export",
  "decision radar": "decision-radar",
};

export function workflowSectionPanelId(sectionName: string): string | null {
  return SECTION_PANELS[sectionName.trim().toLowerCase()] ?? null;
}

/** Keep the quest log compact even if a host supplies an unexpectedly large list. */
export function boundedWorkflowEvents(
  events: readonly WorkflowEventDTO[],
  limit = 40,
): WorkflowEventDTO[] {
  const cap = Math.max(1, Math.min(100, Math.floor(limit) || 40));
  return events.slice(-cap);
}

/**
 * Check the authoritative run reached through a durable receipt against the
 * exact command capability retained by this UI. Later commands may legitimately
 * change lifecycle/pointer state, but template and terminal step outcomes are
 * stable identities that must still match.
 */
export function validateRecoveredWorkflowRun(
  run: WorkflowRunDTO,
  command: WorkflowCommandDTO,
  receipt: WorkflowCommandReceiptDTO,
): string | null {
  if (run.id !== receipt.original_run_id) {
    return "The receipt resolved to a different workflow run.";
  }
  if (command.kind === "start_workflow" && run.template_id !== command.template_id) {
    return "The recovered workflow does not match the requested template.";
  }
  if (command.kind !== "start_workflow" && run.id !== command.run_id) {
    return "The recovered workflow does not match the requested run.";
  }
  if (command.kind === "complete_step" || command.kind === "skip_step") {
    const step = run.steps.find((candidate) => candidate.step_id === command.step_id);
    const expected = command.kind === "complete_step" ? "completed" : "skipped";
    if (!step || step.status !== expected) {
      return `The recovered workflow does not confirm that step as ${expected}.`;
    }
  }
  return null;
}

export function workflowNoChangeMessage(command: WorkflowCommandDTO): string {
  if (command.kind === "refresh") return "No verifiable workflow checks changed.";
  if (command.kind === "advance") return "No other open workflow step was available.";
  return "Workflow state was already up to date.";
}
