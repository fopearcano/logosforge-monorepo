import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type DragEvent as ReactDragEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import type {
  StoryStructureActDTO,
  StoryStructureChapterDTO,
  StoryStructureDTO,
  StoryStructureSceneDTO,
} from "@logosforge/ui-contracts";
import { useStudio } from "../../adapters/StudioProvider";
import { useSelection } from "../../adapters/selection";
import { ApiRequestError } from "../../adapters/httpApiClient";
import {
  flushPendingProjectSaves,
  trackProjectWrite,
} from "../../adapters/projectSaveCoordinator";
import { useMountedRef, useStoryStructure } from "../../hooks";
import {
  createScenePlacementDraft,
  describeScenePlacementDraft,
  placeScenePlacementDraft,
  scenePlacementPlan,
  stepScenePlacementDraft,
  type PlannedScenePlacement,
  type ScenePlacementDraft,
  type ScenePlacementEdge,
} from "./storyStructurePlacement";

const STRUCTURE_SCENE_DRAG_MIME = "application/x-logosforge-structure-scene";

export interface StudioSceneNavigatorProps {
  /** Host lifecycle guard (project handoff, layout hydration, app close, …). */
  disabled?: boolean;
  /**
   * Open one canonical scene through the host's guarded navigation path.
   * `false` means the host deliberately kept the current workspace in place.
   */
  onOpenScene(sceneId: number): Promise<boolean>;
  /** Optional host-owned project search/omnibox entry point. */
  onSearch?: () => void;
}

export interface StudioStructureChapterProjection {
  chapter: StoryStructureChapterDTO;
  scenes: StoryStructureSceneDTO[];
}

export interface StudioStructureActProjection {
  act: StoryStructureActDTO;
  chapters: StudioStructureChapterProjection[];
}

export interface StudioStructureProjection {
  acts: StudioStructureActProjection[];
  sceneIds: Set<number>;
  sceneCount: number;
}

function normalized(value: string): string {
  return value.trim().toLocaleLowerCase();
}

function matches(value: string | number, needle: string): boolean {
  return normalized(String(value)).includes(needle);
}

/**
 * Filter the core-owned tree without changing its order or structural numbers.
 * A matching group retains every descendant; a matching scene retains its
 * ancestors. Expansion during filtering is a render-time projection only.
 */
export function filterStudioStoryStructure(
  structure: StoryStructureDTO,
  query: string,
): StudioStructureProjection {
  const needle = normalized(query);
  const acts: StudioStructureActProjection[] = [];
  const sceneIds = new Set<number>();

  for (const act of structure.acts) {
    const actMatch = needle !== "" && (
      matches(act.name, needle)
      || matches(act.number, needle)
      || matches(`act ${act.number}`, needle)
    );
    const chapters: StudioStructureChapterProjection[] = [];
    for (const chapter of act.chapters) {
      const chapterMatch = needle !== "" && (
        matches(chapter.name, needle)
        || matches(chapter.number, needle)
        || matches(`chapter ${chapter.number}`, needle)
      );
      const scenes = chapter.scenes.filter((scene) => (
        !needle
        || actMatch
        || chapterMatch
        || matches(scene.title, needle)
        || matches(scene.beat, needle)
        || matches(scene.number, needle)
        || matches(scene.order_index, needle)
      ));
      if (!needle || actMatch || chapterMatch || scenes.length > 0) {
        chapters.push({ chapter, scenes: actMatch || chapterMatch ? chapter.scenes : scenes });
      }
    }
    if (!needle || actMatch || chapters.length > 0) {
      acts.push({ act, chapters: actMatch ? act.chapters.map((chapter) => ({ chapter, scenes: chapter.scenes })) : chapters });
    }
  }

  for (const act of acts) {
    for (const chapter of act.chapters) {
      for (const scene of chapter.scenes) sceneIds.add(scene.id);
    }
  }
  return { acts, sceneIds, sceneCount: sceneIds.size };
}

function actKey(act: StoryStructureActDTO): string {
  return JSON.stringify(["act", act.number, act.unassigned, act.name]);
}

function chapterKey(act: StoryStructureActDTO, chapter: StoryStructureChapterDTO): string {
  return JSON.stringify([
    "chapter",
    act.number,
    act.unassigned,
    act.name,
    chapter.number,
    chapter.unassigned,
    chapter.name,
  ]);
}

