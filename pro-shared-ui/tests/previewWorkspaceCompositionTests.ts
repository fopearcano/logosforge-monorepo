import fs from "node:fs";
import path from "node:path";
import type { ProjectDTO } from "@logosforge/ui-contracts";
import type { PlatformAdapter } from "../src/adapters/platform";
import { resetWorkspaceLayout, setWorkspacePreset } from "../src/workspace/layoutModel";
import {
  createPreviewLayoutPlatform,
  drainPreviewIdentityOperations,
  previewProjectNeedsReconciliation,
  previewUnloadNeedsConfirmation,
  previewWorkspaceStorageKey,
  selectPreviewBootstrapProject,
  type PreviewStorage,
} from "../preview/integratedWorkspaceRuntime";

const previewRoot = path.join(process.cwd(), "preview");
const readPreview = (relative: string) => fs.readFileSync(path.join(previewRoot, relative), "utf8");
const failures: string[] = [];

const requireMarkers = (file: string, markers: readonly string[]): string => {
  const source = readPreview(file);
  for (const marker of markers) {
    if (!source.includes(marker)) failures.push(`${file} is missing ${marker}`);
  }
  return source;
};

const integrated = requireMarkers("IntegratedWorkspaceHarness.tsx", [
  'data-screen-label="Workspace Shell — Integrated"',
  "STUDIO_AI_COMPANIONS_PANEL_ID",
  "STUDIO_PANELS",
  "STUDIO_WORKSPACE_PANEL_IDS",
  "studioPanelGroupsForMode(mode)",
  "findStudioPanel(panelId)",
  "{panel.node}",
  "<WorkspaceShell",
  "<DockWorkspace",
  "<PanelErrorBoundary",
  "<AssistantDock",
  "useWorkspaceLayout({",
  "allowedPanelIds: STUDIO_WORKSPACE_PANEL_IDS",
  "export function IntegratedWorkspaceHarness({",
  "externalTransitioning,",
  "registerIdentityGuard,",
  "createPreviewLayoutPlatform(upstream.platform, source)",
  "(WRITING_MODES as readonly string[]).includes(candidate)",
  "bootstrappedRef.current",
  "selectProjectRef.current",
  "refreshOperations.current.add(running)",
  "drainPreviewIdentityOperations(",
  "if (error && !projectReady) void refreshProjects()",
]);

for (const marker of [
  "StudioOmnibox",
  "createCommandRegistry",
  "parseRecentProjectIds",
  "rememberRecentProject",
  "localStorage.getItem",
  "localStorage.setItem",
  "omniboxOpen",
  "setOmniboxOpen(true)",
  "const omniboxAvailable = projectReady && hydrated && !projectSwitching && !externalTransitioning",
  "onCommandPalette={omniboxAvailable ? requestOpenOmnibox : undefined}",
  "<StudioOmnibox",
  "open={omniboxOpen}",
  "projects={projects}",
  "recentProjectIds={recentProjectIds}",
  "onNavigate={selectPanel}",
  "onSelectProject={selectProject}",
  "type StudioNavigationOptions,",
  "const [pendingNote, setPendingNote] = useState<number | null>(null)",
  "const [pendingComment, setPendingComment] = useState<number | null>(null)",
  'setPendingScene(panelId === "manuscript" ? options?.sceneId ?? null : null)',
  'setPendingPsykeEntry(panelId === "psyke" ? options?.psykeEntryId ?? null : null)',
  'setPendingNote(panelId === "notes" ? options?.noteId ?? null : null)',
  'setPendingComment(panelId === "comments" ? options?.commentId ?? null : null)',
  'setPendingKnowledgeGraph(panelId === "graph" && options?.graphFocusKey ? {',
  'setPendingContinuityIssue(panelId === "continuity" ? options?.continuityIssueKey ?? null : null)',
  'setPendingContinuityRepair(panelId === STUDIO_AI_COMPANIONS_PANEL_ID ? options?.continuityRepair ?? null : null)',
  "setPendingNote(null)",
  "setPendingComment(null)",
  "const toggleFocus = useCallback((): Promise<boolean> => {",
  "const returnPanelId = layoutRef.current.focused?.panelId ?? \"manuscript\"",
  ": panelFocusTarget(returnPanelId)",
  "onToggleFocus={() => { void toggleFocus(); }}",
  "noteTargetId: pendingNote",
  "clearNoteTarget: (noteId) => setPendingNote",
  "commentTargetId: pendingComment",
  "clearCommentTarget: (commentId) => setPendingComment",
]) {
  if (!integrated.includes(marker)) failures.push(`Integrated browser omnibox is missing ${marker}`);
}
const shortcutOffset = integrated.indexOf("const openOmnibox");
const shortcutSource = shortcutOffset < 0 ? "" : integrated.slice(shortcutOffset, shortcutOffset + 1_500);
for (const marker of [
  "event.metaKey",
  "event.ctrlKey",
  "event.key.toLowerCase()",
  '"k"',
  "event.repeat",
  "event.preventDefault()",
  "setOmniboxOpen(true)",
  'window.addEventListener("keydown", openOmnibox)',
  'window.removeEventListener("keydown", openOmnibox)',
]) {
  if (!shortcutSource.includes(marker)) failures.push(`Integrated browser omnibox shortcut is missing ${marker}`);
}
const registryOffset = integrated.lastIndexOf("createCommandRegistry([");
const registrySource = registryOffset < 0 ? "" : integrated.slice(registryOffset, registryOffset + 6_000);
for (const marker of ["toggleWorkspacePreset", "resetWorkspaceLayout", "...SKIN_OPTIONS.map", "setSkin(skinOption.id)", 'category: "Skins"']) {
  if (!registrySource.includes(marker)) failures.push(`Integrated browser omnibox registry is missing ${marker}`);
}

