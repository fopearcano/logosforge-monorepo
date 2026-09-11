import {
  ExtractionPollingCancelled,
  pollExtractionJob,
} from '../src/hooks/extractionPolling';
import type { ExtractionJobDTO } from '@logosforge/ui-contracts';

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: boolean): void => {
  if (condition) passed += 1;
  else failures.push(label);
};
const job = (status: string, done = 0): ExtractionJobDTO => ({ job_id: 'job-1', status, done, total: 2 });

{
  const sequence = [job('cancelling', 1), job('done', 2)];
  const progress: string[] = [];
  const outcome = await pollExtractionJob({
    initial: job('running'),
    load: async () => sequence.shift()!,
    signal: new AbortController().signal,
    intervalMs: 0,
    onProgress: (value) => progress.push(value.status),
  });
  check('poll follows running through cancelling to done', outcome.kind === 'done');
  check('poll publishes every observed state', progress.join(',') === 'running,cancelling,done');
}

{
  const outcome = await pollExtractionJob({
    initial: job('running'), load: async () => job('running'),
    signal: new AbortController().signal, intervalMs: 0, maxPolls: 2,
  });
  check('poll has an explicit bounded timeout', outcome.kind === 'timeout');
}

{
  const outcome = await pollExtractionJob({
    initial: job('cancelled'), load: async () => job('done'),
    signal: new AbortController().signal, intervalMs: 0,
  });
  check('cancelled job is terminal without another request', outcome.kind === 'cancelled');
}

{
  const controller = new AbortController();
  const polling = pollExtractionJob({
    initial: job('running'), load: async () => job('done'),
    signal: controller.signal, intervalMs: 60_000,
  });
  controller.abort();
  let cancelled = false;
  try { await polling; } catch (error) { cancelled = error instanceof ExtractionPollingCancelled; }
  check('AbortSignal interrupts the wait immediately', cancelled);
}

console.log(`Extraction polling tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} extraction-polling test(s) failed`);
console.log('EXTRACTION POLLING TESTS: PASS');
