/** Focused pure tests for the persisted Studio workspace layout model. */

import {
  DOCK_SIZE,
  NAVIGATOR_SIZE,
  WorkspaceLayoutValidationError,
  activateDockPanel,
  bringFloatingPanelToFront,
  closePanel,
  createDefaultWorkspaceLayout,
  getPanelPlacement,
  getWorkspaceVisibility,
  focusPanel,
  moveFloatingPanel,
  movePanel,
  openPanel,
  reconcileWorkspaceLayout,
  resizeDock,
  resizeFloatingPanel,
  resizeNavigator,
  restoreWorkspaceLayout,
  resetWorkspaceLayout,
  serializeWorkspaceLayout,
  setDockCollapsed,
  setFloatingPanelMinimized,
  setFloatingPanelBounds,
  setNavigatorCollapsed,
  setWorkspacePreset,
  toggleWorkspacePreset,
  validateWorkspaceLayout,
  type LegacyWorkspaceLayoutV0,
  type WorkspaceLayout,
} from "../src/workspace/layoutModel";

let passed = 0;
const failures: string[] = [];

function check(label: string, condition: boolean): void {
  if (condition) passed += 1;
  else failures.push(label);
}

function jsonClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

{
  const layout = createDefaultWorkspaceLayout();
  const validation = validateWorkspaceLayout(layout);
  check("default layout validates", validation.ok);
  check("default is Cockpit", layout.preset === "cockpit");
  check("default center opens manuscript", layout.docks.center.activePanelId === "manuscript");
  check("default center includes the dashboard", layout.docks.center.panelIds.join(",") === "manuscript,dashboard");
  check("default right dock opens AI Companions", layout.docks.right.activePanelId === "ai-companions");
  check("default bottom dock is visible", getWorkspaceVisibility(layout).docks.bottom);
}

{
  const withExtra = jsonClone(createDefaultWorkspaceLayout()) as WorkspaceLayout & { surprise?: boolean };
  withExtra.surprise = true;
  const result = validateWorkspaceLayout(withExtra);
  check("unknown root key is rejected", !result.ok && result.issues.some((issue) => issue.includes("unsupported keys")));

  const duplicate = jsonClone(createDefaultWorkspaceLayout());
  duplicate.docks.bottom.panelIds.push("manuscript");
  const duplicateResult = validateWorkspaceLayout(duplicate);
  check("panel cannot occupy two docks", !duplicateResult.ok && duplicateResult.issues.some((issue) => issue.includes("more than once")));

  const nonInteger = jsonClone(createDefaultWorkspaceLayout());
  nonInteger.docks.right.sizePx = 300.5;
  check("fractional persisted sizes are rejected", !validateWorkspaceLayout(nonInteger).ok);

  const staleActive = jsonClone(createDefaultWorkspaceLayout());
  staleActive.docks.bottom.activePanelId = "missing";
  check("active tab must belong to its dock", !validateWorkspaceLayout(staleActive).ok);
}

