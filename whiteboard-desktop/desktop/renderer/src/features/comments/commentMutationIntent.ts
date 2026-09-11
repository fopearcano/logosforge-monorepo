import {
  captureDocumentIdentity,
  registerDocDiscarder,
  registerDocFlusher,
  waitForPendingDocWrites,
  type CapturedDocumentIdentity,
} from '../../state/currentDocument';
import type { Comment, CommentAnchor, CommentReply } from './commentsApi';

export type CommentPatch = {
  body?: string;
  resolved?: boolean;
  anchor?: CommentAnchor;
};

interface CommentIntent {
  patch: CommentPatch;
  optimisticReplies: Map<string, CommentReply>;
}

const intents = new Map<string, CommentIntent>();
type RetainedIntentWriter = (
  identity: CapturedDocumentIdentity,
  commentId: string,
) => Promise<Comment | null>;
type RetainedIntentListener = (
  identity: CapturedDocumentIdentity,
  commentId: string,
  updated: Comment,
) => void;
let retainedIntentWriter: RetainedIntentWriter | null = null;
const retainedIntentListeners = new Set<RetainedIntentListener>();

function intentKey(identity: CapturedDocumentIdentity, commentId: string): string {
  return `${identity.documentId}\u0000${identity.incarnation}\u0000${commentId}`;
}

function intentFor(
  identity: CapturedDocumentIdentity,
  commentId: string,
  create = false,
): CommentIntent | null {
  const key = intentKey(identity, commentId);
  const existing = intents.get(key);
  if (existing || !create) return existing ?? null;
  const intent: CommentIntent = { patch: {}, optimisticReplies: new Map() };
  intents.set(key, intent);
  return intent;
}

function equalAnchor(a: CommentAnchor | undefined, b: CommentAnchor | undefined): boolean {
  if (a === b) return true;
  if (!a || !b) return false;
  return (
    a.block_index === b.block_index
    && a.block_id === b.block_id
    && a.from_offset === b.from_offset
    && a.to_offset === b.to_offset
    && a.end_block_index === b.end_block_index
    && a.end_block_id === b.end_block_id
    && a.prefix === b.prefix
    && a.suffix === b.suffix
  );
}

function prune(identity: CapturedDocumentIdentity, commentId: string, intent: CommentIntent): void {
  if (Object.keys(intent.patch).length === 0 && intent.optimisticReplies.size === 0) {
    intents.delete(intentKey(identity, commentId));
  }
}

/** Retain the writer's newest value for every independently editable field. */
export function retainCommentPatch(
  identity: CapturedDocumentIdentity,
  commentId: string,
  patch: CommentPatch,
): void {
  const intent = intentFor(identity, commentId, true)!;
  intent.patch = { ...intent.patch, ...patch };
}

/** Snapshot all scalar intent still awaiting acknowledgement. */
export function pendingCommentPatch(
  identity: CapturedDocumentIdentity,
  commentId: string,
): CommentPatch {
  const patch = intentFor(identity, commentId)?.patch ?? {};
  return {
    ...patch,
    ...(patch.anchor ? { anchor: { ...patch.anchor } } : {}),
  };
}

/**
 * Acknowledge only values that still equal the sent snapshot. A newer edit made
 * while the request was in flight remains overlaid and will be sent next.
 */
export function acknowledgeCommentPatch(
  identity: CapturedDocumentIdentity,
  commentId: string,
  sent: CommentPatch,
): void {
  const intent = intentFor(identity, commentId);
  if (!intent) return;
  if (Object.prototype.hasOwnProperty.call(sent, 'body') && intent.patch.body === sent.body) {
    delete intent.patch.body;
  }
  if (
    Object.prototype.hasOwnProperty.call(sent, 'resolved')
    && intent.patch.resolved === sent.resolved
  ) {
    delete intent.patch.resolved;
  }
  if (
    Object.prototype.hasOwnProperty.call(sent, 'anchor')
    && equalAnchor(intent.patch.anchor, sent.anchor)
  ) {
    delete intent.patch.anchor;
  }
  prune(identity, commentId, intent);
}

export function retainOptimisticCommentReplies(
  identity: CapturedDocumentIdentity,
  commentId: string,
  replies: CommentReply[],
): void {
  const intent = intentFor(identity, commentId, true)!;
  for (const reply of replies) intent.optimisticReplies.set(reply.id, reply);
}

export function acknowledgeOptimisticCommentReplies(
  identity: CapturedDocumentIdentity,
  commentId: string,
  replyIds: string[],
): void {
  const intent = intentFor(identity, commentId);
  if (!intent) return;
  for (const replyId of replyIds) intent.optimisticReplies.delete(replyId);
  prune(identity, commentId, intent);
}

