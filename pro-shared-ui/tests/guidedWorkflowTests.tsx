import { MessagePort } from "node:worker_threads";
import { act, create, type ReactTestInstance, type ReactTestRenderer } from "react-test-renderer";
import type {
  WorkflowCommandDTO,
  WorkflowCommandReceiptDTO,
  WorkflowCommandResultDTO,
  WorkflowEventDTO,
  WorkflowRunDTO,
  WorkflowTemplateDTO,
} from "@logosforge/ui-contracts";
import type { ApiClient } from "../src/adapters/api";
import type { PlatformAdapter } from "../src/adapters/platform";
import { StudioProvider, type StudioNavigationOptions } from "../src/adapters/StudioProvider";
import { ApiRequestError } from "../src/adapters/httpApiClient";
import {
  RuntimeDtoValidationError,
  validateWorkflowRunDTOForRequest,
} from "../src/adapters/runtimeDtoValidation";
import { GuidedWorkflowStepper } from "../src/components/projectos/GuidedWorkflowStepper";
import {
  boundedWorkflowEvents,
  planWorkflowCommand,
  validateRecoveredWorkflowRun,
  workflowNoChangeMessage,
  workflowSectionPanelId,
} from "../src/components/projectos/guidedWorkflowTransactions";

let assertions = 0;
function check(value: unknown, message: string): asserts value {
  assertions += 1;
  if (!value) throw new Error(message);
}

function text(node: ReactTestInstance): string {
  return node.children.map((child) => typeof child === "string" ? child : text(child)).join("");
}

function button(renderer: ReactTestRenderer, label: string): ReactTestInstance {
  const match = renderer.root.findAllByType("button").find((candidate) => text(candidate) === label);
  if (!match) throw new Error(`Button not found: ${label}`);
  return match;
}

async function flush(rounds = 16): Promise<void> {
  for (let index = 0; index < rounds; index += 1) await Promise.resolve();
}

const template: WorkflowTemplateDTO = {
  id: "rewrite",
  title: "Rewrite",
  description: "Review and safely apply a focused rewrite.",
  category: "rewrite",
  modes: [],
  steps: [
    { id: "select", title: "Select the passage", description: "Choose the passage.", kind: "manual", section_name: "Manuscript", action_id: "", completion_check: "", modes: [] },
    { id: "draft", title: "Draft the rewrite", description: "Ask Logos for an optional proposal.", kind: "creative", section_name: "Manuscript", action_id: "inline_rewrite", completion_check: "", modes: [] },
    { id: "review", title: "Review the result", description: "Inspect the applied result.", kind: "check", section_name: "Review", action_id: "", completion_check: "no_preferred_rewrite", modes: [] },
  ],
};

function workflowRun(overrides: Partial<WorkflowRunDTO> = {}): WorkflowRunDTO {
  const timestamp = "2026-10-07T12:00:00Z";
  return {
    id: 21,
    project_id: 7,
    title: "Rewrite Pass",
    description: template.description,
    status: "active",
    writing_mode: "novel",
    template_id: template.id,
    current_step_id: "draft",
    total_steps: 3,
    completed_steps: 1,
    revision: "a".repeat(64),
    source_type: "",
    source_id: null,
    created_at: timestamp,
    updated_at: timestamp,
    completed_at: null,
    steps: [
      { step_id: "select", title: "Select the passage", description: "Choose the passage.", kind: "manual", status: "completed", sort_index: 0, section_name: "Manuscript", action_id: "", completion_check: "", notes: "", target_type: "scene", target_id: 12, created_at: timestamp, updated_at: timestamp },
      { step_id: "draft", title: "Draft the rewrite", description: "Ask Logos for an optional proposal.", kind: "creative", status: "active", sort_index: 1, section_name: "Manuscript", action_id: "inline_rewrite", completion_check: "", notes: "", target_type: "scene", target_id: 12, created_at: timestamp, updated_at: timestamp },
      { step_id: "review", title: "Review the result", description: "Inspect the applied result.", kind: "check", status: "pending", sort_index: 2, section_name: "Review", action_id: "", completion_check: "no_preferred_rewrite", notes: "", target_type: "", target_id: null, created_at: timestamp, updated_at: timestamp },
    ],
    ...overrides,
  };
}