{
  const legacy: LegacyWorkspaceLayoutV0 = {
    version: 0,
    mode: "focus",
    navigatorCollapsed: true,
    navigatorWidthPx: 200,
    rightDockWidthPx: 500,
    bottomDockHeightPx: 260,
    centerPanelIds: ["manuscript", "notes"],
    rightPanelIds: ["logos"],
    bottomPanelIds: ["timeline"],
  };
  const restored = restoreWorkspaceLayout(legacy);
  check("v0 layout migrates", restored.source === "migrated");
  check("migration preserves Focus preference", restored.layout.preset === "focus");
  check("migration preserves panel order", restored.layout.docks.center.panelIds.join(",") === "manuscript,notes");
  check("migration preserves dock dimensions", restored.layout.docks.right.sizePx === 500 && restored.layout.docks.bottom.sizePx === 260);

  const future = restoreWorkspaceLayout({ ...createDefaultWorkspaceLayout(), version: 99 });
  check("future schema safely falls back", future.source === "default" && future.fallbackReason === "future" && future.diagnostics.length > 0);
  check("fallback is a usable default", validateWorkspaceLayout(future.layout).ok);

  const corruptJson = restoreWorkspaceLayout("{broken");
  check("corrupt JSON safely falls back", corruptJson.source === "default" && corruptJson.fallbackReason === "invalid" && corruptJson.diagnostics.length === 1);

  const versionOne = JSON.parse(serializeWorkspaceLayout(movePanel(
    createDefaultWorkspaceLayout(),
    "outline",
    { kind: "floating", bounds: { x: 14, y: 28, width: 420, height: 300 } },
  ))) as Record<string, unknown> & { floatingPanels: Array<Record<string, unknown>> };
  versionOne.version = 1;
  delete versionOne.floatingPanels[0]?.coordinateSpace;
  const versionOneRestored = restoreWorkspaceLayout(versionOne);
  check(
    "v1 workspace-relative floats migrate explicitly",
    versionOneRestored.source === "migrated"
      && versionOneRestored.layout.floatingPanels[0]?.coordinateSpace === "workspace",
  );
}

{
  const initial = createDefaultWorkspaceLayout();
  const snapshot = serializeWorkspaceLayout(initial);
  const moved = movePanel(initial, "outline", { kind: "dock", region: "right", index: 1 });
  check("movement does not mutate its source", serializeWorkspaceLayout(initial) === snapshot);
  check("panel leaves its old dock", !moved.docks.bottom.panelIds.includes("outline"));
  check("panel arrives at requested tab index", moved.docks.right.panelIds[1] === "outline");
  check("moved dock activates the panel", moved.docks.right.activePanelId === "outline");
  check("moved panel becomes workspace focus", moved.focused?.panelId === "outline" && moved.focused.zone === "right");
  check("placement query reports the destination", JSON.stringify(getPanelPlacement(moved, "outline")) === JSON.stringify({ kind: "dock", region: "right", index: 1 }));

  const reordered = movePanel(moved, "outline", { kind: "dock", region: "right", index: 99 });
  check("same-dock move clamps to the end", reordered.docks.right.panelIds.at(-1) === "outline");
}

{
  let layout = createDefaultWorkspaceLayout();
  layout = movePanel(layout, "ai-companions", { kind: "floating", bounds: { x: 17, y: 29, width: 700, height: 510 } });
  check("tear-off removes dock tab", !layout.docks.right.panelIds.includes("ai-companions"));
  check("tear-off preserves requested geometry", layout.floatingPanels[0]?.x === 17 && layout.floatingPanels[0]?.width === 700);
  check("new tear-offs use workspace coordinates", layout.floatingPanels[0]?.coordinateSpace === "workspace");

  layout = setFloatingPanelBounds(
    layout,
    "ai-companions",
    { x: -1420, y: 80, width: 820, height: 620 },
    "screen",
  );
  check(
    "native bounds atomically switch to screen coordinates",
    layout.floatingPanels[0]?.coordinateSpace === "screen"
      && layout.floatingPanels[0]?.x === -1420
      && layout.floatingPanels[0]?.width === 820,
  );
  layout = moveFloatingPanel(layout, "ai-companions", 24, 36);
  check(
    "browser movement converts persisted screen coordinates back to workspace coordinates",
    layout.floatingPanels[0]?.coordinateSpace === "workspace"
      && layout.floatingPanels[0]?.x === 24
      && layout.floatingPanels[0]?.y === 36,
  );

  layout = movePanel(layout, "outline", { kind: "floating" });
  layout = bringFloatingPanelToFront(layout, "ai-companions");
  check("bring-to-front produces contiguous stacking", layout.floatingPanels.map((panel) => panel.zIndex).join(",") === "0,1");
  check("bring-to-front moves requested panel last", layout.floatingPanels.at(-1)?.panelId === "ai-companions");

  layout = resizeFloatingPanel(layout, "ai-companions", 1, 10_000);
  const ai = layout.floatingPanels.find((panel) => panel.panelId === "ai-companions");
  check("floating resize clamps both dimensions", ai?.width === 240 && ai.height === 1_200);

  layout = setFloatingPanelMinimized(layout, "ai-companions", true);
  check("minimized floating panel is hidden in Cockpit", !getWorkspaceVisibility(layout).floatingPanelIds.includes("ai-companions"));
}

