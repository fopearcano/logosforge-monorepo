/**
 * Opt-in access to fonts installed on the writer's computer.
 *
 * `queryLocalFonts()` is deliberately called only by the exported user-gesture
 * adapter. Callers must invoke it directly from a click/change handler: putting
 * an awaited permission preflight in front of the call loses Chromium's user
 * activation and causes a SecurityError.
 *
 * The returned inventory is intentionally reduced to family names. Whiteboard
 * never asks `FontData.blob()` for font bytes and never persists the inventory;
 * only the family explicitly chosen by the writer belongs in editor settings.
 */

export const INSTALLED_FONT_FAMILY_MAX_LENGTH = 128;

/** The narrow portion of Chromium's FontData used by Whiteboard. */
export interface LocalFontFaceDescriptor {
  family: unknown;
}

/**
 * Kept local instead of widening Window globally because TypeScript's DOM
 * library can lag Chromium's Local Font Access API.
 */
export interface LocalFontQueryHost {
  queryLocalFonts?: () => Promise<readonly LocalFontFaceDescriptor[]>;
}

export type InstalledFontInventoryErrorCode =
  | 'unsupported'
  | 'denied'
  | 'security'
  | 'failed';

export class InstalledFontInventoryError extends Error {
  readonly code: InstalledFontInventoryErrorCode;

  constructor(code: InstalledFontInventoryErrorCode, message: string) {
    super(message);
    this.name = 'InstalledFontInventoryError';
    this.code = code;
  }
}

// A font family is always emitted as a quoted CSS string, but a conservative
// allowlist is still useful at the localStorage boundary. It supports Unicode
// family names while excluding CSS delimiters, escapes, quotes, and controls.
const SAFE_FAMILY_NAME = /^[\p{L}\p{M}\p{N}][\p{L}\p{M}\p{N}\p{Zs} ._'’&()+#!-]*$/u;
const FAMILY_SORTER = new Intl.Collator('en', {
  numeric: true,
  sensitivity: 'base',
  usage: 'sort',
});

/** Normalize a local-font family at both the browser-result and storage edge. */
export function normalizeInstalledFontFamily(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const normalized = value
    .normalize('NFC')
    .replace(/\p{Zs}+/gu, ' ')
    .trim();
  if (
    normalized.length === 0
    || normalized.length > INSTALLED_FONT_FAMILY_MAX_LENGTH
    || !SAFE_FAMILY_NAME.test(normalized)
  ) {
    return null;
  }
  return normalized;
}

/**
 * Reduce per-face FontData records to a deterministic family picker list.
 * Invalid names are omitted and case-only duplicates collapse to one entry.
 */
export function dedupeInstalledFontFamilies(
  faces: readonly LocalFontFaceDescriptor[],
): string[] {
  const candidates = faces
    .map((face) => normalizeInstalledFontFamily(face?.family))
    .filter((family): family is string => family !== null)
    .sort((left, right) => {
      const compared = FAMILY_SORTER.compare(left, right);
      if (compared !== 0) return compared;
      return left < right ? -1 : left > right ? 1 : 0;
    });

  const seen = new Set<string>();
  const families: string[] = [];
  for (const family of candidates) {
    const key = family.toLocaleLowerCase('en-US');
    if (seen.has(key)) continue;
    seen.add(key);
    families.push(family);
  }
  return families;
}

/**
 * Convert a validated family into a non-injectable CSS stack. The mode voice is
 * the fallback when a font is later removed from the operating system.
 */
export function installedFontCssStack(value: unknown): string | null {
  const family = normalizeInstalledFontFamily(value);
  if (!family) return null;
  // The validator rejects both characters, but escaping again keeps this sink
  // safe if the accepted family grammar is deliberately broadened later.
  const quoted = family.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
  return `"${quoted}", var(--wb-mode-typeface)`;
}

function failureName(error: unknown): string {
  return error && typeof error === 'object' && 'name' in error
    ? String((error as { name?: unknown }).name ?? '')
    : '';
}

/**
 * Enumerate installed families. Invoke this function directly from a user
 * gesture; it intentionally calls `queryLocalFonts()` before its first await.
 */
export async function queryInstalledFontFamiliesFromUserGesture(
  suppliedHost?: LocalFontQueryHost,
): Promise<string[]> {
  const host = suppliedHost ?? (window as unknown as LocalFontQueryHost);
  const query = host.queryLocalFonts;
  if (typeof query !== 'function') {
    throw new InstalledFontInventoryError(
      'unsupported',
      'Installed-font access is not supported by this Whiteboard runtime.',
    );
  }

  let pending: Promise<readonly LocalFontFaceDescriptor[]>;
  try {
    // Keep this invocation synchronous with the originating click/change event.
    pending = query.call(host);
  } catch (error) {
    throw inventoryError(error);
  }

  try {
    return dedupeInstalledFontFamilies(await pending);
  } catch (error) {
    throw inventoryError(error);
  }
}

function inventoryError(error: unknown): InstalledFontInventoryError {
  const name = failureName(error);
  if (name === 'NotAllowedError') {
    return new InstalledFontInventoryError(
      'denied',
      'Whiteboard was not allowed to read the installed-font list.',
    );
  }
  if (name === 'SecurityError') {
    return new InstalledFontInventoryError(
      'security',
      'Installed fonts can only be loaded from Whiteboard after an explicit click.',
    );
  }
  return new InstalledFontInventoryError(
    'failed',
    'Whiteboard could not read the installed-font list.',
  );
}
