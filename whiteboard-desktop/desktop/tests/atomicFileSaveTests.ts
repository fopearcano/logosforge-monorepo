import * as path from 'node:path';

import {
  atomicWriteTextFile,
  type AtomicFileSystem,
  type AtomicWriteHandle,
} from '../electron/atomic-file-save';
import { PendingOperationTracker } from '../electron/pending-operation-tracker';

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: boolean): void => {
  if (condition) passed += 1;
  else failures.push(label);
};

interface FakeFileSystem extends AtomicFileSystem {
  files: Map<string, string>;
  events: string[];
}

function createFakeFileSystem(options: { failWrite?: boolean; failRename?: boolean } = {}): FakeFileSystem {
  const files = new Map<string, string>();
  const events: string[] = [];
  return {
    files,
    events,
    async openExclusive(filePath) {
      events.push(`open:${filePath}`);
      if (files.has(filePath)) {
        throw Object.assign(new Error('exists'), { code: 'EEXIST' });
      }
      files.set(filePath, '');
      const handle: AtomicWriteHandle = {
        async writeText(content) {
          events.push('write');
          if (options.failWrite) throw new Error('injected write failure');
          files.set(filePath, content);
        },
        async sync() {
          events.push('sync-file');
        },
        async close() {
          events.push('close');
        },
      };
      return handle;
    },
    async rename(sourcePath, destinationPath) {
      events.push(`rename:${sourcePath}->${destinationPath}`);
      if (options.failRename) throw new Error('injected rename failure');
      const content = files.get(sourcePath);
      if (content === undefined) throw new Error('source missing');
      files.set(destinationPath, content);
      files.delete(sourcePath);
    },
    async remove(filePath) {
      events.push(`remove:${filePath}`);
      if (!files.delete(filePath)) throw Object.assign(new Error('missing'), { code: 'ENOENT' });
    },
    async syncDirectory(directoryPath) {
      events.push(`sync-directory:${directoryPath}`);
    },
  };
}

const destination = path.join('workspace', 'draft.fountain');
const tempPath = path.join('workspace', '.draft.fountain.test.tmp');

const successful = createFakeFileSystem();
successful.files.set(destination, 'old');
await atomicWriteTextFile(destination, 'new', {
  fileSystem: successful,
  createTempPath: () => tempPath,
});
check('successful save replaces destination content', successful.files.get(destination) === 'new');
check('successful save leaves no temp file', !successful.files.has(tempPath));
check(
  'file is flushed and closed before the atomic rename',
  successful.events.indexOf('sync-file') < successful.events.findIndex((event) => event.startsWith('rename:'))
    && successful.events.indexOf('close') < successful.events.findIndex((event) => event.startsWith('rename:')),
);
check(
  'temp file is allocated beside destination',
  path.dirname(successful.events[0].slice('open:'.length)) === path.dirname(destination),
);
check('containing directory is synced after rename', successful.events.at(-1) === `sync-directory:${path.dirname(destination)}`);

const writeFailure = createFakeFileSystem({ failWrite: true });
writeFailure.files.set(destination, 'old');
let writeRejected = false;
try {
  await atomicWriteTextFile(destination, 'new', {
    fileSystem: writeFailure,
    createTempPath: () => tempPath,
  });
} catch {
  writeRejected = true;
}
check('write failure is reported', writeRejected);
check('write failure preserves existing destination', writeFailure.files.get(destination) === 'old');
check('write failure removes temp file', !writeFailure.files.has(tempPath));
check('write failure never attempts rename', !writeFailure.events.some((event) => event.startsWith('rename:')));

const renameFailure = createFakeFileSystem({ failRename: true });
renameFailure.files.set(destination, 'old');
let renameRejected = false;
try {
  await atomicWriteTextFile(destination, 'new', {
    fileSystem: renameFailure,
    createTempPath: () => tempPath,
  });
} catch {
  renameRejected = true;
}
check('rename failure is reported', renameRejected);
check('rename failure preserves existing destination', renameFailure.files.get(destination) === 'old');
check('rename failure removes temp file', !renameFailure.files.has(tempPath));
check('rename happens only after close', renameFailure.events.indexOf('close') < renameFailure.events.findIndex((event) => event.startsWith('rename:')));

let resolveFirst!: () => void;
let resolveSecond!: () => void;
const first = new Promise<void>((resolve) => { resolveFirst = resolve; });
const second = new Promise<void>((resolve) => { resolveSecond = resolve; });
const tracker = new PendingOperationTracker();
void tracker.track(first);
let drainSettled = false;
const drain = tracker.drain().then(() => { drainSettled = true; });
await Promise.resolve();
check('drain waits for tracked operation', !drainSettled && tracker.size === 1);
void tracker.track(second);
resolveFirst();
await Promise.resolve();
await Promise.resolve();
check('drain also waits for operation added while draining', !drainSettled && tracker.size === 1);
resolveSecond();
await drain;
check('drain settles only after every tracked operation', drainSettled && tracker.size === 0);

console.log(`Atomic file save tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} atomic-file-save test(s) failed`);
console.log('ATOMIC FILE SAVE TESTS: PASS');
