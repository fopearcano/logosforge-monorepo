/**
 * Import/Export format tests. Pure — no Electron/DOM/network. Runs headlessly
 * (esbuild + node): `npm run test:import-export`. Throws (non-zero) on failure.
 */

import type { WhiteboardBlock, WhiteboardDocument } from '../whiteboard/types';
import type { PendingDocumentConflictRecovery } from '../../api/backend';
import {
  ImportError,
  LOGOSFORGE_FORMAT,
  OUTLINE_CONFLICT_FORMAT,
  PENDING_DOCUMENT_RECOVERY_FORMAT,
  WHITEBOARD_CONFLICT_FORMAT,
  assertRecoveryImportTargetStillActive,
  buildCommentsReport,
  buildExport,
  buildLogosforgeEnvelope,
  looksBinary,
  parseFdx,
  parseImport,
  parseLogosforge,
  recoveryImportIdentityRelationship,
  suggestedExportName,
  type ExportComment,
  type ExportPayload,
} from './importExportFormats';
import {
  applyRecoveryImport,
  confirmRecoveryImportSteps,
  runRecoveryImportAfterPreflight,
} from './recoveryImportApplication';
import { pendingDocumentRecoveryEnvelope } from './pendingRecoveryCopy';
import { blocksToFdx } from '../screenplay/screenplayExport';
import { outlineConflictEnvelope } from '../outline/outlineConflictCopy';
import { whiteboardConflictEnvelope } from '../whiteboard/whiteboardConflictCopy';

let passed = 0;
const failures: string[] = [];
function check(label: string, cond: boolean) {
  if (cond) passed += 1;
  else failures.push(label);
}
function throws(label: string, fn: () => unknown) {
  try {
    fn();
    failures.push(label + ' (expected throw)');
  } catch {
    passed += 1;
  }
}
async function asyncTest(label: string, fn: () => Promise<void>) {
  try {
    await fn();
    passed += 1;
  } catch (error) {
    failures.push(`${label}: ${error instanceof Error ? error.message : String(error)}`);
  }
}

const texts = (blocks: WhiteboardBlock[]) => blocks.map((b) => b.text);
const sampleSettings = {
  sceneHeadingStyle: 'bold',
  blankLinesBeforeScene: 1,
  includeOutline: false,
  typeface: 'courier-prime',
  showInvisibles: true,
} as ExportPayload['settings'];

const payload = (over: Partial<ExportPayload> = {}): ExportPayload => ({
  title: 'My Script',
  mode: 'screenplay',
  blocks: [
    { id: 'b0', type: 'heading', text: 'Act One', level: 1 },
    { id: 'b1', type: 'paragraph', text: 'INT. HOUSE - DAY' },
    { id: 'b2', type: 'paragraph', text: 'She opens the door.' },
  ],
  settings: sampleSettings,
  outline: [],
  ...over,
});

// 1. Import TXT / MD: lines → blocks, `#` → heading; markdown bullets preserved.
{
  const r = parseImport('txt', '# Title\nA line\n- bullet one\n- bullet two');
  check('txt heading', r.blocks[0].type === 'heading' && r.blocks[0].text === 'Title');
  check('txt paragraph', r.blocks[1].text === 'A line');
  check('md bullet preserved verbatim', texts(parseImport('md', '- a\n- b').blocks).join('|') === '- a|- b');
  check('txt does not force a mode', r.mode === undefined);
}

// 2. Import Fountain forces Screenplay mode.
{
  const r = parseImport('fountain', 'INT. HOUSE - DAY\n\nAction here.');
  check('fountain forces screenplay', r.mode === 'screenplay');
  check('fountain keeps text', texts(r.blocks).includes('INT. HOUSE - DAY'));
}

// 3. Binary detection → friendly error.
check('looksBinary true on NUL', looksBinary('abc\u0000def'));
check('looksBinary false on text', !looksBinary('plain text'));
throws('binary import rejected', () => parseImport('txt', 'PNG\u0000binary'));

