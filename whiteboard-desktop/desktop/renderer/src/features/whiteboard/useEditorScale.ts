/** React glue for the editor view scale — persisted in localStorage. */

import { useCallback, useState } from 'react';

import { nextScale, type ScaleAction } from './editorScale';

const KEY = 'logosforge-editor-scale';

function initialScale(): number {
  try {
    const v = parseFloat(localStorage.getItem(KEY) ?? '');
    if (!Number.isNaN(v) && v > 0) return v;
  } catch {
    /* ignore */
  }
  return 1;
}

export interface EditorScaleApi {
  scale: number;
  apply: (action: ScaleAction) => void;
}

export function useEditorScale(): EditorScaleApi {
  const [scale, setScale] = useState<number>(initialScale);

  const apply = useCallback((action: ScaleAction) => {
    setScale((s) => {
      const n = nextScale(s, action);
      try {
        localStorage.setItem(KEY, String(n));
      } catch {
        /* ignore */
      }
      return n;
    });
  }, []);

  return { scale, apply };
}
