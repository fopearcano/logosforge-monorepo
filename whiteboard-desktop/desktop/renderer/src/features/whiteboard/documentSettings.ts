/**
 * Document Settings (Screenplay) — pure types, defaults, and persistence.
 *
 * Kept tiny and writing-first (this is NOT a general preferences system).
 * Persisted in localStorage so it survives restarts without touching the
 * backend document contract. React glue lives in `useDocumentSettings.ts`.
 */

export type SceneHeadingStyle = 'normal' | 'bold' | 'underline' | 'bold-underline';
export type Typeface = 'courier-prime' | 'courier' | 'monospace';
export type NarrativePerson = 'unspecified' | 'first' | 'third-limited' | 'third-omniscient';
export type NarrativeStyle = 'neutral' | 'literary' | 'commercial' | 'cinematic' | 'minimalist' | 'lyrical';
export type NarrativeRegister = 'neutral' | 'formal' | 'standard' | 'colloquial' | 'vernacular';
export type SlangLevel = 'none' | 'light' | 'moderate' | 'heavy';

export interface DocumentSettings {
  /** General narrative voice defaults used by Billy/Logos in every mode. */
  narrativePerson: NarrativePerson;
  narrativeStyle: NarrativeStyle;
  narrativeRegister: NarrativeRegister;
  slangLevel: SlangLevel;
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
  narrativePerson: 'unspecified',
  narrativeStyle: 'neutral',
  narrativeRegister: 'neutral',
  slangLevel: 'none',
  sceneHeadingStyle: 'bold',
  blankLinesBeforeScene: 1,
  includeOutline: false,
  typeface: 'courier-prime',
  showInvisibles: true,
};

const PERSON_LABEL: Record<NarrativePerson, string> = {
  unspecified: '',
  first: 'first person',
  'third-limited': 'third person limited',
  'third-omniscient': 'third person omniscient',
};

/** Compact, explicit AI grounding. Empty defaults add no prompt noise. */
export function narrativeProfileContext(settings: DocumentSettings): string {
  const parts: string[] = [];
  const person = PERSON_LABEL[settings.narrativePerson];
  if (person) parts.push(`Person: ${person}`);
  if (settings.narrativeStyle !== 'neutral') parts.push(`Style: ${settings.narrativeStyle}`);
  if (settings.narrativeRegister !== 'neutral') parts.push(`Register: ${settings.narrativeRegister}`);
  if (settings.slangLevel !== 'none') parts.push(`Slang: ${settings.slangLevel}`);
  return parts.length
    ? `[Narrative Voice]\n${parts.join('; ')}. Treat these as the writer's general voice defaults unless the selected passage deliberately differs.`
    : '';
}

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
