/**
 * LittleBoy pure helper tests (context bounding, mode labels, Logos action
 * registry + apply-mode logic). No React/DOM/network. Runs headlessly
 * (esbuild + node): `npm run test:littleboy`. Throws (non-zero) on failure.
 */

import { boundedContext, clamp, contextPreview } from './context/selectionContext';
import {
  contextLabel,
  isScreenplayMode,
  modeLabel,
  screenplayElementLabel,
} from './context/writingModeContext';
import {
  LOGOS_ACTIONS,
  LOGOS_TRANSFORM_ACTIONS,
  applyModeFor,
  isTransformAction,
} from './logos/logosTypes';
import { buildProjectContext, prependProjectContext, PROJECT_MAX } from './context/projectContext';
import { parseBillyMessage, stripActionBlocks } from './billy/billyText';
import type { WhiteboardBlock } from '../whiteboard/types';
import { DEFAULT_SETTINGS, narrativeProfileContext } from '../whiteboard/documentSettings';
import { billyChat } from './littleboyApi';
import {
  StaleLittleBoyResponseError,
  runLittleBoyDocumentRequest,
  sameDocumentIdentity,
} from './littleboyRequestLifecycle';
import {
  captureDocumentIdentity,
  flushPendingDocSaves,
  setCurrentDocumentIdentity,
} from '../../state/currentDocument';

let passed = 0;
const failures: string[] = [];
function check(label: string, cond: boolean) {
  if (cond) passed += 1;
  else failures.push(label);
}

// 1. clamp
check('clamp keeps short text', clamp('hello', 10) === 'hello');
check('clamp truncates with ellipsis', clamp('hello world', 5) === 'hell…');
check('clamp handles empty', clamp('', 5) === '');

// 2. boundedContext
check('boundedContext collapses blank runs', boundedContext('a\n\n\n\nb') === 'a\n\nb');
check('boundedContext trims', boundedContext('   x   ') === 'x');
check('boundedContext bounds length', boundedContext('a'.repeat(5000), 100).length === 100);

// 3. contextPreview
check('preview prefers selection', contextPreview('  the   sea  ', 'block text') === 'the sea');
check('preview falls back to block', contextPreview('', 'the block text') === 'the block text');
check('preview clamps', contextPreview('x'.repeat(500), '', 20).length === 20);

// 4. writing-mode labels
check('modeLabel screenplay', modeLabel('screenplay') === 'Screenplay');
check('modeLabel novel', modeLabel('novel') === 'Novel');
check('modeLabel unknown capitalizes', modeLabel('foo') === 'Foo');
check('modeLabel null default', modeLabel(null) === 'Novel');
check('isScreenplayMode true', isScreenplayMode('screenplay'));
check('isScreenplayMode false', !isScreenplayMode('novel'));
check('screenplayElementLabel maps', screenplayElementLabel('scene_heading') === 'Scene Heading');
check('screenplayElementLabel empty', screenplayElementLabel(null) === '');
check('contextLabel screenplay + element', contextLabel('screenplay', 'character') === 'Screenplay · Character');
check('contextLabel ignores element off-screenplay', contextLabel('novel', 'character') === 'Novel');

// 5. Logos action registry
check('nine default actions', LOGOS_ACTIONS.length === 9);
{
  const ids = LOGOS_ACTIONS.map((a) => a.id);
  for (const expected of [
    'rewrite', 'expand', 'compress', 'make_more_visual', 'improve_dialogue',
    'improve_action', 'explain', 'summarize', 'connect_to_psyke',
  ]) {
    check(`action present: ${expected}`, ids.includes(expected as (typeof ids)[number]));
  }
}
check('six transform actions', LOGOS_TRANSFORM_ACTIONS.length === 6);
check('isTransformAction rewrite', isTransformAction('rewrite'));
check('isTransformAction explain false', !isTransformAction('explain'));
check('isTransformAction connect false', !isTransformAction('connect_to_psyke'));

