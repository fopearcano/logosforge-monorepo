import { WRITING_MODES, type WritingMode } from "@logosforge/ui-contracts";
import {
  ManuscriptEditor,
  OutlinePanel,
} from "../src/components/manuscript";
import {
  DecisionRadar,
  GuidedWorkflowStepper,
  NarrativeDashboard,
} from "../src/components/projectos";
import { StoryHealthHud } from "../src/components/intelligence";
import { ProgressionsPanel } from "../src/components/bible";
import {
  STUDIO_AI_COMPANIONS_PANEL_ID,
  STUDIO_PANEL_GROUPS,
  STUDIO_PANEL_IDS,
  STUDIO_PANELS,
  STUDIO_WORKSPACE_PANEL_IDS,
  findStudioPanel,
  studioPanelGroupsForMode,
  studioPanelsForMode,
} from "../src/workspace/panelCatalog";
import {
  STUDIO_PANEL_SHORTCUTS,
  panelIdForKeyboardShortcut,
  studioPanelShortcut,
} from "../src/workspace/panelShortcuts";

let assertions = 0;
function check(condition: unknown, message: string): asserts condition {
  assertions += 1;
  if (!condition) throw new Error(message);
}

const EXPECTED_PANEL_IDS = [
  "projects",
  "dashboard",
  "manuscript",
  "notes",
  "comments",
  "dexters-room",
  "outline",
  "story-grid",
  "timeline",
  "canvas-plot",
  "series",
  "structure",
  "acts",
  "beats",
  "chapters",
  "structure-analysis",
  "format-studio",
  "health",
  "pacing",
  "balance",
  "tags",
  "continuity",
  "decision-radar",
  "guided-workflows",
  "adapt",
  "review",
  "psyke",
  "progressions",
  "characters",
  "theme-scenes",
  "graph",
  "plugins",
  "connector",
  "export",
  "ai-settings",
  "settings",
  "help",
] as const;

const RESERVED_DIRECT_SHORTCUTS = [
  ["projects", "Primary+O"],
  ["dashboard", "Primary+2"],
  ["manuscript", "Primary+1"],
  ["comments", "Primary+Shift+C"],
  ["outline", "Primary+3"],
  ["timeline", "Primary+4"],
  ["export", "Primary+E"],
  ["settings", "Primary+Comma"],
  [STUDIO_AI_COMPANIONS_PANEL_ID, "Primary+J"],
] as const;

