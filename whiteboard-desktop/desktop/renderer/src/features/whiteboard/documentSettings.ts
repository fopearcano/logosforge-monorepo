/**
 * Document Settings (Screenplay) — pure types, defaults, and persistence.
 *
 * Kept tiny and writing-first (this is NOT a general preferences system).
 * Persisted inside each backend Whiteboard document so projects cannot leak
 * voice/format choices into one another. React glue lives in
 * `useDocumentSettings.ts`.
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

const LEGACY_KEY = 'logosforge-doc-settings';
const LEGACY_TARGET_KEY = 'logosforge-doc-settings-migration-target';
const PERSONS: NarrativePerson[] = ['unspecified', 'first', 'third-limited', 'third-omniscient'];
const STYLES: NarrativeStyle[] = ['neutral', 'literary', 'commercial', 'cinematic', 'minimalist', 'lyrical'];
const REGISTERS: NarrativeRegister[] = ['neutral', 'formal', 'standard', 'colloquial', 'vernacular'];
const SLANG: SlangLevel[] = ['none', 'light', 'moderate', 'heavy'];
const HEADING_STYLES: SceneHeadingStyle[] = ['normal', 'bold', 'underline', 'bold-underline'];
const TYPEFACES: Typeface[] = ['courier-prime', 'courier', 'monospace'];

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return typeof value === 'string' && allowed.includes(value as T) ? value as T : fallback;
}

/** Defensive normalization for backend, legacy, and imported settings. */
export function normalizeDocumentSettings(value: unknown): DocumentSettings {
  const raw = record(value);
  return {
    narrativePerson: oneOf(raw.narrativePerson, PERSONS, DEFAULT_SETTINGS.narrativePerson),
    narrativeStyle: oneOf(raw.narrativeStyle, STYLES, DEFAULT_SETTINGS.narrativeStyle),
    narrativeRegister: oneOf(raw.narrativeRegister, REGISTERS, DEFAULT_SETTINGS.narrativeRegister),
    slangLevel: oneOf(raw.slangLevel, SLANG, DEFAULT_SETTINGS.slangLevel),
    sceneHeadingStyle: oneOf(raw.sceneHeadingStyle, HEADING_STYLES, DEFAULT_SETTINGS.sceneHeadingStyle),
    blankLinesBeforeScene: raw.blankLinesBeforeScene === 2 ? 2 : 1,
    includeOutline: typeof raw.includeOutline === 'boolean' ? raw.includeOutline : DEFAULT_SETTINGS.includeOutline,
    typeface: oneOf(raw.typeface, TYPEFACES, DEFAULT_SETTINGS.typeface),
    showInvisibles: typeof raw.showInvisibles === 'boolean' ? raw.showInvisibles : DEFAULT_SETTINGS.showInvisibles,
  };
}

/** Read the old global value only for its chosen migration target document. */
export function legacySettingsForDocument(documentId: string): Partial<DocumentSettings> | null {
  try {
    const raw = localStorage.getItem(LEGACY_KEY);
    if (!raw) return null;
    let target = localStorage.getItem(LEGACY_TARGET_KEY);
    if (!target) {
      target = documentId;
      localStorage.setItem(LEGACY_TARGET_KEY, target);
    }
    if (target !== documentId) return null;
    const parsed = JSON.parse(raw) as unknown;
    return normalizeDocumentSettings(parsed);
  } catch {
    return null;
  }
}

/** Clear legacy bytes only after that target loads persisted backend settings. */
export function clearLegacySettingsMigration(documentId: string): void {
  try {
    if (localStorage.getItem(LEGACY_TARGET_KEY) !== documentId) return;
    localStorage.removeItem(LEGACY_KEY);
    localStorage.removeItem(LEGACY_TARGET_KEY);
  } catch {
    /* storage is optional */
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
