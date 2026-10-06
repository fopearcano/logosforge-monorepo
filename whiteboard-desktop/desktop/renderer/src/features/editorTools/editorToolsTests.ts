/**
 * Nerd Mode editor-tools tests. Pure — no editor/DOM. Runs headlessly
 * (esbuild + node): `npm run test:editor-tools`. Throws (non-zero) on failure.
 */

import type { FountainBlock } from '../screenplay/fountainTypes';
import { DEFAULT_EDITOR_TOOLS, EDITOR_TYPEFACES, normalizeSystemFontFamily } from './editorToolTypes';
import { EDITOR_TYPEFACE_STACKS, editorToolsAttrs, editorToolsVars, installedTypefaceStack } from './editorToolsSurface';
import { findFoldableRegions, headingLevel, hiddenBlocks, isFoldHead } from './folding/foldingModel';
import { gutterDigits, lineNumbersForCount } from './lineNumbers/lineNumbers';
import { classifySyntax } from './syntax/syntaxClassifier';
import { normalizeEditorTools } from './useEditorTools';

let passed = 0;
const failures: string[] = [];
function check(label: string, cond: boolean) {
  if (cond) passed += 1;
  else failures.push(label);
}
const json = (v: unknown) => JSON.stringify(v);

const line = (text: string): FountainBlock => ({ text, isHeading: false });
const lines = (...t: string[]): FountainBlock[] => t.map(line);
const heading = (text: string, level: number): FountainBlock => ({ text, isHeading: true, level });
const tokens = (blocks: FountainBlock[], mode: string) =>
  classifySyntax(blocks, mode).map((b) => b.token);
const inlineOf = (text: string, mode: string) =>
  classifySyntax([line(text)], mode)[0].inline.map((s) => s.token);

// 1. Line numbers
check('line numbers 1..3', json(lineNumbersForCount(3)) === json([1, 2, 3]));
check('line numbers empty', json(lineNumbersForCount(0)) === json([]));
check('gutter digits 9', gutterDigits(9) === 1);
check('gutter digits 10', gutterDigits(10) === 2);
check('gutter digits 0 -> 1', gutterDigits(0) === 1);

// 2. Heading level
check('headingLevel node', headingLevel(heading('Act', 2)) === 2);
check('headingLevel hash', headingLevel(line('## Foo')) === 2);
check('headingLevel hash1', headingLevel(line('# Foo')) === 1);
check('headingLevel plain', headingLevel(line('plain text')) === 0);

// 3. Foldable regions — headings (novel)
{
  const blocks = [heading('Chapter One', 1), line('a'), line('b'), heading('Chapter Two', 1), line('c')];
  const regions = findFoldableRegions(blocks, 'novel');
  check('novel: two heading regions', regions.length === 2);
  check('novel: first region body', regions[0].head === 0 && regions[0].end === 2);
  check('novel: second region body', regions[1].head === 3 && regions[1].end === 4);
  check('fold head 0 hides 1,2', json([...hiddenBlocks(regions, new Set([0]))]) === json([1, 2]));
  check('no fold hides nothing', hiddenBlocks(regions, new Set()).size === 0);
  check('isFoldHead 0', isFoldHead(regions, 0) && !isFoldHead(regions, 1));
}

// 4. Nested headings — folding the parent hides the child + content
{
  const blocks = [heading('Act', 1), heading('Seq', 2), line('x'), heading('Act 2', 1)];
  const regions = findFoldableRegions(blocks, 'screenplay');
  const top = regions.find((r) => r.head === 0)!;
  const sub = regions.find((r) => r.head === 1)!;
  check('nested: parent ends at 2', top.end === 2);
  check('nested: child ends at 2', sub.end === 2);
  check('nested: fold parent hides child+content', json([...hiddenBlocks(regions, new Set([0]))]) === json([1, 2]));
}

// 5. Screenplay multi-block note + boneyard regions
{
  const note = findFoldableRegions(lines('action', '[[', 'a note', ']]', 'more'), 'screenplay').find(
    (r) => r.kind === 'note',
  );
  check('note region head/end', !!note && note.head === 1 && note.end === 3);
  const bone = findFoldableRegions(lines('/*', 'cut', '*/', 'keep'), 'screenplay').find(
    (r) => r.kind === 'boneyard',
  );
  check('boneyard region head/end', !!bone && bone.head === 0 && bone.end === 2);
  // Novel mode has no note/boneyard folding.
  check('novel: no note folding', !findFoldableRegions(lines('[[', 'x', ']]'), 'novel').some((r) => r.kind === 'note'));
}

// 6. Screenplay syntax categories
{
  const blocks = [
    heading('Act One', 1),
    line('INT. HOUSE - DAY'),
    line('He runs.'),
    line('JOHN'),
    line('Hello.'),
    line('(softly)'),
    line('Bye.'),
    line('CUT TO:'),
    line('= a synopsis'),
    line('[[a note]]'),
  ];
  check(
    'screenplay tokens',
    json(tokens(blocks, 'screenplay')) ===
      json([
        'section',
        'scene_heading',
        'action',
        'character',
        'dialogue',
        'parenthetical',
        'dialogue',
        'transition',
        'synopsis',
        'note',
      ]),
  );
  check('screenplay title field', tokens(lines('Title: My Film', '', 'INT. X'), 'screenplay')[0] === 'title_field');
  check('screenplay boneyard token', tokens(lines('/*', 'cut', '*/'), 'screenplay').every((t) => t === 'boneyard'));
}

