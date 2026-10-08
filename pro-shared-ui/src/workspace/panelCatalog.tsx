import type { ReactElement } from "react";
import type { WritingMode } from "@logosforge/ui-contracts";
import {
  ActsView,
  BeatsView,
  ChaptersView,
  CommentsPanel,
  ManuscriptEditor,
  NotesPanel,
  OutlinePanel,
  StoryGrid,
  StructurePanel,
  TagsView,
} from "../components/manuscript";
import {
  AdaptView,
  AiSettingsPanel,
  ConnectorPanel,
  ContinuityPanel,
  DecisionRadar,
  GuidedWorkflowStepper,
  NarrativeDashboard,
  PluginsPanel,
  ProjectsPanel,
  ReviewDashboard,
  SeriesNavigator,
} from "../components/projectos";
import {
  CharacterBalance,
  CoverageAnalysis,
  PacingInsights,
  StoryHealthHud,
} from "../components/intelligence";
import { FormatStructure } from "../components/aipanels";
import { CrossCutting, ExportDialog, VoiceHud } from "../components/formatpanels";
import { CharacterLinks, PsykeBible, ThemeScenes } from "../components/bible";
import { CanvasPlot, KnowledgeGraph, TimelinePanel } from "../components/spatialcanvas";
import { HelpPanel } from "../components/help";
import type { DockRegionId } from "./layoutModel";
import { studioPanelShortcut } from "./panelShortcuts";

/**
 * Stable ID reserved for the host-composed AI companions surface.
 *
 * The shared catalog deliberately does not provide its node: desktop and web
 * hosts own the companion container and its host-level open/tab preferences.
 */
export const STUDIO_AI_COMPANIONS_PANEL_ID = "ai-companions" as const;

/** A platform-neutral panel that every Pro host can compose into its workspace. */
export interface StudioPanelCatalogEntry {
  /** Durable workspace-layout key. Persist this value, never the display label. */
  readonly id: string;
  readonly label: string;
  /** Canonical global shortcut used by every Pro host and the Help guide. */
  readonly shortcut: string;
  readonly node: ReactElement;
  readonly preferredRegion?: DockRegionId;
  /** Omitted means the panel is available in every writing mode. */
  readonly modes?: readonly WritingMode[];
}

export interface StudioPanelGroup {
  /** Empty groups are intentionally rendered without a heading by host rails. */
  readonly group: string;
  readonly panels: readonly StudioPanelCatalogEntry[];
}

function panel(
  entry: Omit<StudioPanelCatalogEntry, "shortcut">,
): StudioPanelCatalogEntry {
  const shortcut = studioPanelShortcut(entry.id);
  if (!shortcut) throw new Error(`Missing keyboard shortcut for Studio panel: ${entry.id}`);
  return { ...entry, shortcut };
}

/**
 * Canonical shared Studio panel catalog.
 *
 * Hosts own project/bootstrap lifecycle and special host surfaces, while this
 * module owns the common panel IDs, labels, grouping, mode gates, preferred
 * placement, and component identity. Keeping those facts here prevents desktop
 * and browser workspaces from silently drifting apart.
 */
