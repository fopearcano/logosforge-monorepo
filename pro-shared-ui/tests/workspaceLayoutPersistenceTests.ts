import type { PlatformAdapter } from "../src/adapters/platform";
import {
  resizeNavigator,
  setNavigatorCollapsed,
  setWorkspacePreset,
  resetWorkspaceLayout,
  type WorkspaceLayout,
} from "../src/workspace/layoutModel";
import {
  useWorkspaceLayout,
  type UseWorkspaceLayoutOptions,
  type WorkspaceLayoutState,
} from "../src/workspace/useWorkspaceLayout";
import {
  beginHookRender,
  discardHookEffects,
  flushHookEffects,
  resetHookRuntime,
} from "./fakeReactHookRuntime";

const PANEL_IDS = [
  "manuscript",
  "dashboard",
  "ai-companions",
  "decision-radar",
  "outline",
  "health",
] as const;

let passed = 0;
const failures: string[] = [];

function check(label: string, condition: boolean): void {
  if (condition) passed += 1;
  else failures.push(label);
}

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason: unknown) => void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

async function settle(rounds = 8): Promise<void> {
  for (let index = 0; index < rounds; index += 1) await Promise.resolve();
}

function platform(overrides: Partial<PlatformAdapter>): PlatformAdapter {
  return {
    isDesktop: true,
    openFile: async () => ({ canceled: true }),
    saveFile: async () => ({ canceled: true }),
    openExternal: async () => undefined,
    ...overrides,
  };
}

function render(options: UseWorkspaceLayoutOptions): WorkspaceLayoutState {
  beginHookRender();
  return useWorkspaceLayout(options);
}

async function hydrate(options: UseWorkspaceLayoutOptions): Promise<WorkspaceLayoutState> {
  render(options);
  flushHookEffects();
  await settle();
  const state = render(options);
  flushHookEffects();
  return state;
}

// A concrete project cannot mutate before its own load has resolved. Switching
// projects also synchronously projects a safe fallback, before passive effects.
{
  resetHookRuntime();
  const firstLoad = deferred<unknown | null>();
  const secondLoad = deferred<unknown | null>();
  const adapter = platform({
    loadLayout: (projectId) => projectId === 1 ? firstLoad.promise : secondLoad.promise,
    saveLayout: async () => undefined,
  });
  let options: UseWorkspaceLayoutOptions = {
    projectId: 1,
    platform: adapter,
    allowedPanelIds: PANEL_IDS,
    debounceMs: 60_000,
  };
  const initial = render(options);
  let updaterCalled = false;
  initial.updateLayout((layout) => {
    updaterCalled = true;
    return setWorkspacePreset(layout, "focus");
  });
  check("unhydrated project rejects mutation before invoking updater", !updaterCalled);
  flushHookEffects();
  await settle();

  options = { ...options, projectId: 2 };
  const switched = render(options);
  check("project switch synchronously hides the previous layout", switched.layout.preset === "cockpit");
  check("project switch reports loading before its effect", switched.loading && !switched.hydrated);
  updaterCalled = false;
  switched.updateLayout((layout) => {
    updaterCalled = true;
    return setWorkspacePreset(layout, "focus");
  });
  check("new project rejects mutation before hydration", !updaterCalled);
  flushHookEffects();
  await settle();

  const projectTwo = resizeNavigator(resetWorkspaceLayout(PANEL_IDS), 333);
  const staleProjectOne = resizeNavigator(resetWorkspaceLayout(PANEL_IDS), 444);
  secondLoad.resolve(projectTwo);
  firstLoad.resolve(staleProjectOne);
  await settle();
  const hydrated = render(options);
  check("stale load cannot replace the current project layout", hydrated.layout.navigator.widthPx === 333);
  check("current project hydrates after its own load", hydrated.hydrated && !hydrated.loading);
  resetHookRuntime();
}

