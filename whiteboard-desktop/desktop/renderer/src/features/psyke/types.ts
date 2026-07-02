/** Shared types for the PSYKE feature. Mirrors the backend DTOs. */

export type PsykeElementType = 'character' | 'place' | 'object' | 'lore' | 'theme' | 'other';

export interface PsykeEntry {
  id: string;
  name: string;
  entry_type: string;
  aliases: string[];
  description?: string;
  notes?: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface PsykeSearchResponse {
  query: string;
  results: PsykeEntry[];
}

export interface PsykeCreatePayload {
  type: PsykeElementType;
  name: string;
  description: string;
  notes: string;
}

export interface PsykeCreateResponse {
  ok: boolean;
  element: PsykeEntry;
}

/** Partial update — only the provided fields change. */
export interface PsykeUpdatePayload {
  type?: PsykeElementType;
  name?: string;
  description?: string;
  notes?: string;
}

export interface PsykeDeleteResponse {
  ok: boolean;
  deleted: string;
}