for (const forbidden of [
  "PreviewPanel",
  "WorkspaceDockHarness",
  "WORKSPACE QA",
  "State-preservation test draft",
  "Type here, then move this tab",
  "Live dock preview for resize",
  "DOCK QA",
  "SYNTHETIC DESIGN FIXTURE",
  "SYNTHETIC DOCK QA FIXTURE",
]) {
  if (integrated.includes(forbidden)) {
    failures.push(`IntegratedWorkspaceHarness contains synthetic fixture marker: ${forbidden}`);
  }
}

const app = requireMarkers("App.tsx", [
  'useState("Workspace Shell — Integrated")',
  '["Workspace Shell — Integrated", ({ source, identitySwitching, registerIdentityGuard }) => (',
  '["Workspace Shell — Design Fixture", <WorkspaceShellDesignFixture />',
  'data-preview-fixture="workspace-shell-design"',
  "SYNTHETIC DESIGN FIXTURE",
  "identityGuardRef.current?.()",
  "await flushPendingProjectSaves({ commitActiveField: true })",
  'key={`${source}:${projectId}`}',
]);
const appFunctionOffset = app.indexOf("export function App()");
for (const marker of [
  "const mockApi = createMockApiClient()",
  "const liveApi = createHttpApiClient()",
]) {
  const offset = app.indexOf(marker);
  if (offset < 0 || offset > appFunctionOffset) {
    failures.push(`App must create each preview API identity once at module scope: ${marker}`);
  }
}
if ((app.match(/createMockApiClient\(\)/g) ?? []).length !== 1) {
  failures.push("App must own exactly one stable mock ApiClient identity");
}
if ((app.match(/createHttpApiClient\(\)/g) ?? []).length !== 1) {
  failures.push("App must own exactly one stable live ApiClient identity");
}

const fixture = requireMarkers("WorkspaceDockHarness.tsx", [
  'data-preview-fixture="workspace-dock-qa"',
  "SYNTHETIC DOCK QA FIXTURE",
  "function PreviewPanel",
  'aria-label="State-preservation test draft"',
  "DOCK QA",
]);
if (fixture.includes('data-screen-label="Workspace Shell — Integrated"')) {
  failures.push("Synthetic dock fixture impersonates the integrated workspace screen label");
}

requireMarkers("main.tsx", [
  'query.has("workspace-dock-harness")',
  "<WorkspaceDockHarness />",
]);

requireMarkers("integratedWorkspaceRuntime.ts", [
  "createPreviewLayoutPlatform",
  "previewWorkspaceStorageKey",
  "drainPreviewIdentityOperations",
  "selectPreviewBootstrapProject",
  "previewProjectNeedsReconciliation",
  "previewUnloadNeedsConfirmation",
]);

requireMarkers("IntegratedWorkspaceHarness.tsx", [
  'window.addEventListener("beforeunload", confirmPendingSaves)',
  'window.removeEventListener("beforeunload", confirmPendingSaves)',
  'event.returnValue = ""',
]);

let behaviorChecks = 0;
const behaviorCheck = (condition: unknown, message: string): void => {
  if (!condition) failures.push(`behavior: ${message}`);
  else behaviorChecks += 1;
};

class MemoryStorage implements PreviewStorage {
  readonly values = new Map<string, string>();
  failOnceFor: string | null = null;

  getItem(key: string): string | null { return this.values.get(key) ?? null; }
  setItem(key: string, value: string): void {
    if (this.failOnceFor === key) {
      this.failOnceFor = null;
      throw new Error("simulated storage failure");
    }
    this.values.set(key, value);
  }
  removeItem(key: string): void { this.values.delete(key); }
}

const hostPlatform: PlatformAdapter = {
  isDesktop: false,
  openFile: async () => ({ canceled: true }),
  saveFile: async () => ({ canceled: true }),
  openExternal: async () => undefined,
};
const storage = new MemoryStorage();
const mockLayoutPlatform = createPreviewLayoutPlatform(hostPlatform, "mock", storage);
const liveLayoutPlatform = createPreviewLayoutPlatform(hostPlatform, "live", storage);
const firstLayout = setWorkspacePreset(resetWorkspaceLayout(["manuscript"]), "focus");
const secondLayout = resetWorkspaceLayout(["manuscript"]);
await mockLayoutPlatform.saveLayout!(1, firstLayout);
await liveLayoutPlatform.saveLayout!(1, secondLayout);
behaviorCheck(
  await mockLayoutPlatform.loadLayout!(1) !== await liveLayoutPlatform.loadLayout!(1),
  "workspace layouts must stay isolated by preview source",
);
await mockLayoutPlatform.saveLayout!(2, secondLayout);
behaviorCheck(
  await mockLayoutPlatform.loadLayout!(1) !== await mockLayoutPlatform.loadLayout!(2),
  "workspace layouts must stay isolated by project",
);
await mockLayoutPlatform.saveLayout!(1, secondLayout);
behaviorCheck(
  await mockLayoutPlatform.loadLayoutBackup!(1) === JSON.stringify(firstLayout),
  "a successful replacement must rotate the prior primary into backup",
);