{
  let layout = createDefaultWorkspaceLayout();
  layout = movePanel(layout, "ai-companions", {
    kind: "floating",
    bounds: { x: 111, y: 75, width: 530, height: 410 },
  });
  layout = movePanel(layout, "outline", {
    kind: "floating",
    bounds: { x: -42, y: 93, width: 360, height: 280 },
  });
  layout = setFloatingPanelMinimized(layout, "outline", true);
  layout = bringFloatingPanelToFront(layout, "ai-companions");

  const source = serializeWorkspaceLayout(layout);
  const outlineBefore = layout.floatingPanels.find((panel) => panel.panelId === "outline");
  const moved = moveFloatingPanel(layout, "outline", 999_999, -999_999);
  const outlineAfter = moved.floatingPanels.find((panel) => panel.panelId === "outline");
  check("floating move does not mutate its source", serializeWorkspaceLayout(layout) === source);
  check(
    "floating move clamps persisted coordinates",
    outlineAfter?.x === 100_000 && outlineAfter.y === -100_000,
  );
  check(
    "floating move preserves size, minimized state, and stack ownership",
    outlineAfter?.width === outlineBefore?.width
      && outlineAfter?.height === outlineBefore?.height
      && outlineAfter?.minimized === true
      && outlineAfter?.zIndex === outlineBefore?.zIndex,
  );
  check(
    "floating move preserves the current focused panel",
    moved.focused?.zone === "floating" && moved.focused.panelId === "ai-companions",
  );
}

{
  let layout = createDefaultWorkspaceLayout();
  layout = movePanel(layout, "ai-companions", {
    kind: "floating",
    bounds: { x: 40, y: 48, width: 540, height: 420 },
  });
  layout = movePanel(layout, "outline", {
    kind: "floating",
    bounds: { x: 92, y: 106, width: 400, height: 300 },
  });
  layout = focusPanel(layout, "ai-companions");
  layout = setFloatingPanelMinimized(layout, "ai-companions", true);
  check(
    "minimizing the focused float transfers focus to the visible center fallback",
    layout.focused?.zone === "center"
      && layout.focused.panelId === layout.docks.center.activePanelId,
  );
  check(
    "minimizing a float preserves its persisted placement",
    layout.floatingPanels.some((panel) => panel.panelId === "ai-companions" && panel.minimized),
  );

  const restored = focusPanel(layout, "ai-companions");
  const restoredAi = restored.floatingPanels.find((panel) => panel.panelId === "ai-companions");
  check(
    "focusing a minimized float restores and focuses it",
    restoredAi?.minimized === false
      && restored.focused?.zone === "floating"
      && restored.focused.panelId === "ai-companions",
  );
  check(
    "focusing a restored float raises it above its siblings",
    restoredAi?.zIndex === restored.floatingPanels.length - 1
      && restored.floatingPanels.at(-1)?.panelId === "ai-companions",
  );
}

