/** Billy (hovering chat) UI types. */

export interface BillyMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  pending?: boolean;
  error?: boolean;
}

/** Context attached to a Billy message at send time. */
export interface BillyContextInput {
  selected_text?: string;
  nearby_context?: string;
  writing_mode?: string;
  document_title?: string;
}
