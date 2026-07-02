/**
 * Editor view scale (pure) — Bigger / Smaller / Actual Size.
 *
 * Drives an in-app `--wb-scale` CSS variable (the writing surface + Preview),
 * deliberately separate from browser/Electron zoom. React glue lives in
 * `useEditorScale.ts`.
 */

export const MIN_SCALE = 0.7;
export const MAX_SCALE = 1.8;
export const SCALE_STEP = 0.1;

export type ScaleAction = 'bigger' | 'smaller' | 'actual';

const clamp = (n: number): number =>
  Math.min(MAX_SCALE, Math.max(MIN_SCALE, Math.round(n * 100) / 100));

export function nextScale(scale: number, action: ScaleAction): number {
  if (action === 'actual') return 1;
  return clamp(action === 'bigger' ? scale + SCALE_STEP : scale - SCALE_STEP);
}

export function scaleToPct(scale: number): number {
  return Math.round(scale * 100);
}
