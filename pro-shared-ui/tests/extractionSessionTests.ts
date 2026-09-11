import {
  forgetExtraction,
  recallExtraction,
  rememberExtraction,
} from '../src/hooks/extractionSession';

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: boolean): void => {
  if (condition) passed += 1;
  else failures.push(label);
};

forgetExtraction(91);
rememberExtraction(91, { jobId: 'job-91' });
check('active job is remembered by project', recallExtraction(91)?.jobId === 'job-91');
check('another project cannot see the job', recallExtraction(92) == null);
const copy = recallExtraction(91)!;
copy.jobId = 'mutated';
check('callers cannot mutate remembered state', recallExtraction(91)?.jobId === 'job-91');
forgetExtraction(91);
check('forgotten extraction state is absent', recallExtraction(91) == null);

console.log(`Extraction session tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} extraction-session test(s) failed`);
console.log('EXTRACTION SESSION TESTS: PASS');
