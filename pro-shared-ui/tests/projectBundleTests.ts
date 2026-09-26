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
expectParseError(
  'non-array PSYKE relations rejected before project creation',
  JSON.stringify({
    format: BUNDLE_FORMAT,
    project: { manuscript: { blocks: [] }, psyke: { elements: [], relations: {} } },
  }),
  'This bundle has an invalid PSYKE relations section.',
);
expectParseError(
  'non-object PSYKE relation rejected before project creation',
  JSON.stringify({
    format: BUNDLE_FORMAT,
    project: { manuscript: { blocks: [] }, psyke: { elements: [], relations: ['bad'] } },
  }),
  'This bundle contains an invalid PSYKE relation.',
);
expectParseError(
  'non-array PSYKE progressions rejected before project creation',
  JSON.stringify({
    format: BUNDLE_FORMAT,
    project: { manuscript: { blocks: [] }, psyke: { elements: [], progressions: {} } },
  }),
  'This bundle has an invalid PSYKE progressions section.',
);
expectParseError(
  'non-object PSYKE progression rejected before project creation',
  JSON.stringify({
    format: BUNDLE_FORMAT,
    project: { manuscript: { blocks: [] }, psyke: { elements: [], progressions: [false] } },
  }),
  'This bundle contains an invalid PSYKE progression.',
);
expectParseError(
  'non-object inline comment rejected before project creation',
  JSON.stringify({
    format: BUNDLE_FORMAT,
    project: { manuscript: { blocks: [] }, comments: ['bad'] },
  }),
  'This bundle contains an invalid inline comment.',
);
expectParseError(
  'inline comment without an anchor rejected before project creation',
  JSON.stringify({
    format: BUNDLE_FORMAT,
    project: { manuscript: { blocks: [] }, comments: [{ id: 'c1' }] },
  }),
  'This bundle contains an invalid inline comment anchor.',
);
expectParseError(
  'non-array inline comment replies rejected before project creation',
  JSON.stringify({
    format: BUNDLE_FORMAT,
    project: { manuscript: { blocks: [] }, comments: [{ id: 'c1', anchor: {}, replies: {} }] },
  }),
  'This bundle contains an invalid inline comment replies section.',
);
expectParseError(
  'non-object inline comment reply rejected before project creation',
  JSON.stringify({
    format: BUNDLE_FORMAT,
    project: { manuscript: { blocks: [] }, comments: [{ id: 'c1', anchor: {}, replies: [false] }] },
  }),
  'This bundle contains an invalid inline comment reply.',
);

