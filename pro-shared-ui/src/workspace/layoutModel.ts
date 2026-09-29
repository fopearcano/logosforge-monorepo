/**
 * Platform-neutral, persisted state for the Studio workspace.
 *
 * Hosts store this object through PlatformAdapter.loadLayout/saveLayout. The
 * renderer owns its meaning: hosts must continue treating it as opaque JSON.
 * Keep every mutation immutable so a shell can safely queue persistence from
 * React state without an earlier snapshot changing underneath it.
 */

export const WORKSPACE_LAYOUT_SCHEMA = "logosforge.pro.workspace-layout" as const;
export const WORKSPACE_LAYOUT_VERSION = 1 as const;

export const WORKSPACE_PANEL_LIMIT = 128;
export const WORKSPACE_PANEL_ID_LIMIT = 120;

export const DOCK_REGION_IDS = ["left", "center", "right", "bottom"] as const;
export type DockRegionId = (typeof DOCK_REGION_IDS)[number];
export type WorkspacePreset = "cockpit" | "focus";

export interface NavigatorLayout {
  collapsed: boolean;
  widthPx: number;
}

export interface DockRegionLayout {
  /** Ordered tabs in this dock. */
  panelIds: string[];
  /** Null exactly when the dock has no panels. */
  activePanelId: string | null;
  /** Center is the permanent work surface and can never be collapsed. */
  collapsed: boolean;
  /** Width for side docks, height for bottom, and zero for center. */
  sizePx: number;
}

export interface FloatingPanelLayout {
  panelId: string;
  x: number;
  y: number;
  width: number;
  height: number;
  minimized: boolean;
  /** Contiguous, zero-based stacking order. */
  zIndex: number;
}

export interface WorkspaceLayout {
  schema: typeof WORKSPACE_LAYOUT_SCHEMA;
  version: typeof WORKSPACE_LAYOUT_VERSION;
  /** Focus changes visibility only; the underlying cockpit arrangement stays. */
  preset: WorkspacePreset;
  navigator: NavigatorLayout;
  docks: Record<DockRegionId, DockRegionLayout>;
  floatingPanels: FloatingPanelLayout[];
  /** Last keyboard/pointer focus. Active tabs remain separately tracked per dock. */
  focused: WorkspacePanelFocus | null;
}

export type WorkspaceZoneId = DockRegionId | "floating";

export interface WorkspacePanelFocus {
  zone: WorkspaceZoneId;
  panelId: string;
}

/** The only legacy shape accepted by the migration boundary. */
export interface LegacyWorkspaceLayoutV0 {
  version: 0;
  mode: WorkspacePreset;
  navigatorCollapsed: boolean;
  navigatorWidthPx: number;
  rightDockWidthPx: number;
  bottomDockHeightPx: number;
  centerPanelIds: string[];
  rightPanelIds: string[];
  bottomPanelIds: string[];
}

export type WorkspaceLayoutValidation =
  | { ok: true; value: WorkspaceLayout }
  | { ok: false; issues: string[] };

export type WorkspaceLayoutRestoreSource = "current" | "migrated" | "default";
export type WorkspaceLayoutFallbackReason = "absent" | "invalid" | "future";

export interface RestoredWorkspaceLayout {
  layout: WorkspaceLayout;
  source: WorkspaceLayoutRestoreSource;
  /** Empty for a valid current layout and an intentionally absent saved value. */
  diagnostics: string[];
  /** Why a safe default was projected; omitted for restored/migrated layouts. */
  fallbackReason?: WorkspaceLayoutFallbackReason;
}

export type PanelPlacement =
  | { kind: "dock"; region: DockRegionId; index: number }
  | { kind: "floating"; bounds?: Partial<FloatingPanelBounds> };

export interface FloatingPanelBounds {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface WorkspaceVisibility {
  navigator: boolean;
  docks: Record<DockRegionId, boolean>;
  floatingPanelIds: string[];
}

export class WorkspaceLayoutValidationError extends Error {
  readonly issues: string[];

  constructor(issues: readonly string[]) {
    super(`Invalid Studio workspace layout: ${issues.join("; ")}`);
    this.name = "WorkspaceLayoutValidationError";
    this.issues = [...issues];
  }
}

export const NAVIGATOR_SIZE = { min: 160, max: 480, default: 232 } as const;
export const DOCK_SIZE = {
  left: { min: 240, max: 960, default: 300 },
  center: { min: 0, max: 0, default: 0 },
  right: { min: 240, max: 960, default: 460 },
  bottom: { min: 120, max: 640, default: 220 },
} as const satisfies Record<DockRegionId, { min: number; max: number; default: number }>;

export const FLOATING_PANEL_SIZE = {
  minWidth: 240,
  maxWidth: 1_920,
  minHeight: 160,
  maxHeight: 1_200,
  defaultWidth: 640,
  defaultHeight: 480,
} as const;

const POSITION_LIMIT = 100_000;
const PANEL_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9 ._:/-]*$/;

function defaultDock(region: DockRegionId, panelIds: string[]): DockRegionLayout {
  return {
    panelIds: [...panelIds],
    activePanelId: panelIds[0] ?? null,
    collapsed: region !== "center" && panelIds.length === 0,
    sizePx: DOCK_SIZE[region].default,
  };
}