// A load failure belongs to the current generation even though that generation
// is intentionally unhydrated. It must remain visible for the retry UI, while a
// subsequent project render must hide it synchronously.
{
  resetHookRuntime();
  let options: UseWorkspaceLayoutOptions = {
    projectId: 6,
    platform: platform({
      loadLayout: async (projectId) => {
        if (projectId === 6) throw new Error("layout read failed");
        return null;
      },
      saveLayout: async () => undefined,
    }),
    allowedPanelIds: PANEL_IDS,
    debounceMs: 60_000,
  };
  const failed = await hydrate(options);
  check(
    "current-project load failure is visible while unhydrated",
    !failed.hydrated && failed.loading && failed.error?.message === "layout read failed",
  );
  options = { ...options, projectId: 7 };
  const switched = render(options);
  check("stale project load error is hidden synchronously", switched.error === null);
  flushHookEffects();
  await settle();
  resetHookRuntime();
}

// Referentially new but semantically identical platform/catalog configuration
// must not restart hydration or clear pending state.
{
  resetHookRuntime();
  let loads = 0;
  const loadedLayout = setWorkspacePreset(resetWorkspaceLayout(PANEL_IDS), "focus");
  const loadLayout = async () => {
    loads += 1;
    return loadedLayout;
  };
  let options: UseWorkspaceLayoutOptions = {
    projectId: 7,
    platform: platform({ loadLayout, saveLayout: async () => undefined }),
    allowedPanelIds: [...PANEL_IDS],
    debounceMs: 60_000,
  };
  await hydrate(options);
  options = {
    ...options,
    platform: platform({ loadLayout, saveLayout: async () => undefined }),
    allowedPanelIds: [...PANEL_IDS].reverse(),
  };
  render(options);
  flushHookEffects();
  await settle();
  check("stable configuration fingerprint avoids duplicate load", loads === 1);

  const replacementLoad = async () => {
    loads += 1;
    return null;
  };
  options = {
    ...options,
    platform: platform({ loadLayout: replacementLoad, saveLayout: async () => undefined }),
  };
  const changedCapability = render(options);
  check("changed load capability invalidates the prior hydration synchronously", changedCapability.loading);
  check("changed load capability projects a safe fallback before its effect", changedCapability.layout.preset === "cockpit");
  flushHookEffects();
  await settle();
  check("changed load capability rehydrates the same project", loads === 2 && render(options).hydrated);
  resetHookRuntime();
}

// A concurrent render that never commits may not invalidate the ownership refs
// used by the still-visible project's handlers and asynchronous completions.
{
  resetHookRuntime();
  const adapter = platform({
    loadLayout: async (projectId) => resizeNavigator(resetWorkspaceLayout(PANEL_IDS), 300 + projectId),
    saveLayout: async () => undefined,
  });
  let options: UseWorkspaceLayoutOptions = {
    projectId: 8,
    platform: adapter,
    allowedPanelIds: PANEL_IDS,
    debounceMs: 60_000,
  };
  await hydrate(options);

  const abandonedOptions = { ...options, projectId: 9 };
  const abandoned = render(abandonedOptions);
  check("uncommitted project render projects a safe fallback", abandoned.loading && !abandoned.hydrated);
  discardHookEffects();

  const resumed = render(options);
  check("abandoned render leaves committed project hydrated", resumed.hydrated && !resumed.loading);
  resumed.updateLayout((layout) => setNavigatorCollapsed(layout, true));
  check("abandoned render leaves committed project mutable", render(options).layout.navigator.collapsed);
  flushHookEffects();
  await settle();
  resetHookRuntime();
}

