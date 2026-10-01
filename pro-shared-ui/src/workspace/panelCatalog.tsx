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
      { id: "projects", label: "Projects", node: <ProjectsPanel /> },
      { id: "dashboard", label: "Dashboard", node: <NarrativeDashboard /> },
      { id: "manuscript", label: "Manuscript", node: <ManuscriptEditor /> },
      { id: "notes", label: "Notes", node: <NotesPanel /> },
      { id: "comments", label: "Comments", node: <CommentsPanel /> },
      { id: "dexters-room", label: "Dexter's Room", node: <VoiceHud /> },
    ],
  },
  {
    group: "PLAN",
    panels: [
      { id: "outline", label: "Outline", node: <OutlinePanel />, preferredRegion: "bottom" },
      { id: "story-grid", label: "Story Grid", node: <StoryGrid /> },
      { id: "timeline", label: "Timeline", node: <TimelinePanel /> },
      { id: "canvas-plot", label: "Canvas Plot", node: <CanvasPlot /> },
      { id: "series", label: "Series", node: <SeriesNavigator />, modes: ["series"] },
    ],
  },
  {
    group: "STRUCTURE",
    panels: [
      { id: "structure", label: "Structure", node: <StructurePanel /> },
      { id: "acts", label: "Acts", node: <ActsView /> },
      { id: "beats", label: "Beats", node: <BeatsView /> },
      { id: "chapters", label: "Chapters", node: <ChaptersView />, modes: ["novel"] },
      { id: "structure-analysis", label: "Structure Analysis", node: <CoverageAnalysis /> },
      { id: "format-studio", label: "Format Studio", node: <FormatStructure /> },
    ],
  },
  {
    group: "ANALYTICS",
    panels: [
      { id: "health", label: "Health", node: <StoryHealthHud />, preferredRegion: "bottom" },
      { id: "pacing", label: "Pacing", node: <PacingInsights /> },
      { id: "balance", label: "Balance", node: <CharacterBalance /> },
      { id: "tags", label: "Tags", node: <TagsView /> },
      { id: "continuity", label: "Continuity", node: <ContinuityPanel /> },
      { id: "decision-radar", label: "Decision Radar", node: <DecisionRadar />, preferredRegion: "right" },
      { id: "adapt", label: "Adapt", node: <AdaptView /> },
      { id: "review", label: "Review", node: <ReviewDashboard /> },
    ],
  },
  {
    group: "BIBLE",
    panels: [
      { id: "psyke", label: "PSYKE", node: <PsykeBible /> },
      { id: "characters", label: "Characters", node: <CharacterLinks /> },
      { id: "theme-scenes", label: "Theme Scenes", node: <ThemeScenes /> },
      { id: "graph", label: "Graph", node: <KnowledgeGraph /> },
    ],
  },
  {
    group: "",
    panels: [
      { id: "plugins", label: "Plugins", node: <PluginsPanel /> },
      { id: "connector", label: "Connector", node: <ConnectorPanel /> },
      { id: "export", label: "Export", node: <ExportDialog /> },
      { id: "ai-settings", label: "AI Settings", node: <AiSettingsPanel /> },
      { id: "settings", label: "Settings", node: <CrossCutting /> },
      { id: "help", label: "Help", node: <HelpPanel /> },
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