{
  const initial = createDefaultWorkspaceLayout();
  const collapsed = setDockCollapsed(initial, "right", true);
  check("dock can collapse", collapsed.docks.right.collapsed);
  check(
    "collapsing the focused dock returns logical focus to the active center panel",
    collapsed.focused?.zone === "center"
      && collapsed.focused.panelId === initial.docks.center.activePanelId,
  );
  check(
    "collapsing a dock preserves its active panel for expansion",
    collapsed.docks.right.activePanelId === initial.docks.right.activePanelId,
  );
  const expanded = setDockCollapsed(collapsed, "right", false);
  check(
    "expanding a dock restores logical focus to its active panel",
    expanded.focused?.zone === "right"
      && expanded.focused.panelId === expanded.docks.right.activePanelId,
  );
  check("center refuses collapse", !setDockCollapsed(initial, "center", true).docks.center.collapsed);

  const wide = resizeDock(initial, "right", 100_000);
  const shallow = resizeDock(initial, "bottom", 1);
  check("side resize clamps to maximum", wide.docks.right.sizePx === DOCK_SIZE.right.max);
  check("bottom resize clamps to minimum", shallow.docks.bottom.sizePx === DOCK_SIZE.bottom.min);

  const navWide = resizeNavigator(initial, 50_000);
  const navClosed = setNavigatorCollapsed(navWide, true);
  check("navigator resize clamps", navWide.navigator.widthPx === NAVIGATOR_SIZE.max);
  check("navigator collapse hides it", !getWorkspaceVisibility(navClosed).navigator);
}

{
  let layout = createDefaultWorkspaceLayout();
  layout = movePanel(layout, "dashboard", { kind: "dock", region: "left", index: 0 });
  layout = movePanel(layout, "decision-radar", { kind: "dock", region: "left", index: 1 });
  layout = resizeDock(layout, "left", 421);
  check(
    "left dock owns moved panels exactly once",
    layout.docks.left.panelIds.join(",") === "dashboard,decision-radar"
      && !layout.docks.center.panelIds.includes("dashboard")
      && !layout.docks.right.panelIds.includes("decision-radar"),
  );
  check("left dock retains its independent width", layout.docks.left.sizePx === 421);

  layout = setDockCollapsed(layout, "left", true);
  check(
    "collapsing the focused left dock preserves ownership and falls back to center focus",
    layout.docks.left.collapsed
      && layout.docks.left.panelIds.join(",") === "dashboard,decision-radar"
      && layout.focused?.zone === "center",
  );
  layout = setDockCollapsed(layout, "left", false);
  check(
    "expanding the left dock restores its active-panel focus",
    !layout.docks.left.collapsed
      && layout.focused?.zone === "left"
      && layout.focused.panelId === layout.docks.left.activePanelId,
  );

  const tooWide = resizeDock(layout, "left", 100_000);
  check("left resize clamps to its maximum", tooWide.docks.left.sizePx === DOCK_SIZE.left.max);
  const movedAway = movePanel(layout, "dashboard", { kind: "dock", region: "bottom", index: 0 });
  check(
    "moving out of the left dock transfers unique panel ownership",
    !movedAway.docks.left.panelIds.includes("dashboard")
      && movedAway.docks.bottom.panelIds.filter((panelId) => panelId === "dashboard").length === 1
      && validateWorkspaceLayout(movedAway).ok,
  );
}

{
  const cockpit = createDefaultWorkspaceLayout();
  const rightState = serializeWorkspaceLayout(setDockCollapsed(cockpit, "right", true));
  let layout = setDockCollapsed(cockpit, "right", true);
  layout = setWorkspacePreset(layout, "focus");
  const focusVisibility = getWorkspaceVisibility(layout);
  check("Focus is editor-only", focusVisibility.docks.center && !focusVisibility.navigator && !focusVisibility.docks.right && !focusVisibility.docks.bottom);

  layout = toggleWorkspacePreset(layout);
  check("toggle returns to Cockpit", layout.preset === "cockpit");
  check("Focus round trip retains dock preference", serializeWorkspaceLayout(layout) === rightState);
}

