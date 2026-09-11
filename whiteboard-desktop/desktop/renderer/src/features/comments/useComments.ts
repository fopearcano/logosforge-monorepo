/** Per-document comments state: load on doc switch, optimistic create/edit/delete. */

import { useCallback, useEffect, useRef, useState } from 'react';

import {
  captureDocumentIdentity,
  markPendingDocSave,
  runPendingDocWrite,
  runSerializedPendingDocWrite,
  type CapturedDocumentIdentity,
  useCurrentDocId,
  waitForPendingDocWrites,
} from '../../state/currentDocument';
import {
  type Comment,
  type CommentAnchor,
  type CommentDraft,
  type CommentReply,
  addReply as apiAddReply,
  createComment,
  deleteComment,
  deleteReply as apiDeleteReply,
  getCommentsForDocument,
  updateComment,
} from './commentsApi';
import {
  applyRetainedCommentIntent,
  applyRetainedCommentIntents,
  configureRetainedCommentIntentWriter,
  discardRetainedCommentIntent,
  flushRetainedCommentIntent,
  hasRetainedCommentIntent,
  retainCommentPatch,
  retainOptimisticCommentReplies,
  subscribeRetainedCommentIntent,
  type CommentPatch,
} from './commentMutationIntent';

function isCurrentIdentity(identity: CapturedDocumentIdentity): boolean {
  const current = captureDocumentIdentity();
  return (
    current.documentId === identity.documentId
    && current.incarnation === identity.incarnation
  );
}

