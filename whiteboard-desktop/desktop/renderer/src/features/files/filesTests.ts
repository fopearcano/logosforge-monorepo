/**
 * File serialization tests. Pure — no Electron/DOM. Runs headlessly
 * (esbuild + node): `npm run test:files`. Throws (non-zero) on failure.
 */

import type { WhiteboardBlock } from '../whiteboard/types';
import { fileStateLabel, windowTitle } from './fileState';
import { baseName, blocksToText, defaultExtForMode, suggestedFileName, textToBlocks } from './fileSerialize';

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

// --- report ---
console.log(`File management tests: ${passed} passed, ${failures.length} failed`);
for (const f of failures) console.log('  FAIL: ' + f);
if (failures.length) throw new Error(`${failures.length} file test(s) failed`);
console.log('FILE TESTS: PASS');
