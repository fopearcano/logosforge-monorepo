import { MessagePort } from "node:worker_threads";
import { useEffect } from "react";
import { act, create, type ReactTestInstance, type ReactTestRenderer } from "react-test-renderer";
import type {
  ContinuityCommandDTO,
  ContinuityCommandResultDTO,
  ContinuityReportDTO,
} from "@logosforge/ui-contracts";
import type { ApiClient } from "../src/adapters/api";
import type { PlatformAdapter } from "../src/adapters/platform";
import { StudioProvider, type StudioNavigationOptions } from "../src/adapters/StudioProvider";
import { ContinuityPanel } from "../src/components/projectos/ContinuityPanel";
import { ApiRequestError, ApiRequestTimeoutError } from "../src/adapters/httpApiClient";
import { AssistantDock } from "../src/components/aipanels/AssistantDock";
import { useSelection } from "../src/adapters/selection";

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

interface Deferred<T> {
  promise: Promise<T>;
  resolve(value: T): void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((next) => { resolve = next; });
  return { promise, resolve };
}

function SelectSceneForTest({ sceneId, selectedText = "" }: { sceneId: number; selectedText?: string }) {
  const { setSelection } = useSelection();
  return (
    <button
      type="button"
      onClick={() => setSelection({ sceneId, text: selectedText, section: "Manuscript" })}
    >SET TEST SELECTION</button>
  );
}

const report: ContinuityReportDTO = {
  project_id: 7,
  review_revision: "a".repeat(64),
  writing_mode: "novel",
  blocking_count: 1,
  warning_count: 0,
  unavailable: [],
  issues: [{
    id: "0123456789abcdef",
    review_fingerprint: "f".repeat(64),
    issue_type: "continuity_gap",
    dimension: "plot",
    severity: "blocking",
    confidence: "confirmed",
    title: "A setup link points to a missing scene.",
    explanation: "The linked payoff no longer exists.",
    suggested_action: "Repair the setup/payoff link.",
    related_scene_ids: [12],
    status: "open",
  }],
};

function reviewedReport(
  projectId = 7,
  status: "open" | "deferred" | "dismissed" | "resolved" = "open",
  revision = "a".repeat(64),
): ContinuityReportDTO {
  const issue = { ...report.issues[0]!, status };
  return {
    ...report,
    project_id: projectId,
    review_revision: revision,
    issues: [issue],
    blocking_count: status === "open" ? 1 : 0,
  };
}

const api = {
  getContinuity: async () => report,
  subscribe: () => () => {},
} as unknown as ApiClient;
const platform = { isDesktop: false } as PlatformAdapter;
const navigation: Array<{ panel: string; options?: StudioNavigationOptions }> = [];
let clears = 0;
let focused = 0;
let scrolled = 0;
const focusDocument = { activeElement: null as unknown };
const focusThief = {};
const focusFrames = new Map<number, FrameRequestCallback>();
let nextFocusFrame = 1;
const previousFocusWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
Object.defineProperty(globalThis, "window", {
  configurable: true,
  value: {
    requestAnimationFrame: (callback: FrameRequestCallback) => {
      const id = nextFocusFrame;
      nextFocusFrame += 1;
      focusFrames.set(id, callback);
      return id;
    },
    cancelAnimationFrame: (id: number) => { focusFrames.delete(id); },
  },
});

function runFocusFrame() {
  const scheduled = [...focusFrames.values()];
  focusFrames.clear();
  for (const callback of scheduled) callback(0);
}

function tree(
  issueKey: string | null,
  apiClient: ApiClient = api,
  onClear: () => void = () => { clears += 1; },
) {
  return (
    <StudioProvider
      services={{ api: apiClient, platform }}
      projectId={7}
      nav={{
        navigate: (panel, options) => navigation.push({ panel, options }),
        continuityTargetIssueKey: issueKey,
        clearContinuityTarget: onClear,
      }}
    >
      <ContinuityPanel />
    </StudioProvider>
  );
}

async function flush() {
  for (let index = 0; index < 12; index += 1) await Promise.resolve();
}

let renderer!: ReactTestRenderer;
await act(async () => {
  renderer = create(tree("0123456789abcdef"), {
    createNodeMock: (element) => {
      if (!element.props["data-continuity-issue-id"]) return {};
      const node = {
        ownerDocument: focusDocument,
        focus: () => {
          focused += 1;
          focusDocument.activeElement = node;
        },
        scrollIntoView: () => { scrolled += 1; },
      };
      return node;
    },
  });
  await flush();
});

check(clears === 0 && focused === 0, "a continuity target must remain pending until its issue card is focusable");
await act(async () => { runFocusFrame(); await Promise.resolve(); });
check(clears === 0 && focused === 1, "calling focus must not immediately consume the continuity target");
focusDocument.activeElement = focusThief;
await act(async () => { runFocusFrame(); await Promise.resolve(); });
check(clears === 0, "a first focus stolen before the confirmation frame must keep the target pending");
await act(async () => { runFocusFrame(); await Promise.resolve(); });
await act(async () => { runFocusFrame(); await Promise.resolve(); });

