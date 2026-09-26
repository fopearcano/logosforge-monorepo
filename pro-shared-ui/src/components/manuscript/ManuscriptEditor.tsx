import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import type { CommentReplyDTO, InlineCommentDTO, SceneDTO } from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useStudio, useManuscriptTarget, useNavigate } from "../../adapters/StudioProvider";
import { useSelection } from "../../adapters/selection";
import { useComments, useScenes } from "../../hooks";
import { classifyLines, renderLineText, fountainLineStyle } from "../../format/fountain";
import { ProseEditor, type ProseCommentHighlight, type ProseSelectionRange } from "./ProseEditor";
import { TitleCommentInput, type TitleCommentHighlight } from "./TitleCommentInput";
import {
  createMultiFieldCommentDraft,
  createSingleFieldCommentDraft,
  findOrphanedCommentIds,
  locateComment,
  reconcileCommentSpans,
  reconciledCommentPatch,
  type CommentAnchorDraft,
  type CommentSelectionEndpoint,
  type CommentSpan,
} from "./commentAnchors";
import {
  proseDomPointFromViewport,
  proseDomPointToTextOffset,
  proseRootForDomPoint,
} from "./commentDomSelection";
import { useHideResolvedPreference } from "./commentPreferences";
import {
  detectCommentAssistantMention,
  persistCommentAssistantReply,
} from "./commentAssistant";
import { absoluteTime, formatRelativeTime, isImportedSource } from "./commentPresentation";
import { createSceneSaveQueue, type SceneSaveQueue } from "./sceneSaveQueue";
import {
  flushPendingProjectSaves,
  markProjectSavePending,
  registerProjectFlusher,
  trackProjectWrite,
} from "../../adapters/projectSaveCoordinator";
import { ApiRequestError } from "../../adapters/httpApiClient";
import { useMountedRef } from "../../hooks/useMountedRef";
import { pruneSceneIds, pruneSceneRecord, touchWarmSceneIds } from "./manuscriptViewport";

/**
 * The Studio's genuine writing surface — a continuous, inline-editable manuscript.
 * Each scene autosaves to the core via `updateScene` (debounced) with per-scene save
 * state + live counts; reconciliation guards (edit-sequence + in-flight serialize)
 * keep a refetch from clobbering active typing. In script modes the FORMAT toggle
 * shows a LIVE screenplay-formatted preview of the active scene beside the plain
 * editor — edit on the left, see Fountain elements (scene heading / character /
 * dialogue / …) render live on the right. (A true in-textarea contentEditable was
 * prototyped but its cross-browser caret/paste/Firefox hazards made a read-only live
 * preview the robust choice.) Also: scene reorder/delete + cross-panel selection.
 * Large manuscripts keep only visible, active, recently used, or unsaved
 * ProseMirror instances mounted; off-screen scenes retain their state/save queue
 * and render as lightweight readable text until approached or activated.
 */

const SAVE_DEBOUNCE_MS = 800;
const SCRIPT_MODES = new Set(["screenplay", "stage_script", "stage", "series"]);

const panelBox: CSSProperties = {
  position: "relative", width: "100%", height: "100%",
  background: "radial-gradient(120% 70% at 50% 0%,var(--panel),var(--base))",
  border: "1px solid var(--line)", boxShadow: "0 16px 60px rgba(0,0,0,.6)",
  overflow: "hidden", display: "flex", flexDirection: "column",
};

const wordCount = (t: string) => (t.trim() ? t.trim().split(/\s+/).length : 0);
const actLabel = (act: string) => (/^act\b/i.test(act.trim()) ? act.trim() : `ACT ${act.trim()}`);

const message = (text: string) => (
  <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: "34px 0", textAlign: "center", fontSize: 12, color: "var(--txt3)", letterSpacing: ".04em" }}>{text}</div>
);

const linkBtn: CSSProperties = { background: "transparent", border: "none", padding: 0, font: "inherit", cursor: "pointer", letterSpacing: ".14em", fontSize: 9.5 };
const iconBtn: CSSProperties = { background: "transparent", border: "none", padding: "0 3px", font: "inherit", cursor: "pointer", color: "var(--txt3)", fontSize: 12, lineHeight: 1 };
const commentAction: CSSProperties = { ...linkBtn, padding: "5px 8px", border: "1px solid var(--line2)", background: "var(--panel2)", color: "var(--amber)", letterSpacing: ".1em", fontSize: 8.5 };
const commentPopover: CSSProperties = {
  position: "absolute", zIndex: 14, right: 0, top: 42, width: 320, maxWidth: "min(320px,90vw)",
  border: "1px solid var(--amber)", background: "var(--panel)", boxShadow: "0 16px 44px rgba(0,0,0,.72)",
  padding: 12, color: "var(--txt)", fontSize: 10,
};
const commentTextArea: CSSProperties = {
  width: "100%", minHeight: 66, resize: "vertical", boxSizing: "border-box",
  border: "1px solid var(--line2)", background: "var(--base)", color: "var(--txt)",
  padding: 8, font: "inherit", fontSize: 10.5, lineHeight: 1.5,
};

type SaveStatus = "idle" | "dirty" | "saving" | "saved" | "error";
interface SceneDraft {
  title: string;
  content: string;
  act: string;
  chapter: string;
  plotline: string;
  summary: string;
}
type FlushHandlers = { flush: () => Promise<boolean>; cancel: () => void };
type LiveSceneText = { title: string; content: string };
type LiveSceneTextStore = { projectId: number | null; byScene: Record<number, LiveSceneText> };
type ViewportAnchor = { left: number; right: number; top: number; bottom: number };
type ExternalCommentDraft = {
  requestId: number;
  projectId: number;
  sceneId: number;
  draft: CommentAnchorDraft;
  anchor: ViewportAnchor | null;
};
type CrossScenePointerStart = {
  root: HTMLElement;
  endpoint: CommentSelectionEndpoint;
  x: number;
  y: number;
};
type CommentOperation = {
  kind: "create" | "resolve" | "reply" | "assistant" | "delete-reply" | "delete-thread";
  commentId?: number;
  replyId?: number;
  assistantLabel?: "Assistant" | "Counterpart";
};

const viewportAnchorFromRect = (rect: Pick<DOMRect, "left" | "right" | "top" | "bottom">): ViewportAnchor => ({
  left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom,
});

function anchoredPopoverStyle(anchor: ViewportAnchor | null, width: number, heightHint: number): CSSProperties {
  if (typeof window === "undefined") return { ...commentPopover, position: "fixed", top: 64, right: 24, width };
  const gutter = 12;
  const availableWidth = Math.max(240, window.innerWidth - gutter * 2);
  const panelWidth = Math.min(width, availableWidth);
  if (!anchor) {
    return {
      ...commentPopover, position: "fixed", top: 64, right: gutter, width: panelWidth,
      maxWidth: availableWidth, maxHeight: "calc(100vh - 76px)", overflowY: "auto",
    };
  }
  const left = Math.min(Math.max(gutter, anchor.right - panelWidth), window.innerWidth - panelWidth - gutter);
  const below = anchor.bottom + 8;
  const top = below + heightHint <= window.innerHeight - gutter
    ? below
    : Math.max(gutter, anchor.top - heightHint - 8);
  return {
    ...commentPopover, position: "fixed", top, left, right: "auto", width: panelWidth,
    maxWidth: availableWidth, maxHeight: `calc(100vh - ${top + gutter}px)`, overflowY: "auto",
  };
}

function anchoredCommentButtonStyle(anchor: ViewportAnchor | null): CSSProperties {
  if (typeof window === "undefined" || !anchor) return { ...commentAction, position: "absolute", right: 0, top: 42, zIndex: 12 };
  const width = 104;
  const left = Math.min(Math.max(8, anchor.right + 7), window.innerWidth - width - 8);
  const top = Math.min(Math.max(8, anchor.bottom + 7), window.innerHeight - 36);
  return { ...commentAction, position: "fixed", left, top, zIndex: 16, boxShadow: "0 8px 24px rgba(0,0,0,.55)" };
}

function commentSelectionEndpointFromDomPoint(
  root: HTMLElement,
  container: Node,
  offset: number,
): CommentSelectionEndpoint | null {
  const sceneElement = root.closest<HTMLElement>("[data-scene-id]");
  const sceneId = Number(sceneElement?.dataset.sceneId);
  const textOffset = proseDomPointToTextOffset(root, container, offset);
  if (!Number.isSafeInteger(sceneId) || textOffset == null) return null;
  return { sceneId, field: "content", offset: textOffset };
}

function viewportAnchorForSelectionRange(range: Range): ViewportAnchor | null {
  const rects = Array.from(range.getClientRects()).filter((rect) => rect.width > 0 || rect.height > 0);
  const rect = rects.at(-1) ?? range.getBoundingClientRect();
  return rect.width > 0 || rect.height > 0 ? viewportAnchorFromRect(rect) : null;
}
const STATUS_GLYPH: Record<SaveStatus, { g: string; c: string; t: string }> = {
  idle: { g: "", c: "var(--txt3)", t: "" },
  dirty: { g: "●", c: "var(--amber)", t: "unsaved" },
  saving: { g: "⋯", c: "var(--accent)", t: "saving…" },
  saved: { g: "✓", c: "var(--green)", t: "saved" },
  error: { g: "!", c: "var(--crimson)", t: "save failed — keeps the change; retries on the next edit / blur" },
};

const ActDivider = ({ scene }: { scene: SceneDTO }) => (
  <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "0 0 18px" }}>
    <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 10, letterSpacing: ".3em", color: "var(--accent)" }}>
      {actLabel(scene.act)}{scene.chapter ? ` · ${scene.chapter}` : ""}
    </span>
    <span style={{ flex: 1, height: 1, background: "var(--line2)" }} />
  </div>
);

function SceneStaticProse({
  content,
  title,
  onActivate,
}: {
  content: string;
  title: string;
  onActivate: () => void;
}) {
  return (
    <button
      type="button"
      data-prose-static
      onClick={onActivate}
      aria-label={`Activate prose editor for ${title || "untitled scene"}`}
      title="Click to edit this scene"
      style={{ display: "block", width: "100%", minHeight: "1.62em", border: "1px solid transparent", background: "transparent", color: "var(--txt)", padding: 0, textAlign: "left", fontFamily: "'Courier Prime',monospace", fontSize: 15, lineHeight: 1.62, cursor: "text" }}
    >
      {!content
        ? <span style={{ color: "var(--txt3)" }}>Write the scene…</span>
        : <span style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{content}</span>}
    </button>
  );
}