// 4. FDX import foundation.
{
  const fdx = `<?xml version="1.0" encoding="UTF-8"?>
<FinalDraft DocumentType="Script" Version="1"><Content>
<Paragraph Type="Scene Heading"><Text>INT. HOUSE - DAY</Text></Paragraph>
<Paragraph Type="Action"><Text>She enters &amp; sits.</Text></Paragraph>
<Paragraph Type="Character"><Text>JANE</Text></Paragraph>
<Paragraph Type="Parenthetical"><Text>quietly</Text></Paragraph>
<Paragraph Type="Dialogue"><Text>Hello there.</Text></Paragraph>
<Paragraph Type="Transition"><Text>CUT TO:</Text></Paragraph>
</Content></FinalDraft>`;
  const r = parseFdx(fdx);
  const t = texts(r.blocks);
  check('fdx → screenplay', r.mode === 'screenplay');
  check('fdx scene heading', t.includes('INT. HOUSE - DAY'));
  check('fdx action + entity decode', t.includes('She enters & sits.'));
  check('fdx character', t.includes('JANE'));
  check('fdx parenthetical wrapped', t.includes('(quietly)'));
  check('fdx dialogue', t.includes('Hello there.'));
  check('fdx transition', t.includes('CUT TO:'));
  // forced scene heading when not already a slug
  check('fdx forces non-slug scene', texts(parseFdx('<Paragraph Type="Scene Heading"><Text>The Beach</Text></Paragraph>').blocks).includes('.THE BEACH'));
  throws('fdx invalid rejected', () => parseFdx('just some plain text, not xml'));
}

// 5. LogosForge envelope round-trip (content + mode + settings + title).
{
  const env = buildLogosforgeEnvelope(payload({ outline: [{ id: 'n1', parentId: null, type: 'act', title: 'Act One', summary: 'The setup and inciting incident.', order: 0, collapsed: false, completed: false, status: 'none', tags: [], colorLabel: 'none', createdAt: '2026-09-25T00:00:00Z', updatedAt: '2026-09-25T00:00:00Z' }] }));
  check('envelope format', env.format === LOGOSFORGE_FORMAT);
  check('envelope version', env.version === '1.0');
  const json = JSON.stringify(env);
  check('envelope embeds no file paths', !json.includes('filePath') && !json.includes('/home') && !json.includes('\\Users'));
  const r = parseLogosforge(json);
  check('envelope round-trips mode', r.mode === 'screenplay');
  check('envelope round-trips title', r.title === 'My Script');
  check('envelope round-trips content', texts(r.blocks).includes('INT. HOUSE - DAY'));
  check('envelope round-trips settings', r.settings?.typeface === 'courier-prime');
  check('envelope round-trips outline', (r.outline?.length ?? 0) === 1 && r.outline?.[0].title === 'Act One');
  check('envelope round-trips outline summary', r.outline?.[0].summary === 'The setup and inciting incident.');
}

// 6. LogosForge tolerates the raw JSON export shape ({title, mode, blocks}).
{
  const raw = buildExport('json', payload());
  const obj = JSON.parse(raw) as { title: string; mode: string; blocks: unknown[] };
  check('json export shape', obj.title === 'My Script' && obj.mode === 'screenplay' && obj.blocks.length === 3);
  const r = parseLogosforge(raw);
  check('raw json imports blocks', texts(r.blocks).includes('She opens the door.'));
  check('raw json imports mode', r.mode === 'screenplay');
}

// 7. LogosForge validation errors.
throws('invalid JSON rejected', () => parseLogosforge('{not json'));
throws('wrong format rejected', () => parseLogosforge('{"format":"something-else","document":{"content":"x"}}'));
throws('no content rejected', () => parseLogosforge('{"format":"logosforge-whiteboard","document":{}}'));

// 8. Text/MD/Fountain export = the shared serialization (# headings preserved).
{
  const txt = buildExport('txt', payload());
  check('export txt has heading', txt.includes('# Act One'));
  check('export fountain equals txt serialization', buildExport('fountain', payload()) === txt);
  check('export md equals txt serialization', buildExport('md', payload()) === txt);
}

// 9. HTML export: headings + paragraphs, escaped, titled.
{
  const html = buildExport('html', payload({ blocks: [{ id: 'h', type: 'heading', text: 'A & B', level: 2 }, { id: 'p', type: 'paragraph', text: '<script>x</script>' }] }));
  check('html h2', html.includes('<h2>A &amp; B</h2>'));
  check('html escapes paragraph', html.includes('&lt;script&gt;x&lt;/script&gt;') && !html.includes('<script>x'));
  check('html has title', html.includes('<title>My Script</title>'));
}

// 10. Suggested export filename swaps the extension.
check('suggested swaps ext', suggestedExportName('script.fountain', 'logosforge') === 'script.logosforge');
check('suggested untitled fallback', suggestedExportName('', 'txt') === 'untitled.txt');
check('suggested no-ext stem', suggestedExportName('notes', 'md') === 'notes.md');

// 11. ImportError type is thrown for friendly failures.
{
  let isImportError = false;
  try {
    parseLogosforge('nope');
  } catch (e) {
    isImportError = e instanceof ImportError;
  }
  check('parse failures are ImportError', isImportError);
}

