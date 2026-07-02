/** Pure writing-mode/context labels for the AI agents (unit-testable). */

const MODE_LABELS: Record<string, string> = {
  novel: 'Novel',
  screenplay: 'Screenplay',
  graphic_novel: 'Graphic Novel',
  stage_script: 'Stage Script',
  notes: 'Notes',
  scene: 'Scene',
};

export function modeLabel(mode: string | null | undefined): string {
  if (!mode) return 'Novel';
  return MODE_LABELS[mode] ?? mode.charAt(0).toUpperCase() + mode.slice(1);
}

export function isScreenplayMode(mode: string | null | undefined): boolean {
  return mode === 'screenplay';
}

const ELEMENT_LABELS: Record<string, string> = {
  scene_heading: 'Scene Heading',
  action: 'Action',
  character: 'Character',
  dialogue: 'Dialogue',
  parenthetical: 'Parenthetical',
  transition: 'Transition',
  section: 'Section',
  synopsis: 'Synopsis',
  note: 'Note',
};

export function screenplayElementLabel(el: string | null | undefined): string {
  if (!el) return '';
  return ELEMENT_LABELS[el] ?? el;
}

/** A compact one-line description of the active context (for box headers). */
export function contextLabel(mode: string, element?: string | null): string {
  const m = modeLabel(mode);
  const e = isScreenplayMode(mode) ? screenplayElementLabel(element) : '';
  return e ? `${m} · ${e}` : m;
}