function sceneLabel(scene: StoryStructureSceneDTO): string {
  return scene.title.trim() || "Untitled scene";
}

function sceneNumber(scene: StoryStructureSceneDTO): string {
  return scene.number.trim();
}

function groupCountLabel(count: number): string {
  return `${count} scene${count === 1 ? "" : "s"}`;
}

function actToggleLabel(act: StoryStructureActDTO): string {
  const prefix = act.unassigned ? "Unassigned act" : `Act ${act.number || "—"}: ${act.name}`;
  return `${prefix}, ${groupCountLabel(act.scene_count)}`;
}

function chapterToggleLabel(chapter: StoryStructureChapterDTO): string {
  const prefix = chapter.unassigned
    ? "Unassigned chapter"
    : `Chapter ${chapter.number || "—"}: ${chapter.name}`;
  return `${prefix}, ${groupCountLabel(chapter.scene_count)}`;
}

interface ScenePath {
  actKey: string;
  chapterKey: string;
}

interface PointerSceneMove {
  projectId: number;
  revision: string;
  sceneId: number;
}

interface PendingMoveFocus {
  projectId: number;
  sceneId: number;
  structureAtRequest: StoryStructureDTO | undefined;
}

function findScenePath(structure: StoryStructureDTO | undefined, sceneId: number | null): ScenePath | null {
  if (!structure || sceneId == null) return null;
  for (const act of structure.acts) {
    for (const chapter of act.chapters) {
      if (chapter.scenes.some((scene) => scene.id === sceneId)) {
        return { actKey: actKey(act), chapterKey: chapterKey(act, chapter) };
      }
    }
  }
  return null;
}

/**
 * Compact, live, core-owned structure navigator for a Studio workspace.
 *
 * Scene activation remains host-owned. Structure movement uses the core's
 * revision-guarded placement transaction after the shared save barrier settles.
 */