// 12. buildCommentsReport — grouping, location (nearest heading), quote + body.
{
  const comments: ExportComment[] = [
    { quote: 'the door', body: 'tense beat here', resolved: false, blockIndex: 2 },
    { quote: 'Act One', body: 'rename this act', resolved: true, blockIndex: 0 },
    { quote: 'orphan line', body: '', resolved: false, blockIndex: 1 },
  ];
  const md = buildCommentsReport(payload({ comments }), '2026-06-29T00:00:00.000Z');
  check('report title', md.startsWith('# Comments — My Script'));
  check('report counts', md.includes('3 comments · 2 open · 1 resolved · exported 2026-06-29'));
  check('report has Open + Resolved sections', md.includes('## Open') && md.includes('## Resolved'));
  check('report uses nearest heading as location', md.includes('### 1. Act One'));
  check('report quotes the span', md.includes('> the door'));
  check('report shows body', md.includes('tense beat here'));
  check('report marks empty notes', md.includes('_(empty note)_'));
  check('report includes resolved body', md.includes('rename this act'));
}

// 13. buildCommentsReport — falls back to ¶ number when no heading precedes.
{
  const md = buildCommentsReport(
    {
      title: 'T',
      mode: 'novel',
      blocks: [
        { id: 'b0', type: 'paragraph', text: 'first para' },
        { id: 'b1', type: 'paragraph', text: 'second para' },
      ],
      settings: sampleSettings,
      outline: [],
      comments: [{ quote: 'second', body: 'note', resolved: false, blockIndex: 1 }],
    },
    '2026-06-29T00:00:00.000Z',
  );
  check('report paragraph-number fallback', md.includes('### 1. ¶ 2'));
}

// 14. No comments → explicit empty marker; buildExport routes 'comments'.
{
  const empty = buildCommentsReport(payload({ comments: [] }), '2026-06-29T00:00:00.000Z');
  check('empty report', empty.includes('0 comments') && empty.includes('_No comments._'));
  const md = buildExport('comments', payload({ comments: [{ quote: 'x', body: 'y', resolved: false, blockIndex: 1 }] }));
  check('buildExport routes comments', md.startsWith('# Comments — My Script') && md.includes('> x'));
}

// 15. FDX export (blocksToFdx) — typed paragraphs, XML-escaped, round-trips via parseFdx.
{
  const sp: WhiteboardBlock[] = [
    { id: 'b0', type: 'paragraph', text: 'INT. HOUSE - DAY' },
    { id: 'b1', type: 'paragraph', text: 'She opens the door & waits.' },
    { id: 'b2', type: 'paragraph', text: 'MARA' },
    { id: 'b3', type: 'paragraph', text: 'Hello.' },
  ];
  const fdx = blocksToFdx(sp);
  check('fdx FinalDraft root', fdx.includes('<FinalDraft') && fdx.includes('</FinalDraft>'));
  check('fdx scene-heading paragraph', fdx.includes('Type="Scene Heading"'));
  check('fdx character paragraph', fdx.includes('Type="Character"'));
  check('fdx escapes ampersand', fdx.includes('door &amp; waits'));
  const back = parseFdx(fdx);
  check('fdx round-trips to screenplay', back.mode === 'screenplay');
  check('fdx round-trip keeps slug', texts(back.blocks).some((t) => t.includes('INT. HOUSE - DAY')));
}

