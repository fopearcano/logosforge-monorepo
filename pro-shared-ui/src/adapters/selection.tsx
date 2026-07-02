import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

/**
 * The Studio's lightweight cross-panel selection bus. The Manuscript Editor
 * publishes the scene the writer is in + the text they have selected; panels like
 * Logos consume it (to act on the live selection and pass the scene's context),
 * instead of each panel needing the writer to re-paste a passage.
 *
 * This is internal UI state owned by the shared-ui (NOT host-injected) — it's
 * nested inside <StudioProvider> so it's available app-wide with no app change.
 */

export interface StudioSelection {
  /** The scene the writer is currently editing, or null. */
  sceneId: number | null;
  /** The text currently selected (empty if a collapsed caret / non-text panel). */
  text: string;
  /** Which Logos section the active selection belongs to (e.g. "Manuscript",
   *  "PSYKE", "Outline", "Plot", "Timeline", "Graph"). Lets Logos attach the right
   *  node context when a non-manuscript panel publishes. */
  section?: string;
  /** A generic node reference for non-scene panels (psyke entry id, outline node id,
   *  plot block id, timeline event id, graph node id). */
  nodeId?: string | number | null;
}

interface SelectionContextValue {
  selection: StudioSelection;
  setSelection: (s: StudioSelection) => void;
}

const EMPTY: StudioSelection = { sceneId: null, text: "" };
const STABLE_NOOP: SelectionContextValue = { selection: EMPTY, setSelection: () => {} };

const SelectionContext = createContext<SelectionContextValue | null>(null);

export function SelectionProvider({ children }: { children: ReactNode }) {
  const [selection, setSel] = useState<StudioSelection>(EMPTY);
  const setSelection = useCallback((s: StudioSelection) => setSel(s), []);
  return <SelectionContext.Provider value={{ selection, setSelection }}>{children}</SelectionContext.Provider>;
}

/** Read/publish the active cross-panel selection. Safe (no-op) outside a provider. */
export function useSelection(): SelectionContextValue {
  return useContext(SelectionContext) ?? STABLE_NOOP;
}
