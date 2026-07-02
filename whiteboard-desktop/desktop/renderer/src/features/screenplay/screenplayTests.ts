/**
 * Screenplay parser/classifier tests. Pure — no editor/DOM. Runnable headlessly
 * (esbuild + node): `npm run test:screenplay`. Throws (non-zero exit) on failure.
 */

import { deriveOutline } from '../outline/deriveOutline';
import { DEFAULT_SETTINGS, surfaceDataAttrs } from '../whiteboard/documentSettings';
import { nextScale, scaleToPct } from '../whiteboard/editorScale';
import { parseEmphasis } from './fountainParser';
import type { FountainBlock } from './fountainTypes';
import { computeSuggestions, filterSuggestions } from './screenplayAutocomplete';
import { detectBoneyard } from './screenplayBoneyard';
import { classify, extractCharacters } from './screenplayClassifier';
import { cycleCase, toggleCenter } from './screenplayCommands';
import { blocksToFountainText, stripForExport } from './screenplayExport';
import { approxPageCount } from './screenplayPageCount';
import {
  buildPreview,
  groupPreviewItems,
  previewSegments,
  previewToPlainText,
  type PreviewLine,
} from './screenplayPreview';
import { sectionShiftTabLevel, sectionTabLevel } from './screenplaySections';
import { parseTitlePage } from './screenplayTitlePage';

let passed = 0;
const failures: string[] = [];

function check(label: string, cond: boolean) {
  if (cond) passed += 1;
  else failures.push(label);
}

const line = (text: string): FountainBlock => ({ text, isHeading: false });
const lines = (...texts: string[]): FountainBlock[] => texts.map(line);

function eqTypes(label: string, blocks: FountainBlock[], want: string[]) {
  const got = classify(blocks);
  check(`${label} (got ${JSON.stringify(got)})`, JSON.stringify(got) === JSON.stringify(want));
}

const classesOf = (text: string) => parseEmphasis(text).map((r) => r.className);
const json = (v: unknown) => JSON.stringify(v);

// 1. Scene headings
eqTypes('scene INT.', lines('INT. HOUSE - NIGHT'), ['scene_heading']);
eqTypes('scene EXT.', lines('EXT. ROAD - DAY'), ['scene_heading']);
eqTypes('scene INT./EXT.', lines('INT./EXT. CAR - DAY'), ['scene_heading']);
eqTypes('scene I/E.', lines('I/E. CAR'), ['scene_heading']);
eqTypes('scene EST.', lines('EST. CITY - DAWN'), ['scene_heading']);

// 2. Forced scene heading / not-forced
eqTypes('forced scene .X', lines('.STRANGE DREAM SPACE'), ['scene_heading']);
eqTypes('not forced ..', lines('..ellipsis is action'), ['action']);

// 3. Action
eqTypes('action prose', lines('He walks across the room.'), ['action']);

// 4. Character + dialogue
eqTypes('character+dialogue', lines('JOHN', 'Hello there.'), ['character', 'dialogue']);
eqTypes('OLD MAN', lines('OLD MAN', 'Get off my lawn.'), ['character', 'dialogue']);

// 5. Parenthetical
eqTypes(
  'parenthetical',
  lines('JOHN', 'Hi.', '(quietly)', 'Bye.'),
  ['character', 'dialogue', 'parenthetical', 'dialogue'],
);

// 6. Transition
eqTypes('transition CUT TO:', lines('CUT TO:'), ['transition']);
eqTypes('transition FADE TO:', lines('FADE TO:'), ['transition']);

// 7. Forced transition
eqTypes('forced transition >', lines('> SMASH CUT:'), ['transition']);

// 8. Centered
eqTypes('centered', lines('> This is centered <'), ['centered']);

// 9. Sections
eqTypes('section #', lines('# Act One'), ['section']);
eqTypes('section ##', lines('## Sequence One'), ['section']);
eqTypes('section heading node', [{ text: 'Act One', isHeading: true, level: 1 }], ['section']);

// 10. Synopsis
eqTypes('synopsis', lines('= This is a synopsis'), ['synopsis']);

// 11. Note
eqTypes('note', lines('[[This is a note]]'), ['note']);

// 12. Page break
eqTypes('page break ===', lines('==='), ['page_break']);
eqTypes('page break =====', lines('====='), ['page_break']);