/** A useful first-run Cockpit. IDs are renderer registry keys, not display text. */
export function createDefaultWorkspaceLayout(): WorkspaceLayout {
  return {
    schema: WORKSPACE_LAYOUT_SCHEMA,
    version: WORKSPACE_LAYOUT_VERSION,
    preset: "cockpit",
    navigator: { collapsed: false, widthPx: NAVIGATOR_SIZE.default },
    docks: {
      left: defaultDock("left", []),
      center: defaultDock("center", ["manuscript", "dashboard"]),
      right: defaultDock("right", ["ai-companions", "decision-radar"]),
      bottom: defaultDock("bottom", ["outline", "health"]),
    },
    floatingPanels: [],
    focused: { zone: "center", panelId: "manuscript" },
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function checkExactKeys(
  value: Record<string, unknown>,
  expected: readonly string[],
  path: string,
  issues: string[],
): boolean {
  const expectedSet = new Set(expected);
  const missing = expected.filter((key) => !Object.prototype.hasOwnProperty.call(value, key));
  const extra = Object.keys(value).filter((key) => !expectedSet.has(key));
  if (missing.length > 0) issues.push(`${path} is missing ${missing.join(", ")}`);
  if (extra.length > 0) issues.push(`${path} has unsupported keys ${extra.join(", ")}`);
  return missing.length === 0 && extra.length === 0;
}

function isIntegerInRange(value: unknown, min: number, max: number): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= min && value <= max;
}

function isPanelId(value: unknown): value is string {
  return typeof value === "string"
    && value.length > 0
    && value.length <= WORKSPACE_PANEL_ID_LIMIT
    && value.trim() === value
    && PANEL_ID_PATTERN.test(value);
}

function readPanelIds(value: unknown, path: string, issues: string[]): string[] | null {
  if (!Array.isArray(value)) {
    issues.push(`${path} must be an array`);
    return null;
  }
  if (value.length > WORKSPACE_PANEL_LIMIT) {
    issues.push(`${path} exceeds ${WORKSPACE_PANEL_LIMIT} panels`);
    return null;
  }
  const panelIds: string[] = [];
  const local = new Set<string>();
  for (let index = 0; index < value.length; index += 1) {
    const panelId = value[index];
    if (!isPanelId(panelId)) {
      issues.push(`${path}[${index}] is not a valid panel ID`);
      continue;
    }
    if (local.has(panelId)) {
      issues.push(`${path} contains duplicate panel ID ${panelId}`);
      continue;
    }
    local.add(panelId);
    panelIds.push(panelId);
  }
  return panelIds;
}

function readDock(value: unknown, region: DockRegionId, issues: string[]): DockRegionLayout | null {
  const path = `layout.docks.${region}`;
  if (!isRecord(value)) {
    issues.push(`${path} must be an object`);
    return null;
  }
  checkExactKeys(value, ["panelIds", "activePanelId", "collapsed", "sizePx"], path, issues);
  const panelIds = readPanelIds(value.panelIds, `${path}.panelIds`, issues);
  if (panelIds === null) return null;

  const active = value.activePanelId;
  if (active !== null && !isPanelId(active)) {
    issues.push(`${path}.activePanelId must be a panel ID or null`);
  } else if (panelIds.length === 0 && active !== null) {
    issues.push(`${path}.activePanelId must be null for an empty dock`);
  } else if (typeof active === "string" && !panelIds.includes(active)) {
    issues.push(`${path}.activePanelId must belong to its dock`);
  } else if (panelIds.length > 0 && active === null) {
    issues.push(`${path}.activePanelId is required for a non-empty dock`);
  }

  if (typeof value.collapsed !== "boolean") {
    issues.push(`${path}.collapsed must be boolean`);
  } else if (region === "center" && value.collapsed) {
    issues.push("layout.docks.center cannot be collapsed");
  } else if (region !== "center" && panelIds.length === 0 && !value.collapsed) {
    issues.push(`${path} must be collapsed while empty`);
  }

  const size = DOCK_SIZE[region];
  if (!isIntegerInRange(value.sizePx, size.min, size.max)) {
    issues.push(`${path}.sizePx must be an integer from ${size.min} to ${size.max}`);
  }

  if (
    (active !== null && !isPanelId(active))
    || typeof value.collapsed !== "boolean"
    || !isIntegerInRange(value.sizePx, size.min, size.max)
  ) return null;

  return {
    panelIds,
    activePanelId: active,
    collapsed: value.collapsed,
    sizePx: value.sizePx,
  };
}

function readFloatingPanel(
  value: unknown,
  index: number,
  issues: string[],
): FloatingPanelLayout | null {
  const path = `layout.floatingPanels[${index}]`;
  if (!isRecord(value)) {
    issues.push(`${path} must be an object`);
    return null;
  }
  checkExactKeys(value, ["panelId", "x", "y", "width", "height", "minimized", "zIndex"], path, issues);
  if (!isPanelId(value.panelId)) issues.push(`${path}.panelId is not valid`);
  if (!isIntegerInRange(value.x, -POSITION_LIMIT, POSITION_LIMIT)) {
    issues.push(`${path}.x is outside the supported range`);
  }
  if (!isIntegerInRange(value.y, -POSITION_LIMIT, POSITION_LIMIT)) {
    issues.push(`${path}.y is outside the supported range`);
  }
  if (!isIntegerInRange(value.width, FLOATING_PANEL_SIZE.minWidth, FLOATING_PANEL_SIZE.maxWidth)) {
    issues.push(`${path}.width is outside the supported range`);
  }
  if (!isIntegerInRange(value.height, FLOATING_PANEL_SIZE.minHeight, FLOATING_PANEL_SIZE.maxHeight)) {
    issues.push(`${path}.height is outside the supported range`);
  }
  if (typeof value.minimized !== "boolean") issues.push(`${path}.minimized must be boolean`);
  if (!isIntegerInRange(value.zIndex, 0, WORKSPACE_PANEL_LIMIT - 1)) {
    issues.push(`${path}.zIndex is outside the supported range`);
  }
  if (
    !isPanelId(value.panelId)
    || !isIntegerInRange(value.x, -POSITION_LIMIT, POSITION_LIMIT)
    || !isIntegerInRange(value.y, -POSITION_LIMIT, POSITION_LIMIT)
    || !isIntegerInRange(value.width, FLOATING_PANEL_SIZE.minWidth, FLOATING_PANEL_SIZE.maxWidth)
    || !isIntegerInRange(value.height, FLOATING_PANEL_SIZE.minHeight, FLOATING_PANEL_SIZE.maxHeight)
    || typeof value.minimized !== "boolean"
    || !isIntegerInRange(value.zIndex, 0, WORKSPACE_PANEL_LIMIT - 1)
  ) return null;
  return {
    panelId: value.panelId,
    x: value.x,
    y: value.y,
    width: value.width,
    height: value.height,
    minimized: value.minimized,
    zIndex: value.zIndex,
  };
}

/** Strictly decode the current persisted schema. Unknown keys are rejected. */
export function validateWorkspaceLayout(value: unknown): WorkspaceLayoutValidation {
  const issues: string[] = [];
  if (!isRecord(value)) return { ok: false, issues: ["layout must be an object"] };
  checkExactKeys(value, ["schema", "version", "preset", "navigator", "docks", "floatingPanels", "focused"], "layout", issues);
  if (value.schema !== WORKSPACE_LAYOUT_SCHEMA) issues.push("layout.schema is not supported");
  if (value.version !== WORKSPACE_LAYOUT_VERSION) issues.push("layout.version is not supported");
  if (value.preset !== "cockpit" && value.preset !== "focus") {
    issues.push("layout.preset must be cockpit or focus");
  }

  let navigator: NavigatorLayout | null = null;
  if (!isRecord(value.navigator)) {
    issues.push("layout.navigator must be an object");
  } else {
    checkExactKeys(value.navigator, ["collapsed", "widthPx"], "layout.navigator", issues);
    if (typeof value.navigator.collapsed !== "boolean") {
      issues.push("layout.navigator.collapsed must be boolean");
    }
    if (!isIntegerInRange(value.navigator.widthPx, NAVIGATOR_SIZE.min, NAVIGATOR_SIZE.max)) {
      issues.push(`layout.navigator.widthPx must be an integer from ${NAVIGATOR_SIZE.min} to ${NAVIGATOR_SIZE.max}`);
    }
    if (
      typeof value.navigator.collapsed === "boolean"
      && isIntegerInRange(value.navigator.widthPx, NAVIGATOR_SIZE.min, NAVIGATOR_SIZE.max)
    ) {
      navigator = { collapsed: value.navigator.collapsed, widthPx: value.navigator.widthPx };
    }
  }

  const decodedDocks: Partial<Record<DockRegionId, DockRegionLayout>> = {};
  if (!isRecord(value.docks)) {
    issues.push("layout.docks must be an object");
  } else {
    checkExactKeys(value.docks, DOCK_REGION_IDS, "layout.docks", issues);
    for (const region of DOCK_REGION_IDS) {
      const dock = readDock(value.docks[region], region, issues);
      if (dock !== null) decodedDocks[region] = dock;
    }
  }

  const floatingPanels: FloatingPanelLayout[] = [];
  if (!Array.isArray(value.floatingPanels)) {
    issues.push("layout.floatingPanels must be an array");
  } else if (value.floatingPanels.length > WORKSPACE_PANEL_LIMIT) {
    issues.push(`layout.floatingPanels exceeds ${WORKSPACE_PANEL_LIMIT} panels`);
  } else {
    value.floatingPanels.forEach((entry, index) => {
      const panel = readFloatingPanel(entry, index, issues);
      if (panel !== null) floatingPanels.push(panel);
    });
  }

  const allPanelIds: string[] = [];
  for (const region of DOCK_REGION_IDS) {
    allPanelIds.push(...(decodedDocks[region]?.panelIds ?? []));
  }
  allPanelIds.push(...floatingPanels.map((panel) => panel.panelId));
  if (allPanelIds.length > WORKSPACE_PANEL_LIMIT) {
    issues.push(`layout contains more than ${WORKSPACE_PANEL_LIMIT} panels`);
  }
  const globalIds = new Set<string>();
  for (const panelId of allPanelIds) {
    if (globalIds.has(panelId)) issues.push(`panel ${panelId} appears more than once`);
    globalIds.add(panelId);
  }

  const zIndexes = floatingPanels.map((panel) => panel.zIndex).sort((a, b) => a - b);
  if (zIndexes.some((zIndex, index) => zIndex !== index)) {
    issues.push("layout.floatingPanels zIndex values must be unique and contiguous from zero");
  }

  let focused: WorkspacePanelFocus | null = null;
  if (value.focused !== null) {
    if (!isRecord(value.focused)) {
      issues.push("layout.focused must be an object or null");
    } else {
      checkExactKeys(value.focused, ["zone", "panelId"], "layout.focused", issues);
      const zone = value.focused.zone;
      const panelId = value.focused.panelId;
      const validZone = zone === "floating" || (DOCK_REGION_IDS as readonly unknown[]).includes(zone);
      if (!validZone) issues.push("layout.focused.zone is not supported");
      if (!isPanelId(panelId)) issues.push("layout.focused.panelId is not valid");
      if (validZone && isPanelId(panelId)) {
        const placed = zone === "floating"
          ? floatingPanels.some((panel) => panel.panelId === panelId)
          : decodedDocks[zone as DockRegionId]?.panelIds.includes(panelId) === true;
        if (!placed) issues.push("layout.focused must refer to a panel in its zone");
        else focused = { zone: zone as WorkspaceZoneId, panelId };
      }
    }
  }

  if (
    issues.length > 0
    || navigator === null
    || value.schema !== WORKSPACE_LAYOUT_SCHEMA
    || value.version !== WORKSPACE_LAYOUT_VERSION
    || (value.preset !== "cockpit" && value.preset !== "focus")
    || DOCK_REGION_IDS.some((region) => decodedDocks[region] === undefined)
  ) return { ok: false, issues };

  const orderedFloating = [...floatingPanels].sort((a, b) => a.zIndex - b.zIndex);
  return {
    ok: true,
    value: {
      schema: WORKSPACE_LAYOUT_SCHEMA,
      version: WORKSPACE_LAYOUT_VERSION,
      preset: value.preset,
      navigator,
      docks: {
        left: decodedDocks.left!,
        center: decodedDocks.center!,
        right: decodedDocks.right!,
        bottom: decodedDocks.bottom!,
      },
      floatingPanels: orderedFloating,
      focused,
    },
  };
}

function validateLegacyWorkspaceLayout(value: unknown):
  | { ok: true; value: LegacyWorkspaceLayoutV0 }
  | { ok: false; issues: string[] } {
  const issues: string[] = [];
  if (!isRecord(value)) return { ok: false, issues: ["legacy layout must be an object"] };
  checkExactKeys(value, [
    "version",
    "mode",
    "navigatorCollapsed",
    "navigatorWidthPx",
    "rightDockWidthPx",
    "bottomDockHeightPx",
    "centerPanelIds",
    "rightPanelIds",
    "bottomPanelIds",
  ], "legacy layout", issues);
  if (value.version !== 0) issues.push("legacy layout.version must be 0");
  if (value.mode !== "cockpit" && value.mode !== "focus") {
    issues.push("legacy layout.mode must be cockpit or focus");
  }
  if (typeof value.navigatorCollapsed !== "boolean") {
    issues.push("legacy layout.navigatorCollapsed must be boolean");
  }
  if (!isIntegerInRange(value.navigatorWidthPx, NAVIGATOR_SIZE.min, NAVIGATOR_SIZE.max)) {
    issues.push("legacy layout.navigatorWidthPx is outside the supported range");
  }
  if (!isIntegerInRange(value.rightDockWidthPx, DOCK_SIZE.right.min, DOCK_SIZE.right.max)) {
    issues.push("legacy layout.rightDockWidthPx is outside the supported range");
  }
  if (!isIntegerInRange(value.bottomDockHeightPx, DOCK_SIZE.bottom.min, DOCK_SIZE.bottom.max)) {
    issues.push("legacy layout.bottomDockHeightPx is outside the supported range");
  }
  const centerPanelIds = readPanelIds(value.centerPanelIds, "legacy layout.centerPanelIds", issues);
  const rightPanelIds = readPanelIds(value.rightPanelIds, "legacy layout.rightPanelIds", issues);
  const bottomPanelIds = readPanelIds(value.bottomPanelIds, "legacy layout.bottomPanelIds", issues);
  const ids = [...(centerPanelIds ?? []), ...(rightPanelIds ?? []), ...(bottomPanelIds ?? [])];
  const unique = new Set<string>();
  for (const panelId of ids) {
    if (unique.has(panelId)) issues.push(`legacy panel ${panelId} appears more than once`);
    unique.add(panelId);
  }
  if (ids.length > WORKSPACE_PANEL_LIMIT) issues.push(`legacy layout exceeds ${WORKSPACE_PANEL_LIMIT} panels`);

  if (
    issues.length > 0
    || value.version !== 0
    || (value.mode !== "cockpit" && value.mode !== "focus")
    || typeof value.navigatorCollapsed !== "boolean"
    || !isIntegerInRange(value.navigatorWidthPx, NAVIGATOR_SIZE.min, NAVIGATOR_SIZE.max)
    || !isIntegerInRange(value.rightDockWidthPx, DOCK_SIZE.right.min, DOCK_SIZE.right.max)
    || !isIntegerInRange(value.bottomDockHeightPx, DOCK_SIZE.bottom.min, DOCK_SIZE.bottom.max)
    || centerPanelIds === null
    || rightPanelIds === null
    || bottomPanelIds === null
  ) return { ok: false, issues };

  return {
    ok: true,
    value: {
      version: 0,
      mode: value.mode,
      navigatorCollapsed: value.navigatorCollapsed,
      navigatorWidthPx: value.navigatorWidthPx,
      rightDockWidthPx: value.rightDockWidthPx,
      bottomDockHeightPx: value.bottomDockHeightPx,
      centerPanelIds,
      rightPanelIds,
      bottomPanelIds,
    },
  };
}

export function migrateLegacyWorkspaceLayout(value: LegacyWorkspaceLayoutV0): WorkspaceLayout {
  const layout = createDefaultWorkspaceLayout();
  layout.preset = value.mode;
  layout.navigator = { collapsed: value.navigatorCollapsed, widthPx: value.navigatorWidthPx };
  layout.docks.center = defaultDock("center", value.centerPanelIds);
  layout.docks.right = {
    ...defaultDock("right", value.rightPanelIds),
    sizePx: value.rightDockWidthPx,
  };
  layout.docks.bottom = {
    ...defaultDock("bottom", value.bottomPanelIds),
    sizePx: value.bottomDockHeightPx,
  };
  const firstFocus = layout.docks.center.activePanelId != null
    ? { zone: "center" as const, panelId: layout.docks.center.activePanelId }
    : layout.docks.right.activePanelId != null
      ? { zone: "right" as const, panelId: layout.docks.right.activePanelId }
      : layout.docks.bottom.activePanelId != null
        ? { zone: "bottom" as const, panelId: layout.docks.bottom.activePanelId }
        : null;
  layout.focused = firstFocus;
  return layout;
}

function allowedPanelSet(allowedPanelIds: Iterable<string>): Set<string> {
  const allowed = new Set<string>(["manuscript"]);
  for (const panelId of allowedPanelIds) {
    if (isPanelId(panelId)) allowed.add(panelId);
  }
  return allowed;
}

function reconcileRawCurrentLayout(
  value: unknown,
  allowed: ReadonlySet<string>,
): { value: unknown; changed: boolean } {
  if (!isRecord(value) || !isRecord(value.docks) || !Array.isArray(value.floatingPanels)) {
    return { value, changed: false };
  }
  const seen = new Set<string>();
  let changed = false;
  const nextDocks: Record<string, unknown> = { ...value.docks };
  // Center wins duplicate ownership, then visible Cockpit docks, then the
  // optional left dock. Manuscript is always repaired into center first.
  const priority: DockRegionId[] = ["center", "right", "bottom", "left"];
  for (const region of priority) {
    const rawDock = value.docks[region];
    if (!isRecord(rawDock) || !Array.isArray(rawDock.panelIds)) continue;
    const panelIds: string[] = [];
    if (region === "center") {
      panelIds.push("manuscript");
      seen.add("manuscript");
      if (rawDock.panelIds[0] !== "manuscript") changed = true;
    }
    for (const entry of rawDock.panelIds) {
      if (!isPanelId(entry) || entry === "manuscript" || !allowed.has(entry) || seen.has(entry)) {
        changed = true;
        continue;
      }
      seen.add(entry);
      panelIds.push(entry);
    }
    const activePanelId = typeof rawDock.activePanelId === "string" && panelIds.includes(rawDock.activePanelId)
      ? rawDock.activePanelId
      : panelIds[0] ?? null;
    if (activePanelId !== rawDock.activePanelId) changed = true;
    const collapsed = region === "center"
      ? false
      : panelIds.length === 0
        ? true
        : rawDock.collapsed;
    if (collapsed !== rawDock.collapsed) changed = true;
    nextDocks[region] = { ...rawDock, panelIds, activePanelId, collapsed };
  }

  const nextFloating: unknown[] = [];
  for (const entry of value.floatingPanels) {
    if (!isRecord(entry) || !isPanelId(entry.panelId) || !allowed.has(entry.panelId) || seen.has(entry.panelId)) {
      changed = true;
      continue;
    }
    seen.add(entry.panelId);
    const zIndex = nextFloating.length;
    if (entry.zIndex !== zIndex) changed = true;
    nextFloating.push({ ...entry, zIndex });
  }

  let focused: WorkspacePanelFocus = { zone: "center", panelId: "manuscript" };
  if (isRecord(value.focused) && isPanelId(value.focused.panelId)) {
    const zone = value.focused.zone;
    const focusedPanelId = value.focused.panelId;
    const placed = zone === "floating"
      ? nextFloating.some((entry) => isRecord(entry) && entry.panelId === focusedPanelId)
      : (DOCK_REGION_IDS as readonly unknown[]).includes(zone)
        && isRecord(nextDocks[zone as DockRegionId])
        && Array.isArray((nextDocks[zone as DockRegionId] as Record<string, unknown>).panelIds)
        && ((nextDocks[zone as DockRegionId] as Record<string, unknown>).panelIds as unknown[]).includes(focusedPanelId);
    if (placed) focused = { zone: zone as WorkspaceZoneId, panelId: focusedPanelId };
    else changed = true;
  } else {
    changed = true;
  }

  return {
    value: {
      ...value,
      docks: nextDocks,
      floatingPanels: nextFloating,
      focused,
    },
    changed,
  };
}

function reconcileRawLegacyLayout(
  value: unknown,
  allowed: ReadonlySet<string>,
): { value: unknown; changed: boolean } {
  if (!isRecord(value)) return { value, changed: false };
  const keys = ["centerPanelIds", "rightPanelIds", "bottomPanelIds"] as const;
  if (keys.some((key) => !Array.isArray(value[key]))) return { value, changed: false };
  const seen = new Set<string>(["manuscript"]);
  let changed = false;
  const result: Record<string, unknown> = { ...value };
  for (const key of keys) {
    const panelIds = key === "centerPanelIds" ? ["manuscript"] : [];
    const raw = value[key] as unknown[];
    if (key === "centerPanelIds" && raw[0] !== "manuscript") changed = true;
    for (const entry of raw) {
      if (!isPanelId(entry) || entry === "manuscript" || !allowed.has(entry) || seen.has(entry)) {
        changed = true;
        continue;
      }
      seen.add(entry);
      panelIds.push(entry);
    }
    result[key] = panelIds;
  }
  return { value: result, changed };
}

/**
 * Reconcile a previously decoded layout against the renderer's live panel
 * registry. Stale/plugin IDs and duplicates are dropped deterministically;
 * manuscript is repaired into center and focused as the safe home surface.
 */
export function reconcileWorkspaceLayout(
  layout: WorkspaceLayout,
  allowedPanelIds: Iterable<string>,
): WorkspaceLayout {
  const reconciled = reconcileRawCurrentLayout(layout, allowedPanelSet(allowedPanelIds));
  const parsed = validateWorkspaceLayout(reconciled.value);
  return parsed.ok ? parsed.value : resetWorkspaceLayout(allowedPanelIds);
}

export function resetWorkspaceLayout(allowedPanelIds?: Iterable<string>): WorkspaceLayout {
  const layout = createDefaultWorkspaceLayout();
  if (allowedPanelIds === undefined) return layout;
  const reconciled = reconcileRawCurrentLayout(layout, allowedPanelSet(allowedPanelIds));
  const parsed = validateWorkspaceLayout(reconciled.value);
  // The built-in fallback is structurally constant and manuscript is always
  // allowed, so reaching this branch would signal a programming error.
  if (!parsed.ok) throw new WorkspaceLayoutValidationError(parsed.issues);
  return parsed.value;
}

/**
 * Restore saved state without ever leaking a partially valid object to the UI.
 * Invalid, corrupt, or future-version data falls back to a fresh default.
 */
export function restoreWorkspaceLayout(
  input: unknown,
  allowedPanelIds?: Iterable<string>,
): RestoredWorkspaceLayout {
  const allowed = allowedPanelIds === undefined ? null : allowedPanelSet(allowedPanelIds);
  const fallback = () => allowed === null ? createDefaultWorkspaceLayout() : resetWorkspaceLayout(allowed);
  if (input === null || input === undefined || input === "") {
    return { layout: fallback(), source: "default", diagnostics: [], fallbackReason: "absent" };
  }
  let candidate: unknown = input;
  if (typeof input === "string") {
    try {
      candidate = JSON.parse(input) as unknown;
    } catch {
      return {
        layout: fallback(),
        source: "default",
        diagnostics: ["Saved workspace layout is not valid JSON"],
        fallbackReason: "invalid",
      };
    }
  }

  if (isRecord(candidate) && candidate.version === 0) {
    const reconciled = allowed === null
      ? { value: candidate, changed: false }
      : reconcileRawLegacyLayout(candidate, allowed);
    const legacy = validateLegacyWorkspaceLayout(reconciled.value);
    if (legacy.ok) {
      const migrated = allowed === null
        ? migrateLegacyWorkspaceLayout(legacy.value)
        : reconcileWorkspaceLayout(migrateLegacyWorkspaceLayout(legacy.value), allowed);
      const validation = validateWorkspaceLayout(migrated);
      if (validation.ok) return {
        layout: validation.value,
        source: "migrated",
        diagnostics: reconciled.changed ? ["Unavailable or duplicate panels were removed"] : [],
      };
      return {
        layout: fallback(),
        source: "default",
        diagnostics: validation.issues,
        fallbackReason: "invalid",
      };
    }
    return {
      layout: fallback(),
      source: "default",
      diagnostics: legacy.issues,
      fallbackReason: "invalid",
    };
  }

  const reconciled = allowed === null
    ? { value: candidate, changed: false }
    : reconcileRawCurrentLayout(candidate, allowed);
  const current = validateWorkspaceLayout(reconciled.value);
  if (current.ok) return {
    layout: current.value,
    source: "current",
    diagnostics: reconciled.changed ? ["Unavailable or duplicate panels were removed"] : [],
  };
  return {
    layout: fallback(),
    source: "default",
    diagnostics: current.issues,
    fallbackReason: isRecord(candidate)
      && candidate.schema === WORKSPACE_LAYOUT_SCHEMA
      && typeof candidate.version === "number"
      && candidate.version > WORKSPACE_LAYOUT_VERSION
      ? "future"
      : "invalid",
  };
}

function canonicalLayout(layout: WorkspaceLayout): WorkspaceLayout {
  const parsed = validateWorkspaceLayout(layout);
  if (!parsed.ok) throw new WorkspaceLayoutValidationError(parsed.issues);
  return parsed.value;
}

/** Deterministic JSON: fixed object-key order and meaningful tab/z order only. */
export function serializeWorkspaceLayout(layout: WorkspaceLayout): string {
  const value = canonicalLayout(layout);
  const dock = (region: DockRegionId) => ({
    panelIds: [...value.docks[region].panelIds],
    activePanelId: value.docks[region].activePanelId,
    collapsed: value.docks[region].collapsed,
    sizePx: value.docks[region].sizePx,
  });
  return JSON.stringify({
    schema: WORKSPACE_LAYOUT_SCHEMA,
    version: WORKSPACE_LAYOUT_VERSION,
    preset: value.preset,
    navigator: {
      collapsed: value.navigator.collapsed,
      widthPx: value.navigator.widthPx,
    },
    docks: {
      left: dock("left"),
      center: dock("center"),
      right: dock("right"),
      bottom: dock("bottom"),
    },
    floatingPanels: value.floatingPanels.map((panel) => ({
      panelId: panel.panelId,
      x: panel.x,
      y: panel.y,
      width: panel.width,
      height: panel.height,
      minimized: panel.minimized,
      zIndex: panel.zIndex,
    })),
    focused: value.focused === null
      ? null
      : { zone: value.focused.zone, panelId: value.focused.panelId },
  });
}

function cloneWorkspaceLayout(layout: WorkspaceLayout): WorkspaceLayout {
  return {
    schema: WORKSPACE_LAYOUT_SCHEMA,
    version: WORKSPACE_LAYOUT_VERSION,
    preset: layout.preset,
    navigator: { ...layout.navigator },
    docks: {
      left: { ...layout.docks.left, panelIds: [...layout.docks.left.panelIds] },
      center: { ...layout.docks.center, panelIds: [...layout.docks.center.panelIds] },
      right: { ...layout.docks.right, panelIds: [...layout.docks.right.panelIds] },
      bottom: { ...layout.docks.bottom, panelIds: [...layout.docks.bottom.panelIds] },
    },
    floatingPanels: layout.floatingPanels.map((panel) => ({ ...panel })),
    focused: layout.focused === null ? null : { ...layout.focused },
  };
}

function assertPanelId(panelId: string): void {
  if (!isPanelId(panelId)) {
    throw new RangeError(`Invalid workspace panel ID: ${String(panelId)}`);
  }
}

function assertFiniteNumber(value: number, name: string): void {
  if (!Number.isFinite(value)) throw new RangeError(`${name} must be finite`);
}

function clampInteger(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, Math.round(value)));
}

