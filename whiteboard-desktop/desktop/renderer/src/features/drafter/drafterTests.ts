import {
  createDrafterPage,
  documentPrintRoute,
  DRAFTER_MAX_PAGES,
  DRAFTER_TITLE_MAX,
  nextTabIndex,
  normalizeDrafterTitle,
  reconcileWritingSurface,
  removeDrafterPage,
  renameDrafterPage,
  replaceDrafterPageBlocks,
  validateDrafterPages,
  writingSurfaceTabDomId,
  writingSurfaceTabId,
} from './drafterModel';
import { getDrafterPages, putDrafterPages } from './drafterApi';
import {
  installResourceRevision,
  resetResourceRevisionsForTests,
  resourceEtag,
} from '../../api/resourceRevision';
import type { DrafterPage } from './types';

let passed = 0;
const failures: string[] = [];

function test(name: string, run: () => void): void {
  try {
    run();
    passed += 1;
  } catch (error) {
    failures.push(`${name}: ${error instanceof Error ? error.message : String(error)}`);
  }
}

async function asyncTest(name: string, run: () => Promise<void>): Promise<void> {
  try {
    await run();
    passed += 1;
  } catch (error) {
    failures.push(`${name}: ${error instanceof Error ? error.message : String(error)}`);
  }
}

const incarnation = '0123456789abcdef0123456789abcdef';
const revision1 = '11111111111111111111111111111111';
const revision2 = '22222222222222222222222222222222';

function page(id: string, title = id): DrafterPage {
  return {
    id,
    title,
    blocks: [{ id: `${id}-block`, type: 'paragraph', text: `${title} text` }],
    created_at: '2026-01-01T00:00:00.000Z',
    updated_at: '2026-01-01T00:00:00.000Z',
  };
}

test('new pages normalize titles and copy imported blocks under fresh ids', () => {
  const imported = [
    { id: 'source-1', type: 'heading1', text: 'Scene heading' },
    { id: 'source-2', type: 'paragraph', text: 'Draft prose' },
  ];
  const created = createDrafterPage('  Scene sketch  ', imported);
  if (created.title !== 'Scene sketch') throw new Error(`Unexpected title ${created.title}`);
  if (created.blocks.map((block) => block.text).join('|') !== 'Scene heading|Draft prose') {
    throw new Error('Imported text was not preserved');
  }
  if (created.blocks.some((block, index) => block.id === imported[index].id)) {
    throw new Error('Imported block identities leaked into the project');
  }
  if (!created.created_at || created.updated_at !== created.created_at) {
    throw new Error('New page timestamps were not initialized together');
  }
});

test('blank and oversized titles have deterministic safe names', () => {
  if (normalizeDrafterTitle('   ') !== 'Untitled draft') throw new Error('Blank title has no fallback');
  if (normalizeDrafterTitle('x'.repeat(DRAFTER_TITLE_MAX + 4)).length !== DRAFTER_TITLE_MAX) {
    throw new Error('Title limit was not enforced');
  }
});

test('rename, editor updates, and delete only mutate the addressed page', () => {
  const before = [page('one'), page('two')];
  const renamed = renameDrafterPage(before, 'two', '  New name ', '2026-02-01T00:00:00.000Z');
  if (renamed[0] !== before[0] || renamed[1].title !== 'New name') {
    throw new Error('Rename changed the wrong page');
  }
  const blocks = [{ id: 'new-block', type: 'paragraph', text: 'New draft' }];
  const edited = replaceDrafterPageBlocks(renamed, 'two', blocks, '2026-03-01T00:00:00.000Z');
  if (edited[0] !== renamed[0] || edited[1].blocks !== blocks) {
    throw new Error('Editor update changed the wrong page');
  }
  const removed = removeDrafterPage(edited, 'two');
  if (removed.length !== 1 || removed[0].id !== 'one') throw new Error('Delete removed the wrong page');
});

test('missing draft surfaces return to the permanent manuscript tab', () => {
  const present = reconcileWritingSurface({ kind: 'draft', pageId: 'one' }, [page('one')]);
  const missing = reconcileWritingSurface({ kind: 'draft', pageId: 'gone' }, [page('one')]);
  if (present.kind !== 'draft' || missing.kind !== 'manuscript') {
    throw new Error('Writing surface reconciliation is unsafe');
  }
});

