/**
 * Logos — the inline/contextual AI box. Opens near the caret/selection, runs a
 * quick contextual action against the LittleBoy backend, and (only on explicit
 * confirmation) applies a scoped replacement to the captured selection.
 *
 * It is embedded in the writing surface — not a chat panel.
 */

import type { Editor } from '@tiptap/react';
import { useEffect, useMemo, useRef, useState } from 'react';

import { contextLabel } from '../context/writingModeContext';
import { contextPreview } from '../context/selectionContext';
import type { EditorContext, LogosActionId } from '../littleboyTypes';
import { LogosActionMenu } from './LogosActionMenu';
import { applyModeFor } from './logosTypes';
import { useLogosInline } from './useLogosInline';

interface Props {
  editor: Editor;
  context: EditorContext;
  baseUrl: string;
  onClose: () => void;
}

const BOX_WIDTH = 340;
const BOX_MAX_HEIGHT = 360;

/** Our schema has no hardBreak; represent multi-line output as paragraphs. */
function toParagraphs(text: string) {
  return text.split('\n').map((line) => ({
    type: 'paragraph',
    content: line ? [{ type: 'text', text: line }] : [],
  }));
}

function clampPosition(coords: EditorContext['coords']) {
  let left = coords.left;
  if (left + BOX_WIDTH > window.innerWidth - 12) left = window.innerWidth - BOX_WIDTH - 12;
  if (left < 12) left = 12;
  let top = coords.bottom + 6;
  if (top + BOX_MAX_HEIGHT > window.innerHeight - 12) {
    top = Math.max(12, coords.top - BOX_MAX_HEIGHT - 6);
  }
  return { left, top };
}

export function LogosInlineBox({ editor, context, baseUrl, onClose }: Props) {
  const { status, response, error, run } = useLogosInline({ baseUrl });
  const [instruction, setInstruction] = useState('');
  const instructionRef = useRef<HTMLInputElement>(null);

  const pos = useMemo(() => clampPosition(context.coords), [context.coords]);
  const hasSelection = context.selection.trim().length > 0;
  const preview = contextPreview(context.selection, context.block);

  useEffect(() => {
    instructionRef.current?.focus();
  }, []);

  const doAction = (action: LogosActionId) => {
    void run({
      action,
      selected_text: context.selection || undefined,
      nearby_context: context.nearby || undefined,
      writing_mode: context.mode,
      instruction: instruction.trim() || undefined,
      document_title: context.documentTitle,
    });
  };

  const result = response?.result ?? '';
  const applyMode = response ? applyModeFor(response, hasSelection) : 'insert';

  const applyReplace = () => {
    const replacement = response?.suggested_replacement;
    if (!replacement) return;
    const { from, to } = context;
    try {
      if (!replacement.includes('\n')) {
        editor.chain().focus().insertContentAt({ from, to }, replacement).run();
      } else {
        editor.chain().focus().insertContentAt({ from, to }, toParagraphs(replacement)).run();
      }
    } catch {
      /* ignore apply failures */
    }
    onClose();
  };

  const insertBelow = () => {
    if (!result) return;
    try {
      const after = editor.state.doc.resolve(context.to).after();
      editor.chain().focus().insertContentAt(after, toParagraphs(result)).run();
    } catch {
      editor.chain().focus().insertContentAt(context.to, toParagraphs(result)).run();
    }
    onClose();
  };

  const copyResult = () => {
    if (result) navigator.clipboard?.writeText(result)?.catch(() => undefined);
  };

  return (
    <div
      className="logos-box littleboy-box"
      style={{ left: pos.left, top: pos.top }}
      role="dialog"
      aria-label="Logos inline assistant"
    >
      <div className="logos-head">
        <span className="logos-title">Logos · {contextLabel(context.mode, context.screenplayElement)}</span>
        <button type="button" className="logos-close" onClick={onClose} title="Close (Esc)" aria-label="Close">
          ×
        </button>
      </div>

      <div className="logos-context" title={context.selection || context.block}>
        {hasSelection ? '“' + preview + '”' : preview || 'Current block'}
      </div>

      <form
        className="logos-prompt-row"
        onSubmit={(e) => {
          e.preventDefault();
          doAction('rewrite');
        }}
      >
        <input
          ref={instructionRef}
          className="logos-prompt"
          type="text"
          placeholder="Optional instruction (then pick an action)…"
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
        />
      </form>

      <LogosActionMenu onAction={doAction} disabled={status === 'loading'} />

      {status === 'loading' && <div className="logos-status">Thinking…</div>}
      {status === 'error' && <div className="logos-status logos-error">Logos error: {error}</div>}

      {status === 'done' && response && (
        <div className="logos-result">
          <div className="logos-output">{result}</div>
          {response.note && <div className="logos-note">{response.note}</div>}
          <div className="logos-apply">
            {applyMode === 'apply' ? (
              <button type="button" onClick={applyReplace} title="Replace the selected text">
                Apply (replace selection)
              </button>
            ) : (
              <button type="button" onClick={insertBelow} disabled={!result}>
                Insert below
              </button>
            )}
            <button type="button" onClick={copyResult} disabled={!result}>
              Copy
            </button>
            <button type="button" onClick={onClose}>
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