// 6. applyModeFor (Apply only with a replacement AND a selection)
check('apply when replacement + selection', applyModeFor({ suggested_replacement: 'x' }, true) === 'apply');
check('insert when replacement but no selection', applyModeFor({ suggested_replacement: 'x' }, false) === 'insert');
check('insert when no replacement', applyModeFor({ suggested_replacement: null }, true) === 'insert');
check('insert when empty replacement', applyModeFor({ suggested_replacement: '' }, true) === 'insert');

// N. project context (outline + cast digest, prepended to nearby_context)
const wbDoc = (texts: string[]): WhiteboardBlock[] =>
  texts.map((text, i) => ({ id: `b${i}`, type: 'paragraph', text }));
{
  const pc = buildProjectContext(
    wbDoc(['INT. KITCHEN - DAY', 'Alice enters.', 'ALICE', 'Hello, Bob.', 'BOB', 'Hi, Alice.']),
    'screenplay',
  );
  check('project context lists the cast', /Cast:.*ALICE.*BOB/.test(pc));
  check('project context lists the scene heading', /INT\. KITCHEN/.test(pc));
  check('derived structure is labelled as manuscript, not manual outline', /Manuscript structure already drafted:/.test(pc));
  check('empty doc -> empty project context', buildProjectContext(wbDoc(['']), 'screenplay') === '');
  // prepend join + fallbacks
  check('prepend joins project then nearby', prependProjectContext('PROJ', 'NEAR') === 'PROJ\n\nNEAR');
  check('prepend falls back to nearby', prependProjectContext('', 'NEAR') === 'NEAR');
  check('prepend falls back to project', prependProjectContext('PROJ', undefined) === 'PROJ');
  // bounding: a large doc is capped + clamped
  const big: string[] = [];
  for (let i = 0; i < 40; i += 1) {
    big.push(`INT. LOCATION ${i} - DAY`, `PERSON${i}`, 'Some dialogue line here.');
  }
  const bigPc = buildProjectContext(wbDoc(big), 'screenplay');
  check('project context stays within PROJECT_MAX', bigPc.length <= PROJECT_MAX);
check('over-long cast/outline shows a "+N more" cap', /\(\+\d+ more\)/.test(bigPc));
}

// Narrative voice defaults are explicit AI grounding, but empty defaults add no noise.
check('default narrative profile is empty', narrativeProfileContext(DEFAULT_SETTINGS) === '');
{
  const voice = narrativeProfileContext({
    ...DEFAULT_SETTINGS,
    narrativePerson: 'first',
    narrativeStyle: 'literary',
    narrativeRegister: 'colloquial',
    slangLevel: 'light',
  });
  check('narrative profile includes person', /first person/.test(voice));
  check('narrative profile includes style/register/slang', /literary/.test(voice) && /colloquial/.test(voice) && /Slang: light/.test(voice));
}

// 6. stripActionBlocks — keep Billy's machine <action> directive out of the transcript
check('strips a complete <action> block', stripActionBlocks('Prose here.\n\n<action>{"a":1}</action>') === 'Prose here.');
check('strips a truncated / unclosed <action> tag', stripActionBlocks('Prose here.\n\n<action>{"a":1}') === 'Prose here.');
check('leaves prose with no action tag untouched', stripActionBlocks('Just normal advice.') === 'Just normal advice.');
check('preserves the prose that precedes the action', stripActionBlocks('Line one.\nLine two.\n<action>{"x":true}</action>') === 'Line one.\nLine two.');
check('removes the tag even with attributes/whitespace', !stripActionBlocks('Text <action >{"k":"v"}</action> tail').includes('<action'));