export const STUDIO_PANEL_GROUPS: readonly StudioPanelGroup[] = [
  {
    group: "",
    panels: [
      panel({ id: "projects", label: "Projects", node: <ProjectsPanel /> }),
      panel({ id: "dashboard", label: "Dashboard", node: <NarrativeDashboard /> }),
      panel({ id: "manuscript", label: "Manuscript", node: <ManuscriptEditor /> }),
      panel({ id: "notes", label: "Notes", node: <NotesPanel /> }),
      panel({ id: "comments", label: "Comments", node: <CommentsPanel /> }),
      panel({ id: "dexters-room", label: "Dexter's Room", node: <VoiceHud /> }),
    ],
  },
  {
    group: "PLAN",
    panels: [
      panel({ id: "outline", label: "Outline", node: <OutlinePanel />, preferredRegion: "bottom" }),
      panel({ id: "story-grid", label: "Story Grid", node: <StoryGrid /> }),
      panel({ id: "timeline", label: "Timeline", node: <TimelinePanel /> }),
      panel({ id: "canvas-plot", label: "Canvas Plot", node: <CanvasPlot /> }),
      panel({ id: "series", label: "Series", node: <SeriesNavigator />, modes: ["series"] }),
    ],
  },
  {
    group: "STRUCTURE",
    panels: [
      panel({ id: "structure", label: "Structure", node: <StructurePanel /> }),
      panel({ id: "acts", label: "Acts", node: <ActsView /> }),
      panel({ id: "beats", label: "Beats", node: <BeatsView /> }),
      panel({ id: "chapters", label: "Chapters", node: <ChaptersView />, modes: ["novel"] }),
      panel({ id: "structure-analysis", label: "Structure Analysis", node: <CoverageAnalysis /> }),
      panel({ id: "format-studio", label: "Format Studio", node: <FormatStructure /> }),
    ],
  },
  {
    group: "ANALYTICS",
    panels: [
      panel({ id: "health", label: "Health", node: <StoryHealthHud />, preferredRegion: "bottom" }),
      panel({ id: "pacing", label: "Pacing", node: <PacingInsights /> }),
      panel({ id: "balance", label: "Balance", node: <CharacterBalance /> }),
      panel({ id: "tags", label: "Tags", node: <TagsView /> }),
      panel({ id: "continuity", label: "Continuity", node: <ContinuityPanel /> }),
      panel({ id: "decision-radar", label: "Decision Radar", node: <DecisionRadar />, preferredRegion: "right" }),
      panel({ id: "guided-workflows", label: "Guided Workflows", node: <GuidedWorkflowStepper />, preferredRegion: "right" }),
      panel({ id: "adapt", label: "Adapt", node: <AdaptView /> }),
      panel({ id: "review", label: "Review", node: <ReviewDashboard /> }),
    ],
  },
  {
    group: "BIBLE",
    panels: [
      panel({ id: "psyke", label: "PSYKE", node: <PsykeBible /> }),
      panel({ id: "characters", label: "Characters", node: <CharacterLinks /> }),
      panel({ id: "theme-scenes", label: "Theme Scenes", node: <ThemeScenes /> }),
      panel({ id: "graph", label: "Graph", node: <KnowledgeGraph /> }),
    ],
  },
  {
    group: "",
    panels: [
      panel({ id: "plugins", label: "Plugins", node: <PluginsPanel /> }),
      panel({ id: "connector", label: "Connector", node: <ConnectorPanel /> }),
      panel({ id: "export", label: "Export", node: <ExportDialog /> }),
      panel({ id: "ai-settings", label: "AI Settings", node: <AiSettingsPanel /> }),
      panel({ id: "settings", label: "Settings", node: <CrossCutting /> }),
      panel({ id: "help", label: "Help", node: <HelpPanel /> }),
    ],
  },
];

export const STUDIO_PANELS: readonly StudioPanelCatalogEntry[] =
  STUDIO_PANEL_GROUPS.flatMap((group) => group.panels);

/** Shared panel IDs only; excludes the host-owned AI companion surface. */
export const STUDIO_PANEL_IDS: readonly string[] = STUDIO_PANELS.map((panel) => panel.id);

/** Every durable ID accepted by the standard Pro workspace layout. */
export const STUDIO_WORKSPACE_PANEL_IDS: readonly string[] = [
  ...STUDIO_PANEL_IDS,
  STUDIO_AI_COMPANIONS_PANEL_ID,
];

export function findStudioPanel(value: string): StudioPanelCatalogEntry | undefined {
  return STUDIO_PANELS.find((panel) => panel.id === value || panel.label === value);
}

export function studioPanelGroupsForMode(mode: WritingMode): readonly StudioPanelGroup[] {
  return STUDIO_PANEL_GROUPS
    .map((group) => ({
      ...group,
      panels: group.panels.filter((panel) => !panel.modes || panel.modes.includes(mode)),
    }))
    .filter((group) => group.panels.length > 0);
}

export function studioPanelsForMode(mode: WritingMode): readonly StudioPanelCatalogEntry[] {
  return studioPanelGroupsForMode(mode).flatMap((group) => group.panels);
}