function createReplyClientId(): string {
  const randomUuid = globalThis.crypto?.randomUUID?.();
  if (randomUuid) return `reply-${randomUuid}`;
  return `reply-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export interface CommentsApi {
  comments: Comment[];
  loading: boolean;
  error: string | null;
  dismissError: () => void;
  add: (draft: CommentDraft) => Promise<Comment | null>;
  edit: (
    id: string,
    patch: { body?: string; resolved?: boolean; anchor?: CommentAnchor },
  ) => Promise<void>;
  remove: (id: string) => Promise<void>;
  addReply: (id: string, body: string) => Promise<void>;
  removeReply: (id: string, replyId: string) => Promise<void>;
  reload: () => void;
}

export function useComments(baseUrl: string, ready: boolean): CommentsApi {
  const docId = useCurrentDocId();
  const [comments, setComments] = useState<Comment[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loadSeq = useRef(0);
  const commentMutationSeq = useRef(new Map<string, number>());
  const invalidateLoad = useCallback(() => {
    loadSeq.current += 1;
    setLoading(false);
  }, []);
  const beginCommentMutation = useCallback((id: string): number => {
    const next = (commentMutationSeq.current.get(id) ?? 0) + 1;
    commentMutationSeq.current.set(id, next);
    return next;
  }, []);
  const isLatestCommentMutation = useCallback(
    (id: string, sequence: number): boolean => commentMutationSeq.current.get(id) === sequence,
    [],
  );

  const persistRetainedIntent = useCallback(
    async (identity: CapturedDocumentIdentity, id: string): Promise<Comment | null> => (
      flushRetainedCommentIntent(identity, id, {
        update: (patch) => updateComment(id, patch, baseUrl, undefined, identity),
        addReply: (reply) => apiAddReply(
          id,
          reply.body,
          baseUrl,
          undefined,
          reply.id,
          identity,
        ),
      })
    ),
    [baseUrl],
  );

  // Configure an app-lifetime owner rather than making the hook own the close
  // flusher. Its explicit-id transport survives a render-boundary remount; this
  // listener only reconciles successful retries while a view is mounted.
  useEffect(() => {
    configureRetainedCommentIntentWriter(persistRetainedIntent);
    return subscribeRetainedCommentIntent((identity, id, updated) => {
      if (!isCurrentIdentity(identity)) return;
      setComments((prev) => prev.map((comment) => (
        comment.id === id
          ? applyRetainedCommentIntent(identity, updated)
          : comment
      )));
    });
  }, [persistRetainedIntent]);

  const load = useCallback(async () => {
    if (!ready) return;
    const requestIdentity = captureDocumentIdentity();
    const requestDocId = requestIdentity.documentId;
    if (!requestDocId) {
      setLoading(false);
      return;
    }
    const seq = (loadSeq.current += 1);
    setLoading(true);
    try {
      // A root-boundary remount can begin while the retiring hook's mutation is
      // still settling. Read only after that shared write barrier, and address
      // the captured document explicitly rather than the mutable singleton.
      await waitForPendingDocWrites();
      if (!isCurrentIdentity(requestIdentity) || seq !== loadSeq.current) return;
      const loaded = await getCommentsForDocument(baseUrl, requestDocId);
      if (!isCurrentIdentity(requestIdentity) || seq !== loadSeq.current) return;
      setComments(applyRetainedCommentIntents(requestIdentity, loaded));
    } catch (err) {
      if (!isCurrentIdentity(requestIdentity) || seq !== loadSeq.current) return;
      setError(err instanceof Error ? err.message : 'Could not load comments.');
      /* keep the last good list */
    } finally {
      if (isCurrentIdentity(requestIdentity) && seq === loadSeq.current) setLoading(false);
    }
  }, [baseUrl, ready]);

  // Initial load + reload whenever the active document changes.
  useEffect(() => {
    setComments([]);
    setError(null);
    void load();
  }, [docId, load]);

  const add = useCallback(
    async (draft: CommentDraft) => {
      const operationIdentity = captureDocumentIdentity();
      const operationDocId = operationIdentity.documentId;
      invalidateLoad();
      try {
        const created = await runPendingDocWrite(
          () => createComment(draft, baseUrl, undefined, operationIdentity),
          operationDocId,
        );
        if (!isCurrentIdentity(operationIdentity)) return null;
        setComments((prev) => [...prev, created]);
        return created;
      } catch (err) {
        if (!isCurrentIdentity(operationIdentity)) return null;
        setError(err instanceof Error ? err.message : 'Could not add comment — it was not saved.');
        return null;
      }
    },
    [baseUrl, invalidateLoad],
  );

  const edit = useCallback(
    async (id: string, patch: CommentPatch) => {
      const operationIdentity = captureDocumentIdentity();
      const operationDocId = operationIdentity.documentId;
      const mutation = beginCommentMutation(id);
      invalidateLoad();
      // Keep independently editable fields until a response acknowledges the
      // exact values sent. Thus a later body edit also carries an earlier failed
      // resolve toggle instead of silently replacing it.
      retainCommentPatch(operationIdentity, id, patch);
      markPendingDocSave();
      setComments((prev) => prev.map((c) => (c.id === id ? { ...c, ...patch } : c)));
      try {
        const updated = await runSerializedPendingDocWrite(
          `comment:${id}`,
          () => persistRetainedIntent(operationIdentity, id),
          operationDocId,
        );
        if (!isCurrentIdentity(operationIdentity)) return;
        if (updated) {
          setComments((prev) => prev.map((c) => (
            c.id === id ? applyRetainedCommentIntent(operationIdentity, updated) : c
          )));
        }
        if (
          isLatestCommentMutation(id, mutation)
          && hasRetainedCommentIntent(operationIdentity, id)
        ) {
          setError('Some comment changes are still unsaved.');
        }
      } catch (err) {
        if (
          !isCurrentIdentity(operationIdentity)
          || !isLatestCommentMutation(id, mutation)
        ) return;
        // Leave the optimistic overlay visible and retained. A later edit sends
        // every still-unacknowledged field, while a remount/load reapplies it.
        setError(err instanceof Error ? err.message : 'Could not save comment.');
      }
    },
    [beginCommentMutation, invalidateLoad, isLatestCommentMutation, persistRetainedIntent],
  );

  const remove = useCallback(
    async (id: string) => {
      const operationIdentity = captureDocumentIdentity();
      const operationDocId = operationIdentity.documentId;
      const mutation = beginCommentMutation(id);
      invalidateLoad();
      setComments((prev) => prev.filter((c) => c.id !== id));
      try {
        await runSerializedPendingDocWrite(
          `comment:${id}`,
          () => deleteComment(id, baseUrl, undefined, operationIdentity),
          operationDocId,
        );
        discardRetainedCommentIntent(operationIdentity, id);
      } catch (err) {
        if (
          !isCurrentIdentity(operationIdentity)
          || !isLatestCommentMutation(id, mutation)
        ) return;
        setError(err instanceof Error ? err.message : 'Could not delete comment — restoring.');
        void load(); // resync, re-adding the comment that failed to delete
      }
    },
    [baseUrl, beginCommentMutation, invalidateLoad, isLatestCommentMutation, load],
  );

  // Reply ops await the server (which returns the updated comment) then swap it in
  // — simpler than optimistic temp-id reconciliation, and replies aren't latency-
  // critical. Failures surface via the error channel.
  const replace = useCallback(
    (updated: Comment) => setComments((prev) => prev.map((c) => (c.id === updated.id ? updated : c))),
    [],
  );

  const addReply = useCallback(
    async (id: string, body: string) => {
      const operationIdentity = captureDocumentIdentity();
      const operationDocId = operationIdentity.documentId;
      const mutation = beginCommentMutation(id);
      invalidateLoad();
      // Optimistic: show the reply (and a "thinking…" placeholder when an assistant
      // is @-mentioned) immediately; the server response (incl. any AI reply) replaces it.
      const stamp = new Date().toISOString();
      const optimisticReply: CommentReply = {
        id: createReplyClientId(),
        body,
        author: 'you',
        created_at: stamp,
      };
      const optimistic: CommentReply[] = [optimisticReply];
      const transientReplyIds: string[] = [];
      const m = body.match(/@(billy|logos)\b/i);
      if (m) {
        const who = m[1][0].toUpperCase() + m[1].slice(1).toLowerCase();
        const thinking: CommentReply = {
          id: `tmp-ai-${Date.now()}-${mutation}`,
          body: `${who} is thinking…`,
          author: who,
          created_at: stamp,
        };
        transientReplyIds.push(thinking.id);
        optimistic.push(thinking);
      }
      // Retain the writer's reply, but not the transient assistant placeholder:
      // a failed request must never leave “thinking…” behind indefinitely.
      retainOptimisticCommentReplies(operationIdentity, id, [optimisticReply]);
      markPendingDocSave();
      setComments((prev) => prev.map((c) => (c.id === id ? { ...c, replies: [...c.replies, ...optimistic] } : c)));
      try {
        const updated = await runSerializedPendingDocWrite(
          `comment:${id}`,
          () => persistRetainedIntent(operationIdentity, id),
          operationDocId,
        );
        if (!isCurrentIdentity(operationIdentity)) return;
        if (updated) replace(applyRetainedCommentIntent(operationIdentity, updated));
        if (
          isLatestCommentMutation(id, mutation)
          && hasRetainedCommentIntent(operationIdentity, id)
        ) {
          setError('Some comment changes are still unsaved.');
        }
      } catch (err) {
        if (isCurrentIdentity(operationIdentity) && transientReplyIds.length) {
          const transient = new Set(transientReplyIds);
          setComments((prev) => prev.map((comment) => (
            comment.id === id
              ? { ...comment, replies: comment.replies.filter((reply) => !transient.has(reply.id)) }
              : comment
          )));
        }
        if (
          !isCurrentIdentity(operationIdentity)
          || !isLatestCommentMutation(id, mutation)
        ) return;
        setError(err instanceof Error ? err.message : 'Could not add reply.');
      }
    },
    [
      beginCommentMutation,
      invalidateLoad,
      isLatestCommentMutation,
      persistRetainedIntent,
      replace,
    ],
  );

  const removeReply = useCallback(
    async (id: string, replyId: string) => {
      const operationIdentity = captureDocumentIdentity();
      const operationDocId = operationIdentity.documentId;
      const mutation = beginCommentMutation(id);
      invalidateLoad();
      try {
        const updated = await runSerializedPendingDocWrite(
          `comment:${id}`,
          () => apiDeleteReply(id, replyId, baseUrl, undefined, operationIdentity),
          operationDocId,
        );
        if (!isCurrentIdentity(operationIdentity)) return;
        replace(applyRetainedCommentIntent(operationIdentity, updated));
        if (
          isLatestCommentMutation(id, mutation)
          && hasRetainedCommentIntent(operationIdentity, id)
        ) {
          setError('Some comment changes are still unsaved.');
        }
      } catch (err) {
        if (
          !isCurrentIdentity(operationIdentity)
          || !isLatestCommentMutation(id, mutation)
        ) return;
        setError(err instanceof Error ? err.message : 'Could not delete reply.');
      }
    },
    [baseUrl, beginCommentMutation, invalidateLoad, isLatestCommentMutation, replace],
  );

  return {
    comments,
    loading,
    error,
    dismissError: () => setError(null),
    add,
    edit,
    remove,
    addReply,
    removeReply,
    reload: () => void load(),
  };
}
