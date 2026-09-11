/** Whiteboard `.lfbundle` parser + Pro import orchestration tests. */

import type { ApiClient } from '../src/adapters/api';
import {
  BUNDLE_FORMAT,
  importProjectBundle,
  parseProjectBundle,
  type ProjectBundle,
} from '../src/adapters/projectBundle';

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: boolean): void => {
  if (condition) passed += 1;
  else failures.push(label);
};

function expectParseError(label: string, value: string, message: string): void {
  try {
    parseProjectBundle(value);
    failures.push(label);
  } catch (error) {
    check(label, error instanceof Error && error.message === message);
  }
}

const minimal = JSON.stringify({
  format: BUNDLE_FORMAT,
  version: '1',
  project: { title: 'Minimal', mode: 'novel', manuscript: { blocks: [] } },
});
check('minimal valid bundle parses', parseProjectBundle(minimal).project?.title === 'Minimal');
expectParseError('invalid JSON rejected', '{', "That file isn't valid JSON.");
expectParseError('wrong format rejected', '{}', "That isn't a LogosForge project bundle (.lfbundle).");
expectParseError(
  'non-object project rejected',
  JSON.stringify({ format: BUNDLE_FORMAT, project: [] }),
  'This bundle has no project data.',
);
expectParseError(
  'missing manuscript rejected before project creation',
  JSON.stringify({ format: BUNDLE_FORMAT, project: {} }),
  'This bundle has no manuscript block list.',
);
expectParseError(
  'invalid manuscript row rejected',
  JSON.stringify({ format: BUNDLE_FORMAT, project: { manuscript: { blocks: ['bad'] } } }),
  'This bundle contains an invalid manuscript block.',
);
expectParseError(
  'invalid optional section rejected',
  JSON.stringify({
    format: BUNDLE_FORMAT,
    project: { manuscript: { blocks: [] }, outline: {} },
  }),
  'This bundle has an invalid outline section.',
);

const psykeCalls: Array<{ projectId: number; body: Record<string, unknown> }> = [];
const outlineCalls: Array<{ projectId: number; body: Record<string, unknown> }> = [];
const settingsCalls: Array<Record<string, unknown>> = [];
let nextOutlineId = 500;
const api = {
  importWhiteboard: async (body: Record<string, unknown>) => {
    check('manuscript import receives every block', Array.isArray(body.blocks) && body.blocks.length === 4);
    return {
      project_id: 77,
      title: 'Graduated Story',
      mode: 'novel',
      scenes_created: 2,
      scene_titles: ['Chapter One', 'Chapter Two'],
      scene_ids_by_block: [101, 101, 202, 202],
    };
  },
  listScenes: async () => [
    { id: 101, title: 'Chapter One', content: 'Opening alpha.' },
    { id: 202, title: 'Chapter Two', content: 'Closing beta.' },
  ],
  getSettings: async () => ({ settings: { existing: 'kept' } }),
  patchSettings: async (_projectId: number, body: { settings: Record<string, unknown> }) => {
    settingsCalls.push(body.settings);
    return body;
  },
  createPsyke: async (projectId: number, body: Record<string, unknown>) => {
    psykeCalls.push({ projectId, body });
    if (body.name === 'Broken entry') throw new Error('simulated PSYKE failure');
    return { id: psykeCalls.length, project_id: projectId, ...body };
  },
  createOutlineNode: async (projectId: number, body: Record<string, unknown>) => {
    outlineCalls.push({ projectId, body });
    if (body.title === 'Fail node') throw new Error('simulated outline failure');
    nextOutlineId += 1;
    return { id: nextOutlineId, project_id: projectId, ...body };
  },
} as unknown as ApiClient;