{
  let rich = createDefaultWorkspaceLayout();
  rich = movePanel(rich, "dashboard", { kind: "dock", region: "left", index: 0 });
  rich = resizeDock(rich, "left", 437);
  rich = movePanel(rich, "ai-companions", {
    kind: "floating",
    bounds: { x: 137, y: 81, width: 618, height: 454 },
  });
  rich = movePanel(rich, "outline", {
    kind: "floating",
    bounds: { x: -23, y: 211, width: 377, height: 266 },
  });
  rich = setFloatingPanelMinimized(rich, "outline", true);
  rich = focusPanel(rich, "ai-companions");

  const encoded = serializeWorkspaceLayout(rich);
  const restored = restoreWorkspaceLayout(encoded);
  const ai = rich.floatingPanels.find((panel) => panel.panelId === "ai-companions");
  const outline = rich.floatingPanels.find((panel) => panel.panelId === "outline");
  check(
    "rich left-and-floating layout records distinct geometry, stack, minimized, and focus state",
    rich.docks.left.panelIds.join(",") === "dashboard"
      && rich.docks.left.sizePx === 437
      && ai?.x === 137
      && ai.y === 81
      && ai.width === 618
      && ai.height === 454
      && outline?.x === -23
      && outline.y === 211
      && outline.minimized
      && outline.zIndex !== ai.zIndex
      && rich.focused?.zone === "floating"
      && rich.focused.panelId === "ai-companions",
  );
  check(
    "rich left-and-floating layout restores byte-for-byte",
    restored.source === "current" && serializeWorkspaceLayout(restored.layout) === encoded,
  );

  const focusProjection = setWorkspacePreset(restored.layout, "focus");
  const focusVisibility = getWorkspaceVisibility(focusProjection);
  check(
    "Focus hides rich cockpit surfaces without deleting them",
    !focusVisibility.docks.left
      && focusVisibility.floatingPanelIds.length === 0
      && JSON.stringify(focusProjection.docks) === JSON.stringify(restored.layout.docks)
      && JSON.stringify(focusProjection.floatingPanels) === JSON.stringify(restored.layout.floatingPanels)
      && JSON.stringify(focusProjection.focused) === JSON.stringify(restored.layout.focused),
  );
  const cockpitProjection = toggleWorkspacePreset(focusProjection);
  check(
    "Focus-to-Cockpit restores every rich layout byte",
    serializeWorkspaceLayout(cockpitProjection) === encoded,
  );
}

{
  const a = createDefaultWorkspaceLayout();
  const b = {
    focused: a.focused === null ? null : { panelId: a.focused.panelId, zone: a.focused.zone },
    floatingPanels: [],
    docks: {
      bottom: { ...a.docks.bottom, panelIds: [...a.docks.bottom.panelIds] },
      right: { ...a.docks.right, panelIds: [...a.docks.right.panelIds] },
      center: { ...a.docks.center, panelIds: [...a.docks.center.panelIds] },
      left: { ...a.docks.left, panelIds: [...a.docks.left.panelIds] },
    },
    navigator: { widthPx: a.navigator.widthPx, collapsed: a.navigator.collapsed },
    preset: a.preset,
    version: a.version,
    schema: a.schema,
  } as WorkspaceLayout;
  const encoded = serializeWorkspaceLayout(a);
  check("serialization ignores object insertion order", encoded === serializeWorkspaceLayout(b));
  const roundTrip = restoreWorkspaceLayout(encoded);
  check("serialized layout round-trips", roundTrip.source === "current" && serializeWorkspaceLayout(roundTrip.layout) === encoded);

  const invalid = jsonClone(a);
  invalid.navigator.widthPx = -1;
  let threw = false;
  try {
    serializeWorkspaceLayout(invalid);
  } catch (error) {
    threw = error instanceof WorkspaceLayoutValidationError;
  }
  check("invalid state cannot be serialized", threw);
}

{
  const initial = createDefaultWorkspaceLayout();
  const activated = activateDockPanel(initial, "right", "decision-radar");
  check("dock activation changes only active tab", activated.docks.right.activePanelId === "decision-radar" && initial.docks.right.activePanelId === "ai-companions");
  check("dock activation updates focused zone", activated.focused?.zone === "right" && activated.focused.panelId === "decision-radar");
}