// 13. Emphasis
check('emph bold', json(classesOf('**bold**')) === json(['sp-emph-marker', 'sp-bold', 'sp-emph-marker']));
check('emph italic', json(classesOf('*italic*')) === json(['sp-emph-marker', 'sp-italic', 'sp-emph-marker']));
check('emph bold-italic', json(classesOf('***bi***')) === json(['sp-emph-marker', 'sp-bold-italic', 'sp-emph-marker']));
check('emph underline', json(classesOf('_u_')) === json(['sp-emph-marker', 'sp-underline', 'sp-emph-marker']));
check('emph mixed', classesOf('a **b** c *d*').includes('sp-bold') && classesOf('a **b** c *d*').includes('sp-italic'));
const range = parseEmphasis('**bold**');
check('emph content range', range[1]?.from === 2 && range[1]?.to === 6);

// 14. Autocomplete filtering
check(
  'filter by E',
  json(filterSuggestions(['EXT. ', 'EXT. HOUSE - NIGHT', 'ELENA', 'INT. '], 'E')) ===
    json(['EXT. ', 'EXT. HOUSE - NIGHT', 'ELENA']),
);
check('filter empty returns all', filterSuggestions(['A', 'B'], '').length === 2);

// 15. Suggestion extraction + context ordering
const spDoc = lines('INT. HOUSE - DAY', '', 'JOHN', 'Hello.', '', 'CUT TO:');
check('suggest has character', computeSuggestions(spDoc, false).includes('JOHN'));
check('suggest has scene', computeSuggestions(spDoc, false).includes('INT. HOUSE - DAY'));
check('suggest has transition', computeSuggestions(spDoc, false).includes('CUT TO:'));
check('static slugs first by default', computeSuggestions(spDoc, false)[0] === 'INT. ');
check('characters first when flagged', computeSuggestions(spDoc, true)[0] === 'JOHN');

// 16. Section indent/outdent math
check('sectionTab 1->2', sectionTabLevel(1) === 2);
check('sectionTab caps at 3', sectionTabLevel(3) === 3);
check('sectionShiftTab 2->1', sectionShiftTabLevel(2) === 1);
check('sectionShiftTab 1->paragraph', sectionShiftTabLevel(1) === 0);

// 17. Boneyard / omitted text
check('boneyard multi-block', json(detectBoneyard(lines('/*', 'omitted', '*/'))) === json([true, true, true]));
check('boneyard single line', json(detectBoneyard(lines('action', '/* x */', 'more'))) === json([false, true, false]));
check('boneyard spanning', json(detectBoneyard(lines('/* a', 'b', 'c */', 'd'))) === json([true, true, true, false]));

// 18. Title page fields
{
  const tp = parseTitlePage(lines('Title: My Movie', 'Author: Me', '', 'INT. HOUSE - DAY'));
  check('title parsed', tp.fields.title === 'My Movie');
  check('author parsed', tp.fields.author === 'Me');
  check('title page endIndex', tp.endIndex === 3);
  check('no title page', parseTitlePage(lines('INT. HOUSE - DAY', 'Action.')).endIndex === 0);
  check('multi-line value', parseTitlePage(lines('Title:', '   My Movie', '   Subtitle', '')).fields.title === 'My Movie\nSubtitle');
}

// 19. Strip notes + boneyard for export
{
  const out = stripForExport('Hello [[a note]] and /* omitted */ world');
  check('export strips note', !out.includes('[['));
  check('export strips boneyard', !out.includes('/*'));
  check('export keeps text', out.includes('Hello') && out.includes('world'));
}

// 20. Outline extraction + section hierarchy
{
  const ob = (type: string, text: string, level?: number) => ({ id: text, type, text, level });
  const doc = [
    ob('heading', 'Act One', 1),
    ob('heading', 'Sequence One', 2),
    ob('paragraph', '= Opening image'),
    ob('paragraph', '[[Need stronger hook]]'),
    ob('paragraph', 'INT. HOUSE - DAY'),
    ob('paragraph', 'Action.'),
  ];
  const ol = deriveOutline(doc as never, 'screenplay');
  check('outline kinds', json(ol.map((o) => o.kind)) === json(['section', 'section', 'synopsis', 'note', 'scene']));
  check('outline section levels', ol[0].level === 1 && ol[1].level === 2);
  check(
    'novel outline = headings only',
    json(deriveOutline(doc as never, 'novel').map((o) => o.kind)) === json(['section', 'section']),
  );
}