function completedCurrent(run = workflowRun()): WorkflowRunDTO {
  const next = structuredClone(run);
  next.steps[1]!.status = "completed";
  next.steps[2]!.status = "active";
  next.current_step_id = "review";
  next.completed_steps = 2;
  next.revision = "b".repeat(64);
  next.updated_at = "2026-10-07T12:01:00Z";
  return next;
}

const receipt = (command: WorkflowCommandDTO): WorkflowCommandReceiptDTO => ({
  project_id: 7,
  request_digest: "d".repeat(64),
  command_kind: command.kind,
  expected_revision: command.kind === "start_workflow" ? "" : command.expected_revision,
  applied_revision: "b".repeat(64),
  original_changed: true,
  original_run_id: 21,
  committed_at: "2026-10-07T12:01:00Z",
});

// Pure planning and recovery invariants.
const active = workflowRun();
const plannedComplete = planWorkflowCommand(active, { kind: "complete_step", stepId: "draft", notes: "  reviewed  " });
check(
  plannedComplete.command?.kind === "complete_step"
    && plannedComplete.command.expected_revision === active.revision
    && plannedComplete.command.notes === "reviewed",
  "step completion must bind the current active step and authoritative revision",
);
check(
  !planWorkflowCommand(active, { kind: "skip_step", stepId: "review" }).command,
  "pending workflow steps must never be exposed as directly actionable",
);
const paused = workflowRun({ status: "paused" });
check(
  !planWorkflowCommand(paused, { kind: "refresh" }).command
    && planWorkflowCommand(paused, { kind: "resume" }).command?.kind === "resume",
  "paused workflows must disable verify/advance while retaining an explicit resume",
);
const blocked = workflowRun({
  status: "blocked",
  steps: active.steps.map((step) => step.step_id === "draft" ? { ...step, status: "blocked" } : { ...step }),
});
check(planWorkflowCommand(blocked, { kind: "resume" }).command?.kind === "resume", "blocked workflows must retain an explicit resume path");
check(workflowSectionPanelId(" Manuscript ") === "manuscript" && workflowSectionPanelId("Run arbitrary action") === null, "section deep links must be allowlisted and fail closed");
const manyEvents = Array.from({ length: 55 }, (_, index): WorkflowEventDTO => ({
  id: index + 1, project_id: 7, workflow_run_id: 21, step_id: null,
  event_type: "changed", message: String(index + 1), metadata: {}, created_at: "2026-10-07T12:00:00Z",
}));
check(boundedWorkflowEvents(manyEvents, 40).length === 40 && boundedWorkflowEvents(manyEvents, 40)[0]?.id === 16, "the event log must retain only its newest bounded entries");
const completeCommand = plannedComplete.command!;
check(validateRecoveredWorkflowRun(completedCurrent(), completeCommand, receipt(completeCommand)) === null, "receipt recovery must validate the durable step outcome");
check(validateRecoveredWorkflowRun(active, completeCommand, receipt(completeCommand)) != null, "receipt recovery must reject a run that does not contain the promised stable step outcome");
check(workflowNoChangeMessage({ kind: "refresh", run_id: 21, expected_revision: active.revision }).includes("No verifiable"), "no-op refresh copy must not claim a mutation");

// Runtime validation accepts Core's blocked coherence and rejects malformed pointers.
check(validateWorkflowRunDTOForRequest(active, 7, 21) === active, "the runtime validator must accept a coherent active run");
check(validateWorkflowRunDTOForRequest(blocked, 7, 21) === blocked, "the runtime validator must accept a current blocked step on a blocked run");
let malformedPointer: unknown = null;
try {
  validateWorkflowRunDTOForRequest({ ...active, current_step_id: "review" }, 7, 21);
} catch (error) {
  malformedPointer = error;
}
check(malformedPointer instanceof RuntimeDtoValidationError, "the runtime validator must reject a current pointer that is not the active step");
let malformedCompleted: unknown = null;
try {
  validateWorkflowRunDTOForRequest({ ...completedCurrent(), status: "completed", current_step_id: "review" }, 7, 21);
} catch (error) {
  malformedCompleted = error;
}
check(malformedCompleted instanceof RuntimeDtoValidationError, "terminal workflow runs must fail closed when they retain a current pointer");