const focusedIssue = renderer.root.findByProps({
  "data-continuity-issue-id": "0123456789abcdef",
});
check(focusedIssue.props.style.border.includes("var(--cyan)"), "the exact continuity issue must be visibly focused");
check(clears === 1 && focused === 2 && scrolled === 2, "an authoritative issue target must retry stolen focus and consume exactly once after stable focus");

await act(async () => {
  renderer.update(tree("0123456789abcdef"));
  await flush();
});
check(clears === 1, "a static provider must not cause repeated continuity target consumption");

const sceneButton = renderer.root.findByProps({
  "aria-label": "Open scene 12 for continuity issue",
});
act(() => sceneButton.props.onClick());
check(
  navigation.at(-1)?.panel === "Manuscript" && navigation.at(-1)?.options?.sceneId === 12,
  "Continuity issue scene chips must deep-link the exact manuscript scene",
);

await act(async () => {
  renderer.update(tree(null));
  await flush();
  renderer.update(tree("0123456789abcdef"));
  await flush();
});
await act(async () => { runFocusFrame(); await Promise.resolve(); });
check(focusFrames.size === 1, "the stable-focus confirmation frame must remain cancellable");
await act(async () => {
  renderer.update(tree("ffffffffffffffff"));
  await flush();
});
check(clears === 2, "a stale continuity target must be consumed instead of remaining pending");
check(focusFrames.size === 0, "a new continuity target must cancel the prior target's pending focus confirmation");
const stale = renderer.root.findByProps({ role: "status" });
check(text(stale).includes("no longer present"), "a stale continuity target must be reported truthfully");

await act(async () => {
  renderer.update(tree(null));
  await flush();
  renderer.update(tree("0123456789abcdef"));
  await flush();
});
await act(async () => { runFocusFrame(); await Promise.resolve(); });
check(focusFrames.size === 1, "a mounted target should have one pending full-frame focus confirmation");
act(() => renderer.unmount());
check(focusFrames.size === 0 && clears === 2, "unmount must cancel pending focus work without consuming its target");
if (previousFocusWindow) Object.defineProperty(globalThis, "window", previousFocusWindow);
else delete (globalThis as unknown as { window?: unknown }).window;

let resolvePostBarrier!: (value: ContinuityReportDTO) => void;
const postBarrierReport = new Promise<ContinuityReportDTO>((resolve) => {
  resolvePostBarrier = resolve;
});
let cachedReads = 0;
const cachedApi = {
  getContinuity: async () => {
    cachedReads += 1;
    return cachedReads === 1 ? report : postBarrierReport;
  },
  invalidatePendingReads: () => {},
  subscribe: () => () => {},
} as unknown as ApiClient;
let cachedClears = 0;
let cachedRenderer!: ReactTestRenderer;
await act(async () => {
  cachedRenderer = create(tree(null, cachedApi, () => { cachedClears += 1; }));
  await flush();
});
await act(async () => {
  cachedRenderer.update(tree(
    "0123456789abcdef",
    cachedApi,
    () => { cachedClears += 1; },
  ));
  await Promise.resolve();
});
check(
  cachedReads === 2 && cachedClears === 0,
  "a target arriving over a cached panel must wait for its own authoritative refresh",
);
resolvePostBarrier({ ...report, blocking_count: 0, issues: [] });
await act(async () => {
  await flush();
});
check(
  cachedClears === 1,
  "the cached-panel target must be consumed only after the post-barrier refresh settles",
);
const refreshedStale = cachedRenderer.root.findByProps({ role: "status" });
check(
  text(refreshedStale).includes("no longer present"),
  "the post-barrier report, not cached data, must decide whether an issue is stale",
);
act(() => cachedRenderer.unmount());