function panelCount(layout: WorkspaceLayout): number {
  return DOCK_REGION_IDS.reduce((count, region) => count + layout.docks[region].panelIds.length, 0)
    + layout.floatingPanels.length;
}

function firstAvailableFocus(layout: WorkspaceLayout): WorkspacePanelFocus | null {
  for (const region of ["center", "right", "bottom", "left"] as const) {
    const panelId = layout.docks[region].activePanelId;
    if (panelId !== null) return { zone: region, panelId };
  }
  const floating = layout.floatingPanels.at(-1);
  return floating === undefined ? null : { zone: "floating", panelId: floating.panelId };
}

function removePanelMutable(layout: WorkspaceLayout, panelId: string): void {
  for (const region of DOCK_REGION_IDS) {
    const dock = layout.docks[region];
    const index = dock.panelIds.indexOf(panelId);
    if (index < 0) continue;
    dock.panelIds.splice(index, 1);
    if (dock.activePanelId === panelId) dock.activePanelId = dock.panelIds[0] ?? null;
    if (dock.panelIds.length === 0 && region !== "center") dock.collapsed = true;
  }
  layout.floatingPanels = layout.floatingPanels.filter((panel) => panel.panelId !== panelId);
  if (layout.focused?.panelId === panelId) layout.focused = firstAvailableFocus(layout);
}

