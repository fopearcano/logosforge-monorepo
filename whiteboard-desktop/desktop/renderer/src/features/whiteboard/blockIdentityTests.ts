/** Pure stable-block-id tests. Run with `npm run test:block-ids`. */

import { chooseIdentityKeeper, freshBlockIds, normalizeBlockIds } from './blockIdentity';

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: boolean): void => {
  if (condition) passed += 1;
  else failures.push(label);
};

const ids = normalizeBlockIds(['chapter', '', 'chapter', null, 'scene']);
check('first valid id is preserved', ids[0] === 'chapter');
check('another valid id is preserved', ids[4] === 'scene');
check('blank id is replaced', ids[1].startsWith('block-'));
check('duplicate id is replaced', ids[2] !== 'chapter');
check('non-string id is replaced', ids[3].startsWith('block-'));
check('all normalized ids are unique', new Set(ids).size === ids.length);
const fresh = freshBlockIds(3);
check('fresh identity set has requested size', fresh.length === 3);
check('fresh identity set is unique', new Set(fresh).size === fresh.length);
check(
  'split at start keeps id on unchanged text half',
  chooseIdentityKeeper('Original text', 0, [
    { text: '', position: 0 },
    { text: 'Original text', position: 2 },
  ]) === 1,
);
check(
  'split in middle keeps id on prefix half',
  chooseIdentityKeeper('Original text', 0, [
    { text: 'Original', position: 0 },
    { text: ' text', position: 10 },
  ]) === 0,
);
check(
  'pasted duplicate does not steal original id',
  chooseIdentityKeeper('Same', 20, [
    { text: 'Same', position: 0 },
    { text: 'Same', position: 20 },
  ]) === 1,
);

console.log(`Block identity tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} block identity test(s) failed`);
console.log('BLOCK IDENTITY TESTS: PASS');