let reviewStatus: "open" | "resolved" = "open";
let reviewReads = 0;
const submittedReviews: Array<{ projectId: number; command: ContinuityCommandDTO; key: string }> = [];
const reviewApi = {
  getContinuity: async (projectId: number) => {
    reviewReads += 1;
    const revision = reviewReads === 1 ? "a".repeat(64) : reviewStatus === "open" ? "b".repeat(64) : "c".repeat(64);
    return reviewedReport(projectId, reviewStatus, revision);
  },
  executeContinuityCommand: async (
    projectId: number,
    command: ContinuityCommandDTO,
    key: string,
  ): Promise<ContinuityCommandResultDTO> => {
    submittedReviews.push({ projectId, command: structuredClone(command), key });
    reviewStatus = "resolved";
    return {
      continuity: reviewedReport(projectId, "resolved", "c".repeat(64)),
      changed: true,
      affected_issue_id: command.issue_id,
      previous_status: "open",
      status: "resolved",
      replayed: false,
      applied_revision: "c".repeat(64),
    };
  },
  getContinuityCommandReceipt: async () => { throw new Error("receipt lookup should not run for a successful write"); },
  invalidatePendingReads: () => {},
  subscribe: () => () => {},
} as unknown as ApiClient;
let reviewRenderer!: ReactTestRenderer;
await act(async () => {
  reviewRenderer = create(tree(null, reviewApi));
  await flush();
});
await act(async () => {
  button(reviewRenderer, "RESOLVE").props.onClick({ currentTarget: { focus: () => {} } });
  await flush();
});
check(submittedReviews.length === 0, "opening a Continuity review must not mutate state");
const decisionDialog = reviewRenderer.root.findByProps({ role: "dialog" });
check(
  text(decisionDialog).includes("does not edit manuscript text or run AI"),
  "the explicit Continuity confirmation must distinguish review state from manuscript repair",
);
await act(async () => {
  button(reviewRenderer, "CONFIRM DECISION").props.onClick();
  await flush();
});
check(
  submittedReviews.length === 1
    && submittedReviews[0]?.projectId === 7
    && submittedReviews[0]?.command.kind === "resolve_issue"
    && submittedReviews[0]?.command.expected_revision === "b".repeat(64)
    && submittedReviews[0]!.key.length >= 16,
  "a Continuity decision must bind the post-barrier revision and one capability-sized key",
);
check(text(reviewRenderer.root).includes("Continuity review decision saved"), "a committed Continuity review must announce success");
check(reviewRenderer.root.findAllByType("button").filter((candidate) => text(candidate) === "RESOLVE").length === 0, "reviewed issues must stop offering open-only actions after refresh");
act(() => reviewRenderer.unmount());

let recoveredReads = 0;
let receiptChecks = 0;
let recoveredSubmissions = 0;
const recoveredApi = {
  getContinuity: async (projectId: number) => {
    recoveredReads += 1;
    return reviewedReport(
      projectId,
      recoveredSubmissions > 0 ? "resolved" : "open",
      recoveredSubmissions > 0 ? "c".repeat(64) : recoveredReads === 1 ? "a".repeat(64) : "b".repeat(64),
    );
  },
  executeContinuityCommand: async (projectId: number) => {
    recoveredSubmissions += 1;
    throw new ApiRequestTimeoutError("POST", `/api/projects/${projectId}/continuity/commands`, 50);
  },
  getContinuityCommandReceipt: async (projectId: number, _key: string, command: ContinuityCommandDTO) => {
    receiptChecks += 1;
    return {
      project_id: projectId,
      request_digest: "d".repeat(64),
      command_kind: command.kind,
      expected_revision: command.expected_revision,
      applied_revision: "c".repeat(64),
      original_changed: true,
      original_affected_issue_id: command.issue_id,
      expected_issue_fingerprint: command.expected_issue_fingerprint,
      previous_status: "open" as const,
      status: "resolved" as const,
      committed_at: "2026-10-07T12:00:00Z",
    };
  },
  invalidatePendingReads: () => {},
  subscribe: () => () => {},
} as unknown as ApiClient;
let recoveredRenderer!: ReactTestRenderer;
await act(async () => {
  recoveredRenderer = create(tree(null, recoveredApi));
  await flush();
});
await act(async () => {
  button(recoveredRenderer, "RESOLVE").props.onClick({ currentTarget: { focus: () => {} } });
  await flush();
});
await act(async () => {
  button(recoveredRenderer, "CONFIRM DECISION").props.onClick();
  await flush();
});
check(
  recoveredSubmissions === 1 && receiptChecks === 1
    && text(recoveredRenderer.root).includes("Recovered the committed Continuity decision"),
  "an ambiguous write must recover from the durable receipt without resubmitting",
);
act(() => recoveredRenderer.unmount());

let resendAttempts = 0;
const resendSubmissions: Array<{ command: ContinuityCommandDTO; key: string }> = [];
const resendApi = {
  getContinuity: async (projectId: number) => reviewedReport(
    projectId,
    resendAttempts >= 2 ? "resolved" : "open",
    resendAttempts >= 2 ? "c".repeat(64) : "b".repeat(64),
  ),
  executeContinuityCommand: async (projectId: number, command: ContinuityCommandDTO, key: string): Promise<ContinuityCommandResultDTO> => {
    resendAttempts += 1;
    resendSubmissions.push({ command: structuredClone(command), key });
    if (resendAttempts === 1) {
      throw new ApiRequestTimeoutError("POST", `/api/projects/${projectId}/continuity/commands`, 50);
    }
    return {
      continuity: reviewedReport(projectId, "resolved", "c".repeat(64)),
      changed: true,
      affected_issue_id: command.issue_id,
      previous_status: "open",
      status: "resolved",
      replayed: false,
      applied_revision: "c".repeat(64),
    };
  },
  getContinuityCommandReceipt: async () => {
    throw new ApiRequestError("GET", "/api/projects/7/continuity/command-receipt", 404, "not found", "continuity_receipt_not_found");
  },
  invalidatePendingReads: () => {},
  subscribe: () => () => {},
} as unknown as ApiClient;
let resendRenderer!: ReactTestRenderer;
await act(async () => {
  resendRenderer = create(tree(null, resendApi));
  await flush();
});
await act(async () => {
  button(resendRenderer, "RESOLVE").props.onClick({ currentTarget: { focus: () => {} } });
  await flush();
});
await act(async () => {
  button(resendRenderer, "CONFIRM DECISION").props.onClick();
  await flush();
});
check(text(resendRenderer.root).includes("One retry may reuse this exact reviewed command"), "a clean receipt miss must offer exactly one same-proposal resend");
await act(async () => {
  button(resendRenderer, "RETRY EXACT COMMAND").props.onClick();
  await flush();
});
check(
  resendSubmissions.length === 2
    && resendSubmissions[0]?.key === resendSubmissions[1]?.key
    && JSON.stringify(resendSubmissions[0]?.command) === JSON.stringify(resendSubmissions[1]?.command),
  "the one allowed resend must preserve the exact command and Idempotency-Key",
);
act(() => resendRenderer.unmount());

