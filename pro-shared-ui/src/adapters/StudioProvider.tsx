import { createContext, useContext, type ReactNode } from "react";
import type { KnowledgeGraphViewMode, WritingMode } from "@logosforge/ui-contracts";
import type { ApiClient } from "./api";
import type { PlatformAdapter } from "./platform";
import { SelectionProvider } from "./selection";
import { accentVars } from "../theme/accent";

/** The two adapters every Studio component depends on, injected by the host app. */
export interface StudioServices {
  api: ApiClient;
  platform: PlatformAdapter;
}

/** Typed one-shot targets accepted by cross-panel navigation. */
export interface StudioNavigationOptions {
  sceneId?: number;
  psykeEntryId?: number;
  noteId?: number;
  commentId?: number;
  graphFocusKey?: string;
  graphViewMode?: KnowledgeGraphViewMode;
  graphIncludeInferred?: boolean;
  graphDepth?: 1 | 2;
  continuityIssueKey?: string;
  /** Proposal-only handoff into Billy; no AI call or manuscript write occurs. */
  continuityRepair?: ContinuityRepairTarget;
  aiTool?: string;
}

export interface ContinuityRepairTarget {
  /** Unique one-shot capability so a stale clear cannot consume a newer handoff. */
  handoffId: string;
  ownerProjectId: number;
  issueId: string;
  sceneId: number | null;
  draft: string;
}

export interface KnowledgeGraphNavigationTarget {
  focusKey: string;
  viewMode: KnowledgeGraphViewMode;
  includeInferred: boolean;
  depth: 1 | 2;
}

export interface NavTarget {
  /**
   * Open a workspace surface after the host's pending-save barrier. Hosts that
   * can observe that barrier return false when navigation was stopped; legacy
   * embedders may still return void.
   */
  navigate?: (
    panel: string,
    opts?: StudioNavigationOptions,
  ) => void | boolean | Promise<void | boolean>;
  manuscriptTargetSceneId?: number | null;
  clearManuscriptTarget?: (sceneId?: number) => void;
  /** PSYKE entry requested by an external surface such as the Console. */
  psykeTargetEntryId?: number | null;
  clearPsykeTarget?: (entryId?: number) => void;
  /** Note requested by an external surface such as the Omnibox. */
  noteTargetId?: number | null;
  clearNoteTarget?: (noteId?: number) => void;
  /** Comment thread requested by an external surface such as the Omnibox. */
  commentTargetId?: number | null;
  clearCommentTarget?: (commentId?: number) => void;
  /** Exact canonical graph neighborhood requested by Decision Radar or another surface. */
  knowledgeGraphTarget?: KnowledgeGraphNavigationTarget | null;
  clearKnowledgeGraphTarget?: (focusKey?: string) => void;
  /** Exact computed Semantic Continuity issue requested by another surface. */
  continuityTargetIssueKey?: string | null;
  clearContinuityTarget?: (issueKey?: string) => void;
  /** One-shot Continuity repair brief for the AI companion surface. */
  continuityRepairTarget?: ContinuityRepairTarget | null;
  clearContinuityRepairTarget?: (handoffId?: string) => void;
  /** Switch the active project (host owns projectId state). */
  selectProject?: (id: number) => Promise<boolean>;
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
        <SelectionProvider resetKey={projectId}>{children}</SelectionProvider>
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
export function useNavigate(): (
  panel: string,
  opts?: StudioNavigationOptions,
) => void | boolean | Promise<void | boolean> {
  const nav = useContext(StudioContext)?.navigate;
  return nav ?? (() => {});
}

/** Switch the active project from any panel (no-op outside a provider or if the host didn't inject it). */
export function useSelectProject(): (id: number) => Promise<boolean> {
  const fn = useContext(StudioContext)?.selectProject;
  return fn ?? (async () => false);
}

/** Ask the host to re-fetch its project list (after a create/rename/delete). */
export function useRefreshProjects(): () => void {
  const fn = useContext(StudioContext)?.refreshProjects;
  return fn ?? (() => {});
}

/** The scene the Manuscript editor should scroll to + focus, plus a clear() — consumed by ManuscriptEditor. */
export function useManuscriptTarget(): { sceneId: number | null; clear: () => void } {
  const ctx = useContext(StudioContext);
  const sceneId = ctx?.manuscriptTargetSceneId ?? null;
  return { sceneId, clear: () => ctx?.clearManuscriptTarget?.(sceneId ?? undefined) };
}

/** The PSYKE entry another surface asked the Bible to reveal. */
export function usePsykeTarget(): { entryId: number | null; clear: () => void } {
  const ctx = useContext(StudioContext);
  const entryId = ctx?.psykeTargetEntryId ?? null;
  return { entryId, clear: () => ctx?.clearPsykeTarget?.(entryId ?? undefined) };
}

/** The note another surface asked the Notes panel to open. */
export function useNoteTarget(): { noteId: number | null; clear: () => void } {
  const ctx = useContext(StudioContext);
  const noteId = ctx?.noteTargetId ?? null;
  return { noteId, clear: () => ctx?.clearNoteTarget?.(noteId ?? undefined) };
}

/** The thread another surface asked the Comments panel to reveal and focus. */
export function useCommentTarget(): { commentId: number | null; clear: () => void } {
  const ctx = useContext(StudioContext);
  const commentId = ctx?.commentTargetId ?? null;
  return { commentId, clear: () => ctx?.clearCommentTarget?.(commentId ?? undefined) };
}

/** The exact canonical graph neighborhood another surface asked Graph to reveal. */
export function useKnowledgeGraphTarget(): {
  target: KnowledgeGraphNavigationTarget | null;
  clear: () => void;
} {
  const ctx = useContext(StudioContext);
  const target = ctx?.knowledgeGraphTarget ?? null;
  return {
    target,
    clear: () => ctx?.clearKnowledgeGraphTarget?.(target?.focusKey),
  };
}

/** The exact current Semantic Continuity issue another surface asked to reveal. */
export function useContinuityTarget(): { issueKey: string | null; clear: () => void } {
  const ctx = useContext(StudioContext);
  const issueKey = ctx?.continuityTargetIssueKey ?? null;
  return {
    issueKey,
    clear: () => ctx?.clearContinuityTarget?.(issueKey ?? undefined),
  };
}

/** Proposal-only Continuity repair brief another surface asked Billy to stage. */
export function useContinuityRepairTarget(): {
  target: ContinuityRepairTarget | null;
  clear: () => void;
} {
  const ctx = useContext(StudioContext);
  const target = ctx?.continuityRepairTarget ?? null;
  return {
    target,
    clear: () => ctx?.clearContinuityRepairTarget?.(target?.handoffId),
  };
}
