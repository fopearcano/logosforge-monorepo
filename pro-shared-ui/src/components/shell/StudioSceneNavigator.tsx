import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import type { SceneDTO } from "@logosforge/ui-contracts";
import { useStudio } from "../../adapters/StudioProvider";
import { useSelection } from "../../adapters/selection";
import { useMountedRef, useScenes } from "../../hooks";

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

export interface StudioSceneNavigatorRow {
  scene: SceneDTO;
  position: number;
  searchText: string;
  metadata: string;
}

function normalized(value: string): string {
  return value.trim().toLocaleLowerCase();
}

/** Match the Manuscript's canonical client projection: sort_order, then id. */
export function sortStudioNavigatorScenes(scenes: readonly SceneDTO[]): SceneDTO[] {
  return [...scenes].sort((left, right) => left.sort_order - right.sort_order || left.id - right.id);
}

export function filterStudioNavigatorScenes(
  scenes: readonly SceneDTO[],
  query: string,
): StudioSceneNavigatorRow[] {
  const needle = normalized(query);
  return sortStudioNavigatorScenes(scenes)
    .map((scene, index): StudioSceneNavigatorRow => {
      const title = scene.title.trim() || "Untitled scene";
      const metadata = [scene.act, scene.chapter, scene.beat]
        .map((part) => part.trim())
        .filter(Boolean)
        .join(" · ");
      const position = scene.order_index > 0 ? scene.order_index : index + 1;
      return {
        scene,
        position,
        metadata,
        searchText: normalized([
          String(position),
          title,
          scene.act,
          scene.chapter,
          scene.beat,
        ].join(" ")),
      };
    })
    .filter((row) => !needle || row.searchText.includes(needle));
}

/**
 * Compact, live scene index for a Studio workspace navigator.
 *
 * The core remains authoritative for scene data. The component performs no
 * writes and does not claim a navigation succeeded until the host resolves its
 * save-barrier-aware callback.
 */
export function StudioSceneNavigator({
  disabled = false,
  onOpenScene,
  onSearch,
}: StudioSceneNavigatorProps) {
  const { projectId } = useStudio();
  const { selection } = useSelection();
  const { data: scenes, loading, error, refetch } = useScenes();
  const [query, setQuery] = useState("");
  const [openingSceneId, setOpeningSceneId] = useState<number | null>(null);
  const [activationError, setActivationError] = useState("");
  const activationRef = useRef<object | null>(null);
  const mounted = useMountedRef();
  const headingId = useId();
  const projectIdRef = useRef(projectId);
  projectIdRef.current = projectId;

  useEffect(() => {
    activationRef.current = null;
    setQuery("");
    setOpeningSceneId(null);
    setActivationError("");
  }, [projectId]);

  const rows = useMemo(
    () => filterStudioNavigatorScenes(scenes ?? [], query),
    [query, scenes],
  );
  const total = scenes?.length ?? 0;
  const blocked = disabled || openingSceneId != null;

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

  return (
    <section
      className="lf-studio-scene-navigator"
      data-screen-label="Studio Scene Navigator"
      data-scene-navigator="true"
      aria-labelledby={headingId}
    >
      <div className="lf-studio-scene-navigator-heading">
        <span id={headingId}>SCENES</span>
        <span aria-label={`${total} project scenes`}>{total}</span>
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
          disabled={disabled}
          placeholder="Title, act, chapter, beat"
          aria-label="Filter project scenes"
        />
      </label>

      {error && (
        <div className="lf-studio-scene-message lf-studio-scene-error" role="alert">
          <span>Couldn't refresh scenes — {error}</span>
          <button type="button" onClick={refetch}>Retry</button>
        </div>
      )}
      {activationError && (
        <div className="lf-studio-scene-message lf-studio-scene-error" role="alert">
          <span>{activationError}</span>
          <button type="button" aria-label="Dismiss scene navigation error" onClick={() => setActivationError("")}>Dismiss</button>
        </div>
      )}

      {loading && scenes == null ? (
        <div className="lf-studio-scene-message" role="status">Loading scenes…</div>
      ) : error && scenes == null ? null : total === 0 ? (
        <div className="lf-studio-scene-message" role="status">No scenes yet</div>
      ) : rows.length === 0 ? (
        <div className="lf-studio-scene-message" role="status">No matching scenes</div>
      ) : (
        <ol
          className="lf-studio-scene-list"
          aria-label="Project scenes"
          aria-busy={openingSceneId != null || loading || undefined}
        >
          {rows.map(({ scene, position, metadata }) => {
            const title = scene.title.trim() || "Untitled scene";
            const active = selection.sceneId === scene.id;
            const opening = openingSceneId === scene.id;
            return (
              <li key={scene.id}>
                <button
                  type="button"
                  className="lf-studio-scene-row"
                  data-scene-id={scene.id}
                  data-opening={opening || undefined}
                  aria-label={`Open scene ${position}: ${title}`}
                  aria-current={active ? "location" : undefined}
                  aria-disabled={blocked || undefined}
                  onClick={() => { if (!blocked) void activate(scene.id); }}
                >
                  <span className="lf-studio-scene-position">{position}</span>
                  <span className="lf-studio-scene-copy">
                    <span className="lf-studio-scene-title">{title}</span>
                    {metadata && <span className="lf-studio-scene-meta">{metadata}</span>}
                  </span>
                  <span className="lf-studio-scene-state" aria-hidden="true">
                    {opening ? "…" : active ? "●" : ""}
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