let exhaustedPosts = 0;
let exhaustedReceiptChecks = 0;
const exhaustedCommands: Array<{ command: ContinuityCommandDTO; key: string }> = [];
const exhaustedReceiptRequests: Array<{ command: ContinuityCommandDTO; key: string }> = [];
const exhaustedApi = {
  getContinuity: async (projectId: number) => reviewedReport(projectId, "open", "b".repeat(64)),
  executeContinuityCommand: async (projectId: number, command: ContinuityCommandDTO, key: string) => {
    exhaustedPosts += 1;
    exhaustedCommands.push({ command: structuredClone(command), key });
    throw new ApiRequestTimeoutError("POST", `/api/projects/${projectId}/continuity/commands`, 50);
  },
  getContinuityCommandReceipt: async (_projectId: number, key: string, command: ContinuityCommandDTO) => {
    exhaustedReceiptChecks += 1;
    exhaustedReceiptRequests.push({ command: structuredClone(command), key });
    throw new ApiRequestError("GET", "/api/projects/7/continuity/command-receipt", 404, "not found", "continuity_receipt_not_found");
  },
  invalidatePendingReads: () => {},
  subscribe: () => () => {},
} as unknown as ApiClient;
let exhaustedRenderer!: ReactTestRenderer;
await act(async () => {
  exhaustedRenderer = create(tree(null, exhaustedApi));
  await flush();
});
await act(async () => {
  button(exhaustedRenderer, "RESOLVE").props.onClick({ currentTarget: { focus: () => {} } });
  await flush();
});
await act(async () => {
  button(exhaustedRenderer, "CONFIRM DECISION").props.onClick();
  await flush();
});
await act(async () => {
  button(exhaustedRenderer, "RETRY EXACT COMMAND").props.onClick();
  await flush();
});
await act(async () => {
  button(exhaustedRenderer, "CHECK RECEIPT").props.onClick();
  await flush();
});
check(
  exhaustedPosts === 2 && exhaustedReceiptChecks === 3
    && exhaustedCommands.every((entry) => entry.key === exhaustedCommands[0]?.key
      && JSON.stringify(entry.command) === JSON.stringify(exhaustedCommands[0]?.command))
    && exhaustedReceiptRequests.every((entry) => entry.key === exhaustedCommands[0]?.key
      && JSON.stringify(entry.command) === JSON.stringify(exhaustedCommands[0]?.command)),
  "after one exact resend, recovery must become receipt-only and retain the exact command capability",
);
act(() => exhaustedRenderer.unmount());

let apiAPosts = 0;
let apiBPosts = 0;
const apiA = {
  getContinuity: async () => reviewedReport(7, "open", "b".repeat(64)),
  executeContinuityCommand: async () => { apiAPosts += 1; throw new Error("unexpected api A write"); },
  subscribe: () => () => {},
  invalidatePendingReads: () => {},
} as unknown as ApiClient;
const apiB = {
  getContinuity: async () => reviewedReport(7, "open", "d".repeat(64)),
  executeContinuityCommand: async () => { apiBPosts += 1; throw new Error("unexpected api B write"); },
  subscribe: () => () => {},
  invalidatePendingReads: () => {},
} as unknown as ApiClient;
let adapterSwapRenderer!: ReactTestRenderer;
await act(async () => {
  adapterSwapRenderer = create(tree(null, apiA));
  await flush();
});
await act(async () => {
  button(adapterSwapRenderer, "RESOLVE").props.onClick({ currentTarget: { focus: () => {} } });
  await flush();
});
const oldAdapterConfirm = button(adapterSwapRenderer, "CONFIRM DECISION");
const oldAdapterConfirmHandler = oldAdapterConfirm.props.onClick as () => void;
await act(async () => {
  adapterSwapRenderer.update(tree(null, apiB));
  await flush();
});
act(() => oldAdapterConfirmHandler());
await act(async () => { await flush(); });
check(
  apiAPosts === 0 && apiBPosts === 0
    && adapterSwapRenderer.root.findAllByProps({ role: "dialog" }).length === 0,
  "a same-project API adapter swap must invalidate an older reviewed proposal before dispatch",
);
act(() => adapterSwapRenderer.unmount());

