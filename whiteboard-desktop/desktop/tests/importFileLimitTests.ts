import { promises as fs } from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';

import {
  MAX_PENDING_DOCUMENT_PAYLOAD_BYTES,
  MAX_RECOVERY_IMPORT_FILE_BYTES,
  assertImportFileIdentity,
  assertImportFileMetadata,
  readBoundedImportHandle,
  readBoundedImportTextFile,
} from '../electron/import-file-limit';
import { MAX_LOGOSFORGE_BYTES } from '../renderer/src/features/files/importExportFormats';

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: boolean): void => {
  if (condition) passed += 1;
  else failures.push(label);
};

let nonFileRejected = false;
let oversizedRejected = false;
try {
  assertImportFileMetadata({ size: 10, isFile: () => false });
} catch {
  nonFileRejected = true;
}
try {
  assertImportFileMetadata({ size: MAX_RECOVERY_IMPORT_FILE_BYTES + 1, isFile: () => true });
} catch {
  oversizedRejected = true;
}
check('non-regular import paths are rejected', nonFileRejected);
check('oversized import files are rejected', oversizedRejected);
assertImportFileMetadata({ size: MAX_RECOVERY_IMPORT_FILE_BYTES, isFile: () => true });
check('regular file at exact cap is accepted', true);
check('renderer and main caps match', MAX_LOGOSFORGE_BYTES === MAX_RECOVERY_IMPORT_FILE_BYTES);
check(
  'whiteboard conflict patch plus merged document fits bounded envelope',
  MAX_RECOVERY_IMPORT_FILE_BYTES === (2 * MAX_PENDING_DOCUMENT_PAYLOAD_BYTES) + (1024 * 1024),
);
check(
  'pending recovery payload fits bounded envelope',
  MAX_PENDING_DOCUMENT_PAYLOAD_BYTES + (1024 * 1024) <= MAX_RECOVERY_IMPORT_FILE_BYTES,
);
check(
  'outline recovery payload fits bounded envelope',
  MAX_PENDING_DOCUMENT_PAYLOAD_BYTES + (1024 * 1024) <= MAX_RECOVERY_IMPORT_FILE_BYTES,
);

const temp = await fs.mkdtemp(path.join(os.tmpdir(), 'lf-import-limit-'));
try {
  const stablePath = path.join(temp, 'stable.json');
  await fs.writeFile(stablePath, '{"ok":true}', 'utf8');
  check(
    'bounded reader reads one stable regular file',
    await readBoundedImportTextFile(stablePath) === '{"ok":true}',
  );

  const oversizePath = path.join(temp, 'oversize.json');
  await fs.writeFile(oversizePath, 'x', 'utf8');
  await fs.truncate(oversizePath, MAX_RECOVERY_IMPORT_FILE_BYTES + 1);
  let realOversizeRejected = false;
  try {
    await readBoundedImportTextFile(oversizePath);
  } catch {
    realOversizeRejected = true;
  }
  check('real oversized file is rejected before allocation', realOversizeRejected);

  const otherPath = path.join(temp, 'other.json');
  await fs.writeFile(otherPath, '{}', 'utf8');
  const stableStats = await fs.lstat(stablePath);
  const otherStats = await fs.lstat(otherPath);
  let swapRejected = false;
  try {
    assertImportFileIdentity(stableStats, stableStats, otherStats);
  } catch {
    swapRejected = true;
  }
  check('path identity swap is rejected', swapRejected);

  const growthPath = path.join(temp, 'growth.json');
  await fs.writeFile(growthPath, 'abc', 'utf8');
  const growthHandle = await fs.open(growthPath, 'r');
  const beforeGrowth = await growthHandle.stat();
  await fs.appendFile(growthPath, 'd', 'utf8');
  let growthRejected = false;
  try {
    await readBoundedImportHandle(growthHandle, beforeGrowth);
  } catch {
    growthRejected = true;
  } finally {
    await growthHandle.close();
  }
  check('growth after fstat is rejected', growthRejected);

  const truncationPath = path.join(temp, 'truncation.json');
  await fs.writeFile(truncationPath, 'abcd', 'utf8');
  const truncationHandle = await fs.open(truncationPath, 'r');
  const beforeTruncation = await truncationHandle.stat();
  await fs.truncate(truncationPath, 2);
  let truncationRejected = false;
  try {
    await readBoundedImportHandle(truncationHandle, beforeTruncation);
  } catch {
    truncationRejected = true;
  } finally {
    await truncationHandle.close();
  }
  check('truncation after fstat is rejected', truncationRejected);

  const symlinkPath = path.join(temp, 'link.json');
  let symlinkRejected = false;
  try {
    await fs.symlink(stablePath, symlinkPath, 'file');
    try {
      await readBoundedImportTextFile(symlinkPath);
    } catch {
      symlinkRejected = true;
    }
  } catch (error) {
    // Windows can deny symlink creation unless Developer Mode is enabled.
    const code = (error as NodeJS.ErrnoException).code;
    if (code === 'EPERM' || code === 'EACCES') {
      try {
        assertImportFileMetadata({ size: 1, isFile: () => false });
      } catch {
        symlinkRejected = true;
      }
    } else {
      throw error;
    }
  }
  check('symlink import path is rejected', symlinkRejected);
} finally {
  await fs.rm(temp, { recursive: true, force: true });
}

console.log(`Import file limit tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.log(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} import-file-limit test(s) failed`);
console.log('IMPORT FILE LIMIT TESTS: PASS');