test('tab keys wrap and Home/End target stable endpoints', () => {
  const actual = [
    nextTabIndex(0, 'ArrowLeft', 3),
    nextTabIndex(2, 'ArrowRight', 3),
    nextTabIndex(1, 'Home', 3),
    nextTabIndex(1, 'End', 3),
    nextTabIndex(1, 'Enter', 3),
  ];
  if (JSON.stringify(actual) !== JSON.stringify([2, 0, 0, 2, null])) {
    throw new Error(`Unexpected tab navigation ${JSON.stringify(actual)}`);
  }
});

test('a backend-valid draft named manuscript cannot collide with the permanent tab', () => {
  const manuscript = { kind: 'manuscript' } as const;
  const draft = { kind: 'draft', pageId: 'manuscript' } as const;
  if (writingSurfaceTabId(manuscript) === writingSurfaceTabId(draft)) {
    throw new Error('Logical tab ids collide');
  }
  if (writingSurfaceTabDomId(manuscript) === writingSurfaceTabDomId(draft)) {
    throw new Error('DOM tab ids collide');
  }
});

test('the 256-page boundary is accepted and page 257 is rejected before autosave', () => {
  const maximum = Array.from({ length: DRAFTER_MAX_PAGES }, (_, index) => page(`page-${index}`));
  const atLimit = validateDrafterPages(maximum);
  if (atLimit !== null) throw new Error(`Page 256 should be valid: ${atLimit}`);
  const overLimit = validateDrafterPages([...maximum, page('page-over-limit')]);
  if (!overLimit?.includes(String(DRAFTER_MAX_PAGES))) {
    throw new Error(`Page 257 was not rejected: ${String(overLimit)}`);
  }
});

test('PDF routing never prints a Drafter page as the canonical prose document', () => {
  if (documentPrintRoute('novel', { kind: 'draft', pageId: 'scene' }) !== 'switch-to-manuscript') {
    throw new Error('Prose printing did not route through the manuscript');
  }
  if (documentPrintRoute('novel', { kind: 'manuscript' }) !== 'active-manuscript') {
    throw new Error('Manuscript prose printing should use the active DOM');
  }
  if (documentPrintRoute('screenplay', { kind: 'draft', pageId: 'scene' }) !== 'screenplay-data') {
    throw new Error('Screenplay printing should use canonical serialized blocks');
  }
});

await asyncTest('GET scopes Drafter pages to the document and validates the response revision', async () => {
  resetResourceRevisionsForTests();
  const originalFetch = globalThis.fetch;
  let requestUrl = '';
  let incarnationHeader = '';
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    requestUrl = String(input);
    incarnationHeader = new Headers(init?.headers).get('X-LogosForge-Document-Incarnation') ?? '';
    return new Response(JSON.stringify({ pages: [page('one')], revision: revision1 }), {
      status: 200,
      headers: { 'Content-Type': 'application/json', ETag: resourceEtag('drafter', incarnation, revision1) },
    });
  }) as typeof fetch;
  try {
    const result = await getDrafterPages('http://127.0.0.1:8777', 'project 7', incarnation);
    if (!requestUrl.endsWith('/api/drafter/pages?doc=project%207')) throw new Error(requestUrl);
    if (incarnationHeader !== incarnation || result.pages[0].id !== 'one') {
      throw new Error('GET lost document identity or page data');
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
});

await asyncTest('PUT sends a complete conditional page snapshot without manuscript fields', async () => {
  resetResourceRevisionsForTests();
  installResourceRevision('drafter', '7', incarnation, revision1);
  const originalFetch = globalThis.fetch;
  let request: RequestInit | undefined;
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    request = init;
    return new Response(JSON.stringify({ pages: [page('one')], revision: revision2 }), {
      status: 200,
      headers: { 'Content-Type': 'application/json', ETag: resourceEtag('drafter', incarnation, revision2) },
    });
  }) as typeof fetch;
  try {
    await putDrafterPages('http://127.0.0.1:8777', '7', incarnation, [page('one')], revision1);
    const headers = new Headers(request?.headers);
    const body = JSON.parse(String(request?.body)) as Record<string, unknown>;
    if (request?.method !== 'PUT') throw new Error('PUT method missing');
    if (headers.get('If-Match') !== resourceEtag('drafter', incarnation, revision1)) {
      throw new Error('Conditional validator missing');
    }
    if (!Array.isArray(body.pages) || 'blocks' in body || 'title' in body) {
      throw new Error('Drafter write was mixed with the manuscript payload');
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
});

for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} Drafter test(s) failed`);
console.log(`DRAFTER TESTS: PASS (${passed})`);