const preflight = deferred<ContinuityReportDTO>();
let preflightReads = 0;
let preflightPosts = 0;
const preflightApi = {
  getContinuity: async (projectId: number) => {
    if (projectId === 8) return reviewedReport(8, "open", "e".repeat(64));
    preflightReads += 1;
    return preflightReads === 1
      ? reviewedReport(7, "open", "a".repeat(64))
      : preflight.promise;
  },
  executeContinuityCommand: async () => { preflightPosts += 1; throw new Error("unexpected preflight write"); },
  subscribe: () => () => {},
  invalidatePendingReads: () => {},
} as unknown as ApiClient;
let preflightRenderer!: ReactTestRenderer;
await act(async () => {
  preflightRenderer = create(tree(null, preflightApi));
  await flush();
});
await act(async () => {
  button(preflightRenderer, "RESOLVE").props.onClick({ currentTarget: { focus: () => {} } });
  for (let index = 0; index < 6; index += 1) await Promise.resolve();
});
check(preflightReads === 2, "project-switch preflight coverage must hold an authoritative refresh in flight");
await act(async () => {
  preflightRenderer.update(
    <StudioProvider services={{ api: preflightApi, platform }} projectId={8} nav={{ navigate: () => {} }}>
      <ContinuityPanel />
    </StudioProvider>,
  );
  await flush();
});
await act(async () => {
  preflight.resolve(reviewedReport(7, "open", "b".repeat(64)));
  await flush();
});
check(
  preflightPosts === 0 && preflightRenderer.root.findAllByProps({ role: "dialog" }).length === 0,
  "a project switch during fresh preflight must discard the old owner without opening or dispatching a proposal",
);
act(() => preflightRenderer.unmount());

const staleCommand = deferred<ContinuityCommandResultDTO>();
let staleCommandStarted = false;
const staleApi = {
  getContinuity: async (projectId: number) => reviewedReport(projectId, "open", "b".repeat(64)),
  executeContinuityCommand: async () => {
    staleCommandStarted = true;
    return staleCommand.promise;
  },
  getContinuityCommandReceipt: async () => { throw new Error("receipt lookup should not run"); },
  invalidatePendingReads: () => {},
  subscribe: () => () => {},
} as unknown as ApiClient;
let staleRenderer!: ReactTestRenderer;
await act(async () => {
  staleRenderer = create(tree(null, staleApi));
  await flush();
});
await act(async () => {
  button(staleRenderer, "RESOLVE").props.onClick({ currentTarget: { focus: () => {} } });
  await flush();
});
await act(async () => {
  button(staleRenderer, "CONFIRM DECISION").props.onClick();
  await flush();
});
check(staleCommandStarted, "project-switch coverage must hold a real in-flight Continuity command");
await act(async () => {
  staleRenderer.update(
    <StudioProvider services={{ api: staleApi, platform }} projectId={8} nav={{ navigate: () => {} }}>
      <ContinuityPanel />
    </StudioProvider>,
  );
  await flush();
});
await act(async () => {
  staleCommand.resolve({
    continuity: reviewedReport(7, "resolved", "c".repeat(64)),
    changed: true,
    affected_issue_id: report.issues[0]!.id,
    previous_status: "open",
    status: "resolved",
    replayed: false,
    applied_revision: "c".repeat(64),
  });
  await flush();
});
check(
  !text(staleRenderer.root).includes("Continuity review decision saved"),
  "a delayed old-project command must not announce or repopulate state in the new project",
);
act(() => staleRenderer.unmount());

navigation.length = 0;
let repairRenderer!: ReactTestRenderer;
await act(async () => {
  repairRenderer = create(tree(null));
  await flush();
});
await act(async () => {
  button(repairRenderer, "REPAIR SC.12").props.onClick();
  await flush();
});
const repairNavigation = navigation.at(-1);
check(
  repairNavigation?.panel === "ai-companions"
    && repairNavigation.options?.aiTool === "Billy"
    && repairNavigation.options?.sceneId === 12
    && (repairNavigation.options?.continuityRepair?.handoffId.length ?? 0) >= 16
    && repairNavigation.options?.continuityRepair?.ownerProjectId === 7
    && repairNavigation.options.continuityRepair.issueId === report.issues[0]!.id
    && repairNavigation.options.continuityRepair.draft.includes("Do not alter the manuscript automatically"),
  "repair handoff must stage an unsent Billy brief for the explicitly selected scene",
);
act(() => repairRenderer.unmount());

let stoppedNavigationCount = 0;
let stoppedRepairRenderer!: ReactTestRenderer;
await act(async () => {
  stoppedRepairRenderer = create(
    <StudioProvider
      services={{ api, platform }}
      projectId={7}
      nav={{
        navigate: async () => {
          stoppedNavigationCount += 1;
          return false;
        },
      }}
    >
      <ContinuityPanel />
    </StudioProvider>,
  );
  await flush();
});
await act(async () => {
  button(stoppedRepairRenderer, "REPAIR SC.12").props.onClick();
  await flush();
});
check(
  stoppedNavigationCount === 1
    && text(stoppedRepairRenderer.root).includes("Billy did not receive the repair handoff")
    && !text(stoppedRepairRenderer.root).includes("Sent Billy a repair handoff"),
  "a stopped workspace navigation must not claim that Billy received a repair handoff",
);
act(() => stoppedRepairRenderer.unmount());

