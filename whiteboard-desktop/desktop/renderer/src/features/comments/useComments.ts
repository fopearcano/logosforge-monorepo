/** Per-document comments state: load on doc switch, optimistic create/edit/delete. */

import { useCallback, useEffect, useState } from 'react';

import { useCurrentDocId } from '../../state/currentDocument';
import {
  type Comment,
  type CommentAnchor,
  type CommentDraft,
  type CommentReply,
  addReply as apiAddReply,
  createComment,
  deleteComment,
  deleteReply as apiDeleteReply,
  getComments,
  updateComment,
} from './commentsApi';

export interface CommentsApi {
  comments: Comment[];
  loading: boolean;
  error: string | null;
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

  // Auto-dismiss a surfaced error so it doesn't linger.
  useEffect(() => {
    if (!error) return undefined;
    const t = setTimeout(() => setError(null), 4000);
    return () => clearTimeout(t);
  }, [error]);

  const load = useCallback(async () => {
    if (!ready) return;
    setLoading(true);
    try {
      setComments(await getComments(baseUrl));
    } catch {
      /* keep the last good list */
    } finally {
      setLoading(false);
    }
  }, [baseUrl, ready]);

  // Initial load + reload whenever the active document changes.
  useEffect(() => {
    setComments([]);
    void load();
  }, [docId, load]);

  const add = useCallback(
    async (draft: CommentDraft) => {
      try {
        const created = await createComment(draft, baseUrl);
        setComments((prev) => [...prev, created]);
        return created;
      } catch {
        setError('Could not add comment — it was not saved.');
        return null;
      }
    },
    [baseUrl],
  );

  const edit = useCallback(
    async (id: string, patch: { body?: string; resolved?: boolean; anchor?: CommentAnchor }) => {
      setComments((prev) => prev.map((c) => (c.id === id ? { ...c, ...patch } : c)));
      try {
        const updated = await updateComment(id, patch, baseUrl);
        setComments((prev) => prev.map((c) => (c.id === id ? updated : c)));
      } catch {
        setError('Could not save comment — reverting.');
        void load(); // resync from the backend, dropping the optimistic value
      }
    },
    [baseUrl, load],
  );

  const remove = useCallback(
    async (id: string) => {
      setComments((prev) => prev.filter((c) => c.id !== id));
      try {
        await deleteComment(id, baseUrl);
      } catch {
        setError('Could not delete comment — restoring.');
        void load(); // resync, re-adding the comment that failed to delete
      }
    },
    [baseUrl, load],
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
      // Optimistic: show the reply (and a "thinking…" placeholder when an assistant
      // is @-mentioned) immediately; the server response (incl. any AI reply) replaces it.
      const stamp = new Date().toISOString();
      const optimistic: CommentReply[] = [{ id: `tmp-${Date.now()}`, body, author: 'you', created_at: stamp }];
      const m = body.match(/@(billy|logos)\b/i);
      if (m) {
        const who = m[1][0].toUpperCase() + m[1].slice(1).toLowerCase();
        optimistic.push({ id: `tmp-ai-${Date.now()}`, body: `${who} is thinking…`, author: who, created_at: stamp });
      }
      setComments((prev) => prev.map((c) => (c.id === id ? { ...c, replies: [...c.replies, ...optimistic] } : c)));
      try {
        replace(await apiAddReply(id, body, baseUrl));
      } catch {
        setError('Could not add reply.');
        void load();
      }
    },
    [baseUrl, replace, load],
  );

  const removeReply = useCallback(
    async (id: string, replyId: string) => {
      try {
        replace(await apiDeleteReply(id, replyId, baseUrl));
      } catch {
        setError('Could not delete reply.');
      }
    },
    [baseUrl, replace],
  );

  return { comments, loading, error, add, edit, remove, addReply, removeReply, reload: () => void load() };
}
