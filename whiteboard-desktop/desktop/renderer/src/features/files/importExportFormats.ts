/**
 * Import / Export format conversions (pure, testable — no Electron/DOM/network).
 *
 * This EXTENDS the existing file system (fileSerialize / screenplayExport); it
 * does not replace Open/Save. Open/Save still use blocksToText/textToBlocks.
 *
 *   Import  : external file text  -> ImportResult (blocks + optional mode/…)
 *   Export  : current document    -> a string in the chosen format
 *
 * The LogosForge internal format (.logosforge) is the JSON envelope documented
 * in PART 7 of the task. No machine paths are ever written into exported files.
 */

import {
  OUTLINE_COLORS,
  OUTLINE_STATUSES,
  OUTLINE_TYPES,
  type OutlineNode,
} from '../outline/outlineModel';
import type { DocumentSettings } from '../whiteboard/documentSettings';
import type { WhiteboardBlock } from '../whiteboard/types';
import { blocksToText, textToBlocks } from './fileSerialize';

export const LOGOSFORGE_FORMAT = 'logosforge-whiteboard';
export const LOGOSFORGE_VERSION = '1.0';
export const WHITEBOARD_CONFLICT_FORMAT = 'logosforge-whiteboard-conflict';
export const OUTLINE_CONFLICT_FORMAT = 'logosforge-whiteboard-outline-conflict';
export const PENDING_DOCUMENT_RECOVERY_FORMAT = 'logosforge-pending-document-recovery';

export type RecoveryImportFormat =
  | typeof WHITEBOARD_CONFLICT_FORMAT
  | typeof OUTLINE_CONFLICT_FORMAT
  | typeof PENDING_DOCUMENT_RECOVERY_FORMAT;

export interface RecoveryImportDescriptor {
  format: RecoveryImportFormat;
  scope: 'whiteboard' | 'outline';
  documentId: string;
  /** Missing only on legacy outline conflict copies exported before identity binding. */
  incarnation: string | null;
  sourceRevision: string | null;
  exportedAt: string;
}

export interface RecoveryImportTarget {
  documentId: string;
  incarnation: string;
}

export type RecoveryIdentityRelationship =
  | 'same'
  | 'different-document'
  | 'different-incarnation'
  | 'unverifiable';

export type ImportFormatId = 'txt' | 'md' | 'fountain' | 'logosforge' | 'fdx';
export type ExportFormatId =
  | 'txt'
  | 'md'
  | 'fountain'
  | 'logosforge'
  | 'json'
  | 'html'
  | 'comments'
  | 'project-bundle';

export interface DialogFilter {
  name: string;
  extensions: string[];
}

export interface ImportFormatDef {
  id: ImportFormatId;
  label: string;
  action: string; // e.g. 'import:txt' — the shared menu action id
  filters: DialogFilter[];
  /** Importing this format switches the document to this writing mode. */
  forcesMode?: string;
}

export interface ExportFormatDef {
  id: ExportFormatId;
  label: string;
  action: string; // e.g. 'export:fountain'
  ext: string;
  filters: DialogFilter[];
}

const ALL_FILES: DialogFilter = { name: 'All Files', extensions: ['*'] };

export const IMPORT_FORMATS: ImportFormatDef[] = [
  { id: 'txt', label: 'Import Text…', action: 'import:txt', filters: [{ name: 'Text', extensions: ['txt'] }, ALL_FILES] },
  { id: 'md', label: 'Import Markdown…', action: 'import:md', filters: [{ name: 'Markdown', extensions: ['md', 'markdown'] }, ALL_FILES] },
  { id: 'fountain', label: 'Import Fountain…', action: 'import:fountain', filters: [{ name: 'Fountain', extensions: ['fountain'] }, ALL_FILES], forcesMode: 'screenplay' },
  { id: 'logosforge', label: 'Import LogosForge…', action: 'import:logosforge', filters: [{ name: 'LogosForge', extensions: ['logosforge', 'logforge', 'json'] }, ALL_FILES] },
  { id: 'fdx', label: 'Import Final Draft…', action: 'import:fdx', filters: [{ name: 'Final Draft', extensions: ['fdx'] }, ALL_FILES], forcesMode: 'screenplay' },
];

export const EXPORT_FORMATS: ExportFormatDef[] = [
  // Whole-project bundle (manuscript + outline + comments + PSYKE) — the migration
  // + backup format. Its content is assembled by the backend, not buildExport().
  { id: 'project-bundle', label: 'Export Project (.lfbundle)…', action: 'export:project-bundle', ext: 'lfbundle', filters: [{ name: 'LogosForge Project', extensions: ['lfbundle'] }] },
  { id: 'txt', label: 'Export as Text…', action: 'export:txt', ext: 'txt', filters: [{ name: 'Text', extensions: ['txt'] }] },
  { id: 'md', label: 'Export as Markdown…', action: 'export:md', ext: 'md', filters: [{ name: 'Markdown', extensions: ['md'] }] },
  { id: 'fountain', label: 'Export as Fountain…', action: 'export:fountain', ext: 'fountain', filters: [{ name: 'Fountain', extensions: ['fountain'] }] },
  { id: 'logosforge', label: 'Export as LogosForge…', action: 'export:logosforge', ext: 'logosforge', filters: [{ name: 'LogosForge', extensions: ['logosforge'] }] },
  { id: 'json', label: 'Export as JSON…', action: 'export:json', ext: 'json', filters: [{ name: 'JSON', extensions: ['json'] }] },
  { id: 'html', label: 'Export as HTML…', action: 'export:html', ext: 'html', filters: [{ name: 'HTML', extensions: ['html'] }] },
  { id: 'comments', label: 'Export Comments…', action: 'export:comments', ext: 'md', filters: [{ name: 'Markdown', extensions: ['md'] }] },
];

