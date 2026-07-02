/**
 * LittleBoy — the Whiteboard Small AI system. Mounts the two lightweight agents
 * over the editor and owns their shortcuts + context capture:
 *
 *   Billy (hovering chat)     Cmd/Ctrl+Shift+B
 *   Logos (inline/contextual) Cmd/Ctrl+Shift+L   (legacy alias: Cmd/Ctrl+K)
 *
 * The shortcut/ESC handler runs in the capture phase so it reliably beats the
 * editor keymap and the app's global ESC (which restores hidden panels) — ESC
 * closes the active AI box FIRST. Billy's conversation is kept for the session
 * (the chat hook lives here, so closing/reopening preserves the thread).
 *
 * This is the Small system only: no Counterpart, no Quantum, no Pro workspace.
 */

import type { Editor } from '@tiptap/react';
import { useCallback, useEffect, useRef, useState } from 'react';

import {
  publishLittleBoyOpenState,
  registerLittleBoyToggles,
} from '../../state/littleBoyControl';
import { docToBlocks } from '../whiteboard/WhiteboardEditor';
import { BillyFloatingChat } from './billy/BillyFloatingChat';
import { useBillyChat } from './billy/useBillyChat';
import { collectEditorContext } from './context/collectEditorContext';
import { buildProjectContext, prependProjectContext } from './context/projectContext';
import { LogosInlineBox } from './logos/LogosInlineBox';
import type { EditorContext } from './littleboyTypes';

interface Props {
  editor: Editor;
  mode: string;
  baseUrl: string;
  documentTitle?: string;
  screenplayElement?: string | null;
}

function defaultBillyPos(): { x: number; y: number } {
  const x = typeof window !== 'undefined' ? Math.max(8, window.innerWidth - 360 - 24) : 24;
  return { x, y: 84 };
}

export function LittleBoyProvider({ editor, mode, baseUrl, documentTitle, screenplayElement }: Props) {
  const billy = useBillyChat({ baseUrl });

  const [billyOpen, setBillyOpen] = useState(false);
  const [billyPos, setBillyPos] = useState<{ x: number; y: number } | null>(null);
  const [logosContext, setLogosContext] = useState<EditorContext | null>(null);

  // Live refs so the capture-phase key handler subscribes once but sees current values.
  const ctxRef = useRef({ mode, documentTitle, screenplayElement });
  ctxRef.current = { mode, documentTitle, screenplayElement };
  const billyOpenRef = useRef(billyOpen);
  billyOpenRef.current = billyOpen;
  const logosOpenRef = useRef(logosContext !== null);
  logosOpenRef.current = logosContext !== null;

  const openBilly = useCallback(() => {
    setBillyPos((p) => p ?? defaultBillyPos());
    setBillyOpen(true);
  }, []);
  const closeBilly = useCallback(() => setBillyOpen(false), []);

  const openLogos = useCallback(() => {
    const c = ctxRef.current;
    const ctx = collectEditorContext(editor, {
      mode: c.mode,
      documentTitle: c.documentTitle,
      screenplayElement: c.screenplayElement,
    });
    // Prepend the document's outline + cast so Logos isn't project-blind.
    const project = buildProjectContext(docToBlocks(editor.getJSON()), c.mode);
    setLogosContext({ ...ctx, nearby: prependProjectContext(project, ctx.nearby) });
  }, [editor]);
  const closeLogos = useCallback(() => setLogosContext(null), []);

  // Shortcuts + ESC, in the capture phase (beats editor keymap + app ESC).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (e.key === 'Escape') {
        if (logosOpenRef.current) {
          e.preventDefault();
          e.stopPropagation();
          closeLogos();
        } else if (billyOpenRef.current) {
          e.preventDefault();
          e.stopPropagation();
          closeBilly();
        }
        return;
      }
      if (!mod || e.altKey) return;
      // Billy: Cmd/Ctrl+Shift+B
      if (e.shiftKey && e.code === 'KeyB') {
        e.preventDefault();
        e.stopPropagation();
        if (billyOpenRef.current) closeBilly();
        else openBilly();
        return;
      }
      // Logos: Cmd/Ctrl+Shift+L (official) or Cmd/Ctrl+K (legacy alias)
      if ((e.shiftKey && e.code === 'KeyL') || (!e.shiftKey && e.code === 'KeyK')) {
        e.preventDefault();
        e.stopPropagation();
        if (logosOpenRef.current) closeLogos();
        else openLogos();
      }
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [openBilly, closeBilly, openLogos, closeLogos]);

  // Let the title-bar buttons toggle the agents (they live up in the App shell).
  useEffect(
    () =>
      registerLittleBoyToggles({
        billy: () => (billyOpenRef.current ? closeBilly() : openBilly()),
        logos: () => (logosOpenRef.current ? closeLogos() : openLogos()),
      }),
    [openBilly, closeBilly, openLogos, closeLogos],
  );

  // Publish open state so the title-bar buttons can show active/inactive.
  useEffect(() => {
    publishLittleBoyOpenState({ billyOpen, logosOpen: logosContext !== null });
  }, [billyOpen, logosContext]);

  const onBillySend = useCallback(
    (text: string) => {
      const c = ctxRef.current;
      const ctx = collectEditorContext(editor, {
        mode: c.mode,
        documentTitle: c.documentTitle,
        screenplayElement: c.screenplayElement,
      });
      // Ground Billy in the whole document (outline + cast), not just nearby text.
      const project = buildProjectContext(docToBlocks(editor.getJSON()), c.mode);
      billy.send(text, {
        selected_text: ctx.selection || undefined,
        nearby_context: prependProjectContext(project, ctx.nearby) || undefined,
        writing_mode: ctx.mode,
        document_title: ctx.documentTitle,
      });
    },
    [editor, billy],
  );

  return (
    <>
      {billyOpen && billyPos && (
        <BillyFloatingChat
          messages={billy.messages}
          sending={billy.sending}
          onSend={onBillySend}
          onClear={billy.clear}
          onClose={closeBilly}
          position={billyPos}
          onPositionChange={setBillyPos}
        />
      )}
      {logosContext && (
        <LogosInlineBox editor={editor} context={logosContext} baseUrl={baseUrl} onClose={closeLogos} />
      )}
    </>
  );
}
