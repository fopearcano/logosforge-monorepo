/** The hideable Comments side panel — comments on the active writing surface. */

import type { CSSProperties } from 'react';

import {
  PanelTransparencyControl,
  usePanelTransparency,
} from '../../components/PanelTransparencyControl';
import { useFloatingPanel } from '../../components/useFloatingPanel';
import type { Comment } from './commentsApi';

interface Props {
  comments: Comment[];
  surfaceLabel: string;
  hideResolved: boolean;
  onToggleHideResolved: () => void;
  onSelect: (id: string) => void;
  onToggleResolved: (id: string) => void;
  onDelete: (id: string) => void;
  onClose: () => void;
}

const TRANSPARENCY_STORAGE_KEY = 'logosforge-comments-transparency';

export function CommentsWindow({
  comments,
  surfaceLabel,
  hideResolved,
  onToggleHideResolved,
  onSelect,
  onToggleResolved,
  onDelete,
  onClose,
}: Props) {
  const floating = useFloatingPanel({
    storageKey: 'logosforge-comments-panel-position',
    width: 336,
    defaultSide: 'right',
    defaultTop: 70,
  });
  const panelTransparency = usePanelTransparency(TRANSPARENCY_STORAGE_KEY);
  const open = comments.filter((c) => !c.resolved);
  const resolved = comments.filter((c) => c.resolved);
  const ordered = hideResolved ? open : [...open, ...resolved];

  return (
    <aside
      className={`comments-window floating-panel has-panel-transparency${floating.dragging ? ' is-dragging' : ''}`}
      style={{
        left: floating.position.x,
        top: floating.position.y,
        '--panel-opacity': String(panelTransparency.opacity),
      } as CSSProperties}
      aria-label={`Comments for ${surfaceLabel}`}
    >
      <header className="comments-head">
        <button
          type="button"
          className="floating-panel-drag"
          onPointerDown={floating.onPointerDown}
          onKeyDown={floating.onKeyDown}
          aria-label="Move Comments panel. Use arrow keys for precise movement."
          title="Drag to move · Arrow keys move precisely"
        >
          ⠿
        </button>
        <PanelTransparencyControl
          label="Comments panel"
          value={panelTransparency.transparency}
          onChange={panelTransparency.setTransparency}
        />
        <span className="comments-title">Comments · {surfaceLabel}</span>
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
            No comments yet. Select text on this writing page and click <strong>Comment</strong> to
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