export const IMPORT_BY_ID = new Map(IMPORT_FORMATS.map((f) => [f.id, f]));
export const EXPORT_BY_ID = new Map(EXPORT_FORMATS.map((f) => [f.id, f]));

/** A friendly, user-facing failure (caught and shown as an error toast). */
export class ImportError extends Error {}

export interface ImportResult {
  blocks: WhiteboardBlock[];
  mode?: string;
  settings?: Partial<DocumentSettings>;
  outline?: OutlineNode[];
  psyke?: { elements: unknown[] };
  title?: string;
  /** Present only for a protected conflict/recovery copy. */
  recovery?: RecoveryImportDescriptor;
}

// --- import ----------------------------------------------------------------

/** Heuristic: NUL bytes mean we were handed a binary (e.g. image) file. */
export function looksBinary(text: string): boolean {
  return /\u0000/.test(text);
}

export function parseImport(format: ImportFormatId, text: string): ImportResult {
  if (looksBinary(text)) {
    throw new ImportError('This file does not look like a readable text document.');
  }
  switch (format) {
    case 'txt':
    case 'md':
      // Plain text / Markdown: one block per line; `#` lines become headings.
      // Markdown bullets/syntax are preserved verbatim as paragraph text.
      return { blocks: textToBlocks(text) };
    case 'fountain':
      return { blocks: textToBlocks(text), mode: 'screenplay' };
    case 'fdx':
      return parseFdx(text);
    case 'logosforge':
      return parseLogosforge(text);
    default:
      throw new ImportError('Unsupported import format.');
  }
}

const ENTITIES: Record<string, string> = {
  '&amp;': '&',
  '&lt;': '<',
  '&gt;': '>',
  '&quot;': '"',
  '&apos;': "'",
  '&#39;': "'",
};

