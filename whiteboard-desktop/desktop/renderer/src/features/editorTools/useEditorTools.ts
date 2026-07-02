/** React glue for the Nerd Mode editor tools — load once, persist on change. */

import { useCallback, useState } from 'react';

import { DEFAULT_EDITOR_TOOLS, type EditorToolsState } from './editorToolTypes';

const KEY = 'logosforge-editor-tools';

type BoolKey = 'lineNumbers' | 'currentLineHighlight' | 'folding' | 'syntax';

function load(): EditorToolsState {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return { ...DEFAULT_EDITOR_TOOLS, ...(JSON.parse(raw) as Partial<EditorToolsState>) };
  } catch {
    /* ignore */
  }
  return DEFAULT_EDITOR_TOOLS;
}

function persist(s: EditorToolsState) {
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* ignore */
  }
}

export interface EditorToolsApi {
  tools: EditorToolsState;
  update: <K extends keyof EditorToolsState>(key: K, value: EditorToolsState[K]) => void;
  toggle: (key: BoolKey) => void;
  reset: () => void;
}

export function useEditorTools(): EditorToolsApi {
  const [tools, setTools] = useState<EditorToolsState>(load);

  const update = useCallback<EditorToolsApi['update']>((key, value) => {
    setTools((prev) => {
      const next = { ...prev, [key]: value };
      persist(next);
      return next;
    });
  }, []);

  const toggle = useCallback((key: BoolKey) => {
    setTools((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      persist(next);
      return next;
    });
  }, []);

  const reset = useCallback(() => {
    persist(DEFAULT_EDITOR_TOOLS);
    setTools(DEFAULT_EDITOR_TOOLS);
  }, []);

  return { tools, update, toggle, reset };
}
