/** React glue for the Nerd Mode editor tools — load once, persist on change. */

import { useCallback, useState } from 'react';

import {
  DEFAULT_EDITOR_TOOLS,
  EDITOR_TYPEFACES,
  FONT_SIZE_MAX,
  FONT_SIZE_MIN,
  LINE_HEIGHT_MAX,
  LINE_HEIGHT_MIN,
  type EditorToolsState,
} from './editorToolTypes';

const KEY = 'logosforge-editor-tools';

type BoolKey = 'lineNumbers' | 'currentLineHighlight' | 'folding' | 'syntax';

const TYPEFACE_SET = new Set<string>(EDITOR_TYPEFACES);
const HEX_COLOR = /^#[0-9a-f]{6}$/i;

function optionalNumber(value: unknown, min: number, max: number): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max
    ? value
    : null;
}

/** Normalize persisted preferences so stale/edited storage cannot leak invalid CSS. */
export function normalizeEditorTools(value: unknown): EditorToolsState {
  const raw = value && typeof value === 'object' ? (value as Record<string, unknown>) : {};
  return {
    lineNumbers: typeof raw.lineNumbers === 'boolean' ? raw.lineNumbers : DEFAULT_EDITOR_TOOLS.lineNumbers,
    currentLineHighlight:
      typeof raw.currentLineHighlight === 'boolean'
        ? raw.currentLineHighlight
        : DEFAULT_EDITOR_TOOLS.currentLineHighlight,
    folding: typeof raw.folding === 'boolean' ? raw.folding : DEFAULT_EDITOR_TOOLS.folding,
    syntax: typeof raw.syntax === 'boolean' ? raw.syntax : DEFAULT_EDITOR_TOOLS.syntax,
    fontSize: optionalNumber(raw.fontSize, FONT_SIZE_MIN, FONT_SIZE_MAX),
    lineHeight: optionalNumber(raw.lineHeight, LINE_HEIGHT_MIN, LINE_HEIGHT_MAX),
    typeface: TYPEFACE_SET.has(String(raw.typeface))
      ? (raw.typeface as EditorToolsState['typeface'])
      : DEFAULT_EDITOR_TOOLS.typeface,
    textColor:
      typeof raw.textColor === 'string' && HEX_COLOR.test(raw.textColor)
        ? raw.textColor.toLowerCase()
        : null,
    layout: raw.layout === 'paged' || raw.layout === 'flow' ? raw.layout : DEFAULT_EDITOR_TOOLS.layout,
  };
}

function load(): EditorToolsState {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return normalizeEditorTools(JSON.parse(raw));
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