const psykeCalls: Array<{ projectId: number; body: Record<string, unknown> }> = [];
const relationCalls: Array<{ projectId: number; body: Record<string, unknown> }> = [];
const progressionCalls: Array<{ projectId: number; body: Record<string, unknown> }> = [];
const outlineCalls: Array<{ projectId: number; body: Record<string, unknown> }> = [];
const settingsCalls: Array<Record<string, unknown>> = [];
let nextOutlineId = 500;
const api = {
  importWhiteboard: async (body: Record<string, unknown>) => {
    check('manuscript import receives every block', Array.isArray(body.blocks) && body.blocks.length === 4);
    const comments = body.comments as Array<Record<string, unknown>>;
    check(
      'manuscript import receives complete comment threads',
      Array.isArray(comments) && comments.length === 2 &&
        comments[0]?.id === 'c1' && comments[0]?.resolved === false &&
        Array.isArray(comments[0]?.replies) && comments[0]?.replies.length === 1 &&
        (comments[1]?.anchor as Record<string, unknown>)?.end_block_id === 'b1',
    );
    return {
      project_id: 77,
      title: 'Graduated Story',
      mode: 'novel',
      scenes_created: 2,
      scene_titles: ['Chapter One', 'Chapter Two'],
      scene_ids_by_block: [101, 101, 202, 202],
      comments_created: 1,
      comments_skipped: 1,
      comment_replies_created: 1,
      comment_replies_skipped: 2,
    };
  },
  listScenes: async () => [
    { id: 101, title: 'Chapter One', content: 'Opening alpha.' },
    { id: 202, title: 'Chapter Two', content: 'Closing beta.' },
    { id: 303, title: 'Echo', content: 'First scene with this title.' },
    { id: 404, title: 'Echo', content: 'Second scene with this title.' },
  ],
  getSettings: async () => ({ settings: { existing: 'kept' } }),
  patchSettings: async (_projectId: number, body: { settings: Record<string, unknown> }) => {
    settingsCalls.push(body.settings);
    return body;
  },
  createPsyke: async (projectId: number, body: Record<string, unknown>) => {
    psykeCalls.push({ projectId, body });
    if (body.name === 'Broken entry') throw new Error('simulated PSYKE failure');
    const destinationIds: Record<string, number> = {
      Mara: 1100,
      Lighthouse: 9300,
      Storm: 6200,
    };
    return { id: destinationIds[String(body.name)], ...body };
  },
  createRelation: async (projectId: number, body: Record<string, unknown>) => {
    relationCalls.push({ projectId, body });
    if (body.relation_type === 'api-fail') throw new Error('simulated relation failure');
    return {
      id: `${body.source_id}:${body.target_id}`,
      source_id: body.source_id,
      target_id: body.target_id,
      source: '',
      target: '',
      relation_type: body.relation_type ?? '',
    };
  },
  createProgression: async (projectId: number, body: Record<string, unknown>) => {
    progressionCalls.push({ projectId, body });
    if (body.text === 'API progression failure') {
      throw new Error('simulated progression failure');
    }
    return {
      id: 7000 + progressionCalls.length,
      entry_id: body.entry_id,
      text: body.text,
      scene_id: body.scene_id ?? null,
      scene_title: '',
      sort_order: progressionCalls.length,
    };
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
  version: '1.0',
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
        { id: '41', name: 'Mara', entry_type: 'character', aliases: ['M'], description: 'Lead' },
        { id: '42', name: 'Mara', entry_type: 'character' },
        { id: '43', name: '   ', entry_type: 'place' },
        { id: '99', name: 'Broken entry', entry_type: 'lore' },
        { id: '17', name: 'Lighthouse', entry_type: 'place', notes: 'North coast' },
        { id: '73', name: 'Storm', entry_type: 'lore' },
      ],
      relations: [
        // Whiteboard emits numeric references even though element ids are strings.
        // The destination ids deliberately reverse the source ordering: importer
        // must preserve this source/target direction, not recanonicalize the pair.
        {
          id: '17:41', source_id: 17, target_id: 41,
          source: 'Lighthouse', target: 'Mara', relation_type: 'payoff',
        },
        {
          id: '41:73', source_id: 41, target_id: 73,
          source: 'Mara', target: 'Storm', relation_type: 'api-fail',
        },
        {
          id: '17:404', source_id: 17, target_id: 404,
          source: 'Lighthouse', target: 'Missing', relation_type: 'thematic_echo',
        },
        {
          id: '41:41', source_id: 41, target_id: 41,
          source: 'Mara', target: 'Mara', relation_type: 'self',
        },
        {
          id: '17:41', source_id: 41, target_id: 17,
          source: 'Mara', target: 'Lighthouse', relation_type: 'duplicate-reverse',
        },
        {
          id: '0:17', source_id: 0, target_id: 17,
          source: 'Invalid', target: 'Lighthouse', relation_type: 'invalid-id',
        },
      ],
      progressions: [
        // Deliberately out of source order. Creation order is how the core assigns
        // destination sort_order, so the importer must sort per entry first.
        {
          id: 502, entry_id: 41, text: 'Second Mara beat', scene_id: null,
          scene_title: '', sort_order: 2,
        },
        {
          id: 501, entry_id: 41, text: 'First Mara beat', scene_id: 880,
          scene_title: '  Chapter Two  ', sort_order: 1,
        },
        {
          id: 503, entry_id: 17, text: 'Missing scene beat', scene_id: 881,
          scene_title: 'No longer present', sort_order: 1,
        },
        {
          id: 504, entry_id: 73, text: 'Ambiguous scene beat', scene_id: 882,
          scene_title: ' Echo ', sort_order: 1,
        },
        {
          id: 505, entry_id: 17, text: 'Intentionally unanchored', scene_id: null,
          scene_title: '', sort_order: 2,
        },
        {
          id: 506, entry_id: 404, text: 'Missing entry beat', scene_id: null,
          scene_title: '', sort_order: 1,
        },
        {
          id: 507, entry_id: 0, text: 'Invalid entry id', scene_id: null,
          scene_title: '', sort_order: 1,
        },
        {
          id: 508, entry_id: 73, text: '', scene_id: null,
          scene_title: '', sort_order: 2,
        },
        {
          id: 509, entry_id: 73, text: 'API progression failure', scene_id: null,
          scene_title: '', sort_order: 3,
        },
        {
          id: 510, entry_id: 73, text: 'After failed progression', scene_id: null,
          scene_title: '', sort_order: 4,
        },
        {
          id: 511, entry_id: 73, text: 17 as unknown as string, scene_id: null,
          scene_title: '', sort_order: 5,
        },
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
    comments: [
      {
        id: 'c1',
        anchor: {
          block_index: 1,
          block_id: 'b1',
          from_offset: 0,
          to_offset: 7,
          prefix: '',
          suffix: ' alpha.',
        },
        quote: 'Opening',
        body: 'Start with a sharper verb.',
        resolved: false,
        replies: [{
          id: 'r1',
          body: 'Agreed.',
          author: 'writer',
          created_at: '2026-09-01T10:01:00Z',
        }],
        created_at: '2026-09-01T10:00:00Z',
        updated_at: '2026-09-01T10:01:00Z',
      },
      {
        id: 'c2',
        anchor: {
          block_index: 0,
          block_id: 'b0',
          from_offset: 0,
          to_offset: 7,
          end_block_index: 1,
          end_block_id: 'b1',
          prefix: '',
          suffix: '',
        },
        quote: 'Chapter One\nOpening',
        body: 'Cross-field source selection.',
        resolved: true,
        replies: [],
        created_at: '2026-09-02T10:00:00Z',
        updated_at: '2026-09-02T10:00:00Z',
      },
    ],
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
check('PSYKE successes counted', result.entries === 3 && psykeCalls.length === 4);
check('PSYKE invalid/duplicate/failed rows reported', result.entriesSkipped === 3);
check('PSYKE description maps into details', (psykeCalls[0].body.details as { description?: string }).description === 'Lead');
check(
  'relations use remapped destination ids and preserve direction',
  relationCalls[0]?.projectId === 77 &&
    relationCalls[0]?.body.source_id === 9300 &&
    relationCalls[0]?.body.target_id === 1100 &&
    relationCalls[0]?.body.relation_type === 'payoff',
);
check(
  'invalid duplicate and failed relations are reported without redundant writes',
  result.relations === 1 && result.relationsSkipped === 5 && relationCalls.length === 2,
);
check(
  'relationship import never forwards source ids',
  relationCalls.every((call) =>
    call.body.source_id !== 17 && call.body.source_id !== 41 && call.body.source_id !== 73 &&
    call.body.target_id !== 17 && call.body.target_id !== 41 && call.body.target_id !== 73),
);
const firstMaraBeatIndex = progressionCalls.findIndex((call) => call.body.text === 'First Mara beat');
const secondMaraBeatIndex = progressionCalls.findIndex((call) => call.body.text === 'Second Mara beat');
check(
  'progression create order preserves source sort_order per entry',
  firstMaraBeatIndex >= 0 && firstMaraBeatIndex < secondMaraBeatIndex,
);
const firstMaraBeat = progressionCalls[firstMaraBeatIndex];
check(
  'progressions remap entry and uniquely matched trimmed scene title',
  firstMaraBeat?.projectId === 77 &&
    firstMaraBeat?.body.entry_id === 1100 &&
    firstMaraBeat?.body.scene_id === 202,
);
check(
  'source scene ids are never forwarded',
  progressionCalls.every((call) =>
    call.body.scene_id !== 880 && call.body.scene_id !== 881 && call.body.scene_id !== 882),
);
check(
  'missing and ambiguous scene titles create unanchored progressions',
  progressionCalls.find((call) => call.body.text === 'Missing scene beat')?.body.scene_id === null &&
    progressionCalls.find((call) => call.body.text === 'Ambiguous scene beat')?.body.scene_id === null,
);
check(
  'valid progression work continues after one API failure',
  progressionCalls.some((call) => call.body.text === 'API progression failure') &&
    progressionCalls.some((call) => call.body.text === 'After failed progression'),
);
check(
  'blank string progression text is preserved',
  progressionCalls.some((call) => call.body.text === ''),
);
check(
  'progression successes failures and scene-link outcomes are reported',
  result.progressions === 7 &&
    result.progressionsSkipped === 4 &&
    result.progressionSceneLinks === 1 &&
    result.progressionSceneLinksSkipped === 2 &&
    progressionCalls.length === 8,
);
check(
  'progression import never forwards source entry ids',
  progressionCalls.every((call) =>
    call.body.entry_id !== 17 && call.body.entry_id !== 41 && call.body.entry_id !== 73),
);
check('outline create failure reported', result.outlineNodes === 4 && result.outlineSkipped === 1);
check('missing outline parent reported', result.outlineReparented === 1);
check('no duplicate outline ids reported for clean ids', result.outlineDuplicateIds === 0);
check(
  'comment and reply import outcomes come from the core mapping report',
  result.comments === 1 && result.commentsSkipped === 1 &&
    result.commentReplies === 1 && result.commentRepliesSkipped === 2,
);
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

// A pre-graph (v1.0) bundle with entries only stays importable and never calls
// relationship/progression endpoints. The new result counters remain explicit.
{
  let legacyGraphCalls = 0;
  const legacyApi = {
    importWhiteboard: async () => ({
      project_id: 88,
      title: 'Legacy bundle',
      mode: 'novel',
      scenes_created: 1,
      scene_titles: ['Legacy bundle'],
      scene_ids_by_block: [808],
    }),
    createPsyke: async (_projectId: number, body: Record<string, unknown>) => ({
      id: 8800,
      ...body,
    }),
    createRelation: async () => { legacyGraphCalls += 1; throw new Error('unexpected relation'); },
    createProgression: async () => { legacyGraphCalls += 1; throw new Error('unexpected progression'); },
    createOutlineNode: async () => { throw new Error('unexpected outline'); },
  } as unknown as ApiClient;
  const legacyBundle = parseProjectBundle(JSON.stringify({
    format: BUNDLE_FORMAT,
    version: '1.0',
    project: {
      title: 'Legacy bundle',
      mode: 'novel',
      manuscript: { blocks: [{ id: 'old', type: 'paragraph', text: 'Legacy.' }] },
      psyke: { elements: [{ id: '1', name: 'Legacy hero', entry_type: 'character' }] },
    },
  }));
  const legacyResult = await importProjectBundle(legacyApi, legacyBundle);
  check('legacy entries-only bundle still imports its entry', legacyResult.entries === 1);
  check(
    'legacy bundle has zero graph outcomes and no graph writes',
    legacyResult.relations === 0 &&
      legacyResult.relationsSkipped === 0 &&
      legacyResult.progressions === 0 &&
      legacyResult.progressionsSkipped === 0 &&
      legacyResult.progressionSceneLinks === 0 &&
      legacyResult.progressionSceneLinksSkipped === 0 &&
      legacyGraphCalls === 0,
  );
}

// Exact duplicate entries can safely share the one recreated destination row,
// but a source id reused for two different entries is ambiguous and must never
// be chosen for a relationship or progression.
{
  const progressionBodies: Record<string, unknown>[] = [];
  const duplicateIdApi = {
    importWhiteboard: async () => ({
      project_id: 89,
      title: 'Duplicate ids',
      mode: 'novel',
      scenes_created: 0,
      scene_titles: [],
      scene_ids_by_block: [],
    }),
    createPsyke: async (_projectId: number, body: Record<string, unknown>) => ({
      id: ({ Shared: 5100, Alpha: 5200, Beta: 5300 } as Record<string, number>)[String(body.name)],
      ...body,
    }),
    createRelation: async () => { throw new Error('unexpected relation'); },
    createProgression: async (_projectId: number, body: Record<string, unknown>) => {
      progressionBodies.push(body);
      return { id: 1, entry_id: body.entry_id, text: body.text, scene_id: null, scene_title: '', sort_order: 1 };
    },
    createOutlineNode: async () => { throw new Error('unexpected outline'); },
  } as unknown as ApiClient;
  const duplicateIdBundle: ProjectBundle = {
    format: BUNDLE_FORMAT,
    version: '1.0',
    project: {
      manuscript: { blocks: [] },
      psyke: {
        elements: [
          { id: '1', name: 'Shared', entry_type: 'character' },
          { id: '2', name: 'Shared', entry_type: 'character' },
          { id: '3', name: 'Alpha', entry_type: 'place' },
          { id: '3', name: 'Beta', entry_type: 'place' },
        ],
        progressions: [
          { id: 1, entry_id: 2, text: 'Safe duplicate mapping', scene_id: null, scene_title: '', sort_order: 1 },
          { id: 2, entry_id: 3, text: 'Ambiguous mapping', scene_id: null, scene_title: '', sort_order: 1 },
        ],
      },
    },
  };
  const duplicateIdResult = await importProjectBundle(duplicateIdApi, duplicateIdBundle);
  check(
    'exact duplicate entry ids map to their shared destination entry',
    progressionBodies.length === 1 && progressionBodies[0].entry_id === 5100,
  );
  check(
    'conflicting reused source entry id remains unmapped',
    duplicateIdResult.progressions === 1 && duplicateIdResult.progressionsSkipped === 1,
  );
}

// A scene-list read is advisory: progression anchors need its unique-title
// evidence and therefore degrade to null, while outline links still have the
// authoritative block-index map returned by the manuscript import.
{
  const progressionBodies: Record<string, unknown>[] = [];
  const outlineBodies: Record<string, unknown>[] = [];
  const unavailableScenesApi = {
    importWhiteboard: async () => ({
      project_id: 90,
      title: 'Scene read fallback',
      mode: 'novel',
      scenes_created: 1,
      scene_titles: ['Only Scene'],
      scene_ids_by_block: [901],
    }),
    createPsyke: async (_projectId: number, body: Record<string, unknown>) => ({ id: 7100, ...body }),
    listScenes: async () => { throw new Error('simulated scene-list failure'); },
    createProgression: async (_projectId: number, body: Record<string, unknown>) => {
      progressionBodies.push(body);
      return { id: 1, entry_id: body.entry_id, text: body.text, scene_id: body.scene_id, scene_title: '', sort_order: 1 };
    },
    createOutlineNode: async (_projectId: number, body: Record<string, unknown>) => {
      outlineBodies.push(body);
      return { id: 8100, ...body };
    },
  } as unknown as ApiClient;
  const unavailableScenesBundle: ProjectBundle = {
    format: BUNDLE_FORMAT,
    version: '1.0',
    project: {
      manuscript: { blocks: [{ id: 'b0', type: 'heading', text: 'Only Scene', level: 1 }] },
      psyke: {
        elements: [{ id: '1', name: 'Hero', entry_type: 'character' }],
        progressions: [
          { id: 1, entry_id: 1, text: 'Linked beat', scene_id: 44, scene_title: 'Only Scene', sort_order: 1 },
        ],
      },
      outline: [
        { id: 'o1', title: 'Only Scene', link: { blockIndex: 0, quote: 'Only Scene', blockId: 'b0' } },
      ],
    },
  };
  const unavailableScenesResult = await importProjectBundle(unavailableScenesApi, unavailableScenesBundle);
  check(
    'scene-list failure preserves progression unanchored and reports its anchor',
    progressionBodies[0]?.scene_id === null &&
      unavailableScenesResult.progressionSceneLinks === 0 &&
      unavailableScenesResult.progressionSceneLinksSkipped === 1,
  );
  check(
    'scene-list failure retains outline block-map fallback',
    outlineBodies[0]?.scene_id === 901 && unavailableScenesResult.links === 1 && unavailableScenesResult.linksSkipped === 0,
  );
}

// If manuscript/project creation fails, no secondary API may run.
{
  let secondaryCalls = 0;
  const failingApi = {
    importWhiteboard: async () => { throw new Error('core import failed'); },
    createPsyke: async () => { secondaryCalls += 1; },
    createRelation: async () => { secondaryCalls += 1; },
    createProgression: async () => { secondaryCalls += 1; },
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
