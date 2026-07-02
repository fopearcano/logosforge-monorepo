/**
 * Fold state — the set of collapsed region-head block indices.
 *
 * Best-effort persistence in localStorage (indices may shift across heavy edits;
 * that only affects which blocks appear collapsed, never the document text —
 * folding is purely visual, so hidden text is always saved/restored).
 */

import { useCallback, useState } from 'react';

const KEY = 'logosforge-folds';

function load(): Set<number> {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return new Set(JSON.parse(raw) as number[]);
  } catch {
    /* ignore */
  }
  return new Set();
}

function persist(s: Set<number>) {
  try {
    localStorage.setItem(KEY, JSON.stringify([...s]));
  } catch {
    /* ignore */
  }
}

export interface FoldingApi {
  folds: Set<number>;
  toggleFold: (index: number) => void;
  clearFolds: () => void;
}

export function useFolding(): FoldingApi {
  const [folds, setFolds] = useState<Set<number>>(load);

  const toggleFold = useCallback((index: number) => {
    setFolds((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      persist(next);
      return next;
    });
  }, []);

  const clearFolds = useCallback(() => {
    setFolds(new Set());
    persist(new Set());
  }, []);

  return { folds, toggleFold, clearFolds };
}