// 7. Novel / Notes syntax categories
{
  const blocks = [heading('Chapter', 1), heading('Section', 2), heading('Sub', 3), line('prose'), line('- item'), line('- [ ] todo')];
  check(
    'novel tokens',
    json(tokens(blocks, 'novel')) === json(['chapter', 'heading', 'subheading', 'plain', 'bullet', 'checkbox']),
  );
}

// 8. Inline tokens (shared)
check('inline emphasis', inlineOf('a **b** c', 'screenplay').includes('emphasis'));
check('inline note', inlineOf('see [[this]] ok', 'novel').includes('note'));
check('inline todo', inlineOf('remember TODO later', 'novel').includes('todo'));
check('inline tag (notes)', inlineOf('a #idea and @bob', 'notes').filter((t) => t === 'tag').length === 2);
check('inline link', inlineOf('see [t](http://x.com) here', 'notes').includes('link'));
check('inline checkbox (notes)', inlineOf('- [x] done', 'notes').includes('checkbox'));
check('no tags in screenplay', !inlineOf('a #idea here', 'screenplay').includes('tag'));

// 9. Stage / Graphic Novel reuse their real mode classifiers for semantic colour.
check(
  'stage syntax categories',
  json(tokens(lines('ACT I', 'MARA', 'Hello.', '(quietly)'), 'stage_script')) ===
    json(['scene_heading', 'character', 'dialogue', 'parenthetical']),
);
check(
  'graphic novel syntax categories',
  json(tokens(lines('PAGE ONE', 'PANEL 1', 'CAPTION: Later', 'SFX: BOOM', 'MARA: Go.'), 'graphic_novel')) ===
    json(['chapter', 'subheading', 'note', 'transition', 'dialogue']),
);

// 10. Editor-view typography + persisted preference normalization.
{
  const tools = {
    ...DEFAULT_EDITOR_TOOLS,
    typeface: 'handwritten' as const,
    textColor: '#A1B2C3',
  };
  const attrs = editorToolsAttrs(tools);
  const vars = editorToolsVars(tools);
  check('typeface emits its surface gate', attrs['data-editor-typeface'] === 'handwritten');
  check('handwritten stack reaches CSS', /cursive/.test(vars['--wb-editor-typeface'] ?? ''));
  check('manuscript colour reaches CSS', vars['--wb-editor-ink'] === '#A1B2C3');
  check(
    'every non-default typeface has a stack',
    EDITOR_TYPEFACES.filter((face) => face !== 'default' && face !== 'installed')
      .every((face) => Boolean(EDITOR_TYPEFACE_STACKS[face])),
  );
  check(
    'typewriter stack stays distinct from bundled screenplay Courier',
    EDITOR_TYPEFACE_STACKS.typewriter !== EDITOR_TYPEFACE_STACKS['courier-prime'] &&
      !EDITOR_TYPEFACE_STACKS.typewriter.includes("'Courier Prime'"),
  );
  check(
    'chalkboard and handwritten stacks prefer different platform faces',
    EDITOR_TYPEFACE_STACKS.chalkboard.split(',')[0] !== EDITOR_TYPEFACE_STACKS.handwritten.split(',')[0],
  );

  const normalized = normalizeEditorTools({
    syntax: false,
    typeface: 'courier-prime',
    textColor: '#ABCDEF',
    fontSize: 20,
    lineHeight: 1.7,
    layout: 'paged',
  });
  check('normalizer keeps valid typeface', normalized.typeface === 'courier-prime');
  check('normalizer canonicalizes colour', normalized.textColor === '#abcdef');
  check('normalizer keeps valid typography', normalized.fontSize === 20 && normalized.lineHeight === 1.7);
  const rejected = normalizeEditorTools({ typeface: 'remote-font', textColor: 'url(evil)', fontSize: 99 });
  check(
    'normalizer rejects invalid CSS preferences',
    rejected.typeface === 'default' && rejected.textColor === null && rejected.fontSize === null,
  );
  check('system font accepts international family', normalizeSystemFontFamily('  Noto Sans CJK 日本語  ') === 'Noto Sans CJK 日本語');
  check('system font rejects CSS fallback list', normalizeSystemFontFamily('Garamond, serif') === null);
  check('system font rejects CSS injection', normalizeSystemFontFamily('Garamond; color: red') === null);
  const installed = normalizeEditorTools({ typeface: 'installed', systemFontFamily: 'EB Garamond' });
  check('normalizer keeps installed font family', installed.systemFontFamily === 'EB Garamond');
  check('installed font stack is safely quoted', installedTypefaceStack(installed.systemFontFamily) === '"EB Garamond", var(--wb-mode-typeface)');
  check('installed font reaches surface', editorToolsVars(installed)['--wb-editor-typeface'] === '"EB Garamond", var(--wb-mode-typeface)');
  const missingInstalled = { ...DEFAULT_EDITOR_TOOLS, typeface: 'installed' as const };
  check('empty installed font does not gate surface', !('data-editor-typeface' in editorToolsAttrs(missingInstalled)));
}

// --- report ---
console.log(`Editor tools tests: ${passed} passed, ${failures.length} failed`);
for (const f of failures) console.log('  FAIL: ' + f);
if (failures.length) throw new Error(`${failures.length} editor-tools test(s) failed`);
console.log('EDITOR TOOLS TESTS: PASS');
