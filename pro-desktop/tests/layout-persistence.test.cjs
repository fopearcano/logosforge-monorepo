const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const Module = require('node:module');
const os = require('node:os');
const path = require('node:path');

const MAX_LAYOUT_BYTES = 256 * 1024;

let passed = 0;
function check(label, condition) {
  assert.ok(condition, label);
  passed += 1;
}

async function rejects(label, work, pattern) {
  await assert.rejects(work, pattern, label);
  passed += 1;
}

async function main() {
  const userData = await fs.mkdtemp(path.join(os.tmpdir(), 'logosforge-pro-layout-'));
  const layouts = path.join(userData, 'layouts');
  const sessionPath = path.join(userData, 'session-state.json');
  const sessionBackupPath = `${sessionPath}.bak`;
  const layoutPath = (projectId) => path.join(layouts, `${projectId}.json`);
  const backupPath = (projectId) => `${layoutPath(projectId)}.bak`;
  const tempFiles = async () => {
    try {
      return (await fs.readdir(layouts)).filter((entry) => entry.endsWith('.tmp'));
    } catch (error) {
      if (error && error.code === 'ENOENT') return [];
      throw error;
    }
  };
  const sessionTemporaryFiles = async () => (await fs.readdir(userData))
    .filter((entry) => entry.startsWith('.session-state.json.')
      && (entry.endsWith('.tmp') || entry.endsWith('.retired')));

  const electronMock = {
    app: { getPath: (name) => {
      assert.equal(name, 'userData');
      return userData;
    } },
    dialog: {},
    shell: {},
  };
  const originalLoad = Module._load;
  Module._load = function loadWithElectronMock(request, parent, isMain) {
    if (request === 'electron') return electronMock;
    return originalLoad.call(this, request, parent, isMain);
  };

  let manager;
  try {
    manager = require('../dist-electron/file-manager.js');
  } finally {
    Module._load = originalLoad;
  }

  try {
    assert.equal(await manager.loadDesktopSessionState(), null);
    passed += 1;

    await manager.saveLastActiveProjectId(11);
    assert.deepEqual(
      await manager.loadDesktopSessionState(),
      { version: 1, lastActiveProjectId: 11 },
    );
    passed += 1;
    assert.deepEqual(
      JSON.parse(await fs.readFile(sessionPath, 'utf8')),
      { version: 1, lastActiveProjectId: 11 },
    );
    passed += 1;
    check('session save leaves no temporary generation behind', (await sessionTemporaryFiles()).length === 0);

    // Host writes are serialized in invocation order. The last rapid switch
    // must remain authoritative even when callers do not await each other.
    await Promise.all([
      manager.saveLastActiveProjectId(31),
      manager.saveLastActiveProjectId(32),
      manager.saveLastActiveProjectId(33),
    ]);
    assert.deepEqual(
      await manager.loadDesktopSessionState(),
      { version: 1, lastActiveProjectId: 33 },
    );
    passed += 1;
    assert.deepEqual(
      JSON.parse(await fs.readFile(sessionBackupPath, 'utf8')),
      { version: 1, lastActiveProjectId: 32 },
    );
    passed += 1;
    check('rapid session writes leave no temporary generation', (await sessionTemporaryFiles()).length === 0);

    await manager.saveLastActiveProjectId(null);
    assert.deepEqual(
      await manager.loadDesktopSessionState(),
      { version: 1, lastActiveProjectId: null },
    );
    passed += 1;

    await fs.writeFile(sessionPath, '{corrupt session', 'utf8');
    assert.equal(await manager.loadDesktopSessionState(), null);
    passed += 1;
    await fs.writeFile(sessionPath, JSON.stringify({ version: 2, lastActiveProjectId: 33 }), 'utf8');
    assert.equal(await manager.loadDesktopSessionState(), null);
    passed += 1;
    await fs.writeFile(sessionPath, JSON.stringify({ version: 1, lastActiveProjectId: 0 }), 'utf8');
    assert.equal(await manager.loadDesktopSessionState(), null);
    passed += 1;
    await fs.writeFile(sessionPath, 'x'.repeat(4 * 1024 + 1), 'utf8');
    assert.equal(await manager.loadDesktopSessionState(), null);
    passed += 1;

    // A failed atomic install cannot truncate or replace the previous valid
    // generation, and the queue must remain usable by the next write.
    await manager.saveLastActiveProjectId(41);
    const sessionOriginalRename = fs.rename;
    fs.rename = async (source, destination) => {
      if (destination === sessionPath && path.basename(source).endsWith('.tmp')) {
        const error = new Error('injected session rename failure');
        error.code = 'EIO';
        throw error;
      }
      return sessionOriginalRename(source, destination);
    };
    try {
      await rejects(
        'session atomic replacement failure is surfaced',
        () => manager.saveLastActiveProjectId(42),
        /injected session rename failure/,
      );
    } finally {
      fs.rename = sessionOriginalRename;
    }
    assert.deepEqual(
      await manager.loadDesktopSessionState(),
      { version: 1, lastActiveProjectId: 41 },
    );
    passed += 1;
    check('failed session replacement cleans its temporary generation', (await sessionTemporaryFiles()).length === 0);
    await manager.saveLastActiveProjectId(43);
    assert.deepEqual(
      await manager.loadDesktopSessionState(),
      { version: 1, lastActiveProjectId: 43 },
    );
    passed += 1;

    // Exercise the actual Windows replace refusal: the validated predecessor
    // remains at the stable .bak path while temp becomes the new primary.
    let sessionInstallAttempts = 0;
    fs.rename = async (source, destination) => {
      if (destination === sessionPath && path.basename(String(source)).endsWith('.tmp')) {
        sessionInstallAttempts += 1;
        if (sessionInstallAttempts === 1) {
          const error = new Error('injected Windows session replace refusal');
          error.code = 'EPERM';
          throw error;
        }
      }
      return sessionOriginalRename(source, destination);
    };
    try {
      await manager.saveLastActiveProjectId(44);
    } finally {
      fs.rename = sessionOriginalRename;
    }
    check('session replacement exercised the Windows fallback', sessionInstallAttempts === 2);
    assert.deepEqual(
      await manager.loadDesktopSessionState(),
      { version: 1, lastActiveProjectId: 44 },
    );
    assert.deepEqual(
      JSON.parse(await fs.readFile(sessionBackupPath, 'utf8')),
      { version: 1, lastActiveProjectId: 43 },
    );
    passed += 2;
    check('Windows session fallback cleans temporary generations', (await sessionTemporaryFiles()).length === 0);

    // Model a process crash in the Windows move-then-install gap. Primary is
    // absent, while the fixed backup and an orphaned retired generation remain.
    const injectedRetired = path.join(userData, '.session-state.json.injected.retired');
    await fs.rename(sessionPath, injectedRetired);
    assert.deepEqual(
      await manager.loadDesktopSessionState(),
      { version: 1, lastActiveProjectId: 43 },
    );
    passed += 1;
    await fs.rm(injectedRetired, { force: true });
    await manager.saveLastActiveProjectId(45);

    // If fallback installation and restoration both fail, the stable backup is
    // still loadable. The next successful write can proceed from that state.
    sessionInstallAttempts = 0;
    fs.rename = async (source, destination) => {
      const sourceName = path.basename(String(source));
      if (destination === sessionPath && sourceName.endsWith('.tmp')) {
        sessionInstallAttempts += 1;
        const error = new Error(sessionInstallAttempts === 1
          ? 'injected Windows session replace refusal'
          : 'injected session install failure');
        error.code = sessionInstallAttempts === 1 ? 'EPERM' : 'EIO';
        throw error;
      }
      if (destination === sessionPath && sourceName.endsWith('.retired')) {
        const error = new Error('injected session restore failure');
        error.code = 'EACCES';
        throw error;
      }
      return sessionOriginalRename(source, destination);
    };
    try {
      await rejects(
        'failed Windows session install is surfaced',
        () => manager.saveLastActiveProjectId(46),
        /injected session install failure/,
      );
    } finally {
      fs.rename = sessionOriginalRename;
    }
    assert.deepEqual(
      await manager.loadDesktopSessionState(),
      { version: 1, lastActiveProjectId: 45 },
    );
    passed += 1;
    const crashArtifacts = await sessionTemporaryFiles();
    check(
      'failed Windows restore retains one recoverable retired artifact',
      crashArtifacts.length === 1 && crashArtifacts[0].endsWith('.retired'),
    );
    await Promise.all(crashArtifacts.map((entry) => fs.rm(path.join(userData, entry), { force: true })));
    await manager.saveLastActiveProjectId(47);

    // A read and a shutdown drain requested behind a stalled write cannot
    // overtake it or observe the preceding generation.
    let releaseSessionInstall;
    let markSessionInstallReached;
    const sessionInstallGate = new Promise((resolve) => { releaseSessionInstall = resolve; });
    const sessionInstallReached = new Promise((resolve) => { markSessionInstallReached = resolve; });
    fs.rename = async (source, destination) => {
      if (destination === sessionPath && path.basename(String(source)).endsWith('.tmp')) {
        markSessionInstallReached();
        await sessionInstallGate;
      }
      return sessionOriginalRename(source, destination);
    };
    const stalledSave = manager.saveLastActiveProjectId(48);
    try {
      await sessionInstallReached;
      let readSettled = false;
      let drainSettled = false;
      const orderedRead = manager.loadDesktopSessionState().then((value) => {
        readSettled = true;
        return value;
      });
      const pendingDrain = manager.drainDesktopSessionSaves().then(() => { drainSettled = true; });
      await new Promise((resolve) => setImmediate(resolve));
      check('session read waits behind the pending write', !readSettled);
      check('shutdown drain waits behind pending session operations', !drainSettled);
      releaseSessionInstall();
      await stalledSave;
      assert.deepEqual(
        await orderedRead,
        { version: 1, lastActiveProjectId: 48 },
      );
      await pendingDrain;
      passed += 2;
    } finally {
      releaseSessionInstall();
      fs.rename = sessionOriginalRename;
    }
    check('ordered session operations clean temporary generations', (await sessionTemporaryFiles()).length === 0);

    await rejects(
      'invalid session project ids never reach the filesystem',
      () => manager.saveLastActiveProjectId(0),
      /project\s?id/i,
    );
    await rejects(
      'an undefined session project id is not treated as an explicit clear',
      () => manager.saveLastActiveProjectId(undefined),
      /project\s?id/i,
    );

    const first = { version: 1, preset: 'cockpit', regions: { center: ['manuscript'] } };
    await manager.saveLayout(11, first);
    assert.deepEqual(await manager.loadLayout(11), first);
    passed += 1;
    check('ordinary save leaves no temporary generation behind', (await tempFiles()).length === 0);

    // The limit is in encoded bytes, not JavaScript code units. This string is
    // comfortably below 256K characters but above 256 KiB once UTF-8 encoded.
    const multibyteOversize = { text: 'é'.repeat(140_000) };
    check(
      'oversize fixture exceeds the encoded-byte cap',
      JSON.stringify(multibyteOversize).length < MAX_LAYOUT_BYTES
        && Buffer.byteLength(JSON.stringify(multibyteOversize), 'utf8') > MAX_LAYOUT_BYTES,
    );
    await rejects(
      'save rejects a layout above the byte cap',
      () => manager.saveLayout(12, multibyteOversize),
      /256 KiB safety limit/,
    );
    check('oversize rejection creates no destination', !(await fs.stat(layoutPath(12)).then(() => true, () => false)));
    check('oversize rejection creates no temporary generation', (await tempFiles()).length === 0);

    const cyclic = {};
    cyclic.self = cyclic;
    await rejects('save rejects non-JSON data', () => manager.saveLayout(13, cyclic), /circular/i);
    check('serialization rejection creates no temporary generation', (await tempFiles()).length === 0);

    const recovered = { version: 1, preset: 'focus', recovered: true };
    await fs.mkdir(layouts, { recursive: true });
    await fs.writeFile(layoutPath(20), '{damaged current', 'utf8');
    await fs.writeFile(backupPath(20), JSON.stringify(recovered), 'utf8');
    assert.deepEqual(await manager.loadLayout(20), manager.INVALID_STORED_LAYOUT);
    passed += 1;
    assert.deepEqual(await manager.loadLayoutBackup(20), recovered);
    passed += 1;

    const current = { version: 1, source: 'current' };
    const staleBackup = { version: 1, source: 'backup' };
    await fs.writeFile(layoutPath(21), JSON.stringify(current), 'utf8');
    await fs.writeFile(backupPath(21), JSON.stringify(staleBackup), 'utf8');
    assert.deepEqual(await manager.loadLayout(21), current);
    passed += 1;

    await fs.writeFile(layoutPath(22), 'x'.repeat(MAX_LAYOUT_BYTES + 1), 'utf8');
    await fs.writeFile(backupPath(22), JSON.stringify(recovered), 'utf8');
    assert.deepEqual(await manager.loadLayout(22), manager.INVALID_STORED_LAYOUT);
    passed += 1;
    assert.deepEqual(await manager.loadLayoutBackup(22), recovered);
    passed += 1;

    await fs.writeFile(layoutPath(23), '{bad', 'utf8');
    await fs.writeFile(backupPath(23), '{also bad', 'utf8');
    assert.deepEqual(await manager.loadLayout(23), manager.INVALID_STORED_LAYOUT);
    assert.deepEqual(await manager.loadLayoutBackup(23), manager.INVALID_STORED_LAYOUT);
    passed += 2;

    // Every ordinary replacement retains the immediately prior valid
    // generation, including POSIX's successful overwrite path.
    const first29 = { version: 1, generation: 'first' };
    const second29 = { version: 1, generation: 'second' };
    await manager.saveLayout(29, first29);
    await manager.saveLayout(29, second29);
    assert.deepEqual(await manager.loadLayout(29), second29);
    assert.deepEqual(await manager.loadLayoutBackup(29), first29);
    passed += 2;
    check('ordinary replacement leaves no temporary generation', (await tempFiles()).length === 0);

    // A non-replace error must leave the previous generation intact and remove
    // the unique same-directory temporary file.
    const old24 = { version: 1, generation: 'old' };
    const next24 = { version: 1, generation: 'next' };
    await manager.saveLayout(24, old24);
    const originalRename = fs.rename;
    fs.rename = async (source, destination) => {
      if (destination === layoutPath(24) && path.basename(source).endsWith('.tmp')) {
        const error = new Error('injected rename failure');
        error.code = 'EIO';
        throw error;
      }
      return originalRename(source, destination);
    };
    try {
      await rejects('unexpected atomic replacement failure is surfaced', () => manager.saveLayout(24, next24), /injected rename failure/);
    } finally {
      fs.rename = originalRename;
    }
    assert.deepEqual(await manager.loadLayout(24), old24);
    passed += 1;
    check('failed atomic replacement cleans its temporary generation', (await tempFiles()).length === 0);

    // Exercise the Windows-style replace fallback on every platform: current is
    // moved to .bak, then the completed temporary generation becomes current.
    const old25 = { version: 1, generation: 'old' };
    const next25 = { version: 1, generation: 'next' };
    await manager.saveLayout(25, old25);
    let replacementAttempts = 0;
    fs.rename = async (source, destination) => {
      if (destination === layoutPath(25) && path.basename(source).endsWith('.tmp')) {
        replacementAttempts += 1;
        if (replacementAttempts === 1) {
          const error = new Error('injected Windows replace refusal');
          error.code = 'EPERM';
          throw error;
        }
      }
      return originalRename(source, destination);
    };
    try {
      await manager.saveLayout(25, next25);
    } finally {
      fs.rename = originalRename;
    }
    assert.deepEqual(JSON.parse(await fs.readFile(layoutPath(25), 'utf8')), next25);
    assert.deepEqual(JSON.parse(await fs.readFile(backupPath(25), 'utf8')), old25);
    passed += 2;
    check('fallback replacement cleans its temporary generation', (await tempFiles()).length === 0);

    // If installation of the new generation fails after the old one moved to
    // backup, the fallback must restore that backup before surfacing failure.
    const old26 = { version: 1, generation: 'old' };
    const next26 = { version: 1, generation: 'next' };
    await manager.saveLayout(26, old26);
    replacementAttempts = 0;
    fs.rename = async (source, destination) => {
      if (destination === layoutPath(26) && path.basename(source).endsWith('.tmp')) {
        replacementAttempts += 1;
        const error = new Error(replacementAttempts === 1 ? 'replace refused' : 'install failed');
        error.code = replacementAttempts === 1 ? 'EPERM' : 'EIO';
        throw error;
      }
      return originalRename(source, destination);
    };
    try {
      await rejects('failed fallback install is surfaced', () => manager.saveLayout(26, next26), /install failed/);
    } finally {
      fs.rename = originalRename;
    }
    assert.deepEqual(await manager.loadLayout(26), old26);
    passed += 1;
    check('failed fallback restores the previous current generation', await fs.stat(layoutPath(26)).then(() => true, () => false));
    check('failed fallback cleans its temporary generation', (await tempFiles()).length === 0);

    // Recovery writes must not rotate a corrupt primary over the validated
    // backup if installation of the repaired generation fails.
    const good30 = { version: 1, generation: 'known-good-backup' };
    const repaired30 = { version: 1, generation: 'repaired' };
    await fs.writeFile(layoutPath(30), '{corrupt primary', 'utf8');
    await fs.writeFile(backupPath(30), JSON.stringify(good30), 'utf8');
    replacementAttempts = 0;
    fs.rename = async (source, destination) => {
      if (destination === layoutPath(30) && path.basename(source).endsWith('.tmp')) {
        replacementAttempts += 1;
        const error = new Error(replacementAttempts === 1 ? 'replace refused' : 'repair install failed');
        error.code = replacementAttempts === 1 ? 'EPERM' : 'EIO';
        throw error;
      }
      return originalRename(source, destination);
    };
    try {
      await rejects(
        'failed recovery install is surfaced',
        () => manager.saveLayout(30, repaired30, { preserveBackup: true }),
        /repair install failed/,
      );
    } finally {
      fs.rename = originalRename;
    }
    assert.deepEqual(await manager.loadLayoutBackup(30), good30);
    passed += 1;
    check('failed recovery keeps its validated backup', (await tempFiles()).length === 0);

    // Failures before rename must also close the handle and remove the unique
    // temp generation; otherwise repeated disk errors leak files forever.
    const originalOpen = fs.open;
    fs.open = async (...args) => {
      const handle = await originalOpen(...args);
      if (path.basename(String(args[0])).includes('.27.json.')) {
        handle.writeFile = async () => { throw new Error('injected write failure'); };
      }
      return handle;
    };
    try {
      await rejects('temporary write failure is surfaced', () => manager.saveLayout(27, first), /injected write failure/);
    } finally {
      fs.open = originalOpen;
    }
    check('write failure cleans its temporary generation', (await tempFiles()).length === 0);

    fs.open = async (...args) => {
      const handle = await originalOpen(...args);
      if (path.basename(String(args[0])).includes('.28.json.')) {
        handle.sync = async () => { throw new Error('injected sync failure'); };
      }
      return handle;
    };
    try {
      await rejects('temporary sync failure is surfaced', () => manager.saveLayout(28, first), /injected sync failure/);
    } finally {
      fs.open = originalOpen;
    }
    check('sync failure cleans its temporary generation', (await tempFiles()).length === 0);

    await rejects('invalid project ids never reach the filesystem', () => manager.saveLayout(0, first), /project\s?id/i);
  } finally {
    await fs.rm(userData, { recursive: true, force: true });
  }

  console.log(`Layout persistence tests: ${passed} passed, 0 failed`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