// 21. Filter ordering, note label, page-break boundary
check(
  'filter prefix before substring',
  json(filterSuggestions(['SMASH CUT:', 'CUT TO:', 'DISSOLVE TO:'], 'C')) === json(['CUT TO:', 'SMASH CUT:']),
);
{
  const ol = deriveOutline([{ id: 'n', type: 'paragraph', text: '[[Need stronger hook]]' }] as never, 'screenplay');
  check('outline note label strips brackets', ol[0]?.label === 'Need stronger hook');
}
eqTypes('== is synopsis, not page break', lines('=='), ['synopsis']);

// 22. Preview hides notes + omitted text, keeps the surrounding action/dialogue
{
  const pv = buildPreview(
    lines(
      'INT. HOUSE - DAY',
      'She reads a [[remember the key]] letter.',
      '/* cut this scene */',
      'JOHN',
      'Hello.',
    ),
    DEFAULT_SETTINGS,
  );
  const body = pv.lines.map((l) => l.text).join('\n');
  check('preview hides inline note', !body.includes('[['));
  check('preview hides boneyard', !body.includes('/*') && !body.includes('cut this scene'));
  check('preview keeps action text', body.includes('She reads a') && body.includes('letter.'));
  check('preview keeps dialogue', pv.lines.some((l) => l.type === 'dialogue' && l.text === 'Hello.'));
}

// 23. Preview excludes whole note lines + multi-block boneyard
{
  const pv = buildPreview(lines('[[just a note]]', 'Action here.', '/*', 'omitted', '*/'), DEFAULT_SETTINGS);
  check('preview drops note line', !pv.lines.some((l) => l.type === 'note'));
  check('preview drops boneyard block', !pv.lines.some((l) => l.text.includes('omitted')));
}

// 24. Preview handles the title page
{
  const pv = buildPreview(
    lines('Title: My Movie', 'Author: Me', '', 'INT. HOUSE - DAY', 'Action.'),
    DEFAULT_SETTINGS,
  );
  check('preview parses title field', pv.titlePage.title === 'My Movie');
  check('preview title not in body', !pv.lines.some((l) => l.text.includes('My Movie')));
  check('preview body starts at scene', pv.lines[0]?.type === 'scene_heading');
}

// 25. Preview include-outline setting
{
  const blocks = lines('# Act One', '= a synopsis', 'INT. HOUSE - DAY');
  const without = buildPreview(blocks, DEFAULT_SETTINGS);
  const withOutline = buildPreview(blocks, { ...DEFAULT_SETTINGS, includeOutline: true });
  check(
    'preview excludes outline by default',
    !without.lines.some((l) => l.type === 'section' || l.type === 'synopsis'),
  );
  check(
    'preview includes outline when enabled',
    withOutline.lines.some((l) => l.type === 'section') &&
      withOutline.lines.some((l) => l.type === 'synopsis'),
  );
}

// 26. Document settings → scene-heading style data attribute
check('settings attr default bold', surfaceDataAttrs(DEFAULT_SETTINGS)['data-scene-style'] === 'bold');
check(
  'settings attr underline',
  surfaceDataAttrs({ ...DEFAULT_SETTINGS, sceneHeadingStyle: 'underline' })['data-scene-style'] === 'underline',
);
check(
  'settings attr invisibles off',
  surfaceDataAttrs({ ...DEFAULT_SETTINGS, showInvisibles: false })['data-invisibles'] === 'off',
);

// 27. View scale state
check('scale bigger', nextScale(1, 'bigger') === 1.1);
check('scale smaller', nextScale(1, 'smaller') === 0.9);
check('scale actual', nextScale(1.4, 'actual') === 1);
check('scale clamps max', nextScale(1.8, 'bigger') === 1.8);
check('scale clamps min', nextScale(0.7, 'smaller') === 0.7);
check('scale pct', scaleToPct(1.1) === 110);

// 28. Capitalization cycle (lower → UPPER → Sentence → lower)
check('case lower->UPPER', cycleCase('hello world') === 'HELLO WORLD');
check('case UPPER->Sentence', cycleCase('HELLO WORLD') === 'Hello world');
check('case mixed->lower', cycleCase('Hello World') === 'hello world');

