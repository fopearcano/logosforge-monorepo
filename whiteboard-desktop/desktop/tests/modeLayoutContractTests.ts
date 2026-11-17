import fs from 'node:fs';
import path from 'node:path';

import { modeBehavior } from '../renderer/src/features/whiteboard/modes';

interface CssRule {
  selectors: string[];
  declarations: string;
}

const cssPath = path.join(process.cwd(), 'renderer', 'src', 'styles', 'app.css');
const css = fs.readFileSync(cssPath, 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
const rules: CssRule[] = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((match) => ({
  selectors: match[1].split(',').map((selector) => selector.trim()).filter(Boolean),
  declarations: match[2],
}));

const failures: string[] = [];
const check = (label: string, condition: boolean): void => {
  if (!condition) failures.push(label);
};

const exposedModes = ['novel', 'screenplay', 'graphic_novel', 'stage_script'] as const;
for (const mode of exposedModes) {
  check(`${mode} mode is registered`, modeBehavior(mode).id === mode);
}
check('legacy series mode normalizes to the Novel layout', modeBehavior('series').id === 'novel');

const novelIndentRules = rules.flatMap((rule) =>
  rule.selectors
    .filter((selector) =>
      selector.includes('[data-writing-mode="novel"]')
      && /(?:^|;)\s*text-indent\s*:/.test(rule.declarations),
    )
    .map((selector) => ({ selector, declarations: rule.declarations })),
);
check('Novel has one paragraph indentation rule', novelIndentRules.length === 1);
check(
  'Novel indentation applies to every body paragraph',
  novelIndentRules.length === 1
    && novelIndentRules[0].selector === '.wb-editor[data-writing-mode="novel"] p'
    && /text-indent\s*:\s*1\.7em\s*;?/.test(novelIndentRules[0].declarations),
);

for (const { selector } of novelIndentRules) {
  if (/:first-|:last-|:nth-|\+\s*p\b/.test(selector)) {
    failures.push(`Novel body alignment depends on document position: ${selector}`);
  }
}

for (const mode of exposedModes.filter((value) => value !== 'novel')) {
  const unexpected = rules.flatMap((rule) =>
    rule.selectors.filter((selector) =>
      selector.includes(`[data-writing-mode="${mode}"]`)
      && /(?:^|;)\s*text-indent\s*:/.test(rule.declarations),
    ),
  );
  check(`${mode} does not inherit Novel paragraph indentation`, unexpected.length === 0);
}

const positionDependentHorizontalRules = rules.flatMap((rule) => {
  if (!/(?:text-indent|text-align|padding-left|margin-left)\s*:/.test(rule.declarations)) return [];
  return rule.selectors.filter((selector) =>
    exposedModes.some((mode) => selector.includes(`[data-writing-mode="${mode}"]`))
    && /:first-|:last-|:nth-|\+\s*(?:[a-z]|\.|\[)/i.test(selector),
  );
});
check(
  'No writing mode changes horizontal alignment by sibling position',
  positionDependentHorizontalRules.length === 0,
);

for (const marker of [
  '.wb-editor[data-writing-mode="screenplay"] > .sp-dialogue',
  '.wb-editor[data-writing-mode="graphic_novel"] p',
  '.wb-editor[data-writing-mode="graphic_novel"] .gn-dialogue',
  '.wb-editor[data-writing-mode="stage_script"] .sp-action',
  '.wb-editor[data-writing-mode="stage_script"] .sp-dialogue',
]) {
  check(`Mode layout CSS retains ${marker}`, css.includes(marker));
}

console.log(`Mode layout contract tests: ${exposedModes.length} modes · ${rules.length} CSS rules`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} mode layout contract test(s) failed`);
console.log('MODE LAYOUT CONTRACT TESTS: PASS');
