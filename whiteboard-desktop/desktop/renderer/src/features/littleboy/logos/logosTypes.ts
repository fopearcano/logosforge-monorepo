/** Logos (inline agent) action registry + pure UI helpers. */

import type { LogosActionId, LogosInlineResponse } from '../littleboyTypes';

export type LogosStatus = 'idle' | 'loading' | 'done' | 'error';

export interface LogosActionDef {
  id: LogosActionId;
  label: string;
  hint: string;
}

/** The default Logos actions (Part 6.5), in display order. */
export const LOGOS_ACTIONS: LogosActionDef[] = [
  { id: 'rewrite', label: 'Rewrite', hint: 'Reword while keeping meaning' },
  { id: 'expand', label: 'Expand', hint: 'Add detail' },
  { id: 'compress', label: 'Compress', hint: 'Tighten / shorten' },
  { id: 'make_more_visual', label: 'Make visual', hint: 'More concrete & visual' },
  { id: 'improve_dialogue', label: 'Improve dialogue', hint: 'Subtext, distinct voices' },
  { id: 'improve_action', label: 'Improve action', hint: 'Vivid present-tense action' },
  { id: 'explain', label: 'Explain', hint: 'Explain the passage' },
  { id: 'summarize', label: 'Summarize', hint: 'Condense' },
  { id: 'connect_to_psyke', label: 'Connect to PSYKE', hint: 'Find related story-bible entries' },
];

/** Actions that propose a replacement for the selected text (enable Apply). */
export const LOGOS_TRANSFORM_ACTIONS: LogosActionId[] = [
  'rewrite',
  'expand',
  'compress',
  'improve_dialogue',
  'improve_action',
  'make_more_visual',
];

export function isTransformAction(id: string): boolean {
  return (LOGOS_TRANSFORM_ACTIONS as string[]).includes(id);
}

export type LogosApplyMode = 'apply' | 'insert';

/**
 * Decide how a result can be applied (Part 6.6): only offer Apply (scoped
 * replace) when the backend returned a replacement AND there is a selection to
 * replace; otherwise the result can only be Inserted/Copied.
 */
export function applyModeFor(resp: Pick<LogosInlineResponse, 'suggested_replacement'>, hasSelection: boolean): LogosApplyMode {
  return resp.suggested_replacement && hasSelection ? 'apply' : 'insert';
}