// 29. Center command toggle
check('center wraps', toggleCenter('THE END') === '> THE END <');
check('center unwraps', toggleCenter('> THE END <') === 'THE END');

// 30. Export plain text preserves the raw Fountain (markers/notes/boneyard kept)
{
  const wb = [
    { id: 'a', type: 'heading', text: 'Act One', level: 1 },
    { id: 'b', type: 'paragraph', text: 'INT. HOUSE - DAY' },
    { id: 'c', type: 'paragraph', text: 'She reads a [[note]] and /* cut */ stays.' },
  ];
  const text = blocksToFountainText(wb);
  check('export writes section as #', text.includes('# Act One'));
  check('export preserves scene', text.includes('INT. HOUSE - DAY'));
  check('export preserves raw note + boneyard', text.includes('[[note]]') && text.includes('/* cut */'));
}

// 31. Preview plain-text copy strips markers; page count approximates
{
  const pv = buildPreview(lines('INT. HOUSE - DAY', 'A **bold** move.'), DEFAULT_SETTINGS);
  const txt = previewToPlainText(pv);
  check('preview copy strips markers', txt.includes('A bold move.') && !txt.includes('**'));
  check('preview segments strip markers', previewSegments('a **b** c').map((s) => s.text).join('') === 'a b c');
  const few = approxPageCount(lines('INT. HOUSE - DAY', 'Short action.'));
  const many = approxPageCount(
    Array.from({ length: 200 }, () => line('A reasonably long line of screenplay action text here.')),
  );
  check('page count empty is 0', approxPageCount([]) === 0);
  check('page count grows with content', many > few && few >= 1);
}

// --- Dual dialogue grouping + title-page draft ---
{
  const L = (type: PreviewLine['type'], text: string): PreviewLine => ({ type, text });

  const dualItems = groupPreviewItems([
    L('character', 'GIRL'),
    L('dialogue', 'Hello there.'),
    L('character', 'BOY ^'),
    L('dialogue', 'Hi yourself.'),
  ]);
  const dual = dualItems.find((it) => it.kind === 'dual');
  check('one dual group', dualItems.filter((it) => it.kind === 'dual').length === 1);
  check('dual left is first speaker', dual?.kind === 'dual' && dual.left[0].text === 'GIRL');
  check('dual right caret stripped', dual?.kind === 'dual' && dual.right[0].text === 'BOY');
  check('dual right keeps dialogue', dual?.kind === 'dual' && dual.right[1].text === 'Hi yourself.');

  // No spurious dual: a normal scene + single speaker.
  const plain = groupPreviewItems([
    L('scene_heading', 'INT. ROOM — DAY'),
    L('character', 'MARA'),
    L('dialogue', 'Anyone home?'),
  ]);
  check('plain scene is a line', plain[0].kind === 'line');
  check('plain speaker is a block', plain[1].kind === 'block');
  check('no false dual grouping', plain.every((it) => it.kind !== 'dual'));

  // A lone "^" speaker (no preceding block) still strips the caret.
  const lone = groupPreviewItems([L('character', 'ECHO ^'), L('dialogue', 'Alone.')]);
  check('lone caret block, not dual', lone[0].kind === 'block');
  check('lone caret stripped', lone[0].kind === 'block' && lone[0].lines[0].text === 'ECHO');

  // The dual caret is also stripped in character extraction, so "BOY" and
  // "BOY ^" are one autocomplete name (not two).
  const cast = extractCharacters([
    { text: 'BOY', isHeading: false },
    { text: 'Hi.', isHeading: false },
    { text: '', isHeading: false },
    { text: 'BOY ^', isHeading: false },
    { text: 'Hey.', isHeading: false },
  ]);
  check('dual caret dedupes in character extraction', cast.filter((n) => n === 'BOY').length === 1);

  // Three simultaneous speakers: Fountain is 2-up, so the 3rd "^" can't make a
  // third column — it degrades to a standalone caret-stripped block (documented).
  const three = groupPreviewItems([
    L('character', 'A'), L('dialogue', '1'),
    L('character', 'B ^'), L('dialogue', '2'),
    L('character', 'C ^'), L('dialogue', '3'),
  ]);
  const threeBlock = three.find((it) => it.kind === 'block');
  check('3-way: exactly one dual', three.filter((it) => it.kind === 'dual').length === 1);
  check('3-way: third speaker is a standalone caret-stripped block',
    threeBlock?.kind === 'block' && threeBlock.lines[0].text === 'C');

  // Title-page draft date is parsed into its own field.
  const tp = buildPreview(
    [
      { text: 'Title: Cold Storage', isHeading: false },
      { text: 'Draft date: 6/28/26', isHeading: false },
      { text: '', isHeading: false },
      { text: 'INT. ARCHIVE — NIGHT', isHeading: false },
    ],
    DEFAULT_SETTINGS,
  );
  check('title-page title parsed', tp.titlePage.title === 'Cold Storage');
  check('title-page draft date parsed', tp.titlePage['draft date'] === '6/28/26');
}