let stagedClearCount = 0;
let stagedClearedHandoff = "";
let stagedAssistantCalls = 0;
const stagedDraft = "Review this continuity repair without sending it automatically.";
const stagedApi = {
  listScenes: async () => [{
    id: 12,
    title: "Observation Ring",
    summary: "",
    synopsis: "",
    goal: "",
    conflict: "",
    outcome: "",
    beat: "",
    act: "",
    chapter: "",
    plotline: "",
    color_label: "",
    tags: [],
    content: "Original scene prose.",
    sort_order: 12,
    order_index: 12,
    character_ids: [],
    place_ids: [],
    who_knows_what: "",
    revision: "scene-revision",
  }],
  assistantChat: async () => {
    stagedAssistantCalls += 1;
    return { reply: "Proposed repair." };
  },
  subscribe: () => () => {},
} as unknown as ApiClient;
let stagedRenderer!: ReactTestRenderer;
let stagedInputFocuses = 0;
let stagedInputPreventedScroll = false;
await act(async () => {
  stagedRenderer = create(
    <StudioProvider
      services={{ api: stagedApi, platform }}
      projectId={7}
      nav={{
        continuityRepairTarget: {
          handoffId: "repair-handoff-stage-0001",
          ownerProjectId: 7,
          issueId: report.issues[0]!.id,
          sceneId: 12,
          draft: stagedDraft,
        },
        clearContinuityRepairTarget: (handoffId) => {
          stagedClearCount += 1;
          stagedClearedHandoff = handoffId ?? "";
        },
      }}
    >
      <AssistantDock />
    </StudioProvider>,
    {
      createNodeMock: (element) => element.props["aria-label"] === "Message Billy"
        ? {
            focus: (options?: FocusOptions) => {
              stagedInputFocuses += 1;
              stagedInputPreventedScroll = options?.preventScroll === true;
            },
          }
        : {},
    },
  );
  await flush();
});
check(
  stagedRenderer.root.findByProps({ "aria-label": "Message Billy" }).props.value === stagedDraft
    && text(stagedRenderer.root).includes("brief staged, not sent")
    && text(stagedRenderer.root).includes("SC.12")
    && stagedClearCount >= 1
    && stagedClearedHandoff === "repair-handoff-stage-0001"
    && stagedAssistantCalls === 0
    && stagedInputFocuses >= 1
    && stagedInputPreventedScroll,
  "Billy must consume the one-shot repair handoff as an unsent, scene-bound draft",
);
act(() => stagedRenderer.unmount());

const existingBillyDraft = "Do not lose this unsent author draft.";
const protectedRepairTarget = {
  handoffId: "repair-handoff-preserve-0001",
  ownerProjectId: 7,
  issueId: report.issues[0]!.id,
  sceneId: 12,
  draft: "Incoming Continuity repair brief.",
};
let protectedClearCount = 0;
const protectedTree = (target: typeof protectedRepairTarget | null) => (
  <StudioProvider
    services={{ api: stagedApi, platform }}
    projectId={7}
    nav={{
      continuityRepairTarget: target,
      clearContinuityRepairTarget: () => { protectedClearCount += 1; },
    }}
  >
    <AssistantDock />
  </StudioProvider>
);
let protectedRenderer!: ReactTestRenderer;
let protectedReplaceFocuses = 0;
let protectedReplacePreventedScroll = false;
await act(async () => {
  protectedRenderer = create(protectedTree(null), {
    createNodeMock: (element) => {
      if (element.type === "button" && element.props.children === "REPLACE DRAFT") return {
          focus: (options?: FocusOptions) => {
            protectedReplaceFocuses += 1;
            protectedReplacePreventedScroll = options?.preventScroll === true;
          },
        };
      if (element.props["aria-label"] === "Message Billy") return { focus: () => {} };
      return {};
    },
  });
  await flush();
  protectedRenderer.root.findByProps({ "aria-label": "Message Billy" }).props.onChange({
    target: { value: existingBillyDraft },
  });
  await flush();
  protectedRenderer.update(protectedTree(protectedRepairTarget));
  await flush();
  protectedRenderer.update(protectedTree(null));
  await flush();
});
check(
  protectedRenderer.root.findByProps({ "aria-label": "Message Billy" }).props.value === existingBillyDraft,
  "a Continuity handoff must not overwrite an existing unsent Billy draft",
);
check(
  text(protectedRenderer.root).includes("existing Billy draft preserved")
    && protectedClearCount >= 1
    && protectedReplaceFocuses >= 1
    && protectedReplacePreventedScroll,
  "a blocked repair handoff must be consumed once and ask before replacing the draft",
);
await act(async () => {
  button(protectedRenderer, "REPLACE DRAFT").props.onClick();
  await flush();
});
check(
  protectedRenderer.root.findByProps({ "aria-label": "Message Billy" }).props.value
    === protectedRepairTarget.draft
    && text(protectedRenderer.root).includes("brief staged, not sent")
    && !text(protectedRenderer.root).includes("existing Billy draft preserved"),
  "explicit replacement must stage the waiting repair brief without sending it",
);
act(() => protectedRenderer.unmount());

