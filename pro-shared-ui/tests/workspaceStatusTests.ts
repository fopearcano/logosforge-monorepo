/** Pure workspace-status reducer tests. */

import type { ProjectSaveStatusSnapshot } from "../src/adapters/projectSaveCoordinator";
import {
  deriveWorkspaceStatus,
  type WorkspaceStatusInput,
} from "../src/status/workspaceStatus";

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: boolean): void => {
  if (condition) passed += 1;
  else failures.push(label);
};

const cleanSave = (patch: Partial<ProjectSaveStatusSnapshot> = {}): ProjectSaveStatusSnapshot => ({
  dirtyRevision: 0,
  savedRevision: 0,
  dirty: false,
  inFlightCount: 0,
  flushing: false,
  lastSavedAt: null,
  lastError: null,
  ...patch,
});

const input = (patch: Partial<WorkspaceStatusInput> = {}): WorkspaceStatusInput => ({
  coreState: "connected",
  projectSave: cleanSave(),
  workspaceLayoutSaving: false,
  workspaceLayoutError: null,
  handoffPhase: "idle",
  storage: "local",
  ...patch,
});

const ready = deriveWorkspaceStatus(input());
check(
  "clean workspace reports local readiness without sync claims",
  ready.kind === "ready"
    && ready.copy === "LOCAL · READY"
    && ready.storage === "local"
    && ready.storageCopy === "LOCAL"
    && ready.tone === "neutral",
);

const saved = deriveWorkspaceStatus(input({
  projectSave: cleanSave({ lastSavedAt: 1234 }),
}));
check(
  "successful persistence reports saved locally",
  saved.kind === "saved" && saved.copy === "SAVED LOCALLY" && saved.lastSavedAt === 1234,
);

const saving = deriveWorkspaceStatus(input({
  projectSave: cleanSave({ dirtyRevision: 2, dirty: true, inFlightCount: 2 }),
}));
check(
  "multiple writes report an exact local in-flight count",
  saving.kind === "saving"
    && saving.copy === "SAVING LOCALLY · 2"
    && saving.inFlightCount === 2
    && saving.tone === "info",
);

const dirty = deriveWorkspaceStatus(input({
  projectSave: cleanSave({ dirtyRevision: 3, savedRevision: 2, dirty: true }),
}));
check("dirty state is explicit", dirty.kind === "dirty" && dirty.copy === "UNSAVED CHANGES" && dirty.tone === "warning");

const saveError = deriveWorkspaceStatus(input({
  projectSave: cleanSave({ dirtyRevision: 3, savedRevision: 2, dirty: true, lastError: new Error("disk full") }),
  coreState: "error",
  coreDetail: "core exited",
  workspaceLayoutError: new Error("layout failed"),
  handoffPhase: "closing",
}));
check(
  "save failure has highest priority and retains its reason",
  saveError.kind === "save-error"
    && saveError.priority === 100
    && saveError.tone === "danger"
    && saveError.detail.includes("disk full"),
);

const offlineDirty = deriveWorkspaceStatus(input({
  coreState: "error",
  coreDetail: "process exited",
  projectSave: cleanSave({ dirtyRevision: 1, dirty: true }),
}));
check(
  "core failure distinguishes pending local work",
  offlineDirty.kind === "core-error-unsaved"
    && offlineDirty.copy === "CORE UNAVAILABLE · UNSAVED"
    && offlineDirty.detail.includes("process exited"),
);

const layoutError = deriveWorkspaceStatus(input({ workspaceLayoutError: "permission denied" }));
check(
  "layout failure does not claim project-save failure",
  layoutError.kind === "layout-error"
    && layoutError.tone === "warning"
    && layoutError.detail.startsWith("Project data may be saved")
    && layoutError.detail.includes("permission denied"),
);

const closing = deriveWorkspaceStatus(input({
  handoffPhase: "closing",
  projectSave: cleanSave({ dirtyRevision: 1, dirty: true }),
}));
check("close handoff explains its save barrier", closing.kind === "closing" && closing.copy === "SAVING BEFORE CLOSE");

const switching = deriveWorkspaceStatus(input({ handoffPhase: "switching" }));
check("clean project handoff reports switching", switching.kind === "switching" && switching.copy === "SWITCHING PROJECT");

const connectingDirty = deriveWorkspaceStatus(input({
  coreState: "connecting",
  projectSave: cleanSave({ dirtyRevision: 1, dirty: true }),
}));
check(
  "connecting state does not hide unsaved changes",
  connectingDirty.kind === "connecting-unsaved" && connectingDirty.copy === "UNSAVED · CONNECTING",
);

const layoutSaving = deriveWorkspaceStatus(input({ workspaceLayoutSaving: true }));
check("layout persistence is named separately", layoutSaving.kind === "layout-saving" && layoutSaving.copy === "SAVING WORKSPACE");

for (const model of [ready, saved, saving, dirty, saveError, offlineDirty, layoutError, closing, switching, connectingDirty, layoutSaving]) {
  const claims = `${model.copy} ${model.detail} ${model.storageCopy}`;
  check(`status ${model.kind} makes no cloud/sync claim`, !/cloud|synced|syncing/i.test(claims));
}

check(
  "priority orders failures, handoffs, active saves, and settled state",
  saveError.priority > offlineDirty.priority
    && offlineDirty.priority > layoutError.priority
    && layoutError.priority > closing.priority
    && closing.priority > saving.priority
    && saving.priority > saved.priority,
);

console.log(`Workspace status tests: ${passed} passed, ${failures.length} failed`);
for (const item of failures) console.error(`  FAIL: ${item}`);
if (failures.length) throw new Error(`${failures.length} workspace-status test(s) failed`);
console.log("WORKSPACE STATUS TESTS: PASS");