// Concurrent callers share one drain. An edit arriving during the first write
// is serialized into exactly one subsequent write by that same drain.
{
  resetHookRuntime();
  const writes: Array<Deferred<void>> = [];
  const snapshots: WorkspaceLayout[] = [];
  const adapter = platform({
    loadLayout: async () => null,
    saveLayout: async (_projectId, value) => {
      snapshots.push(value as WorkspaceLayout);
      const write = deferred<void>();
      writes.push(write);
      return write.promise;
    },
  });
  const options: UseWorkspaceLayoutOptions = {
    projectId: 3,
    platform: adapter,
    allowedPanelIds: PANEL_IDS,
    debounceMs: 60_000,
  };
  const state = await hydrate(options);
  state.updateLayout((layout) => setWorkspacePreset(layout, "focus"));
  const firstFlush = state.flushLayout();
  const secondFlush = state.flushLayout();
  check("concurrent flush callers receive the same promise", firstFlush === secondFlush);
  await settle();
  check("single-flight drain starts one write", writes.length === 1);

  state.updateLayout((layout) => setNavigatorCollapsed(layout, true));
  writes[0]?.resolve(undefined);
  await settle();
  check("edit during save produces one serialized follow-up", writes.length === 2);
  check(
    "follow-up snapshot contains the latest edit",
    snapshots[1]?.preset === "focus" && snapshots[1]?.navigator.collapsed === true,
  );
  writes[1]?.resolve(undefined);
  const [firstResult, secondResult] = await Promise.all([firstFlush, secondFlush]);
  check("shared drain succeeds for every caller", firstResult && secondResult && writes.length === 2);
  const saved = render(options);
  check("successful drain clears saving and error", !saved.saving && saved.error === null);
  resetHookRuntime();
}

// A failed current-owner save remains dirty and retryable.
{
  resetHookRuntime();
  let attempts = 0;
  let fail = true;
  const options: UseWorkspaceLayoutOptions = {
    projectId: 4,
    platform: platform({
      loadLayout: async () => null,
      saveLayout: async () => {
        attempts += 1;
        if (fail) throw new Error("disk unavailable");
      },
    }),
    allowedPanelIds: PANEL_IDS,
    debounceMs: 60_000,
  };
  const state = await hydrate(options);
  state.updateLayout((layout) => setWorkspacePreset(layout, "focus"));
  const failed = await state.flushLayout();
  let current = render(options);
  check("failed save reports failure and preserves its error", !failed && current.error?.message === "disk unavailable");
  fail = false;
  const retried = await current.retryLayoutPersistence();
  current = render(options);
  check("failed save retains dirty state for retry", retried && attempts === 2);
  check("successful retry clears the prior error", current.error === null);
  resetHookRuntime();
}

// Even a caller that changes project ownership without the app-level handoff
// barrier cannot let a stale save completion clear the new project's edit.
{
  resetHookRuntime();
  const writes: Array<{ projectId: number; gate: Deferred<void>; layout: WorkspaceLayout }> = [];
  const adapter = platform({
    loadLayout: async () => null,
    saveLayout: async (projectId, value) => {
      const gate = deferred<void>();
      writes.push({ projectId, gate, layout: value as WorkspaceLayout });
      return gate.promise;
    },
  });
  let options: UseWorkspaceLayoutOptions = {
    projectId: 12,
    platform: adapter,
    allowedPanelIds: PANEL_IDS,
    debounceMs: 60_000,
  };
  let state = await hydrate(options);
  state.updateLayout((layout) => setWorkspacePreset(layout, "focus"));
  const draining = state.flushLayout();
  await settle();
  check("old project save begins before ownership change", writes[0]?.projectId === 12);

  options = { ...options, projectId: 13 };
  render(options);
  flushHookEffects();
  await settle();
  state = render(options);
  flushHookEffects();
  state.updateLayout((layout) => setNavigatorCollapsed(layout, true));
  const sharedDrain = state.flushLayout();
  check("new owner joins the in-flight drain", draining === sharedDrain);

  writes[0]?.gate.resolve(undefined);
  await settle();
  check("stale completion drains the new owner next", writes[1]?.projectId === 13);
  check("new owner snapshot retains its edit", writes[1]?.layout.navigator.collapsed === true);
  writes[1]?.gate.resolve(undefined);
  check("cross-owner drain completes successfully", await draining);
  resetHookRuntime();
}

