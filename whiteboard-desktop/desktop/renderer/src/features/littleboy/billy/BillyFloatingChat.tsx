/**
 * Billy — a compact, draggable, hovering AI chat box over the editor. It is
 * deliberately small (not a side panel, not a Pro workspace) and theme-aware.
 */

import { useCallback, useEffect, useRef, type MouseEvent as ReactMouseEvent } from 'react';

import { BillyChatInput } from './BillyChatInput';
import { BillyMessageList } from './BillyMessageList';
import type { BillyMessage } from './billyTypes';

interface Props {
  messages: BillyMessage[];
  sending: boolean;
  onSend: (text: string) => void;
  onClear: () => void;
  onClose: () => void;
  position: { x: number; y: number };
  onPositionChange: (pos: { x: number; y: number }) => void;
}

const BOX_WIDTH = 340;
const BOX_HEIGHT = 420;

export function BillyFloatingChat({
  messages,
  sending,
  onSend,
  onClear,
  onClose,
  position,
  onPositionChange,
}: Props) {
  const dragState = useRef<{ dx: number; dy: number } | null>(null);
  const onPosRef = useRef(onPositionChange);
  onPosRef.current = onPositionChange;

  const onHeaderMouseDown = useCallback(
    (e: ReactMouseEvent) => {
      // Don't start a drag from the header buttons.
      if ((e.target as HTMLElement).closest('button')) return;
      dragState.current = { dx: e.clientX - position.x, dy: e.clientY - position.y };
      e.preventDefault();
    },
    [position.x, position.y],
  );

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      const d = dragState.current;
      if (!d) return;
      const x = Math.min(Math.max(8, e.clientX - d.dx), window.innerWidth - BOX_WIDTH - 8);
      const y = Math.min(Math.max(8, e.clientY - d.dy), window.innerHeight - 80);
      onPosRef.current({ x, y });
    };
    const onUp = () => {
      dragState.current = null;
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, []);

  return (
    <div
      className="billy-box littleboy-box"
      style={{ left: position.x, top: position.y, width: BOX_WIDTH, height: BOX_HEIGHT }}
      role="dialog"
      aria-label="Billy chat"
    >
      <div className="billy-head" onMouseDown={onHeaderMouseDown}>
        <div className="billy-titles">
          <span className="billy-title">LITTLEBOY</span>
        </div>
        <div className="billy-head-actions">
          <button
            type="button"
            className="billy-head-btn"
            onClick={onClear}
            disabled={messages.length === 0}
            title="Clear chat"
          >
            Clear
          </button>
          <button type="button" className="billy-head-btn" onClick={onClose} title="Close (Esc)" aria-label="Close">
            ×
          </button>
        </div>
      </div>

      <BillyMessageList
        messages={messages}
        onSuggestion={(label) =>
          onSend(`Apply this suggestion and show me the concrete revised text I can drop into the draft: “${label}”.`)
        }
      />
      <BillyChatInput onSend={onSend} disabled={sending} />
    </div>
  );
}
