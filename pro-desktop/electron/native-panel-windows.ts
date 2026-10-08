/**
 * Pure data and geometry helpers for the Electron-native floating panel host.
 *
 * Keep this module free of Electron imports so its security boundary and
 * multi-display recovery can be exercised by the small Node test suite.
 */

export const NATIVE_PANEL_WINDOW_FRAME_PREFIX = 'logosforge-panel:';
export type NativePanelWindowFramePrefix = typeof NATIVE_PANEL_WINDOW_FRAME_PREFIX;

/**
 * This intentionally duplicates STUDIO_WORKSPACE_PANEL_IDS. The Electron main
 * process must not load the renderer's React panel catalog merely to validate a
 * security-sensitive window.open request.
 */
export const NATIVE_PANEL_IDS = [
  'projects',
  'dashboard',
  'manuscript',
  'notes',
  'comments',
  'dexters-room',
  'outline',
  'story-grid',
  'timeline',
  'canvas-plot',
  'series',
  'structure',
  'acts',
  'beats',
  'chapters',
  'structure-analysis',
  'format-studio',
  'health',
  'pacing',
  'balance',
  'tags',
  'continuity',
  'decision-radar',
  'guided-workflows',
  'adapt',
  'review',
  'psyke',
  'characters',
  'theme-scenes',
  'graph',
  'plugins',
  'connector',
  'export',
  'ai-settings',
  'settings',
  'help',
  'ai-companions',
] as const;

export type NativePanelId = typeof NATIVE_PANEL_IDS[number];

const nativePanelIdSet: ReadonlySet<string> = new Set(NATIVE_PANEL_IDS);

export interface NativePanelWindowBounds {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface NativePanelWindowRequest {
  panelId: NativePanelId;
  token: string;
}

export type NativePanelWindowEvent =
  | { type: 'bounds-changed'; panelId: NativePanelId; token: string; bounds: NativePanelWindowBounds }
  | { type: 'focused'; panelId: NativePanelId; token: string }
  | { type: 'minimized'; panelId: NativePanelId; token: string }
  | { type: 'restored'; panelId: NativePanelId; token: string; bounds: NativePanelWindowBounds }
  | { type: 'close-requested'; panelId: NativePanelId; token: string; bounds: NativePanelWindowBounds }
  | { type: 'closed'; panelId: NativePanelId; token: string; reason: 'renderer' | 'unexpected' };

export const NATIVE_PANEL_WINDOW_CHANNELS = {
  event: 'native-panel:event',
  show: 'native-panel:show',
  focus: 'native-panel:focus',
  minimize: 'native-panel:minimize',
  restore: 'native-panel:restore',
  close: 'native-panel:close',
  bounds: 'native-panel:bounds',
} as const;

export type NativePanelWindowChannels = typeof NATIVE_PANEL_WINDOW_CHANNELS;

export function isNativePanelId(value: unknown): value is NativePanelId {
  return typeof value === 'string' && nativePanelIdSet.has(value);
}

export function requireNativePanelId(value: unknown): NativePanelId {
  if (!isNativePanelId(value)) throw new Error('Unknown native panel id.');
  return value;
}

export function requireNativePanelWindowToken(value: unknown): string {
  if (typeof value !== 'string' || !/^[A-Za-z0-9_-]{16,128}$/.test(value)) {
    throw new Error('Invalid native panel window token.');
  }
  return value;
}

export function nativePanelWindowFrameName(panelId: string, token: string): string {
  return `${NATIVE_PANEL_WINDOW_FRAME_PREFIX}${requireNativePanelId(panelId)}:${requireNativePanelWindowToken(token)}`;
}

export function nativePanelWindowRequestFromFrameName(
  frameName: string,
): NativePanelWindowRequest | null {
  if (!frameName.startsWith(NATIVE_PANEL_WINDOW_FRAME_PREFIX)) return null;
  const request = frameName.slice(NATIVE_PANEL_WINDOW_FRAME_PREFIX.length);
  const separatorIndex = request.lastIndexOf(':');
  if (separatorIndex <= 0) return null;
  const panelId = request.slice(0, separatorIndex);
  const token = request.slice(separatorIndex + 1);
  if (!isNativePanelId(panelId)) return null;
  try {
    return { panelId, token: requireNativePanelWindowToken(token) };
  } catch {
    return null;
  }
}

export function panelIdFromNativePanelFrameName(frameName: string): NativePanelId | null {
  return nativePanelWindowRequestFromFrameName(frameName)?.panelId ?? null;
}

function isUsableRectangle(value: NativePanelWindowBounds): boolean {
  return Number.isFinite(value.x)
    && Number.isFinite(value.y)
    && Number.isFinite(value.width)
    && Number.isFinite(value.height)
    && value.width > 0
    && value.height > 0;
}

function intersectionArea(a: NativePanelWindowBounds, b: NativePanelWindowBounds): number {
  const width = Math.max(0, Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x));
  const height = Math.max(0, Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y));
  return width * height;
}

