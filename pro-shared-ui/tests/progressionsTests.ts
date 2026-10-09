import { readFileSync } from "node:fs";
import { join } from "node:path";
import { MessagePort } from "node:worker_threads";
import { createElement } from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import type {
  ProgressionCommandDTO,
  ProgressionCommandReceiptDTO,
  ProgressionCommandResultDTO,
  ProgressionSnapshotDTO,
} from "@logosforge/ui-contracts";
import { createHttpApiClient } from "../src/adapters/httpApiClient";
import { ApiRequestError } from "../src/adapters/httpApiClient";
import type { ApiClient } from "../src/adapters/api";
import type { PlatformAdapter } from "../src/adapters/platform";
import { StudioProvider } from "../src/adapters/StudioProvider";
import { ProgressionsPanel, resolveProgressionNavigationTarget } from "../src/components/bible/ProgressionsPanel";
import { PanelHostProvider } from "../src/components/common/PanelHost";
import {
  ProgressionCommandCoordinator,
  resetProgressionCommandMemoryForTests,
  type ProgressionCommandStorage,
} from "../src/adapters/progressionCommandCoordinator";
import {
  RuntimeDtoValidationError,
  validateProgressionCommandReceiptDTOForRequest,
  validateProgressionCommandResultDTOForRequest,
  validateProgressionSnapshotDTOForProject,
} from "../src/adapters/runtimeDtoValidation";

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: boolean): void => {
  if (condition) passed += 1;
  else failures.push(label);
};
const rejects = (label: string, run: () => unknown): void => {
  try { run(); failures.push(label); }
  catch (error) { check(label, error instanceof RuntimeDtoValidationError); }
};

const revisionA = "a".repeat(64);
const revisionB = "b".repeat(64);
const revisionC = "c".repeat(64);
const snapshot = (overrides: Partial<ProgressionSnapshotDTO> = {}): ProgressionSnapshotDTO => ({
  project_id: 7,
  revision: revisionB,
  tracks: [{
    id: 11,
    project_id: 7,
    kind: "character",
    title: "Mara trusts the signal",
    description: "A character arc.",
    color_label: "cyan",
    sort_order: 0,
    legacy_compatibility: false,
    primary_psyke_entry_id: 41,
    primary_psyke_entry_name: "Mara",
    primary_psyke_entry_type: "character",
    secondary_psyke_entry_id: null,
    secondary_psyke_entry_name: "",
    secondary_psyke_entry_type: "",
    beats: [{
      id: 21,
      track_id: 11,
      text: "She answers.",
      sort_order: 0,
      anchor_kind: "scene",
      scene_id: 3,
      scene_title: "The Reply",
      anchor_ref: null,
      anchor_label: "",
    }],
    coverage: {
      total_beats: 1,
      anchored_beats: 1,
      unanchored_beats: 0,
      scene_anchored_beats: 1,
      document_anchored_beats: 0,
      coverage_percent: 100,
      status: "complete",
      out_of_order_beat_ids: [],
    },
  }],
  summary: {
    total_tracks: 1,
    total_beats: 1,
    anchored_beats: 1,
    unanchored_beats: 0,
    coverage_percent: 100,
    by_kind: { story: 0, character: 1, relationship: 0, theme: 0, world: 0, custom: 0 },
    by_status: { empty: 0, unanchored: 0, partial: 0, complete: 1 },
  },
  ...overrides,
});

const command: ProgressionCommandDTO = {
  kind: "create_beat",
  expected_revision: revisionA,
  track_id: 11,
  text: "She answers.",
  anchor_kind: "scene",
  scene_id: 3,
  anchor_ref: null,
  anchor_label: "",
};
const result: ProgressionCommandResultDTO = {
  progressions: snapshot(),
  changed: true,
  affected_track_ids: [11],
  affected_beat_ids: [21],
  created_track_id: null,
  created_beat_id: 21,
  replayed: false,
  applied_revision: revisionB,
};

