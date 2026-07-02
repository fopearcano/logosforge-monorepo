/** Outline item types (derived from the document, client-side). */

export type OutlineKind = 'section' | 'scene' | 'synopsis' | 'note';

export interface OutlineItem {
  id: string;
  label: string;
  kind: OutlineKind;
  /** Heading level for sections (0 for non-section kinds). */
  level: number;
  /** Index of the source block — used to scroll the editor to it. */
  blockIndex: number;
}
