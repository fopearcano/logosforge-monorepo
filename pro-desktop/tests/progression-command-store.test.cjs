const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const Module = require('node:module');
const os = require('node:os');
const path = require('node:path');

let passed = 0;
function check(label, condition) {
  assert.ok(condition, label);
  passed += 1;
}

async function rejects(label, work, pattern) {
  await assert.rejects(async () => work(), pattern, label);
  passed += 1;
}

const scope = 'logosforge-pro-desktop-local-core';
const storageKey = `logosforge.pro.progressions.pending.v1:${encodeURIComponent(scope)}:2`;
const revision = 'a'.repeat(64);
const envelope = ({
  saveKey = 'progression-action:2:create-track',
  idempotencyKey = 'progression-store-key-0001',
  title = 'Departure',
  resendAttempted = false,
  receiptOnly = false,
} = {}) => JSON.stringify({
  version: 1,
  scope,
  storedAt: 1_700_000_000_000,
  saveKey,
  pending: {
    projectId: 2,
    command: {
      kind: 'create_track',
      expected_revision: revision,
      track_kind: 'story',
      title,
      description: '',
      color: '',
      primary_psyke_entry_id: null,
      secondary_psyke_entry_id: null,
    },
    key: idempotencyKey,
    resendAttempted,
    receiptOnly,
  },
});

async function main() {
  const userData = await fs.mkdtemp(path.join(os.tmpdir(), 'logosforge-pro-progression-store-'));
  const electronMock = {
    app: { getPath: (name) => {
      assert.equal(name, 'userData');
      return userData;
    } },
  };
  const originalLoad = Module._load;
  Module._load = function loadWithElectronMock(request, parent, isMain) {
    if (request === 'electron') return electronMock;
    return originalLoad.call(this, request, parent, isMain);
  };

  let store;
  try {
    store = require('../dist-electron/progression-command-store.js');
  } finally {
    Module._load = originalLoad;
  }

  try {
    assert.equal(await store.loadProgressionCommandRecovery(storageKey), null);
    passed += 1;

    const initial = envelope();
    await store.saveProgressionCommandRecovery(storageKey, initial);
    assert.equal(await store.loadProgressionCommandRecovery(storageKey), initial);
    passed += 1;

    const locked = envelope({ receiptOnly: true });
    await store.saveProgressionCommandRecovery(storageKey, locked);
    assert.equal(await store.loadProgressionCommandRecovery(storageKey), locked);
    passed += 1;

    await rejects(
      'receipt-only safety cannot move backwards',
      () => store.saveProgressionCommandRecovery(storageKey, initial),
      /cannot move backwards/i,
    );
    const resendLocked = envelope({ resendAttempted: true, receiptOnly: true });
    await store.saveProgressionCommandRecovery(storageKey, resendLocked);
    await rejects(
      'resend-attempted safety cannot move backwards',
      () => store.saveProgressionCommandRecovery(storageKey, locked),
      /cannot move backwards/i,
    );
    await rejects(
      'a different immutable command cannot replace the unresolved slot',
      () => store.saveProgressionCommandRecovery(storageKey, envelope({ title: 'Return' })),
      /different unresolved/i,
    );

    const staleExpected = envelope({ idempotencyKey: 'progression-store-key-9999' });
    assert.equal(
      await store.removeProgressionCommandRecovery(storageKey, staleExpected),
      false,
    );
    assert.equal(await store.loadProgressionCommandRecovery(storageKey), resendLocked);
    passed += 2;

    assert.equal(await store.removeProgressionCommandRecovery(storageKey, initial), true);
    assert.equal(await store.loadProgressionCommandRecovery(storageKey), null);
    passed += 2;

    const next = envelope({
      saveKey: 'progression-action:2:create-track-next',
      idempotencyKey: 'progression-store-key-0002',
      title: 'Return',
    });
    await store.saveProgressionCommandRecovery(storageKey, next);
    assert.equal(await store.loadProgressionCommandRecovery(storageKey), next);
    passed += 1;

    const storeDirectory = path.join(userData, 'progression-command-recovery');
    const primaryName = (await fs.readdir(storeDirectory))
      .find((entry) => entry.endsWith('.json'));
    assert.ok(primaryName, 'the store must create one stable primary file');
    const primaryPath = path.join(storeDirectory, primaryName);
    const backupPath = `${primaryPath}.bak`;
    await fs.writeFile(primaryPath, '{corrupt primary', 'utf8');
    // The preceding fsynced tombstone is the safe recovery generation; a
    // corrupt replacement therefore cannot resurrect the older command.
    assert.equal(await store.loadProgressionCommandRecovery(storageKey), null);
    passed += 1;
    check('a backup generation is retained', await fs.stat(backupPath).then(() => true, () => false));

    await rejects(
      'untrusted storage keys are rejected before filesystem access',
      () => store.loadProgressionCommandRecovery('../../outside'),
      /storage key/i,
    );
    await rejects(
      'envelope project ids must match their storage slot',
      () => store.saveProgressionCommandRecovery(
        storageKey.replace(/:2$/, ':3'),
        initial,
      ),
      /envelope|command/i,
    );
    await rejects(
      'oversized envelopes are rejected',
      () => store.saveProgressionCommandRecovery(storageKey, 'x'.repeat(128 * 1024 + 1)),
      /128 KiB/i,
    );

    await store.drainProgressionCommandRecoveryOperations();
    const leftovers = (await fs.readdir(storeDirectory))
      .filter((entry) => entry.endsWith('.tmp'));
    check('durable writes leave no temporary generation behind', leftovers.length === 0);
  } finally {
    await fs.rm(userData, { recursive: true, force: true });
  }

  console.log(`Progressions command store tests: ${passed} passed, 0 failed`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