check(
  "valid Progressions snapshot passes strict runtime validation",
  validateProgressionSnapshotDTOForProject(structuredClone(snapshot()), 7).tracks[0]?.beats[0]?.id === 21,
);
check(
  "Progressions deep links resolve an exact track",
  resolveProgressionNavigationTarget(snapshot().tracks, { trackId: 11, beatId: null })?.track.id === 11,
);
check(
  "Progressions deep links resolve a beat through its canonical owner",
  resolveProgressionNavigationTarget(snapshot().tracks, { trackId: null, beatId: 21 })?.beat?.id === 21,
);
check(
  "Progressions deep links fail closed when track and beat identities disagree",
  resolveProgressionNavigationTarget(snapshot().tracks, { trackId: 11, beatId: 999 }) === null,
);
check(
  "migrated custom compatibility track with one nonstandard subject passes validation",
  (() => {
    const compatibility = structuredClone(snapshot());
    compatibility.tracks[0]!.kind = "custom";
    compatibility.tracks[0]!.legacy_compatibility = true;
    compatibility.tracks[0]!.primary_psyke_entry_type = "artifact";
    compatibility.summary.by_kind.character = 0;
    compatibility.summary.by_kind.custom = 1;
    return validateProgressionSnapshotDTOForProject(compatibility, 7).tracks[0]?.kind === "custom";
  })(),
);
check(
  "legacy custom compatibility subject with a Core-valid blank name and type passes validation",
  (() => {
    const compatibility = structuredClone(snapshot());
    compatibility.tracks[0]!.kind = "custom";
    compatibility.tracks[0]!.legacy_compatibility = true;
    compatibility.tracks[0]!.primary_psyke_entry_name = "";
    compatibility.tracks[0]!.primary_psyke_entry_type = "";
    compatibility.summary.by_kind.character = 0;
    compatibility.summary.by_kind.custom = 1;
    return validateProgressionSnapshotDTOForProject(compatibility, 7)
      .tracks[0]?.primary_psyke_entry_id === 41;
  })(),
);
check(
  "relationship subjects with Core-valid blank names and types pass validation",
  (() => {
    const relationship = structuredClone(snapshot());
    relationship.tracks[0]!.kind = "relationship";
    relationship.tracks[0]!.primary_psyke_entry_name = "";
    relationship.tracks[0]!.primary_psyke_entry_type = "";
    relationship.tracks[0]!.secondary_psyke_entry_id = 42;
    relationship.tracks[0]!.secondary_psyke_entry_name = "";
    relationship.tracks[0]!.secondary_psyke_entry_type = "";
    relationship.summary.by_kind.character = 0;
    relationship.summary.by_kind.relationship = 1;
    return validateProgressionSnapshotDTOForProject(relationship, 7)
      .tracks[0]?.secondary_psyke_entry_id === 42;
  })(),
);
check(
  "Core-valid blank PSYKE subject labels pass validation when stable id and type remain present",
  (() => {
    const blankLabel = structuredClone(snapshot());
    blankLabel.tracks[0]!.primary_psyke_entry_name = "";
    return validateProgressionSnapshotDTOForProject(blankLabel, 7)
      .tracks[0]?.primary_psyke_entry_id === 41;
  })(),
);
rejects("character tracks still require an exact character subject type", () => {
  const invalid = structuredClone(snapshot());
  invalid.tracks[0]!.primary_psyke_entry_type = "";
  validateProgressionSnapshotDTOForProject(invalid, 7);
});
rejects("story track cannot carry a PSYKE subject", () => {
  const invalid = structuredClone(snapshot());
  invalid.tracks[0]!.kind = "story";
  invalid.summary.by_kind.character = 0;
  invalid.summary.by_kind.story = 1;
  validateProgressionSnapshotDTOForProject(invalid, 7);
});
rejects("foreign project snapshot is rejected", () => validateProgressionSnapshotDTOForProject(snapshot(), 8));
rejects("scene anchor without scene id is rejected", () => {
  const invalid = structuredClone(snapshot());
  invalid.tracks[0]!.beats[0]!.scene_id = null;
  validateProgressionSnapshotDTOForProject(invalid, 7);
});
rejects("coverage counts cannot disagree with beats", () => {
  const invalid = structuredClone(snapshot());
  invalid.tracks[0]!.coverage.anchored_beats = 0;
  validateProgressionSnapshotDTOForProject(invalid, 7);
});
check(
  "valid command result binds created beat family and revision",
  validateProgressionCommandResultDTOForRequest(structuredClone(result), 7, command).created_beat_id === 21,
);
check(
  "replayed create preserves its original created id with empty affected families",
  validateProgressionCommandResultDTOForRequest({
    ...structuredClone(result),
    changed: false,
    replayed: true,
    affected_track_ids: [],
    affected_beat_ids: [],
  }, 7, command).created_beat_id === 21,
);
rejects("fresh no-op create cannot claim a created id", () => {
  validateProgressionCommandResultDTOForRequest({
    ...structuredClone(result),
    changed: false,
    replayed: false,
    progressions: snapshot({ revision: revisionA }),
    applied_revision: revisionA,
    affected_track_ids: [],
    affected_beat_ids: [],
  }, 7, command);
});
rejects("create beat cannot claim a created track", () => {
  validateProgressionCommandResultDTOForRequest({ ...structuredClone(result), created_track_id: 11 }, 7, command);
});