const flattened = STUDIO_PANEL_GROUPS.flatMap((group) => group.panels);
check(
  STUDIO_PANELS.length === flattened.length
    && STUDIO_PANELS.every((panel, index) => panel === flattened[index]),
  "STUDIO_PANELS must be the canonical groups flattened without copies or omissions",
);
check(
  STUDIO_PANEL_IDS.join("\n") === EXPECTED_PANEL_IDS.join("\n"),
  "the shared catalog durable panel IDs changed unexpectedly",
);
check(
  new Set(STUDIO_PANEL_IDS).size === STUDIO_PANEL_IDS.length,
  "shared catalog panel IDs must be unique",
);
check(
  new Set(STUDIO_PANELS.map((panel) => panel.label)).size === STUDIO_PANELS.length,
  "shared catalog panel labels must be unique for deterministic navigation",
);
check(
  STUDIO_WORKSPACE_PANEL_IDS.length === STUDIO_PANEL_IDS.length + 1
    && STUDIO_WORKSPACE_PANEL_IDS.slice(0, -1).every((id, index) => id === STUDIO_PANEL_IDS[index])
    && STUDIO_WORKSPACE_PANEL_IDS.at(-1) === STUDIO_AI_COMPANIONS_PANEL_ID
    && STUDIO_WORKSPACE_PANEL_IDS.filter((id) => id === STUDIO_AI_COMPANIONS_PANEL_ID).length === 1,
  "workspace IDs must add the host-owned AI companion surface exactly once",
);
check(STUDIO_PANELS.length === 37, "the shared catalog must expose all 37 shared Pro panels");
check(
  STUDIO_PANEL_SHORTCUTS.length === 38
    && STUDIO_PANEL_SHORTCUTS.map((definition) => definition.id).join("\n")
      === STUDIO_WORKSPACE_PANEL_IDS.join("\n"),
  "canonical shortcuts must cover the 37 shared panels plus AI Companions exactly once",
);
check(
  STUDIO_PANELS.every((panel) => {
    const definition = STUDIO_PANEL_SHORTCUTS.find((candidate) => candidate.id === panel.id);
    return definition?.label === panel.label
      && definition.shortcut === panel.shortcut
      && studioPanelShortcut(panel.id) === panel.shortcut;
  }),
  "every shared panel must expose its matching canonical shortcut",
);
const aiShortcut = STUDIO_PANEL_SHORTCUTS.find(
  (definition) => definition.id === STUDIO_AI_COMPANIONS_PANEL_ID,
);
check(
  aiShortcut?.label === "AI Companions"
    && aiShortcut.shortcut === "Primary+J"
    && studioPanelShortcut(STUDIO_AI_COMPANIONS_PANEL_ID) === aiShortcut.shortcut,
  "AI Companions must complete the 38-panel shortcut catalog",
);
for (const [field, values] of [
  ["ids", STUDIO_PANEL_SHORTCUTS.map((definition) => definition.id.toLowerCase())],
  ["labels", STUDIO_PANEL_SHORTCUTS.map((definition) => definition.label.toLowerCase())],
  ["shortcuts", STUDIO_PANEL_SHORTCUTS.map((definition) => definition.shortcut.toLowerCase())],
] as const) {
  check(
    new Set(values).size === values.length,
    `canonical panel shortcut ${field} must be unique`,
  );
}
check(
  new Set(RESERVED_DIRECT_SHORTCUTS.map(([, shortcut]) => shortcut.toLowerCase())).size
    === RESERVED_DIRECT_SHORTCUTS.length,
  "reserved direct panel shortcuts must not duplicate one another",
);
check(
  RESERVED_DIRECT_SHORTCUTS.every(([id, shortcut]) => (
    STUDIO_PANEL_SHORTCUTS.some((definition) => (
      definition.id === id && definition.shortcut === shortcut
    ))
  )),
  "reserved direct panel shortcuts must retain their established assignments",
);
const reservedDirectIds = new Set(RESERVED_DIRECT_SHORTCUTS.map(([id]) => id));
check(
  STUDIO_PANEL_SHORTCUTS
    .filter((definition) => !reservedDirectIds.has(definition.id))
    .every((definition) => /^Primary\+Alt\+Shift\+[A-Z0-9]$/.test(definition.shortcut)),
  "non-reserved panel shortcuts must stay in the canonical modifier family",
);

const shortcutEvent = (overrides: Partial<KeyboardEvent> = {}) => ({
  key: "",
  code: "",
  ctrlKey: false,
  metaKey: false,
  altKey: false,
  shiftKey: false,
  repeat: false,
  defaultPrevented: false,
  isComposing: false,
  getModifierState: () => false,
  ...overrides,
});
check(
  panelIdForKeyboardShortcut(shortcutEvent({ key: "c", ctrlKey: true, shiftKey: true })) === "comments",
  "Control panel shortcuts must resolve on Windows/Linux",
);
check(
  panelIdForKeyboardShortcut(shortcutEvent({ key: "J", metaKey: true })) === STUDIO_AI_COMPANIONS_PANEL_ID,
  "Command panel shortcuts must resolve on macOS",
);
check(
  panelIdForKeyboardShortcut(shortcutEvent({ key: "%", code: "Digit5", ctrlKey: true, altKey: true, shiftKey: true })) === "guided-workflows",
  "shifted digit shortcuts must match their physical Digit code",
);
check(
  panelIdForKeyboardShortcut(shortcutEvent({ key: "˜", code: "KeyN", metaKey: true, altKey: true, shiftKey: true })) === "notes",
  "Option-modified macOS letters must match their physical Key code",
);
check(
  panelIdForKeyboardShortcut(shortcutEvent({ key: "N", ctrlKey: true, altKey: true, shiftKey: true, getModifierState: (key) => key === "AltGraph" })) === null,
  "AltGraph text entry must never trigger panel navigation",
);
check(
  panelIdForKeyboardShortcut(shortcutEvent({ key: "n", ctrlKey: true, altKey: true, shiftKey: true, repeat: true })) === null,
  "held panel shortcuts must not repeat navigation",
);
check(
  panelIdForKeyboardShortcut(shortcutEvent({ key: "c", ctrlKey: true, altKey: true, shiftKey: false })) === null,
  "panel shortcut matching must require exact modifiers",
);