// --------------------------------------------------------------- Scene editor
function SceneEditor({
  scene, index, showAct, formatted, mode, busy, onWords, onContent, onStatus, onActive, registerFlush,
  onDelete, onMoveUp, onMoveDown, isFirst, isLast, renderProse, registerSceneNode, onRequestEdit,
  commentSpans, comments, openCommentIds, onOpenComments, onCommentsChanged, onCommentCreated, onLiveText,
  activeCommentDraftSceneId, onCommentDraftOwnership, externalCommentDraft, onExternalCommentDraftConsumed,
}: {
  scene: SceneDTO; index: number; showAct: boolean; formatted: boolean; mode: string; busy: boolean;
  onWords: (id: number, n: number) => void;
  onContent: (id: number, c: string) => void;
  onStatus: (ownerProjectId: number | null, id: number, s: SaveStatus) => void;
  onActive: (id: number) => void;
  registerFlush: (id: number, h: FlushHandlers | null) => void;
  onDelete: () => void; onMoveUp: () => void; onMoveDown: () => void;
  isFirst: boolean; isLast: boolean;
  renderProse: boolean;
  registerSceneNode: (id: number, node: HTMLDivElement | null) => void;
  onRequestEdit: (id: number) => void;
  commentSpans: CommentSpan[];
  comments: InlineCommentDTO[];
  openCommentIds: number[];
  onOpenComments: (ids: number[]) => void;
  onCommentsChanged: () => void;
  onCommentCreated: () => void;
  onLiveText: (ownerProjectId: number | null, id: number, value: LiveSceneText) => void;
  activeCommentDraftSceneId: number | null;
  onCommentDraftOwnership: (sceneId: number | null) => void;
  externalCommentDraft: ExternalCommentDraft | null;
  onExternalCommentDraftConsumed: (requestId: number) => void;
}) {
  const { api, projectId } = useStudio();
  const navigate = useNavigate();
  // A SceneEditor belongs to the project it mounted under. Keep that owner id
  // even if a host accidentally rerenders once with a new active project before
  // this old scene unmounts.
  const ownerProjectId = useRef<number | null>(projectId ?? null).current;
  const { setSelection } = useSelection();
  const [title, setTitle] = useState(scene.title ?? "");
  const [content, setContent] = useState(scene.content ?? "");
  const [act, setAct] = useState(scene.act ?? "");
  const [chapter, setChapter] = useState(scene.chapter ?? "");
  const [plotline, setPlotline] = useState(scene.plotline ?? "");
  const [summary, setSummary] = useState(scene.summary ?? "");
  const [showDetails, setShowDetails] = useState(false);
  const [status, setStatus] = useState<SaveStatus>("idle");
  const [saveConflict, setSaveConflict] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [resolvingConflict, setResolvingConflict] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  const [commentDraft, setCommentDraft] = useState<CommentAnchorDraft | null>(null);
  const [commentComposerOpen, setCommentComposerOpen] = useState(false);
  const [commentBody, setCommentBody] = useState("");
  const [commentBusy, setCommentBusy] = useState(false);
  const [commentError, setCommentError] = useState("");
  const [commentOperation, setCommentOperation] = useState<CommentOperation | null>(null);
  const [replyDrafts, setReplyDrafts] = useState<Record<number, string>>({});
  const [confirmDeleteCommentId, setConfirmDeleteCommentId] = useState<number | null>(null);
  const [deletedReplyIds, setDeletedReplyIds] = useState<Set<number>>(() => new Set());
  const [commentDraftAnchor, setCommentDraftAnchor] = useState<ViewportAnchor | null>(null);
  const [commentMarkAnchor, setCommentMarkAnchor] = useState<ViewportAnchor | null>(null);
  const [commentClock, setCommentClock] = useState(Date.now);
  const timer = useRef<number | null>(null);
  const mounted = useMountedRef();
  const sceneElementRef = useRef<HTMLDivElement | null>(null);
  const commentCloseRef = useRef<HTMLButtonElement | null>(null);
  const commentPopoverRef = useRef<HTMLElement | null>(null);
  const commentConfirmDeleteRef = useRef<HTMLButtonElement | null>(null);
  const commentReturnFocusRef = useRef<HTMLElement | null>(null);
  const replyComposerRefs = useRef(new Map<number, HTMLTextAreaElement>());
  const deleteThreadButtonRefs = useRef(new Map<number, HTMLButtonElement>());
  const lastPointerRef = useRef<{ x: number; y: number; at: number } | null>(null);
  const sceneNodeRef = useCallback((node: HTMLDivElement | null) => {
    sceneElementRef.current = node;
    registerSceneNode(scene.id, node);
  }, [registerSceneNode, scene.id]);

  const setStat = useCallback((s: SaveStatus) => { if (!mounted.current) return; setStatus(s); onStatus(ownerProjectId, scene.id, s); }, [onStatus, ownerProjectId, scene.id]);
  const statusRef = useRef(setStat);
  statusRef.current = setStat;
  const draftRef = useRef<SceneDraft>({ title, content, act, chapter, plotline, summary });
  const revisionRef = useRef(scene.revision ?? "");
  const forceOverwriteRef = useRef(false);
  const writeRef = useRef<(draft: SceneDraft) => Promise<void>>(async () => {});
  writeRef.current = async (draft) => {
    if (ownerProjectId == null) throw new Error("No owning project for this scene.");
    const force = forceOverwriteRef.current;
    forceOverwriteRef.current = false;
    try {
      const updated = await trackProjectWrite(api.updateScene(ownerProjectId, scene.id, {
        ...draft,
        ...(!force && revisionRef.current ? { expected_revision: revisionRef.current } : {}),
      }));
      revisionRef.current = updated.revision ?? "";
      if (mounted.current) { setSaveConflict(false); setSaveError(""); }
    } catch (error) {
      if (mounted.current) {
        setSaveError(error instanceof Error ? error.message : String(error));
        if (error instanceof ApiRequestError && error.code === "scene_conflict") setSaveConflict(true);
      }
      throw error;
    }
  };
  const queueRef = useRef<SceneSaveQueue<SceneDraft> | null>(null);
  if (!queueRef.current) {
    queueRef.current = createSceneSaveQueue({
      initial: draftRef.current,
      write: (draft) => writeRef.current(draft),
      onStatus: (next) => statusRef.current(next),
      onDirty: markProjectSavePending,
    });
  }
  // report word count + live content (for the FORMAT preview) upward
  useEffect(() => { onWords(scene.id, wordCount(content)); onContent(scene.id, content); }, [content, onWords, onContent, scene.id]);
  useEffect(() => { onContent(scene.id, content); }, [formatted, onContent, scene.id]);
  // Comment marks use the editor's live UTF-16 coordinate space. Publishing both
  // fields keeps relocation correct before the debounced scene refetch catches up.
  useEffect(() => {
    onLiveText(ownerProjectId, scene.id, { title, content });
  }, [content, onLiveText, ownerProjectId, scene.id, title]);

  useEffect(() => {
    const queue = queueRef.current!;
    if (!queue.isDirty()) {
      const next = {
        title: scene.title ?? "", content: scene.content ?? "",
        act: scene.act ?? "", chapter: scene.chapter ?? "",
        plotline: scene.plotline ?? "", summary: scene.summary ?? "",
      };
      setTitle(scene.title ?? ""); setContent(scene.content ?? "");
      setAct(scene.act ?? ""); setChapter(scene.chapter ?? ""); setPlotline(scene.plotline ?? ""); setSummary(scene.summary ?? "");
      draftRef.current = next;
      revisionRef.current = scene.revision ?? "";
      setSaveConflict(false); setSaveError("");
      queue.reset(next);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scene.id, scene.title, scene.content, scene.act, scene.chapter, scene.plotline, scene.summary, scene.revision]);

  const schedule = (patch: Partial<SceneDraft>) => {
    const next = { ...draftRef.current, ...patch };
    draftRef.current = next;
    queueRef.current!.update(next);
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      timer.current = null;
      void queueRef.current!.flush();
    }, SAVE_DEBOUNCE_MS);
  };
  const flushNow = useCallback(async (): Promise<boolean> => {
    if (timer.current !== null) { clearTimeout(timer.current); timer.current = null; }
    return queueRef.current?.flush() ?? true;
  }, []);
  const cancelSave = useCallback(() => {
    if (timer.current !== null) { clearTimeout(timer.current); timer.current = null; }
    queueRef.current?.cancel();
  }, []);
  const reloadAfterConflict = useCallback(async () => {
    if (ownerProjectId == null || resolvingConflict) return;
    const localAtStart = draftRef.current;
    setResolvingConflict(true);
    try {
      const latest = (await api.listScenes(ownerProjectId)).find((item) => item.id === scene.id);
      if (!latest) throw new Error("The scene no longer exists.");
      if (draftRef.current !== localAtStart) {
        throw new Error("The local draft changed while reloading. Review it and choose again.");
      }
      if (timer.current !== null) { clearTimeout(timer.current); timer.current = null; }
      const next: SceneDraft = {
        title: latest.title ?? "", content: latest.content ?? "", act: latest.act ?? "",
        chapter: latest.chapter ?? "", plotline: latest.plotline ?? "", summary: latest.summary ?? "",
      };
      setTitle(next.title); setContent(next.content); setAct(next.act);
      setChapter(next.chapter); setPlotline(next.plotline); setSummary(next.summary);
      draftRef.current = next;
      revisionRef.current = latest.revision ?? "";
      queueRef.current?.reset(next);
      setSaveConflict(false); setSaveError(""); setStat("saved");
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : String(error));
    } finally {
      setResolvingConflict(false);
    }
  }, [api, ownerProjectId, resolvingConflict, scene.id, setStat]);
  const overwriteAfterConflict = useCallback(async () => {
    if (resolvingConflict) return;
    setResolvingConflict(true);
    forceOverwriteRef.current = true;
    try {
      await flushNow();
    } finally {
      forceOverwriteRef.current = false;
      setResolvingConflict(false);
    }
  }, [flushNow, resolvingConflict]);
  useEffect(() => {
    registerFlush(scene.id, { flush: flushNow, cancel: cancelSave });
    const unregisterProjectFlusher = registerProjectFlusher(flushNow);
    return () => {
      unregisterProjectFlusher();
      registerFlush(scene.id, null);
      void flushNow();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const lastPub = useRef("");
  const publishText = useCallback((text: string) => {
    const key = `${scene.id}:${text}`;
    if (key === lastPub.current) return;
    lastPub.current = key;
    setSelection({ sceneId: scene.id, text, section: "Manuscript" });
  }, [scene.id, setSelection]);

  const proseHighlights = useMemo<ProseCommentHighlight[]>(() => commentSpans
    .filter((span) => span.field === "content")
    .map((span) => ({
      commentId: span.commentId,
      fromOffset: span.fromOffset,
      toOffset: span.toOffset,
      resolved: span.resolved,
    })), [commentSpans]);
  const titleHighlights = useMemo<TitleCommentHighlight[]>(() => commentSpans
    .filter((span) => span.field === "title")
    .map((span) => ({
      commentId: span.commentId,
      fromOffset: span.fromOffset,
      toOffset: span.toOffset,
      resolved: span.resolved,
    })), [commentSpans]);
  const titleHighlighted = titleHighlights.length > 0;
  const activeComments = openCommentIds
    .map((id) => comments.find((comment) => comment.id === id))
    .filter((comment): comment is InlineCommentDTO => Boolean(comment));
  const openCommentIdsKey = openCommentIds.join(",");

  const restoreCommentFocus = useCallback(() => {
    const target = commentReturnFocusRef.current;
    commentReturnFocusRef.current = null;
    if (target?.isConnected) window.setTimeout(() => target.focus({ preventScroll: true }), 0);
  }, []);

  const closeCommentPopover = useCallback(() => {
    setConfirmDeleteCommentId(null);
    setCommentError("");
    onOpenComments([]);
    restoreCommentFocus();
  }, [onOpenComments, restoreCommentFocus]);

  const clearCommentDraft = useCallback((restoreFocus = false) => {
    setCommentDraft(null);
    setCommentComposerOpen(false);
    setCommentBody("");
    setCommentDraftAnchor(null);
    onCommentDraftOwnership(null);
    if (restoreFocus) restoreCommentFocus();
  }, [onCommentDraftOwnership, restoreCommentFocus]);

  const findCommentMarkAnchor = useCallback((ids: readonly number[]): ViewportAnchor | null => {
    const root = sceneElementRef.current;
    if (!root || ids.length === 0) return null;
    const requested = new Set(ids);
    const candidates = Array.from(root.querySelectorAll<HTMLElement>("[data-comment-ids]"))
      .filter((element) => (element.dataset.commentIds ?? "").split(",").map(Number).some((id) => requested.has(id)))
      .map((element) => ({ element, rect: element.getBoundingClientRect() }))
      .filter(({ rect }) => rect.width > 0 || rect.height > 0);
    if (!candidates.length) return null;
    const pointer = lastPointerRef.current;
    const pointed = pointer && Date.now() - pointer.at < 1_000
      ? candidates.find(({ rect }) => pointer.x >= rect.left && pointer.x <= rect.right && pointer.y >= rect.top && pointer.y <= rect.bottom)
      : undefined;
    const viewportMiddle = window.innerHeight / 2;
    const visible = candidates.filter(({ rect }) => rect.bottom >= 0 && rect.top <= window.innerHeight);
    const selected = pointed ?? (visible.length ? visible : candidates)
      .slice()
      .sort((left, right) => Math.abs((left.rect.top + left.rect.bottom) / 2 - viewportMiddle) - Math.abs((right.rect.top + right.rect.bottom) / 2 - viewportMiddle))[0];
    return selected ? viewportAnchorFromRect(selected.rect) : null;
  }, []);

  const openCommentThreads = useCallback((ids: number[], explicitAnchor?: ViewportAnchor) => {
    if (!ids.length) return;
    if (document.activeElement instanceof HTMLElement && !commentPopoverRef.current?.contains(document.activeElement)) {
      commentReturnFocusRef.current = document.activeElement;
    }
    clearCommentDraft(false);
    setCommentError("");
    setCommentMarkAnchor(explicitAnchor ?? findCommentMarkAnchor(ids));
    onOpenComments(ids);
  }, [clearCommentDraft, findCommentMarkAnchor, onOpenComments]);

  useEffect(() => {
    if (
      !externalCommentDraft
      || externalCommentDraft.projectId !== ownerProjectId
      || externalCommentDraft.sceneId !== scene.id
    ) return;
    if (document.activeElement instanceof HTMLElement) commentReturnFocusRef.current = document.activeElement;
    onCommentDraftOwnership(scene.id);
    onOpenComments([]);
    setCommentDraft(externalCommentDraft.draft);
    setCommentDraftAnchor(externalCommentDraft.anchor);
    setCommentComposerOpen(false);
    setCommentBody("");
    setCommentError("");
    onExternalCommentDraftConsumed(externalCommentDraft.requestId);
  }, [externalCommentDraft, onCommentDraftOwnership, onExternalCommentDraftConsumed, onOpenComments, ownerProjectId, scene.id]);

  useEffect(() => {
    if (activeCommentDraftSceneId === scene.id) return;
    setCommentDraft(null);
    setCommentComposerOpen(false);
    setCommentBody("");
    setCommentDraftAnchor(null);
  }, [activeCommentDraftSceneId, scene.id]);

  useEffect(() => {
    if (!openCommentIdsKey) {
      setConfirmDeleteCommentId(null);
      setCommentMarkAnchor(null);
      return undefined;
    }
    if (document.activeElement instanceof HTMLElement && !commentPopoverRef.current?.contains(document.activeElement)) {
      commentReturnFocusRef.current = document.activeElement;
    }
    setCommentMarkAnchor(findCommentMarkAnchor(openCommentIds));
    const timer = window.setTimeout(() => commentCloseRef.current?.focus({ preventScroll: true }), 0);
    return () => window.clearTimeout(timer);
    // openCommentIdsKey is the stable identity; the array is recreated by render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [findCommentMarkAnchor, openCommentIdsKey]);

  useEffect(() => {
    setDeletedReplyIds((current) => {
      const serverIds = new Set(activeComments.flatMap((comment) => comment.replies.map((reply) => reply.id)));
      const next = new Set([...current].filter((id) => serverIds.has(id)));
      return next.size === current.size ? current : next;
    });
  }, [comments, openCommentIdsKey]);

  useEffect(() => {
    if (!openCommentIdsKey) return undefined;
    setCommentClock(Date.now());
    const timer = window.setInterval(() => setCommentClock(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, [openCommentIdsKey]);

  useEffect(() => {
    if (confirmDeleteCommentId == null) return undefined;
    const timer = window.setTimeout(() => commentConfirmDeleteRef.current?.focus({ preventScroll: true }), 0);
    return () => window.clearTimeout(timer);
  }, [confirmDeleteCommentId]);

  useEffect(() => {
    if (!commentDraft && !openCommentIdsKey) return undefined;
    let frame: number | null = null;
    const onViewportChange = (event: Event) => {
      const target = event.target;
      if (target instanceof Node && commentPopoverRef.current?.contains(target)) return;
      if (commentDraft && !commentComposerOpen && !commentBusy) clearCommentDraft(false);
      if (openCommentIds.length) {
        if (frame != null) window.cancelAnimationFrame(frame);
        frame = window.requestAnimationFrame(() => {
          frame = null;
          setCommentMarkAnchor(findCommentMarkAnchor(openCommentIds));
        });
      }
    };
    window.addEventListener("scroll", onViewportChange, true);
    window.addEventListener("resize", onViewportChange);
    return () => {
      window.removeEventListener("scroll", onViewportChange, true);
      window.removeEventListener("resize", onViewportChange);
      if (frame != null) window.cancelAnimationFrame(frame);
    };
  }, [clearCommentDraft, commentBusy, commentComposerOpen, commentDraft, findCommentMarkAnchor, openCommentIds, openCommentIdsKey]);

  const captureCommentSelection = (field: "content" | "title", fromOffset: number, toOffset: number, anchor?: ViewportAnchor) => {
    if (commentComposerOpen) return;
    const draft = createSingleFieldCommentDraft({ ...scene, title, content }, field, fromOffset, toOffset);
    if (document.activeElement instanceof HTMLElement) commentReturnFocusRef.current = document.activeElement;
    onCommentDraftOwnership(scene.id);
    onOpenComments([]);
    setCommentDraft(draft);
    setCommentDraftAnchor(anchor ?? null);
    setCommentError("");
  };

  const captureProseCommentSelection = (range: ProseSelectionRange | null) => {
    if (!range) {
      if (!commentComposerOpen && activeCommentDraftSceneId === scene.id) clearCommentDraft(false);
      return;
    }
    const selection = window.getSelection();
    const domRange = selection?.rangeCount ? selection.getRangeAt(0) : null;
    const rect = domRange?.getBoundingClientRect();
    captureCommentSelection(
      "content",
      range.fromOffset,
      range.toOffset,
      rect && (rect.width > 0 || rect.height > 0) ? viewportAnchorFromRect(rect) : undefined,
    );
  };

  const submitComment = async () => {
    if (ownerProjectId == null || !commentDraft || !commentBody.trim() || commentBusy) return;
    const writerMessage = commentBody.trim();
    setCommentBusy(true);
    setCommentOperation({ kind: "create" });
    setCommentError("");
    try {
      const spansMultipleFields = commentDraft.anchor.start_scene_id !== commentDraft.anchor.end_scene_id
        || commentDraft.anchor.start_field !== commentDraft.anchor.end_field;
      if (spansMultipleFields) {
        await flushPendingProjectSaves();
      } else {
        const saved = await flushNow();
        if (!saved) throw new Error("Save this scene before attaching a comment.");
      }
      const created = await trackProjectWrite(api.createComment(ownerProjectId, {
        anchor: commentDraft.anchor,
        quote: commentDraft.quote,
        body: writerMessage,
      }));
      const mention = detectCommentAssistantMention(writerMessage);
      setCommentBody("");
      setCommentDraft(null);
      setCommentDraftAnchor(null);
      setCommentComposerOpen(false);
      onCommentDraftOwnership(null);
      onCommentCreated();
      onOpenComments([created.id]);
      if (mention) {
        try {
          const assistantLabel = mention === "counterpart" ? "Counterpart" : "Assistant";
          setCommentOperation({ kind: "assistant", commentId: created.id, assistantLabel });
          await persistCommentAssistantReply(api, ownerProjectId, created, writerMessage, mention);
          onCommentsChanged();
        } catch (assistantError) {
          setCommentError(`Comment saved, but ${mention} couldn't reply — ${assistantError instanceof Error ? assistantError.message : String(assistantError)}`);
        }
      }
    } catch (error) {
      setCommentError(`Couldn't create the comment — ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setCommentBusy(false);
      setCommentOperation(null);
    }
  };

  const toggleCommentResolved = async (comment: InlineCommentDTO) => {
    if (ownerProjectId == null || commentBusy) return;
    setCommentBusy(true);
    setCommentOperation({ kind: "resolve", commentId: comment.id });
    setCommentError("");
    try {
      await trackProjectWrite(api.updateComment(ownerProjectId, comment.id, { resolved: !comment.resolved }));
      onCommentsChanged();
    } catch (error) {
      setCommentError(`Couldn't update the comment — ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setCommentBusy(false);
      setCommentOperation(null);
    }
  };

  const submitCommentReply = async (comment: InlineCommentDTO) => {
    if (ownerProjectId == null || commentBusy) return;
    const writerMessage = (replyDrafts[comment.id] ?? "").trim();
    if (!writerMessage) return;
    const mention = detectCommentAssistantMention(writerMessage);
    setCommentBusy(true);
    setCommentOperation({ kind: "reply", commentId: comment.id });
    setCommentError("");
    let nativeReplySaved = false;
    try {
      await trackProjectWrite(api.createCommentReply(ownerProjectId, comment.id, { body: writerMessage, author: "you" }));
      nativeReplySaved = true;
      setReplyDrafts((current) => ({ ...current, [comment.id]: "" }));
      onCommentsChanged();
      if (mention) {
        const assistantLabel = mention === "counterpart" ? "Counterpart" : "Assistant";
        setCommentOperation({ kind: "assistant", commentId: comment.id, assistantLabel });
        await persistCommentAssistantReply(api, ownerProjectId, comment, writerMessage, mention);
        onCommentsChanged();
      }
    } catch (error) {
      const label = mention === "counterpart" ? "Counterpart" : "Assistant";
      setCommentError(nativeReplySaved && mention
        ? `Your reply was saved, but ${label} couldn't answer — ${error instanceof Error ? error.message : String(error)}`
        : `Couldn't post the reply — ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setCommentBusy(false);
      setCommentOperation(null);
      window.setTimeout(() => replyComposerRefs.current.get(comment.id)?.focus({ preventScroll: true }), 0);
    }
  };

  const deleteCommentReply = async (comment: InlineCommentDTO, reply: CommentReplyDTO) => {
    if (ownerProjectId == null || commentBusy) return;
    setCommentBusy(true);
    setCommentOperation({ kind: "delete-reply", commentId: comment.id, replyId: reply.id });
    setCommentError("");
    try {
      await trackProjectWrite(api.deleteCommentReply(ownerProjectId, comment.id, reply.id));
      setDeletedReplyIds((current) => new Set(current).add(reply.id));
      onCommentsChanged();
    } catch (error) {
      setCommentError(`Couldn't delete the reply — ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setCommentBusy(false);
      setCommentOperation(null);
      window.setTimeout(() => replyComposerRefs.current.get(comment.id)?.focus({ preventScroll: true }), 0);
    }
  };

  const deleteCommentThread = async (comment: InlineCommentDTO) => {
    if (ownerProjectId == null || commentBusy || confirmDeleteCommentId !== comment.id) return;
    setCommentBusy(true);
    setCommentOperation({ kind: "delete-thread", commentId: comment.id });
    setCommentError("");
    try {
      await trackProjectWrite(api.deleteComment(ownerProjectId, comment.id));
      const remaining = openCommentIds.filter((id) => id !== comment.id);
      setConfirmDeleteCommentId(null);
      onOpenComments(remaining);
      onCommentsChanged();
      if (!remaining.length) restoreCommentFocus();
    } catch (error) {
      setCommentError(`Couldn't delete the thread — ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setCommentBusy(false);
      setCommentOperation(null);
    }
  };

  const st = STATUS_GLYPH[status];
  // content-visibility:auto establishes layout/paint containment, which also
  // changes the containing block for our viewport-positioned comment overlays.
  // Lift containment while this scene owns a FAB/composer/thread popover so
  // fixed coordinates stay viewport-relative and the overlay cannot be culled.
  const commentOverlayActive = commentDraft != null || activeComments.length > 0;
  const keepLiveEditor = renderProse || saveConflict || status === "dirty" || status === "saving" || status === "error";
  return (
    <div
      ref={sceneNodeRef}
      id={`ms-scene-${scene.id}`}
      data-scene-id={scene.id}
      data-scene-prose={keepLiveEditor ? "live" : "static"}
      onPointerDownCapture={(event) => { lastPointerRef.current = { x: event.clientX, y: event.clientY, at: Date.now() }; }}
      style={{ position: "relative", marginBottom: 30, scrollMarginTop: 18, contentVisibility: commentOverlayActive ? "visible" : "auto", containIntrinsicSize: "auto 360px" }}
    >
      {showAct && scene.act && <ActDivider scene={scene} />}
      <div style={{ display: "flex", gap: 12, alignItems: "baseline", marginBottom: 10 }}>
        <span style={{ fontFamily: "'Chakra Petch'", color: "var(--txt3)", fontSize: 13, flex: "none" }}>{index + 1}</span>
        <TitleCommentInput
          value={title}
          highlights={titleHighlights}
          onChange={(e) => {
            const nextTitle = e.target.value;
            setTitle(nextTitle);
            onLiveText(ownerProjectId, scene.id, { title: nextTitle, content });
            schedule({ title: nextTitle });
          }}
          onFocus={() => { onActive(scene.id); onContent(scene.id, content); }}
          onCommentActivate={(commentIds, event) => {
            const rect = event.currentTarget.getBoundingClientRect();
            openCommentThreads(commentIds, {
              left: event.clientX,
              right: event.clientX,
              top: rect.top,
              bottom: rect.bottom,
            });
          }}
          onSelect={(event) => {
            const from = event.currentTarget.selectionStart ?? 0;
            const to = event.currentTarget.selectionEnd ?? from;
            if (to > from) {
              const rect = event.currentTarget.getBoundingClientRect();
              const centerRatio = title.length ? Math.min(1, Math.max(0, ((from + to) / 2) / title.length)) : .5;
              const center = rect.left + rect.width * centerRatio;
              captureCommentSelection("title", from, to, { left: center, right: center, top: rect.top, bottom: rect.bottom });
            } else if (!commentComposerOpen && activeCommentDraftSceneId === scene.id) clearCommentDraft(false);
          }}
          onBlur={() => void flushNow()}
          placeholder="UNTITLED SCENE"
          ariaLabel={`Scene ${index + 1} title`}
          spellCheck={false}
        />
        {titleHighlighted && (
          <button
            type="button"
            aria-label={`Open comments on scene ${index + 1} title`}
            title="Open title comment"
            onClick={(event) => openCommentThreads(
              commentSpans.filter((span) => span.field === "title").map((span) => span.commentId),
              viewportAnchorFromRect(event.currentTarget.getBoundingClientRect()),
            )}
            style={{ ...iconBtn, color: "var(--amber)" }}
          >◈</button>
        )}
        <span title={st.t} style={{ flex: "none", fontSize: 11, color: st.c, minWidth: 12, textAlign: "right" }}>{st.g}</span>
        {confirmDel ? (
          <span style={{ display: "flex", gap: 4, alignItems: "center", flex: "none", fontSize: 9 }}>
            <span style={{ color: "var(--txt3)" }}>delete?</span>
            <button type="button" aria-label="Confirm delete scene" onClick={onDelete} style={{ ...iconBtn, color: "var(--crimson)" }}>✓</button>
            <button type="button" aria-label="Cancel delete" onClick={() => setConfirmDel(false)} style={iconBtn}>✗</button>
          </span>
        ) : (
          <span style={{ display: "flex", gap: 2, alignItems: "center", flex: "none" }}>
            <button type="button" aria-label="Scene details" title="Act / chapter / summary" onClick={() => setShowDetails((v) => !v)} style={{ ...iconBtn, color: showDetails ? "var(--accent)" : "var(--txt3)" }}>⋮</button>
            <button type="button" aria-label="Move scene up" disabled={isFirst || busy} onClick={onMoveUp} style={{ ...iconBtn, opacity: isFirst || busy ? 0.25 : 1 }}>↑</button>
            <button type="button" aria-label="Move scene down" disabled={isLast || busy} onClick={onMoveDown} style={{ ...iconBtn, opacity: isLast || busy ? 0.25 : 1 }}>↓</button>
            <button type="button" aria-label="Delete scene" onClick={() => setConfirmDel(true)} style={iconBtn}>✕</button>
          </span>
        )}
      </div>
      {saveConflict && (
        <div role="alert" style={{ display: "flex", alignItems: "center", gap: 8, margin: "-2px 0 10px 25px", padding: "7px 9px", border: "1px solid var(--crimson)", background: "rgba(255,82,96,.08)", color: "var(--txt2)", fontSize: 9.5 }}>
          <span style={{ flex: 1 }}>This scene changed elsewhere. Your local draft is preserved.{saveError ? ` ${saveError}` : ""}</span>
          <button type="button" disabled={resolvingConflict} onClick={() => void reloadAfterConflict()} style={{ ...linkBtn, color: "var(--txt2)" }}>DISCARD LOCAL · RELOAD</button>
          <button type="button" disabled={resolvingConflict} onClick={() => void overwriteAfterConflict()} style={{ ...linkBtn, color: "var(--crimson)" }}>OVERWRITE NEWER VERSION</button>
        </div>
      )}
      {!saveConflict && status === "error" && saveError && (
        <div role="alert" style={{ margin: "-2px 0 10px 25px", color: "var(--crimson)", fontSize: 9.5 }}>Save failed · {saveError}</div>
      )}
      {showDetails && (
        <div style={{ display: "flex", gap: 10, margin: "0 0 12px", flexWrap: "wrap", alignItems: "center" }}>
          {([["ACT", act, setAct, "e.g. Act I", 90], ["CHAPTER", chapter, setChapter, "e.g. 1", 90], ["PLOTLINE", plotline, setPlotline, "e.g. A-plot", 110], ["SUMMARY", summary, setSummary, "one-line scene summary", 300]] as const).map(([label, val, setter, ph, w]) => (
            <label key={label} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 8, letterSpacing: ".14em", color: "var(--txt3)" }}>
              {label}
              <input
                value={val}
                onChange={(e) => {
                  setter(e.target.value);
                  const field = label === "ACT" ? "act" : label === "CHAPTER" ? "chapter" : label === "PLOTLINE" ? "plotline" : "summary";
                  schedule({ [field]: e.target.value });
                }}
                onFocus={() => { onActive(scene.id); onContent(scene.id, content); }}
                onBlur={() => void flushNow()}
                placeholder={ph}
                aria-label={`Scene ${index + 1} ${label.toLowerCase()}`}
                style={{ width: w, background: "var(--tint)", border: "1px solid var(--line2)", outline: "none", color: "var(--txt)", fontFamily: "inherit", fontSize: 11, padding: "5px 8px" }}
              />
            </label>
          ))}
        </div>
      )}
      {keepLiveEditor
        ? <ProseEditor
          value={content}
          onChange={(v) => {
            setContent(v);
            onLiveText(ownerProjectId, scene.id, { title, content: v });
            schedule({ content: v });
          }}
          onFocusActive={() => { onActive(scene.id); onContent(scene.id, content); publishText(""); }}
          onSelectionText={publishText}
          onSelectionRange={captureProseCommentSelection}
          commentHighlights={proseHighlights}
          onCommentActivate={openCommentThreads}
          onBlur={() => void flushNow()}
          formatted={formatted}
          mode={mode}
          placeholder="Write the scene…"
        />
        : <SceneStaticProse content={content} title={title} onActivate={() => onRequestEdit(scene.id)} />}
      {commentDraft && !commentComposerOpen && activeComments.length === 0 && (
        <button
          type="button"
          aria-label={`Comment on selected text “${commentDraft.quote.slice(0, 60)}”`}
          onPointerDown={(event) => event.preventDefault()}
          onPointerUp={(event) => { event.stopPropagation(); setCommentComposerOpen(true); }}
          onMouseDown={(event) => event.preventDefault()}
          onMouseUp={(event) => { event.stopPropagation(); setCommentComposerOpen(true); }}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              setCommentComposerOpen(true);
            }
          }}
          onClick={() => setCommentComposerOpen(true)}
          style={anchoredCommentButtonStyle(commentDraftAnchor)}
        >
          ＋ COMMENT
        </button>
      )}
      {commentDraft && commentComposerOpen && (
        <div
          ref={(node) => { commentPopoverRef.current = node; }}
          role="dialog"
          aria-label="Add comment to selection"
          onKeyDown={(event) => {
            if (event.key === "Escape" && !commentBusy) {
              event.preventDefault();
              clearCommentDraft(true);
            }
          }}
          style={anchoredPopoverStyle(commentDraftAnchor, 340, 310)}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <span style={{ color: "var(--amber)", letterSpacing: ".14em", fontSize: 8.5 }}>NEW COMMENT</span>
            <span style={{ flex: 1 }} />
            <button type="button" aria-label="Cancel new comment" disabled={commentBusy} onClick={() => { setCommentError(""); clearCommentDraft(true); }} style={{ ...iconBtn, opacity: commentBusy ? .45 : 1 }}>✕</button>
          </div>
          <blockquote style={{ margin: "0 0 9px", padding: "7px 9px", borderLeft: "2px solid var(--amber)", background: "var(--tint)", color: "var(--txt2)", fontFamily: "'Courier Prime',monospace", fontSize: 10.5, lineHeight: 1.45, maxHeight: 90, overflow: "auto" }}>“{commentDraft.quote}”</blockquote>
          <textarea
            autoFocus
            aria-label="Comment text"
            value={commentBody}
            onChange={(event) => setCommentBody(event.target.value)}
            onKeyDown={(event) => {
              if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                event.preventDefault();
                void submitComment();
              }
            }}
            placeholder="What should change here?"
            rows={4}
            style={commentTextArea}
          />
          {commentError && <div role="alert" style={{ color: "var(--crimson)", marginTop: 7 }}>{commentError}</div>}
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 7, marginTop: 9 }}>
            <button type="button" disabled={commentBusy} onClick={() => { setCommentError(""); clearCommentDraft(true); }} style={{ ...commentAction, color: "var(--txt2)", opacity: commentBusy ? .45 : 1 }}>CANCEL</button>
            <button type="button" disabled={commentBusy || !commentBody.trim()} onClick={() => void submitComment()} style={{ ...commentAction, opacity: commentBusy || !commentBody.trim() ? .45 : 1 }}>{commentOperation?.kind === "assistant" ? `${commentOperation.assistantLabel?.toUpperCase()} THINKING…` : commentBusy ? "SAVING…" : "ADD COMMENT"}</button>
          </div>
        </div>
      )}
      {!commentComposerOpen && activeComments.length > 0 && (
        <aside
          ref={(node) => { commentPopoverRef.current = node; }}
          role="dialog"
          aria-label={activeComments.length === 1 ? "Comment thread" : `${activeComments.length} overlapping comment threads`}
          tabIndex={-1}
          onKeyDown={(event) => {
            if (event.key !== "Escape" || commentBusy) return;
            event.preventDefault();
            if (confirmDeleteCommentId != null) {
              const id = confirmDeleteCommentId;
              setConfirmDeleteCommentId(null);
              window.setTimeout(() => deleteThreadButtonRefs.current.get(id)?.focus({ preventScroll: true }), 0);
            } else {
              closeCommentPopover();
            }
          }}
          style={anchoredPopoverStyle(commentMarkAnchor, 390, 620)}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <span style={{ color: "var(--amber)", letterSpacing: ".14em", fontSize: 8.5 }}>{activeComments.length === 1 ? "COMMENT THREAD" : `${activeComments.length} OVERLAPPING THREADS`}</span>
            <span style={{ flex: 1 }} />
            <button ref={commentCloseRef} type="button" aria-label="Close comment thread" disabled={commentBusy} onClick={closeCommentPopover} style={{ ...iconBtn, opacity: commentBusy ? .45 : 1 }}>✕</button>
          </div>
          {commentError && (
            <div role="alert" style={{ display: "flex", alignItems: "start", gap: 7, color: "var(--crimson)", border: "1px solid rgba(232,68,58,.45)", background: "rgba(232,68,58,.08)", padding: "7px 8px", marginBottom: 8, lineHeight: 1.45 }}>
              <span style={{ flex: 1 }}>{commentError}</span>
              <button type="button" aria-label="Dismiss comment error" onClick={() => setCommentError("")} style={{ ...iconBtn, color: "var(--crimson)" }}>✕</button>
            </div>
          )}
          {activeComments.map((comment) => {
            const replies = comment.replies
              .filter((reply) => !deletedReplyIds.has(reply.id))
              .slice()
              .sort((left, right) => left.sort_order - right.sort_order || left.id - right.id);
            const threadOperation = commentOperation?.commentId === comment.id ? commentOperation : null;
            const assistantThinking = threadOperation?.kind === "assistant";
            const confirmingDelete = confirmDeleteCommentId === comment.id;
            const imported = isImportedSource(comment.source_id);
            return (
              <article key={comment.id} aria-labelledby={`manuscript-comment-${comment.id}`} style={{ borderTop: "1px solid var(--line2)", padding: "11px 0 13px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 7, flexWrap: "wrap" }}>
                  <span id={`manuscript-comment-${comment.id}`} style={{ color: comment.resolved ? "var(--green)" : "var(--amber)", letterSpacing: ".13em", fontSize: 7.5 }}>{comment.resolved ? "✓ RESOLVED" : "● OPEN"}</span>
                  <span style={{ color: "var(--txt3)", fontSize: 7 }}>{imported ? "IMPORTED" : "NATIVE PRO"}</span>
                  <time dateTime={comment.created_at} title={absoluteTime(comment.created_at)} style={{ color: "var(--txt3)", fontSize: 7.5 }}>{formatRelativeTime(comment.created_at, commentClock)}</time>
                  <span style={{ flex: 1 }} />
                  <button
                    type="button"
                    disabled={commentBusy}
                    aria-label={comment.resolved ? "Reopen comment" : "Resolve comment"}
                    onClick={() => void toggleCommentResolved(comment)}
                    style={{ ...commentAction, color: comment.resolved ? "var(--green)" : "var(--amber)", opacity: commentBusy ? .45 : 1 }}
                  >{threadOperation?.kind === "resolve" ? "SAVING…" : comment.resolved ? "REOPEN" : "RESOLVE"}</button>
                </div>
                <blockquote style={{ margin: "0 0 8px", padding: "6px 8px", borderLeft: "2px solid var(--amber)", background: "var(--tint)", color: "var(--txt2)", fontFamily: "'Courier Prime',monospace", fontSize: 9.5, lineHeight: 1.45, maxHeight: 86, overflowY: "auto", whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>“{comment.quote}”</blockquote>
                <div style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", lineHeight: 1.5, fontSize: 10.5 }}>{comment.body || <em style={{ color: "var(--txt3)" }}>(No comment text)</em>}</div>

                <div style={{ marginTop: 11, color: "var(--txt3)", letterSpacing: ".13em", fontSize: 7.5 }}>REPLIES · {replies.length}</div>
                {replies.length === 0 && !assistantThinking
                  ? <div style={{ color: "var(--txt3)", marginTop: 7, fontStyle: "italic" }}>No replies in this thread.</div>
                  : (
                      <div role="list" aria-label={`Replies to comment ${comment.id}`} style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 7 }}>
                        {replies.map((reply) => {
                          const deleting = threadOperation?.kind === "delete-reply" && threadOperation.replyId === reply.id;
                          return (
                            <div key={reply.id} role="listitem" style={{ border: "1px solid var(--line2)", background: "var(--tint)", padding: "7px 8px" }}>
                              <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginBottom: 4 }}>
                                <strong style={{ color: "var(--accent)", fontSize: 9 }}>{reply.author || "Unknown author"}</strong>
                                {isImportedSource(reply.source_id) && <span style={{ color: "var(--amber)", fontSize: 6.5, letterSpacing: ".1em" }}>IMPORTED</span>}
                                <time dateTime={reply.created_at} title={absoluteTime(reply.created_at)} style={{ color: "var(--txt3)", fontSize: 7 }}>{formatRelativeTime(reply.created_at, commentClock)}</time>
                                <span style={{ flex: 1 }} />
                                <button
                                  type="button"
                                  aria-label={`Delete reply from ${reply.author || "Unknown author"}`}
                                  disabled={commentBusy}
                                  onClick={() => void deleteCommentReply(comment, reply)}
                                  style={{ ...commentAction, padding: "2px 5px", color: "var(--crimson)", borderColor: "rgba(232,68,58,.45)", opacity: commentBusy ? .45 : 1 }}
                                >{deleting ? "DELETING…" : "DELETE"}</button>
                              </div>
                              <div style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", lineHeight: 1.5 }}>{reply.body}</div>
                            </div>
                          );
                        })}
                        {assistantThinking && (
                          <div role="status" aria-live="polite" style={{ border: "1px dashed var(--line-cy)", padding: "7px 8px", color: "var(--accent)" }}>
                            {threadOperation.assistantLabel} is thinking…
                          </div>
                        )}
                      </div>
                    )}

                <form onSubmit={(event) => { event.preventDefault(); void submitCommentReply(comment); }} style={{ marginTop: 10 }}>
                  <label htmlFor={`manuscript-comment-reply-${comment.id}`} style={{ display: "block", color: "var(--txt3)", fontSize: 7.5, letterSpacing: ".13em", marginBottom: 5 }}>ADD REPLY</label>
                  <textarea
                    ref={(node) => {
                      if (node) replyComposerRefs.current.set(comment.id, node);
                      else replyComposerRefs.current.delete(comment.id);
                    }}
                    id={`manuscript-comment-reply-${comment.id}`}
                    aria-label="Reply to comment"
                    aria-describedby={`manuscript-comment-reply-help-${comment.id}`}
                    value={replyDrafts[comment.id] ?? ""}
                    disabled={commentBusy}
                    onChange={(event) => setReplyDrafts((current) => ({ ...current, [comment.id]: event.target.value }))}
                    onKeyDown={(event) => {
                      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
                        event.preventDefault();
                        void submitCommentReply(comment);
                      }
                    }}
                    placeholder="Write a reply… Mention @assistant or @counterpart for an AI response."
                    rows={3}
                    style={commentTextArea}
                  />
                  <div style={{ display: "flex", alignItems: "center", gap: 7, marginTop: 6, flexWrap: "wrap" }}>
                    <button type="submit" disabled={commentBusy || !(replyDrafts[comment.id] ?? "").trim()} style={{ ...commentAction, opacity: commentBusy || !(replyDrafts[comment.id] ?? "").trim() ? .45 : 1 }}>
                      {threadOperation?.kind === "reply" ? "POSTING…" : assistantThinking ? `${threadOperation.assistantLabel?.toUpperCase()} THINKING…` : "POST REPLY"}
                    </button>
                    <span id={`manuscript-comment-reply-help-${comment.id}`} style={{ color: "var(--txt3)", fontSize: 7 }}>Ctrl/⌘ + Enter to post · Esc closes</span>
                    <span style={{ flex: 1 }} />
                    {confirmingDelete ? (
                      <span role="group" aria-label="Confirm thread deletion" style={{ display: "flex", alignItems: "center", gap: 5, flexWrap: "wrap" }}>
                        <span style={{ color: "var(--crimson)", fontSize: 7.5 }}>Delete thread and {replies.length} {replies.length === 1 ? "reply" : "replies"}?</span>
                        <button ref={commentConfirmDeleteRef} type="button" disabled={commentBusy} onClick={() => void deleteCommentThread(comment)} style={{ ...commentAction, color: "white", background: "var(--crimson)", borderColor: "var(--crimson)", opacity: commentBusy ? .45 : 1 }}>{threadOperation?.kind === "delete-thread" ? "DELETING…" : "DELETE PERMANENTLY"}</button>
                        <button
                          type="button"
                          disabled={commentBusy}
                          onClick={() => {
                            setConfirmDeleteCommentId(null);
                            window.setTimeout(() => deleteThreadButtonRefs.current.get(comment.id)?.focus({ preventScroll: true }), 0);
                          }}
                          style={{ ...commentAction, color: "var(--txt2)", opacity: commentBusy ? .45 : 1 }}
                        >CANCEL</button>
                      </span>
                    ) : (
                      <button
                        ref={(node) => {
                          if (node) deleteThreadButtonRefs.current.set(comment.id, node);
                          else deleteThreadButtonRefs.current.delete(comment.id);
                        }}
                        type="button"
                        aria-label="Delete comment thread"
                        disabled={commentBusy}
                        onClick={() => setConfirmDeleteCommentId(comment.id)}
                        style={{ ...commentAction, color: "var(--crimson)", borderColor: "rgba(232,68,58,.45)", opacity: commentBusy ? .45 : 1 }}
                      >DELETE THREAD</button>
                    )}
                  </div>
                </form>
              </article>
            );
          })}
          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 8 }}>
            <button type="button" onClick={() => { onOpenComments([]); navigate("Comments"); }} style={commentAction}>OPEN COMMENTS PANEL ›</button>
          </div>
        </aside>
      )}
    </div>
  );
}

// ------------------------------------------------- Live screenplay-format preview
function FormatPreview({ scene, content }: { scene: SceneDTO | undefined; content: string }) {
  const lines = classifyLines(content || "");
  return (
    <div style={{ width: 340, flex: "none", borderLeft: "1px solid var(--line)", background: "linear-gradient(180deg,var(--panel2),var(--base))", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <div style={{ height: 30, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 13px", borderBottom: "1px solid var(--line)", background: "rgba(76,194,255,.04)" }}>
        <span style={{ fontSize: 8.5, letterSpacing: ".24em", color: "var(--accent)" }}>FORMAT PREVIEW</span>
        <span style={{ fontSize: 8, color: "var(--txt3)", letterSpacing: ".1em" }}>◈ LIVE</span>
      </div>
      <div style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "16px 18px", fontFamily: "'Courier Prime',monospace", fontSize: 13, lineHeight: 1.6, color: "var(--txt)" }}>
        {!scene
          ? <div style={{ color: "var(--txt3)", fontStyle: "italic", fontSize: 11 }}>Click into a scene to preview it formatted.</div>
          : (
            <>
              <div style={{ fontWeight: 700, color: "var(--strong)", marginBottom: 12, letterSpacing: ".02em" }}>{scene.title || "UNTITLED SCENE"}</div>
              {content.trim() === ""
                ? <div style={{ opacity: 0.5, fontStyle: "italic" }}>(no prose yet)</div>
                : lines.map((l, i) =>
                  l.type === "page_break" ? <hr key={i} style={{ border: "none", borderTop: "1px dashed var(--line2)", margin: "14px 0" }} />
                    : l.type === "empty" ? <div key={i} style={{ height: ".8em" }} />
                    : <div key={i} style={fountainLineStyle(l.type)}>{renderLineText(l) || " "}</div>)}
            </>
          )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------ Manuscript rail
function ManuscriptRail({
  scenes, wordsById, statusById, total, onJump, activeId,
}: {
  scenes: SceneDTO[]; wordsById: Record<number, number>; statusById: Record<number, SaveStatus>;
  total: number; onJump: (id: number) => void; activeId: number | null;
}) {
  const maxWords = Math.max(1, ...scenes.map((s) => wordsById[s.id] ?? 0));
  const pages = Math.max(0, Math.round(total / 250));
  const mins = Math.max(0, Math.round(total / 200));
  const avg = scenes.length ? Math.round(total / scenes.length) : 0;
  const Stat = ({ label, value }: { label: string; value: string }) => (
    <div style={{ flex: 1 }}>
      <div style={{ fontFamily: "'Chakra Petch'", fontSize: 19, color: "var(--strong)", letterSpacing: ".02em" }}>{value}</div>
      <div style={{ fontSize: 8, color: "var(--txt3)", letterSpacing: ".16em", marginTop: 2 }}>{label}</div>
    </div>
  );
  return (
    <div style={{ width: 300, flex: "none", borderLeft: "1px solid var(--line)", background: "linear-gradient(180deg,var(--panel2),var(--base))", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <div style={{ height: 30, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 13px", borderBottom: "1px solid var(--line)", background: "rgba(76,194,255,.04)" }}>
        <span style={{ fontSize: 8.5, letterSpacing: ".24em", color: "var(--accent)" }}>MANUSCRIPT</span>
        <span style={{ fontSize: 8, color: "var(--txt3)", letterSpacing: ".1em" }}>◈ LIVE</span>
      </div>
      <div style={{ display: "flex", gap: 10, padding: 14, borderBottom: "1px solid var(--line2)" }}>
        <Stat label="WORDS" value={total.toLocaleString()} /><Stat label="SCENES" value={String(scenes.length)} /><Stat label="~PAGES" value={String(pages)} />
      </div>
      <div style={{ display: "flex", gap: 10, padding: "10px 14px", borderBottom: "1px solid var(--line2)", fontSize: 9, color: "var(--txt2)" }}>
        <span>~{mins} min read</span><span style={{ color: "var(--txt3)" }}>·</span><span>{avg} avg words/scene</span>
      </div>
      <div style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "8px 8px 14px" }}>
        <div style={{ fontSize: 8, color: "var(--txt3)", letterSpacing: ".2em", padding: "4px 6px 8px" }}>SCENES — JUMP</div>
        {scenes.map((s, i) => {
          const w = wordsById[s.id] ?? wordCount(s.content);
          const stt = STATUS_GLYPH[statusById[s.id] ?? "idle"];
          const active = s.id === activeId;
          return (
            <button key={s.id} type="button" onClick={() => onJump(s.id)} title={`Jump to scene ${i + 1}`}
              style={{ display: "block", width: "100%", textAlign: "left", background: active ? "rgba(76,194,255,.07)" : "transparent", border: "none", borderLeft: `2px solid ${active ? "var(--accent)" : "transparent"}`, padding: "6px 6px", cursor: "pointer", font: "inherit" }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 7 }}>
                <span style={{ fontFamily: "'Chakra Petch'", fontSize: 10, color: "var(--txt3)", flex: "none" }}>{i + 1}</span>
                <span style={{ flex: 1, minWidth: 0, fontSize: 11, color: active ? "var(--strong)" : "var(--txt2)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{s.title || "Untitled"}</span>
                {stt.g && <span style={{ fontSize: 9, color: stt.c, flex: "none" }}>{stt.g}</span>}
                <span style={{ fontSize: 9, color: "var(--txt3)", flex: "none" }}>{w}</span>
              </div>
              <div style={{ height: 3, marginTop: 4, background: "var(--tint2)" }}>
                <div style={{ width: `${Math.round((w / maxWords) * 100)}%`, height: "100%", background: active ? "var(--accent)" : "var(--line-cy,#2b6f8f)" }} />
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------- Manuscript
export function ManuscriptEditor(props: PanelProps) {
  const { api, projectId, writingMode } = useStudio();
  const projectKey = projectId ?? null;
  const { data: scenes, loading, error, refetch } = useScenes();
  const { data: commentData, loading: commentsLoading, error: commentsError, refetch: refetchComments } = useComments();
  const [hideResolvedComments, setHideResolvedComments] = useHideResolvedPreference();
  const sorted = useMemo(() => [...(scenes ?? [])].sort((a, b) => a.sort_order - b.sort_order), [scenes]);
  const isScript = SCRIPT_MODES.has(String(writingMode ?? ""));

  const [focus, setFocus] = useState(false);
  const [format, setFormat] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [wordsById, setWordsById] = useState<Record<number, number>>({});
  const [activeContent, setActiveContent] = useState<{ id: number; content: string } | null>(null);
  const [statusById, setStatusById] = useState<Record<number, SaveStatus>>({});
  const [activeId, setActiveId] = useState<number | null>(null);
  const [warmSceneIds, setWarmSceneIds] = useState<number[]>([]);
  const [nearSceneIds, setNearSceneIds] = useState<Set<number>>(() => new Set());
  const [openCommentTarget, setOpenCommentTarget] = useState<{ sceneId: number; ids: number[] } | null>(null);
  const [activeCommentDraftSceneId, setActiveCommentDraftSceneId] = useState<number | null>(null);
  const [externalCommentDraft, setExternalCommentDraft] = useState<ExternalCommentDraft | null>(null);
  const [liveSceneTextStore, setLiveSceneTextStore] = useState<LiveSceneTextStore>({ projectId: null, byScene: {} });
  const flushers = useRef(new Map<number, FlushHandlers>());
  const focusAfter = useRef<number | null>(null);
  const jumpTimer = useRef<number | null>(null);
  const commentNavIndex = useRef(-1);
  const externalCommentDraftId = useRef(0);
  const crossScenePointerStart = useRef<CrossScenePointerStart | null>(null);
  const orphanCleanup = useRef(new Set<number>());
  const reconciliationAttempts = useRef(new Map<number, string>());
  const statusGuardRef = useRef<{ projectId: number | null; byScene: Record<number, SaveStatus> }>({ projectId: null, byScene: {} });
  const commentMutationGuardRef = useRef<{
    projectId: number | null;
    safe: boolean;
    sceneSnapshot: readonly SceneDTO[] | null;
    commentsSnapshot: readonly InlineCommentDTO[] | undefined;
  }>({ projectId: null, safe: false, sceneSnapshot: null, commentsSnapshot: undefined });
  const manuscriptScrollRef = useRef<HTMLDivElement | null>(null);
  const sceneNodesRef = useRef(new Map<number, HTMLDivElement>());
  const sceneObserverRef = useRef<IntersectionObserver | null>(null);
  const activeIdRef = useRef(activeId);
  activeIdRef.current = activeId;
  const showFormat = isScript && format && !focus;
  const showFormatRef = useRef(showFormat);
  showFormatRef.current = showFormat;
  const intersectionSupported = typeof IntersectionObserver !== "undefined";

  useEffect(() => {
    setWordsById({}); setActiveContent(null); setStatusById({}); setActiveId(null);
    setWarmSceneIds([]); setNearSceneIds(new Set()); setActionError(null);
    setOpenCommentTarget(null); setActiveCommentDraftSceneId(null); setExternalCommentDraft(null); commentNavIndex.current = -1; externalCommentDraftId.current = 0; crossScenePointerStart.current = null; orphanCleanup.current.clear(); reconciliationAttempts.current.clear();
    statusGuardRef.current = { projectId: projectKey, byScene: {} };
    setLiveSceneTextStore((current) => current.projectId === projectKey ? current : { projectId: projectKey, byScene: {} });
    activeIdRef.current = null; focusAfter.current = null;
  }, [projectKey]);

  const onWords = useCallback((id: number, n: number) => setWordsById((m) => (m[id] === n ? m : { ...m, [id]: n })), []);
  const onContent = useCallback((id: number, content: string) => {
    if (activeIdRef.current !== id || !showFormatRef.current) return;
    setActiveContent((current) => current?.id === id && current.content === content ? current : { id, content });
  }, []);
  const onStatus = useCallback((ownerProjectId: number | null, id: number, s: SaveStatus) => {
    if (ownerProjectId !== projectKey) return;
    const guarded = statusGuardRef.current.projectId === projectKey ? statusGuardRef.current.byScene : {};
    if (guarded[id] !== s) statusGuardRef.current = { projectId: projectKey, byScene: { ...guarded, [id]: s } };
    setStatusById((m) => (m[id] === s ? m : { ...m, [id]: s }));
  }, [projectKey]);
  const onLiveText = useCallback((ownerProjectId: number | null, id: number, value: LiveSceneText) => {
    if (ownerProjectId !== projectKey) return;
    setLiveSceneTextStore((current) => {
      const byScene = current.projectId === projectKey ? current.byScene : {};
      const previous = byScene[id];
      if (previous?.title === value.title && previous.content === value.content) return current;
      return { projectId: projectKey, byScene: { ...byScene, [id]: value } };
    });
  }, [projectKey]);
  const onActive = useCallback((id: number) => {
    activeIdRef.current = id;
    setActiveId(id);
    setActiveContent((current) => current?.id === id ? current : null);
    setWarmSceneIds((current) => touchWarmSceneIds(current, id));
  }, []);
  const registerFlush = useCallback((id: number, h: FlushHandlers | null) => {
    if (h) flushers.current.set(id, h); else flushers.current.delete(id);
  }, []);

  const registerSceneNode = useCallback((id: number, node: HTMLDivElement | null) => {
    const previous = sceneNodesRef.current.get(id);
    if (previous === node) return;
    if (previous) sceneObserverRef.current?.unobserve(previous);
    if (node) {
      sceneNodesRef.current.set(id, node);
      sceneObserverRef.current?.observe(node);
    } else {
      sceneNodesRef.current.delete(id);
    }
  }, []);

  useEffect(() => {
    const root = manuscriptScrollRef.current;
    if (!root || typeof IntersectionObserver === "undefined") return undefined;
    const observer = new IntersectionObserver((entries) => {
      if (sceneObserverRef.current !== observer) return;
      setNearSceneIds((current) => {
        let next: Set<number> | null = null;
        for (const entry of entries) {
          const id = Number((entry.target as HTMLElement).dataset.sceneId);
          if (!Number.isInteger(id)) continue;
          const has = current.has(id);
          if (entry.isIntersecting === has) continue;
          if (!next) next = new Set(current);
          if (entry.isIntersecting) next.add(id); else next.delete(id);
        }
        return next ?? current;
      });
    }, { root, rootMargin: "900px 0px", threshold: 0 });
    sceneObserverRef.current = observer;
    for (const node of sceneNodesRef.current.values()) observer.observe(node);
    return () => {
      observer.disconnect();
      if (sceneObserverRef.current === observer) sceneObserverRef.current = null;
    };
  }, [projectId]);

  const sceneIdsKey = sorted.map((scene) => scene.id).join(",");
  useEffect(() => {
    const valid = new Set(sorted.map((scene) => scene.id));
    setWordsById((current) => pruneSceneRecord(current, valid));
    setStatusById((current) => pruneSceneRecord(current, valid));
    if (statusGuardRef.current.projectId === projectKey) {
      statusGuardRef.current = { projectId: projectKey, byScene: pruneSceneRecord(statusGuardRef.current.byScene, valid) };
    }
    setLiveSceneTextStore((current) => current.projectId === projectKey
      ? { projectId: projectKey, byScene: pruneSceneRecord(current.byScene, valid) }
      : current);
    setActiveContent((current) => current && valid.has(current.id) ? current : null);
    setWarmSceneIds((current) => pruneSceneIds(current, valid));
    setNearSceneIds((current) => {
      const next = new Set([...current].filter((id) => valid.has(id)));
      return next.size === current.size ? current : next;
    });
    setActiveId((current) => {
      const next = current != null && valid.has(current) ? current : sorted[0]?.id ?? null;
      return next;
    });
  }, [projectKey, sceneIdsKey]);

  useEffect(() => () => {
    if (jumpTimer.current !== null) window.clearTimeout(jumpTimer.current);
  }, []);

  const comments = commentData ?? [];
  const liveSceneText = liveSceneTextStore.projectId === projectKey ? liveSceneTextStore.byScene : {};
  const liveScenesReady = sorted.every((scene) => liveSceneText[scene.id] != null);
  const commentScenes = useMemo(() => sorted.map((scene) => {
    const live = liveSceneText[scene.id];
    return live ? { ...scene, title: live.title, content: live.content } : scene;
  }), [liveSceneText, sorted]);
  const consumeExternalCommentDraft = useCallback((requestId: number) => {
    setExternalCommentDraft((current) => current?.requestId === requestId ? null : current);
  }, []);
  const publishCrossSceneCommentDraft = useCallback((
    start: CommentSelectionEndpoint,
    end: CommentSelectionEndpoint,
    anchor: ViewportAnchor | null,
  ) => {
    if (projectId == null) return;
    const draft = createMultiFieldCommentDraft(commentScenes, start, end);
    if (!draft) return;
    const requestId = externalCommentDraftId.current + 1;
    externalCommentDraftId.current = requestId;
    setOpenCommentTarget(null);
    setActiveCommentDraftSceneId(start.sceneId);
    onActive(start.sceneId);
    setExternalCommentDraft({ requestId, projectId, sceneId: start.sceneId, draft, anchor });
  }, [commentScenes, onActive, projectId]);
  const captureCrossSceneCommentSelection = useCallback(() => {
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || selection.rangeCount !== 1) return;
    const range = selection.getRangeAt(0);
    const startRoot = proseRootForDomPoint(range.startContainer);
    const endRoot = proseRootForDomPoint(range.endContainer);
    const manuscriptRoot = manuscriptScrollRef.current;
    if (
      !startRoot
      || !endRoot
      || startRoot === endRoot
      || !manuscriptRoot?.contains(startRoot)
      || !manuscriptRoot.contains(endRoot)
    ) return;
    const start = commentSelectionEndpointFromDomPoint(startRoot, range.startContainer, range.startOffset);
    const end = commentSelectionEndpointFromDomPoint(endRoot, range.endContainer, range.endOffset);
    if (!start || !end) return;
    publishCrossSceneCommentDraft(start, end, viewportAnchorForSelectionRange(range));
  }, [publishCrossSceneCommentDraft]);
  const beginCrossScenePointerSelection = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    crossScenePointerStart.current = null;
    if (event.button !== 0 || !(event.target instanceof Node)) return;
    const root = proseRootForDomPoint(event.target);
    if (!root || !manuscriptScrollRef.current?.contains(root)) return;
    const point = proseDomPointFromViewport(root, event.clientX, event.clientY);
    if (!point) return;
    const endpoint = commentSelectionEndpointFromDomPoint(root, point.container, point.offset);
    if (endpoint) crossScenePointerStart.current = { root, endpoint, x: event.clientX, y: event.clientY };
  }, []);
  const finishCrossScenePointerSelection = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    const started = crossScenePointerStart.current;
    crossScenePointerStart.current = null;
    if (!started || event.button !== 0) {
      captureCrossSceneCommentSelection();
      return;
    }
    if (Math.hypot(event.clientX - started.x, event.clientY - started.y) < 6) {
      captureCrossSceneCommentSelection();
      return;
    }
    const hit = document.elementFromPoint(event.clientX, event.clientY);
    const endRoot = proseRootForDomPoint(hit);
    if (!endRoot || endRoot === started.root || !manuscriptScrollRef.current?.contains(endRoot)) {
      captureCrossSceneCommentSelection();
      return;
    }
    const endPoint = proseDomPointFromViewport(endRoot, event.clientX, event.clientY);
    if (!endPoint) return;
    const released = commentSelectionEndpointFromDomPoint(endRoot, endPoint.container, endPoint.offset);
    if (!released) return;
    const relationship = started.root.compareDocumentPosition(endRoot);
    if (relationship & Node.DOCUMENT_POSITION_DISCONNECTED) return;
    const startComesFirst = Boolean(relationship & Node.DOCUMENT_POSITION_FOLLOWING);
    const start = startComesFirst ? started.endpoint : released;
    const end = startComesFirst ? released : started.endpoint;
    publishCrossSceneCommentDraft(start, end, {
      left: event.clientX,
      right: event.clientX,
      top: event.clientY,
      bottom: event.clientY,
    });
  }, [captureCrossSceneCommentSelection, publishCrossSceneCommentDraft]);
  const commentSaveBlocked = sorted.some((scene) => {
    const status = statusById[scene.id];
    return status === "dirty" || status === "saving" || status === "error";
  });
  const commentMutationsSafe = projectId != null
    && !loading && !commentsLoading && !error && !commentsError
    && scenes != null && commentData != null && liveScenesReady && !commentSaveBlocked;
  commentMutationGuardRef.current = {
    projectId: projectKey,
    safe: commentMutationsSafe,
    sceneSnapshot: commentScenes,
    commentsSnapshot: commentData,
  };
  const visibleComments = useMemo(
    () => hideResolvedComments ? comments.filter((comment) => !comment.resolved) : comments,
    [comments, hideResolvedComments],
  );
  const resolvedCommentSpans = useMemo(
    () => reconcileCommentSpans(visibleComments, commentScenes),
    [commentScenes, visibleComments],
  );
  const commentSpansByScene = useMemo(() => {
    const result = new Map<number, CommentSpan[]>();
    for (const span of resolvedCommentSpans) {
      const bucket = result.get(span.sceneId);
      if (bucket) bucket.push(span); else result.set(span.sceneId, [span]);
    }
    return result;
  }, [resolvedCommentSpans]);
  const unresolvedCommentTargets = useMemo(() => comments
    .filter((comment) => !comment.resolved)
    .map((comment) => ({ comment, location: locateComment(comment, commentScenes) }))
    .filter((item): item is { comment: InlineCommentDTO; location: CommentSpan } => item.location != null)
    .sort((left, right) => {
      const leftScene = commentScenes.findIndex((scene) => scene.id === left.location.sceneId);
      const rightScene = commentScenes.findIndex((scene) => scene.id === right.location.sceneId);
      return leftScene - rightScene
        || (left.location.field === right.location.field ? 0 : left.location.field === "title" ? -1 : 1)
        || left.location.fromOffset - right.location.fromOffset
        || left.comment.id - right.comment.id;
    }), [commentScenes, comments]);

  // Persist a relocated range only after every scene editor has reported its
  // live text and every save queue is settled. A delayed, identity-checked guard
  // prevents a keystroke or resource refetch from racing a stale anchor patch.
  useEffect(() => {
    if (!commentMutationsSafe || projectId == null || !commentData) return undefined;
    const pending = commentData.flatMap((comment) => {
      const patch = reconciledCommentPatch(comment, commentScenes);
      if (!patch) {
        reconciliationAttempts.current.delete(comment.id);
        return [];
      }
      const signature = JSON.stringify([comment.anchor, comment.quote, patch]);
      return reconciliationAttempts.current.get(comment.id) === signature
        ? []
        : [{ commentId: comment.id, patch, signature }];
    });
    if (!pending.length) return undefined;
    const ownerProjectId = projectId;
    const sceneSnapshot = commentScenes;
    const commentsSnapshot = commentData;
    const timer = window.setTimeout(() => {
      const guard = commentMutationGuardRef.current;
      const guardedStatuses = statusGuardRef.current.projectId === ownerProjectId
        ? statusGuardRef.current.byScene
        : {};
      const newlyBlocked = sceneSnapshot.some((scene) => {
        const status = guardedStatuses[scene.id];
        return status === "dirty" || status === "saving" || status === "error";
      });
      if (
        !guard.safe
        || newlyBlocked
        || guard.projectId !== ownerProjectId
        || guard.sceneSnapshot !== sceneSnapshot
        || guard.commentsSnapshot !== commentsSnapshot
      ) return;

      for (const item of pending) reconciliationAttempts.current.set(item.commentId, item.signature);
      void Promise.all(pending.map(async (item) => {
        try {
          await trackProjectWrite(api.updateComment(ownerProjectId, item.commentId, item.patch));
          return null;
        } catch (updateError) {
          if (reconciliationAttempts.current.get(item.commentId) === item.signature) {
            reconciliationAttempts.current.delete(item.commentId);
          }
          return updateError;
        }
      })).then((results) => {
        const failure = results.find((result) => result != null);
        if (commentMutationGuardRef.current.projectId !== ownerProjectId) return;
        refetchComments();
        if (failure) {
          setActionError(`Couldn't preserve a relocated comment — ${failure instanceof Error ? failure.message : String(failure)}`);
        }
      });
    }, 1200);
    return () => window.clearTimeout(timer);
  }, [api, commentData, commentMutationsSafe, commentScenes, projectId, refetchComments]);

  // A comment is deleted only after its live text has saved and neither its quote
  // nor either context landmark can be found. The same delayed guard prevents
  // stale parent data, project switches, and in-flight edits from deleting it.
  useEffect(() => {
    if (!commentMutationsSafe || projectId == null || !commentData) return undefined;
    const ids = findOrphanedCommentIds(commentData, commentScenes).filter((id) => !orphanCleanup.current.has(id));
    if (!ids.length) return undefined;
    const ownerProjectId = projectId;
    const sceneSnapshot = commentScenes;
    const commentsSnapshot = commentData;
    const timer = window.setTimeout(() => {
      const guard = commentMutationGuardRef.current;
      const guardedStatuses = statusGuardRef.current.projectId === ownerProjectId
        ? statusGuardRef.current.byScene
        : {};
      const newlyBlocked = sceneSnapshot.some((scene) => {
        const status = guardedStatuses[scene.id];
        return status === "dirty" || status === "saving" || status === "error";
      });
      if (
        !guard.safe
        || newlyBlocked
        || guard.projectId !== ownerProjectId
        || guard.sceneSnapshot !== sceneSnapshot
        || guard.commentsSnapshot !== commentsSnapshot
      ) return;
      for (const id of ids) orphanCleanup.current.add(id);
      void Promise.all(ids.map((id) => trackProjectWrite(api.deleteComment(ownerProjectId, id))))
        .then(() => refetchComments())
        .catch((cleanupError) => {
          for (const id of ids) orphanCleanup.current.delete(id);
          if (commentMutationGuardRef.current.projectId === ownerProjectId) {
            setActionError(`Couldn't clean up an orphaned comment — ${cleanupError instanceof Error ? cleanupError.message : String(cleanupError)}`);
          }
        });
    }, 1200);
    return () => window.clearTimeout(timer);
  }, [api, commentData, commentMutationsSafe, commentScenes, projectId, refetchComments]);

  const total = useMemo(() => sorted.reduce((n, s) => n + (wordsById[s.id] ?? wordCount(s.content)), 0), [sorted, wordsById]);
  const statuses = useMemo(() => sorted.map((s) => statusById[s.id]).filter(Boolean) as SaveStatus[], [sorted, statusById]);
  const saveLabel = statuses.includes("saving") ? "SAVING…" : statuses.some((s) => s === "dirty" || s === "error") ? "UNSAVED" : "ALL SAVED";
  const saveColor = saveLabel === "SAVING…" ? "var(--accent)" : saveLabel === "UNSAVED" ? "var(--amber)" : "var(--green)";

  const effectiveActiveId = activeId ?? sorted[0]?.id ?? null;
  const activeScene = sorted.find((s) => s.id === effectiveActiveId) ?? sorted[0];
  const previewContent = activeScene ? (activeContent?.id === activeScene.id ? activeContent.content : activeScene.content) : "";

  const jump = useCallback((id: number, focusProse = true) => {
    onActive(id);
    const el = document.getElementById(`ms-scene-${id}`);
    el?.scrollIntoView({ block: "center", behavior: "smooth" });
    if (jumpTimer.current !== null) window.clearTimeout(jumpTimer.current);
    jumpTimer.current = window.setTimeout(() => {
      jumpTimer.current = null;
      const current = document.getElementById(`ms-scene-${id}`);
      current?.scrollIntoView({ block: "center", behavior: "smooth" });
      if (focusProse) (current?.querySelector("[data-prose]") as HTMLElement | null)?.focus({ preventScroll: true });
    }, 40);
  }, [onActive]);

  useEffect(() => {
    if (focusAfter.current != null && sorted.some((s) => s.id === focusAfter.current)) {
      jump(focusAfter.current); focusAfter.current = null;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sorted.map((s) => s.id).join(",")]);

  // Cross-panel nav: another panel asked to open a specific scene → jump to it.
  const { sceneId: navTarget, clear: clearNavTarget } = useManuscriptTarget();
  useEffect(() => {
    if (navTarget != null && sorted.some((s) => s.id === navTarget)) {
      // wait a tick so the scene DOM exists after a panel switch, THEN jump and
      // clear. Clearing must happen inside the timeout: clearing synchronously
      // flips navTarget→null, which re-runs this effect and its cleanup would
      // cancel the still-pending jump (a real race — the scene never activated).
      const target = navTarget;
      const t = window.setTimeout(() => { jump(target); clearNavTarget(); }, 60);
      return () => clearTimeout(t);
    }
    return undefined;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [navTarget, sorted.map((s) => s.id).join(",")]);

  const addScene = async () => {
    if (projectId == null || busy) return;
    setBusy(true);
    setActionError(null);
    try {
      const created = await trackProjectWrite(api.createScene(projectId, { title: `Scene ${sorted.length + 1}` }));
      focusAfter.current = created.id; refetch();
    } catch (error) {
      setActionError(`Couldn't create the scene — ${error instanceof Error ? error.message : String(error)}`);
    } finally { setBusy(false); }
  };
  const removeScene = async (id: number) => {
    if (projectId == null || busy) return;
    setBusy(true);
    setActionError(null);
    try {
      const saved = await (flushers.current.get(id)?.flush() ?? Promise.resolve(true));
      if (!saved) throw new Error("Resolve this scene's save error before deleting it.");
      await trackProjectWrite(api.deleteScene(projectId, id));
      // Dispose local edits only after the destructive request succeeds. If the
      // API rejects, the editor remains live and its draft can still autosave.
      flushers.current.get(id)?.cancel();
      refetch();
    } catch (error) {
      setActionError(`Couldn't delete the scene — ${error instanceof Error ? error.message : String(error)}`);
    } finally { setBusy(false); }
  };
  const moveScene = async (id: number, toIndex: number) => {
    if (projectId == null || busy || toIndex < 0 || toIndex >= sorted.length) return;
    setBusy(true);
    setActionError(null);
    try {
      await flushPendingProjectSaves();
      const target = (await api.listScenes(projectId)).find((scene) => scene.id === id);
      if (!target) throw new Error("The scene no longer exists.");
      await trackProjectWrite(api.updateScene(projectId, id, {
        sort_order: toIndex,
        ...(target.revision ? { expected_revision: target.revision } : {}),
      }));
      refetch();
    } catch (error) {
      setActionError(`Couldn't reorder the scene — ${error instanceof Error ? error.message : String(error)}`);
    } finally { setBusy(false); }
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
      e.preventDefault();
      setActionError(null);
      void flushPendingProjectSaves().catch((error) => setActionError(
        `Save failed — ${error instanceof Error ? error.message : String(error)}`,
      ));
    } else if (e.altKey && !e.metaKey && !e.ctrlKey && (e.key === "ArrowDown" || e.key === "ArrowUp") && unresolvedCommentTargets.length > 0) {
      e.preventDefault();
      const openId = openCommentTarget?.ids[0];
      const openIndex = openId == null ? -1 : unresolvedCommentTargets.findIndex((item) => item.comment.id === openId);
      const base = openIndex >= 0 ? openIndex : commentNavIndex.current;
      const delta = e.key === "ArrowDown" ? 1 : -1;
      const nextIndex = (base + delta + unresolvedCommentTargets.length) % unresolvedCommentTargets.length;
      const next = unresolvedCommentTargets[nextIndex]!;
      commentNavIndex.current = nextIndex;
      setOpenCommentTarget({ sceneId: next.location.sceneId, ids: [next.comment.id] });
      // The destination thread popover owns focus. A normal scene jump focuses
      // prose after its delayed scroll, which would steal focus from the dialog.
      jump(next.location.sceneId, false);
    }
  };

  return (
    <PanelShell {...props}>
      <div data-screen-label="Manuscript Editor" style={panelBox} onKeyDown={onKeyDown}>
        <Corners br />
        <div style={{ height: 44, flex: "none", display: "flex", alignItems: "center", gap: 14, padding: "0 18px", borderBottom: "1px solid var(--line)", background: "var(--tint)" }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 14, letterSpacing: ".14em", color: "var(--strong)" }}>MANUSCRIPT</span>
          <span style={{ fontSize: 10, color: "var(--txt2)" }}>{total.toLocaleString()} <span style={{ color: "var(--txt3)" }}>WORDS</span> · {sorted.length} SCENES</span>
          <div style={{ display: "flex", alignItems: "center", gap: 6, height: 20, padding: "0 9px", border: `1px solid ${saveColor}`, color: saveColor, fontSize: 9, letterSpacing: ".14em" }}>
            <span style={{ width: 5, height: 5, borderRadius: "50%", background: saveColor }} />{saveLabel}
          </div>
          <div style={{ flex: 1 }} />
          <button
            type="button"
            aria-label={hideResolvedComments ? "Show all comment marks" : "Show open comment marks"}
            aria-pressed={hideResolvedComments}
            title={hideResolvedComments ? "Resolved comment marks are hidden" : "Resolved comment marks are visible"}
            onClick={() => setHideResolvedComments(!hideResolvedComments)}
            style={{ ...linkBtn, color: hideResolvedComments ? "var(--amber)" : "var(--txt2)" }}
          >
            ◈ {hideResolvedComments ? "OPEN MARKS" : "ALL MARKS"}
          </button>
          {isScript && <button type="button" onClick={() => setFormat((f) => !f)} disabled={focus} aria-pressed={format} title="Live screenplay-format preview of the scene you're editing" style={{ ...linkBtn, color: format ? "var(--accent)" : "var(--txt2)", opacity: focus ? 0.4 : 1 }}>❏ FORMAT</button>}
          <button type="button" onClick={addScene} disabled={busy || projectId == null} style={{ ...linkBtn, color: "var(--txt2)", opacity: busy || projectId == null ? 0.5 : 1 }}>＋ SCENE</button>
          <button type="button" onClick={() => setFocus((f) => !f)} aria-pressed={focus} style={{ ...linkBtn, color: focus ? "var(--accent)" : "var(--txt2)" }}>⊹ FOCUS</button>
        </div>
        {actionError && <button type="button" role="alert" title="Dismiss" onClick={() => setActionError(null)} style={{ flex: "none", width: "100%", textAlign: "left", border: "none", borderBottom: "1px solid var(--crimson)", background: "rgba(255,82,96,.08)", color: "var(--crimson)", padding: "7px 18px", font: "inherit", fontSize: 9.5, cursor: "pointer" }}>{actionError}</button>}
        {commentsError && (
          <div role="alert" style={{ flex: "none", display: "flex", alignItems: "center", gap: 10, borderBottom: "1px solid var(--crimson)", background: "rgba(255,82,96,.08)", color: "var(--crimson)", padding: "7px 18px", fontSize: 9.5 }}>
            <span style={{ flex: 1 }}>Comments couldn't load — {commentsError}</span>
            <button type="button" onClick={refetchComments} style={{ ...commentAction, color: "var(--crimson)", borderColor: "rgba(232,68,58,.45)" }}>RETRY COMMENTS</button>
          </div>
        )}

        <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
          <div
            ref={manuscriptScrollRef}
            data-manuscript-scroll
            onPointerDownCapture={beginCrossScenePointerSelection}
            onPointerUp={finishCrossScenePointerSelection}
            onKeyUpCapture={captureCrossSceneCommentSelection}
            style={{ flex: 1, minWidth: 0, display: "flex", justifyContent: "center", padding: "26px 26px 60px", overflowY: "auto" }}
          >
            <div style={{ width: "100%", maxWidth: focus ? 720 : 660 }}>
              {projectId == null ? message("Open a project to start writing.")
                : loading ? message("Loading manuscript…")
                : error ? message(`Couldn't load manuscript — ${error}`)
                : sorted.length === 0 ? (
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 14, padding: "60px 0", color: "var(--txt3)" }}>
                    <div style={{ fontSize: 12, letterSpacing: ".04em" }}>No scenes yet — this manuscript is empty.</div>
                    <button type="button" onClick={addScene} disabled={busy} style={{ ...linkBtn, fontSize: 11, letterSpacing: ".16em", color: "var(--accent)", border: "1px solid var(--line-cy,#2b6f8f)", padding: "8px 16px" }}>＋ WRITE THE FIRST SCENE</button>
                  </div>
                )
                : sorted.map((s, i) => (
                  <SceneEditor
                    key={`${projectKey ?? "none"}:${s.id}`} scene={s} index={i}
                    showAct={i === 0 || sorted[i - 1]!.act !== s.act}
                    formatted={isScript && format} mode={String(writingMode ?? "")} busy={busy}
                    onWords={onWords} onContent={onContent} onStatus={onStatus} onActive={onActive} registerFlush={registerFlush}
                    onDelete={() => removeScene(s.id)} onMoveUp={() => moveScene(s.id, i - 1)} onMoveDown={() => moveScene(s.id, i + 1)}
                    isFirst={i === 0} isLast={i === sorted.length - 1}
                    renderProse={!intersectionSupported || s.id === effectiveActiveId || nearSceneIds.has(s.id) || warmSceneIds.includes(s.id)}
                    registerSceneNode={registerSceneNode} onRequestEdit={jump}
                    commentSpans={commentSpansByScene.get(s.id) ?? []}
                    comments={visibleComments}
                    openCommentIds={openCommentTarget?.sceneId === s.id ? openCommentTarget.ids : []}
                    onOpenComments={(ids) => setOpenCommentTarget(ids.length ? { sceneId: s.id, ids } : null)}
                    onCommentsChanged={refetchComments}
                    onCommentCreated={() => { refetch(); refetchComments(); }}
                    onLiveText={onLiveText}
                    activeCommentDraftSceneId={activeCommentDraftSceneId}
                    onCommentDraftOwnership={setActiveCommentDraftSceneId}
                    externalCommentDraft={externalCommentDraft?.projectId === projectKey && externalCommentDraft.sceneId === s.id ? externalCommentDraft : null}
                    onExternalCommentDraftConsumed={consumeExternalCommentDraft}
                  />
                ))}
            </div>
          </div>
          {!focus && sorted.length > 0 && (
            showFormat
              ? <FormatPreview scene={activeScene} content={previewContent} />
              : <ManuscriptRail scenes={sorted} wordsById={wordsById} statusById={statusById} total={total} onJump={jump} activeId={effectiveActiveId} />
          )}
        </div>
      </div>
    </PanelShell>
  );
}