const currentKey = previewWorkspaceStorageKey("mock", 1);
const backupKey = previewWorkspaceStorageKey("mock", 1, true);
storage.setItem(backupKey, "known-good-backup");
const currentBeforeFailure = storage.getItem(currentKey);
storage.failOnceFor = currentKey;
let storageFailure: unknown = null;
try {
  await mockLayoutPlatform.saveLayout!(1, firstLayout);
} catch (error) {
  storageFailure = error;
}
behaviorCheck(storageFailure instanceof Error, "storage failures must be observable to the layout hook");
behaviorCheck(storage.getItem(currentKey) === currentBeforeFailure, "failed saves must preserve the prior primary");
behaviorCheck(storage.getItem(backupKey) === "known-good-backup", "failed saves must roll backup rotation back");

interface Deferred<T> { promise: Promise<T>; resolve(value: T): void }
const deferred = <T>(): Deferred<T> => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => { resolve = resolvePromise; });
  return { promise, resolve };
};
const refresh = deferred<void>();
const lateQueue = deferred<void>();
const refreshOperations = new Set<Promise<unknown>>([refresh.promise]);
const operationQueue = { current: Promise.resolve() };
refresh.promise.then(() => {
  refreshOperations.delete(refresh.promise);
  operationQueue.current = lateQueue.promise;
});
let flushes = 0;
let drained = false;
const draining = drainPreviewIdentityOperations(refreshOperations, operationQueue, async () => { flushes += 1; })
  .then(() => { drained = true; });
await Promise.resolve();
behaviorCheck(!drained, "identity drain must wait for an in-flight project refresh");
refresh.resolve();
await Promise.resolve();
await Promise.resolve();
behaviorCheck(!drained, "identity drain must notice a handoff enqueued by refresh completion");
lateQueue.resolve();
await draining;
behaviorCheck(drained && flushes >= 2, "identity drain must reach a stable queue before returning");

let rejectedFlush: unknown = null;
try {
  await drainPreviewIdentityOperations(new Set(), { current: Promise.resolve() }, async () => {
    throw new Error("unsaved editor");
  });
} catch (error) {
  rejectedFlush = error;
}
behaviorCheck(rejectedFlush instanceof Error, "a failed save barrier must reject the identity transition");

const projectFixtures: ProjectDTO[] = [
  { id: 4, title: "Four", description: "", narrative_engine: "novel", default_writing_format: "novel", format_mode: "novel" },
  { id: 7, title: "Seven", description: "", narrative_engine: "screenplay", default_writing_format: "screenplay", format_mode: "screenplay" },
];
behaviorCheck(selectPreviewBootstrapProject(projectFixtures, 7) === 7, "bootstrap must honor an available preferred project");
behaviorCheck(selectPreviewBootstrapProject(projectFixtures, 99) === 4, "bootstrap must fall back to the first authoritative project");
behaviorCheck(previewProjectNeedsReconciliation(projectFixtures, 99), "refresh must detect a vanished active project");
behaviorCheck(!previewProjectNeedsReconciliation(projectFixtures, 7), "refresh must preserve a still-present active project");
const cleanUnloadState = {
  projectDirty: false,
  projectWritesInFlight: 0,
  projectFlushInProgress: false,
  layoutSaving: false,
  layoutError: null,
  identityTransitioning: false,
};
behaviorCheck(!previewUnloadNeedsConfirmation(cleanUnloadState), "a fully saved workspace must not trigger an unload warning");
behaviorCheck(previewUnloadNeedsConfirmation({ ...cleanUnloadState, projectDirty: true }), "dirty editor state must trigger an unload warning");
behaviorCheck(previewUnloadNeedsConfirmation({ ...cleanUnloadState, projectWritesInFlight: 1 }), "in-flight writes must trigger an unload warning");
behaviorCheck(previewUnloadNeedsConfirmation({ ...cleanUnloadState, layoutSaving: true }), "an in-flight layout save must trigger an unload warning");
behaviorCheck(previewUnloadNeedsConfirmation({ ...cleanUnloadState, layoutError: new Error("quota") }), "a failed layout save must trigger an unload warning");
behaviorCheck(previewUnloadNeedsConfirmation({ ...cleanUnloadState, identityTransitioning: true }), "an identity handoff must trigger an unload warning");

console.log(`Integrated preview composition + runtime checks · ${behaviorChecks} behavioral assertions`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} integrated preview composition violation(s)`);
console.log("INTEGRATED PREVIEW COMPOSITION TESTS: PASS");
