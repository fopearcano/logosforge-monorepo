import { normalizeDocumentSettings } from './documentSettings';
import type { WhiteboardBlock, WhiteboardDocument, WhiteboardUpdate } from './types';

const STABLE_ID_RE = /^[^\s\u0000-\u001f\u007f]{1,256}$/;
const SCREENPLAY_TYPES = new Set([
  'scene_heading', 'action', 'character', 'dialogue', 'parenthetical', 'transition',
  'section', 'synopsis', 'note', 'centered', 'lyrics', 'page_break', 'empty',
]);
const RECOVERY_MODES = new Set(['novel', 'screenplay', 'graphic_novel', 'stage_script']);

function canonicalMode(value: unknown): string {
  if (value === 'series') return 'novel';
  return typeof value === 'string' && RECOVERY_MODES.has(value) ? value : 'novel';
}

function canonicalTimestamp(value: unknown, fallback: string): string {
  if (typeof value !== 'string' || !Number.isFinite(Date.parse(value))) return fallback;
  return new Date(value).toISOString();
}

/** Repair legacy structural metadata without truncating manuscript text. */
export function canonicalizeWhiteboardRecoveryBlocks(value: unknown): WhiteboardBlock[] {
  if (!Array.isArray(value)) return [];
  const usedIds = new Set<string>();
  return value.map((rawValue, index): WhiteboardBlock => {
    const raw = rawValue && typeof rawValue === 'object' && !Array.isArray(rawValue)
      ? rawValue as Record<string, unknown>
      : {};
    const candidate = typeof raw.id === 'string' ? raw.id : '';
    let id = STABLE_ID_RE.test(candidate) && !usedIds.has(candidate)
      ? candidate
      : `recovered-block-${index + 1}`;
    while (usedIds.has(id)) id = `${id}-copy`;
    usedIds.add(id);
    const text = typeof raw.text === 'string' ? raw.text : '';
    const type = typeof raw.type === 'string'
      && raw.type.length <= 64
      && raw.type.trim() === raw.type
      && raw.type.length > 0
      ? raw.type
      : 'paragraph';
    const block: WhiteboardBlock = { id, type, text };
    if (raw.level === null || (
      Number.isSafeInteger(raw.level)
      && Number(raw.level) >= 1
      && Number(raw.level) <= 6
    )) block.level = raw.level as number | null;
    if (raw.sp === null || (typeof raw.sp === 'string' && SCREENPLAY_TYPES.has(raw.sp))) {
      block.sp = raw.sp;
    }
    if (Array.isArray(raw.marks)) {
      block.marks = raw.marks.flatMap((markValue) => {
        const mark = markValue && typeof markValue === 'object' && !Array.isArray(markValue)
          ? markValue as Record<string, unknown>
          : null;
        if (
          !mark
          || (mark.type !== 'bold' && mark.type !== 'italic')
          || !Number.isSafeInteger(mark.from)
          || !Number.isSafeInteger(mark.to)
          || Number(mark.from) < 0
          || Number(mark.to) <= Number(mark.from)
          || Number(mark.to) > text.length
        ) return [];
        return [{
          type: mark.type,
          from: mark.from as number,
          to: mark.to as number,
        }];
      });
    }
    return block;
  });
}

/** Canonicalize only fields the Whiteboard recovery schema owns. */
export function canonicalizeWhiteboardRecoveryPayload(
  value: Record<string, unknown>,
): WhiteboardUpdate {
  const payload: WhiteboardUpdate = {};
  if ('title' in value) payload.title = typeof value.title === 'string' ? value.title : '';
  if ('mode' in value) payload.mode = canonicalMode(value.mode);
  if ('blocks' in value) payload.blocks = canonicalizeWhiteboardRecoveryBlocks(value.blocks);
  if ('settings' in value) payload.settings = normalizeDocumentSettings(value.settings);
  return payload;
}

export function canonicalizeWhiteboardRecoveryDocument(
  document: WhiteboardDocument,
  exportedAt: string,
): WhiteboardDocument {
  return {
    id: document.id,
    incarnation: document.incarnation,
    revision: document.revision,
    ...(Number.isSafeInteger(document.viewRevision) && Number(document.viewRevision) >= 0
      ? { viewRevision: document.viewRevision }
      : {}),
    title: typeof document.title === 'string' ? document.title : '',
    mode: canonicalMode(document.mode),
    blocks: canonicalizeWhiteboardRecoveryBlocks(document.blocks),
    settings: normalizeDocumentSettings(document.settings),
    updated_at: canonicalTimestamp(document.updated_at, exportedAt),
  };
}
