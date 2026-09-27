import { freshBlockIds } from '../whiteboard/blockIdentity';
import type { WhiteboardBlock } from '../whiteboard/types';
import type { DrafterPage, WritingSurface } from './types';

export const MANUSCRIPT_TAB_ID = 'manuscript';
export const DRAFTER_TITLE_MAX = 240;
export const DRAFTER_MAX_PAGES = 256;
export const DRAFTER_MAX_BLOCKS_PER_PAGE = 20_000;
export const DRAFTER_MAX_BLOCKS_TOTAL = 100_000;
export const DRAFTER_MAX_TEXT_CHARS_TOTAL = 32_000_000;
export const DRAFTER_MAX_MARKS_PER_PAGE = 20_000;
export const DRAFTER_MAX_MARKS_TOTAL = 100_000;
export const DRAFTER_MAX_MARK_METADATA_CHARS_PER_PAGE = 1_000_000;
export const DRAFTER_MAX_MARK_METADATA_CHARS_TOTAL = 8_000_000;
export const DRAFTER_MAX_SERIALIZED_BYTES_TOTAL = 96 * 1024 * 1024;

const DRAFTER_PAGE_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const DRAFTER_MAX_BLOCK_ID_CHARS = 128;
const DRAFTER_MAX_BLOCK_TYPE_CHARS = 64;
const DRAFTER_MAX_BLOCK_SP_CHARS = 64;
const DRAFT_TAB_PREFIX = 'draft:';

const BLANK_BLOCK: WhiteboardBlock = { id: 'draft-blank', type: 'paragraph', text: '' };