function normalizeFloatingStack(layout: WorkspaceLayout): void {
  layout.floatingPanels.sort((a, b) => a.zIndex - b.zIndex || a.panelId.localeCompare(b.panelId));
  layout.floatingPanels.forEach((panel, index) => { panel.zIndex = index; });
}

export function getPanelPlacement(layout: WorkspaceLayout, panelId: string): PanelPlacement | null {
  for (const region of DOCK_REGION_IDS) {
    const index = layout.docks[region].panelIds.indexOf(panelId);
    if (index >= 0) return { kind: "dock", region, index };
  }
  const floating = layout.floatingPanels.find((panel) => panel.panelId === panelId);
  if (!floating) return null;
  return {
    kind: "floating",
    bounds: { x: floating.x, y: floating.y, width: floating.width, height: floating.height },
  };
}

/** Add a new panel or atomically move an existing panel to a new placement. */
export function placePanel(
  layout: WorkspaceLayout,
  panelId: string,
  placement: PanelPlacement,
): WorkspaceLayout {
  assertPanelId(panelId);
  const alreadyPlaced = getPanelPlacement(layout, panelId) !== null;
  if (!alreadyPlaced && panelCount(layout) >= WORKSPACE_PANEL_LIMIT) {
    throw new RangeError(`Workspace cannot contain more than ${WORKSPACE_PANEL_LIMIT} panels`);
  }
  const next = cloneWorkspaceLayout(layout);
  const previousFloating = next.floatingPanels.find((panel) => panel.panelId === panelId);
  removePanelMutable(next, panelId);

  if (placement.kind === "dock") {
    if (!(DOCK_REGION_IDS as readonly string[]).includes(placement.region)) {
      throw new RangeError(`Unsupported dock region: ${String(placement.region)}`);
    }
    assertFiniteNumber(placement.index, "placement.index");
    const dock = next.docks[placement.region];
    const index = clampInteger(placement.index, 0, dock.panelIds.length);
    dock.panelIds.splice(index, 0, panelId);
    dock.activePanelId = panelId;
    dock.collapsed = false;
    next.focused = { zone: placement.region, panelId };
  } else {
    const bounds = placement.bounds ?? {};
    const rawX = bounds.x ?? previousFloating?.x ?? 80;
    const rawY = bounds.y ?? previousFloating?.y ?? 80;
    const rawWidth = bounds.width ?? previousFloating?.width ?? FLOATING_PANEL_SIZE.defaultWidth;
    const rawHeight = bounds.height ?? previousFloating?.height ?? FLOATING_PANEL_SIZE.defaultHeight;
    assertFiniteNumber(rawX, "floating x");
    assertFiniteNumber(rawY, "floating y");
    assertFiniteNumber(rawWidth, "floating width");
    assertFiniteNumber(rawHeight, "floating height");
    next.floatingPanels.push({
      panelId,
      x: clampInteger(rawX, -POSITION_LIMIT, POSITION_LIMIT),
      y: clampInteger(rawY, -POSITION_LIMIT, POSITION_LIMIT),
      width: clampInteger(rawWidth, FLOATING_PANEL_SIZE.minWidth, FLOATING_PANEL_SIZE.maxWidth),
      height: clampInteger(rawHeight, FLOATING_PANEL_SIZE.minHeight, FLOATING_PANEL_SIZE.maxHeight),
      minimized: previousFloating?.minimized ?? false,
      zIndex: next.floatingPanels.length,
    });
    next.focused = { zone: "floating", panelId };
  }
  normalizeFloatingStack(next);
  return next;
}