function stableCompact(value: unknown): string {
  if (value === null || typeof value === "string" || typeof value === "boolean" || typeof value === "number") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableCompact).join(",")}]`;
  const record = value as Record<string, unknown>;
  return `{${Object.keys(record).sort().filter((key) => record[key] !== undefined).map((key) => `${JSON.stringify(key)}:${stableCompact(record[key])}`).join(",")}}`;
}
async function commandDigest(): Promise<string> {
  const { kind, expected_revision, ...fields } = command;
  const body = stableCompact({ scope: "progression-command-v1", project_id: 7, kind, expected_revision, fields });
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(body));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}
const digest = await commandDigest();
const receipt: ProgressionCommandReceiptDTO = {
  project_id: 7,
  request_digest: digest,
  command_kind: "create_beat",
  expected_revision: revisionA,
  applied_revision: revisionB,
  original_changed: true,
  original_affected_track_ids: [11],
  original_affected_beat_ids: [21],
  original_created_track_id: null,
  original_created_beat_id: 21,
  committed_at: "2026-10-09T12:00:00Z",
};
check(
  "valid receipt is bound to exact command digest",
  validateProgressionCommandReceiptDTOForRequest(structuredClone(receipt), 7, command, digest).original_created_beat_id === 21,
);
rejects("receipt digest mismatch is rejected", () => {
  validateProgressionCommandReceiptDTOForRequest({ ...receipt, request_digest: "c".repeat(64) }, 7, command, digest);
});

const originalFetch = globalThis.fetch;
const requests: Array<{ url: string; init: RequestInit }> = [];
globalThis.fetch = async (inputValue: RequestInfo | URL, init: RequestInit = {}) => {
  const url = String(inputValue);
  requests.push({ url, init });
  const payload = url.endsWith("/command-receipt")
    ? receipt
    : init.method === "POST"
      ? result
      : snapshot();
  return new Response(JSON.stringify(payload), { status: 200, headers: { "content-type": "application/json" } });
};
try {
  const api = createHttpApiClient("");
  const read = await api.getProgressions(7);
  check("HTTP adapter uses canonical Progressions GET", read.project_id === 7 && requests.at(-1)?.url === "/api/projects/7/progressions");
  const applied = await api.executeProgressionCommand(7, command, "progression-test-key-0001");
  const commandRequest = requests.at(-1)!;
  const commandHeaders = new Headers(commandRequest.init.headers);
  check(
    "HTTP adapter posts exact command with Idempotency-Key",
    applied.created_beat_id === 21
      && commandRequest.url === "/api/projects/7/progressions/commands"
      && commandRequest.init.method === "POST"
      && commandHeaders.get("idempotency-key") === "progression-test-key-0001"
      && JSON.stringify(JSON.parse(String(commandRequest.init.body))) === JSON.stringify(command),
  );
  const recovered = await api.getProgressionCommandReceipt(7, "progression-test-key-0001", command);
  const receiptRequest = requests.at(-1)!;
  const receiptHeaders = new Headers(receiptRequest.init.headers);
  check(
    "HTTP receipt read is no-store and validates canonical digest",
    recovered.applied_revision === revisionB
      && receiptRequest.url === "/api/projects/7/progressions/command-receipt"
      && receiptHeaders.get("idempotency-key") === "progression-test-key-0001"
      && receiptHeaders.get("cache-control") === "no-store",
  );
} finally {
  globalThis.fetch = originalFetch;
}

class MemoryStorage implements ProgressionCommandStorage {
  readonly values = new Map<string, string>();
  getItem(key: string): string | null { return this.values.get(key) ?? null; }
  setItem(key: string, value: string): void { this.values.set(key, value); }
  removeItem(key: string): void { this.values.delete(key); }
}

const coordinatorStorage = new MemoryStorage();
const coordinatorPending = {
  projectId: 7,
  command,
  key: "progression-recovery-key-0001",
  resendAttempted: true,
  receiptOnly: true,
};
const coordinator = new ProgressionCommandCoordinator("core-alpha", coordinatorStorage);
check(
  "pending Progressions recovery command is durably saved before transport",
  await coordinator.save("progression-beat:7:new-11", coordinatorPending),
);
resetProgressionCommandMemoryForTests();
const restartedCoordinator = new ProgressionCommandCoordinator("core-alpha", coordinatorStorage);
const restartedPending = await restartedCoordinator.load(7);
check(
  "exact Progressions command and idempotency key survive a simulated app restart",
  restartedPending?.saveKey === "progression-beat:7:new-11"
    && restartedPending.pending.key === coordinatorPending.key
    && JSON.stringify(restartedPending.pending.command) === JSON.stringify(command)
    && restartedPending.pending.receiptOnly,
);
check(
  "durable Progressions recovery records are isolated by Core scope and project",
  await new ProgressionCommandCoordinator("core-beta", coordinatorStorage).load(7) === null
    && await restartedCoordinator.load(8) === null,
);
await restartedCoordinator.remove(7, "a-stale-save-owner");
check(
  "a stale panel cannot erase a newer durable Progressions recovery record",
  (await restartedCoordinator.load(7))?.pending.key === coordinatorPending.key,
);
check(
  "the exact save owner can clear its durable Progressions recovery record",
  await restartedCoordinator.remove(7, "progression-beat:7:new-11"),
);
check(
  "the cleared Progressions recovery record is absent",
  await restartedCoordinator.load(7) === null,
);
check(
  "a lost compare-remove response can be retried idempotently after the tombstone committed",
  await restartedCoordinator.remove(7, "progression-beat:7:new-11"),
);

const component = readFileSync(join(process.cwd(), "src", "components", "bible", "ProgressionsPanel.tsx"), "utf8");
for (const marker of [
  'data-screen-label="BIBLE · PROGRESSIONS"',
  '"progression_receipt_not_found"',
  'registerProjectFlusher',
  'markProjectSavePending',
  'ANCHOR COVERAGE',
  'navigate("Manuscript", { sceneId:',
  'navigate("PSYKE", { psykeEntryId:',
  'primarySubjectOptions',
  'A relationship progression needs two different PSYKE subjects.',
  'legacyCompatibilityLocked',
  'sourceRevision: snapshot?.revision ?? null',
  'expected_revision: current.sourceRevision!',
  '...(textChanged ? { text: current.text.trim() } : {})',
  'pendingProgressionCommandsRef',
  'ProgressionCommandCoordinator',
  'commandCoordinatorRef.current.save(saveKey, pending)',
  'getProgressionCommandReceipt(pending.projectId, pending.key, pending.command)',
  'pending.receiptOnly || pending.resendAttempted',
  'No durable receipt is available yet after the one allowed same-key resend.',
  'inFlightProgressionCommandsRef.current.size > 0',
  'const commandSaveKey = saveKey ?? `progression-action:${ownerProjectId}:${name}`;',
  'const stored = await commandCoordinator.load(projectId);',
  'pending.projectId !== previousProjectId',
  'checkPendingReceiptOnly',
  'useProgressionTarget',
  'data-progression-track-id',
  'data-progression-beat-id',
  'That Progressions evidence is no longer present in the current project.',
  'targetRequestRef',
  'requestId: refetch()',
  'lastSuccessfulRequest < targetRequestRef.current.requestId',
  'if (!data || data.project_id !== projectId)',
  'lastSuccessfulRequest >= commandSnapshot.authoritativeRequestId',
  'const selectedTrack = filteredTracks.find',
  'ownerWindow?.confirm("Delete this progression track and every beat in it?")',
  '>ABANDON</button>',
  '>CHECK RECEIPT</button>',
]) check(`Progressions panel includes ${marker}`, component.includes(marker));
check(
  "receipt-only retry checks the same key before considering its one resend",
  (() => {
    const resume = component.slice(
      component.indexOf("const resumePending"),
      component.indexOf("const runCommand"),
    );
    return resume.indexOf("recovered = await checkSavedReceipt(pending);")
      < resume.indexOf("if (pending.receiptOnly || pending.resendAttempted)");
  })(),
);
check(
  "same-render double Save is blocked before the first await",
  component.indexOf("inFlightProgressionCommandsRef.current.add(commandSaveKey)")
    < component.indexOf('setStatus("Saving Progressions…")'),
);
check(
  "a pending Save cannot mint a replacement command key",
  (component.match(/const key = idempotencyKey\(\);/g) ?? []).length === 1
    && !component.slice(
      component.indexOf("const resumePending"),
      component.indexOf("const runCommand"),
    ).includes("idempotencyKey()"),
);
check(
  "track and beat reorder partitions are rebuilt from the latest snapshot",
  component.includes("const ids = [...latest.tracks]")
    && component.includes("const latestTrack = latest.tracks.find"),
);
check(
  "all eight commands use the persisted receipt delivery path",
  !component.includes("const deliver = useCallback")
    && component.includes("replacePending(commandSaveKey, nextPending)")
    && component.includes("deliverSaved(commandSaveKey, nextPending)")
    && component.includes("trackProjectWrite(write, { saveKey: commandSaveKey })"),
);
check(
  "project switching restores unresolved per-project receipt state",
  component.includes("pending.projectId !== previousProjectId")
    && component.includes("pending.projectId === projectId")
    && component.includes("setReceiptOnlySaveKey(stored.saveKey)"),
);

const platform = { isDesktop: false } as PlatformAdapter;
const progressionApi = (read: () => Promise<ProgressionSnapshotDTO>): ApiClient => ({
  getProgressions: read,
  listPsyke: async () => [],
  listScenes: async () => [],
  subscribe: () => () => {},
} as unknown as ApiClient);
const renderTarget = async (
  api: ApiClient,
  target: { trackId: number | null; beatId: number | null } | null,
  onClear: () => void,
): Promise<ReactTestRenderer> => {
  let renderer!: ReactTestRenderer;
  await act(async () => {
    renderer = create(createElement(StudioProvider, {
      services: { api, platform },
      projectId: 7,
      nav: { progressionTarget: target, clearProgressionTarget: onClear },
      children: createElement(ProgressionsPanel),
    }));
    for (let index = 0; index < 6; index += 1) await Promise.resolve();
  });
  return renderer;
};

const targetTree = (
  api: ApiClient,
  target: { trackId: number | null; beatId: number | null } | null,
  onClear: () => void,
) => createElement(StudioProvider, {
  services: { api, platform },
  projectId: 7,
  nav: { progressionTarget: target, clearProgressionTarget: onClear },
  children: createElement(ProgressionsPanel),
});

let unavailableClears = 0;
let targetRenderer = await renderTarget(
  progressionApi(async () => { throw new Error("Progressions unavailable"); }),
  { trackId: 11, beatId: null },
  () => { unavailableClears += 1; },
);
check(
  "a failed Progressions read keeps the exact one-shot target pending",
  unavailableClears === 0,
);
act(() => targetRenderer.unmount());

let cachedReads = 0;
let cachedFailureClears = 0;
const cachedFailureApi = progressionApi(async () => {
  cachedReads += 1;
  if (cachedReads === 1) return snapshot({ tracks: [] });
  throw new Error("Post-target Progressions read failed");
});
targetRenderer = await renderTarget(cachedFailureApi, null, () => { cachedFailureClears += 1; });
await act(async () => {
  targetRenderer.update(targetTree(
    cachedFailureApi,
    { trackId: 11, beatId: null },
    () => { cachedFailureClears += 1; },
  ));
  for (let index = 0; index < 8; index += 1) await Promise.resolve();
});
check(
  "a failed post-target read cannot consume the target against an older cached snapshot",
  cachedReads >= 2
    && cachedFailureClears === 0
    && !targetRenderer.root.findAllByProps({ role: "status" })
      .some((node) => node.children.join("").includes("no longer present")),
);
act(() => targetRenderer.unmount());

let staleClears = 0;
targetRenderer = await renderTarget(
  progressionApi(async () => snapshot({ tracks: [] })),
  { trackId: 11, beatId: null },
  () => { staleClears += 1; },
);
check(
  "only an authoritative current snapshot may consume a missing target as stale",
  staleClears === 1
    && targetRenderer.root.findAllByProps({ role: "status" })
      .some((node) => node.children.join("").includes("no longer present")),
);
act(() => targetRenderer.unmount());

let resolvedClears = 0;
targetRenderer = await renderTarget(
  progressionApi(async () => snapshot()),
  { trackId: null, beatId: 21 },
  () => { resolvedClears += 1; },
);
check(
  "an authoritative beat target opens the exact row and is consumed once",
  resolvedClears === 1
    && targetRenderer.root.findByProps({ "data-progression-beat-id": 21 }),
);
act(() => targetRenderer.unmount());

const renderedText = (node: { children?: readonly unknown[] }): string => (node.children ?? [])
  .map((child) => typeof child === "string" || typeof child === "number"
    ? String(child)
    : child && typeof child === "object" && "children" in child
      ? renderedText(child as { children?: readonly unknown[] })
      : "")
  .join("");
const findButton = (renderer: ReactTestRenderer, label: string) => renderer.root
  .findAllByType("button")
  .find((candidate) => renderedText(candidate) === label);
const settle = async (turns = 10) => {
  for (let index = 0; index < turns; index += 1) await Promise.resolve();
};
const renderPanel = async (
  api: ApiClient,
  panelPlatform: PlatformAdapter,
  ownerDocument?: Document,
): Promise<ReactTestRenderer> => {
  let renderer!: ReactTestRenderer;
  const panel = createElement(ProgressionsPanel);
  const child = ownerDocument
    ? createElement(PanelHostProvider, { ownerDocument }, panel)
    : panel;
  await act(async () => {
    renderer = create(createElement(StudioProvider, {
      services: { api, platform: panelPlatform },
      projectId: 7,
      children: child,
    }));
    await settle();
  });
  return renderer;
};

const ambientStorageDescriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
const ambientConfirmDescriptor = Object.getOwnPropertyDescriptor(globalThis, "confirm");
const panelStorage = new MemoryStorage();
Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: panelStorage,
});
try {
  // Electron recovery is asynchronous and app-owned. The panel must remain
  // mutation-locked until that authority has answered, then restore the exact
  // command without consulting the renderer origin's localStorage.
  const hostScope = "progressions-desktop-host-store-test";
  const hostBacking = new MemoryStorage();
  await new ProgressionCommandCoordinator(hostScope, hostBacking).save(
    "progression-beat:7:desktop-host",
    {
      projectId: 7,
      command,
      key: "progression-desktop-host-key-0001",
      resendAttempted: true,
      receiptOnly: false,
    },
  );
  const hostRaw = [...hostBacking.values.values()][0]!;
  let resolveHostLoad!: (value: string | null) => void;
  const hostLoad = new Promise<string | null>((resolve) => { resolveHostLoad = resolve; });
  const desktopHostStorage: ProgressionCommandStorage = {
    getItem: () => hostLoad,
    setItem: (_key, value) => { hostBacking.values.set([...hostBacking.values.keys()][0]!, value); },
    removeItem: (key) => { hostBacking.removeItem(key); return true; },
  };
  let gatedRenderer = await renderPanel(
    progressionApi(async () => snapshot()),
    {
      ...platform,
      isDesktop: true,
      persistenceScope: hostScope,
      progressionCommandStorage: desktopHostStorage,
    },
  );
  check(
    "desktop Progressions mutations stay gated while app-owned recovery is loading",
    findButton(gatedRenderer, "+ TRACK")?.props.disabled === true
      && gatedRenderer.root.findAllByProps({ role: "status" })
        .some((node) => renderedText(node).includes("Checking durable Progressions recovery")),
  );
  await act(async () => {
    resolveHostLoad(hostRaw);
    await settle(14);
  });
  check(
    "desktop host recovery restores the unresolved command as receipt-only",
    findButton(gatedRenderer, "CHECK RECEIPT") != null
      && findButton(gatedRenderer, "+ TRACK")?.props.disabled === true,
  );
  act(() => gatedRenderer.unmount());

  // A persisted ambiguous delivery represents a renderer/app that disappeared
  // after transport started. A fresh component must use only the same receipt.
  const restartScope = "progressions-restart-panel-test";
  const restartSaveKey = "progression-beat:7:new-11";
  const restartKey = "progression-panel-restart-key-0001";
  const restartCoordinator = new ProgressionCommandCoordinator(restartScope, panelStorage);
  await restartCoordinator.save(restartSaveKey, {
    projectId: 7,
    command,
    key: restartKey,
    resendAttempted: true,
    receiptOnly: false,
  });
  resetProgressionCommandMemoryForTests();
  let restartExecuteCalls = 0;
  let restartReceiptKey = "";
  let restartReceiptCommand: ProgressionCommandDTO | null = null;
  const restartApi = {
    ...progressionApi(async () => snapshot()),
    executeProgressionCommand: async () => {
      restartExecuteCalls += 1;
      throw new Error("a restored command must never be resent");
    },
    getProgressionCommandReceipt: async (_projectId: number, key: string, expected: ProgressionCommandDTO) => {
      restartReceiptKey = key;
      restartReceiptCommand = expected;
      return receipt;
    },
  } as ApiClient;
  let panelRenderer = await renderPanel(
    restartApi,
    { ...platform, persistenceScope: restartScope },
  );
  const checkReceiptButton = findButton(panelRenderer, "CHECK RECEIPT");
  check(
    "a fresh Progressions subtree restores an unresolved durable command as receipt-only",
    checkReceiptButton != null
      && panelRenderer.root.findAllByProps({ role: "alert" })
        .some((node) => renderedText(node).includes("Only its durable receipt")),
  );
  await act(async () => {
    checkReceiptButton?.props.onClick();
    await settle(14);
  });
  check(
    "receipt recovery after simulated restart uses the exact persisted key and command without resend",
    restartExecuteCalls === 0
      && restartReceiptKey === restartKey
      && JSON.stringify(restartReceiptCommand) === JSON.stringify(command)
      && await new ProgressionCommandCoordinator(restartScope, panelStorage).load(7) === null
      && panelRenderer.root.findAllByProps({ role: "status" })
        .some((node) => renderedText(node).includes("Recovered the committed Progressions change")),
  );
  act(() => panelRenderer.unmount());

  const staleInitial = snapshot({ revision: revisionA });
  const staleConcurrent = structuredClone(staleInitial);
  staleConcurrent.revision = revisionB;
  staleConcurrent.tracks[0]!.title = "A collaborator changed this title";
  let staleReads = 0;
  let staleSubmitted: ProgressionCommandDTO | null = null;
  const staleApi = {
    ...progressionApi(async () => {
      staleReads += 1;
      return staleReads === 1 ? staleInitial : staleConcurrent;
    }),
    listPsyke: async () => [{
      id: 41,
      name: "Mara",
      type: "character",
      aliases: [],
      notes: "",
      is_global: false,
      details: {},
    }],
    executeProgressionCommand: async (_projectId: number, submitted: ProgressionCommandDTO) => {
      staleSubmitted = submitted;
      throw new ApiRequestError(
        "POST",
        "/api/projects/7/progressions/commands",
        409,
        "Progressions changed after they were loaded.",
        "progression_conflict",
      );
    },
    getProgressionCommandReceipt: async () => { throw new Error("not expected"); },
  } as ApiClient;
  panelRenderer = await renderPanel(
    staleApi,
    { ...platform, persistenceScope: "progressions-stale-edit-test" },
  );
  await act(async () => {
    findButton(panelRenderer, "EDIT")?.props.onClick();
    await settle();
  });
  const staleDialog = panelRenderer.root.findByProps({ role: "dialog" });
  act(() => staleDialog.findAllByType("input")[0]!.props.onChange({
    target: { value: "My local title" },
  }));
  await act(async () => {
    findButton(panelRenderer, "SAVE")?.props.onClick();
    await settle(14);
  });
  check(
    "a stale full-field track draft submits its opening revision instead of silently rebasing",
    staleSubmitted?.kind === "update_track"
      && staleSubmitted.expected_revision === revisionA
      && panelRenderer.root.findAllByProps({ role: "dialog" }).length === 1
      && panelRenderer.root.findAllByProps({ role: "alert" })
        .some((node) => renderedText(node).includes("will not be rebased over newer work")),
  );
  act(() => findButton(panelRenderer, "CANCEL")?.props.onClick());
  act(() => panelRenderer.unmount());

  const commandBase = snapshot({ revision: revisionA });
  const commandView = structuredClone(commandBase);
  commandView.revision = revisionB;
  commandView.tracks[0]!.title = "Optimistic command response";
  const authoritativeView = structuredClone(commandView);
  authoritativeView.revision = revisionC;
  authoritativeView.tracks[0]!.title = "Authoritative live title";
  let commandReads = 0;
  const snapshotApi = {
    ...progressionApi(async () => {
      commandReads += 1;
      return commandReads <= 2 ? commandBase : authoritativeView;
    }),
    listPsyke: async () => [{
      id: 41,
      name: "Mara",
      type: "character",
      aliases: [],
      notes: "",
      is_global: false,
      details: {},
    }],
    executeProgressionCommand: async () => ({
      progressions: commandView,
      changed: true,
      affected_track_ids: [11],
      affected_beat_ids: [],
      created_track_id: null,
      created_beat_id: null,
      replayed: false,
      applied_revision: revisionB,
    }),
    getProgressionCommandReceipt: async () => { throw new Error("not expected"); },
  } as ApiClient;
  panelRenderer = await renderPanel(
    snapshotApi,
    { ...platform, persistenceScope: "progressions-command-snapshot-test" },
  );
  act(() => findButton(panelRenderer, "EDIT")?.props.onClick());
  const snapshotDialog = panelRenderer.root.findByProps({ role: "dialog" });
  act(() => snapshotDialog.findAllByType("input")[0]!.props.onChange({
    target: { value: "Local command title" },
  }));
  await act(async () => {
    findButton(panelRenderer, "SAVE")?.props.onClick();
    await settle(16);
  });
  check(
    "a post-command authoritative read supersedes the optimistic command snapshot",
    commandReads >= 3
      && renderedText(panelRenderer.root.findByType("h2")) === "Authoritative live title"
      && !renderedText(panelRenderer.root).includes("Optimistic command response"),
  );
  act(() => panelRenderer.unmount());

  const filteredSnapshot = structuredClone(snapshot({ revision: revisionA }));
  const storyTrack = structuredClone(filteredSnapshot.tracks[0]!);
  storyTrack.id = 12;
  storyTrack.kind = "story";
  storyTrack.title = "The visible story track";
  storyTrack.sort_order = 1;
  storyTrack.primary_psyke_entry_id = null;
  storyTrack.primary_psyke_entry_name = "";
  storyTrack.primary_psyke_entry_type = "";
  storyTrack.beats = [];
  storyTrack.coverage = {
    total_beats: 0,
    anchored_beats: 0,
    unanchored_beats: 0,
    scene_anchored_beats: 0,
    document_anchored_beats: 0,
    coverage_percent: 0,
    status: "empty",
    out_of_order_beat_ids: [],
  };
  filteredSnapshot.tracks.push(storyTrack);
  panelRenderer = await renderPanel(
    progressionApi(async () => filteredSnapshot),
    { ...platform, persistenceScope: "progressions-filter-selection-test" },
  );
  act(() => findButton(panelRenderer, "story")?.props.onClick());
  check(
    "selection is reconciled to a track inside the active kind filter",
    renderedText(panelRenderer.root.findByType("h2")) === "The visible story track",
  );
  act(() => panelRenderer.unmount());

  let ownerConfirmCalls = 0;
  let detachedExecuteCalls = 0;
  Object.defineProperty(globalThis, "confirm", {
    configurable: true,
    value: () => { throw new Error("ambient confirmation must not be used"); },
  });
  const ownerWindow = {
    localStorage: panelStorage,
    confirm: () => {
      ownerConfirmCalls += 1;
      return false;
    },
  } as unknown as Window;
  const ownerDocument = { defaultView: ownerWindow } as unknown as Document;
  const detachedApi = {
    ...progressionApi(async () => snapshot()),
    executeProgressionCommand: async () => {
      detachedExecuteCalls += 1;
      throw new Error("confirmation should have cancelled");
    },
  } as ApiClient;
  panelRenderer = await renderPanel(
    detachedApi,
    { ...platform, persistenceScope: "progressions-detached-confirm-test" },
    ownerDocument,
  );
  act(() => findButton(panelRenderer, "DELETE")?.props.onClick());
  check(
    "destructive confirmation uses the detached panel ownerWindow",
    ownerConfirmCalls === 1 && detachedExecuteCalls === 0,
  );
  act(() => panelRenderer.unmount());
} finally {
  if (ambientStorageDescriptor) {
    Object.defineProperty(globalThis, "localStorage", ambientStorageDescriptor);
  } else {
    Reflect.deleteProperty(globalThis, "localStorage");
  }
  if (ambientConfirmDescriptor) {
    Object.defineProperty(globalThis, "confirm", ambientConfirmDescriptor);
  } else {
    Reflect.deleteProperty(globalThis, "confirm");
  }
  resetProgressionCommandMemoryForTests();
}

console.log(`Progressions UI/adapter tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} Progressions test(s) failed`);

for (const handle of process._getActiveHandles()) {
  if (handle instanceof MessagePort) handle.unref();
}