function isMeaningfullyVisible(
  bounds: NativePanelWindowBounds,
  workArea: NativePanelWindowBounds,
): boolean {
  const visibleWidth = Math.max(
    0,
    Math.min(bounds.x + bounds.width, workArea.x + workArea.width) - Math.max(bounds.x, workArea.x),
  );
  // A bottom/side strip is not enough: the OS title bar must remain reachable
  // so the writer can recover the window without resetting the whole layout.
  const titleBarTopIsReachable = bounds.y >= workArea.y
    && bounds.y + Math.min(32, bounds.height) <= workArea.y + workArea.height;
  return visibleWidth >= Math.min(96, bounds.width)
    && titleBarTopIsReachable;
}

/**
 * Recover a BrowserWindow outer rectangle into a current display work area.
 * Electron reports both BrowserWindow bounds and Display workArea in DIP
 * coordinates, so no scale-factor conversion belongs here.
 */
export function recoverNativePanelWindowBounds(
  bounds: NativePanelWindowBounds,
  workAreas: readonly NativePanelWindowBounds[],
  preferredWorkArea?: NativePanelWindowBounds,
): NativePanelWindowBounds {
  const usableAreas = workAreas.filter(isUsableRectangle);
  if (!isUsableRectangle(bounds) || usableAreas.length === 0) return { ...bounds };

  let target = preferredWorkArea && isUsableRectangle(preferredWorkArea)
    ? preferredWorkArea
    : usableAreas[0];
  let largestIntersection = -1;
  for (const workArea of usableAreas) {
    const area = intersectionArea(bounds, workArea);
    if (area > largestIntersection) {
      target = workArea;
      largestIntersection = area;
    }
  }

  // With no intersection, Electron's getDisplayMatching result (passed as the
  // preferred work area) is the nearest useful recovery target.
  if (largestIntersection === 0 && preferredWorkArea && isUsableRectangle(preferredWorkArea)) {
    target = preferredWorkArea;
  }

  const rounded = {
    x: Math.round(bounds.x),
    y: Math.round(bounds.y),
    width: Math.round(bounds.width),
    height: Math.round(bounds.height),
  };
  // Preserve deliberate cross-display or partly offscreen placement while a
  // usable title edge remains reachable. Recovery is for lost displays, not a
  // policy that continually snaps user-positioned windows into one monitor.
  if (rounded.width <= target.width
    && rounded.height <= target.height
    && usableAreas.some((workArea) => isMeaningfullyVisible(rounded, workArea))) {
    return rounded;
  }

  const width = Math.min(Math.max(1, rounded.width), Math.round(target.width));
  const height = Math.min(Math.max(1, rounded.height), Math.round(target.height));
  const minX = Math.round(target.x);
  const minY = Math.round(target.y);
  const maxX = Math.round(target.x + target.width - width);
  const maxY = Math.round(target.y + target.height - height);
  return {
    x: Math.min(Math.max(rounded.x, minX), maxX),
    y: Math.min(Math.max(rounded.y, minY), maxY),
    width,
    height,
  };
}