export const movePanel = placePanel;

export function removePanel(layout: WorkspaceLayout, panelId: string): WorkspaceLayout {
  const next = cloneWorkspaceLayout(layout);
  removePanelMutable(next, panelId);
  normalizeFloatingStack(next);
  return next;
}

export function activateDockPanel(
  layout: WorkspaceLayout,
  region: DockRegionId,
  panelId: string,
): WorkspaceLayout {
  if (!layout.docks[region].panelIds.includes(panelId)) {
    throw new RangeError(`Panel ${panelId} is not in the ${region} dock`);
  }
  const next = cloneWorkspaceLayout(layout);
  next.docks[region].activePanelId = panelId;
  next.docks[region].collapsed = false;
  next.focused = { zone: region, panelId };
  return next;
}

/** Activate an existing panel wherever it is placed. */
export function focusPanel(layout: WorkspaceLayout, panelId: string): WorkspaceLayout {
  const placement = getPanelPlacement(layout, panelId);
  if (placement === null) throw new RangeError(`Panel ${panelId} is not open`);
  if (placement.kind === "dock") return activateDockPanel(layout, placement.region, panelId);
  let next = setFloatingPanelMinimized(layout, panelId, false);
  next = bringFloatingPanelToFront(next, panelId);
  next.focused = { zone: "floating", panelId };
  return next;
}