const platform = { isDesktop: false } as PlatformAdapter;
function tree(
  api: ApiClient,
  navigation: Array<{ panel: string; options?: StudioNavigationOptions }> = [],
) {
  return (
    <StudioProvider
      services={{ api, platform }}
      projectId={7}
      writingMode="novel"
      nav={{ navigate: (panel, options) => { navigation.push({ panel, options }); } }}
    >
      <GuidedWorkflowStepper />
    </StudioProvider>
  );
}

const eventRows = manyEvents.map((event) => ({ ...event, workflow_run_id: 21 }));
let liveRun = workflowRun();
let logosRuns = 0;
let commandCalls = 0;
let runReads = 0;
const submissions: Array<{ command: WorkflowCommandDTO; key: string }> = [];
const subscriptions: Array<(event: { event: string }) => void> = [];
const panelApi = {
  getWorkflowTemplates: async () => [structuredClone(template), { ...structuredClone(template), id: "project_setup", title: "Project Setup" }],
  getWorkflowRecommendations: async () => [{ template_id: "project_setup", title: "Project Setup", reason: "Your project is ready for its next foundation step.", severity: "suggestion" }],
  getWorkflows: async () => [structuredClone(liveRun)],
  getWorkflowRun: async () => { runReads += 1; return structuredClone(liveRun); },
  getWorkflowEvents: async () => structuredClone(eventRows),
  executeWorkflowCommand: async (_projectId: number, command: WorkflowCommandDTO, key: string): Promise<WorkflowCommandResultDTO> => {
    commandCalls += 1;
    submissions.push({ command: structuredClone(command), key });
    liveRun = completedCurrent(liveRun);
    return { workflow: structuredClone(liveRun), changed: true, replayed: false, applied_revision: liveRun.revision };
  },
  getWorkflowCommandReceipt: async (_projectId: number, _key: string, command: WorkflowCommandDTO) => receipt(command),
  runLogos: async () => { logosRuns += 1; return {}; },
  invalidatePendingReads: () => {},
  subscribe: (_projectId: number, handler: (event: { event: string }) => void) => { subscriptions.push(handler); return () => {}; },
} as unknown as ApiClient;
const navigation: Array<{ panel: string; options?: StudioNavigationOptions }> = [];
let renderer!: ReactTestRenderer;
await act(async () => {
  renderer = create(tree(panelApi, navigation));
  await flush();
});
check(text(renderer.root).includes("Rewrite Pass") && text(renderer.root).includes("Your project is ready"), "the panel must render authoritative runs, templates, and recommendations");
check(renderer.root.findAll((node) => node.props["data-workflow-event-id"] != null).length === 40, "the rendered event timeline must remain bounded");
const runningTemplate = renderer.root.findByProps({ "data-workflow-template-id": "rewrite" });
check(runningTemplate.findAllByType("button")[0]?.props.disabled === true, "a template with an unfinished run must not expose another start command");
await act(async () => {
  renderer.root.findByProps({ "aria-label": "Open Manuscript for Draft the rewrite" }).props.onClick();
  await flush();
});
check(navigation.at(-1)?.panel === "manuscript" && navigation.at(-1)?.options?.sceneId === 12, "a workflow section handoff must preserve the safe exact scene target");
await act(async () => {
  renderer.root.findByProps({ "aria-label": "Open Logos suggestion inline_rewrite" }).props.onClick();
  await flush();
});
check(navigation.at(-1)?.panel === "ai-companions" && navigation.at(-1)?.options?.aiTool === "Logos" && logosRuns === 0, "Logos handoff must only open the review surface and never execute the suggested action");
await act(async () => {
  button(renderer, "MARK COMPLETE").props.onClick();
  await flush();
});
check(
  commandCalls === 1
    && submissions[0]?.command.kind === "complete_step"
    && submissions[0]?.key.length >= 16
    && text(renderer.root).includes("Workflow state updated"),
  "the live panel must submit one revision-bound command with a fresh capability key",
);
const readsBeforeEvent = runReads;
await act(async () => {
  subscriptions.forEach((handler) => handler({ event: "workflow_changed" }));
  await new Promise((resolve) => setTimeout(resolve, 150));
  await flush();
});
check(runReads > readsBeforeEvent, "workflow_changed must invalidate the selected live run");
act(() => renderer.unmount());

