/** The hideable Comments side panel — a list of every comment in the document. */

import type { Comment } from './commentsApi';

interface Props {
  comments: Comment[];
  hideResolved: boolean;
  onToggleHideResolved: () => void;
  onSelect: (id: string) => void;
  onToggleResolved: (id: string) => void;
  onDelete: (id: string) => void;
  onClose: () => void;
}

export function CommentsWindow({
  comments,
  hideResolved,
  onToggleHideResolved,
  onSelect,
  onToggleResolved,
  onDelete,
  onClose,
}: Props) {
  const open = comments.filter((c) => !c.resolved);
  const resolved = comments.filter((c) => c.resolved);
  const ordered = hideResolved ? open : [...open, ...resolved];

  return (
    <aside className="comments-window" aria-label="Comments">
      <header className="comments-head">
        <span className="comments-title">Comments</span>
        <span className="comments-count">{open.length}</span>
        {resolved.length > 0 && (
          <button
            type="button"
            className="comments-filter"
            onClick={onToggleHideResolved}
            aria-pressed={hideResolved}
            title={hideResolved ? 'Show resolved comments' : 'Hide resolved comments'}
          >
            {hideResolved ? `Show resolved (${resolved.length})` : `Hide resolved (${resolved.length})`}
          </button>
        )}
        <button
          type="button"
          className="comments-close"
          onClick={onClose}
          aria-label="Close comments"
          title="Close (Ctrl/Cmd+Shift+C)"
        >
          ×
        </button>
      </header>
      <div className="comments-body">
        {comments.length === 0 ? (
          <p className="comments-empty">
            No comments yet. Select text in your document and click <strong>Comment</strong> to
            add one.
          </p>
        ) : ordered.length === 0 ? (
          <p className="comments-empty">
            {resolved.length} resolved comment{resolved.length === 1 ? '' : 's'} hidden.
          </p>
        ) : (
          ordered.map((c) => (
            <div key={c.id} className={`comment-item${c.resolved ? ' is-resolved' : ''}`}>
              <button
                type="button"
                className="comment-item-main"
                onClick={() => onSelect(c.id)}
                title="Jump to this comment"
                aria-label={`Jump to comment on “${c.quote}”`}
              >
                <span className="comment-item-quote">“{c.quote}”</span>
                <span className="comment-item-body">
                  {c.body ? c.body : <em className="comment-item-empty">empty note</em>}
                </span>
                {c.replies.length > 0 && (
                  <span className="comment-item-replies">
                    💬 {c.replies.length} {c.replies.length === 1 ? 'reply' : 'replies'}
                  </span>
                )}
              </button>
              <div className="comment-item-actions">
                <button
                  type="button"
                  className="comment-act"
                  title={c.resolved ? 'Reopen' : 'Resolve'}
                  aria-label={c.resolved ? 'Reopen comment' : 'Resolve comment'}
                  onClick={() => onToggleResolved(c.id)}
                >
                  {c.resolved ? '↺' : '✓'}
                </button>
                <button
                  type="button"
                  className="comment-act comment-act-danger"
                  title="Delete"
                  aria-label="Delete comment"
                  onClick={() => onDelete(c.id)}
                >
                  ×
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </aside>
  );
}