/** Focus an open panel, or place a closed one at the end of its preferred dock. */
export function openPanel(
  layout: WorkspaceLayout,
  panelId: string,
  preferredRegion: DockRegionId = "center",
): WorkspaceLayout {
  const placement = getPanelPlacement(layout, panelId);
  return placement === null
    ? placePanel(layout, panelId, {
      kind: "dock",
      region: preferredRegion,
      index: layout.docks[preferredRegion].panelIds.length,
    })
    : focusPanel(layout, panelId);
}

/** Manuscript is the permanent safe work surface and is never closable. */
export function closePanel(layout: WorkspaceLayout, panelId: string): WorkspaceLayout {
  return panelId === "manuscript" ? cloneWorkspaceLayout(layout) : removePanel(layout, panelId);
}

export function setDockCollapsed(
  layout: WorkspaceLayout,
  region: DockRegionId,
  collapsed: boolean,
): WorkspaceLayout {
  const next = cloneWorkspaceLayout(layout);
  next.docks[region].collapsed = region === "center"
    ? false
    : next.docks[region].panelIds.length === 0 || collapsed;
  if (next.docks[region].collapsed && next.focused?.zone === region) {
    const centerPanelId = next.docks.center.activePanelId ?? "manuscript";
    next.focused = { zone: "center", panelId: centerPanelId };
  } else if (!next.docks[region].collapsed && !collapsed && region !== "center") {
    const activePanelId = next.docks[region].activePanelId;
    if (activePanelId) next.focused = { zone: region, panelId: activePanelId };
  }
  return next;
}