function decodeEntities(s: string): string {
  return s.replace(/&(amp|lt|gt|quot|apos|#39);/g, (m) => ENTITIES[m] ?? m);
}

/**
 * Final Draft (.fdx) import foundation. FDX is well-structured XML; we extract
 * the screenplay paragraphs (Type + concatenated <Text> runs) with regex (no
 * DOMParser, so this stays pure + headless-testable) and emit Fountain text.
 *
 * Supported element types: Scene Heading, Action, Character, Parenthetical,
 * Dialogue, Transition (others fall through as Action).
 */
export function parseFdx(xml: string): ImportResult {
  if (!/<FinalDraft\b/i.test(xml) && !/<Paragraph\b/i.test(xml)) {
    throw new ImportError('This does not look like a Final Draft (.fdx) file.');
  }
  const paras = [...xml.matchAll(/<Paragraph\b([^>]*)>([\s\S]*?)<\/Paragraph>/gi)];
  if (paras.length === 0) {
    throw new ImportError('No screenplay content found in the Final Draft file.');
  }

  const lines: string[] = [];
  const pushSpaced = (line: string) => {
    if (lines.length && lines[lines.length - 1] !== '') lines.push('');
    lines.push(line);
  };

  for (const [, attrs, inner] of paras) {
    const typeMatch = attrs.match(/Type="([^"]*)"/i);
    const type = (typeMatch?.[1] ?? 'Action').toLowerCase();
    const text = decodeEntities(
      [...inner.matchAll(/<Text\b[^>]*>([\s\S]*?)<\/Text>/gi)].map((m) => m[1]).join(''),
    ).trim();
    if (!text && type !== 'action') continue;

    switch (type) {
      case 'scene heading': {
        const isSlug = /^(int|ext|est|int\.?\/ext|i\/e)\b/i.test(text);
        // Scene headings read uppercase; force a leading "." when it isn't a slug.
        pushSpaced(isSlug ? text.toUpperCase() : `.${text.toUpperCase()}`);
        break;
      }
      case 'character':
        pushSpaced(text.toUpperCase()); // a Fountain character cue is uppercase
        break;
      case 'parenthetical':
        lines.push(/^\(.*\)$/.test(text) ? text : `(${text})`);
        break;
      case 'dialogue':
        lines.push(text); // attaches under the preceding Character/Dialogue
        break;
      case 'transition': {
        const isTrans = /to:$/i.test(text) || text.startsWith('>');
        pushSpaced(isTrans ? text.toUpperCase() : `> ${text}`);
        break;
      }
      default: // Action / General / unknown
        pushSpaced(text);
        break;
    }
  }

  return { blocks: textToBlocks(lines.join('\n')), mode: 'screenplay' };
}

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

const DOCUMENT_ID_RE = /^[1-9]\d*$/;
const INCARNATION_RE = /^[a-f0-9]{32}$/i;
const REVISION_RE = /^[a-f0-9]{32}$/;
const SESSION_RE = /^[A-Za-z0-9_-]{8,110}$/;
const CONFLICT_ID_RE = /^main_conflict_[1-9]\d*$/;
const ERROR_CODE_RE = /^[a-z][a-z0-9_]*$/;
const ISO_TIMESTAMP_RE =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$/;
// Mirrors electron/import-file-limit.ts. A v1 manuscript conflict intentionally
// contains both the pending patch and merged document (2 × the 128 MiB pending
// payload limit), plus one MiB of compact-envelope overhead. A contract test
// keeps the independently compiled renderer/main constants synchronized.
export const MAX_LOGOSFORGE_BYTES = (2 * 128 * 1024 * 1024) + (1024 * 1024);
const MAX_BLOCKS = 250_000;
const MAX_MARKS_PER_BLOCK = 100_000;
const MAX_OUTLINE_ITEMS = 100_000;
const MAX_OUTLINE_DEPTH = 512;
const STABLE_ID_RE = /^[^\s\u0000-\u001f\u007f]{1,256}$/;
const SCREENPLAY_TYPES = new Set([
  'scene_heading', 'action', 'character', 'dialogue', 'parenthetical', 'transition',
  'section', 'synopsis', 'note', 'centered', 'lyrics', 'page_break', 'empty',
]);
const RECOVERY_MODES = new Set(['novel', 'screenplay', 'graphic_novel', 'stage_script', 'series']);

function invalidRecovery(detail: string): never {
  throw new ImportError(`Invalid LogosForge file: ${detail}`);
}

function recoveryRecord(value: unknown, label: string): Record<string, unknown> {
  return asRecord(value) ?? invalidRecovery(`${label} must be an object.`);
}

function recoveryString(value: unknown, label: string, allowEmpty = false): string {
  if (typeof value !== 'string' || (!allowEmpty && !value.length)) {
    invalidRecovery(`${label} must be a${allowEmpty ? '' : ' non-empty'} string.`);
  }
  return value as string;
}

function recoveryDocumentId(value: unknown): string {
  const documentId = recoveryString(value, 'document_id');
  if (!DOCUMENT_ID_RE.test(documentId)) invalidRecovery('document_id is not valid.');
  return documentId;
}

function recoveryStableId(value: unknown, label: string): string {
  const id = recoveryString(value, label);
  if (!STABLE_ID_RE.test(id)) invalidRecovery(`${label} is not a valid stable id.`);
  return id;
}

function recoveryMode(value: unknown, label: string): string {
  const mode = recoveryString(value, label);
  if (!RECOVERY_MODES.has(mode)) invalidRecovery(`${label} is not a supported Whiteboard mode.`);
  return mode === 'series' ? 'novel' : mode;
}

function recoveryTitle(value: unknown, label: string): string {
  return recoveryString(value, label, true);
}

function recoveryIncarnation(value: unknown): string {
  const incarnation = recoveryString(value, 'incarnation');
  if (!INCARNATION_RE.test(incarnation)) invalidRecovery('incarnation is not valid.');
  return incarnation.toLowerCase();
}

function recoveryRevision(value: unknown, label: string): string {
  const revision = recoveryString(value, label);
  if (!REVISION_RE.test(revision)) invalidRecovery(`${label} is not valid.`);
  return revision;
}

function recoveryTimestamp(value: unknown, label: string): string {
  const timestamp = recoveryString(value, label);
  if (!ISO_TIMESTAMP_RE.test(timestamp) || !Number.isFinite(Date.parse(timestamp))) {
    invalidRecovery(`${label} is not a valid timestamp.`);
  }
  return timestamp;
}

function recoveryVersion(value: unknown): void {
  if (value !== 1) invalidRecovery('version must be 1.');
}

function hasOnlyKeys(value: Record<string, unknown>, allowed: readonly string[], label: string): void {
  const allowedSet = new Set(allowed);
  const unexpected = Object.keys(value).find((key) => !allowedSet.has(key));
  if (unexpected) invalidRecovery(`${label} contains unsupported field "${unexpected}".`);
}

function parseBlocks(value: unknown, label: string): WhiteboardBlock[] {
  if (!Array.isArray(value)) invalidRecovery(`${label} must be an array.`);
  if (value.length > MAX_BLOCKS) invalidRecovery(`${label} contains too many blocks.`);
  const ids = new Set<string>();
  return value.map((raw, index): WhiteboardBlock => {
    const block = recoveryRecord(raw, `${label}[${index}]`);
    hasOnlyKeys(block, ['id', 'type', 'text', 'level', 'sp', 'marks'], `${label}[${index}]`);
    const id = recoveryStableId(block.id, `${label}[${index}].id`);
    if (ids.has(id)) invalidRecovery(`${label} contains duplicate block id "${id}".`);
    ids.add(id);
    const type = recoveryString(block.type, `${label}[${index}].type`);
    if (type.trim() !== type || type.length > 64) invalidRecovery(`${label}[${index}].type is not valid.`);
    const text = recoveryString(block.text, `${label}[${index}].text`, true);
    const parsed: WhiteboardBlock = { id, type, text };
    if (block.level !== undefined) {
      if (block.level !== null && (!Number.isSafeInteger(block.level) || Number(block.level) < 1 || Number(block.level) > 6)) {
        invalidRecovery(`${label}[${index}].level is not valid.`);
      }
      parsed.level = block.level as number | null;
    }
    if (block.sp !== undefined) {
      if (block.sp !== null && !SCREENPLAY_TYPES.has(block.sp as string)) {
        invalidRecovery(`${label}[${index}].sp is not valid.`);
      }
      parsed.sp = block.sp as string | null;
    }
    if (block.marks !== undefined) {
      if (!Array.isArray(block.marks)) invalidRecovery(`${label}[${index}].marks must be an array.`);
      if (block.marks.length > MAX_MARKS_PER_BLOCK) {
        invalidRecovery(`${label}[${index}].marks contains too many entries.`);
      }
      parsed.marks = block.marks.map((rawMark, markIndex) => {
        const mark = recoveryRecord(rawMark, `${label}[${index}].marks[${markIndex}]`);
        hasOnlyKeys(mark, ['type', 'from', 'to'], `${label}[${index}].marks[${markIndex}]`);
        if (mark.type !== 'bold' && mark.type !== 'italic') {
          invalidRecovery(`${label}[${index}].marks[${markIndex}].type is not valid.`);
        }
        if (
          !Number.isSafeInteger(mark.from)
          || !Number.isSafeInteger(mark.to)
          || Number(mark.from) < 0
          || Number(mark.to) <= Number(mark.from)
          || Number(mark.to) > text.length
        ) {
          invalidRecovery(`${label}[${index}].marks[${markIndex}] has invalid offsets.`);
        }
        return {
          type: mark.type as 'bold' | 'italic',
          from: mark.from as number,
          to: mark.to as number,
        };
      });
    }
    return parsed;
  });
}

const SETTINGS_ENUMS: Record<string, readonly unknown[]> = {
  narrativePerson: ['unspecified', 'first', 'third-limited', 'third-omniscient'],
  narrativeStyle: ['neutral', 'literary', 'commercial', 'cinematic', 'minimalist', 'lyrical'],
  narrativeRegister: ['neutral', 'formal', 'standard', 'colloquial', 'vernacular'],
  slangLevel: ['none', 'light', 'moderate', 'heavy'],
  sceneHeadingStyle: ['normal', 'bold', 'underline', 'bold-underline'],
  blankLinesBeforeScene: [1, 2],
  includeOutline: [true, false],
  typeface: ['courier-prime', 'courier', 'monospace'],
  showInvisibles: [true, false],
};

function parseSettings(value: unknown, label: string): Partial<DocumentSettings> {
  const settings = recoveryRecord(value, label);
  hasOnlyKeys(settings, Object.keys(SETTINGS_ENUMS), label);
  for (const [key, allowed] of Object.entries(SETTINGS_ENUMS)) {
    if (key in settings && !allowed.includes(settings[key])) {
      invalidRecovery(`${label}.${key} is not valid.`);
    }
  }
  return { ...settings } as Partial<DocumentSettings>;
}

function parseOutline(
  value: unknown,
  label: string,
  legacyTimestampFallback?: string,
): OutlineNode[] {
  if (!Array.isArray(value)) invalidRecovery(`${label} must be an array.`);
  if (value.length > MAX_OUTLINE_ITEMS) invalidRecovery(`${label} contains too many items.`);
  const ids = new Set<string>();
  const items = value.map((raw, index): OutlineNode => {
    const item = recoveryRecord(raw, `${label}[${index}]`);
    hasOnlyKeys(
      item,
      [
        'id', 'parentId', 'type', 'title', 'summary', 'order', 'collapsed', 'completed',
        'status', 'tags', 'colorLabel', 'linkedLineId', 'link', 'createdAt', 'updatedAt',
      ],
      `${label}[${index}]`,
    );
    const id = recoveryStableId(item.id, `${label}[${index}].id`);
    if (ids.has(id)) invalidRecovery(`${label} contains duplicate item id "${id}".`);
    ids.add(id);
    if (item.parentId !== null && (
      typeof item.parentId !== 'string'
      || !STABLE_ID_RE.test(item.parentId)
    )) {
      invalidRecovery(`${label}[${index}].parentId is not valid.`);
    }
    if (!(OUTLINE_TYPES as readonly unknown[]).includes(item.type)) {
      invalidRecovery(`${label}[${index}].type is not valid.`);
    }
    if (typeof item.order !== 'number' || !Number.isFinite(item.order)) {
      invalidRecovery(`${label}[${index}].order is not valid.`);
    }
    if (typeof item.collapsed !== 'boolean' || typeof item.completed !== 'boolean') {
      invalidRecovery(`${label}[${index}] has invalid state flags.`);
    }
    if (!(OUTLINE_STATUSES as readonly unknown[]).includes(item.status)) {
      invalidRecovery(`${label}[${index}].status is not valid.`);
    }
    if (!(OUTLINE_COLORS as readonly unknown[]).includes(item.colorLabel)) {
      invalidRecovery(`${label}[${index}].colorLabel is not valid.`);
    }
    if (!Array.isArray(item.tags) || item.tags.some((tag) =>
      typeof tag !== 'string' || !tag.length
    )) {
      invalidRecovery(`${label}[${index}].tags is not valid.`);
    }
    const title = recoveryString(item.title, `${label}[${index}].title`, true);
    const summary = recoveryString(item.summary, `${label}[${index}].summary`, true);
    const nodeTimestamp = (candidate: unknown, timestampLabel: string): string => {
      try {
        return recoveryTimestamp(candidate, timestampLabel);
      } catch (error) {
        if (legacyTimestampFallback && typeof candidate === 'string') {
          return legacyTimestampFallback;
        }
        throw error;
      }
    };
    const createdAt = nodeTimestamp(item.createdAt, `${label}[${index}].createdAt`);
    const updatedAt = nodeTimestamp(item.updatedAt, `${label}[${index}].updatedAt`);
    if (
      item.linkedLineId !== undefined
      && item.linkedLineId !== null
      && (typeof item.linkedLineId !== 'string' || !STABLE_ID_RE.test(item.linkedLineId))
    ) {
      invalidRecovery(`${label}[${index}].linkedLineId is not valid.`);
    }
    let link: OutlineNode['link'];
    if (item.link !== undefined && item.link !== null) {
      const rawLink = recoveryRecord(item.link, `${label}[${index}].link`);
      hasOnlyKeys(rawLink, ['blockIndex', 'quote', 'blockId'], `${label}[${index}].link`);
      if (!Number.isSafeInteger(rawLink.blockIndex) || Number(rawLink.blockIndex) < 0) {
        invalidRecovery(`${label}[${index}].link.blockIndex is not valid.`);
      }
      const quote = recoveryString(rawLink.quote, `${label}[${index}].link.quote`, true);
      if (
        rawLink.blockId !== undefined
        && (typeof rawLink.blockId !== 'string' || !STABLE_ID_RE.test(rawLink.blockId))
      ) {
        invalidRecovery(`${label}[${index}].link.blockId is not valid.`);
      }
      link = {
        blockIndex: rawLink.blockIndex as number,
        quote,
        ...(rawLink.blockId === undefined ? {} : { blockId: rawLink.blockId as string }),
      };
    } else if (item.link === null) {
      link = null;
    }
    return {
      id,
      parentId: item.parentId as string | null,
      type: item.type as OutlineNode['type'],
      title,
      summary,
      order: item.order,
      collapsed: item.collapsed,
      completed: item.completed,
      status: item.status as OutlineNode['status'],
      tags: [...item.tags] as string[],
      colorLabel: item.colorLabel as OutlineNode['colorLabel'],
      ...(item.linkedLineId === undefined ? {} : { linkedLineId: item.linkedLineId as string | null }),
      ...(item.link === undefined ? {} : { link }),
      createdAt,
      updatedAt,
    };
  });

  const byId = new Map(items.map((item) => [item.id, item]));
  for (const item of items) {
    if (item.parentId === item.id) invalidRecovery(`${label} item "${item.id}" cannot parent itself.`);
    if (item.parentId !== null && !ids.has(item.parentId)) {
      invalidRecovery(`${label} item "${item.id}" has a missing parent.`);
    }
    const seen = new Set<string>();
    let cursor: OutlineNode | undefined = item;
    let depth = 0;
    while (cursor && cursor.parentId !== null) {
      if (seen.has(cursor.id)) invalidRecovery(`${label} contains a parent cycle.`);
      seen.add(cursor.id);
      depth += 1;
      if (depth > MAX_OUTLINE_DEPTH) invalidRecovery(`${label} exceeds the maximum nesting depth.`);
      cursor = byId.get(cursor.parentId);
    }
  }
  // Old app builds tolerated negative/fractional/duplicate numeric order. Use
  // it only as a stable sort hint, then emit the current 0..n sibling invariant.
  const canonicalOrders = new Map<string, number>();
  const byParent = new Map<string | null, Array<{ item: OutlineNode; index: number }>>();
  items.forEach((item, index) => {
    const siblings = byParent.get(item.parentId) ?? [];
    siblings.push({ item, index });
    byParent.set(item.parentId, siblings);
  });
  for (const siblings of byParent.values()) {
    siblings
      .sort((left, right) => left.item.order - right.item.order || left.index - right.index)
      .forEach(({ item }, order) => canonicalOrders.set(item.id, order));
  }
  return items.map((item) => ({ ...item, order: canonicalOrders.get(item.id) as number }));
}

function deepEqual(left: unknown, right: unknown): boolean {
  if (Object.is(left, right)) return true;
  if (Array.isArray(left) || Array.isArray(right)) {
    return Array.isArray(left)
      && Array.isArray(right)
      && left.length === right.length
      && left.every((item, index) => deepEqual(item, right[index]));
  }
  const leftRecord = asRecord(left);
  const rightRecord = asRecord(right);
  if (!leftRecord || !rightRecord) return false;
  const leftKeys = Object.keys(leftRecord).sort();
  const rightKeys = Object.keys(rightRecord).sort();
  return leftKeys.length === rightKeys.length
    && leftKeys.every((key, index) => key === rightKeys[index] && deepEqual(leftRecord[key], rightRecord[key]));
}

function parseWhiteboardConflict(root: Record<string, unknown>): ImportResult {
  hasOnlyKeys(
    root,
    [
      'format', 'version', 'document_id', 'incarnation', 'base_revision',
      'exported_at', 'pending_patch', 'document',
    ],
    'root',
  );
  recoveryVersion(root.version);
  const documentId = recoveryDocumentId(root.document_id);
  const incarnation = recoveryIncarnation(root.incarnation);
  const baseRevision = recoveryRevision(root.base_revision, 'base_revision');
  const exportedAt = recoveryTimestamp(root.exported_at, 'exported_at');
  const doc = recoveryRecord(root.document, 'document');
  hasOnlyKeys(
    doc,
    ['id', 'incarnation', 'revision', 'viewRevision', 'title', 'mode', 'blocks', 'settings', 'updated_at'],
    'document',
  );
  if (recoveryDocumentId(doc.id) !== documentId) invalidRecovery('document.id does not match document_id.');
  if (recoveryIncarnation(doc.incarnation) !== incarnation) {
    invalidRecovery('document.incarnation does not match incarnation.');
  }
  if (recoveryRevision(doc.revision, 'document.revision') !== baseRevision) {
    invalidRecovery('document.revision does not match base_revision.');
  }
  if (doc.viewRevision !== undefined && (!Number.isSafeInteger(doc.viewRevision) || Number(doc.viewRevision) < 0)) {
    invalidRecovery('document.viewRevision is not valid.');
  }
  const title = recoveryTitle(doc.title, 'document.title');
  const mode = recoveryMode(doc.mode, 'document.mode');
  const blocks = parseBlocks(doc.blocks, 'document.blocks');
  const settings = parseSettings(doc.settings, 'document.settings');
  recoveryTimestamp(doc.updated_at, 'document.updated_at');

  const patch = recoveryRecord(root.pending_patch, 'pending_patch');
  hasOnlyKeys(patch, ['title', 'mode', 'blocks', 'settings'], 'pending_patch');
  if (!Object.keys(patch).length) invalidRecovery('pending_patch is empty.');
  const parsedPatch: Record<string, unknown> = {};
  if ('title' in patch) parsedPatch.title = recoveryTitle(patch.title, 'pending_patch.title');
  if ('mode' in patch) parsedPatch.mode = recoveryMode(patch.mode, 'pending_patch.mode');
  if ('blocks' in patch) parsedPatch.blocks = parseBlocks(patch.blocks, 'pending_patch.blocks');
  if ('settings' in patch) parsedPatch.settings = parseSettings(patch.settings, 'pending_patch.settings');
  const mergedValues: Record<string, unknown> = { title, mode, blocks, settings };
  for (const [key, value] of Object.entries(parsedPatch)) {
    if (!deepEqual(value, mergedValues[key])) {
      invalidRecovery(`pending_patch.${key} does not match the merged document.`);
    }
  }
  return {
    blocks,
    title,
    mode,
    settings,
    recovery: {
      format: WHITEBOARD_CONFLICT_FORMAT,
      scope: 'whiteboard',
      documentId,
      incarnation,
      sourceRevision: baseRevision,
      exportedAt,
    },
  };
}

function parseOutlineConflict(root: Record<string, unknown>): ImportResult {
  hasOnlyKeys(
    root,
    ['format', 'version', 'document_id', 'incarnation', 'base_revision', 'exported_at', 'items'],
    'root',
  );
  recoveryVersion(root.version);
  const documentId = recoveryDocumentId(root.document_id);
  const hasIncarnation = root.incarnation !== undefined;
  const hasBaseRevision = root.base_revision !== undefined;
  if (hasIncarnation !== hasBaseRevision) {
    invalidRecovery('legacy outline identity fields must either both be present or both be absent.');
  }
  const incarnation = hasIncarnation ? recoveryIncarnation(root.incarnation) : null;
  const baseRevision = hasBaseRevision
    ? recoveryRevision(root.base_revision, 'base_revision')
    : null;
  const exportedAt = recoveryTimestamp(root.exported_at, 'exported_at');
  return {
    blocks: [],
    outline: parseOutline(root.items, 'items', exportedAt),
    recovery: {
      format: OUTLINE_CONFLICT_FORMAT,
      scope: 'outline',
      documentId,
      incarnation,
      sourceRevision: baseRevision,
      exportedAt,
    },
  };
}

function parsePendingRecovery(root: Record<string, unknown>): ImportResult {
  hasOnlyKeys(root, ['format', 'version', 'exported_at', 'recovery'], 'root');
  recoveryVersion(root.version);
  const exportedAt = recoveryTimestamp(root.exported_at, 'exported_at');
  const recovery = recoveryRecord(root.recovery, 'recovery');
  hasOnlyKeys(
    recovery,
    ['conflictId', 'version', 'kind', 'documentId', 'incarnation', 'write', 'error'],
    'recovery',
  );
  const conflictId = recoveryString(recovery.conflictId, 'recovery.conflictId');
  if (conflictId.length > 64 || !CONFLICT_ID_RE.test(conflictId)) {
    invalidRecovery('recovery.conflictId is not valid.');
  }
  if (!Number.isSafeInteger(recovery.version) || Number(recovery.version) < 1) {
    invalidRecovery('recovery.version is not valid.');
  }
  if (recovery.kind !== 'whiteboard' && recovery.kind !== 'outline') {
    invalidRecovery('recovery.kind is not valid.');
  }
  const kind = recovery.kind;
  const documentId = recoveryDocumentId(recovery.documentId);
  const incarnation = recoveryIncarnation(recovery.incarnation);
  const write = recoveryRecord(recovery.write, 'recovery.write');
  hasOnlyKeys(
    write,
    ['kind', 'documentId', 'incarnation', 'resourceRevision', 'revision', 'sessionId', 'payload'],
    'recovery.write',
  );
  if (write.kind !== kind) invalidRecovery('recovery.write.kind does not match recovery.kind.');
  if (recoveryDocumentId(write.documentId) !== documentId) {
    invalidRecovery('recovery.write.documentId does not match recovery.documentId.');
  }
  if (recoveryIncarnation(write.incarnation) !== incarnation) {
    invalidRecovery('recovery.write.incarnation does not match recovery.incarnation.');
  }
  const sourceRevision = recoveryRevision(write.resourceRevision, 'recovery.write.resourceRevision');
  if (!Number.isSafeInteger(write.revision) || Number(write.revision) < 1) {
    invalidRecovery('recovery.write.revision is not valid.');
  }
  const sessionId = recoveryString(write.sessionId, 'recovery.write.sessionId');
  if (!SESSION_RE.test(sessionId)) invalidRecovery('recovery.write.sessionId is not valid.');

  const error = recoveryRecord(recovery.error, 'recovery.error');
  hasOnlyKeys(
    error,
    ['code', 'status', 'message', 'currentRevision', 'currentEtag'],
    'recovery.error',
  );
  const errorCode = recoveryString(error.code, 'recovery.error.code');
  if (!ERROR_CODE_RE.test(errorCode) || errorCode.length > 128) {
    invalidRecovery('recovery.error.code is not valid.');
  }
  if (!Number.isSafeInteger(error.status) || Number(error.status) < 400 || Number(error.status) > 499) {
    invalidRecovery('recovery.error.status is not valid.');
  }
  const errorMessage = recoveryString(error.message, 'recovery.error.message');
  if (errorMessage.length > 8192) invalidRecovery('recovery.error.message is too long.');
  if (errorCode === 'revision_conflict') {
    if (error.status !== 409) invalidRecovery('revision conflict status must be 409.');
    const currentRevision = recoveryRevision(error.currentRevision, 'recovery.error.currentRevision');
    const expectedEtag = `"lfwb:${kind}:${incarnation}:${currentRevision}"`;
    if (error.currentEtag !== expectedEtag) {
      invalidRecovery('recovery.error.currentEtag does not match its revision.');
    }
  } else if (error.currentRevision !== undefined || error.currentEtag !== undefined) {
    invalidRecovery('non-conflict recovery has unexpected revision validators.');
  }

  const payload = recoveryRecord(write.payload, 'recovery.write.payload');
  const descriptor: RecoveryImportDescriptor = {
    format: PENDING_DOCUMENT_RECOVERY_FORMAT,
    scope: kind,
    documentId,
    incarnation,
    sourceRevision,
    exportedAt,
  };
  if (kind === 'outline') {
    hasOnlyKeys(payload, ['items'], 'recovery.write.payload');
    if (Object.keys(payload).length !== 1) {
      invalidRecovery('outline recovery payload must contain only items.');
    }
    return {
      blocks: [],
      outline: parseOutline(payload.items, 'recovery.write.payload.items', exportedAt),
      recovery: descriptor,
    };
  }

  hasOnlyKeys(payload, ['title', 'mode', 'blocks', 'settings'], 'recovery.write.payload');
  if (!['title', 'mode', 'blocks', 'settings'].every((key) => key in payload)) {
    invalidRecovery('whiteboard recovery payload is not a complete document snapshot.');
  }
  return {
    title: recoveryTitle(payload.title, 'recovery.write.payload.title'),
    mode: recoveryMode(payload.mode, 'recovery.write.payload.mode'),
    blocks: parseBlocks(payload.blocks, 'recovery.write.payload.blocks'),
    settings: parseSettings(payload.settings, 'recovery.write.payload.settings'),
    recovery: descriptor,
  };
}

/** Source identity is provenance, never write authority. Mismatches are allowed
 * only after the caller presents the additional high-signal confirmation. */
export function recoveryImportIdentityRelationship(
  recovery: RecoveryImportDescriptor,
  activeDocumentId: string,
  activeIncarnation: string,
): RecoveryIdentityRelationship {
  if (!recovery.incarnation) return 'unverifiable';
  if (activeDocumentId !== recovery.documentId) return 'different-document';
  if (activeIncarnation.toLowerCase() !== recovery.incarnation) return 'different-incarnation';
  return 'same';
}

/** Recheck the captured target after asynchronous pickers/dialogs and after the
 * tracked-operation lease is acquired. Source metadata is deliberately absent. */
export function assertRecoveryImportTargetStillActive(
  target: RecoveryImportTarget,
  activeDocumentId: string,
  activeIncarnation: string,
): void {
  if (
    !target.documentId
    || !target.incarnation
    || target.documentId !== activeDocumentId
    || target.incarnation !== activeIncarnation
  ) {
    throw new ImportError(
      'The active document changed while recovery confirmation was open. Nothing was restored; try again in the intended document.',
    );
  }
}

/**
 * Parse + validate a LogosForge JSON file. Tolerant of two shapes:
 *   - the full envelope ({format, version, document:{content|blocks,…}, outline,…})
 *   - the raw JSON export ({title, mode, blocks})
 */
export function parseLogosforge(jsonText: string): ImportResult {
  if (
    jsonText.length > MAX_LOGOSFORGE_BYTES
    || new TextEncoder().encode(jsonText).byteLength > MAX_LOGOSFORGE_BYTES
  ) {
    throw new ImportError('This LogosForge file is too large to import safely.');
  }
  let root: unknown;
  try {
    root = JSON.parse(jsonText);
  } catch {
    throw new ImportError('This file is not valid JSON.');
  }
  const r = asRecord(root);
  if (!r) throw new ImportError('This is not a valid LogosForge document.');
  if (r.format === WHITEBOARD_CONFLICT_FORMAT) return parseWhiteboardConflict(r);
  if (r.format === OUTLINE_CONFLICT_FORMAT) return parseOutlineConflict(r);
  if (r.format === PENDING_DOCUMENT_RECOVERY_FORMAT) return parsePendingRecovery(r);
  if (typeof r.format === 'string' && r.format !== LOGOSFORGE_FORMAT) {
    throw new ImportError(`Unrecognized format "${String(r.format)}".`);
  }

  const doc = asRecord(r.document) ?? r; // raw export has no "document" wrapper
  let blocks: WhiteboardBlock[] | null = null;
  if (Array.isArray(doc.blocks)) {
    blocks = parseBlocks(doc.blocks, 'document.blocks');
  } else if (typeof doc.content === 'string') {
    blocks = textToBlocks(doc.content);
  }
  if (!blocks) throw new ImportError('No document content found in this LogosForge file.');

  const result: ImportResult = { blocks };
  if (typeof doc.mode === 'string') result.mode = doc.mode;
  if (typeof doc.title === 'string') result.title = doc.title;
  if (doc.settings !== undefined) result.settings = parseSettings(doc.settings, 'document.settings');
  if (r.outline !== undefined) result.outline = parseOutline(r.outline, 'outline');
  const psyke = asRecord(r.psyke);
  if (psyke && Array.isArray(psyke.elements)) {
    result.psyke = { elements: psyke.elements };
  }
  return result;
}

// --- export ----------------------------------------------------------------

/** A comment, flattened for export (the files feature owns its own DTO rather
 * than depending on the comments feature). */
export interface ExportComment {
  quote: string;
  body: string;
  resolved: boolean;
  blockIndex: number;
  createdAt?: string;
}

export interface ExportPayload {
  title: string;
  mode: string;
  blocks: WhiteboardBlock[];
  settings: DocumentSettings;
  outline: OutlineNode[];
  psyke?: { elements: unknown[] };
  comments?: ExportComment[];
}

export function buildLogosforgeEnvelope(
  p: ExportPayload,
  nowIso: string = new Date().toISOString(),
): Record<string, unknown> {
  return {
    format: LOGOSFORGE_FORMAT,
    version: LOGOSFORGE_VERSION,
    document: {
      title: p.title,
      mode: p.mode,
      content: blocksToText(p.blocks),
      settings: p.settings,
    },
    outline: p.outline ?? [],
    psyke: p.psyke ?? { elements: [] },
    metadata: {
      createdAt: nowIso,
      updatedAt: nowIso,
      exportedAt: nowIso,
    },
  };
}

const HTML_ESCAPE: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
};
function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => HTML_ESCAPE[c]);
}

