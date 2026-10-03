import type {
  StoryStructurePlacementDTO,
  StoryStructureDTO,
} from "@logosforge/ui-contracts";

export type ScenePlacementEdge = "before" | "after";

export interface ScenePlacementEntry {
  sceneId: number;
  title: string;
  number: string;
  episodeId: number | null;
  act: string;
  chapter: string;
  actLabel: string;
  chapterLabel: string;
}

export interface ScenePlacementDraft {
  projectId: number;
  expectedRevision: string;
  sceneId: number;
  originIndex: number;
  originAct: string;
  originChapter: string;
  entries: ScenePlacementEntry[];
}

export type ScenePlacementBlockReason =
  | "boundary"
  | "episode_boundary"
  | "missing_scene";

export interface ScenePlacementDraftResult {
  draft: ScenePlacementDraft;
  moved: boolean;
  reason?: ScenePlacementBlockReason;
}

export interface PlannedScenePlacement {
  sceneId: number;
  body: StoryStructurePlacementDTO;
  canonicalIndex: number;
  totalScenes: number;
  actLabel: string;
  chapterLabel: string;
  title: string;
  number: string;
}

function storedLabel(name: string, unassigned: boolean): string {
  return unassigned ? "" : name;
}

/** Flatten without sorting: the server's nested arrays are already canonical. */
export function flattenStoryStructure(
  structure: StoryStructureDTO,
): ScenePlacementEntry[] {
  return structure.acts.flatMap((act) => act.chapters.flatMap((chapter) => (
    chapter.scenes.map((scene) => ({
      sceneId: scene.id,
      title: scene.title,
      number: scene.number,
      episodeId: scene.episode_id,
      act: storedLabel(act.name, act.unassigned),
      chapter: storedLabel(chapter.name, chapter.unassigned),
      actLabel: act.name,
      chapterLabel: chapter.name,
    }))
  )));
}

export function createScenePlacementDraft(
  structure: StoryStructureDTO,
  sceneId: number,
): ScenePlacementDraft | null {
  const entries = flattenStoryStructure(structure);
  const originIndex = entries.findIndex((entry) => entry.sceneId === sceneId);
  const origin = entries[originIndex];
  if (!origin) return null;
  return {
    projectId: structure.project_id,
    expectedRevision: structure.revision,
    sceneId,
    originIndex,
    originAct: origin.act,
    originChapter: origin.chapter,
    entries,
  };
}

/** Confirm that a fresh canonical read still has the neighbor the user saw. */
export function isImmediateScenePlacementNeighbor(
  entries: readonly ScenePlacementEntry[],
  sceneId: number,
  expectedNeighborId: number,
  delta: -1 | 1,
): boolean {
  const sourceIndex = entries.findIndex((entry) => entry.sceneId === sceneId);
  return sourceIndex >= 0
    && entries[sourceIndex + delta]?.sceneId === expectedNeighborId;
}

function withMovedEntry(
  draft: ScenePlacementDraft,
  anchorIndex: number,
  edge: ScenePlacementEdge,
): ScenePlacementDraftResult {
  const sourceIndex = draft.entries.findIndex((entry) => entry.sceneId === draft.sceneId);
  const source = draft.entries[sourceIndex];
  const anchor = draft.entries[anchorIndex];
  if (!source || !anchor) return { draft, moved: false, reason: "missing_scene" };
  if (source.sceneId === anchor.sceneId) return { draft, moved: false };
  // A structure placement deliberately preserves Series ownership. Crossing an
  // episode boundary would produce an order the endpoint cannot represent
  // without an explicit episode reassignment, so the navigator blocks it.
  if (source.episodeId !== anchor.episodeId) {
    return { draft, moved: false, reason: "episode_boundary" };
  }

  const entries = draft.entries.slice();
  entries.splice(sourceIndex, 1);
  const remainingAnchorIndex = entries.findIndex((entry) => entry.sceneId === anchor.sceneId);
  if (remainingAnchorIndex < 0) return { draft, moved: false, reason: "missing_scene" };
  const insertionIndex = remainingAnchorIndex + (edge === "after" ? 1 : 0);
  entries.splice(insertionIndex, 0, {
    ...source,
    act: anchor.act,
    chapter: anchor.chapter,
    actLabel: anchor.actLabel,
    chapterLabel: anchor.chapterLabel,
  });
  return { draft: { ...draft, entries }, moved: true };
}

/** Stage a pointer drop relative to another canonical scene. */
export function placeScenePlacementDraft(
  draft: ScenePlacementDraft,
  anchorSceneId: number,
  edge: ScenePlacementEdge,
): ScenePlacementDraftResult {
  const anchorIndex = draft.entries.findIndex((entry) => entry.sceneId === anchorSceneId);
  return anchorIndex < 0
    ? { draft, moved: false, reason: "missing_scene" }
    : withMovedEntry(draft, anchorIndex, edge);
}

/** Stage one accessible keyboard step in canonical order. */
export function stepScenePlacementDraft(
  draft: ScenePlacementDraft,
  delta: -1 | 1,
): ScenePlacementDraftResult {
  const sourceIndex = draft.entries.findIndex((entry) => entry.sceneId === draft.sceneId);
  if (sourceIndex < 0) return { draft, moved: false, reason: "missing_scene" };
  const anchorIndex = sourceIndex + delta;
  if (anchorIndex < 0 || anchorIndex >= draft.entries.length) {
    return { draft, moved: false, reason: "boundary" };
  }
  return withMovedEntry(draft, anchorIndex, delta < 0 ? "before" : "after");
}

export function scenePlacementDraftChanged(draft: ScenePlacementDraft): boolean {
  const currentIndex = draft.entries.findIndex((entry) => entry.sceneId === draft.sceneId);
  const current = draft.entries[currentIndex];
  return Boolean(current && (
    currentIndex !== draft.originIndex
    || current.act !== draft.originAct
    || current.chapter !== draft.originChapter
  ));
}

/** Convert a staged projection into the endpoint's post-removal sibling index. */
export function scenePlacementPlan(
  draft: ScenePlacementDraft,
): PlannedScenePlacement | null {
  const canonicalIndex = draft.entries.findIndex((entry) => entry.sceneId === draft.sceneId);
  const current = draft.entries[canonicalIndex];
  if (!current || !scenePlacementDraftChanged(draft)) return null;
  const siblingIndex = draft.entries
    .filter((entry) => (
      entry.episodeId === current.episodeId
      && entry.act === current.act
      && entry.chapter === current.chapter
    ))
    .findIndex((entry) => entry.sceneId === draft.sceneId);
  if (siblingIndex < 0) return null;
  return {
    sceneId: draft.sceneId,
    body: {
      expected_revision: draft.expectedRevision,
      act: current.act,
      chapter: current.chapter,
      index: siblingIndex,
      // Omission is intentional: moving structure must preserve Series
      // ownership. Episode moves belong to the Series Navigator.
    },
    canonicalIndex,
    totalScenes: draft.entries.length,
    actLabel: current.actLabel,
    chapterLabel: current.chapterLabel,
    title: current.title,
    number: current.number,
  };
}

export function describeScenePlacementDraft(draft: ScenePlacementDraft): string {
  const index = draft.entries.findIndex((entry) => entry.sceneId === draft.sceneId);
  const entry = draft.entries[index];
  if (!entry) return "The scene is no longer present in the structure.";
  const position = `position ${index + 1} of ${draft.entries.length}`;
  const path = [entry.chapterLabel, entry.actLabel].filter(Boolean).join(", ");
  return `Moving ${entry.title.trim() || "Untitled scene"}, ${position}${path ? `, ${path}` : ""}.`;
}
