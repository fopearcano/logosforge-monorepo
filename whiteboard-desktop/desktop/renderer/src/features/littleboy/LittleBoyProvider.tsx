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

import { isModalDialogOpen } from '../../components/useModalDialog';
import {
  publishLittleBoyOpenState,
  registerLittleBoyToggles,
} from '../../state/littleBoyControl';
import { docToBlocks } from '../whiteboard/WhiteboardEditor';
import type { WhiteboardBlock } from '../whiteboard/types';
import { BillyFloatingChat } from './billy/BillyFloatingChat';
import { useBillyChat } from './billy/useBillyChat';
import { collectEditorContext } from './context/collectEditorContext';
import {
  buildProjectContext,
  buildWritingSurfaceContext,
  prependProjectContext,
} from './context/projectContext';
import { LogosInlineBox } from './logos/LogosInlineBox';
import type { EditorContext } from './littleboyTypes';

interface Props {
  editor: Editor;
  mode: string;
  baseUrl: string;
  documentTitle?: string;
  screenplayElement?: string | null;
  narrativeProfile?: string;
  /** Canonical manuscript blocks, even when `editor` is a Drafter page. */
  projectBlocks?: WhiteboardBlock[];
  activeSurfaceKind?: 'manuscript' | 'draft';
  activeSurfaceTitle?: string;
  drafterPageTitles?: string[];
  /** Stable id for the editor surface that owns any open inline Logos session. */
  writingSurfaceId?: string;
}

interface LogosSession {
  context: EditorContext;
  editor: Editor;
  writingSurfaceId: string;
}

function defaultBillyPos(): { x: number; y: number } {
  const x = typeof window !== 'undefined' ? Math.max(8, window.innerWidth - 360 - 24) : 24;
  return { x, y: 84 };
}

export function LittleBoyProvider({
  editor,
  mode,
  baseUrl,
  documentTitle,
  screenplayElement,
  narrativeProfile = '',
  projectBlocks,
  activeSurfaceKind = 'manuscript',
  activeSurfaceTitle,
  drafterPageTitles = [],
  writingSurfaceId = activeSurfaceKind,
}: Props) {
  const billy = useBillyChat({ baseUrl });

  const [billyOpen, setBillyOpen] = useState(false);
  const [billyPos, setBillyPos] = useState<{ x: number; y: number } | null>(null);
  const [logosSession, setLogosSession] = useState<LogosSession | null>(null);
  // A surface switch can replace the TipTap editor without remounting this
  // provider (Billy deliberately keeps its conversation). Never render or
  // apply a Logos result unless both the editor and surface still match the
  // selection that was captured when the inline session opened.
  const logosOpen = Boolean(
    logosSession
    && logosSession.editor === editor
    && logosSession.writingSurfaceId === writingSurfaceId,
  );

  // Live refs so the capture-phase key handler subscribes once but sees current values.
  const ctxRef = useRef({
    mode,
    documentTitle,
    screenplayElement,
    narrativeProfile,
    projectBlocks,
    activeSurfaceKind,
    activeSurfaceTitle,
    drafterPageTitles,
  });
  ctxRef.current = {
    mode,
    documentTitle,
    screenplayElement,
    narrativeProfile,
    projectBlocks,
    activeSurfaceKind,
    activeSurfaceTitle,
    drafterPageTitles,
  };
  const billyOpenRef = useRef(billyOpen);
  billyOpenRef.current = billyOpen;
  const logosOpenRef = useRef(logosOpen);
  logosOpenRef.current = logosOpen;

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
    // Prepend drafted manuscript structure + cast. The backend adds the
    // separate writer-authored manual Outline and core PSYKE context.
    const canonicalBlocks = c.projectBlocks ?? docToBlocks(editor.getJSON());
    const manuscript = prependProjectContext(
      c.narrativeProfile,
      buildProjectContext(canonicalBlocks, c.mode),
    );
    const surface = buildWritingSurfaceContext(
      c.activeSurfaceKind,
      c.activeSurfaceTitle,
      c.drafterPageTitles,
    );
    const project = prependProjectContext(manuscript, surface);
    setLogosSession({
      context: { ...ctx, nearby: prependProjectContext(project, ctx.nearby) },
      editor,
      writingSurfaceId,
    });
  }, [editor, writingSurfaceId]);
  const closeLogos = useCallback(() => setLogosSession(null), []);

  useEffect(() => {
    setLogosSession((current) => (
      current
      && (current.editor !== editor || current.writingSurfaceId !== writingSurfaceId)
        ? null
        : current
    ));
  }, [editor, writingSurfaceId]);

  // Shortcuts + ESC, in the capture phase (beats editor keymap + app ESC).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // Window-capture runs before the modal's document-capture listener. Yield
      // while a true modal is open so one Escape cannot close both surfaces and
      // AI shortcuts cannot mutate the background through its inert app tree.
      if (isModalDialogOpen()) return;
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
    publishLittleBoyOpenState({ billyOpen, logosOpen });
  }, [billyOpen, logosOpen]);

  const onBillySend = useCallback(
    (text: string) => {
      const c = ctxRef.current;
      const ctx = collectEditorContext(editor, {
        mode: c.mode,
        documentTitle: c.documentTitle,
        screenplayElement: c.screenplayElement,
      });
      // Ground Billy in drafted manuscript structure + cast, not just nearby
      // text. The backend adds manual Outline + core PSYKE grounding.
      const canonicalBlocks = c.projectBlocks ?? docToBlocks(editor.getJSON());
      const manuscript = prependProjectContext(
        c.narrativeProfile,
        buildProjectContext(canonicalBlocks, c.mode),
      );
      const surface = buildWritingSurfaceContext(
        c.activeSurfaceKind,
        c.activeSurfaceTitle,
        c.drafterPageTitles,
      );
      const project = prependProjectContext(manuscript, surface);
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
      {logosOpen && logosSession && (
        <LogosInlineBox
          editor={logosSession.editor}
          context={logosSession.context}
          baseUrl={baseUrl}
          onClose={closeLogos}
        />
      )}
    </>
  );
}