// Unsupported/invalid stored data can be displayed through a safe fallback but
// is never automatically overwritten as if it were a known migration.
{
  resetHookRuntime();
  let saves = 0;
  let backupLoads = 0;
  const options: UseWorkspaceLayoutOptions = {
    projectId: 5,
    platform: platform({
      loadLayout: async () => ({
        schema: "logosforge.pro.workspace-layout",
        version: 999,
        future: true,
      }),
      loadLayoutBackup: async () => {
        backupLoads += 1;
        return setWorkspacePreset(resetWorkspaceLayout(PANEL_IDS), "focus");
      },
      saveLayout: async () => { saves += 1; },
    }),
    allowedPanelIds: PANEL_IDS,
    debounceMs: 60_000,
  };
  const state = await hydrate(options);
  check("future layout restores a safe hydrated fallback", state.hydrated && state.layout.preset === "cockpit");
  const flushed = await state.flushLayout();
  check("future layout is not auto-rewritten", flushed && saves === 0);
  check("future layout does not fall back to an older backup", backupLoads === 0);
  resetHookRuntime();
}

// A malformed current generation can recover through a separately loaded,
// shared-UI-validated backup. Its repair save must preserve that known-good
// backup until the replacement primary is safely installed.
{
  resetHookRuntime();
  let backupLoads = 0;
  const saveOptions: Array<{ preserveBackup?: boolean } | undefined> = [];
  const recoveredLayout = setWorkspacePreset(
    resizeNavigator(resetWorkspaceLayout(PANEL_IDS), 377),
    "focus",
  );
  const options: UseWorkspaceLayoutOptions = {
    projectId: 10,
    platform: platform({
      loadLayout: async () => ({
        schema: "logosforge.pro.workspace-layout",
        version: 1,
        preset: "cockpit",
      }),
      loadLayoutBackup: async () => {
        backupLoads += 1;
        return recoveredLayout;
      },
      saveLayout: async (_projectId, _layout, options) => {
        saveOptions.push(options);
      },
    }),
    allowedPanelIds: PANEL_IDS,
    debounceMs: 60_000,
  };
  let state = await hydrate(options);
  check(
    "invalid primary restores the validated backup",
    state.layout.preset === "focus" && state.layout.navigator.widthPx === 377 && backupLoads === 1,
  );
  check("successful backup recovery does not surface a load error", state.error === null);
  const repaired = await state.flushLayout();
  state = render(options);
  check("recovered layout is repaired into the primary", repaired && saveOptions.length === 1);
  check("recovery repair preserves the validated backup", saveOptions[0]?.preserveBackup === true);
  check("recovery repair clears dirty state", !state.saving && state.error === null);
  resetHookRuntime();
}

// When no valid backup exists, defaults remain usable but the corruption is
// visible. A deliberate subsequent edit may repair the primary without rotating
// that malformed generation over any host-side recovery file.
{
  resetHookRuntime();
  const saveOptions: Array<{ preserveBackup?: boolean } | undefined> = [];
  const options: UseWorkspaceLayoutOptions = {
    projectId: 11,
    platform: platform({
      loadLayout: async () => ({
        schema: "logosforge.pro.workspace-layout",
        version: 1,
        preset: "broken",
      }),
      loadLayoutBackup: async () => null,
      saveLayout: async (_projectId, _layout, options) => { saveOptions.push(options); },
    }),
    allowedPanelIds: PANEL_IDS,
    debounceMs: 60_000,
  };
  let state = await hydrate(options);
  check("invalid primary without backup surfaces a recovery error", state.hydrated && state.error !== null);
  state.updateLayout((layout) => setWorkspacePreset(layout, "focus"));
  const repaired = await state.flushLayout();
  state = render(options);
  check("deliberate edit can repair an invalid primary", repaired && saveOptions.length === 1 && state.error === null);
  check("invalid-primary repair preserves any host backup", saveOptions[0]?.preserveBackup === true);
  resetHookRuntime();
}

console.log(`Workspace layout persistence tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} workspace layout persistence test(s) failed`);
console.log("WORKSPACE LAYOUT PERSISTENCE TESTS: PASS");