export function pendingOptimisticCommentReplies(
  identity: CapturedDocumentIdentity,
  commentId: string,
): CommentReply[] {
  return [...(intentFor(identity, commentId)?.optimisticReplies.values() ?? [])];
}

export function retainedCommentIds(identity: CapturedDocumentIdentity): string[] {
  const prefix = `${identity.documentId}\u0000${identity.incarnation}\u0000`;
  return [...intents.keys()]
    .filter((key) => key.startsWith(prefix))
    .map((key) => key.slice(prefix.length));
}

/** Keep the latest explicit-address transport alive across React remounts. */
export function configureRetainedCommentIntentWriter(writer: RetainedIntentWriter): void {
  retainedIntentWriter = writer;
}

/** Let the mounted comments view reconcile a successful app-lifetime retry. */
export function subscribeRetainedCommentIntent(
  listener: RetainedIntentListener,
): () => void {
  retainedIntentListeners.add(listener);
  return () => retainedIntentListeners.delete(listener);
}

export function discardRetainedCommentIntents(identity: CapturedDocumentIdentity): void {
  for (const commentId of retainedCommentIds(identity)) {
    discardRetainedCommentIntent(identity, commentId);
  }
}

export interface CommentIntentTransport {
  update: (patch: CommentPatch) => Promise<Comment>;
  addReply: (reply: CommentReply) => Promise<Comment>;
}

/**
 * Persist everything currently retained for one comment. Snapshots are
 * acknowledged value-by-value, so intent added while a request is in flight is
 * left queued for the caller's next pass.
 */
export async function flushRetainedCommentIntent(
  identity: CapturedDocumentIdentity,
  commentId: string,
  transport: CommentIntentTransport,
): Promise<Comment | null> {
  let updated: Comment | null = null;
  const patch = pendingCommentPatch(identity, commentId);
  if (Object.keys(patch).length > 0) {
    updated = await transport.update(patch);
    acknowledgeCommentPatch(identity, commentId, patch);
  }

  const replies = pendingOptimisticCommentReplies(identity, commentId);
  for (const reply of replies) {
    updated = await transport.addReply(reply);
    acknowledgeOptimisticCommentReplies(identity, commentId, [reply.id]);
  }
  return updated;
}

/**
 * App-lifetime close/handoff flush. It deliberately addresses only the
 * captured current incarnation; failed intent for an old deleted document can
 * neither leak into nor block a later document that reuses its numeric id.
 */
export async function flushCurrentDocumentCommentIntents(): Promise<void> {
  const identity = captureDocumentIdentity();
  if (!identity.documentId) return;
  await waitForPendingDocWrites();
  const current = captureDocumentIdentity();
  if (
    current.documentId !== identity.documentId
    || current.incarnation !== identity.incarnation
  ) return;

  while (true) {
    const ids = retainedCommentIds(identity);
    if (ids.length === 0) return;
    const writer = retainedIntentWriter;
    if (!writer) throw new Error('No comment save transport is available.');
    for (const commentId of ids) {
      const updated = await writer(identity, commentId);
      if (updated) {
        for (const listener of retainedIntentListeners) {
          listener(identity, commentId, updated);
        }
      }
    }
    const latest = captureDocumentIdentity();
    if (
      latest.documentId !== identity.documentId
      || latest.incarnation !== identity.incarnation
    ) return;
  }
}

/** Reapply unsatisfied optimistic intent to a full comment returned by the API. */
export function applyRetainedCommentIntent(
  identity: CapturedDocumentIdentity,
  comment: Comment,
): Comment {
  const intent = intentFor(identity, comment.id);
  if (!intent) return comment;
  const serverReplyIds = new Set(comment.replies.map((reply) => reply.id));
  const optimisticReplies = [...intent.optimisticReplies.values()].filter(
    (reply) => !serverReplyIds.has(reply.id),
  );
  return {
    ...comment,
    ...intent.patch,
    replies: optimisticReplies.length
      ? [...comment.replies, ...optimisticReplies]
      : comment.replies,
  };
}

export function applyRetainedCommentIntents(
  identity: CapturedDocumentIdentity,
  comments: Comment[],
): Comment[] {
  return comments.map((comment) => applyRetainedCommentIntent(identity, comment));
}

export function hasRetainedCommentIntent(
  identity: CapturedDocumentIdentity,
  commentId: string,
): boolean {
  return intentFor(identity, commentId) !== null;
}

/** A confirmed comment deletion makes every older field/reply intent irrelevant. */
export function discardRetainedCommentIntent(
  identity: CapturedDocumentIdentity,
  commentId: string,
): void {
  intents.delete(intentKey(identity, commentId));
}

// This ownership must outlive the React tree: a render-boundary fallback still
// has to block close/handoff when an optimistic comment could not be persisted.
registerDocFlusher(flushCurrentDocumentCommentIntents);
registerDocDiscarder(() => discardRetainedCommentIntents(captureDocumentIdentity()));