// 7. parseBillyMessage — lift <action> directives into structured suggestion cards
{
  const p1 = parseBillyMessage(
    'Advice.\n<action>{"action":"create_scene","args":{"x":1},"label":"Establishing Ambient Sounds"}</action>',
  );
  check('parse: prose kept + one action lifted', p1.text === 'Advice.' && p1.actions.length === 1);
  check('parse: label extracted', p1.actions[0]?.label === 'Establishing Ambient Sounds');
  check('parse: action verb extracted', p1.actions[0]?.action === 'create_scene');
  // The real LM Studio failure mode: unclosed tag + stray trailing brace.
  const p2 = parseBillyMessage('Lead-in:\n<action>{"action":"suggest_alt","label":"Subtle hint"}}');
  check('parse: unclosed + stray brace still yields a label', p2.actions[0]?.label === 'Subtle hint');
  check('parse: unclosed directive removed from prose', p2.text === 'Lead-in:');
  // label falls back to a prettified action verb when absent
  const p3 = parseBillyMessage('X <action>{"action":"modify_sound_effect"}</action>');
  check('parse: label falls back to prettified action', p3.actions[0]?.label === 'Modify Sound Effect');
  // plain prose yields no cards
  check('parse: plain prose yields no actions', parseBillyMessage('Just prose.').actions.length === 0);
}

// 8. Long LittleBoy work is scoped to the captured durable identity. The same
// SQLite id in another incarnation is a different document.
const oldIncarnation = '0123456789abcdef0123456789abcdef';
const newIncarnation = 'fedcba9876543210fedcba9876543210';
setCurrentDocumentIdentity('4242', oldIncarnation);
const oldIdentity = captureDocumentIdentity();
check(
  'identity equality includes incarnation',
  sameDocumentIdentity(oldIdentity, { ...oldIdentity })
    && !sameDocumentIdentity(oldIdentity, { documentId: '4242', incarnation: newIncarnation }),
);

// A handoff/close drain must wait for the long request, while an ordinary AI
// transport failure remains an AI error rather than an unsaved-data failure.
let releaseTrackedRequest!: (value: string) => void;
const trackedRequest = runLittleBoyDocumentRequest(
  oldIdentity,
  () => new Promise<string>((resolve) => { releaseTrackedRequest = resolve; }),
);
let drainFinished = false;
const draining = flushPendingDocSaves().then(() => { drainFinished = true; });
await Promise.resolve();
check('document drain waits for active LittleBoy request', !drainFinished);
releaseTrackedRequest('complete');
check('tracked LittleBoy result is preserved', (await trackedRequest) === 'complete');
await draining;
check('document drain finishes after LittleBoy settles', drainFinished);

// Model a DELETE followed by SQLite numeric-id reuse while Billy's response is
// in flight. The wire request stays pinned to the old token and the late result
// is rejected before any hook can publish it into the replacement document.
const originalFetch = globalThis.fetch;
let requestedUrl = '';
let requestedHeaders = new Headers();
let resolveFetch!: (response: Response) => void;
globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
  requestedUrl = String(input);
  requestedHeaders = new Headers(init?.headers);
  return new Promise<Response>((resolve) => { resolveFetch = resolve; });
}) as typeof fetch;

const lateBilly = billyChat(
  'http://127.0.0.1:8777',
  { message: 'Old document question' },
  undefined,
  oldIdentity,
);
setCurrentDocumentIdentity('4242', newIncarnation);
resolveFetch(new Response(JSON.stringify({
  ok: true,
  conversation_id: 'old-conversation',
  message: { role: 'assistant', content: 'late old answer' },
  provider: 'test',
}), { status: 200, headers: { 'Content-Type': 'application/json' } }));

let rejectedLateResponse = false;
try {
  await lateBilly;
} catch (error) {
  rejectedLateResponse = error instanceof StaleLittleBoyResponseError;
} finally {
  globalThis.fetch = originalFetch;
}
check(
  'LittleBoy URL uses captured numeric id',
  requestedUrl === 'http://127.0.0.1:8777/api/littleboy/billy/chat?doc=4242',
);
check(
  'LittleBoy header uses captured incarnation',
  requestedHeaders.get('X-LogosForge-Document-Incarnation') === oldIncarnation,
);
check('late response from deleted incarnation is discarded', rejectedLateResponse);

// --- report ---
console.log(`LittleBoy tests: ${passed} passed, ${failures.length} failed`);
for (const f of failures) console.log('  FAIL: ' + f);
if (failures.length) throw new Error(`${failures.length} littleboy test(s) failed`);
console.log('LITTLEBOY TESTS: PASS');
