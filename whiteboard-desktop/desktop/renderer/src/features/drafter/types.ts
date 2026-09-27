import type { WhiteboardBlock } from '../whiteboard/types';

/** A project-owned scratch page. Drafter pages inherit the document mode/settings. */
export interface DrafterPage {
  id: string;
  title: string;
  blocks: WhiteboardBlock[];
  created_at: string;
  updated_at: string;
}

/** Aggregate, revisioned Drafter resource returned by `/api/drafter/pages`. */
export interface DrafterPagesDocument {
  pages: DrafterPage[];
  revision: string;
}

export type DrafterSaveStatus = 'idle' | 'saving' | 'saved' | 'error' | 'conflict';

export type WritingSurface =
  | { kind: 'manuscript' }
  | { kind: 'draft'; pageId: string };
