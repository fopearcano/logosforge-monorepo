/** Floating editor for a single comment — anchored to its highlight in the text. */

import { useEffect, useRef, useState } from 'react';

import type { Comment } from './commentsApi';

interface Props {
  comment: Comment;
  top: number;
  left: number;
  onSave: (body: string) => void;
  onReply: (body: string) => void;
  onDeleteReply: (replyId: string) => void;
  onToggleResolved: () => void;
  onDelete: () => void;
  onClose: () => void;
}

/** Compact relative time (e.g. "5m ago"), falling back to a date for old notes. */
function timeAgo(iso?: string): string {
  if (!iso) return '';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const s = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (s < 60) return 'just now';
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}d ago`;
  return new Date(iso).toLocaleDateString();
}

export function CommentPopover({
  comment,
  top,
  left,
  onSave,
  onReply,
  onDeleteReply,
  onToggleResolved,
  onDelete,
  onClose,
}: Props) {
  const [body, setBody] = useState(comment.body);
  const [reply, setReply] = useState('');
  const taRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    setBody(comment.body);
    setReply('');
  }, [comment.id, comment.body]);

  useEffect(() => {
    const t = setTimeout(() => taRef.current?.focus(), 0);
    return () => clearTimeout(t);
  }, [comment.id]);

  const dirty = body !== comment.body;

  return (
    <div
      className="comment-popover"
      style={{ top, left }}
      role="dialog"
      aria-label="Comment"
      onMouseDown={(e) => e.stopPropagation()}
    >
      <div className="comment-pop-quote" title={comment.quote}>
        “{comment.quote}”
      </div>
      <textarea
        ref={taRef}
        className="comment-pop-body"
        value={body}
        placeholder="Write a comment…"
        aria-label="Comment text"
        onChange={(e) => setBody(e.target.value)}
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
            e.preventDefault();
            onSave(body);
          } else if (e.key === 'Escape') {
            e.preventDefault();
            onClose();
          }
        }}
      />
      <div className="comment-pop-meta">
        {timeAgo(comment.created_at) || '—'}
        {comment.updated_at && comment.updated_at !== comment.created_at
          ? ` · edited ${timeAgo(comment.updated_at)}`
          : ''}
      </div>

      {comment.replies.length > 0 && (
        <div className="comment-pop-thread">
          {comment.replies.map((r) => (
            <div key={r.id} className="comment-pop-reply">
              <div className="comment-pop-reply-head">
                <span className="comment-pop-reply-author">{r.author}</span>
                <span className="comment-pop-reply-time">{timeAgo(r.created_at)}</span>
                <button
                  type="button"
                  className="comment-pop-reply-del"
                  title="Delete reply"
                  aria-label="Delete reply"
                  onClick={() => onDeleteReply(r.id)}
                >
                  ×
                </button>
              </div>
              <div className="comment-pop-reply-body">{r.body}</div>
            </div>
          ))}
        </div>
      )}

      <div className="comment-pop-replybox">
        <textarea
          className="comment-pop-replyinput"
          value={reply}
          placeholder="Reply… (@Billy or @Logos to ask AI)"
          aria-label="Reply to this comment"
          rows={2}
          onChange={(e) => setReply(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && reply.trim()) {
              e.preventDefault();
              onReply(reply.trim());
              setReply('');
            }
          }}
        />
        <button
          type="button"
          className="comment-pop-btn"
          disabled={!reply.trim()}
          onClick={() => {
            onReply(reply.trim());
            setReply('');
          }}
        >
          Reply
        </button>
      </div>

      <div className="comment-pop-actions">
        <button type="button" className="comment-pop-btn" onClick={onToggleResolved}>
          {comment.resolved ? 'Reopen' : 'Resolve'}
        </button>
        <button
          type="button"
          className="comment-pop-btn comment-pop-danger"
          onClick={onDelete}
        >
          Delete
        </button>
        <span className="comment-pop-spacer" />
        <button type="button" className="comment-pop-btn" onClick={onClose}>
          Close
        </button>
        <button
          type="button"
          className="comment-pop-btn comment-pop-primary"
          disabled={!dirty}
          onClick={() => onSave(body)}
        >
          Save
        </button>
      </div>
    </div>
  );
}
