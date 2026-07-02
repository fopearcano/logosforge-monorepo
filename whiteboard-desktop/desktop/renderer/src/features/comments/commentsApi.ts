/**
 * Frontend client for per-document inline comments.
 *
 *   GET    /api/comments       → load the active doc's comments
 *   POST   /api/comments       → create a comment (anchor + quote + body)
 *   PUT    /api/comments/{id}   → update body / resolved / anchor
 *   DELETE /api/comments/{id}   → delete a comment
 *
 * Every call is scoped to the active document via `withDoc` (?doc=<id>).
 */

import { withDoc } from '../../state/currentDocument';

const DEFAULT_BASE_URL = 'http://127.0.0.1:8777';

export interface CommentAnchor {
  block_index: number;
  from_offset: number;
  to_offset: number;
  /** Last block of a multi-block selection (defaults to block_index). When set,
   * from_offset is in block_index and to_offset is in end_block_index. */
  end_block_index?: number;
  /** Up to 32 chars before/after the quote — used to disambiguate repeated
   * quotes and to re-anchor through in-span edits. Optional (legacy comments). */
  prefix?: string;
  suffix?: string;
}

export interface CommentReply {
  id: string;
  body: string;
  author: string; // "you" = the writer; an assistant name for AI replies
  created_at: string;
}

export interface Comment {
  id: string;
  anchor: CommentAnchor;
  quote: string;
  body: string;
  resolved: boolean;
  replies: CommentReply[];
  created_at: string;
  updated_at: string;
}

export interface CommentDraft {
  anchor: CommentAnchor;
  quote: string;
  body: string;
}

async function asJson<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`Request failed (HTTP ${res.status})`);
  return (await res.json()) as T;
}

export async function getComments(
  baseUrl: string = DEFAULT_BASE_URL,
  signal?: AbortSignal,
): Promise<Comment[]> {
  const data = await asJson<{ comments?: Comment[] }>(
    await fetch(withDoc(`${baseUrl}/api/comments`), { signal }),
  );
  return Array.isArray(data.comments) ? data.comments : [];
}

export async function createComment(
  draft: CommentDraft,
  baseUrl: string = DEFAULT_BASE_URL,
  signal?: AbortSignal,
): Promise<Comment> {
  return asJson<Comment>(
    await fetch(withDoc(`${baseUrl}/api/comments`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(draft),
      signal,
    }),
  );
}

export async function updateComment(
  id: string,
  patch: { body?: string; resolved?: boolean; anchor?: CommentAnchor },
  baseUrl: string = DEFAULT_BASE_URL,
  signal?: AbortSignal,
): Promise<Comment> {
  return asJson<Comment>(
    await fetch(withDoc(`${baseUrl}/api/comments/${encodeURIComponent(id)}`), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
      signal,
    }),
  );
}

export async function deleteComment(
  id: string,
  baseUrl: string = DEFAULT_BASE_URL,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(withDoc(`${baseUrl}/api/comments/${encodeURIComponent(id)}`), {
    method: 'DELETE',
    signal,
  });
  if (!res.ok) throw new Error(`Delete failed (HTTP ${res.status})`);
}

export async function addReply(
  commentId: string,
  body: string,
  baseUrl: string = DEFAULT_BASE_URL,
  signal?: AbortSignal,
): Promise<Comment> {
  return asJson<Comment>(
    await fetch(withDoc(`${baseUrl}/api/comments/${encodeURIComponent(commentId)}/replies`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ body }),
      signal,
    }),
  );
}

export async function deleteReply(
  commentId: string,
  replyId: string,
  baseUrl: string = DEFAULT_BASE_URL,
  signal?: AbortSignal,
): Promise<Comment> {
  return asJson<Comment>(
    await fetch(
      withDoc(
        `${baseUrl}/api/comments/${encodeURIComponent(commentId)}/replies/${encodeURIComponent(replyId)}`,
      ),
      { method: 'DELETE', signal },
    ),
  );
}
