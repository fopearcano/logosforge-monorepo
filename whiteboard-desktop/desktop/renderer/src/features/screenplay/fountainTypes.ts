/** Core Fountain/screenplay types (pure — no editor/DOM imports). */

export type FountainType =
  | 'scene_heading'
  | 'action'
  | 'character'
  | 'dialogue'
  | 'parenthetical'
  | 'transition'
  | 'section'
  | 'synopsis'
  | 'note'
  | 'centered'
  | 'lyrics'
  | 'page_break'
  | 'empty';

export interface FountainBlock {
  text: string;
  /** True for heading nodes (these are Fountain "Sections"). */
  isHeading: boolean;
  level?: number;
}

/** An inline emphasis/marker range, relative to the start of a line's text. */
export interface EmphasisRange {
  from: number; // inclusive char index
  to: number; // exclusive char index
  className: string;
}
