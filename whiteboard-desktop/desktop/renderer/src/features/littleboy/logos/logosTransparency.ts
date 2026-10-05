export const LOGOS_TRANSPARENCY_KEY = 'logosforge-logos-transparency';
export const LOGOS_TRANSPARENCY_MAX = 70;

export function normalizeLogosTransparency(value: unknown): number {
  const numeric = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(numeric)) return 0;
  return Math.min(LOGOS_TRANSPARENCY_MAX, Math.max(0, Math.round(numeric)));
}

export function loadLogosTransparency(): number {
  try {
    return normalizeLogosTransparency(localStorage.getItem(LOGOS_TRANSPARENCY_KEY));
  } catch {
    return 0;
  }
}

export function saveLogosTransparency(value: number): void {
  try {
    localStorage.setItem(LOGOS_TRANSPARENCY_KEY, String(normalizeLogosTransparency(value)));
  } catch {
    /* ignore unavailable storage */
  }
}
