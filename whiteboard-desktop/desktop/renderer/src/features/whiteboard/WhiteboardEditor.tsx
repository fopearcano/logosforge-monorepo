/**
 * The TipTap (ProseMirror) writing surface.
 *
 * Per-mode behavior comes from the mode registry (./modes): Screenplay applies
 * the Fountain engine (../screenplay) — inference formatting + screenplay
 * keyboard; prose modes are plain paragraphs/headings. Content maps 1:1 to the
 * backend's `blocks` contract.
 */

import { EditorContent, useEditor, type Editor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { useEffect, useRef } from 'react';

import { EditorTools, editorToolsKey, editorToolsMeta } from '../editorTools/editorToolsExtension';
import {
  CommentsExtension,
  commentsKey,
  commentsMeta,
  type CommentMark,
} from '../comments/commentsExtension';
import type { EditorToolsState } from '../editorTools/editorToolTypes';
import { GraphicNovelEditing, gnKey } from '../graphicNovel/graphicNovelExtension';
import { StageEditing, stageKey } from '../stage/stageExtension';
import { AutocompletePopup } from '../screenplay/AutocompletePopup';
import type { FountainType } from '../screenplay/fountainTypes';
import {
  ScreenplayEditing,
  currentFountainType,
  fountainKey,
} from '../screenplay/screenplayExtension';
import { useScreenplayAutocomplete } from '../screenplay/useScreenplayAutocomplete';
import type { WhiteboardBlock } from './types';
import { Bold, Italic, inlineFromText, textAndMarks } from './proseMarks';

// --- block <-> ProseMirror document mapping --------------------------------

export function blocksToDoc(blocks: WhiteboardBlock[]) {
  const content = blocks.map((b) => {
    const inline = inlineFromText(b.text, b.marks);
    if (b.type === 'heading') {
      return { type: 'heading', attrs: { level: b.level ?? 1 }, content: inline };
    }
    return { type: 'paragraph', attrs: { sp: b.sp ?? null }, content: inline };
  });
  return { type: 'doc', content: content.length ? content : [{ type: 'paragraph' }] };
}

export function docToBlocks(json: any): WhiteboardBlock[] {
  const nodes: any[] = Array.isArray(json?.content) ? json.content : [];
  return nodes.map((n, i) => {
    const { text, marks } = textAndMarks(n);
    if (n.type === 'heading') {
      return { id: `b${i}`, type: 'heading', text, level: n.attrs?.level ?? 1, marks };
    }
    return { id: `b${i}`, type: 'paragraph', text, sp: n.attrs?.sp ?? null, marks };
  });
}

// --- component --------------------------------------------------------------

interface Props {
  initialBlocks: WhiteboardBlock[];
  mode: string;
  onChangeBlocks: (blocks: WhiteboardBlock[]) => void;
  onEditorReady?: (editor: Editor) => void;
  /** Reports the inferred screenplay element at the cursor (for the status line). */
  onElementChange?: (type: FountainType | null) => void;
  /** Optional Nerd Mode editor aids (line numbers / folding / syntax). */
  editorTools: EditorToolsState;
  folds: Set<number>;
  onToggleFold: (index: number) => void;
  /** Inline comments to paint as highlights (reconciled by the parent). */
  commentMarks?: CommentMark[];
  activeCommentId?: string | null;
  onCommentClick?: (id: string) => void;
}

export function WhiteboardEditor({
  initialBlocks,
  mode,
  onChangeBlocks,
  onEditorReady,
  onElementChange,
  editorTools,
  folds,
  onToggleFold,
  commentMarks,
  activeCommentId,
  onCommentClick,
}: Props) {
  const onChangeRef = useRef(onChangeBlocks);
  onChangeRef.current = onChangeBlocks;
  const onReadyRef = useRef(onEditorReady);
  onReadyRef.current = onEditorReady;
  const onElementRef = useRef(onElementChange);
  onElementRef.current = onElementChange;
  const onToggleFoldRef = useRef(onToggleFold);
  onToggleFoldRef.current = onToggleFold;
  const onCommentClickRef = useRef(onCommentClick);
  onCommentClickRef.current = onCommentClick;

  const { onAutocomplete, setEditor: setAcEditor, popup } = useScreenplayAutocomplete();

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
        bold: false,
        italic: false,
        strike: false,
        code: false,
        codeBlock: false,
        blockquote: false,
        horizontalRule: false,
        bulletList: false,
        orderedList: false,
        listItem: false,
        hardBreak: false,
      }),
      Bold,
      Italic,
      ScreenplayEditing.configure({ onAutocomplete }),
      GraphicNovelEditing,
      StageEditing,
      EditorTools.configure({ onToggleFold: (i) => onToggleFoldRef.current(i) }),
      CommentsExtension.configure({ onCommentClick: (id) => onCommentClickRef.current?.(id) }),
    ],
    content: blocksToDoc(initialBlocks),
    autofocus: 'end',
    // React 18 + StrictMode double-invoke / HMR can leave a TipTap editor that
    // renders immediately in a blank or detached state. Defer the first render
    // to a layout effect so the surface always mounts populated.
    immediatelyRender: false,
    editorProps: {
      // Set data-writing-mode at creation (not only in the effect below) so the
      // very first paint already has the per-mode typography and the screenplay
      // Tab handler reads the right mode — no flash of unstyled text, no race.
      attributes: { class: 'wb-editor', 'data-writing-mode': mode },
    },
    onUpdate: ({ editor: ed }) => {
      onChangeRef.current(docToBlocks(ed.getJSON()));
      onElementRef.current?.(currentFountainType(ed));
    },
    onSelectionUpdate: ({ editor: ed }) => {
      onElementRef.current?.(currentFountainType(ed));
    },
  });

  // Reflect the mode on the surface (drives per-mode typography) and tell the
  // Fountain plugin whether to infer/format (reliable, no DOM-timing race).
  useEffect(() => {
    if (!editor) return;
    editor.view.dom.setAttribute('data-writing-mode', mode);
    editor.view.dispatch(
      editor.state.tr
        .setMeta(fountainKey, { screenplay: mode === 'screenplay' })
        .setMeta(gnKey, { gn: mode === 'graphic_novel' })
        .setMeta(stageKey, { stage: mode === 'stage_script' }),
    );
  }, [editor, mode]);

  // Push the Nerd Mode tool state (line numbers / folding / syntax / folds) into
  // the editor-tools plugin so it can (re)render its decorations.
  useEffect(() => {
    if (!editor) return;
    editor.view.dispatch(editor.state.tr.setMeta(editorToolsKey, editorToolsMeta(editorTools, mode, folds)));
  }, [editor, mode, editorTools, folds]);

  // Push comment marks into the comments plugin so it (re)paints the highlights.
  useEffect(() => {
    if (!editor) return;
    editor.view.dispatch(
      editor.state.tr.setMeta(commentsKey, commentsMeta(commentMarks ?? [], activeCommentId ?? null)),
    );
  }, [editor, commentMarks, activeCommentId]);

  useEffect(() => {
    if (!editor) return;
    setAcEditor(editor);
    onReadyRef.current?.(editor);
    onElementRef.current?.(currentFountainType(editor));
  }, [editor, setAcEditor]);

  return (
    <>
      <EditorContent editor={editor} className="wb-content" />
      <AutocompletePopup {...popup} />
    </>
  );
}
