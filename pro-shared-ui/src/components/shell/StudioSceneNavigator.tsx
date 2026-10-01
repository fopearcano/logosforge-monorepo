import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import type {
  StoryStructureActDTO,
  StoryStructureChapterDTO,
  StoryStructureDTO,
  StoryStructureSceneDTO,
} from "@logosforge/ui-contracts";
import { useStudio } from "../../adapters/StudioProvider";
import { useSelection } from "../../adapters/selection";
import { useMountedRef, useStoryStructure } from "../../hooks";

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
 * It performs no writes and does not claim a scene navigation succeeded until
 * the host resolves its save-barrier-aware callback.
 */
export function StudioSceneNavigator({
  disabled = false,
  onOpenScene,
  onSearch,
}: StudioSceneNavigatorProps) {
  const { projectId } = useStudio();
  const { selection } = useSelection();
  const { data: loadedStructure, loading, error, refetch } = useStoryStructure();
  const structure = loadedStructure?.project_id === projectId ? loadedStructure : undefined;
  const [query, setQuery] = useState("");
  const [expandedActs, setExpandedActs] = useState<Set<string>>(() => new Set());
  const [expandedChapters, setExpandedChapters] = useState<Set<string>>(() => new Set());
  const [openingSceneId, setOpeningSceneId] = useState<number | null>(null);
  const [activationError, setActivationError] = useState("");
  const initializedProjectRef = useRef<number | null>(null);
  const activationRef = useRef<object | null>(null);
  const sceneNodesRef = useRef(new Map<number, HTMLButtonElement>());
  const mounted = useMountedRef();
  const headingId = useId();
  const controlsPrefix = useId().replace(/:/g, "");
  const projectIdRef = useRef(projectId);
  projectIdRef.current = projectId;

  useEffect(() => {
    initializedProjectRef.current = null;
    activationRef.current = null;
    sceneNodesRef.current.clear();
    setQuery("");
    setExpandedActs(new Set());
    setExpandedChapters(new Set());
    setOpeningSceneId(null);
    setActivationError("");
  }, [projectId]);

  const projection = useMemo(
    () => structure ? filterStudioStoryStructure(structure, query) : { acts: [], sceneIds: new Set<number>(), sceneCount: 0 },
    [query, structure],
  );
  const filtering = normalized(query) !== "";
  const total = structure?.scene_count ?? 0;
  const blocked = disabled || openingSceneId != null;
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

  const activate = useCallback(async (sceneId: number) => {
    if (disabled || activationRef.current != null) return;
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
  }, [disabled, mounted, onOpenScene]);

  const toggleAct = useCallback((key: string) => {
    if (disabled || filtering) return;
    setExpandedActs((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  }, [disabled, filtering]);

  const toggleChapter = useCallback((key: string) => {
    if (disabled || filtering) return;
    setExpandedChapters((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  }, [disabled, filtering]);

  const renderScene = (scene: StoryStructureSceneDTO) => {
    const title = sceneLabel(scene);
    const number = sceneNumber(scene);
    const numberLabel = number || "—";
    const active = selection.sceneId === scene.id;
    const opening = openingSceneId === scene.id;
    return (
      <li key={scene.id} data-structure-level="scene" data-structure-number={scene.number}>
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
            {opening ? "…" : active ? "●" : scene.is_orphan ? "◇" : ""}
          </span>
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
            onClick={() => { if (!disabled) onSearch(); }}
            aria-disabled={disabled || undefined}
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
          disabled={disabled}
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
          aria-busy={openingSceneId != null || loading || undefined}
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
                  aria-disabled={(disabled || filtering) || undefined}
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
                          aria-disabled={(disabled || filtering) || undefined}
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
