/** Controlled Apply conflict + diff tests. */

import { assertApplyTargetUnchanged, assertSceneContentUnchanged, lineDiff } from '../src/components/aipanels/applyToScene';

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: boolean): void => {
  if (condition) passed += 1;
  else failures.push(label);
};

assertSceneContentUnchanged('same scene', 'same scene');
check('unchanged scene may be applied', true);
let conflict = '';
try { assertSceneContentUnchanged('old scene', 'new local edit'); }
catch (error) { conflict = error instanceof Error ? error.message : ''; }
check('stale proposal is rejected', conflict.includes('scene changed'));

const target = { projectId: 7, id: 3, title: 'Opening', content: 'same scene' };
assertApplyTargetUnchanged(target, 7, 'same scene');
check('matching project and scene snapshot may be applied', true);
let projectConflict = '';
try { assertApplyTargetUnchanged(target, 8, 'same scene'); }
catch (error) { projectConflict = error instanceof Error ? error.message : ''; }
check('proposal from another project is rejected', projectConflict.includes('active project changed'));

const rows = lineDiff('one\ntwo\nthree', 'one\nchanged\nthree');
check('line diff keeps context', rows.filter((row) => row.type === 'ctx').length === 2);
check('line diff exposes deletion', rows.some((row) => row.type === 'del' && row.text === 'two'));
check('line diff exposes addition', rows.some((row) => row.type === 'add' && row.text === 'changed'));

console.log(`Controlled Apply tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} controlled apply test(s) failed`);
console.log('CONTROLLED APPLY TESTS: PASS');