const assistantScenes = [
  {
    id: 12, title: "Observation Ring", content: "Original scene twelve.", revision: "rev-12",
    summary: "", synopsis: "", goal: "", conflict: "", outcome: "", beat: "", act: "",
    chapter: "", plotline: "", color_label: "", tags: [], sort_order: 12, order_index: 12,
    character_ids: [], place_ids: [], who_knows_what: "",
  },
  {
    id: 13, title: "Reactor Walk", content: "Original scene thirteen.", revision: "rev-13",
    summary: "", synopsis: "", goal: "", conflict: "", outcome: "", beat: "", act: "",
    chapter: "", plotline: "", color_label: "", tags: [], sort_order: 13, order_index: 13,
    character_ids: [], place_ids: [], who_knows_what: "",
  },
];
const delayedScenes = deferred<typeof assistantScenes>();
const delayedRepairBodies: Array<Record<string, unknown>> = [];
const delayedRepairApi = {
  listScenes: async () => delayedScenes.promise,
  assistantChat: async (_projectId: number, body: Record<string, unknown>) => {
    delayedRepairBodies.push(structuredClone(body));
    return { reply: "Scene-bound repair proposal." };
  },
  invalidatePendingReads: () => {},
  subscribe: () => () => {},
} as unknown as ApiClient;
const delayedRepairTarget = {
  handoffId: "repair-loading-handoff-0001",
  ownerProjectId: 7,
  issueId: report.issues[0]!.id,
  sceneId: 12,
  draft: "Wait for scene twelve before sending.",
};
const delayedRepairTree = (target: typeof delayedRepairTarget | null) => (
  <StudioProvider
    services={{ api: delayedRepairApi, platform }}
    projectId={7}
    nav={{ continuityRepairTarget: target, clearContinuityRepairTarget: () => {} }}
  >
    <SelectSceneForTest sceneId={13} selectedText="Unrelated Reactor Walk selection." />
    <AssistantDock />
  </StudioProvider>
);
let delayedRepairRenderer!: ReactTestRenderer;
await act(async () => {
  delayedRepairRenderer = create(delayedRepairTree(delayedRepairTarget));
  await flush();
  delayedRepairRenderer.update(delayedRepairTree(null));
  button(delayedRepairRenderer, "SET TEST SELECTION").props.onClick();
  await flush();
});
check(
  button(delayedRepairRenderer, "SEND").props.disabled === true
    && text(delayedRepairRenderer.root).includes("Loading SC.12"),
  "a scene-bound repair must stay unsent until its exact Scene is authoritative",
);
await act(async () => {
  button(delayedRepairRenderer, "SEND").props.onClick();
  await flush();
});
check(delayedRepairBodies.length === 0, "the send guard must reject programmatic sends while the repair Scene is unresolved");
await act(async () => {
  delayedScenes.resolve(assistantScenes.map((scene) => ({ ...scene })));
  await flush();
});
check(button(delayedRepairRenderer, "SEND").props.disabled === false, "Billy must enable send after the exact repair Scene loads");
await act(async () => {
  button(delayedRepairRenderer, "SEND").props.onClick();
  await flush();
});
check(
  delayedRepairBodies.length === 1
    && delayedRepairBodies[0]?.active_scene_id === 12
    && delayedRepairBodies[0]?.selected_text == null
    && text(delayedRepairRenderer.root).includes("→ Observation Ring"),
  "a loaded repair must retain its exact apply target and omit unrelated selection text",
);
act(() => delayedRepairRenderer.unmount());

