/**
 * Shared LittleBoy types (Whiteboard Small AI). Wire shapes mirror the backend
 * DTOs in backend/app/schemas/littleboy.py.
 */

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

/** Bounded context captured from the editor for an AI request. */
export interface EditorContext {
  /** Selected text (empty when there is no selection). */
  selection: string;
  /** The current paragraph/block text. */
  block: string;
  /** Bounded text around the cursor (selection + surroundings). */
  nearby: string;
  /** ProseMirror positions of the (captured) selection. */
  from: number;
  to: number;
  mode: string;
  screenplayElement?: string | null;
  documentTitle?: string;
  /** Viewport coords of the caret/selection start (for placing Logos). */
  coords: { left: number; top: number; bottom: number };
}

// --- Billy (chat) -----------------------------------------------------------

export interface BillyChatRequest {
  message: string;
  selected_text?: string;
  nearby_context?: string;
  writing_mode?: string;
  document_title?: string;
  conversation_id?: string;
  history?: ChatMessage[];
}

export interface BillyChatResponse {
  ok: boolean;
  conversation_id: string;
  message: ChatMessage;
  provider: string;
  note?: string | null;
}

// --- Logos (inline) ---------------------------------------------------------

export type LogosActionId =
  | 'suggest'
  | 'rewrite'
  | 'expand'
  | 'compress'
  | 'explain'
  | 'improve_dialogue'
  | 'improve_action'
  | 'make_more_visual'
  | 'connect_to_psyke'
  | 'summarize';

export interface LogosInlineRequest {
  action: LogosActionId | string;
  selected_text?: string;
  nearby_context?: string;
  writing_mode?: string;
  instruction?: string;
  document_title?: string;
}

export interface LogosInlineResponse {
  ok: boolean;
  action: string;
  result: string;
  suggested_replacement?: string | null;
  provider: string;
  note?: string | null;
}
