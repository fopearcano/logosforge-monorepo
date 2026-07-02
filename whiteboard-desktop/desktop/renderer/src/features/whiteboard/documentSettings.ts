/**
 * Document Settings (Screenplay) — pure types, defaults, and persistence.
 *
 * Kept tiny and writing-first (this is NOT a general preferences system).
 * Persisted in localStorage so it survives restarts without touching the
 * backend document contract. React glue lives in `useDocumentSettings.ts`.
 */

export type SceneHeadingStyle = 'normal' | 'bold' | 'underline' | 'bold-underline';
export type Typeface = 'courier-prime' | 'courier' | 'monospace';

export interface DocumentSettings {
  /** Scene Heading emphasis (writing surface + Preview). */
  sceneHeadingStyle: SceneHeadingStyle;
  /** Blank lines rendered before a Scene Heading. */
  blankLinesBeforeScene: 1 | 2;
  /** Include Sections/Synopses (outline elements) in the Preview. */
  includeOutline: boolean;
  /** Editor typeface. */
  typeface: Typeface;
  /** Show the (otherwise dimmed) Fountain emphasis markers in the writing view. */
  showInvisibles: boolean;
}

export const DEFAULT_SETTINGS: DocumentSettings = {
  sceneHeadingStyle: 'bold',
  blankLinesBeforeScene: 1,
  includeOutline: false,
  typeface: 'courier-prime',
  showInvisibles: true,
};

const KEY = 'logosforge-doc-settings';

export function loadSettings(): DocumentSettings {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return { ...DEFAULT_SETTINGS, ...(JSON.parse(raw) as Partial<DocumentSettings>) };
  } catch {
    /* ignore */
  }
  return DEFAULT_SETTINGS;
}

export function saveSettings(s: DocumentSettings): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* ignore */
  }
}

/**
 * The `data-*` attributes that drive Screenplay typography from the writing
 * surface, so the writing view and the Preview stay visually in sync via CSS.
 */
export function surfaceDataAttrs(s: DocumentSettings): Record<string, string> {
  return {
    'data-scene-style': s.sceneHeadingStyle,
    'data-scene-blank': String(s.blankLinesBeforeScene),
    'data-typeface': s.typeface,
    'data-invisibles': s.showInvisibles ? 'on' : 'off',
  };
}