{
  const dirty = createDefaultWorkspaceLayout();
  dirty.docks.right.panelIds.push("dashboard", "retired-plugin");
  dirty.docks.right.activePanelId = "retired-plugin";
  const allowed = ["manuscript", "dashboard", "ai-companions", "decision-radar", "outline", "health"];
  const restored = restoreWorkspaceLayout(dirty, allowed);
  check("allowed-ID restore drops duplicate panels", restored.layout.docks.right.panelIds.filter((id) => id === "dashboard").length === 0);
  check("allowed-ID restore drops unavailable panels", !restored.layout.docks.right.panelIds.includes("retired-plugin"));
  check("allowed-ID restore repairs a valid active tab", restored.layout.docks.right.activePanelId === "ai-companions");
  check("allowed-ID restore reports reconciliation", restored.source === "current" && restored.diagnostics.length === 1);

  let floatedManuscript = movePanel(createDefaultWorkspaceLayout(), "manuscript", {
    kind: "floating",
    bounds: { x: 91, y: 73, width: 812, height: 618 },
  });
  floatedManuscript = reconcileWorkspaceLayout(floatedManuscript, allowed);
  const floatedPlacement = getPanelPlacement(floatedManuscript, "manuscript");
  const floatedBounds = floatedPlacement?.kind === "floating" ? floatedPlacement.bounds : undefined;
  check(
    "reconciliation preserves a deliberately floated manuscript",
    floatedPlacement?.kind === "floating"
      && floatedBounds?.x === 91
      && floatedBounds?.y === 73
      && floatedBounds?.width === 812
      && floatedBounds?.height === 618,
  );
  const floatedEncoded = serializeWorkspaceLayout(floatedManuscript);
  const floatedRestored = restoreWorkspaceLayout(floatedEncoded, allowed);
  check(
    "a floated manuscript survives serialized restore with exact placement",
    floatedRestored.source === "current"
      && serializeWorkspaceLayout(floatedRestored.layout) === floatedEncoded,
  );
  const closedFloatedManuscript = closePanel(floatedRestored.layout, "manuscript");
  check(
    "closing the permanent manuscript is a no-op at its current floating placement",
    serializeWorkspaceLayout(closedFloatedManuscript) === floatedEncoded
      && getPanelPlacement(closedFloatedManuscript, "manuscript")?.kind === "floating",
  );

  const withoutManuscript = createDefaultWorkspaceLayout();
  withoutManuscript.docks.center.panelIds = ["dashboard"];
  withoutManuscript.docks.center.activePanelId = "dashboard";
  withoutManuscript.focused = { zone: "center", panelId: "dashboard" };
  const reconciled = reconcileWorkspaceLayout(withoutManuscript, allowed);
  check(
    "reconciliation repairs a genuinely missing manuscript into center",
    reconciled.docks.center.panelIds[0] === "manuscript"
      && getPanelPlacement(reconciled, "manuscript")?.kind === "dock",
  );

  let opened = closePanel(reconciled, "dashboard");
  check("close removes a non-permanent panel", getPanelPlacement(opened, "dashboard") === null);
  opened = closePanel(opened, "manuscript");
  check("close preserves permanent manuscript", getPanelPlacement(opened, "manuscript")?.kind === "dock");
  opened = openPanel(opened, "dashboard", "center");
  opened = focusPanel(opened, "dashboard");
  check("open/focus restores panel and focus", opened.focused?.panelId === "dashboard" && opened.docks.center.activePanelId === "dashboard");

  const reset = resetWorkspaceLayout(["manuscript", "ai-companions"]);
  check("registry-aware reset retains composite AI Companions", reset.docks.right.panelIds.join(",") === "ai-companions");
  check("registry-aware reset omits unavailable defaults", !reset.docks.center.panelIds.includes("dashboard") && reset.docks.bottom.panelIds.length === 0);
}

if (failures.length > 0) {
  console.error(`${failures.length} workspace layout test(s) failed:`);
  failures.forEach((failure) => console.error(` - ${failure}`));
  process.exitCode = 1;
} else {
  console.log(`${passed} workspace layout assertions passed.`);
}