const bundle: ProjectBundle = {
  format: BUNDLE_FORMAT,
  version: '1',
  project: {
    title: 'Graduated Story',
    mode: 'novel',
    settings: { narrativePerson: 'first', narrativeStyle: 'literary' },
    manuscript: {
      blocks: [
        { id: 'b0', type: 'heading', text: 'Chapter One', level: 1 },
        { id: 'b1', type: 'paragraph', text: 'Opening alpha.' },
        { id: 'b2', type: 'heading', text: 'Chapter Two', level: 1 },
        { id: 'b3', type: 'paragraph', text: 'Closing beta.' },
      ],
    },
    psyke: {
      elements: [
        { id: 'p1', name: 'Mara', entry_type: 'character', aliases: ['M'], description: 'Lead' },
        { id: 'p2', name: 'Mara', entry_type: 'character' },
        { id: 'p3', name: '   ', entry_type: 'place' },
        { id: 'p4', name: 'Broken entry', entry_type: 'lore' },
        { id: 'p5', name: 'Lighthouse', entry_type: 'place', notes: 'North coast' },
      ],
    },
    // Child deliberately precedes parent: import must create parent first.
    outline: [
      {
        id: 'child', parentId: 'parent', type: 'scene', title: 'Scene Two', order: 1,
        link: { blockIndex: 2, quote: 'Chapter Two', blockId: 'b2' },
      },
      {
        id: 'parent', parentId: null, type: 'act', title: 'Act I', order: 0,
        summary: 'Mara accepts the impossible crossing.',
        status: 'drafting', completed: true, colorLabel: 'blue', tags: ['arc'],
        link: { blockIndex: 0, quote: 'Chapter One', blockId: 'b0' },
      },
      {
        id: 'stale', parentId: null, type: 'scene', title: 'Stale link', order: 2,
        link: { blockIndex: 3, quote: 'text no longer present', blockId: 'b3' },
      },
      {
        id: 'failed', parentId: null, type: 'scene', title: 'Fail node', order: 3,
        link: { blockIndex: 1, quote: 'Opening alpha.', blockId: 'b1' },
      },
      { id: 'orphan', parentId: 'missing', type: 'beat', title: 'Missing parent', order: 4 },
    ],
    comments: [{ id: 'c1' }, { id: 'c2' }],
  },
};

const result = await importProjectBundle(api, bundle);
check('result identifies created project', result.projectId === 77 && result.scenes === 2);
check('document settings reported as preserved', result.settingsImported && !result.settingsSkipped);
check(
  'document settings merge without clobbering existing project settings',
  settingsCalls[0].existing === 'kept' &&
    (settingsCalls[0].whiteboard_document_settings as Record<string, unknown>).narrativePerson === 'first',
);
check('PSYKE successes counted', result.entries === 2 && psykeCalls.length === 3);
check('PSYKE invalid/duplicate/failed rows reported', result.entriesSkipped === 3);
check('PSYKE description maps into details', (psykeCalls[0].body.details as { description?: string }).description === 'Lead');
check('outline create failure reported', result.outlineNodes === 4 && result.outlineSkipped === 1);
check('missing outline parent reported', result.outlineReparented === 1);
check('no duplicate outline ids reported for clean ids', result.outlineDuplicateIds === 0);
check('comments explicitly counted as deferred', result.comments === 2);
check('resolved and skipped links counted', result.links === 2 && result.linksSkipped === 2);
check('outline is topologically created', outlineCalls[0].body.title === 'Act I' && outlineCalls[1].body.title === 'Scene Two');
check('child receives recreated parent id', outlineCalls[1].body.parent_id === 501);
check('successful links receive mapped scene ids', outlineCalls[0].body.scene_id === 101 && outlineCalls[1].body.scene_id === 202);
check('stale quote prevents wrong scene link', outlineCalls.find((call) => call.body.title === 'Stale link')?.body.scene_id === null);
check('missing parent degrades to root', outlineCalls.find((call) => call.body.title === 'Missing parent')?.body.parent_id === null);
check(
  'outline metadata remains visible',
  outlineCalls[0].body.description ===
    'Mara accepts the impossible crossing.\n\n[Whiteboard: Act · drafting · completed · blue · #arc]',
);

// If manuscript/project creation fails, no secondary API may run.
{
  let secondaryCalls = 0;
  const failingApi = {
    importWhiteboard: async () => { throw new Error('core import failed'); },
    createPsyke: async () => { secondaryCalls += 1; },
    listScenes: async () => { secondaryCalls += 1; return []; },
    createOutlineNode: async () => { secondaryCalls += 1; },
  } as unknown as ApiClient;
  let rejected = false;
  try {
    await importProjectBundle(failingApi, bundle);
  } catch (error) {
    rejected = error instanceof Error && error.message === 'core import failed';
  }
  check('primary import failure propagates', rejected);
  check('primary import failure prevents secondary writes', secondaryCalls === 0);
}

console.log(`Project bundle tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} project bundle test(s) failed`);
console.log('PROJECT BUNDLE TESTS: PASS');
