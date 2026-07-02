/** Shared types for the Whiteboard feature. Mirrors the backend DTOs. */

export type SaveStatus = 'idle' | 'saving' | 'saved' | 'error';

/** An inline bold/italic run, by character offset into the block's plain text. */
export interface InlineMark {
  type: 'bold' | 'italic';
  from: number;
  to: number;
}

export interface WhiteboardBlock {
  id: string;
  /** 'paragraph' | 'heading' (other types are tolerated and treated as paragraphs). */
  type: string;
  text: string;
  level?: number | null;
  /** Screenplay element type on a paragraph (Screenplay mode); persists. */
  sp?: string | null;
  /** Inline bold/italic marks (prose modes); persists alongside the plain text. */
  marks?: InlineMark[];
}

export interface WhiteboardDocument {
  id: string;
  title: string;
  mode: string;
  blocks: WhiteboardBlock[];
  updated_at: string;
}

export interface WhiteboardUpdate {
  title?: string;
  mode?: string;
  blocks?: WhiteboardBlock[];
}