export function toggleDockCollapsed(layout: WorkspaceLayout, region: DockRegionId): WorkspaceLayout {
  return setDockCollapsed(layout, region, !layout.docks[region].collapsed);
}

export function resizeDock(layout: WorkspaceLayout, region: DockRegionId, sizePx: number): WorkspaceLayout {
  assertFiniteNumber(sizePx, "dock size");
  const next = cloneWorkspaceLayout(layout);
  const limits = DOCK_SIZE[region];
  next.docks[region].sizePx = clampInteger(sizePx, limits.min, limits.max);
  return next;
}

export function setNavigatorCollapsed(layout: WorkspaceLayout, collapsed: boolean): WorkspaceLayout {
  const next = cloneWorkspaceLayout(layout);
  next.navigator.collapsed = collapsed;
  return next;
}

export function resizeNavigator(layout: WorkspaceLayout, widthPx: number): WorkspaceLayout {
  assertFiniteNumber(widthPx, "navigator width");
  const next = cloneWorkspaceLayout(layout);
  next.navigator.widthPx = clampInteger(widthPx, NAVIGATOR_SIZE.min, NAVIGATOR_SIZE.max);
  return next;
}

export function setFloatingPanelMinimized(
  layout: WorkspaceLayout,
  panelId: string,
  minimized: boolean,
): WorkspaceLayout {
  const next = cloneWorkspaceLayout(layout);
  const panel = next.floatingPanels.find((entry) => entry.panelId === panelId);
  if (panel) {
    panel.minimized = minimized;
    // A minimized window must not remain the logical focus target: it is hidden
    // from both pointer and keyboard users. Prefer the permanent center surface,
    // then fall back to the first remaining workspace surface.
    if (minimized && next.focused?.panelId === panelId) {
      const centerPanelId = next.docks.center.activePanelId;
      next.focused = centerPanelId === null
        ? firstAvailableFocus(next)
        : { zone: "center", panelId: centerPanelId };
    }
  }
  return next;
}

