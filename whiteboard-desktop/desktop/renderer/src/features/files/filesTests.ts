/**
 * File serialization tests. Pure — no Electron/DOM. Runs headlessly
 * (esbuild + node): `npm run test:files`. Throws (non-zero) on failure.
 */

import type { WhiteboardBlock } from '../whiteboard/types';
import { fileStateLabel, windowTitle } from './fileState';
import { baseName, blocksToText, defaultExtForMode, suggestedFileName, textToBlocks } from './fileSerialize';
import { FileSessionCoordinator } from './fileSessionStore';

let passed = 0;
const failures: string[] = [];
function check(label: string, cond: boolean) {
  if (cond) passed += 1;
  else failures.push(label);
}
const json = (v: unknown) => JSON.stringify(v);
const norm = (b: WhiteboardBlock) => ({ type: b.type, text: b.text, level: b.level ?? undefined });

// 1. Round-trip blocks -> text -> blocks (lossless on type/text/level)
{
  const blocks: WhiteboardBlock[] = [
    { id: 'a', type: 'heading', text: 'Act One', level: 1 },
    { id: 'b', type: 'paragraph', text: 'INT. HOUSE - DAY' },
    { id: 'c', type: 'paragraph', text: 'She reads a [[note]] and /* cut */.' },
    { id: 'd', type: 'heading', text: 'Scene', level: 2 },
    { id: 'e', type: 'paragraph', text: '**bold** action.' },
  ];
  const text = blocksToText(blocks);
  check('text writes # heading', text.includes('# Act One'));
  check('text writes ## heading', text.includes('## Scene'));
  check('text preserves note + boneyard', text.includes('[[note]]') && text.includes('/* cut */'));
  check('round-trip preserves blocks', json(textToBlocks(text).map(norm)) === json(blocks.map(norm)));
}

// 2. Heading-level detection on load
{
  const b = textToBlocks('# A\n## B\n### C\nplain text');
  check('load h1', b[0].type === 'heading' && b[0].level === 1 && b[0].text === 'A');
  check('load h2', b[1].level === 2);
  check('load h3', b[2].level === 3);
  check('load plain', b[3].type === 'paragraph' && b[3].text === 'plain text');
}

// 3. Whitespace / edge cases
check('trailing newline trimmed', textToBlocks('hello\n').length === 1);
check('empty file -> one blank block', textToBlocks('').length === 1 && textToBlocks('')[0].text === '');
check('CRLF handled', textToBlocks('a\r\nb').length === 2 && textToBlocks('a\r\nb')[1].text === 'b');
check('blank lines kept', textToBlocks('a\n\nb').length === 3);

// 4. Default extension per mode
check('ext screenplay', defaultExtForMode('screenplay') === 'fountain');
check('ext novel', defaultExtForMode('novel') === 'md');
check('ext notes', defaultExtForMode('notes') === 'md');
check('ext fallback', defaultExtForMode('stage_script') === 'txt');

// 5. Suggested filename + basename
check('suggested untitled screenplay', suggestedFileName(null, 'screenplay') === 'untitled.fountain');
check('suggested untitled novel', suggestedFileName(null, 'novel') === 'untitled.md');
check('suggested from path', suggestedFileName('/a/b/my-script.fountain', 'novel') === 'my-script.fountain');
check('baseName unix', baseName('/a/b/c.md') === 'c.md');
check('baseName windows', baseName('C:\\docs\\x.txt') === 'x.txt');

// 6. Window title (clean / dirty / untitled)
check('title untitled clean', windowTitle('Untitled', false) === 'LogosForge Whiteboard — Untitled');
check('title untitled dirty', windowTitle('Untitled', true) === 'LogosForge Whiteboard — Untitled *');
check('title file clean', windowTitle('my.fountain', false) === 'LogosForge Whiteboard — my.fountain');
check('title file dirty', windowTitle('my.fountain', true) === 'LogosForge Whiteboard — my.fountain *');

// 7. File-state label (autosave is NOT conflated with file save)
check('state untitled clean', fileStateLabel('Untitled', false, false) === 'Untitled');
check('state untitled dirty', fileStateLabel('Untitled', false, true) === 'Untitled — Modified');
check('state file clean', fileStateLabel('script.fountain', true, false) === 'script.fountain — Saved to file');
check('state file dirty', fileStateLabel('script.fountain', true, true) === 'script.fountain — Modified');

// 8. Saving revision N must not clear an edit made while its write is pending.
{
  const session = new FileSessionCoordinator();
  session.markDirty();
  const written = session.capture('doc-a');
  session.patch({ status: 'saving' });
  session.markDirty();
  const completion = session.completeSave(written, 'doc-a', 'C:\\drafts\\story.md');
  check('save completion remains in the same context', completion.currentContext);
  check('edit during save prevents clean completion', !completion.clean);
  check('edit during save remains dirty', session.getSnapshot().dirty);
  check('Save As still associates the chosen path', session.getSnapshot().filePath === 'C:\\drafts\\story.md');
  check('newer edit restores unsaved status', session.getSnapshot().status === 'unsaved');
}

// 9. A late dialog/write response cannot mutate a replacement file context.
{
  const session = new FileSessionCoordinator();
  session.markDirty();
  const stale = session.capture('doc-a');
  session.replaceContext('C:\\drafts\\other.md');
  const completion = session.completeSave(stale, 'doc-b', 'C:\\drafts\\stale.md');
  check('stale document completion is rejected', !completion.currentContext);
  check('stale completion cannot replace path', session.getSnapshot().filePath === 'C:\\drafts\\other.md');
}

// 10. Disk writes are FIFO, and a rejected write cannot poison the queue.
{
  const session = new FileSessionCoordinator();
  const events: string[] = [];
  let releaseFirst!: () => void;
  const firstGate = new Promise<void>((resolve) => { releaseFirst = resolve; });
  const first = session.runSave(async () => {
    events.push('first:start');
    await firstGate;
    events.push('first:end');
  });
  const second = session.runSave(async () => {
    events.push('second:start');
    events.push('second:end');
  });
  await Promise.resolve();
  check('second write waits for first', json(events) === json(['first:start']));
  releaseFirst();
  await Promise.all([first, second]);
  check(
    'writes finish in request order',
    json(events) === json(['first:start', 'first:end', 'second:start', 'second:end']),
  );

  const failed = session.runSave(async () => { throw new Error('expected'); });
  const recovered = session.runSave(async () => 'recovered');
  check('failed queue item rejects its own caller', (await Promise.allSettled([failed]))[0]?.status === 'rejected');
  check('write after failure still runs', (await recovered) === 'recovered');
  await session.waitForSaves();

  const drainingSession = new FileSessionCoordinator();
  let releaseDrainHead!: () => void;
  const drainHeadGate = new Promise<void>((resolve) => { releaseDrainHead = resolve; });
  void drainingSession.runSave(() => drainHeadGate);
  await Promise.resolve();
  const draining = drainingSession.waitForSaves();
  let appendedRan = false;
  void drainingSession.runSave(async () => { appendedRan = true; });
  releaseDrainHead();
  await draining;
  check('queue drain includes writes appended while waiting', appendedRan);
}

// --- report ---
console.log(`File management tests: ${passed} passed, ${failures.length} failed`);
for (const f of failures) console.log('  FAIL: ' + f);
if (failures.length) throw new Error(`${failures.length} file test(s) failed`);
console.log('FILE TESTS: PASS');
