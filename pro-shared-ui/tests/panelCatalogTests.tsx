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

check(findStudioPanel("manuscript")?.label === "Manuscript", "catalog lookup by durable id failed");
check(findStudioPanel("Manuscript")?.id === "manuscript", "catalog lookup by display label failed");
check(findStudioPanel("missing-panel") === undefined, "unknown catalog values must not resolve");

check(findStudioPanel("manuscript")?.node.type === ManuscriptEditor, "manuscript catalog node must be the real editor");
check(findStudioPanel("dashboard")?.node.type === NarrativeDashboard, "dashboard catalog node must be the real dashboard");
check(findStudioPanel("outline")?.node.type === OutlinePanel, "outline catalog node must be the real outline panel");
check(findStudioPanel("decision-radar")?.node.type === DecisionRadar, "decision-radar catalog node must be the real panel");
check(findStudioPanel("guided-workflows")?.node.type === GuidedWorkflowStepper, "guided-workflows catalog node must be the live workflow panel");
check(findStudioPanel("health")?.node.type === StoryHealthHud, "health catalog node must be the real story-health panel");

check(findStudioPanel("outline")?.preferredRegion === "bottom", "Outline must retain its preferred bottom dock");
check(findStudioPanel("health")?.preferredRegion === "bottom", "Health must retain its preferred bottom dock");
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