function buildHtml(p: ExportPayload): string {
  const body = p.blocks
    .map((b) => {
      if (b.type === 'heading') {
        const lvl = Math.min(3, Math.max(1, b.level ?? 1));
        return `    <h${lvl}>${escapeHtml(b.text)}</h${lvl}>`;
      }
      const t = b.text.trim();
      return t ? `    <p>${escapeHtml(b.text)}</p>` : '';
    })
    .filter(Boolean)
    .join('\n');
  const mono = p.mode === 'screenplay' || p.mode === 'stage_script';
  const font = mono
    ? `"Courier Prime", "Courier New", monospace`
    : `Georgia, "Times New Roman", serif`;
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>${escapeHtml(p.title)}</title>
  <style>
    body { max-width: 42rem; margin: 2rem auto; padding: 0 1rem;
           font-family: ${font}; line-height: 1.5; color: #1a1a1a; }
    h1, h2, h3 { line-height: 1.25; }
    p { white-space: pre-wrap; }
  </style>
</head>
<body>
  <article>
${body}
  </article>
</body>
</html>
`;
}

/** The nearest preceding heading for a block (a human-readable location), or ''. */
function nearestHeading(blocks: WhiteboardBlock[], blockIndex: number): string {
  for (let i = Math.min(blockIndex, blocks.length - 1); i >= 0; i -= 1) {
    if (blocks[i]?.type === 'heading' && blocks[i].text.trim()) return blocks[i].text.trim();
  }
  return '';
}

/**
 * A portable Markdown report of the document's comments (so a reviewer's notes
 * can leave the app). Open and resolved are grouped; each entry shows its location
 * (nearest heading, else paragraph number), the quoted span, and the note body.
 */
export function buildCommentsReport(p: ExportPayload, nowIso: string = new Date().toISOString()): string {
  const comments = p.comments ?? [];
  const open = comments.filter((c) => !c.resolved);
  const resolved = comments.filter((c) => c.resolved);
  const out: string[] = [`# Comments — ${p.title || 'Untitled'}`, ''];
  out.push(`${comments.length} comment${comments.length === 1 ? '' : 's'} · ${open.length} open · ${resolved.length} resolved · exported ${nowIso.slice(0, 10)}`, '');
  if (comments.length === 0) {
    out.push('_No comments._', '');
    return out.join('\n');
  }
  const section = (heading: string, items: ExportComment[]) => {
    if (!items.length) return;
    out.push(`## ${heading}`, '');
    items.forEach((c, i) => {
      const loc = nearestHeading(p.blocks, c.blockIndex) || `¶ ${c.blockIndex + 1}`;
      out.push(`### ${i + 1}. ${loc}`, '');
      out.push(`> ${(c.quote || '').trim() || '(no quoted text)'}`, '');
      out.push((c.body || '').trim() || '_(empty note)_', '');
    });
  };
  section('Open', open);
  section('Resolved', resolved);
  return out.join('\n');
}

/** Convert the current document to a string in the chosen export format. */
export function buildExport(format: ExportFormatId, p: ExportPayload): string {
  switch (format) {
    case 'txt':
    case 'md':
    case 'fountain':
      return blocksToText(p.blocks);
    case 'json':
      return JSON.stringify({ title: p.title, mode: p.mode, blocks: p.blocks }, null, 2);
    case 'logosforge':
      return JSON.stringify(buildLogosforgeEnvelope(p), null, 2);
    case 'html':
      return buildHtml(p);
    case 'comments':
      return buildCommentsReport(p);
    default:
      return blocksToText(p.blocks);
  }
}

/** Suggested export filename: reuse the current stem, swap the extension. */
export function suggestedExportName(baseLabel: string, ext: string): string {
  const stem = baseLabel.replace(/\.[^./\\]+$/, '').trim() || 'untitled';
  return `${stem}.${ext}`;
}