// 16. Conflict/recovery JSON is strictly parsed into scope + untrusted provenance.
const recoveryIso = '2026-09-25T12:00:00.000Z';
const sourceIncarnation = 'a'.repeat(32);
const targetIncarnation = 'b'.repeat(32);
const sourceRevision = '1'.repeat(32);
const currentRevision = '2'.repeat(32);
const recoveryBlocks: WhiteboardBlock[] = [
  {
    id: 'recovered-block',
    type: 'paragraph',
    text: 'Recovered bold text',
    marks: [{ type: 'bold', from: 10, to: 14 }],
  },
];
const recoveryOutline = [{
  id: 'root',
  parentId: null,
  type: 'chapter' as const,
  title: 'Recovered chapter',
  summary: 'A complete outline snapshot.',
  order: 0,
  collapsed: false,
  completed: false,
  status: 'drafting' as const,
  tags: ['recovered'],
  colorLabel: 'blue' as const,
  linkedLineId: null,
  link: { blockIndex: 0, quote: 'Recovered', blockId: 'recovered-block' },
  createdAt: recoveryIso,
  updatedAt: recoveryIso,
}];
const recoveredDocument = {
  id: '41',
  incarnation: sourceIncarnation,
  revision: sourceRevision,
  title: 'Recovered title',
  mode: 'novel',
  blocks: recoveryBlocks,
  settings: sampleSettings,
  updated_at: recoveryIso,
};
const whiteboardConflict = {
  format: WHITEBOARD_CONFLICT_FORMAT,
  version: 1,
  document_id: '41',
  incarnation: sourceIncarnation,
  base_revision: sourceRevision,
  exported_at: recoveryIso,
  pending_patch: {
    title: recoveredDocument.title,
    mode: recoveredDocument.mode,
    blocks: recoveryBlocks,
    settings: sampleSettings,
  },
  document: recoveredDocument,
};
const outlineConflict = outlineConflictEnvelope(
  '41',
  sourceIncarnation,
  sourceRevision,
  recoveryOutline,
  recoveryIso,
);
const pendingRecovery = (kind: 'whiteboard' | 'outline') => ({
  format: PENDING_DOCUMENT_RECOVERY_FORMAT,
  version: 1,
  exported_at: recoveryIso,
  recovery: {
    conflictId: 'main_conflict_7',
    version: 3,
    kind,
    documentId: '41',
    incarnation: sourceIncarnation,
    write: {
      kind,
      documentId: '41',
      incarnation: sourceIncarnation,
      resourceRevision: sourceRevision,
      revision: 9,
      sessionId: 'session_1234',
      payload: kind === 'whiteboard'
        ? {
          title: recoveredDocument.title,
          mode: recoveredDocument.mode,
          blocks: recoveryBlocks,
          settings: sampleSettings,
        }
        : { items: recoveryOutline },
    },
    error: {
      code: 'revision_conflict',
      status: 409,
      message: 'The saved resource changed.',
      currentRevision,
      currentEtag: `"lfwb:${kind}:${sourceIncarnation}:${currentRevision}"`,
    },
  },
});

{
  const parsed = parseLogosforge(JSON.stringify(whiteboardConflict));
  check('whiteboard conflict detected', parsed.recovery?.format === WHITEBOARD_CONFLICT_FORMAT);
  check('whiteboard conflict scope', parsed.recovery?.scope === 'whiteboard');
  check('whiteboard conflict full title/mode', parsed.title === 'Recovered title' && parsed.mode === 'novel');
  check('whiteboard conflict preserves blocks/marks', parsed.blocks[0]?.marks?.[0]?.to === 14);
  check('whiteboard conflict preserves settings', parsed.settings?.typeface === 'courier-prime');
}
{
  const parsed = parseLogosforge(JSON.stringify(outlineConflict));
  check('outline conflict detected', parsed.recovery?.format === OUTLINE_CONFLICT_FORMAT);
  check('outline conflict is outline-only', parsed.recovery?.scope === 'outline' && parsed.blocks.length === 0);
  check('outline conflict preserves items/link', parsed.outline?.[0]?.link?.blockId === 'recovered-block');
}
{
  const parsedWhiteboard = parseLogosforge(JSON.stringify(pendingRecovery('whiteboard')));
  const parsedOutline = parseLogosforge(JSON.stringify(pendingRecovery('outline')));
  check('pending whiteboard recovery detected', parsedWhiteboard.recovery?.scope === 'whiteboard');
  check('pending whiteboard recovery full fidelity', parsedWhiteboard.title === 'Recovered title' && parsedWhiteboard.blocks[0]?.id === 'recovered-block');
  check('pending outline recovery detected', parsedOutline.recovery?.scope === 'outline');
  check('pending outline recovery leaves blocks empty', parsedOutline.blocks.length === 0 && parsedOutline.outline?.length === 1);
}
{
  const value = pendingRecovery('outline');
  const recovery = value.recovery as unknown as PendingDocumentConflictRecovery;
  const rawPayload = recovery.write.payload as Record<string, unknown>;
  recovery.write = {
    ...recovery.write,
    payload: {
    ...rawPayload,
    items: [
      { ...recoveryOutline[0], id: ' duplicate ', parentId: 'duplicate', createdAt: 'legacy' },
      { ...recoveryOutline[0], id: ' duplicate ', parentId: ' duplicate ', updatedAt: 'bad' },
    ],
    },
  };
  const exported = pendingDocumentRecoveryEnvelope(
    recovery,
    recoveryIso,
  );
  const parsed = parseLogosforge(JSON.stringify(exported));
  check(
    'pending outline recovery exporter round-trips tolerated legacy rows',
    parsed.outline?.length === 2
      && new Set(parsed.outline.map((item) => item.id)).size === 2
      && parsed.outline.every((item) => item.parentId !== item.id),
  );
}

