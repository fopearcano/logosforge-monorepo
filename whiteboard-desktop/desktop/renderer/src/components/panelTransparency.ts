export const PANEL_TRANSPARENCY_MAX = 70;

interface PanelTransparencyStorage {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
}

export function normalizePanelTransparency(value: unknown): number {
  const numeric = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(numeric)) return 0;
  return Math.min(PANEL_TRANSPARENCY_MAX, Math.max(0, Math.round(numeric)));
}

export function opacityForPanelTransparency(value: unknown): number {
  return 1 - normalizePanelTransparency(value) / 100;
}

export function loadPanelTransparency(
  storageKey: string,
  storage?: PanelTransparencyStorage,
): number {
  try {
    return normalizePanelTransparency((storage ?? localStorage).getItem(storageKey));
  } catch {
    return 0;
  }
}

export function savePanelTransparency(
  storageKey: string,
  value: number,
  storage?: PanelTransparencyStorage,
): void {
  try {
    (storage ?? localStorage).setItem(storageKey, String(normalizePanelTransparency(value)));
  } catch {
    /* ignore unavailable storage */
  }
}
