/**
 * Wires the screenplay autocomplete: the editor's Tab handler calls
 * `onAutocomplete` (open the popup at the caret with doc-derived suggestions);
 * selecting replaces the current line with the chosen text.
 */

import type { Editor } from '@tiptap/react';
import { useCallback, useRef, useState } from 'react';

import type { AutocompleteContext } from './screenplayExtension';

interface AcState {
  open: boolean;
  left: number;
  top: number;
  query: string;
  from: number;
  to: number;
  suggestions: string[];
}

const CLOSED: AcState = { open: false, left: 0, top: 0, query: '', from: 0, to: 0, suggestions: [] };

export interface PopupProps {
  open: boolean;
  left: number;
  top: number;
  query: string;
  suggestions: string[];
  onSelect: (text: string) => void;
  onClose: () => void;
}

export function useScreenplayAutocomplete() {
  const editorRef = useRef<Editor | null>(null);
  const [state, setState] = useState<AcState>(CLOSED);

  const onAutocomplete = useCallback(
    (ctx: AutocompleteContext) => setState({ open: true, ...ctx }),
    [],
  );
  const onClose = useCallback(() => setState((s) => ({ ...s, open: false })), []);
  const onSelect = useCallback((text: string) => {
    setState((s) => {
      const ed = editorRef.current;
      if (ed && s.open) ed.chain().focus().insertContentAt({ from: s.from, to: s.to }, text).run();
      return { ...s, open: false };
    });
  }, []);
  const setEditor = useCallback((e: Editor | null) => {
    editorRef.current = e;
  }, []);

  const popup: PopupProps = {
    open: state.open,
    left: state.left,
    top: state.top,
    query: state.query,
    suggestions: state.suggestions,
    onSelect,
    onClose,
  };

  return { onAutocomplete, setEditor, popup };
}