export function StudioSceneNavigator({
  disabled = false,
  onOpenScene,
  onSearch,
}: StudioSceneNavigatorProps) {
  const { api, projectId } = useStudio();
  const { selection } = useSelection();
  const { data: loadedStructure, loading, error, refetch } = useStoryStructure();
  const structure = loadedStructure?.project_id === projectId ? loadedStructure : undefined;
  const [query, setQuery] = useState("");
  const [expandedActs, setExpandedActs] = useState<Set<string>>(() => new Set());
  const [expandedChapters, setExpandedChapters] = useState<Set<string>>(() => new Set());
  const [openingSceneId, setOpeningSceneId] = useState<number | null>(null);
  const [placingSceneId, setPlacingSceneId] = useState<number | null>(null);
  const [keyboardMove, setKeyboardMove] = useState<ScenePlacementDraft | null>(null);
  const [draggingSceneId, setDraggingSceneId] = useState<number | null>(null);
  const [dropTarget, setDropTarget] = useState<{ sceneId: number; edge: ScenePlacementEdge } | null>(null);
  const [placementStatus, setPlacementStatus] = useState("");
  const [activationError, setActivationError] = useState("");
  const [placementError, setPlacementError] = useState("");
  const initializedProjectRef = useRef<number | null>(null);
  const activationRef = useRef<object | null>(null);
  const placementRef = useRef<object | null>(null);
  const pointerMoveRef = useRef<PointerSceneMove | null>(null);
  const pendingMoveFocusRef = useRef<PendingMoveFocus | null>(null);
  const moveFocusTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sceneNodesRef = useRef(new Map<number, HTMLButtonElement>());
  const moveHandleNodesRef = useRef(new Map<number, HTMLButtonElement>());
  const mounted = useMountedRef();
  const headingId = useId();
  const controlsPrefix = useId().replace(/:/g, "");
  const projectIdRef = useRef(projectId);
  const structureRef = useRef(structure);
  projectIdRef.current = projectId;
  structureRef.current = structure;

  useEffect(() => {
    initializedProjectRef.current = null;
    activationRef.current = null;
    placementRef.current = null;
    pointerMoveRef.current = null;
    pendingMoveFocusRef.current = null;
    if (moveFocusTimerRef.current != null) clearTimeout(moveFocusTimerRef.current);
    moveFocusTimerRef.current = null;
    sceneNodesRef.current.clear();
    moveHandleNodesRef.current.clear();
    setQuery("");
    setExpandedActs(new Set());
    setExpandedChapters(new Set());
    setOpeningSceneId(null);
    setPlacingSceneId(null);
    setKeyboardMove(null);
    setDraggingSceneId(null);
    setDropTarget(null);
    setPlacementStatus("");
    setActivationError("");
    setPlacementError("");
    return () => {
      if (moveFocusTimerRef.current != null) clearTimeout(moveFocusTimerRef.current);
      moveFocusTimerRef.current = null;
    };
  }, [projectId]);

  const projection = useMemo(
    () => structure ? filterStudioStoryStructure(structure, query) : { acts: [], sceneIds: new Set<number>(), sceneCount: 0 },
    [query, structure],
  );
  const filtering = normalized(query) !== "";
  const total = structure?.scene_count ?? 0;
  const mutating = placingSceneId != null;
  const movingWithKeyboard = keyboardMove != null;
  const blocked = disabled || openingSceneId != null || mutating || movingWithKeyboard;
  const activePath = findScenePath(structure, selection.sceneId);
  const activePathSignature = activePath ? `${activePath.actKey}\u0000${activePath.chapterKey}` : "";
  const currentHidden = filtering
    && selection.sceneId != null
    && findScenePath(structure, selection.sceneId) != null
    && !projection.sceneIds.has(selection.sceneId);

  useEffect(() => {
    if (!structure || initializedProjectRef.current === structure.project_id) return;
    initializedProjectRef.current = structure.project_id;
    const firstAct = structure.acts[0];
    const firstChapter = firstAct?.chapters[0];
    const path = activePath ?? (firstAct && firstChapter
      ? { actKey: actKey(firstAct), chapterKey: chapterKey(firstAct, firstChapter) }
      : null);
    if (path) {
      setExpandedActs(new Set([path.actKey]));
      if (structure.chapter_level) setExpandedChapters(new Set([path.chapterKey]));
    }
  }, [activePathSignature, structure]);

  useEffect(() => {
    if (!activePath || selection.sceneId == null) return;
    setExpandedActs((current) => current.has(activePath.actKey)
      ? current
      : new Set([...current, activePath.actKey]));
    if (structure?.chapter_level) {
      setExpandedChapters((current) => current.has(activePath.chapterKey)
        ? current
        : new Set([...current, activePath.chapterKey]));
    }
  }, [activePathSignature, selection.sceneId, structure?.chapter_level]);

  useEffect(() => {
    if (selection.sceneId == null) return;
    if (!projection.sceneIds.has(selection.sceneId)) return;
    const sceneId = selection.sceneId;
    const timer = setTimeout(() => {
      sceneNodesRef.current.get(sceneId)?.scrollIntoView?.({ block: "nearest" });
    }, 0);
    return () => clearTimeout(timer);
  }, [activePathSignature, projection.sceneIds, selection.sceneId]);

  const registerSceneNode = useCallback((sceneId: number, node: HTMLButtonElement | null) => {
    if (node) sceneNodesRef.current.set(sceneId, node);
    else sceneNodesRef.current.delete(sceneId);
  }, []);

  const registerMoveHandle = useCallback((sceneId: number, node: HTMLButtonElement | null) => {
    if (node) moveHandleNodesRef.current.set(sceneId, node);
    else moveHandleNodesRef.current.delete(sceneId);
  }, []);

  const focusMoveHandle = useCallback((sceneId: number) => {
    if (moveFocusTimerRef.current != null) clearTimeout(moveFocusTimerRef.current);
    moveFocusTimerRef.current = setTimeout(() => {
      moveFocusTimerRef.current = null;
      moveHandleNodesRef.current.get(sceneId)?.focus({ preventScroll: true });
    }, 0);
  }, []);

  useEffect(() => {
    const pending = pendingMoveFocusRef.current;
    if (
      loading
      || !structure
      || !pending
      || pending.projectId !== structure.project_id
    ) return;
    const refreshed = structure !== pending.structureAtRequest;
    if (!refreshed) return;
    const movedPath = findScenePath(structure, pending.sceneId);
    pendingMoveFocusRef.current = null;
    if (!movedPath) return;
    setExpandedActs((current) => current.has(movedPath.actKey)
      ? current
      : new Set([...current, movedPath.actKey]));
    if (structure.chapter_level) {
      setExpandedChapters((current) => current.has(movedPath.chapterKey)
        ? current
        : new Set([...current, movedPath.chapterKey]));
    }
    focusMoveHandle(pending.sceneId);
  }, [focusMoveHandle, loading, structure]);

  const explainBlockedMove = useCallback((reason: "boundary" | "episode_boundary" | "missing_scene" | undefined) => {
    if (reason === "episode_boundary") {
      setPlacementStatus("Scenes cannot cross a Series episode boundary here. Use the Series Navigator to change episode ownership.");
    } else if (reason === "boundary") {
      setPlacementStatus("The scene is already at the edge of its available structure order.");
    } else {
      setPlacementStatus("That move is no longer available. The structure may have changed.");
    }
  }, []);

  const commitPlacement = useCallback(async (plan: PlannedScenePlacement) => {
    const ownerProjectId = projectIdRef.current;
    if (disabled || ownerProjectId == null || openingSceneId != null || placementRef.current != null) return;
    const token = {};
    placementRef.current = token;
    setPlacingSceneId(plan.sceneId);
    setPlacementError("");
    setPlacementStatus(`Saving the new position for ${plan.title.trim() || "Untitled scene"}…`);
    try {
      await flushPendingProjectSaves();
      if (
        !mounted.current
        || placementRef.current !== token
        || projectIdRef.current !== ownerProjectId
      ) return;
      const updated = await trackProjectWrite(
        api.placeScene(ownerProjectId, plan.sceneId, plan.body),
      );
      if (
        !mounted.current
        || placementRef.current !== token
        || projectIdRef.current !== ownerProjectId
      ) return;
      if (updated.project_id !== ownerProjectId) {
        throw new Error("The updated structure belongs to another project.");
      }
      const movedPath = findScenePath(updated, plan.sceneId);
      if (movedPath) {
        setExpandedActs((current) => current.has(movedPath.actKey)
          ? current
          : new Set([...current, movedPath.actKey]));
        if (updated.chapter_level) {
          setExpandedChapters((current) => current.has(movedPath.chapterKey)
            ? current
            : new Set([...current, movedPath.chapterKey]));
        }
      }
      pendingMoveFocusRef.current = {
        projectId: ownerProjectId,
        sceneId: plan.sceneId,
        structureAtRequest: structureRef.current,
      };
      setKeyboardMove(null);
      setPlacementStatus(
        `Moved ${plan.title.trim() || "Untitled scene"} to position ${plan.canonicalIndex + 1} of ${plan.totalScenes}.`,
      );
      refetch();
    } catch (placementFailure) {
      if (
        !mounted.current
        || placementRef.current !== token
        || projectIdRef.current !== ownerProjectId
      ) return;
      const conflict = placementFailure instanceof ApiRequestError
        && (placementFailure.code === "structure_conflict" || placementFailure.status === 409);
      // Even a validation/network/server failure can arrive after the core
      // committed the mutation. Restore focus only after an authoritative
      // refresh, accepting unchanged data for genuinely pre-commit failures.
      pendingMoveFocusRef.current = {
        projectId: ownerProjectId,
        sceneId: plan.sceneId,
        structureAtRequest: structureRef.current,
      };
      setKeyboardMove(null);
      setPlacementError(conflict
        ? "The story structure changed before this move could be saved. It has been refreshed; review the new order and try again."
        : `Couldn't move the scene — ${placementFailure instanceof Error ? placementFailure.message : String(placementFailure)}`);
      setPlacementStatus("");
      refetch();
    } finally {
      if (
        mounted.current
        && placementRef.current === token
        && projectIdRef.current === ownerProjectId
      ) {
        placementRef.current = null;
        setPlacingSceneId(null);
      }
    }
  }, [api, disabled, mounted, openingSceneId, refetch]);

  const beginKeyboardMove = useCallback((sceneId: number) => {
    if (
      disabled
      || filtering
      || openingSceneId != null
      || placingSceneId != null
      || keyboardMove != null
      || !structure
    ) return;
    const draft = createScenePlacementDraft(structure, sceneId);
    if (!draft) {
      setPlacementError("The scene is no longer present in the current structure.");
      return;
    }
    setPlacementError("");
    setKeyboardMove(draft);
    setPlacementStatus(`${describeScenePlacementDraft(draft)} Use Up and Down to choose a position, Enter or Space to save, or Escape to cancel.`);
  }, [disabled, filtering, keyboardMove, openingSceneId, placingSceneId, structure]);

  const cancelKeyboardMove = useCallback((message = "Scene move cancelled.") => {
    const sceneId = keyboardMove?.sceneId;
    setKeyboardMove(null);
    setPlacementStatus(message);
    if (sceneId != null) focusMoveHandle(sceneId);
  }, [focusMoveHandle, keyboardMove?.sceneId]);

  useEffect(() => {
    if (!keyboardMove || !structure || keyboardMove.expectedRevision === structure.revision) return;
    const sceneId = keyboardMove.sceneId;
    setKeyboardMove(null);
    // A completed placement failure owns its post-refresh focus restoration.
    // Do not race that path with the generic "structure changed while staging"
    // cancellation focus below.
    if (placementError) return;
    setPlacementStatus("Scene move cancelled because the story structure changed.");
    focusMoveHandle(sceneId);
  }, [focusMoveHandle, keyboardMove, placementError, structure]);

  const handleMoveKey = useCallback((
    event: ReactKeyboardEvent<HTMLButtonElement>,
    sceneId: number,
  ) => {
    if (disabled || filtering || openingSceneId != null || placingSceneId != null) return;
    const activeDraft = keyboardMove?.sceneId === sceneId ? keyboardMove : null;
    if (!activeDraft) {
      if (keyboardMove != null) return;
      if (event.key === " " || event.key === "Enter") {
        event.preventDefault();
        event.stopPropagation();
        beginKeyboardMove(sceneId);
      }
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      cancelKeyboardMove();
      return;
    }
    if (event.key === "ArrowUp" || event.key === "ArrowDown") {
      event.preventDefault();
      event.stopPropagation();
      const result = stepScenePlacementDraft(activeDraft, event.key === "ArrowUp" ? -1 : 1);
      if (!result.moved) {
        explainBlockedMove(result.reason);
        return;
      }
      setKeyboardMove(result.draft);
      setPlacementStatus(`${describeScenePlacementDraft(result.draft)} Press Enter or Space to save, or Escape to cancel.`);
      return;
    }
    if (event.key === " " || event.key === "Enter") {
      event.preventDefault();
      event.stopPropagation();
      const plan = scenePlacementPlan(activeDraft);
      if (plan) void commitPlacement(plan);
      else cancelKeyboardMove("Scene move cancelled because its position did not change.");
    }
  }, [
    beginKeyboardMove,
    cancelKeyboardMove,
    commitPlacement,
    disabled,
    explainBlockedMove,
    filtering,
    keyboardMove,
    openingSceneId,
    placingSceneId,
  ]);

  const beginPointerMove = useCallback((event: ReactDragEvent<HTMLButtonElement>, sceneId: number) => {
    if (disabled || filtering || blocked || !structure) {
      event.preventDefault();
      return;
    }
    const owner: PointerSceneMove = {
      projectId: structure.project_id,
      revision: structure.revision,
      sceneId,
    };
    pointerMoveRef.current = owner;
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData(STRUCTURE_SCENE_DRAG_MIME, JSON.stringify(owner));
    setDraggingSceneId(sceneId);
    setDropTarget(null);
    setPlacementError("");
    const draft = createScenePlacementDraft(structure, sceneId);
    if (draft) setPlacementStatus(`${describeScenePlacementDraft(draft)} Drop before or after another scene to save.`);
  }, [blocked, disabled, filtering, structure]);

  const pointerMoveSceneId = useCallback((event: ReactDragEvent): number | null => {
    let payload: PointerSceneMove | null = pointerMoveRef.current;
    if (!payload) {
      try {
        const parsed = JSON.parse(event.dataTransfer.getData(STRUCTURE_SCENE_DRAG_MIME)) as {
        projectId?: unknown;
        revision?: unknown;
        sceneId?: unknown;
        };
        payload = typeof parsed.projectId === "number"
          && typeof parsed.revision === "string"
          && typeof parsed.sceneId === "number"
          ? { projectId: parsed.projectId, revision: parsed.revision, sceneId: parsed.sceneId }
          : null;
      } catch {
        payload = null;
      }
    }
    if (!payload) return null;
    return payload.projectId === projectIdRef.current
      && payload.revision === structure?.revision
      ? payload.sceneId
      : null;
  }, [structure?.revision]);

  const pointerPlacement = useCallback((
    event: ReactDragEvent<HTMLLIElement>,
    targetSceneId: number,
  ): { plan: PlannedScenePlacement | null; edge: ScenePlacementEdge; reason?: "boundary" | "episode_boundary" | "missing_scene" } | null => {
    if (!structure || disabled || filtering || placingSceneId != null || openingSceneId != null) return null;
    const sourceSceneId = pointerMoveSceneId(event);
    if (sourceSceneId == null || sourceSceneId === targetSceneId) return null;
    const rect = event.currentTarget.getBoundingClientRect();
    const edge: ScenePlacementEdge = event.clientY < rect.top + rect.height / 2 ? "before" : "after";
    const draft = createScenePlacementDraft(structure, sourceSceneId);
    if (!draft) return null;
    const result = placeScenePlacementDraft(draft, targetSceneId, edge);
    return { plan: scenePlacementPlan(result.draft), edge, reason: result.reason };
  }, [disabled, filtering, openingSceneId, placingSceneId, pointerMoveSceneId, structure]);

  const endPointerMove = useCallback((announceCancellation = true) => {
    const hadOwnedMove = pointerMoveRef.current != null;
    pointerMoveRef.current = null;
    setDraggingSceneId(null);
    setDropTarget(null);
    if (announceCancellation && hadOwnedMove) setPlacementStatus("Scene move cancelled.");
  }, []);

  useEffect(() => {
    const owner = pointerMoveRef.current;
    if (!owner) return;
    if (owner.projectId === projectId && owner.revision === structure?.revision) return;
    pointerMoveRef.current = null;
    setDraggingSceneId(null);
    setDropTarget(null);
    setPlacementStatus("Scene move cancelled because the story structure changed.");
  }, [projectId, structure?.revision]);

  const activate = useCallback(async (sceneId: number) => {
    if (disabled || activationRef.current != null || placementRef.current != null || keyboardMove != null) return;
    const ownerProjectId = projectIdRef.current;
    const token = {};
    activationRef.current = token;
    setOpeningSceneId(sceneId);
    setActivationError("");
    try {
      const opened = await onOpenScene(sceneId);
      if (!mounted.current || activationRef.current !== token || projectIdRef.current !== ownerProjectId) return;
      if (!opened) setActivationError("The scene stayed closed because the workspace could not complete the handoff.");
    } catch (openError) {
      if (!mounted.current || activationRef.current !== token || projectIdRef.current !== ownerProjectId) return;
      setActivationError(
        `Couldn't open the scene — ${openError instanceof Error ? openError.message : String(openError)}`,
      );
    } finally {
      if (mounted.current && activationRef.current === token && projectIdRef.current === ownerProjectId) {
        activationRef.current = null;
        setOpeningSceneId(null);
      }
    }
  }, [disabled, keyboardMove, mounted, onOpenScene]);

  const toggleAct = useCallback((key: string) => {
    if (blocked || filtering) return;
    setExpandedActs((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  }, [blocked, filtering]);

  const toggleChapter = useCallback((key: string) => {
    if (blocked || filtering) return;
    setExpandedChapters((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  }, [blocked, filtering]);

  const renderScene = (scene: StoryStructureSceneDTO) => {
    const title = sceneLabel(scene);
    const number = sceneNumber(scene);
    const numberLabel = number || "—";
    const active = selection.sceneId === scene.id;
    const opening = openingSceneId === scene.id;
    const placing = placingSceneId === scene.id;
    const keyboardOwner = keyboardMove?.sceneId === scene.id;
    const moveUnavailable = disabled
      || filtering
      || openingSceneId != null
      || placingSceneId != null
      || (keyboardMove != null && !keyboardOwner);
    const dropEdge = dropTarget?.sceneId === scene.id ? dropTarget.edge : undefined;
    return (
      <li
        key={scene.id}
        className="lf-studio-scene-entry"
        data-structure-level="scene"
        data-scene-drop-id={scene.id}
        data-structure-number={scene.number}
        data-drop-edge={dropEdge}
        data-drag-source={draggingSceneId === scene.id || undefined}
        onDragOver={(event) => {
          const placement = pointerPlacement(event, scene.id);
          if (!placement || placement.reason || !placement.plan) {
            event.dataTransfer.dropEffect = "none";
            setDropTarget((current) => current?.sceneId === scene.id ? null : current);
            return;
          }
          event.preventDefault();
          event.dataTransfer.dropEffect = "move";
          setDropTarget((current) => current?.sceneId === scene.id && current.edge === placement.edge
            ? current
            : { sceneId: scene.id, edge: placement.edge });
        }}
        onDragLeave={(event) => {
          if (event.relatedTarget instanceof Node && event.currentTarget.contains(event.relatedTarget)) return;
          setDropTarget((current) => current?.sceneId === scene.id ? null : current);
        }}
        onDrop={(event) => {
          const placement = pointerPlacement(event, scene.id);
          event.preventDefault();
          if (!placement) {
            endPointerMove();
            return;
          }
          endPointerMove(false);
          if (placement.reason) {
            explainBlockedMove(placement.reason);
            return;
          }
          if (placement.plan) void commitPlacement(placement.plan);
          else setPlacementStatus("Scene move cancelled because its position did not change.");
        }}
      >
        <button
          ref={(node) => registerSceneNode(scene.id, node)}
          type="button"
          className="lf-studio-scene-row"
          data-scene-id={scene.id}
          data-structure-level="scene"
          data-structure-number={scene.number}
          data-opening={opening || undefined}
          aria-label={number
            ? `Open scene ${number}: ${title}`
            : `Open unnumbered scene: ${title}`}
          aria-current={active ? "location" : undefined}
          aria-disabled={blocked || undefined}
          onClick={() => { if (!blocked) void activate(scene.id); }}
        >
          <span className="lf-studio-scene-position">{numberLabel}</span>
          <span className="lf-studio-scene-copy">
            <span className="lf-studio-scene-title">{title}</span>
            {scene.beat && <span className="lf-studio-scene-meta">{scene.beat}</span>}
          </span>
          <span className="lf-studio-scene-state" aria-hidden="true">
            {opening || placing ? "…" : active ? "●" : scene.is_orphan ? "◇" : ""}
          </span>
        </button>
        <button
          ref={(node) => registerMoveHandle(scene.id, node)}
          type="button"
          className="lf-studio-scene-move-handle"
          data-scene-move-id={scene.id}
          draggable={!moveUnavailable && !keyboardOwner}
          aria-label={`${keyboardOwner ? "Finish moving" : "Move"} scene ${number || "unnumbered"}: ${title}`}
          aria-pressed={keyboardOwner}
          aria-disabled={moveUnavailable || undefined}
          title={filtering
            ? "Clear the scene filter before reordering"
            : keyboardOwner
              ? "Use Up/Down, then Enter or Space to save; Escape cancels"
              : "Drag to reorder, or press Enter or Space for keyboard movement"}
          onClick={() => {
            if (moveUnavailable) return;
            if (keyboardOwner) {
              const plan = keyboardMove ? scenePlacementPlan(keyboardMove) : null;
              if (plan) void commitPlacement(plan);
              else cancelKeyboardMove("Scene move cancelled because its position did not change.");
            } else beginKeyboardMove(scene.id);
          }}
          onKeyDown={(event) => handleMoveKey(event, scene.id)}
          onDragStart={(event) => beginPointerMove(event, scene.id)}
          onDragEnd={() => endPointerMove()}
        >
          <span aria-hidden="true">↕</span>
        </button>
      </li>
    );
  };

  return (
    <section
      className="lf-studio-scene-navigator"
      data-screen-label="Studio Scene Navigator"
      data-scene-navigator="true"
      aria-labelledby={headingId}
    >
      <div className="lf-studio-scene-navigator-heading">
        <span id={headingId}>SCENES</span>
        <span aria-label={`${total} project scenes`}>
          {filtering ? `${projection.sceneCount}/${total}` : total}
        </span>
        {onSearch && (
          <button
            type="button"
            onClick={() => { if (!blocked) onSearch(); }}
            aria-disabled={blocked || undefined}
            className="lf-studio-scene-search-action"
          >
            Search project
          </button>
        )}
      </div>
      <label className="lf-studio-scene-filter">
        <span>FILTER</span>
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.currentTarget.value)}
          onKeyDown={(event) => {
            if (event.key === "Escape" && query) {
              event.preventDefault();
              setQuery("");
            }
          }}
          disabled={disabled || mutating || movingWithKeyboard}
          placeholder="Title, act, chapter, beat"
          aria-label="Filter project scenes"
        />
      </label>

      {error && (
        <div className="lf-studio-scene-message lf-studio-scene-error" role="alert">
          <span>Couldn't refresh story structure — {error}</span>
          <button type="button" onClick={refetch}>Retry</button>
        </div>
      )}
      {activationError && (
        <div className="lf-studio-scene-message lf-studio-scene-error" role="alert">
          <span>{activationError}</span>
          <button type="button" aria-label="Dismiss scene navigation error" onClick={() => setActivationError("")}>Dismiss</button>
        </div>
      )}
      {placementError && (
        <div className="lf-studio-scene-message lf-studio-scene-error" role="alert">
          <span>{placementError}</span>
          <button type="button" aria-label="Dismiss scene placement error" onClick={() => setPlacementError("")}>Dismiss</button>
        </div>
      )}
      {placementStatus && (
        <div className="lf-studio-scene-message lf-studio-scene-placement-status" role="status" aria-live="polite">
          {placementStatus}
        </div>
      )}
      {currentHidden && (
        <div className="lf-studio-scene-message lf-studio-scene-filter-notice" role="status">
          <span>Current scene hidden by filter</span>
          <button type="button" aria-label="Clear scene filter" onClick={() => setQuery("")}>Clear</button>
        </div>
      )}

      {loading && structure == null ? (
        <div className="lf-studio-scene-message" role="status">Loading story structure…</div>
      ) : error && structure == null ? null : total === 0 ? (
        <div className="lf-studio-scene-message" role="status">No scenes yet</div>
      ) : projection.sceneCount === 0 ? (
        <div className="lf-studio-scene-message" role="status">No matching scenes</div>
      ) : (
        <ol
          className="lf-studio-structure-list"
          aria-label="Project structure"
          aria-busy={openingSceneId != null || placingSceneId != null || loading || undefined}
        >
          {projection.acts.map(({ act, chapters }, actIndex) => {
            const aKey = actKey(act);
            const actExpanded = filtering || expandedActs.has(aKey);
            const actControls = `${controlsPrefix}-act-${actIndex}`;
            const flatScenes = chapters.flatMap((chapter) => chapter.scenes);
            return (
              <li
                key={aKey}
                className="lf-studio-structure-act"
                data-structure-level="act"
                data-structure-number={act.number}
              >
                <button
                  type="button"
                  className="lf-studio-structure-toggle lf-studio-structure-act-toggle"
                  data-scene-group-toggle="act"
                  aria-label={actToggleLabel(act)}
                  aria-expanded={actExpanded}
                  aria-controls={actControls}
                  aria-disabled={(blocked || filtering) || undefined}
                  onClick={() => toggleAct(aKey)}
                >
                  <span aria-hidden="true">{actExpanded ? "▾" : "▸"}</span>
                  <span className="lf-studio-structure-number">{act.number || "—"}</span>
                  <span className="lf-studio-structure-name">{act.name}</span>
                  <span className="lf-studio-structure-count">{act.scene_count}</span>
                </button>
                <ol id={actControls} className="lf-studio-structure-children" hidden={!actExpanded}>
                  {structure?.chapter_level ? chapters.map(({ chapter, scenes }, chapterIndex) => {
                    const cKey = chapterKey(act, chapter);
                    const chapterExpanded = filtering || expandedChapters.has(cKey);
                    const chapterControls = `${actControls}-chapter-${chapterIndex}`;
                    return (
                      <li
                        key={cKey}
                        className="lf-studio-structure-chapter"
                        data-structure-level="chapter"
                        data-structure-number={chapter.number}
                      >
                        <button
                          type="button"
                          className="lf-studio-structure-toggle lf-studio-structure-chapter-toggle"
                          data-scene-group-toggle="chapter"
                          aria-label={chapterToggleLabel(chapter)}
                          aria-expanded={chapterExpanded}
                          aria-controls={chapterControls}
                          aria-disabled={(blocked || filtering) || undefined}
                          onClick={() => toggleChapter(cKey)}
                        >
                          <span aria-hidden="true">{chapterExpanded ? "▾" : "▸"}</span>
                          <span className="lf-studio-structure-number">{chapter.number || "—"}</span>
                          <span className="lf-studio-structure-name">{chapter.name}</span>
                          <span className="lf-studio-structure-count">{chapter.scene_count}</span>
                        </button>
                        <ol id={chapterControls} className="lf-studio-structure-scenes" hidden={!chapterExpanded}>
                          {scenes.map(renderScene)}
                        </ol>
                      </li>
                    );
                  }) : flatScenes.map(renderScene)}
                </ol>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
