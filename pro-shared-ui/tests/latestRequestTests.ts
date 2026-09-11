import { createLatestRequestGate } from '../src/hooks/latestRequest';

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: boolean): void => {
  if (condition) passed += 1;
  else failures.push(label);
};

const gate = createLatestRequestGate();
const first = gate.begin('pages');
const other = gate.begin('items');
const second = gate.begin('pages');
check('newer same-key request supersedes the old response', !gate.isCurrent(first));
check('newest same-key request remains current', gate.isCurrent(second));
check('independent resource key remains current', gate.isCurrent(other));
gate.invalidate('items');
check('explicit invalidation rejects an outstanding response', !gate.isCurrent(other));
gate.close();
check('unmount close rejects every outstanding response', !gate.isCurrent(second));
const whileClosed = gate.begin('closed-window');
gate.open();
const afterStrictRemount = gate.begin('pages');
check('StrictMode re-open accepts a fresh request', gate.isCurrent(afterStrictRemount));
check('StrictMode re-open never revives a pre-cleanup token', !gate.isCurrent(second));
check('request begun while closed cannot revive after re-open', !gate.isCurrent(whileClosed));

console.log(`Latest request tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} latest-request test(s) failed`);
console.log('LATEST REQUEST TESTS: PASS');