// Legacy v1 outline conflict copies lacked immutable identity. They remain
// portable, but are classified unverifiable so the UI always asks twice.
{
  const legacy = { ...outlineConflict } as Record<string, unknown>;
  delete legacy.incarnation;
  delete legacy.base_revision;
  legacy.items = [
    { ...recoveryOutline[0], id: 'legacy-a', order: 7.5, createdAt: 'legacy', updatedAt: '' },
    { ...recoveryOutline[0], id: 'legacy-b', order: -2, createdAt: 'not-a-date', updatedAt: 'old' },
  ];
  const parsed = parseLogosforge(JSON.stringify(legacy));
  check('legacy outline recovery remains importable', parsed.recovery?.incarnation === null);
  check(
    'legacy outline order is canonicalized safely',
    parsed.outline?.find((item) => item.id === 'legacy-b')?.order === 0
      && parsed.outline?.find((item) => item.id === 'legacy-a')?.order === 1,
  );
  check(
    'legacy outline timestamps use envelope timestamp',
    parsed.outline?.every((item) => item.createdAt === recoveryIso && item.updatedAt === recoveryIso) === true,
  );
  check(
    'legacy outline identity requires retarget warning',
    !!parsed.recovery
      && recoveryImportIdentityRelationship(parsed.recovery, '41', sourceIncarnation) === 'unverifiable',
  );
}

{
  const canonical = outlineConflictEnvelope(
    '41',
    sourceIncarnation,
    sourceRevision,
    [
      { ...recoveryOutline[0], id: 'current-a', order: 4.2, createdAt: 'old', updatedAt: '' },
      { ...recoveryOutline[0], id: 'current-b', order: -1, createdAt: 'bad', updatedAt: 'bad' },
    ],
    recoveryIso,
  );
  const parsed = parseLogosforge(JSON.stringify(canonical));
  check(
    'current outline exporter canonicalizes tolerated legacy fields',
    parsed.outline?.find((item) => item.id === 'current-b')?.order === 0
      && parsed.outline?.every((item) => item.createdAt === recoveryIso) === true,
  );
}
{
  const toleratedLegacyRows = [
    {
      ...recoveryOutline[0],
      id: ' duplicate ',
      parentId: 'duplicate',
      type: 'unknown',
      status: 'unknown',
      colorLabel: 'unknown',
      tags: ['', ' '.repeat(4), 'x'.repeat(300)],
      linkedLineId: ' bad id ',
      link: { blockIndex: 1.5, quote: 'legacy' },
      createdAt: 'September 25, 2026',
      updatedAt: 'bad',
    },
    {
      ...recoveryOutline[0],
      id: ' duplicate ',
      parentId: ' duplicate ',
      order: Number.NaN,
    },
  ] as unknown as typeof recoveryOutline;
  const canonical = outlineConflictEnvelope(
    '41',
    sourceIncarnation,
    sourceRevision,
    toleratedLegacyRows,
    recoveryIso,
  );
  const parsed = parseLogosforge(JSON.stringify(canonical));
  check(
    'outline conflict exporter round-trips tolerated legacy rows',
    parsed.outline?.length === toleratedLegacyRows.length
      && new Set(parsed.outline.map((item) => item.id)).size === toleratedLegacyRows.length
      && parsed.outline.every((item) => item.parentId !== item.id),
  );
  check(
    'outline recovery preserves long user-authored tag text',
    parsed.outline?.[0]?.tags.includes('x'.repeat(300)) === true,
  );
}
{
  const longTitle = 'T'.repeat(10_000);
  const longSummary = 'S'.repeat(1_100_000);
  const manyTags = Array.from({ length: 1_001 }, (_, index) => `tag-${index}`);
  const canonical = outlineConflictEnvelope(
    '41',
    sourceIncarnation,
    sourceRevision,
    [{ ...recoveryOutline[0], title: longTitle, summary: longSummary, tags: manyTags }],
    recoveryIso,
  );
  const parsed = parseLogosforge(JSON.stringify(canonical));
  check(
    'outline recovery preserves long title and summary',
    parsed.outline?.[0]?.title === longTitle
      && parsed.outline?.[0]?.summary === longSummary
      && parsed.outline?.[0]?.tags.length === manyTags.length,
  );
}
{
  const longTitle = 'W'.repeat(10_000);
  const parsed = parseLogosforge(JSON.stringify({
    ...whiteboardConflict,
    pending_patch: { ...whiteboardConflict.pending_patch, title: longTitle },
    document: { ...whiteboardConflict.document, title: longTitle },
  }));
  check('whiteboard recovery preserves long title', parsed.title === longTitle);
}
{
  const looseBlocks = [
    {
      id: ' duplicate ',
      type: ' ',
      text: 'Bold',
      level: 99,
      sp: 'future-screenplay-type',
      marks: [
        { type: 'bold', from: 0, to: 4, future: true },
        { type: 'italic', from: 2, to: 99 },
      ],
    },
    { id: ' duplicate ', type: 'paragraph', text: 'Second' },
  ] as unknown as WhiteboardBlock[];
  const legacySettings = { ...sampleSettings, futureSetting: { enabled: true } };
  const direct = whiteboardConflictEnvelope(
    { ...recoveredDocument, blocks: looseBlocks, settings: legacySettings } as WhiteboardDocument,
    {
      documentId: '41',
      incarnation: sourceIncarnation,
      queueEpoch: 1,
      revision: 2,
      patch: {
        mode: 'future-writing-mode',
        blocks: looseBlocks,
        settings: legacySettings,
      },
    },
    recoveryIso,
  );
  const parsedDirect = parseLogosforge(JSON.stringify(direct));

  const pending = pendingRecovery('whiteboard').recovery as unknown as PendingDocumentConflictRecovery;
  pending.write = {
    ...pending.write,
    payload: {
      ...(pending.write.payload as Record<string, unknown>),
      mode: 'future-writing-mode',
      blocks: looseBlocks,
      settings: legacySettings,
    },
  };
  const parsedPending = parseLogosforge(JSON.stringify(
    pendingDocumentRecoveryEnvelope(pending, recoveryIso),
  ));
  const isPortable = (parsed: ReturnType<typeof parseLogosforge>) => (
    parsed.mode === 'novel'
    && parsed.blocks.length === 2
    && new Set(parsed.blocks.map((block) => block.id)).size === 2
    && parsed.blocks[0]?.type === 'paragraph'
    && parsed.blocks[0]?.marks?.length === 1
    && parsed.blocks[0]?.marks?.[0]?.type === 'bold'
    && !('futureSetting' in (parsed.settings ?? {}))
  );
  check('direct whiteboard recovery exporter canonicalizes tolerated legacy metadata', isPortable(parsedDirect));
  check('pending whiteboard recovery exporter canonicalizes tolerated legacy metadata', isPortable(parsedPending));
}

