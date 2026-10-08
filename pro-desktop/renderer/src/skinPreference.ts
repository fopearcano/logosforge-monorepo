import { resolveSkin, type SkinId } from '@logosforge/pro-shared-ui';

export const SKIN_STORAGE_KEY = 'lf.skin.v1';
export const LEGACY_THEME_STORAGE_KEY = 'lf.theme';

type ReadableStorage = Pick<Storage, 'getItem'>;
type WritableStorage = Pick<Storage, 'setItem'>;
type SkinRoot = { dataset: DOMStringMap };

/** Read the app-wide preference and migrate the former appearance ids. */
export function readSkinPreference(storage: ReadableStorage = window.localStorage): SkinId {
  try {
    return resolveSkin(storage.getItem(SKIN_STORAGE_KEY) ?? storage.getItem(LEGACY_THEME_STORAGE_KEY));
  } catch {
    return 'forge';
  }
}

/** Preference storage is optional; a locked-down browser must remain usable. */
export function writeSkinPreference(skin: SkinId, storage: WritableStorage = window.localStorage): void {
  try {
    storage.setItem(SKIN_STORAGE_KEY, skin);
  } catch {
    // The active in-memory skin still works for this session.
  }
}

export function applySkinPreference(skin: SkinId, root: SkinRoot = document.documentElement): void {
  root.dataset.skin = skin;
  delete root.dataset.theme;
}
