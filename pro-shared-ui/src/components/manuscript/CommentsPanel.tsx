import { useEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent as ReactKeyboardEvent } from "react";
import type { CommentReplyDTO, InlineCommentDTO, SceneDTO } from "@logosforge/ui-contracts";
import { useNavigate, useStudio } from "../../adapters/StudioProvider";
import { useComments, useScenes } from "../../hooks";
import { useMountedRef } from "../../hooks/useMountedRef";
import { trackProjectWrite } from "../../adapters/projectSaveCoordinator";
import { Corners, PanelShell, type PanelProps } from "../shell/PanelShell";
import {
  detectCommentAssistantMention,
  persistCommentAssistantReply,
  type CommentAssistantHandle,
} from "./commentAssistant";
import { useHideResolvedPreference } from "./commentPreferences";
import {
  absoluteTime,
  anchorLabel,
  buildCommentReport,
  commentReportFilename,
  formatRelativeTime,
  isImportedSource,
  sceneName,
} from "./commentPresentation";

const panelBox: CSSProperties = {
  position: "relative",
  width: "100%",
  height: "100%",
  minHeight: 0,
  background: "linear-gradient(180deg,var(--panel),var(--base))",
  border: "1px solid var(--line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)",
  overflow: "hidden",
  display: "flex",
  flexDirection: "column",
};

const quietButton = (active = false): CSSProperties => ({
  border: `1px solid ${active ? "var(--accent)" : "var(--line2)"}`,
  background: active ? "var(--accent)" : "transparent",
  color: active ? "var(--on-accent)" : "var(--txt2)",
  padding: "5px 9px",
  font: "inherit",
  fontSize: 8.5,
  fontWeight: active ? 700 : 400,
  letterSpacing: ".12em",
  cursor: "pointer",
});

const dangerButton: CSSProperties = {
  ...quietButton(),
  color: "var(--crimson)",
  borderColor: "rgba(232,68,58,.45)",
};

const textAreaStyle: CSSProperties = {
  width: "100%",
  minHeight: 70,
  resize: "vertical",
  boxSizing: "border-box",
  background: "var(--tint)",
  border: "1px solid var(--line2)",
  color: "var(--txt)",
  font: "inherit",
  fontSize: 11,
  lineHeight: 1.55,
  padding: "8px 10px",
};

const message = (text: string, role?: "alert" | "status") => (
  <div role={role} style={{ padding: "36px 18px", textAlign: "center", color: role === "alert" ? "var(--crimson)" : "var(--txt3)", fontSize: 10.5, lineHeight: 1.6 }}>
    {text}
  </div>
);

function compareComments(left: InlineCommentDTO, right: InlineCommentDTO, sceneOrder: Map<number, number>): number {
  if (left.resolved !== right.resolved) return left.resolved ? 1 : -1;
  const leftScene = sceneOrder.get(left.anchor.start_scene_id) ?? Number.MAX_SAFE_INTEGER;
  const rightScene = sceneOrder.get(right.anchor.start_scene_id) ?? Number.MAX_SAFE_INTEGER;
  const leftField = left.anchor.start_field === "title" ? 0 : 1;
  const rightField = right.anchor.start_field === "title" ? 0 : 1;
  return leftScene - rightScene
    || leftField - rightField
    || left.anchor.from_offset - right.anchor.from_offset
    || left.id - right.id;
}

interface ThreadOperation {
  threadId: number;
  kind: "resolve" | "edit" | "reply" | "delete-reply" | "delete-thread" | "assistant";
  replyId?: number;
  assistantHandle?: CommentAssistantHandle;
}

