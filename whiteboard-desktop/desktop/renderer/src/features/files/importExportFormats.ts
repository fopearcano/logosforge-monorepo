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

import type { OutlineNode } from '../outline/outlineModel';
import type { DocumentSettings } from '../whiteboard/documentSettings';
import type { WhiteboardBlock } from '../whiteboard/types';
import { blocksToText, textToBlocks } from './fileSerialize';

export const LOGOSFORGE_FORMAT = 'logosforge-whiteboard';
export const LOGOSFORGE_VERSION = '1.0';

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

/**
 * Parse + validate a LogosForge JSON file. Tolerant of two shapes:
 *   - the full envelope ({format, version, document:{content|blocks,…}, outline,…})
 *   - the raw JSON export ({title, mode, blocks})
 */
export function parseLogosforge(jsonText: string): ImportResult {
  let root: unknown;
  try {
    root = JSON.parse(jsonText);
  } catch {
    throw new ImportError('This file is not valid JSON.');
  }
  const r = asRecord(root);
  if (!r) throw new ImportError('This is not a valid LogosForge document.');
  if (typeof r.format === 'string' && r.format !== LOGOSFORGE_FORMAT) {
    throw new ImportError(`Unrecognized format "${String(r.format)}".`);
  }

  const doc = asRecord(r.document) ?? r; // raw export has no "document" wrapper
  let blocks: WhiteboardBlock[] | null = null;
  if (Array.isArray(doc.blocks)) {
    blocks = doc.blocks as WhiteboardBlock[];
  } else if (typeof doc.content === 'string') {
    blocks = textToBlocks(doc.content);
  }
  if (!blocks) throw new ImportError('No document content found in this LogosForge file.');

  const result: ImportResult = { blocks };
  if (typeof doc.mode === 'string') result.mode = doc.mode;
  if (typeof doc.title === 'string') result.title = doc.title;
  const settings = asRecord(doc.settings);
  if (settings) result.settings = settings as Partial<DocumentSettings>;
  if (Array.isArray(r.outline)) result.outline = r.outline as OutlineNode[];
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