// Source identity is provenance: matching needs one confirmation; mismatching
// remains portable but needs the second high-signal retarget confirmation.
{
  const recovery = parseLogosforge(JSON.stringify(whiteboardConflict)).recovery!;
  check('matching recovery identity classified same', recoveryImportIdentityRelationship(recovery, '41', sourceIncarnation) === 'same');
  check('different source document classified', recoveryImportIdentityRelationship(recovery, '99', sourceIncarnation) === 'different-document');
  check('recreated source id classified', recoveryImportIdentityRelationship(recovery, '41', targetIncarnation) === 'different-incarnation');
  assertRecoveryImportTargetStillActive(
    { documentId: '99', incarnation: targetIncarnation },
    '99',
    targetIncarnation,
  );
  throws('navigation during recovery confirmation rejected', () =>
    assertRecoveryImportTargetStillActive(
      { documentId: '99', incarnation: targetIncarnation },
      '100',
      'c'.repeat(32),
    ));
}

await asyncTest('matching recovery asks once and accepts', async () => {
  const recovery = parseLogosforge(JSON.stringify(whiteboardConflict)).recovery!;
  const steps: string[] = [];
  const accepted = await confirmRecoveryImportSteps(
    recovery,
    { documentId: '41', incarnation: sourceIncarnation },
    async (step) => { steps.push(step); return true; },
  );
  if (!accepted || steps.join(',') !== 'restore') throw new Error(`unexpected steps: ${steps.join(',')}`);
});
await asyncTest('mismatched recovery requires and accepts second confirmation', async () => {
  const recovery = parseLogosforge(JSON.stringify(whiteboardConflict)).recovery!;
  const steps: string[] = [];
  const accepted = await confirmRecoveryImportSteps(
    recovery,
    { documentId: '99', incarnation: targetIncarnation },
    async (step) => { steps.push(step); return true; },
  );
  if (!accepted || steps.join(',') !== 'restore,retarget') throw new Error(`unexpected steps: ${steps.join(',')}`);
});
await asyncTest('canceling mismatch confirmation applies nothing', async () => {
  const recovery = parseLogosforge(JSON.stringify(whiteboardConflict)).recovery!;
  let calls = 0;
  const accepted = await confirmRecoveryImportSteps(
    recovery,
    { documentId: '99', incarnation: targetIncarnation },
    async (step) => { calls += 1; return step === 'restore'; },
  );
  if (accepted || calls !== 2) throw new Error('retarget cancellation was not honored');
});