function ThreadRow({ comment, selected, disabled, scenesById, buttonRef, onSelect, onKeyDown }: {
  comment: InlineCommentDTO;
  selected: boolean;
  disabled: boolean;
  scenesById: Map<number, SceneDTO>;
  buttonRef: (element: HTMLButtonElement | null) => void;
  onSelect: () => void;
  onKeyDown: (event: ReactKeyboardEvent<HTMLButtonElement>) => void;
}) {
  const replyCount = comment.replies.length;
  const quote = comment.quote.trim() || "No quoted text";
  return (
    <div role="listitem">
      <button
        ref={buttonRef}
        type="button"
        disabled={disabled}
        aria-label={`Open comment on “${quote}”`}
        aria-pressed={selected}
        onClick={onSelect}
        onKeyDown={onKeyDown}
        style={{
          position: "relative", width: "100%", border: "none", borderBottom: "1px solid var(--line2)",
          background: selected ? "linear-gradient(90deg,rgba(76,194,255,.12),transparent)" : "transparent",
          color: "inherit", padding: "12px 13px", textAlign: "left", font: "inherit", cursor: disabled ? "default" : "pointer",
          opacity: disabled ? 0.55 : comment.resolved ? 0.72 : 1,
        }}
      >
        {selected && <span aria-hidden="true" style={{ position: "absolute", inset: "0 auto 0 0", width: 2, background: "var(--accent)", boxShadow: "0 0 8px var(--accent)" }} />}
        <span style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
          <span style={{ flex: 1, minWidth: 0, color: "var(--strong)", fontSize: 11, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>“{quote}”</span>
          {isImportedSource(comment.source_id) && <span style={{ color: "var(--txt3)", fontSize: 6.5, letterSpacing: ".12em" }}>IMPORTED</span>}
          <span style={{ color: comment.resolved ? "var(--green)" : "var(--amber)", border: `1px solid ${comment.resolved ? "rgba(98,217,154,.38)" : "rgba(245,177,51,.38)"}`, padding: "1px 5px", fontSize: 7.5, letterSpacing: ".12em" }}>
            {comment.resolved ? "RESOLVED" : "OPEN"}
          </span>
        </span>
        <span style={{ display: "block", color: "var(--txt2)", fontSize: 9.5, lineHeight: 1.5, maxHeight: 43, overflow: "hidden", whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
          {comment.body || "Empty comment"}
        </span>
        <span style={{ display: "flex", gap: 8, marginTop: 8, color: "var(--txt3)", fontSize: 7.5, letterSpacing: ".04em" }}>
          <span style={{ flex: 1, minWidth: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{anchorLabel(comment, scenesById)}</span>
          <span>{replyCount} {replyCount === 1 ? "REPLY" : "REPLIES"}</span>
        </span>
      </button>
    </div>
  );
}

function AnchorButton({ label, sceneId, sceneTitle, onOpen }: { label: string; sceneId: number; sceneTitle: string; onOpen: (sceneId: number) => void }) {
  return (
    <button type="button" aria-label={`Open ${sceneTitle} in Manuscript`} onClick={() => onOpen(sceneId)} style={{ ...quietButton(), color: "var(--accent)", borderColor: "var(--line-cy)" }}>
      {label}
    </button>
  );
}

function CommentDetail({
  comment, scenesById, operation, now, onToggleResolved, onUpdateBody, onCreateReply,
  onDeleteReply, onDeleteThread, onOpenScene,
}: {
  comment: InlineCommentDTO;
  scenesById: Map<number, SceneDTO>;
  operation: ThreadOperation | null;
  now: number;
  onToggleResolved: () => Promise<boolean>;
  onUpdateBody: (body: string) => Promise<boolean>;
  onCreateReply: (body: string) => Promise<boolean>;
  onDeleteReply: (reply: CommentReplyDTO) => Promise<boolean>;
  onDeleteThread: () => Promise<boolean>;
  onOpenScene: (sceneId: number) => void;
}) {
  const [replyDraft, setReplyDraft] = useState("");
  const [editing, setEditing] = useState(false);
  const [editDraft, setEditDraft] = useState(comment.body);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deletedReplyIds, setDeletedReplyIds] = useState<Set<number>>(() => new Set());
  const confirmDeleteRef = useRef<HTMLButtonElement | null>(null);
  const deleteThreadRef = useRef<HTMLButtonElement | null>(null);
  const editCommentRef = useRef<HTMLButtonElement | null>(null);
  const replyComposerRef = useRef<HTMLTextAreaElement | null>(null);
  const restoreDeleteFocus = useRef(false);
  const restoreEditFocus = useRef(false);
  const restoreReplyFocus = useRef(false);
  const imported = isImportedSource(comment.source_id);
  const busy = operation != null;
  const threadOperation = operation?.threadId === comment.id ? operation : null;
  const { anchor } = comment;
  const startTitle = sceneName(anchor.start_scene_id, scenesById);
  const endTitle = sceneName(anchor.end_scene_id, scenesById);
  const startAvailable = scenesById.has(anchor.start_scene_id);
  const endAvailable = scenesById.has(anchor.end_scene_id);
  const hasDistinctEnd = anchor.end_scene_id !== anchor.start_scene_id;
  const replies = comment.replies
    .filter((reply) => !deletedReplyIds.has(reply.id))
    .slice()
    .sort((left, right) => left.sort_order - right.sort_order || left.id - right.id);

  useEffect(() => {
    setReplyDraft("");
    setEditing(false);
    setEditDraft(comment.body);
    setConfirmDelete(false);
    setDeletedReplyIds(new Set());
  }, [comment.id]);

  useEffect(() => {
    setDeletedReplyIds((current) => {
      const serverIds = new Set(comment.replies.map((reply) => reply.id));
      const next = new Set([...current].filter((id) => serverIds.has(id)));
      return next.size === current.size ? current : next;
    });
  }, [comment.replies]);

  useEffect(() => {
    if (!editing) setEditDraft(comment.body);
  }, [comment.body, editing]);

  useEffect(() => {
    if (confirmDelete) confirmDeleteRef.current?.focus();
    else if (restoreDeleteFocus.current) {
      restoreDeleteFocus.current = false;
      deleteThreadRef.current?.focus();
    }
  }, [confirmDelete]);

  useEffect(() => {
    if (!editing && restoreEditFocus.current) {
      restoreEditFocus.current = false;
      editCommentRef.current?.focus();
    }
  }, [editing]);

  useEffect(() => {
    if (!busy && restoreReplyFocus.current) {
      restoreReplyFocus.current = false;
      replyComposerRef.current?.focus();
    }
  }, [busy, deletedReplyIds]);

  const cancelDelete = () => {
    restoreDeleteFocus.current = true;
    setConfirmDelete(false);
  };

  const cancelEdit = () => {
    setEditDraft(comment.body);
    restoreEditFocus.current = true;
    setEditing(false);
  };

  const submitEdit = async () => {
    if (busy || editDraft === comment.body) return;
    if (await onUpdateBody(editDraft.trim())) {
      restoreEditFocus.current = true;
      setEditing(false);
    }
  };

  const submitReply = async () => {
    const body = replyDraft.trim();
    if (!body || busy) return;
    if (await onCreateReply(body)) setReplyDraft("");
  };

  const assistantThinking = threadOperation?.kind === "assistant";
  const thinkingLabel = threadOperation?.assistantHandle === "counterpart" ? "Counterpart" : "Assistant";

  return (
    <section
      aria-label="Selected comment thread"
      onKeyDown={(event) => {
        if (event.key === "Escape" && confirmDelete && !busy) {
          event.preventDefault();
          cancelDelete();
        }
      }}
      style={{ minWidth: 0, minHeight: 0, height: "100%", overflowY: "auto", padding: "18px 20px 28px" }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 9, paddingBottom: 12, borderBottom: "1px solid var(--line2)", flexWrap: "wrap" }}>
        <span style={{ color: comment.resolved ? "var(--green)" : "var(--amber)", fontSize: 8.5, letterSpacing: ".18em" }}>{comment.resolved ? "✓ RESOLVED" : "● OPEN THREAD"}</span>
        <span title={imported ? `Source id: ${comment.source_id}` : undefined} style={{ color: imported ? "var(--amber)" : "var(--txt3)", fontSize: 7, letterSpacing: ".13em" }}>
          {imported ? "IMPORTED SOURCE" : "NATIVE PRO"}
        </span>
        <span style={{ flex: 1 }} />
        {confirmDelete ? (
          <span role="group" aria-label="Confirm thread deletion" style={{ display: "flex", gap: 5, alignItems: "center" }}>
            <span style={{ color: "var(--crimson)", fontSize: 8 }}>Delete thread and {replies.length} {replies.length === 1 ? "reply" : "replies"}?</span>
            <button ref={confirmDeleteRef} type="button" disabled={busy} onClick={() => { void onDeleteThread(); }} style={{ ...dangerButton, background: "var(--crimson)", color: "white", opacity: busy ? 0.55 : 1 }}>
              {threadOperation?.kind === "delete-thread" ? "DELETING…" : "DELETE PERMANENTLY"}
            </button>
            <button type="button" disabled={busy} onClick={cancelDelete} style={{ ...quietButton(), opacity: busy ? 0.55 : 1 }}>CANCEL</button>
          </span>
        ) : (
          <button ref={deleteThreadRef} type="button" aria-label="Delete comment thread" disabled={busy} onClick={() => setConfirmDelete(true)} style={{ ...dangerButton, opacity: busy ? 0.55 : 1, cursor: busy ? "default" : "pointer" }}>DELETE THREAD</button>
        )}
        <button
          type="button"
          aria-label={comment.resolved ? "Reopen comment" : "Resolve comment"}
          disabled={busy}
          onClick={() => { void onToggleResolved(); }}
          style={{ ...quietButton(comment.resolved), opacity: busy ? 0.55 : 1, cursor: busy ? "default" : "pointer" }}
        >
          {threadOperation?.kind === "resolve" ? "SAVING…" : comment.resolved ? "REOPEN" : "RESOLVE"}
        </button>
      </div>

      <div style={{ marginTop: 15, padding: "12px 14px", border: "1px solid var(--line2)", borderLeft: "2px solid var(--accent)", background: "var(--tint)" }}>
        <div style={{ color: "var(--txt3)", fontSize: 7.5, letterSpacing: ".2em", marginBottom: 6 }}>QUOTED TEXT</div>
        <div style={{ color: "var(--strong)", fontFamily: "'Courier Prime',monospace", fontSize: 13, lineHeight: 1.6, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>“{comment.quote}”</div>
      </div>

      <div style={{ marginTop: 12, padding: "10px 12px", border: "1px solid var(--line2)", background: "var(--panel2)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 7, flexWrap: "wrap" }}>
          <span style={{ color: "var(--txt3)", fontSize: 7.5, letterSpacing: ".2em" }}>ANCHOR</span>
          <span style={{ color: "var(--txt2)", fontSize: 9 }}>{anchorLabel(comment, scenesById)}</span>
          <span style={{ flex: 1 }} />
          {startAvailable
            ? <AnchorButton label="OPEN START SCENE" sceneId={anchor.start_scene_id} sceneTitle={startTitle} onOpen={onOpenScene} />
            : <span style={{ color: "var(--crimson)", fontSize: 8, letterSpacing: ".1em" }}>Anchor unavailable · start scene</span>}
          {hasDistinctEnd && (
            endAvailable
              ? <AnchorButton label="OPEN END SCENE" sceneId={anchor.end_scene_id} sceneTitle={endTitle} onOpen={onOpenScene} />
              : <span style={{ color: "var(--crimson)", fontSize: 8, letterSpacing: ".1em" }}>Anchor unavailable · end scene</span>
          )}
        </div>
        {(anchor.prefix || anchor.suffix) && (
          <div style={{ marginTop: 7, color: "var(--txt3)", fontSize: 8.5, lineHeight: 1.45, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
            {anchor.prefix ? `…${anchor.prefix}` : ""}<span style={{ color: "var(--txt2)" }}>〔quoted text〕</span>{anchor.suffix ? `${anchor.suffix}…` : ""}
          </div>
        )}
      </div>

      <div style={{ marginTop: 18 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 7 }}>
          <span style={{ color: "var(--txt3)", fontSize: 7.5, letterSpacing: ".2em" }}>COMMENT</span>
          <span style={{ flex: 1 }} />
          {!editing && (
            <button ref={editCommentRef} type="button" aria-label="Edit comment body" disabled={busy} onClick={() => setEditing(true)} style={{ ...quietButton(), opacity: busy ? 0.55 : 1 }}>EDIT</button>
          )}
        </div>
        {editing ? (
          <form onSubmit={(event) => { event.preventDefault(); void submitEdit(); }}>
            <textarea
              autoFocus
              aria-label="Edit comment body"
              value={editDraft}
              disabled={busy}
              onChange={(event) => setEditDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  event.preventDefault();
                  cancelEdit();
                } else if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                  event.preventDefault();
                  void submitEdit();
                }
              }}
              style={textAreaStyle}
            />
            <div style={{ display: "flex", alignItems: "center", gap: 7, marginTop: 7 }}>
              <button type="submit" disabled={busy || editDraft === comment.body} style={{ ...quietButton(true), opacity: busy || editDraft === comment.body ? 0.55 : 1 }}>{threadOperation?.kind === "edit" ? "SAVING…" : "SAVE COMMENT"}</button>
              <button type="button" disabled={busy} onClick={cancelEdit} style={{ ...quietButton(), opacity: busy ? 0.55 : 1 }}>CANCEL</button>
              <span style={{ color: "var(--txt3)", fontSize: 7.5 }}>Ctrl/⌘ + Enter to save · Esc to cancel</span>
            </div>
          </form>
        ) : (
          <div style={{ color: "var(--txt)", fontSize: 12, lineHeight: 1.65, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{comment.body || <em style={{ color: "var(--txt3)" }}>Empty comment</em>}</div>
        )}
        <time title={absoluteTime(comment.created_at)} dateTime={comment.created_at} style={{ display: "block", marginTop: 7, color: "var(--txt3)", fontSize: 8 }}>
          Created {formatRelativeTime(comment.created_at, now)}
          {comment.updated_at !== comment.created_at ? ` · updated ${formatRelativeTime(comment.updated_at, now)}` : ""}
        </time>
      </div>

      <div style={{ marginTop: 22, paddingTop: 14, borderTop: "1px solid var(--line2)" }}>
        <div style={{ color: "var(--txt3)", fontSize: 7.5, letterSpacing: ".2em", marginBottom: 9 }}>REPLIES · {replies.length}</div>
        {replies.length === 0 && !assistantThinking ? (
          <div style={{ color: "var(--txt3)", fontSize: 10, fontStyle: "italic" }}>No replies in this thread.</div>
        ) : (
          <div role="list" aria-label="Replies" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {replies.map((reply) => {
              const replyImported = isImportedSource(reply.source_id);
              const deleting = threadOperation?.kind === "delete-reply" && threadOperation.replyId === reply.id;
              return (
                <article key={reply.id} role="listitem" style={{ padding: "10px 11px", border: "1px solid var(--line2)", background: "var(--tint)" }}>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 5 }}>
                    <span style={{ color: "var(--accent)", fontSize: 9, fontWeight: 600 }}>{reply.author || "Unknown author"}</span>
                    {replyImported && <span title={`Source id: ${reply.source_id}`} style={{ color: "var(--amber)", fontSize: 6.5, letterSpacing: ".12em" }}>IMPORTED</span>}
                    <time title={absoluteTime(reply.created_at)} dateTime={reply.created_at} style={{ color: "var(--txt3)", fontSize: 7.5 }}>{formatRelativeTime(reply.created_at, now)}</time>
                    <span style={{ flex: 1 }} />
                    <button
                      type="button"
                      aria-label={`Delete reply from ${reply.author || "Unknown author"}`}
                      disabled={busy}
                      onClick={() => {
                          void onDeleteReply(reply).then((deleted) => {
                            if (deleted) {
                              restoreReplyFocus.current = true;
                              setDeletedReplyIds((current) => new Set(current).add(reply.id));
                            }
                        });
                      }}
                      style={{ ...dangerButton, padding: "2px 6px", opacity: busy ? 0.55 : 1, cursor: busy ? "default" : "pointer" }}
                    >
                      {deleting ? "DELETING…" : "DELETE"}
                    </button>
                  </div>
                  <div style={{ color: "var(--txt)", fontSize: 10.5, lineHeight: 1.55, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{reply.body}</div>
                </article>
              );
            })}
            {assistantThinking && (
              <div role="status" aria-live="polite" style={{ padding: "10px 11px", border: "1px dashed var(--line-cy)", color: "var(--accent)", fontSize: 10 }}>
                {thinkingLabel} is thinking…
              </div>
            )}
          </div>
        )}

        <form onSubmit={(event) => { event.preventDefault(); void submitReply(); }} style={{ marginTop: 12 }}>
          <label htmlFor={`comment-reply-${comment.id}`} style={{ display: "block", color: "var(--txt3)", fontSize: 7.5, letterSpacing: ".18em", marginBottom: 6 }}>ADD REPLY</label>
          <textarea
            ref={replyComposerRef}
            id={`comment-reply-${comment.id}`}
            aria-label="Reply to comment"
            aria-describedby={`comment-reply-help-${comment.id}`}
            value={replyDraft}
            disabled={busy}
            onChange={(event) => setReplyDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                event.preventDefault();
                void submitReply();
              }
            }}
            placeholder="Write a reply… Mention @assistant or @counterpart for an AI response."
            style={textAreaStyle}
          />
          <div style={{ display: "flex", alignItems: "center", gap: 9, marginTop: 7 }}>
            <button type="submit" disabled={busy || !replyDraft.trim()} style={{ ...quietButton(true), opacity: busy || !replyDraft.trim() ? 0.55 : 1 }}>
              {threadOperation?.kind === "reply" ? "POSTING…" : assistantThinking ? `${thinkingLabel.toUpperCase()} THINKING…` : "POST REPLY"}
            </button>
            <span id={`comment-reply-help-${comment.id}`} style={{ color: "var(--txt3)", fontSize: 7.5 }}>Ctrl/⌘ + Enter to post</span>
          </div>
        </form>
      </div>
    </section>
  );
}

export function CommentsPanel(props: PanelProps) {
  const { api, platform, projectId } = useStudio();
  const navigate = useNavigate();
  const mounted = useMountedRef();
  const { data: commentsData, loading, error, refetch } = useComments();
  const { data: scenesData } = useScenes();
  const [hideResolved, setHideResolved] = useHideResolvedPreference();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [operation, setOperation] = useState<ThreadOperation | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [exportStatus, setExportStatus] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [deletedThreadId, setDeletedThreadId] = useState<number | null>(null);
  const [now, setNow] = useState(Date.now);
  const operationRef = useRef<ThreadOperation | null>(null);
  const mutationSequence = useRef(0);
  const exportSequence = useRef(0);
  const projectIdRef = useRef(projectId);
  const threadButtonRefs = useRef(new Map<number, HTMLButtonElement>());
  projectIdRef.current = projectId;

  const comments = (commentsData ?? []).filter((comment) => comment.id !== deletedThreadId);
  const scenes = scenesData ?? [];
  const scenesById = useMemo(() => new Map(scenes.map((scene) => [scene.id, scene])), [scenes]);
  const sceneOrder = useMemo(
    () => new Map([...scenes].sort((left, right) => left.sort_order - right.sort_order || left.id - right.id).map((scene, index) => [scene.id, index])),
    [scenes],
  );
  const openCount = comments.filter((comment) => !comment.resolved).length;
  const resolvedCount = comments.length - openCount;
  const visible = useMemo(
    () => comments
      .filter((comment) => !hideResolved || !comment.resolved)
      .slice()
      .sort((left, right) => compareComments(left, right, sceneOrder)),
    [comments, hideResolved, sceneOrder],
  );
  const selected = visible.find((comment) => comment.id === selectedId) ?? visible[0] ?? null;

  useEffect(() => {
    mutationSequence.current += 1;
    exportSequence.current += 1;
    operationRef.current = null;
    setSelectedId(null);
    setOperation(null);
    setActionError(null);
    setExportStatus(null);
    setExporting(false);
    setDeletedThreadId(null);
  }, [api, projectId]);

  useEffect(() => {
    if (deletedThreadId != null && commentsData && !commentsData.some((comment) => comment.id === deletedThreadId)) {
      setDeletedThreadId(null);
    }
  }, [commentsData, deletedThreadId]);

  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    const timer = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const beginOperation = (next: ThreadOperation): number | null => {
    if (projectId == null || operationRef.current != null) return null;
    operationRef.current = next;
    setOperation(next);
    setActionError(null);
    setExportStatus(null);
    return ++mutationSequence.current;
  };

  const isCurrent = (sequence: number, ownerProjectId: number) => (
    mounted.current && mutationSequence.current === sequence && projectIdRef.current === ownerProjectId
  );

  const finishOperation = (sequence: number, ownerProjectId: number) => {
    if (!isCurrent(sequence, ownerProjectId)) return;
    operationRef.current = null;
    setOperation(null);
  };

  const toggleResolved = async (comment: InlineCommentDTO): Promise<boolean> => {
    if (projectId == null) return false;
    const ownerProjectId = projectId;
    const sequence = beginOperation({ threadId: comment.id, kind: "resolve" });
    if (sequence == null) return false;
    try {
      await trackProjectWrite(api.updateComment(ownerProjectId, comment.id, { resolved: !comment.resolved }));
      if (isCurrent(sequence, ownerProjectId)) refetch();
      return true;
    } catch (updateError) {
      if (isCurrent(sequence, ownerProjectId)) {
        setActionError(`Couldn't ${comment.resolved ? "reopen" : "resolve"} the comment — ${updateError instanceof Error ? updateError.message : String(updateError)}`);
      }
      return false;
    } finally {
      finishOperation(sequence, ownerProjectId);
    }
  };

  const updateBody = async (comment: InlineCommentDTO, body: string): Promise<boolean> => {
    if (projectId == null) return false;
    const ownerProjectId = projectId;
    const sequence = beginOperation({ threadId: comment.id, kind: "edit" });
    if (sequence == null) return false;
    try {
      await trackProjectWrite(api.updateComment(ownerProjectId, comment.id, { body }));
      if (isCurrent(sequence, ownerProjectId)) refetch();
      return true;
    } catch (updateError) {
      if (isCurrent(sequence, ownerProjectId)) setActionError(`Couldn't update the comment — ${updateError instanceof Error ? updateError.message : String(updateError)}`);
      return false;
    } finally {
      finishOperation(sequence, ownerProjectId);
    }
  };

  const appendAssistantReply = async (comment: InlineCommentDTO, writerMessage: string, handle: CommentAssistantHandle, ownerProjectId: number): Promise<void> => {
    const showProgress = mounted.current && projectIdRef.current === ownerProjectId;
    const sequence = showProgress
      ? beginOperation({ threadId: comment.id, kind: "assistant", assistantHandle: handle })
      : null;
    const label = handle === "counterpart" ? "Counterpart" : "Assistant";
    try {
      await persistCommentAssistantReply(api, ownerProjectId, comment, writerMessage, handle);
      if (sequence != null && isCurrent(sequence, ownerProjectId)) refetch();
    } catch (assistantError) {
      if (sequence != null && isCurrent(sequence, ownerProjectId)) {
        setActionError(`Your reply was saved, but ${label} couldn't answer — ${assistantError instanceof Error ? assistantError.message : String(assistantError)}`);
      }
    } finally {
      if (sequence != null) finishOperation(sequence, ownerProjectId);
    }
  };

  const createReply = async (comment: InlineCommentDTO, body: string): Promise<boolean> => {
    if (projectId == null) return false;
    const ownerProjectId = projectId;
    const sequence = beginOperation({ threadId: comment.id, kind: "reply" });
    if (sequence == null) return false;
    const mention = detectCommentAssistantMention(body);
    let saved = false;
    try {
      await trackProjectWrite(api.createCommentReply(ownerProjectId, comment.id, { body, author: "you" }));
      saved = true;
      if (isCurrent(sequence, ownerProjectId)) refetch();
    } catch (replyError) {
      if (isCurrent(sequence, ownerProjectId)) setActionError(`Couldn't post the reply — ${replyError instanceof Error ? replyError.message : String(replyError)}`);
    } finally {
      finishOperation(sequence, ownerProjectId);
    }
    if (saved && mention) {
      void appendAssistantReply(comment, body, mention, ownerProjectId);
    }
    return saved;
  };

  const deleteReply = async (comment: InlineCommentDTO, reply: CommentReplyDTO): Promise<boolean> => {
    if (projectId == null) return false;
    const ownerProjectId = projectId;
    const sequence = beginOperation({ threadId: comment.id, kind: "delete-reply", replyId: reply.id });
    if (sequence == null) return false;
    try {
      await trackProjectWrite(api.deleteCommentReply(ownerProjectId, comment.id, reply.id));
      if (isCurrent(sequence, ownerProjectId)) refetch();
      return true;
    } catch (deleteError) {
      if (isCurrent(sequence, ownerProjectId)) setActionError(`Couldn't delete the reply — ${deleteError instanceof Error ? deleteError.message : String(deleteError)}`);
      return false;
    } finally {
      finishOperation(sequence, ownerProjectId);
    }
  };

  const deleteThread = async (comment: InlineCommentDTO): Promise<boolean> => {
    if (projectId == null) return false;
    const ownerProjectId = projectId;
    const sequence = beginOperation({ threadId: comment.id, kind: "delete-thread" });
    if (sequence == null) return false;
    try {
      await trackProjectWrite(api.deleteComment(ownerProjectId, comment.id));
      if (isCurrent(sequence, ownerProjectId)) {
        setDeletedThreadId(comment.id);
        setSelectedId(null);
        refetch();
      }
      return true;
    } catch (deleteError) {
      if (isCurrent(sequence, ownerProjectId)) setActionError(`Couldn't delete the thread — ${deleteError instanceof Error ? deleteError.message : String(deleteError)}`);
      return false;
    } finally {
      finishOperation(sequence, ownerProjectId);
    }
  };

  const exportComments = async () => {
    if (exporting) return;
    const ownerProjectId = projectId;
    const sequence = ++exportSequence.current;
    const isCurrentExport = () => mounted.current
      && exportSequence.current === sequence
      && projectIdRef.current === ownerProjectId;
    setExporting(true);
    setActionError(null);
    setExportStatus(null);
    try {
      const ordered = comments.slice().sort((left, right) => compareComments(left, right, sceneOrder));
      const result = await platform.saveFile({
        suggestedName: commentReportFilename(projectId),
        content: buildCommentReport(ordered, scenesById),
        mimeType: "text/markdown;charset=utf-8",
      });
      if (!result.canceled && isCurrentExport()) setExportStatus(result.path ? `Comment report saved · ${result.path}` : "Comment report saved");
    } catch (saveError) {
      if (isCurrentExport()) setActionError(`Couldn't save the comment report — ${saveError instanceof Error ? saveError.message : String(saveError)}`);
    } finally {
      if (isCurrentExport()) setExporting(false);
    }
  };

  const openScene = (sceneId: number) => {
    if (!scenesById.has(sceneId)) {
      setActionError(`The anchored scene (#${sceneId}) is no longer available.`);
      return;
    }
    navigate("Manuscript", { sceneId });
  };

  const moveThreadFocus = (commentId: number, event: ReactKeyboardEvent<HTMLButtonElement>) => {
    const currentIndex = visible.findIndex((comment) => comment.id === commentId);
    if (currentIndex < 0) return;
    let nextIndex: number | null = null;
    if (event.key === "ArrowDown") nextIndex = Math.min(visible.length - 1, currentIndex + 1);
    else if (event.key === "ArrowUp") nextIndex = Math.max(0, currentIndex - 1);
    else if (event.key === "Home") nextIndex = 0;
    else if (event.key === "End") nextIndex = visible.length - 1;
    if (nextIndex == null || nextIndex === currentIndex) return;
    event.preventDefault();
    const next = visible[nextIndex];
    if (!next) return;
    setSelectedId(next.id);
    threadButtonRefs.current.get(next.id)?.focus();
  };

  return (
    <PanelShell {...props}>
      <div data-screen-label="Comments Panel" style={panelBox}>
        <Corners />
        <header style={{ minHeight: 42, flex: "none", display: "flex", alignItems: "center", gap: 11, padding: "5px 16px", borderBottom: "1px solid var(--line)", flexWrap: "wrap" }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".12em", color: "var(--strong)" }}>COMMENTS</span>
          <span style={{ color: "var(--amber)", fontSize: 8 }}>{openCount} OPEN</span>
          <span style={{ color: "var(--green)", fontSize: 8 }}>{resolvedCount} RESOLVED</span>
          <span style={{ flex: 1 }} />
          <button type="button" aria-label="Export comments as Markdown" disabled={exporting || loading} onClick={() => { void exportComments(); }} style={{ ...quietButton(), opacity: exporting || loading ? 0.55 : 1 }}>{exporting ? "EXPORTING…" : "EXPORT .MD"}</button>
          <button type="button" aria-label="Show all comments" aria-pressed={!hideResolved} onClick={() => setHideResolved(false)} style={quietButton(!hideResolved)}>ALL · {comments.length}</button>
          <button type="button" aria-label="Show open comments" aria-pressed={hideResolved} onClick={() => setHideResolved(true)} style={quietButton(hideResolved)}>OPEN · {openCount}</button>
        </header>
        {actionError && (
          <div role="alert" style={{ flex: "none", display: "flex", alignItems: "center", gap: 9, borderBottom: "1px solid var(--crimson)", background: "rgba(232,68,58,.08)", color: "var(--crimson)", padding: "7px 16px", fontSize: 9.5 }}>
            <span style={{ flex: 1 }}>{actionError}</span>
            <button type="button" aria-label="Dismiss comment error" onClick={() => setActionError(null)} style={{ ...quietButton(), color: "var(--crimson)", borderColor: "rgba(232,68,58,.45)" }}>DISMISS</button>
          </div>
        )}
        {exportStatus && <div role="status" aria-live="polite" style={{ flex: "none", borderBottom: "1px solid var(--green)", color: "var(--green)", padding: "7px 16px", fontSize: 9.5 }}>{exportStatus}</div>}
        <div style={{ flex: 1, minHeight: 0, display: "grid", gridTemplateColumns: "minmax(290px,36%) minmax(0,1fr)" }}>
          <div style={{ minWidth: 0, minHeight: 0, borderRight: "1px solid var(--line)", background: "var(--panel2)", overflowY: "auto" }}>
            {loading
              ? message("Loading comments…", "status")
              : error
                ? (
                    <div role="alert" style={{ padding: "30px 16px", textAlign: "center", color: "var(--crimson)", fontSize: 10, lineHeight: 1.6 }}>
                      <div>Couldn't load comments — {error}</div>
                      <button type="button" onClick={refetch} style={{ ...quietButton(), marginTop: 10 }}>RETRY</button>
                    </div>
                  )
                : comments.length === 0
                  ? message("No comment threads in this project.")
                  : visible.length === 0
                    ? message("No open comments. Choose ALL to review resolved threads.")
                    : (
                        <div role="list" aria-label="Comment threads">
                          {visible.map((comment) => (
                            <ThreadRow
                              key={comment.id}
                              comment={comment}
                              selected={selected?.id === comment.id}
                              disabled={operation != null}
                              scenesById={scenesById}
                              buttonRef={(element) => {
                                if (element) threadButtonRefs.current.set(comment.id, element);
                                else threadButtonRefs.current.delete(comment.id);
                              }}
                              onSelect={() => setSelectedId(comment.id)}
                              onKeyDown={(event) => moveThreadFocus(comment.id, event)}
                            />
                          ))}
                        </div>
                      )}
          </div>
          {selected
            ? (
                <CommentDetail
                  key={selected.id}
                  comment={selected}
                  scenesById={scenesById}
                  operation={operation}
                  now={now}
                  onToggleResolved={() => toggleResolved(selected)}
                  onUpdateBody={(body) => updateBody(selected, body)}
                  onCreateReply={(body) => createReply(selected, body)}
                  onDeleteReply={(reply) => deleteReply(selected, reply)}
                  onDeleteThread={() => deleteThread(selected)}
                  onOpenScene={openScene}
                />
              )
            : message(loading ? "Loading thread…" : "Select a comment thread.")}
        </div>
      </div>
    </PanelShell>
  );
}