check(findStudioPanel("manuscript")?.label === "Manuscript", "catalog lookup by durable id failed");
check(findStudioPanel("Manuscript")?.id === "manuscript", "catalog lookup by display label failed");
check(findStudioPanel("missing-panel") === undefined, "unknown catalog values must not resolve");

check(findStudioPanel("manuscript")?.node.type === ManuscriptEditor, "manuscript catalog node must be the real editor");
check(findStudioPanel("dashboard")?.node.type === NarrativeDashboard, "dashboard catalog node must be the real dashboard");
check(findStudioPanel("outline")?.node.type === OutlinePanel, "outline catalog node must be the real outline panel");
check(findStudioPanel("decision-radar")?.node.type === DecisionRadar, "decision-radar catalog node must be the real panel");
check(findStudioPanel("guided-workflows")?.node.type === GuidedWorkflowStepper, "guided-workflows catalog node must be the live workflow panel");
check(findStudioPanel("health")?.node.type === StoryHealthHud, "health catalog node must be the real story-health panel");
check(findStudioPanel("progressions")?.node.type === ProgressionsPanel, "progressions catalog node must be the real Bible panel");

check(findStudioPanel("outline")?.preferredRegion === "bottom", "Outline must retain its preferred bottom dock");
check(findStudioPanel("health")?.preferredRegion === "bottom", "Health must retain its preferred bottom dock");
check(findStudioPanel("progressions")?.preferredRegion === "bottom", "Progressions must prefer the bottom dock");
check(findStudioPanel("decision-radar")?.preferredRegion === "right", "Decision Radar must retain its preferred right dock");
check(findStudioPanel("guided-workflows")?.preferredRegion === "right", "Guided Workflows must prefer the right dock");

function idsFor(mode: WritingMode): Set<string> {
  return new Set(studioPanelsForMode(mode).map((panel) => panel.id));
}

for (const mode of WRITING_MODES) {
  const ids = idsFor(mode);
  check(ids.has("manuscript"), `${mode} must expose the manuscript`);
  check(ids.has("dashboard"), `${mode} must expose the dashboard`);
  check(ids.has("outline"), `${mode} must expose the outline`);
  check(ids.has("psyke"), `${mode} must expose PSYKE`);
  check(ids.has("progressions"), `${mode} must expose Progressions`);
  check(ids.has("chapters") === (mode === "novel"), `${mode} has the wrong Chapters mode gate`);
  check(ids.has("series") === (mode === "series"), `${mode} has the wrong Series mode gate`);

  const groups = studioPanelGroupsForMode(mode);
  check(groups.length > 0, `${mode} must retain at least one panel group`);
  check(groups.every((group) => group.panels.length > 0), `${mode} must not expose empty panel groups`);
  check(
    groups.flatMap((group) => group.panels).map((panel) => panel.id).join("\n")
      === studioPanelsForMode(mode).map((panel) => panel.id).join("\n"),
    `${mode} group and flat catalog projections must agree`,
  );
}

console.log(`${assertions} shared Studio panel catalog assertions passed.`);
