import { createContext, useContext, type ReactNode } from "react";
import type { WritingMode } from "@logosforge/ui-contracts";
import type { ApiClient } from "./api";
import type { PlatformAdapter } from "./platform";
import { SelectionProvider } from "./selection";
import { accentVars } from "../theme/accent";

/** The two adapters every Studio component depends on, injected by the host app. */
export interface StudioServices {
  api: ApiClient;
  platform: PlatformAdapter;
}

export interface NavTarget {
  navigate?: (panel: string, opts?: { sceneId?: number }) => void;
  manuscriptTargetSceneId?: number | null;
  clearManuscriptTarget?: () => void;
  /** Switch the active project (host owns projectId state). */
  selectProject?: (id: number) => void;
  /** Ask the host to re-fetch its project list (after create/rename/delete). */
  refreshProjects?: () => void;
}

export interface StudioContextValue extends StudioServices, NavTarget {
  /** The active project's writing mode — drives the `--accent` scope. */
  writingMode?: WritingMode | string;
  /** The active project id — data hooks fetch/subscribe against it. */
  projectId?: number;
}

const StudioContext = createContext<StudioContextValue | null>(null);

export function StudioProvider({
  services,
  writingMode,
  projectId,
  nav,
  children,
}: {
  services: StudioServices;
  writingMode?: WritingMode | string;
  projectId?: number;
  /** Cross-panel navigation injected by the host app (switch panel / open a scene). */
  nav?: NavTarget;
  children: ReactNode;
}) {
  return (
    <StudioContext.Provider value={{ ...services, writingMode, projectId, ...nav }}>
      {/*
        Generalize the writingMode → --accent pattern: scope `--accent` for the
        whole Studio tree. `display: contents` sets the custom property for all
        descendants without adding a layout box, so even a single panel rendered
        outside the dock shell still inherits the mode accent.
      */}
      <div style={{ display: "contents", ...accentVars(writingMode) }}>
        <SelectionProvider>{children}</SelectionProvider>
      </div>
    </StudioContext.Provider>
  );
}

/** Access the injected core API + platform adapter + active writing mode. */
export function useStudio(): StudioContextValue {
  const v = useContext(StudioContext);
  if (!v) throw new Error("useStudio() must be used inside <StudioProvider>.");
  return v;
}

/** The active writing mode (drives `--accent`); undefined outside a provider scope. */
export function useWritingMode(): WritingMode | string | undefined {
  return useContext(StudioContext)?.writingMode;
}

/** The active project id; undefined outside a provider scope or with no project open. */
export function useProjectId(): number | undefined {
  return useContext(StudioContext)?.projectId;
}

/** Switch panels / open a scene from any panel. No-op outside a provider or if the host didn't inject nav. */
export function useNavigate(): (panel: string, opts?: { sceneId?: number }) => void {
  const nav = useContext(StudioContext)?.navigate;
  return nav ?? (() => {});
}

/** Switch the active project from any panel (no-op outside a provider or if the host didn't inject it). */
export function useSelectProject(): (id: number) => void {
  const fn = useContext(StudioContext)?.selectProject;
  return fn ?? (() => {});
}

/** Ask the host to re-fetch its project list (after a create/rename/delete). */
export function useRefreshProjects(): () => void {
  const fn = useContext(StudioContext)?.refreshProjects;
  return fn ?? (() => {});
}

/** The scene the Manuscript editor should scroll to + focus, plus a clear() — consumed by ManuscriptEditor. */
export function useManuscriptTarget(): { sceneId: number | null; clear: () => void } {
  const ctx = useContext(StudioContext);
  return { sceneId: ctx?.manuscriptTargetSceneId ?? null, clear: ctx?.clearManuscriptTarget ?? (() => {}) };
}
