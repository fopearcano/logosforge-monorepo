/** Serialized per-scene save queue tests. */

import { createSceneSaveQueue } from '../src/components/manuscript/sceneSaveQueue';

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: boolean): void => {
  if (condition) passed += 1;
  else failures.push(label);
};

{
  const writes: string[] = [];
  const statuses: string[] = [];
  const queue = createSceneSaveQueue({
    initial: 'initial',
    write: async (value) => { writes.push(value); },
    onStatus: (status) => statuses.push(status),
    onDirty: () => {},
  });
  queue.update('draft');
  check('update marks queue dirty', queue.isDirty());
  check('simple flush succeeds', await queue.flush());
  check('simple flush writes latest snapshot', writes.join(',') === 'draft');
  check('successful flush clears dirty state', !queue.isDirty() && statuses.at(-1) === 'saved');
}

{
  let releaseFirst!: () => void;
  const first = new Promise<void>((resolve) => { releaseFirst = resolve; });
  const writes: string[] = [];
  const queue = createSceneSaveQueue({
    initial: 'initial',
    write: async (value) => {
      writes.push(value);
      if (writes.length === 1) await first;
    },
    onStatus: () => {},
    onDirty: () => {},
  });
  queue.update('first edit');
  const flushing = queue.flush();
  queue.update('newest edit');
  releaseFirst();
  check('flush drains edits made during request', await flushing);
  check('in-flight edit writes a second latest snapshot', writes.join('|') === 'first edit|newest edit');
}

{
  let fail = true;
  let attempts = 0;
  const statuses: string[] = [];
  const queue = createSceneSaveQueue({
    initial: 'initial',
    write: async () => {
      attempts += 1;
      if (fail) throw new Error('offline');
    },
    onStatus: (status) => statuses.push(status),
    onDirty: () => {},
  });
  queue.update('keep me');
  check('failed flush reports false', !(await queue.flush()));
  check('failed flush retains dirty snapshot', queue.isDirty() && statuses.at(-1) === 'error');
  fail = false;
  check('retry succeeds without another edit', await queue.flush());
  check('retry actually writes again', attempts === 2 && !queue.isDirty());
}

{
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  let writes = 0;
  const queue = createSceneSaveQueue({
    initial: 'initial',
    write: async () => { writes += 1; await gate; },
    onStatus: () => {},
    onDirty: () => {},
  });
  queue.update('draft');
  const first = queue.flush();
  const second = queue.flush();
  release();
  await Promise.all([first, second]);
  check('concurrent flush callers share one write', writes === 1);
}

{
  let writes = 0;
  const queue = createSceneSaveQueue({
    initial: 'initial',
    write: async () => { writes += 1; },
    onStatus: () => {},
    onDirty: () => {},
  });
  queue.update('deleted scene draft');
  queue.cancel();
  check('explicit deletion cancels queued write', await queue.flush());
  check('cancelled queue performs no write', writes === 0 && !queue.isDirty());
}

console.log(`Scene save queue tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} scene save queue test(s) failed`);
console.log('SCENE SAVE QUEUE TESTS: PASS');
