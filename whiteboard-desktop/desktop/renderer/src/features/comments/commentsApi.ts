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

import {
  captureDocumentIdentity,
  captureDocumentIncarnation,
  type CapturedDocumentIdentity,
  withDoc,
} from '../../state/currentDocument';
import {
  backendFetch,
  withDocumentIncarnation,
  withExpectedDocumentIncarnation,
} from '../../api/backendAuth';
import { responseError } from '../../api/responseError';
import {
  type RuntimeDtoValidator,
  validateComment,
  validateCommentDeleteResponse,
  validateCommentMutationResponse,
  validateCommentsResponse,
} from '../../api/runtimeDtoValidation';

const DEFAULT_BASE_URL = 'http://127.0.0.1:8777';

export interface CommentAnchor {
  /** Legacy anchors omit this and therefore belong to the canonical manuscript. */
  surface?: 'manuscript' | 'drafter';
  /** Required when surface is `drafter`; identifies the project-owned scratch page. */
  drafter_page_id?: string | null;
  block_index: number;
  /** Stable Whiteboard block identity (new anchors); index remains fallback. */
  block_id?: string | null;
  from_offset: number;
  to_offset: number;
  /** Last block of a multi-block selection (defaults to block_index). When set,
   * from_offset is in block_index and to_offset is in end_block_index. */
  end_block_index?: number | null;
  end_block_id?: string | null;
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

async function validatedResponse<T>(
  res: Response,
  validate: RuntimeDtoValidator<T>,
): Promise<T> {
  if (!res.ok) throw await responseError(res, 'Comment request failed');
  return validate(await res.json());
}

export async function getComments(
  baseUrl: string = DEFAULT_BASE_URL,
  signal?: AbortSignal,
): Promise<Comment[]> {
  const identity = captureDocumentIdentity();
  const data = await validatedResponse(
    await backendFetch(withDoc(`${baseUrl}/api/comments`), {
      headers: withExpectedDocumentIncarnation(identity.incarnation),
      signal,
    }),
    validateCommentsResponse,
  );
  return data.comments;
}

/** Load a captured document without consulting the active-id singleton. */
export async function getCommentsForDocument(
  baseUrl: string,
  documentId: string,
  signal?: AbortSignal,
  incarnation: string = captureDocumentIncarnation(documentId),
): Promise<Comment[]> {
  const data = await validatedResponse(
    await backendFetch(
      `${baseUrl}/api/comments?doc=${encodeURIComponent(documentId)}`,
      { headers: withExpectedDocumentIncarnation(incarnation), signal },
    ),
    validateCommentsResponse,
  );
  return data.comments;
}

export async function createComment(
  draft: CommentDraft,
  baseUrl: string = DEFAULT_BASE_URL,
  signal?: AbortSignal,
  identity: CapturedDocumentIdentity = captureDocumentIdentity(),
): Promise<Comment> {
  return validatedResponse(
    await backendFetch(
      `${baseUrl}/api/comments?doc=${encodeURIComponent(identity.documentId)}`,
      {
      method: 'POST',
      headers: withDocumentIncarnation(identity.incarnation, { 'Content-Type': 'application/json' }),
      body: JSON.stringify(draft),
      signal,
      },
    ),
    validateComment,
  );
}

export async function updateComment(
  id: string,
  patch: { body?: string; resolved?: boolean; anchor?: CommentAnchor },
  baseUrl: string = DEFAULT_BASE_URL,
  signal?: AbortSignal,
  identity: CapturedDocumentIdentity = captureDocumentIdentity(),
): Promise<Comment> {
  const result = await validatedResponse(
    await backendFetch(
      `${baseUrl}/api/comments/${encodeURIComponent(id)}?doc=${encodeURIComponent(identity.documentId)}`,
      {
      method: 'PUT',
      headers: withDocumentIncarnation(identity.incarnation, { 'Content-Type': 'application/json' }),
      body: JSON.stringify(patch),
      signal,
      },
    ),
    validateComment,
  );
  return validateCommentMutationResponse(result, id);
}

export async function deleteComment(
  id: string,
  baseUrl: string = DEFAULT_BASE_URL,
  signal?: AbortSignal,
  identity: CapturedDocumentIdentity = captureDocumentIdentity(),
): Promise<void> {
  const res = await backendFetch(
    `${baseUrl}/api/comments/${encodeURIComponent(id)}?doc=${encodeURIComponent(identity.documentId)}`,
    {
      method: 'DELETE',
      headers: withDocumentIncarnation(identity.incarnation),
      signal,
    },
  );
  if (!res.ok) throw await responseError(res, 'Could not delete the comment');
  const acknowledgement = validateCommentDeleteResponse(await res.json());
  if (acknowledgement.deleted !== id) {
    throw new Error('The backend acknowledged deletion of a different comment.');
  }
}

export async function addReply(
  commentId: string,
  body: string,
  baseUrl: string = DEFAULT_BASE_URL,
  signal?: AbortSignal,
  clientId?: string,
  identity: CapturedDocumentIdentity = captureDocumentIdentity(),
): Promise<Comment> {
  const result = await validatedResponse(
    await backendFetch(
      `${baseUrl}/api/comments/${encodeURIComponent(commentId)}/replies?doc=${encodeURIComponent(identity.documentId)}`,
      {
      method: 'POST',
      headers: withDocumentIncarnation(identity.incarnation, { 'Content-Type': 'application/json' }),
      body: JSON.stringify({ body, ...(clientId ? { client_id: clientId } : {}) }),
      signal,
      },
    ),
    validateComment,
  );
  return validateCommentMutationResponse(result, commentId);
}

export async function deleteReply(
  commentId: string,
  replyId: string,
  baseUrl: string = DEFAULT_BASE_URL,
  signal?: AbortSignal,
  identity: CapturedDocumentIdentity = captureDocumentIdentity(),
): Promise<Comment> {
  const result = await validatedResponse(
    await backendFetch(
      `${baseUrl}/api/comments/${encodeURIComponent(commentId)}/replies/${encodeURIComponent(replyId)}`
        + `?doc=${encodeURIComponent(identity.documentId)}`,
      {
        method: 'DELETE',
        headers: withDocumentIncarnation(identity.incarnation),
        signal,
      },
    ),
    validateComment,
  );
  return validateCommentMutationResponse(result, commentId);
}