// Applying outline recovery cannot call any manuscript action; applying a
// manuscript recovery preserves all four complete fields in the active target.
await asyncTest('outline recovery applies only outline', async () => {
  const parsed = parseLogosforge(JSON.stringify(outlineConflict));
  let outlineTarget = '';
  let manuscriptTouched = false;
  await applyRecoveryImport(parsed, '99', {
    applySettings: () => { manuscriptTouched = true; },
    loadBlocks: () => { manuscriptTouched = true; return true; },
    setMode: async () => { manuscriptTouched = true; return true; },
    setTitle: async () => { manuscriptTouched = true; return true; },
    markDirty: () => { manuscriptTouched = true; },
    restoreOutline: async (documentId, items) => {
      outlineTarget = `${documentId}:${items[0]?.title}`;
    },
  });
  if (manuscriptTouched || outlineTarget !== '99:Recovered chapter') {
    throw new Error('outline restore touched manuscript state or wrong target');
  }
});
await asyncTest('whiteboard recovery applies complete content only to active target actions', async () => {
  const parsed = parseLogosforge(JSON.stringify(pendingRecovery('whiteboard')));
  const applied: Record<string, unknown> = {};
  await applyRecoveryImport(parsed, '99', {
    applySettings: (settings) => { applied.settings = settings; },
    loadBlocks: (blocks) => { applied.blocks = blocks; return true; },
    setMode: async (mode) => { applied.mode = mode; return true; },
    setTitle: async (title) => { applied.title = title; return true; },
    markDirty: () => { applied.dirty = true; },
    restoreOutline: async () => { throw new Error('outline unexpectedly restored'); },
  });
  if (
    applied.title !== recoveredDocument.title
    || applied.mode !== recoveredDocument.mode
    || (applied.blocks as WhiteboardBlock[])[0]?.id !== 'recovered-block'
    || (applied.settings as ExportPayload['settings']).typeface !== 'courier-prime'
    || applied.dirty !== true
  ) throw new Error('complete manuscript recovery fields were not applied');
});
await asyncTest('unmounted editor aborts before any manuscript recovery mutation', async () => {
  const parsed = parseLogosforge(JSON.stringify(pendingRecovery('whiteboard')));
  const mutations: string[] = [];
  let rejected = false;
  try {
    await applyRecoveryImport(parsed, '99', {
      loadBlocks: () => false,
      applySettings: () => { mutations.push('settings'); },
      setMode: async () => { mutations.push('mode'); return true; },
      setTitle: async () => { mutations.push('title'); return true; },
      markDirty: () => { mutations.push('dirty'); },
      restoreOutline: async () => { mutations.push('outline'); },
    });
  } catch {
    rejected = true;
  }
  if (!rejected || mutations.length) throw new Error(`mutations before editor readiness: ${mutations.join(',')}`);
});
await asyncTest('failed recovery preflight drain applies nothing', async () => {
  let applyCalls = 0;
  let rejected = false;
  try {
    await runRecoveryImportAfterPreflight(
      () => undefined,
      async () => { throw new Error('pending write did not drain'); },
      async () => { applyCalls += 1; },
    );
  } catch {
    rejected = true;
  }
  if (!rejected || applyCalls !== 0) {
    throw new Error(`rejected=${rejected}; applyCalls=${applyCalls}`);
  }
});
await asyncTest('navigation during recovery preflight applies nothing', async () => {
  let targetChecks = 0;
  let applyCalls = 0;
  let rejected = false;
  try {
    await runRecoveryImportAfterPreflight(
      () => {
        targetChecks += 1;
        if (targetChecks === 2) throw new Error('active document changed');
      },
      async () => undefined,
      async () => { applyCalls += 1; },
    );
  } catch {
    rejected = true;
  }
  if (!rejected || targetChecks !== 2 || applyCalls !== 0) {
    throw new Error(`rejected=${rejected}; targetChecks=${targetChecks}; applyCalls=${applyCalls}`);
  }
});
await asyncTest('recovery preflight orders checks and drain before apply', async () => {
  const events: string[] = [];
  await runRecoveryImportAfterPreflight(
    () => { events.push('check'); },
    async () => { events.push('drain'); },
    async () => { events.push('apply'); },
  );
  if (events.join(',') !== 'check,drain,check,apply') {
    throw new Error(`unexpected order: ${events.join(',')}`);
  }
});