export function newDrafterPageId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `draft-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

export function normalizeDrafterTitle(value: string, fallback = 'Untitled draft'): string {
  return (value.trim() || fallback).slice(0, DRAFTER_TITLE_MAX);
}

export function createDrafterPage(title: string, blocks?: WhiteboardBlock[]): DrafterPage {
  const now = new Date().toISOString();
  const source = blocks?.length ? blocks : [BLANK_BLOCK];
  const ids = freshBlockIds(source.length);
  return {
    id: newDrafterPageId(),
    title: normalizeDrafterTitle(title),
    blocks: source.map((block, index) => ({ ...block, id: ids[index] })),
    created_at: now,
    updated_at: now,
  };
}

export function renameDrafterPage(
  pages: readonly DrafterPage[],
  id: string,
  title: string,
  updatedAt = new Date().toISOString(),
): DrafterPage[] {
  return pages.map((page) => page.id === id
    ? { ...page, title: normalizeDrafterTitle(title), updated_at: updatedAt }
    : page);
}

export function removeDrafterPage(
  pages: readonly DrafterPage[],
  id: string,
): DrafterPage[] {
  return pages.filter((page) => page.id !== id);
}

export function replaceDrafterPageBlocks(
  pages: readonly DrafterPage[],
  id: string,
  blocks: WhiteboardBlock[],
  updatedAt = new Date().toISOString(),
): DrafterPage[] {
  return pages.map((page) => page.id === id
    ? { ...page, blocks, updated_at: updatedAt }
    : page);
}

export function reconcileWritingSurface(
  surface: WritingSurface,
  pages: readonly DrafterPage[],
): WritingSurface {
  if (surface.kind === 'draft' && !pages.some((page) => page.id === surface.pageId)) {
    return { kind: 'manuscript' };
  }
  return surface;
}

export function writingSurfaceTabId(surface: WritingSurface): string {
  return surface.kind === 'manuscript' ? MANUSCRIPT_TAB_ID : `${DRAFT_TAB_PREFIX}${surface.pageId}`;
}

export function writingSurfaceTabDomId(surface: WritingSurface): string {
  return surface.kind === 'manuscript'
    ? 'writing-tab-manuscript'
    : `writing-tab-draft-${surface.pageId}`;
}

function markMetadataCharacters(mark: NonNullable<WhiteboardBlock['marks']>[number]): number {
  // Python validates canonical, sorted-key JSON. InlineMark has a closed schema,
  // so spelling the sorted shape here gives the same character count.
  return JSON.stringify({ from: mark.from, to: mark.to, type: mark.type }).length;
}

function serializedSnapshotBytes(pages: readonly DrafterPage[]): number {
  // Mirror Pydantic's model_dump payload, including block defaults that are not
  // necessarily present on the renderer object, before measuring UTF-8 bytes.
  const normalizedPages = pages.map((page) => ({
    id: page.id,
    title: page.title,
    blocks: page.blocks.map((block) => ({
      id: block.id,
      type: block.type,
      text: block.text,
      level: block.level ?? null,
      sp: block.sp ?? null,
      marks: block.marks ?? null,
    })),
    created_at: page.created_at,
    updated_at: page.updated_at,
  }));
  return new TextEncoder().encode(JSON.stringify({ pages: normalizedPages })).byteLength;
}

/**
 * Validate a complete Drafter snapshot before it enters the retained autosave
 * queue. This intentionally mirrors the backend collection limits so an
 * invalid local edit cannot become a sticky, unrecoverable 422 conflict.
 */
export function validateDrafterPages(pages: readonly DrafterPage[]): string | null {
  if (pages.length > DRAFTER_MAX_PAGES) return `Drafter supports at most ${DRAFTER_MAX_PAGES} pages.`;

  const ids = new Set<string>();
  let blockCount = 0;
  let textCharacters = 0;
  let markCount = 0;
  let markMetadataTotal = 0;

  for (const page of pages) {
    if (!DRAFTER_PAGE_ID_RE.test(page.id)) return 'A Drafter page has an invalid id.';
    if (ids.has(page.id)) return `Drafter page id "${page.id}" is duplicated.`;
    ids.add(page.id);
    if (!page.title.trim() || page.title.length > DRAFTER_TITLE_MAX) {
      return `Drafter page "${page.id}" has an invalid title.`;
    }
    if (
      page.created_at.length > 64
      || page.updated_at.length > 64
      || !Number.isFinite(Date.parse(page.created_at))
      || !Number.isFinite(Date.parse(page.updated_at))
      || !/(?:Z|[+-]\d{2}:\d{2})$/i.test(page.created_at)
      || !/(?:Z|[+-]\d{2}:\d{2})$/i.test(page.updated_at)
    ) return `Drafter page "${page.title}" has an invalid timestamp.`;
    if (page.blocks.length > DRAFTER_MAX_BLOCKS_PER_PAGE) {
      return `Drafter page "${page.title}" contains too many blocks.`;
    }

    blockCount += page.blocks.length;
    let pageTextCharacters = 0;
    let pageMarkCount = 0;
    let pageMarkMetadata = 0;
    for (const block of page.blocks) {
      if (!block.id || block.id.length > DRAFTER_MAX_BLOCK_ID_CHARS) {
        return `Drafter page "${page.title}" contains an invalid block id.`;
      }
      if (!block.type || block.type.length > DRAFTER_MAX_BLOCK_TYPE_CHARS) {
        return `Drafter page "${page.title}" contains an invalid block type.`;
      }
      if (block.sp != null && block.sp.length > DRAFTER_MAX_BLOCK_SP_CHARS) {
        return `Drafter page "${page.title}" contains an invalid screenplay type.`;
      }
      pageTextCharacters += block.text.length;
      const marks = block.marks ?? [];
      pageMarkCount += marks.length;
      for (const mark of marks) pageMarkMetadata += markMetadataCharacters(mark);
    }
    if (pageTextCharacters > DRAFTER_MAX_TEXT_CHARS_TOTAL) {
      return `Drafter page "${page.title}" contains too much text.`;
    }
    if (pageMarkCount > DRAFTER_MAX_MARKS_PER_PAGE) {
      return `Drafter page "${page.title}" contains too many inline marks.`;
    }
    if (pageMarkMetadata > DRAFTER_MAX_MARK_METADATA_CHARS_PER_PAGE) {
      return `Drafter page "${page.title}" contains too much inline-mark metadata.`;
    }
    textCharacters += pageTextCharacters;
    markCount += pageMarkCount;
    markMetadataTotal += pageMarkMetadata;
  }

  if (blockCount > DRAFTER_MAX_BLOCKS_TOTAL) return 'Drafter contains too many blocks.';
  if (textCharacters > DRAFTER_MAX_TEXT_CHARS_TOTAL) return 'Drafter contains too much text.';
  if (markCount > DRAFTER_MAX_MARKS_TOTAL) return 'Drafter contains too many inline marks.';
  if (markMetadataTotal > DRAFTER_MAX_MARK_METADATA_CHARS_TOTAL) {
    return 'Drafter contains too much inline-mark metadata.';
  }
  if (serializedSnapshotBytes(pages) > DRAFTER_MAX_SERIALIZED_BYTES_TOTAL) {
    return 'Drafter exceeds the desktop recovery safety limit.';
  }
  return null;
}

export type DocumentPrintRoute = 'screenplay-data' | 'active-manuscript' | 'switch-to-manuscript';

/** PDF never treats a Drafter page as the project's canonical document. */
export function documentPrintRoute(mode: string, surface: WritingSurface): DocumentPrintRoute {
  if (mode === 'screenplay') return 'screenplay-data';
  return surface.kind === 'manuscript' ? 'active-manuscript' : 'switch-to-manuscript';
}

export function nextTabIndex(
  current: number,
  key: string,
  count: number,
): number | null {
  if (count < 1) return null;
  if (key === 'Home') return 0;
  if (key === 'End') return count - 1;
  if (key === 'ArrowLeft') return (current - 1 + count) % count;
  if (key === 'ArrowRight') return (current + 1) % count;
  return null;
}