/** Move a floating panel without changing its size, minimization, or z-order. */
export function moveFloatingPanel(
  layout: WorkspaceLayout,
  panelId: string,
  x: number,
  y: number,
): WorkspaceLayout {
  assertFiniteNumber(x, "floating x");
  assertFiniteNumber(y, "floating y");
  const next = cloneWorkspaceLayout(layout);
  const panel = next.floatingPanels.find((entry) => entry.panelId === panelId);
  if (panel) {
    panel.x = clampInteger(x, -POSITION_LIMIT, POSITION_LIMIT);
    panel.y = clampInteger(y, -POSITION_LIMIT, POSITION_LIMIT);
  }
  return next;
}

export function resizeFloatingPanel(
  layout: WorkspaceLayout,
  panelId: string,
  width: number,
  height: number,
): WorkspaceLayout {
  assertFiniteNumber(width, "floating width");
  assertFiniteNumber(height, "floating height");
  const next = cloneWorkspaceLayout(layout);
  const panel = next.floatingPanels.find((entry) => entry.panelId === panelId);
  if (panel) {
    panel.width = clampInteger(width, FLOATING_PANEL_SIZE.minWidth, FLOATING_PANEL_SIZE.maxWidth);
    panel.height = clampInteger(height, FLOATING_PANEL_SIZE.minHeight, FLOATING_PANEL_SIZE.maxHeight);
  }
  return next;
}

export function bringFloatingPanelToFront(layout: WorkspaceLayout, panelId: string): WorkspaceLayout {
  const next = cloneWorkspaceLayout(layout);
  const panel = next.floatingPanels.find((entry) => entry.panelId === panelId);
  if (!panel) return next;
  panel.zIndex = next.floatingPanels.length;
  normalizeFloatingStack(next);
  next.focused = { zone: "floating", panelId };
  return next;
}

export function setWorkspacePreset(layout: WorkspaceLayout, preset: WorkspacePreset): WorkspaceLayout {
  const next = cloneWorkspaceLayout(layout);
  next.preset = preset;
  return next;
}

export function toggleWorkspacePreset(layout: WorkspaceLayout): WorkspaceLayout {
  return setWorkspacePreset(layout, layout.preset === "focus" ? "cockpit" : "focus");
}

/** Focus is an editor-only projection; it never destroys the saved cockpit. */
export function getWorkspaceVisibility(layout: WorkspaceLayout): WorkspaceVisibility {
  if (layout.preset === "focus") {
    return {
      navigator: false,
      docks: { left: false, center: true, right: false, bottom: false },
      floatingPanelIds: [],
    };
  }
  return {
    navigator: !layout.navigator.collapsed,
    docks: {
      left: layout.docks.left.panelIds.length > 0 && !layout.docks.left.collapsed,
      center: true,
      right: layout.docks.right.panelIds.length > 0 && !layout.docks.right.collapsed,
      bottom: layout.docks.bottom.panelIds.length > 0 && !layout.docks.bottom.collapsed,
    },
    floatingPanelIds: layout.floatingPanels
      .filter((panel) => !panel.minimized)
      .map((panel) => panel.panelId),
  };
}