const firstRepairReply = deferred<{ reply: string }>();
const repairChatBodies: Array<Record<string, unknown>> = [];
const repairWrites: Array<{ projectId: number; sceneId: number; body: Record<string, unknown> }> = [];
let repairSceneReads = 0;
const repairApi = {
  listScenes: async () => {
    repairSceneReads += 1;
    return assistantScenes.map((scene) => scene.id === 12 && repairSceneReads > 1
      ? { ...scene, content: "Fresh authoritative scene twelve.", revision: "rev-12-fresh" }
      : { ...scene });
  },
  assistantChat: async (_projectId: number, body: Record<string, unknown>) => {
    repairChatBodies.push(structuredClone(body));
    return firstRepairReply.promise;
  },
  updateScene: async (projectId: number, sceneId: number, body: Record<string, unknown>) => {
    repairWrites.push({ projectId, sceneId, body: structuredClone(body) });
    return { ...assistantScenes.find((scene) => scene.id === sceneId)!, ...body };
  },
  invalidatePendingReads: () => {},
  subscribe: () => () => {},
} as unknown as ApiClient;
const repairTargetA = {
  handoffId: "repair-race-handoff-0001",
  ownerProjectId: 7,
  issueId: report.issues[0]!.id,
  sceneId: 12,
  draft: "Repair scene twelve.",
};
const repairTargetB = {
  handoffId: "repair-race-handoff-0002",
  ownerProjectId: 7,
  issueId: report.issues[0]!.id,
  sceneId: 13,
  draft: "Repair scene thirteen.",
};
const assistantTree = (target: typeof repairTargetA | null) => (
  <StudioProvider
    services={{ api: repairApi, platform }}
    projectId={7}
    nav={{ continuityRepairTarget: target, clearContinuityRepairTarget: () => {} }}
  >
    <AssistantDock />
  </StudioProvider>
);
let repairRaceRenderer!: ReactTestRenderer;
await act(async () => {
  repairRaceRenderer = create(assistantTree(repairTargetA));
  await flush();
  repairRaceRenderer.update(assistantTree(null));
  await flush();
});
await act(async () => {
  button(repairRaceRenderer, "SEND").props.onClick();
  for (let index = 0; index < 6; index += 1) await Promise.resolve();
});
check(
  repairChatBodies.length === 1 && repairChatBodies[0]?.active_scene_id === 12,
  "a scene-bound repair request must send the explicitly selected Scene id",
);
await act(async () => {
  repairRaceRenderer.update(assistantTree(repairTargetB));
  await flush();
  repairRaceRenderer.update(assistantTree(null));
  await flush();
});
await act(async () => {
  firstRepairReply.resolve({ reply: "Replacement prose for scene twelve." });
  await flush();
});
check(
  text(repairRaceRenderer.root).includes("→ Observation Ring")
    && !text(repairRaceRenderer.root).includes("→ Reactor Walk"),
  "an older Billy reply must retain its request-time repair target after a newer handoff arrives",
);

const previousWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
Object.defineProperty(globalThis, "window", {
  configurable: true,
  value: { addEventListener: () => {}, removeEventListener: () => {} },
});
await act(async () => {
  button(repairRaceRenderer, "↧ REPLACE").props.onClick();
  await flush();
});
check(
  repairWrites.length === 0
    && text(repairRaceRenderer.root.findByProps({ role: "dialog" })).includes("CONTROLLED APPLY")
    && text(repairRaceRenderer.root.findByProps({ role: "dialog" })).includes("Fresh authoritative scene twelve."),
  "a Billy repair proposal must refresh its request-time Scene snapshot before opening Controlled Apply",
);
await act(async () => {
  button(repairRaceRenderer, "✓ APPLY").props.onClick();
  await flush();
});
check(
  repairWrites.length === 1
    && repairWrites[0]?.projectId === 7
    && repairWrites[0]?.sceneId === 12
    && repairWrites[0]?.body.content === "Replacement prose for scene twelve."
    && repairWrites[0]?.body.expected_revision === "rev-12-fresh"
    && repairSceneReads >= 3,
  "Controlled Apply must write exactly the reply's captured Scene with an optimistic revision",
);
act(() => repairRaceRenderer.unmount());
if (previousWindow) Object.defineProperty(globalThis, "window", previousWindow);
else delete (globalThis as unknown as { window?: unknown }).window;

const planningBodies: Array<Record<string, unknown>> = [];
const planningApi = {
  listScenes: async () => assistantScenes.map((scene) => ({ ...scene })),
  assistantChat: async (_projectId: number, body: Record<string, unknown>) => {
    planningBodies.push(structuredClone(body));
    return { reply: "First choose the scene whose transition should change." };
  },
  subscribe: () => () => {},
} as unknown as ApiClient;
const planningTarget = {
  handoffId: "repair-plan-handoff-0001",
  ownerProjectId: 7,
  issueId: "fedcba9876543210",
  sceneId: null,
  draft: "Plan this repair before choosing a scene.",
};
const planningTree = (target: typeof planningTarget | null) => (
  <StudioProvider
    services={{ api: planningApi, platform }}
    projectId={7}
    nav={{ continuityRepairTarget: target, clearContinuityRepairTarget: () => {} }}
  >
    <SelectSceneForTest sceneId={12} />
    <AssistantDock />
  </StudioProvider>
);
let planningRenderer!: ReactTestRenderer;
await act(async () => {
  planningRenderer = create(planningTree(planningTarget));
  await flush();
  planningRenderer.update(planningTree(null));
  await flush();
});
await act(async () => {
  button(planningRenderer, "SET TEST SELECTION").props.onClick();
  await flush();
  button(planningRenderer, "SEND").props.onClick();
  await flush();
});
check(
  planningBodies.length === 1
    && !("active_scene_id" in planningBodies[0]!)
    && planningRenderer.root.findAllByType("button").every((candidate) => !["↧ REPLACE", "＋ APPEND"].includes(text(candidate))),
  "a planning-only repair must ignore unrelated selection and expose no prose-apply action",
);
act(() => planningRenderer.unmount());

console.log(`${assertions} Continuity Panel assertions passed.`);

for (const handle of process._getActiveHandles()) {
  if (handle instanceof MessagePort) handle.unref();
}