// Strict envelope and content checks keep forged/malformed data out of editor/backend.
throws('recovery version mismatch rejected', () => parseLogosforge(JSON.stringify({ ...whiteboardConflict, version: 2 })));
throws('whiteboard envelope extra root key rejected', () => parseLogosforge(JSON.stringify({ ...whiteboardConflict, surprise: true })));
throws('pending recovery extra receipt key rejected', () => {
  const value = pendingRecovery('whiteboard');
  return parseLogosforge(JSON.stringify({
    ...value,
    recovery: { ...value.recovery, acknowledge: true },
  }));
});
throws('pending recovery write kind mismatch rejected', () => {
  const value = pendingRecovery('whiteboard');
  return parseLogosforge(JSON.stringify({
    ...value,
    recovery: { ...value.recovery, write: { ...value.recovery.write, kind: 'outline' } },
  }));
});
throws('pending recovery write identity mismatch rejected', () => {
  const value = pendingRecovery('outline');
  return parseLogosforge(JSON.stringify({
    ...value,
    recovery: { ...value.recovery, write: { ...value.recovery.write, documentId: '99' } },
  }));
});
throws('pending recovery extra error key rejected', () => {
  const value = pendingRecovery('outline');
  return parseLogosforge(JSON.stringify({
    ...value,
    recovery: { ...value.recovery, error: { ...value.recovery.error, retry: true } },
  }));
});
throws('unknown nested recovery settings rejected', () => {
  const value = pendingRecovery('whiteboard');
  const payload = value.recovery.write.payload as Record<string, unknown>;
  return parseLogosforge(JSON.stringify({
    ...value,
    recovery: {
      ...value.recovery,
      write: {
        ...value.recovery.write,
        payload: { ...payload, settings: { ...sampleSettings, extension: { deeply: ['nested'] } } },
      },
    },
  }));
});
throws('unsupported recovery writing mode rejected', () => {
  const value = pendingRecovery('whiteboard');
  const payload = value.recovery.write.payload as Record<string, unknown>;
  return parseLogosforge(JSON.stringify({
    ...value,
    recovery: {
      ...value.recovery,
      write: { ...value.recovery.write, payload: { ...payload, mode: 'forged_mode' } },
    },
  }));
});
{
  const value = pendingRecovery('whiteboard');
  const payload = value.recovery.write.payload as Record<string, unknown>;
  const parsed = parseLogosforge(JSON.stringify({
    ...value,
    recovery: {
      ...value.recovery,
      write: { ...value.recovery.write, payload: { ...payload, mode: 'series' } },
    },
  }));
  check('legacy series recovery normalizes to novel', parsed.mode === 'novel');
}
throws('duplicate recovery block ids rejected', () => {
  const value = pendingRecovery('whiteboard');
  const payload = value.recovery.write.payload as Record<string, unknown>;
  return parseLogosforge(JSON.stringify({
    ...value,
    recovery: {
      ...value.recovery,
      write: { ...value.recovery.write, payload: { ...payload, blocks: [...recoveryBlocks, ...recoveryBlocks] } },
    },
  }));
});
throws('out-of-range recovery mark rejected', () => {
  const value = pendingRecovery('whiteboard');
  const payload = value.recovery.write.payload as Record<string, unknown>;
  return parseLogosforge(JSON.stringify({
    ...value,
    recovery: {
      ...value.recovery,
      write: {
        ...value.recovery.write,
        payload: {
          ...payload,
          blocks: [{ ...recoveryBlocks[0], marks: [{ type: 'bold', from: 0, to: 999 }] }],
        },
      },
    },
  }));
});
throws('outline duplicate ids rejected', () => parseLogosforge(JSON.stringify({
  ...outlineConflict,
  items: [...recoveryOutline, ...recoveryOutline],
})));
throws('outline parent cycle rejected', () => parseLogosforge(JSON.stringify({
  ...outlineConflict,
  items: [
    { ...recoveryOutline[0], id: 'a', parentId: 'b' },
    { ...recoveryOutline[0], id: 'b', parentId: 'a' },
  ],
})));
throws('outline excessive depth rejected', () => parseLogosforge(JSON.stringify({
  ...outlineConflict,
  items: Array.from({ length: 514 }, (_, index) => ({
    ...recoveryOutline[0],
    id: `deep-${index}`,
    parentId: index === 0 ? null : `deep-${index - 1}`,
  })),
})));

// --- report ---
console.log(`Import/Export tests: ${passed} passed, ${failures.length} failed`);
for (const f of failures) console.log('  FAIL: ' + f);
if (failures.length) throw new Error(`${failures.length} import/export test(s) failed`);
console.log('IMPORT/EXPORT TESTS: PASS');