// Ambiguous writes retain one exact command/key, allow one explicit resend only,
// then become receipt-only. A 503 is ambiguous just like a write timeout.
const ambiguousSubmissions: Array<{ command: WorkflowCommandDTO; key: string }> = [];
const ambiguousReceipts: Array<{ command: WorkflowCommandDTO; key: string }> = [];
const ambiguousApi = {
  getWorkflowTemplates: async () => [structuredClone(template)],
  getWorkflowRecommendations: async () => [],
  getWorkflows: async () => [workflowRun()],
  getWorkflowRun: async () => workflowRun(),
  getWorkflowEvents: async () => [],
  executeWorkflowCommand: async (_projectId: number, command: WorkflowCommandDTO, key: string) => {
    ambiguousSubmissions.push({ command: structuredClone(command), key });
    throw new ApiRequestError("POST", "/api/projects/7/workflows/commands", 503, "unavailable", "service_unavailable");
  },
  getWorkflowCommandReceipt: async (_projectId: number, key: string, command: WorkflowCommandDTO) => {
    ambiguousReceipts.push({ command: structuredClone(command), key });
    throw new ApiRequestError("GET", "/api/projects/7/workflows/command-receipt", 404, "not found", "workflow_receipt_not_found");
  },
  invalidatePendingReads: () => {},
  subscribe: () => () => {},
} as unknown as ApiClient;
let ambiguousRenderer!: ReactTestRenderer;
await act(async () => {
  ambiguousRenderer = create(tree(ambiguousApi));
  await flush();
});
await act(async () => {
  button(ambiguousRenderer, "MARK COMPLETE").props.onClick();
  await flush();
});
check(button(ambiguousRenderer, "RETRY EXACT COMMAND ONCE") != null, "an ambiguous 5xx plus clean receipt miss must offer one bounded exact resend");
await act(async () => {
  button(ambiguousRenderer, "RETRY EXACT COMMAND ONCE").props.onClick();
  await flush();
});
check(button(ambiguousRenderer, "CHECK SAME RECEIPT") != null, "after the exact resend, recovery must become receipt-only");
await act(async () => {
  button(ambiguousRenderer, "CHECK SAME RECEIPT").props.onClick();
  await flush();
});
check(
  ambiguousSubmissions.length === 2
    && ambiguousReceipts.length === 3
    && ambiguousSubmissions.every((entry) => entry.key === ambiguousSubmissions[0]?.key
      && JSON.stringify(entry.command) === JSON.stringify(ambiguousSubmissions[0]?.command))
    && ambiguousReceipts.every((entry) => entry.key === ambiguousSubmissions[0]?.key
      && JSON.stringify(entry.command) === JSON.stringify(ambiguousSubmissions[0]?.command)),
  "ambiguous recovery must never mint another key or alter the exact command, and must never post more than twice",
);
act(() => ambiguousRenderer.unmount());

// A stale 409 is definite: refresh once, do not replay blindly, and release the key.
let stalePosts = 0;
let staleReads = 0;
const staleApi = {
  getWorkflowTemplates: async () => [structuredClone(template)],
  getWorkflowRecommendations: async () => [],
  getWorkflows: async () => [workflowRun()],
  getWorkflowRun: async () => { staleReads += 1; return workflowRun(); },
  getWorkflowEvents: async () => [],
  executeWorkflowCommand: async () => {
    stalePosts += 1;
    throw new ApiRequestError("POST", "/api/projects/7/workflows/commands", 409, "stale", "workflow_conflict");
  },
  invalidatePendingReads: () => {},
  subscribe: () => () => {},
} as unknown as ApiClient;
let staleRenderer!: ReactTestRenderer;
await act(async () => {
  staleRenderer = create(tree(staleApi));
  await flush();
});
const staleReadsBefore = staleReads;
await act(async () => {
  button(staleRenderer, "MARK COMPLETE").props.onClick();
  await flush();
});
check(
  stalePosts === 1
    && staleReads > staleReadsBefore
    && text(staleRenderer.root).includes("changed in another surface")
    && staleRenderer.root.findAllByProps({ "aria-label": "Retry exact workflow command once" }).length === 0,
  "stale workflow conflicts must reconcile from authoritative state without a blind retry",
);
act(() => staleRenderer.unmount());

console.log(`${assertions} Guided Workflow transaction, validator, panel, and recovery assertions passed.`);

for (const handle of process._getActiveHandles()) {
  if (handle instanceof MessagePort) handle.unref();
}
