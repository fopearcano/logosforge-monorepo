/** Whiteboard `.lfbundle` parser + Pro import orchestration tests. */

import type { ProgressionCommandDTO, ProgressionSnapshotDTO } from '@logosforge/ui-contracts';
import type { ApiClient } from '../src/adapters/api';
import { ApiRequestError, ApiRequestTimeoutError } from '../src/adapters/httpApiClient';
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
  'non-array first-class Progressions rejected before project creation',
  JSON.stringify({ format: BUNDLE_FORMAT, project: { manuscript: { blocks: [] }, progression_tracks: {} } }),
  'This bundle has an invalid Progressions tracks section.',
);
expectParseError(
  'invalid first-class Progressions beat rejected before project creation',
  JSON.stringify({
    format: BUNDLE_FORMAT,
    project: { manuscript: { blocks: [] }, progression_tracks: [{ kind: 'story', title: 'Arc', beats: [{ text: 'Beat', anchor_kind: 'guess' }] }] },
  }),
  'This bundle contains an invalid Progressions beat.',
);
expectParseError(
  'invalid Progressions compatibility marker rejected before project creation',
  JSON.stringify({
    format: BUNDLE_FORMAT,
    project: { manuscript: { blocks: [] }, progression_tracks: [{ kind: 'story', title: 'Arc', legacy_compatibility: 'yes', beats: [] }] },
  }),
  'This bundle contains an invalid Progressions compatibility marker.',
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
expectParseError(
  'non-array Drafter pages rejected before project creation',
  JSON.stringify({
    format: BUNDLE_FORMAT,
    project: { manuscript: { blocks: [] }, drafter: { pages: {} } },
  }),
  'This bundle has an invalid Drafter section.',
);
expectParseError(
  'Drafter page without a block list rejected before project creation',
  JSON.stringify({
    format: BUNDLE_FORMAT,
    project: { manuscript: { blocks: [] }, drafter: { pages: [{ id: 'draft-1' }] } },
  }),
  'This bundle contains an invalid Drafter page block list.',
);

const psykeCalls: Array<{ projectId: number; body: Record<string, unknown> }> = [];
const relationCalls: Array<{ projectId: number; body: Record<string, unknown> }> = [];
const progressionCalls: Array<{ projectId: number; body: Record<string, unknown> }> = [];
const outlineCalls: Array<{ projectId: number; body: Record<string, unknown> }> = [];
const noteCalls: Array<{ projectId: number; body: Record<string, unknown> }> = [];
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
      throw new ApiRequestError('POST', '/progressions', 400, 'simulated progression failure');
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
  createNote: async (projectId: number, body: Record<string, unknown>) => {
    noteCalls.push({ projectId, body });
    if (body.title === 'Failed scratch') throw new Error('simulated note failure');
    return { id: 900 + noteCalls.length, ...body, psyke_links: [], scene_links: [] };
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
    drafter: {
      pages: [
        {
          id: 'draft-1',
          title: 'Alternate opening',
          blocks: [
            { id: 'd1', type: 'heading', text: 'A different night', level: 2 },
            { id: 'd2', type: 'paragraph', text: 'Mara waits at the seawall.' },
          ],
          created_at: '2026-09-20T10:00:00Z',
          updated_at: '2026-09-20T11:00:00Z',
        },
        {
          id: 'draft-2',
          title: 'Failed scratch',
          blocks: [{ id: 'd3', type: 'paragraph', text: 'Keep this in the archive.' }],
          created_at: '2026-09-20T12:00:00Z',
          updated_at: '2026-09-20T12:00:00Z',
        },
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
    (settingsCalls[0].whiteboard_document_settings as Record<string, unknown>).narrativePerson === 'first' &&
    Array.isArray(settingsCalls[0].whiteboard_drafter_pages) &&
    (settingsCalls[0].whiteboard_drafter_pages as unknown[]).length === 2,
);
check(
  'Drafter pages become non-canonical Pro Notes with readable formatting',
  noteCalls[0]?.projectId === 77 &&
    noteCalls[0]?.body.title === 'Alternate opening' &&
    noteCalls[0]?.body.content === '## A different night\n\nMara waits at the seawall.' &&
    Array.isArray(noteCalls[0]?.body.tags) &&
    (noteCalls[0]?.body.tags as string[]).includes('whiteboard-drafter'),
);
check(
  'Drafter Note outcomes and exact archive preservation are reported',
  result.drafterPages === 1 && result.drafterPagesSkipped === 1 &&
    result.drafterArchivePreserved && !result.drafterArchiveSkipped,
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

// Additive first-class tracks import after PSYKE/scenes and never reuse source ids.
{
  const commands: ProgressionCommandDTO[] = [];
  let revisionCounter = 0;
  let snapshot: ProgressionSnapshotDTO = {
    project_id: 91,
    revision: '0'.repeat(64),
    tracks: [],
    summary: {
      total_tracks: 0, total_beats: 0, anchored_beats: 0, unanchored_beats: 0,
      coverage_percent: 0,
      by_kind: { story: 0, character: 0, relationship: 0, theme: 0, world: 0, custom: 0 },
      by_status: { empty: 0, unanchored: 0, partial: 0, complete: 0 },
    },
  };
  const refreshSummary = () => {
    const totalBeats = snapshot.tracks.reduce((sum, track) => sum + track.beats.length, 0);
    const anchored = snapshot.tracks.reduce((sum, track) => sum + track.beats.filter((beat) => beat.anchor_kind !== 'unanchored').length, 0);
    snapshot.summary.total_tracks = snapshot.tracks.length;
    snapshot.summary.total_beats = totalBeats;
    snapshot.summary.anchored_beats = anchored;
    snapshot.summary.unanchored_beats = totalBeats - anchored;
    snapshot.summary.coverage_percent = totalBeats ? Math.round(anchored / totalBeats * 100) : 0;
    snapshot.summary.by_kind = { story: 0, character: 0, relationship: 0, theme: 0, world: 0, custom: 0 };
    snapshot.summary.by_status = { empty: 0, unanchored: 0, partial: 0, complete: 0 };
    for (const track of snapshot.tracks) {
      snapshot.summary.by_kind[track.kind] += 1;
      snapshot.summary.by_status[track.coverage.status] += 1;
    }
    revisionCounter += 1;
    snapshot.revision = revisionCounter.toString(16).padStart(64, '0');
  };
  const progressionApi = {
    importWhiteboard: async () => ({ project_id: 91, title: 'Tracked import', mode: 'novel', scenes_created: 1, scene_titles: ['Arrival'], scene_ids_by_block: [901] }),
    createPsyke: async (_projectId: number, body: Record<string, unknown>) => ({ id: 1901, ...body }),
    listScenes: async () => [{ id: 901, title: 'Arrival', content: 'The arrival.' }],
    getProgressions: async () => structuredClone(snapshot),
    getProgressionCommandReceipt: async () => { throw new Error('receipt should not be needed'); },
    executeProgressionCommand: async (_projectId: number, command: ProgressionCommandDTO) => {
      commands.push(command);
      let createdTrackId: number | null = null;
      let createdBeatId: number | null = null;
      let affectedTrackIds: number[] = [];
      let affectedBeatIds: number[] = [];
      if (command.kind === 'create_track') {
        createdTrackId = 2000 + snapshot.tracks.length;
        snapshot.tracks.push({
          id: createdTrackId, project_id: 91, kind: command.track_kind, title: command.title,
          description: command.description ?? '', color_label: command.color_label ?? '', sort_order: snapshot.tracks.length,
          legacy_compatibility: false,
          primary_psyke_entry_id: command.primary_psyke_entry_id ?? null,
          primary_psyke_entry_name: command.primary_psyke_entry_id ? 'Mara' : '',
          primary_psyke_entry_type: command.primary_psyke_entry_id ? 'character' : '',
          secondary_psyke_entry_id: command.secondary_psyke_entry_id ?? null,
          secondary_psyke_entry_name: '', secondary_psyke_entry_type: '', beats: [],
          coverage: { total_beats: 0, anchored_beats: 0, unanchored_beats: 0, scene_anchored_beats: 0, document_anchored_beats: 0, coverage_percent: 0, status: 'empty', out_of_order_beat_ids: [] },
        });
        affectedTrackIds = [createdTrackId];
      } else if (command.kind === 'create_beat') {
        const track = snapshot.tracks.find((candidate) => candidate.id === command.track_id)!;
        createdBeatId = 3000 + track.beats.length;
        track.beats.push({
          id: createdBeatId, track_id: track.id, text: command.text, sort_order: track.beats.length,
          anchor_kind: command.anchor_kind ?? 'unanchored', scene_id: command.scene_id ?? null,
          scene_title: command.scene_id === 901 ? 'Arrival' : '', anchor_ref: command.anchor_ref ?? null,
          anchor_label: command.anchor_label ?? '',
        });
        const sceneCount = track.beats.filter((beat) => beat.anchor_kind === 'scene').length;
        const documentCount = track.beats.filter((beat) => beat.anchor_kind === 'document_block').length;
        const anchored = sceneCount + documentCount;
        track.coverage = {
          total_beats: track.beats.length, anchored_beats: anchored,
          unanchored_beats: track.beats.length - anchored, scene_anchored_beats: sceneCount,
          document_anchored_beats: documentCount, coverage_percent: Math.round(anchored / track.beats.length * 100),
          status: anchored === track.beats.length ? 'complete' : anchored ? 'partial' : 'unanchored', out_of_order_beat_ids: [],
        };
        affectedTrackIds = [track.id]; affectedBeatIds = [createdBeatId];
      }
      refreshSummary();
      return { progressions: structuredClone(snapshot), changed: true, affected_track_ids: affectedTrackIds, affected_beat_ids: affectedBeatIds, created_track_id: createdTrackId, created_beat_id: createdBeatId, replayed: false, applied_revision: snapshot.revision };
    },
    createOutlineNode: async () => { throw new Error('unexpected outline'); },
  } as unknown as ApiClient;
  const progressionBundle: ProjectBundle = {
    format: BUNDLE_FORMAT,
    version: '1.0',
    project: {
      manuscript: { blocks: [{ id: 'b1', type: 'paragraph', text: 'The arrival.' }] },
      psyke: { elements: [{ id: '41', name: 'Mara', entry_type: 'character' }] },
      progression_tracks: [{
        id: 12, kind: 'character', title: 'Mara learns to answer', description: 'Her trust arc.',
        color_label: 'cyan', sort_order: 0,
        primary_psyke_entry_id: 41, primary_psyke_entry_name: 'Mara', primary_psyke_entry_type: 'character',
        secondary_psyke_entry_id: null, secondary_psyke_entry_name: '', secondary_psyke_entry_type: '',
        beats: [
          { id: 21, track_id: 12, text: 'She hears it.', sort_order: 0, anchor_kind: 'scene', scene_id: 700, scene_title: 'Arrival', anchor_ref: null, anchor_label: '' },
          { id: 22, track_id: 12, text: 'She writes alone.', sort_order: 1, anchor_kind: 'document_block', scene_id: null, scene_title: '', anchor_ref: 'drafter:block-7', anchor_label: 'Private draft' },
        ],
      }],
    },
  };
  const imported = await importProjectBundle(progressionApi, progressionBundle);
  const trackCommand = commands.find((command) => command.kind === 'create_track');
  const beatCommands = commands.filter((command) => command.kind === 'create_beat');
  check('first-class track remaps its PSYKE subject', trackCommand?.kind === 'create_track' && trackCommand.primary_psyke_entry_id === 1901);
  check('first-class scene beat remaps by unique title without forwarding source id', beatCommands[0]?.kind === 'create_beat' && beatCommands[0].scene_id === 901);
  check('first-class document anchor preserves reference and label', beatCommands[1]?.kind === 'create_beat' && beatCommands[1].anchor_ref === 'drafter:block-7' && beatCommands[1].anchor_label === 'Private draft');
  check('first-class import reports tracks beats and anchors', imported.progressionTracks === 1 && imported.progressionTrackBeats === 2 && imported.progressionTrackSceneLinks === 1 && imported.progressionTracksSkipped === 0 && imported.progressionTrackBeatsSkipped === 0);
}

// New bundles include the legacy per-entry projection beside canonical tracks.
// Exact beat-id compatibility tracks must go through the legacy endpoint once
// (so Core restores its private linkage), while unmatched legacy rows are not
// duplicated. This includes `other` entries represented as custom tracks, which
// the ordinary canonical create_track command intentionally rejects.
{
  const legacyWrites: Record<string, unknown>[] = [];
  const canonicalCommands: ProgressionCommandDTO[] = [];
  let revisionCounter = 0;
  let snapshot: ProgressionSnapshotDTO = {
    project_id: 92,
    revision: '0'.repeat(64),
    tracks: [],
    summary: {
      total_tracks: 0, total_beats: 0, anchored_beats: 0, unanchored_beats: 0,
      coverage_percent: 0,
      by_kind: { story: 0, character: 0, relationship: 0, theme: 0, world: 0, custom: 0 },
      by_status: { empty: 0, unanchored: 0, partial: 0, complete: 0 },
    },
  };
  const refreshCompatibilitySnapshot = () => {
    snapshot.tracks.forEach((track, trackIndex) => {
      track.sort_order = trackIndex;
      track.beats.forEach((beat, beatIndex) => { beat.sort_order = beatIndex; });
      const sceneCount = track.beats.filter((beat) => beat.anchor_kind === 'scene').length;
      const documentCount = track.beats.filter((beat) => beat.anchor_kind === 'document_block').length;
      const anchored = sceneCount + documentCount;
      track.coverage = {
        total_beats: track.beats.length,
        anchored_beats: anchored,
        unanchored_beats: track.beats.length - anchored,
        scene_anchored_beats: sceneCount,
        document_anchored_beats: documentCount,
        coverage_percent: track.beats.length ? Math.round(anchored / track.beats.length * 100) : 0,
        status: track.beats.length === 0 ? 'empty' : anchored === 0 ? 'unanchored' : anchored === track.beats.length ? 'complete' : 'partial',
        out_of_order_beat_ids: [],
      };
    });
    const totalBeats = snapshot.tracks.reduce((sum, track) => sum + track.beats.length, 0);
    const anchored = snapshot.tracks.reduce((sum, track) => sum + track.coverage.anchored_beats, 0);
    snapshot.summary = {
      total_tracks: snapshot.tracks.length,
      total_beats: totalBeats,
      anchored_beats: anchored,
      unanchored_beats: totalBeats - anchored,
      coverage_percent: totalBeats ? Math.round(anchored / totalBeats * 100) : 0,
      by_kind: { story: 0, character: 0, relationship: 0, theme: 0, world: 0, custom: 0 },
      by_status: { empty: 0, unanchored: 0, partial: 0, complete: 0 },
    };
    for (const track of snapshot.tracks) {
      snapshot.summary.by_kind[track.kind] += 1;
      snapshot.summary.by_status[track.coverage.status] += 1;
    }
    revisionCounter += 1;
    snapshot.revision = revisionCounter.toString(16).padStart(64, '0');
  };
  const compatibilityApi = {
    importWhiteboard: async () => ({ project_id: 92, title: 'Compatibility import', mode: 'novel', scenes_created: 0, scene_titles: [], scene_ids_by_block: [] }),
    createPsyke: async (_projectId: number, body: Record<string, unknown>) => ({
      id: body.name === 'Artifact' ? 2505 : 2506,
      ...body,
    }),
    createProgression: async (_projectId: number, body: Record<string, unknown>) => {
      legacyWrites.push(body);
      let compatibilityTrack = snapshot.tracks.find((track) => track.id === 4100);
      if (!compatibilityTrack) {
        compatibilityTrack = {
          id: 4100, project_id: 92, kind: 'custom', title: 'Artifact', description: '', color_label: '', sort_order: snapshot.tracks.length,
          legacy_compatibility: true,
          primary_psyke_entry_id: 2505, primary_psyke_entry_name: 'Artifact', primary_psyke_entry_type: 'other',
          secondary_psyke_entry_id: null, secondary_psyke_entry_name: '', secondary_psyke_entry_type: '', beats: [],
          coverage: { total_beats: 0, anchored_beats: 0, unanchored_beats: 0, scene_anchored_beats: 0, document_anchored_beats: 0, coverage_percent: 0, status: 'empty', out_of_order_beat_ids: [] },
        };
        snapshot.tracks.push(compatibilityTrack);
      }
      const id = body.text === 'Artifact appears' ? 9101 : 9102;
      compatibilityTrack.beats.push({ id, track_id: 4100, text: String(body.text), sort_order: compatibilityTrack.beats.length, anchor_kind: 'unanchored', scene_id: null, scene_title: '', anchor_ref: null, anchor_label: '' });
      refreshCompatibilitySnapshot();
      return { id, entry_id: body.entry_id, text: body.text, scene_id: null, scene_title: '', sort_order: compatibilityTrack.beats.length - 1 };
    },
    getProgressions: async () => structuredClone(snapshot),
    getProgressionCommandReceipt: async () => { throw new Error('receipt should not be needed'); },
    executeProgressionCommand: async (_projectId: number, command: ProgressionCommandDTO) => {
      canonicalCommands.push(command);
      let createdTrackId: number | null = null;
      let createdBeatId: number | null = null;
      if (command.kind === 'update_track') {
        const track = snapshot.tracks.find((candidate) => candidate.id === command.track_id)!;
        if (command.title !== undefined) track.title = command.title;
        if (command.description !== undefined) track.description = command.description;
        if (command.color_label !== undefined) track.color_label = command.color_label;
      } else if (command.kind === 'update_beat') {
        const beat = snapshot.tracks.flatMap((track) => track.beats).find((candidate) => candidate.id === command.beat_id)!;
        if (command.text !== undefined) beat.text = command.text;
        if (command.anchor_kind !== undefined) beat.anchor_kind = command.anchor_kind;
        if (command.scene_id !== undefined) beat.scene_id = command.scene_id;
        if (command.anchor_ref !== undefined) beat.anchor_ref = command.anchor_ref;
        if (command.anchor_label !== undefined) beat.anchor_label = command.anchor_label;
      } else if (command.kind === 'reorder_beats') {
        const track = snapshot.tracks.find((candidate) => candidate.id === command.track_id)!;
        track.beats = command.beat_ids.map((id) => track.beats.find((beat) => beat.id === id)!);
      } else if (command.kind === 'create_track') {
        createdTrackId = 4200;
        snapshot.tracks.push({
          id: createdTrackId, project_id: 92, kind: command.track_kind, title: command.title,
          description: command.description ?? '', color_label: command.color_label ?? '', sort_order: snapshot.tracks.length,
          legacy_compatibility: false,
          primary_psyke_entry_id: null, primary_psyke_entry_name: '', primary_psyke_entry_type: '',
          secondary_psyke_entry_id: null, secondary_psyke_entry_name: '', secondary_psyke_entry_type: '', beats: [],
          coverage: { total_beats: 0, anchored_beats: 0, unanchored_beats: 0, scene_anchored_beats: 0, document_anchored_beats: 0, coverage_percent: 0, status: 'empty', out_of_order_beat_ids: [] },
        });
      } else if (command.kind === 'create_beat') {
        createdBeatId = 9200;
        snapshot.tracks.find((track) => track.id === command.track_id)!.beats.push({
          id: createdBeatId, track_id: command.track_id, text: command.text, sort_order: 0,
          anchor_kind: command.anchor_kind ?? 'unanchored', scene_id: command.scene_id ?? null,
          scene_title: '', anchor_ref: command.anchor_ref ?? null, anchor_label: command.anchor_label ?? '',
        });
      } else if (command.kind === 'reorder_tracks') {
        snapshot.tracks = command.track_ids.map((id) => snapshot.tracks.find((track) => track.id === id)!);
      }
      refreshCompatibilitySnapshot();
      return {
        progressions: structuredClone(snapshot), changed: true,
        affected_track_ids: [], affected_beat_ids: [], created_track_id: createdTrackId,
        created_beat_id: createdBeatId, replayed: false, applied_revision: snapshot.revision,
      };
    },
    createOutlineNode: async () => { throw new Error('unexpected outline'); },
  } as unknown as ApiClient;
  const compatibilityBundle: ProjectBundle = {
    format: BUNDLE_FORMAT,
    version: '1.0',
    project: {
      manuscript: { blocks: [] },
      psyke: {
        elements: [
          { id: '5', name: 'Artifact', entry_type: 'other' },
          { id: '6', name: 'Hero', entry_type: 'character' },
        ],
        progressions: [
          { id: 71, entry_id: 5, text: 'Artifact appears', scene_id: null, scene_title: '', sort_order: 1 },
          { id: 72, entry_id: 5, text: '', scene_id: null, scene_title: '', sort_order: 0 },
          { id: 80, entry_id: 6, text: 'Stale unmatched projection', scene_id: null, scene_title: '', sort_order: 0 },
        ],
      },
      progression_tracks: [{
        id: 13, kind: 'story', title: 'Whole story', description: 'Primary narrative.', color_label: 'blue', sort_order: 0,
        legacy_compatibility: false,
        primary_psyke_entry_id: null, primary_psyke_entry_name: '', primary_psyke_entry_type: '',
        secondary_psyke_entry_id: null, secondary_psyke_entry_name: '', secondary_psyke_entry_type: '',
        beats: [{ id: 81, track_id: 13, text: 'The story turns.', sort_order: 0, anchor_kind: 'unanchored', scene_id: null, scene_title: '', anchor_ref: null, anchor_label: '' }],
      }, {
        id: 12, kind: 'custom', title: 'Artifact arc', description: 'Ancient object progression.', color_label: 'violet', sort_order: 1,
        legacy_compatibility: true,
        primary_psyke_entry_id: 5, primary_psyke_entry_name: 'Artifact', primary_psyke_entry_type: 'other',
        secondary_psyke_entry_id: null, secondary_psyke_entry_name: '', secondary_psyke_entry_type: '',
        beats: [
          { id: 71, track_id: 12, text: 'Artifact appears', sort_order: 0, anchor_kind: 'document_block', scene_id: null, scene_title: '', anchor_ref: 'drafter:relic', anchor_label: 'Relic draft' },
          { id: 72, track_id: 12, text: '', sort_order: 1, anchor_kind: 'unanchored', scene_id: null, scene_title: '', anchor_ref: null, anchor_label: '' },
        ],
      }],
    },
  };
  const imported = await importProjectBundle(compatibilityApi, compatibilityBundle);
  check(
    'canonical compatibility track imports exactly once through legacy linkage path',
    legacyWrites.length === 2 &&
      legacyWrites.every((body) => body.entry_id === 2505) &&
      canonicalCommands.some((command) => command.kind === 'update_track' && command.track_id === 4100 && command.title === 'Artifact arc' && command.description === 'Ancient object progression.' && command.color_label === 'violet' && command.track_kind === undefined && command.primary_psyke_entry_id === undefined),
  );
  const documentAnchorUpdate = canonicalCommands.find((command) => command.kind === 'update_beat' && command.beat_id === 9101);
  const blankBeatUpdate = canonicalCommands.find((command) => command.kind === 'update_beat' && command.beat_id === 9102);
  const compatibilityReorder = canonicalCommands.find((command) => command.kind === 'reorder_beats' && command.track_id === 4100);
  const globalReorder = canonicalCommands.find((command) => command.kind === 'reorder_tracks');
  check(
    'canonical compatibility import restores document anchor and beat/global ordering',
    documentAnchorUpdate?.kind === 'update_beat' && documentAnchorUpdate.anchor_kind === 'document_block' && documentAnchorUpdate.anchor_ref === 'drafter:relic' && documentAnchorUpdate.anchor_label === 'Relic draft' &&
      blankBeatUpdate?.kind === 'update_beat' && blankBeatUpdate.text === undefined &&
      compatibilityReorder?.kind === 'reorder_beats' && compatibilityReorder.beat_ids.join(',') === '9101,9102' &&
      globalReorder?.kind === 'reorder_tracks' && globalReorder.track_ids.join(',') === '4200,4100',
  );
  check(
    'canonical compatibility import excludes unmatched legacy rows and reports canonical items once',
    !legacyWrites.some((body) => body.text === 'Stale unmatched projection') &&
      imported.progressions === 0 && imported.progressionsSkipped === 0 &&
      imported.progressionTracks === 2 && imported.progressionTrackBeats === 3 &&
      imported.progressionTracksSkipped === 0 && imported.progressionTrackBeatsSkipped === 0,
  );
}

// Explicit compatibility provenance also preserves an empty legacy track. The
// importer materializes its protected Core linkage with one temporary blank
// legacy beat, restores presentation through canonical commands, then deletes
// the temporary beat so the destination remains genuinely empty.
{
  const commands: ProgressionCommandDTO[] = [];
  let legacyCreates = 0;
  let revisionCounter = 0;
  let snapshot: ProgressionSnapshotDTO = {
    project_id: 94,
    revision: '0'.repeat(64),
    tracks: [],
    summary: {
      total_tracks: 0, total_beats: 0, anchored_beats: 0, unanchored_beats: 0, coverage_percent: 0,
      by_kind: { story: 0, character: 0, relationship: 0, theme: 0, world: 0, custom: 0 },
      by_status: { empty: 0, unanchored: 0, partial: 0, complete: 0 },
    },
  };
  const touch = () => {
    revisionCounter += 1;
    snapshot.revision = revisionCounter.toString(16).padStart(64, '0');
    snapshot.summary.total_tracks = snapshot.tracks.length;
    snapshot.summary.total_beats = snapshot.tracks.reduce((sum, track) => sum + track.beats.length, 0);
    snapshot.summary.unanchored_beats = snapshot.summary.total_beats;
    snapshot.summary.by_kind.custom = snapshot.tracks.length;
    snapshot.summary.by_status.empty = snapshot.tracks.filter((track) => track.beats.length === 0).length;
    snapshot.summary.by_status.unanchored = snapshot.tracks.filter((track) => track.beats.length > 0).length;
  };
  const emptyCompatibilityApi = {
    importWhiteboard: async () => ({ project_id: 94, title: 'Empty compatibility', mode: 'novel', scenes_created: 0, scene_titles: [], scene_ids_by_block: [] }),
    createPsyke: async (_projectId: number, body: Record<string, unknown>) => ({ id: 2701, ...body }),
    createProgression: async (_projectId: number, body: Record<string, unknown>) => {
      legacyCreates += 1;
      snapshot.tracks = [{
        id: 4701, project_id: 94, kind: 'custom', title: 'Cipher', description: '', color_label: '', sort_order: 0,
        legacy_compatibility: true,
        primary_psyke_entry_id: 2701, primary_psyke_entry_name: 'Cipher', primary_psyke_entry_type: 'artifact',
        secondary_psyke_entry_id: null, secondary_psyke_entry_name: '', secondary_psyke_entry_type: '',
        beats: [{ id: 9701, track_id: 4701, text: String(body.text), sort_order: 0, anchor_kind: 'unanchored', scene_id: null, scene_title: '', anchor_ref: null, anchor_label: '' }],
        coverage: { total_beats: 1, anchored_beats: 0, unanchored_beats: 1, scene_anchored_beats: 0, document_anchored_beats: 0, coverage_percent: 0, status: 'unanchored', out_of_order_beat_ids: [] },
      }];
      touch();
      return { id: 9701, entry_id: body.entry_id, text: body.text, scene_id: null, scene_title: '', sort_order: 0 };
    },
    getProgressions: async () => structuredClone(snapshot),
    getProgressionCommandReceipt: async () => { throw new Error('receipt should not be needed'); },
    executeProgressionCommand: async (_projectId: number, command: ProgressionCommandDTO) => {
      commands.push(command);
      if (command.kind === 'update_track') {
        const track = snapshot.tracks[0]!;
        if (command.title !== undefined) track.title = command.title;
        if (command.description !== undefined) track.description = command.description;
        if (command.color_label !== undefined) track.color_label = command.color_label;
      } else if (command.kind === 'delete_beat') {
        snapshot.tracks[0]!.beats = [];
        snapshot.tracks[0]!.coverage = { total_beats: 0, anchored_beats: 0, unanchored_beats: 0, scene_anchored_beats: 0, document_anchored_beats: 0, coverage_percent: 0, status: 'empty', out_of_order_beat_ids: [] };
      }
      touch();
      return { progressions: structuredClone(snapshot), changed: true, affected_track_ids: [], affected_beat_ids: [], created_track_id: null, created_beat_id: null, replayed: false, applied_revision: snapshot.revision };
    },
    createOutlineNode: async () => { throw new Error('unexpected outline'); },
  } as unknown as ApiClient;
  const imported = await importProjectBundle(emptyCompatibilityApi, {
    format: BUNDLE_FORMAT,
    version: '1.0',
    project: {
      manuscript: { blocks: [] },
      psyke: { elements: [{ id: '14', name: 'Cipher', entry_type: 'artifact' }], progressions: [] },
      progression_tracks: [{
        id: 140, kind: 'custom', title: 'Cipher lifecycle', description: 'Reserved for later.', color_label: 'amber', sort_order: 0,
        legacy_compatibility: true,
        primary_psyke_entry_id: 14, primary_psyke_entry_name: 'Cipher', primary_psyke_entry_type: 'artifact',
        secondary_psyke_entry_id: null, secondary_psyke_entry_name: '', secondary_psyke_entry_type: '', beats: [],
      }],
    },
  });
  const metadata = commands.find((command) => command.kind === 'update_track');
  check(
    'empty legacy compatibility track restores protected linkage and presentation',
    legacyCreates === 1 && metadata?.kind === 'update_track' && metadata.title === 'Cipher lifecycle' &&
      metadata.description === 'Reserved for later.' && metadata.color_label === 'amber' &&
      metadata.track_kind === undefined && metadata.primary_psyke_entry_id === undefined,
  );
  check(
    'empty legacy compatibility track removes temporary beat and reports no phantom beat',
    commands.some((command) => command.kind === 'delete_beat' && command.beat_id === 9701) &&
      snapshot.tracks[0]?.beats.length === 0 && imported.progressionTracks === 1 &&
      imported.progressionTrackBeats === 0 && imported.progressionTrackBeatsSkipped === 0,
  );
}

// The mere presence of an empty canonical section is authoritative; it must
// suppress compatibility rows left in the legacy projection.
{
  let legacyWrites = 0;
  const emptyCanonicalApi = {
    importWhiteboard: async () => ({ project_id: 93, title: 'Empty canonical import', mode: 'novel', scenes_created: 0, scene_titles: [], scene_ids_by_block: [] }),
    createPsyke: async (_projectId: number, body: Record<string, unknown>) => ({ id: 2601, ...body }),
    createProgression: async () => { legacyWrites += 1; throw new Error('authoritative empty canonical section must suppress legacy rows'); },
    createOutlineNode: async () => { throw new Error('unexpected outline'); },
  } as unknown as ApiClient;
  const imported = await importProjectBundle(emptyCanonicalApi, {
    format: BUNDLE_FORMAT,
    version: '1.0',
    project: {
      manuscript: { blocks: [] },
      psyke: {
        elements: [{ id: '1', name: 'Hero', entry_type: 'character' }],
        progressions: [{ id: 1, entry_id: 1, text: 'Legacy projection', scene_id: null, scene_title: '', sort_order: 0 }],
      },
      progression_tracks: [],
    },
  });
check(
    'empty canonical progression_tracks suppresses legacy compatibility import',
    legacyWrites === 0 && imported.progressions === 0 && imported.progressionsSkipped === 0,
  );
}

// Canonical bundle commands use the same durable-delivery boundary as the live
// panel: only an ambiguous write plus a proven receipt miss permits one exact
// same-key resend. Definitive errors and inconclusive receipt lookups never
// resend, and a second ambiguous miss aborts before dependent writes.
{
  const deliveryBundle = (withBeat = false): ProjectBundle => ({
    format: BUNDLE_FORMAT,
    version: '1.0',
    project: {
      manuscript: { blocks: [] },
      progression_tracks: [{
        id: 1, kind: 'story', title: 'Delivery arc', description: '', color_label: '',
        sort_order: 0, legacy_compatibility: false,
        primary_psyke_entry_id: null, secondary_psyke_entry_id: null,
        beats: withBeat ? [{
          id: 2, track_id: 1, text: 'Dependent beat', sort_order: 0,
          anchor_kind: 'unanchored', scene_id: null, anchor_ref: null, anchor_label: '',
        }] : [],
      }],
    },
  });
  const emptySnapshot = (): ProgressionSnapshotDTO => ({
    project_id: 95,
    revision: '0'.repeat(64),
    tracks: [],
    summary: {
      total_tracks: 0, total_beats: 0, anchored_beats: 0, unanchored_beats: 0,
      coverage_percent: 0,
      by_kind: { story: 0, character: 0, relationship: 0, theme: 0, world: 0, custom: 0 },
      by_status: { empty: 0, unanchored: 0, partial: 0, complete: 0 },
    },
  });
  const committedSnapshot = (): ProgressionSnapshotDTO => ({
    project_id: 95,
    revision: '1'.padStart(64, '0'),
    tracks: [{
      id: 9501, project_id: 95, kind: 'story', title: 'Delivery arc', description: '',
      color_label: '', sort_order: 0, legacy_compatibility: false,
      primary_psyke_entry_id: null, primary_psyke_entry_name: '', primary_psyke_entry_type: '',
      secondary_psyke_entry_id: null, secondary_psyke_entry_name: '', secondary_psyke_entry_type: '',
      beats: [],
      coverage: {
        total_beats: 0, anchored_beats: 0, unanchored_beats: 0,
        scene_anchored_beats: 0, document_anchored_beats: 0, coverage_percent: 0,
        status: 'empty', out_of_order_beat_ids: [],
      },
    }],
    summary: {
      total_tracks: 1, total_beats: 0, anchored_beats: 0, unanchored_beats: 0,
      coverage_percent: 0,
      by_kind: { story: 1, character: 0, relationship: 0, theme: 0, world: 0, custom: 0 },
      by_status: { empty: 1, unanchored: 0, partial: 0, complete: 0 },
    },
  });
  const baseDeliveryApi = {
    importWhiteboard: async () => ({ project_id: 95, title: 'Delivery', mode: 'novel', scenes_created: 0, scene_titles: [], scene_ids_by_block: [] }),
    createOutlineNode: async () => { throw new Error('unexpected outline'); },
  };

  let definitiveWrites = 0;
  let definitiveReceipts = 0;
  const definitiveResult = await importProjectBundle({
    ...baseDeliveryApi,
    getProgressions: async () => emptySnapshot(),
    executeProgressionCommand: async () => {
      definitiveWrites += 1;
      throw new ApiRequestError('POST', '/progressions/commands', 400, 'invalid command');
    },
    getProgressionCommandReceipt: async () => {
      definitiveReceipts += 1;
      throw new Error('receipt must not be checked');
    },
  } as unknown as ApiClient, deliveryBundle());
  check(
    'bundle progression definitive 400 is not resent or receipt-checked',
    definitiveWrites === 1 && definitiveReceipts === 0 && definitiveResult.progressionTracksSkipped === 1,
  );

  let receiptFailureWrites = 0;
  let receiptFailureChecks = 0;
  let receiptFailureRejected = false;
  try {
    await importProjectBundle({
      ...baseDeliveryApi,
      getProgressions: async () => emptySnapshot(),
      executeProgressionCommand: async () => {
        receiptFailureWrites += 1;
        throw new ApiRequestTimeoutError('POST', '/progressions/commands', 1);
      },
      getProgressionCommandReceipt: async () => {
        receiptFailureChecks += 1;
        throw new ApiRequestError('GET', '/progressions/command-receipt', 503, 'unavailable');
      },
    } as unknown as ApiClient, deliveryBundle());
  } catch (error) {
    receiptFailureRejected = error instanceof Error && error.message.includes('receipt lookup was inconclusive');
  }
  check(
    'bundle progression inconclusive receipt lookup never resends',
    receiptFailureRejected && receiptFailureWrites === 1 && receiptFailureChecks === 1,
  );

  let committed = false;
  let lostResponseWrites = 0;
  let lostResponseReceipts = 0;
  const recoveredResult = await importProjectBundle({
    ...baseDeliveryApi,
    getProgressions: async () => structuredClone(committed ? committedSnapshot() : emptySnapshot()),
    executeProgressionCommand: async () => {
      lostResponseWrites += 1;
      committed = true;
      throw new ApiRequestTimeoutError('POST', '/progressions/commands', 1);
    },
    getProgressionCommandReceipt: async () => {
      lostResponseReceipts += 1;
      return {};
    },
  } as unknown as ApiClient, deliveryBundle());
  check(
    'bundle progression recovers commit after lost response without resend',
    lostResponseWrites === 1 && lostResponseReceipts === 1 && recoveredResult.progressionTracks === 1,
  );

  const ambiguousKeys: string[] = [];
  let secondMissReceipts = 0;
  let secondMissRejected = false;
  try {
    await importProjectBundle({
      ...baseDeliveryApi,
      getProgressions: async () => emptySnapshot(),
      executeProgressionCommand: async (_projectId: number, _command: ProgressionCommandDTO, key: string) => {
        ambiguousKeys.push(key);
        throw new ApiRequestTimeoutError('POST', '/progressions/commands', 1);
      },
      getProgressionCommandReceipt: async () => {
        secondMissReceipts += 1;
        throw new ApiRequestError('GET', '/progressions/command-receipt', 404, '', 'progression_receipt_not_found');
      },
    } as unknown as ApiClient, deliveryBundle(true));
  } catch (error) {
    secondMissRejected = error instanceof Error && error.message.includes('Bundle import stopped');
  }
  check(
    'bundle progression second ambiguous receipt miss fails closed with one same-key resend',
    secondMissRejected && ambiguousKeys.length === 2 && new Set(ambiguousKeys).size === 1 && secondMissReceipts === 2,
  );

  let ambiguousLegacyWrites = 0;
  let ambiguousLegacyRejected = false;
  try {
    await importProjectBundle({
      importWhiteboard: async () => ({ project_id: 96, title: 'Legacy delivery', mode: 'novel', scenes_created: 0, scene_titles: [], scene_ids_by_block: [] }),
      createPsyke: async () => ({ id: 9601 }),
      createProgression: async () => {
        ambiguousLegacyWrites += 1;
        throw new ApiRequestTimeoutError('POST', '/psyke/progressions', 1);
      },
      createOutlineNode: async () => { throw new Error('unexpected outline'); },
    } as unknown as ApiClient, {
      format: BUNDLE_FORMAT,
      version: '1.0',
      project: {
        manuscript: { blocks: [] },
        psyke: {
          elements: [{ id: '1', name: 'Legacy subject', entry_type: 'other' }],
          progressions: [{ id: 1, entry_id: 1, text: 'Possibly committed', scene_id: null, sort_order: 0 }],
        },
      },
    });
  } catch (error) {
    ambiguousLegacyRejected = error instanceof Error && error.message.includes('has no durable receipt');
  }
  check(
    'legacy compatibility POST is never retried after an ambiguous outcome',
    ambiguousLegacyRejected && ambiguousLegacyWrites === 1,
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