// --- New cue directly after dialogue (single-spaced script, no blank line) ---
{
  const fb = (text: string): FountainBlock => ({ text, isHeading: false });
  const t2 = classify([fb('MARA'), fb('You came back.'), fb('BRICK'), fb('I never left.')]);
  check('cue after dialogue, no blank -> character', t2[2] === 'character');
  check('speech after that cue -> dialogue', t2[3] === 'dialogue');
  // A normal sentence after dialogue is still dialogue (not a cue).
  const t3 = classify([fb('MARA'), fb('You came back.'), fb('Or so it seemed to her.')]);
  check('lowercase line after dialogue stays dialogue', t3[2] === 'dialogue');
  // An all-caps shout WITH punctuation stays dialogue, not a cue.
  const t4 = classify([fb('MARA'), fb('Wait.'), fb('GET OUT!'), fb('Now.')]);
  check('all-caps line with punctuation stays dialogue', t4[2] === 'dialogue');
}

// --- Audit regressions: over-eager cue / heading / transition detection ---
{
  const fb = (text: string): FountainBlock => ({ text, isHeading: false });
  // ALL-CAPS line with sentence punctuation is NOT a cue (sign / shout / chyron).
  check('all-caps question is not a cue',
    classify([fb('WHAT IS THIS?'), fb('He stares.')])[0] !== 'character');
  // ALL-CAPS interstitial between speeches is not a character cue.
  const s = classify([fb('MARY'), fb('I have to go now.'), fb('SUDDENLY'), fb('The lights go out.')]);
  check('SUDDENLY is not a character cue', s[2] !== 'character');
  // Lowercase / mixed-case transitions are recognized.
  check('lowercase "cut to:" is a transition',
    classify([fb('He runs.'), fb('cut to:'), fb('Next scene.')])[1] === 'transition');
  // A leading-dot decimal is NOT a forced scene heading; a real ".HEADING" is.
  check('".45 caliber" is not a scene heading',
    classify([fb('.45 caliber pistol on the table.')])[0] !== 'scene_heading');
  check('".A QUIET ROOM" is a forced scene heading',
    classify([fb('.A QUIET ROOM')])[0] === 'scene_heading');
  // A parenthetical aside inside action does not spawn phantom dialogue.
  const par = classify([fb('He picks up the phone.'), fb('(softly, to himself)'), fb('Hello?')]);
  check('parenthetical in action is not a dialogue-parenthetical', par[1] !== 'parenthetical');
}

// Lyrics (~) + dual-dialogue cue (^).
{
  const lyr = classify(lines('~Singing in the rain', 'Just an action line.'));
  check('~ line classifies as lyrics', lyr[0] === 'lyrics');
  check('non-~ line is not lyrics', lyr[1] !== 'lyrics');
  // A dual-dialogue cue (CHARACTER ^) still classifies as character + dialogue.
  const d = classify(lines('MARA', 'Hello.', '', 'JOHN ^', 'Hi.'));
  check('dual cue (^) classifies as character', d[3] === 'character');
  check('dual cue speech is dialogue', d[4] === 'dialogue');
}

// --- report ---
console.log(`Screenplay parser tests: ${passed} passed, ${failures.length} failed`);
for (const f of failures) console.log('  FAIL: ' + f);
if (failures.length) throw new Error(`${failures.length} screenplay test(s) failed`);
console.log('SCREENPLAY TESTS: PASS');
