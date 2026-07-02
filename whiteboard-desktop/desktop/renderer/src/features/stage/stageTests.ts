/**
 * Stage-script classifier tests. Pure — no React/DOM. Runs headlessly
 * (esbuild + node): `npm run test:stage`. Throws on failure.
 */

import type { FountainBlock } from '../screenplay/fountainTypes';
import { classifyStage } from './stageClassifier';

let passed = 0;
const failures: string[] = [];
function check(label: string, cond: boolean) {
  if (cond) passed += 1;
  else failures.push(label);
}

const p = (text: string): FountainBlock => ({ text, isHeading: false, level: undefined });
const h = (text: string, level: number): FountainBlock => ({ text, isHeading: true, level });

// 1. Block classification over a representative scene.
const blocks: FountainBlock[] = [
  h('Act One', 2),
  p('Scene 1'),
  p('A bare stage. A single chair. EVELYN stands at the glass, watching nothing.'),
  p('EVELYN'),
  p('You came back.'),
  p('MARCUS'),
  p('I never left. You stopped looking.'),
  p('(She does not turn.)'),
  p('EVELYN'),
  p('(softly)'),
  p('That is not the same as staying.'),
];
const t = classifyStage(blocks);
check('act heading (native)', t[0] === 'scene_heading');
check('scene heading (ACT/SCENE text)', t[1] === 'scene_heading');
check('opening stage direction is action', t[2] === 'action');
check('character cue', t[3] === 'character');
check('dialogue after cue', t[4] === 'dialogue');
check('second cue', t[5] === 'character');
check('second dialogue', t[6] === 'dialogue');
check('standalone parenthetical stage direction', t[7] === 'parenthetical');
check('third cue', t[8] === 'character');
check('cue-modifier parenthetical', t[9] === 'parenthetical');
check('dialogue after a parenthetical', t[10] === 'dialogue');

// 2. Conservative cue detection — never centre plain stage-direction prose.
check('long stage direction is action, not a cue',
  classifyStage([p('MARCUS enters behind her, hat in hand.'), p('She turns.')])[0] === 'action');
check('a sentence is not a cue', classifyStage([p('Determined to leave.'), p('More.')])[0] === 'action');
check('a cue needs a following line', classifyStage([p('EVELYN')])[0] === 'action');

// 3. Cue forms recognized (ALL-CAPS, Title case, trailing colon / parenthetical).
check('ALLCAPS cue', classifyStage([p('OLD MAN'), p('Hello.')])[0] === 'character');
check('Title-case cue', classifyStage([p('Evelyn'), p('Hello.')])[0] === 'character');
check('cue with trailing colon', classifyStage([p('EVELYN:'), p('Hello.')])[0] === 'character');

// 4. Title-Case description prose must NEVER be mis-centered as a cue (audit).
check('Title-Case prose phrase is action, not a cue',
  classifyStage([p('A Long Silence Follows'), p('The lights dim slowly.')])[0] === 'action');
check('pronoun-led Title-Case is action',
  classifyStage([p('She Runs To The Door'), p('He follows.')])[0] === 'action');
// A false cue must not cascade and swallow a real one.
{
  const r = classifyStage([p('The Storm Rages On'), p('HAMLET'), p('Alas, poor Yorick')]);
  check('prose stays action (no cascade)', r[0] === 'action');
  check('real ALL-CAPS cue survives the prose above it', r[1] === 'character');
  check('real dialogue survives', r[2] === 'dialogue');
}

// --- report ---
console.log(`Stage-script tests: ${passed} passed, ${failures.length} failed`);
for (const f of failures) console.log('  FAIL: ' + f);
if (failures.length) throw new Error(`${failures.length} stage test(s) failed`);
console.log('STAGE TESTS: PASS');
