/**
 * Graphic-novel classifier tests. Pure — no React/DOM. Runs headlessly
 * (esbuild + node): `npm run test:gn`. Throws on failure.
 */

import type { FountainBlock } from '../screenplay/fountainTypes';
import { classifyGn, gnInlineRanges } from './graphicNovelClassifier';

let passed = 0;
const failures: string[] = [];
function check(label: string, cond: boolean) {
  if (cond) passed += 1;
  else failures.push(label);
}

const p = (text: string): FountainBlock => ({ text, isHeading: false, level: undefined });
const h = (text: string, level: number): FountainBlock => ({ text, isHeading: true, level });

// 1. Block classification over a representative comic-script snippet.
const blocks: FountainBlock[] = [
  h('Page One', 2),
  h('Panel 1', 3),
  p('EXTERIOR. THE ARCHIVE — NIGHT. A windowless monolith.'),
  p('CAPTION: They built it to remember.'),
  p('SFX: hmmmmmmmm'),
  p('Solenne'),
  p('Wake up. Show me the last thing she touched.'),
  p('LittleBoy (on screen)'),
  p('(whisper)'),
  p('…That’s better than mine.'),
  p('Black panel. A single line of dialogue.'),
];
const t = classifyGn(blocks);
check('page heading', t[0] === 'page');
check('panel heading', t[1] === 'panel');
check('slug/description line', t[2] === 'description');
check('caption', t[3] === 'caption');
check('sfx', t[4] === 'sfx');
check('cue', t[5] === 'cue');
check('dialogue after cue', t[6] === 'dialogue');
check('cue with parenthetical name', t[7] === 'cue');
check('paren', t[8] === 'paren');
check('dialogue after paren', t[9] === 'dialogue');
check('description not mis-cued', t[10] === 'description');

// 2. Conservative cue detection (avoid centering plain description prose).
check('period line is not a cue', classifyGn([p('Determined.'), p('Next.')])[0] === 'description');
check('lowercase line is not a cue', classifyGn([p('wide shot of the room'), p('More.')])[0] === 'description');
check('cue needs a following line', classifyGn([p('Solenne')])[0] === 'description');

// A STANDALONE parenthetical (no preceding cue) must NOT steal the next cue.
{
  const r = classifyGn([
    p('She types without looking at the keys.'), // description
    p('(beat)'), // standalone stage-direction parenthetical
    p('Solenne'), // must stay a cue, not become dialogue
    p('Wake up. Show me the last thing.'), // dialogue
  ]);
  check('standalone paren keeps the next line a cue', r[2] === 'cue');
  check('dialogue still follows that cue', r[3] === 'dialogue');
}

// Title-Case description prose must NOT become a cue + speech-balloon pair.
{
  const r = classifyGn([p('A Dog Runs By'), p('The hero turns around.')]);
  check('Title-Case prose -> description (not a cue)', r[0] === 'description');
  check('the line after it -> description (not dialogue)', r[1] === 'description');
}
// CAPTION / SFX boxes require a delimiter — bare leading words are prose.
check('prose starting "Caption" stays description',
  classifyGn([p('Caption this moment forever'), p('he thinks.')])[0] === 'description');
check('prose starting "Sound" stays description',
  classifyGn([p('Sound travels fast in here.'), p('More.')])[0] === 'description');
check('real "CAPTION:" is still a caption',
  classifyGn([p('CAPTION: Once, there was a city.')])[0] === 'caption');
check('real "SFX:" is still sfx', classifyGn([p('SFX: BOOM')])[0] === 'sfx');

// 3. Inline ranges — caption label + speaker, sfx label + sound.
const cap = gnInlineRanges('CAPTION (Solenne): Forty thousand novels.', 'caption');
check('caption label at start', cap.some((r) => r.className === 'gn-label' && r.from === 0));
check('caption speaker name', cap.some((r) => r.className === 'gn-name'));
const cap2 = gnInlineRanges('CAPTION: They built it.', 'caption');
check('caption label only (no name)', cap2.length === 1 && cap2[0].className === 'gn-label');

const SFX_LINE = 'SFX (terminal): tk-tk-tk';
const sfx = gnInlineRanges(SFX_LINE, 'sfx');
check('sfx label at start', sfx.some((r) => r.className === 'gn-label' && r.from === 0));
const sound = sfx.find((r) => r.className === 'gn-sound');
check('sfx sound text', !!sound && SFX_LINE.slice(sound!.from, sound!.to) === 'tk-tk-tk');

check('no inline spans for description', gnInlineRanges('A windowless monolith.', 'description').length === 0);

// 4. Plain-text PAGE / PANEL markers (not just native headings).
{
  const r = classifyGn([p('PAGE ONE'), p('PANEL 1'), p('A red-lit shack.'), p('PANEL 2'), p('Close on Eli.')]);
  check('plain-text PAGE ONE -> page', r[0] === 'page');
  check('plain-text PANEL 1 -> panel', r[1] === 'panel');
  check('PANEL 2 -> panel (consistent, not dialogue/description)', r[3] === 'panel');
}
check('numbered "Page 1" -> page', classifyGn([p('Page 1')])[0] === 'page');
check('prose "Page after page" stays description',
  classifyGn([p('Page after page, the rain fell.'), p('More.')])[0] === 'description');
check('prose "Panel discussions resumed" stays description',
  classifyGn([p('Panel discussions resumed at noon.'), p('More.')])[0] === 'description');
check('prose "Page one of two." stays description',
  classifyGn([p('Page one of two.'), p('More.')])[0] === 'description');

// 5. Inline dialogue "NAME: speech" (the common comic convention).
check('inline "MARA: …" -> dialogue', classifyGn([p('MARA: It is keeping time with us.')])[0] === 'dialogue');
{
  const r = classifyGn([p('MARA: Hello.'), p('ELI: Goodbye.')]);
  check('two inline dialogues both -> dialogue', r[0] === 'dialogue' && r[1] === 'dialogue');
}
check('prose "Note: remember…" stays description',
  classifyGn([p('Note: remember to feed the cat.'), p('More.')])[0] === 'description');
check('interstitial "CUT: to black" is not dialogue',
  classifyGn([p('CUT: to black.'), p('More.')])[0] !== 'dialogue');
{
  const inl = gnInlineRanges('MARA: It is keeping time.', 'dialogue');
  check('inline dialogue emits a gn-name span on "NAME:"',
    inl.some((r) => r.className === 'gn-name' && r.from === 0 && r.to === 5));
  check('plain speech dialogue emits no name span',
    gnInlineRanges('It is keeping time.', 'dialogue').length === 0);
}

// --- report ---
console.log(`Graphic-novel tests: ${passed} passed, ${failures.length} failed`);
for (const f of failures) console.log('  FAIL: ' + f);
if (failures.length) throw new Error(`${failures.length} graphic-novel test(s) failed`);
console.log('GRAPHIC NOVEL TESTS: PASS');
