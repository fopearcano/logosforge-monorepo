const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const fsPromises = require('node:fs').promises;
const {
  mkdtemp, mkdir, readFile, readdir, rename, rm, writeFile, copyFile,
} = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');

const {
  CloudSyncManager,
  CLOUD_SYNC_FOLDER_NAME,
  validateCloudSyncSnapshot,
} = require('../dist-electron/cloud-sync-manager.js');

const ids = [
  '00000000-0000-4000-8000-000000000001',
  '00000000-0000-4000-8000-000000000002',
  '00000000-0000-4000-8000-000000000003',
  '00000000-0000-4000-8000-000000000004',
  '00000000-0000-4000-8000-000000000005',
  '00000000-0000-4000-8000-000000000006',
  '00000000-0000-4000-8000-000000000007',
  '00000000-0000-4000-8000-000000000008',
  '00000000-0000-4000-8000-000000000009',
  '00000000-0000-4000-8000-00000000000a',
  '00000000-0000-4000-8000-00000000000b',
  '00000000-0000-4000-8000-00000000000c',
  '00000000-0000-4000-8000-00000000000d',
  '00000000-0000-4000-8000-00000000000e',
  '00000000-0000-4000-8000-00000000000f',
];

function idFactory(offset = 0) {
  let index = offset;
  return () => {
    const value = ids[index];
    index += 1;
    if (!value) throw new Error('test UUID sequence exhausted');
    return value;
  };
}

function sequenceFactory(sequence) {
  let index = 0;
  return () => {
    const value = sequence[index++];
    if (!value) throw new Error('test UUID sequence exhausted');
    return value;
  };
}

function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (!value || typeof value !== 'object') return value;
  return Object.fromEntries(Object.keys(value).sort().map((key) => [key, stable(value[key])]));
}

function projectSnapshot(identity, title, content) {
  const payload = {
    format: 'logosforge-pro-project-snapshot',
    version: '1.0',
    schema_version: 1,
    project_identity: identity,
    project: { title, sync_id: identity },
    tables: {
      project: [{ key: identity, values: { title }, references: {} }],
      scene: [{ key: `${identity}:scene`, values: { content }, references: {} }],
    },
  };
  const digest = createHash('sha256').update(JSON.stringify(stable(payload))).digest('hex');
  return { ...payload, digest };
}

async function rejects(promise, pattern) {
  let error;
  try { await promise; } catch (candidate) { error = candidate; }
  assert.ok(error, 'expected promise rejection');
  assert.match(String(error.message || error), pattern);
}

async function main() {
  const root = await mkdtemp(path.join(os.tmpdir(), 'logosforge-pro-cloud-sync-'));
  const managers = [];
  const userA = path.join(root, 'user-a');
  const userB = path.join(root, 'user-b');
  const userC = path.join(root, 'user-c');
  const userD = path.join(root, 'user-d');
  const userE = path.join(root, 'user-e');
  const userP = path.join(root, 'user-poll');
  const userQ = path.join(root, 'user-quarantine');
  const provider = path.join(root, 'provider');
  await Promise.all([
    mkdir(userA), mkdir(userB), mkdir(userC), mkdir(userD), mkdir(userE), mkdir(userP),
    mkdir(userQ), mkdir(provider),
  ]);
  try {
    const managerA = new CloudSyncManager(userA, { createId: idFactory(0), pollIntervalMs: 60_000 });
    managers.push(managerA);
    await managerA.initialize();
    assert.equal((await managerA.getState()).enabled, false, 'fresh install begins disabled');
    await managerA.setFolder(provider);

    const incarnationA = '10000000-0000-4000-8000-000000000001';
    const firstBundle = projectSnapshot(incarnationA, 'Cloud Test', 'root');
    const rootPublish = await managerA.publish({
      localProjectId: '1', localIncarnation: incarnationA,
      bundle: firstBundle, createNewProject: true,
    });
    assert.equal(rootPublish.created, true);
    assert.equal(rootPublish.delivered, true);
    assert.equal(rootPublish.snapshot.generation, 0);
    assert.deepEqual(rootPublish.snapshot.parentSnapshotIds, []);

    const repeated = await managerA.publish({
      localProjectId: '1', localIncarnation: incarnationA,
      bundle: firstBundle,
    });
    assert.equal(repeated.created, false, 'same content is idempotent');
    assert.equal(repeated.snapshot.snapshotId, rootPublish.snapshot.snapshotId);
    await rejects(managerA.publish({
      localProjectId: '4',
      localIncarnation: '10000000-0000-4000-8000-000000000004',
      bundle: firstBundle,
      createNewProject: true,
    }), /does not match its snapshot sync identity/);

    const managerB = new CloudSyncManager(userB, { createId: idFactory(5), pollIntervalMs: 60_000 });
    managers.push(managerB);
    await managerB.initialize();
    await managerB.setFolder(provider);
    let stateB = await managerB.getState();
    assert.equal(stateB.projects.length, 1, 'second device discovers provider project');
    assert.equal(stateB.projects[0].heads.length, 1);
    await rejects(managerB.setBinding({
      localProjectId: '9',
      localIncarnation: incarnationA,
      cloudProjectId: rootPublish.binding.cloudProjectId,
      lastSnapshotId: rootPublish.snapshot.snapshotId,
      lastContentDigest: '0'.repeat(64),
    }), /digest does not match/);
    await rejects(managerB.setBinding({
      localProjectId: '9',
      localIncarnation: '10000000-0000-4000-8000-000000000009',
      cloudProjectId: rootPublish.binding.cloudProjectId,
      lastSnapshotId: rootPublish.snapshot.snapshotId,
      lastContentDigest: rootPublish.snapshot.contentDigest,
    }), /identity does not match/);

    // A local numeric Core id may differ on another device, but one cloud DAG
    // always carries the same portable project incarnation.
    const incarnationB = incarnationA;
    const foreignIncarnation = '10000000-0000-4000-8000-000000000099';
    await rejects(managerB.publish({
      localProjectId: '99',
      localIncarnation: foreignIncarnation,
      bundle: projectSnapshot(foreignIncarnation, 'Foreign', 'wrong parent'),
      cloudProjectId: rootPublish.binding.cloudProjectId,
      parentSnapshotIds: [rootPublish.snapshot.snapshotId],
    }), /cannot inherit history from another project identity/);
    const remoteChild = await managerB.publish({
      localProjectId: '9', localIncarnation: incarnationB,
      bundle: projectSnapshot(incarnationB, 'Cloud Test', 'remote edit'),
      cloudProjectId: rootPublish.binding.cloudProjectId,
      parentSnapshotIds: [rootPublish.snapshot.snapshotId],
    });
    assert.equal(remoteChild.snapshot.generation, 1);

    const localChild = await managerA.publish({
      localProjectId: '1', localIncarnation: incarnationA,
      bundle: projectSnapshot(incarnationA, 'Cloud Test', 'local edit'),
      cloudProjectId: rootPublish.binding.cloudProjectId,
      parentSnapshotIds: [rootPublish.snapshot.snapshotId],
    });
    const divergent = (await managerA.getState()).projects[0];
    assert.equal(divergent.snapshots.length, 3);
    assert.deepEqual(
      new Set(divergent.heads.map((item) => item.snapshotId)),
      new Set([remoteChild.snapshot.snapshotId, localChild.snapshot.snapshotId]),
      'concurrent children remain two immutable heads',
    );

    const preallocated = '20000000-0000-4000-8000-000000000001';
    const forkBundle = projectSnapshot(incarnationA, 'Fork', 'fork bytes');
    const fork = await managerA.publish({
      localProjectId: '2', localIncarnation: incarnationA,
      bundle: forkBundle, createNewProject: true, newCloudProjectId: preallocated,
    });
    assert.equal(fork.binding.cloudProjectId, preallocated);
    const forkReplay = await managerA.publish({
      localProjectId: '2', localIncarnation: incarnationA,
      bundle: forkBundle, createNewProject: true, newCloudProjectId: preallocated,
    });
    assert.equal(forkReplay.created, false, 'preallocated root recovers idempotently');
    await rejects(managerA.publish({
      localProjectId: '2', localIncarnation: incarnationA,
      bundle: projectSnapshot(incarnationA, 'Fork', 'different bytes'),
      createNewProject: true, newCloudProjectId: preallocated,
    }), /already used by different history/);

    const snapshotDir = path.join(
      provider, CLOUD_SYNC_FOLDER_NAME, 'Projects',
      rootPublish.binding.cloudProjectId, 'snapshots',
    );
    const originalPath = path.join(snapshotDir, `${rootPublish.snapshot.snapshotId}.lfsync`);
    const aliasPath = path.join(snapshotDir, '30000000-0000-4000-8000-000000000001.lfsync');
    await copyFile(originalPath, aliasPath);
    stateB = await managerB.getState();
    assert.ok(
      stateB.warnings.some((warning) => warning.includes('file name')),
      'inventory rejects an envelope hidden under another snapshot basename',
    );
    await rm(aliasPath);

    const maxGenerationId = '30000000-0000-4000-8000-000000000002';
    await writeFile(
      path.join(snapshotDir, `${maxGenerationId}.lfsync`),
      JSON.stringify({
        ...JSON.parse(await readFile(originalPath, 'utf8')),
        snapshotId: maxGenerationId,
        generation: Number.MAX_SAFE_INTEGER,
      }),
      'utf8',
    );
    await rejects(managerA.publish({
      localProjectId: '1',
      localIncarnation: incarnationA,
      bundle: projectSnapshot(incarnationA, 'Cloud Test', 'unsafe generation child'),
      cloudProjectId: rootPublish.binding.cloudProjectId,
      parentSnapshotIds: [maxGenerationId],
    }), /generation exceeds the safe transport limit/);
    await rm(path.join(snapshotDir, `${maxGenerationId}.lfsync`));

    const providerAway = `${provider}-offline`;
    await rename(provider, providerAway);
    const queuedBundle = projectSnapshot(
      '10000000-0000-4000-8000-000000000003',
      'Queued',
      'offline root',
    );
    const queued = await managerA.publish({
      localProjectId: '3',
      localIncarnation: queuedBundle.project.sync_id,
      bundle: queuedBundle,
      createNewProject: true,
    });
    assert.equal(queued.delivered, false);
    assert.equal((await managerA.getState()).pendingDeliveries, 1);
    await rename(providerAway, provider);
    assert.deepEqual(await managerA.retryOutbox(), { delivered: 1, pending: 0 });

    const action = {
      actionId: '60000000-0000-4000-8000-000000000001',
      kind: 'pull',
      phase: 'prepared',
      sourceLocalProjectId: '1',
      sourceLocalIncarnation: incarnationA,
      originalCloudProjectId: rootPublish.binding.cloudProjectId,
      snapshotId: remoteChild.snapshot.snapshotId,
      snapshotContentDigest: remoteChild.snapshot.contentDigest,
      parentSnapshotIds: remoteChild.snapshot.parentSnapshotIds,
      expectedSourceDigest: localChild.snapshot.contentDigest,
    };
    await rejects(
      managerA.saveActionReceipt({ ...action, actionId: 'not-a-uuid' }),
      /must be a UUID/,
    );
    await managerA.saveActionReceipt(action);
    await managerA.saveActionReceipt({
      ...action,
      phase: 'restored',
      restoredLocalProjectId: '77',
      restoredLocalIncarnation: '10000000-0000-4000-8000-000000000077',
    });
    await rejects(managerA.saveActionReceipt(action), /cannot move backwards/);
    assert.equal(await managerA.completeActionReceipt(action.actionId), true);
    assert.equal(await managerA.completeActionReceipt(action.actionId), false);

    await managerA.recordRecoveredRemoteHeads(rootPublish.binding.cloudProjectId, [
      remoteChild.snapshot.snapshotId,
      localChild.snapshot.snapshotId,
    ]);
    assert.equal(await managerA.removeRecoveredRemoteHead(
      rootPublish.binding.cloudProjectId,
      remoteChild.snapshot.snapshotId,
    ), true);
    let recovered = (await managerA.getState()).recoveredRemoteHeads;
    assert.deepEqual(recovered, [{
      cloudProjectId: rootPublish.binding.cloudProjectId,
      snapshotIds: [localChild.snapshot.snapshotId],
    }], 'removing one recovered head preserves its siblings atomically');
    assert.equal(await managerA.removeRecoveredRemoteHead(
      rootPublish.binding.cloudProjectId,
      remoteChild.snapshot.snapshotId,
    ), false, 'removing an already absent recovered head is idempotent');
    assert.equal(await managerA.removeRecoveredRemoteHead(
      rootPublish.binding.cloudProjectId,
      localChild.snapshot.snapshotId,
    ), true);
    recovered = (await managerA.getState()).recoveredRemoteHeads;
    assert.deepEqual(recovered, [], 'removing the final head removes the empty ledger row');

    const managerC = new CloudSyncManager(userC, {
      createId: sequenceFactory([
        '40000000-0000-4000-8000-000000000001',
        remoteChild.snapshot.snapshotId,
      ]),
      pollIntervalMs: 60_000,
    });
    managers.push(managerC);
    await managerC.initialize();
    await managerC.setFolder(provider);
    const collision = await managerC.publish({
      localProjectId: '88',
      localIncarnation: incarnationA,
      bundle: projectSnapshot(
        incarnationA,
        'Collision',
        'different immutable bytes',
      ),
      cloudProjectId: rootPublish.binding.cloudProjectId,
      parentSnapshotIds: [rootPublish.snapshot.snapshotId],
    });
    assert.equal(collision.delivered, false, 'same snapshot UUID with different bytes stays queued');
    assert.match((await managerC.getState()).lastError, /same immutable id/);

    // Simulate another process winning the immutable destination name after
    // this manager's existence check but before its no-clobber hard link.
    const managerD = new CloudSyncManager(userD, {
      createId: sequenceFactory([
        '70000000-0000-4000-8000-000000000001',
        '70000000-0000-4000-8000-000000000002',
        '70000000-0000-4000-8000-000000000003',
      ]),
      pollIntervalMs: 60_000,
    });
    managers.push(managerD);
    await managerD.initialize();
    await managerD.setFolder(provider);
    const originalLink = fsPromises.link;
    let racedDestination = null;
    fsPromises.link = async (source, destination) => {
      const attempted = JSON.parse(await readFile(source, 'utf8'));
      const winnerBundle = projectSnapshot(
        '70000000-0000-4000-8000-000000000004',
        'Concurrent winner',
        'won immutable name',
      );
      const winner = {
        ...attempted,
        contentDigest: winnerBundle.digest,
        bundle: winnerBundle,
      };
      racedDestination = destination;
      await writeFile(destination, JSON.stringify(winner), 'utf8');
      return originalLink(source, destination);
    };
    let raced;
    try {
      raced = await managerD.publish({
        localProjectId: '101',
        localIncarnation: '70000000-0000-4000-8000-000000000004',
        bundle: projectSnapshot(
          '70000000-0000-4000-8000-000000000004',
          'Race loser',
          'must not overwrite',
        ),
        createNewProject: true,
      });
    } finally {
      fsPromises.link = originalLink;
    }
    assert.equal(raced.delivered, false, 'a concurrent differing winner remains untouched');
    assert.ok(racedDestination, 'test intercepted the immutable link commit');
    const winnerBytes = JSON.parse(await readFile(racedDestination, 'utf8'));
    assert.equal(winnerBytes.bundle.project.title, 'Concurrent winner');
    assert.match((await managerD.getState()).lastError, /same immutable id/);

    // Recreate the durable state after a process stopped between its atomic
    // outbox write and binding-config commit. A retry must adopt this exact
    // pending root instead of allocating a duplicate cloud history.
    const orphanIdentity = '80000000-0000-4000-8000-000000000004';
    const orphanCloudProjectId = '80000000-0000-4000-8000-000000000001';
    const orphanSnapshotId = '80000000-0000-4000-8000-000000000002';
    const orphanDeviceId = '80000000-0000-4000-8000-000000000003';
    const managerE = new CloudSyncManager(userE, {
      createId: sequenceFactory([orphanDeviceId]),
      pollIntervalMs: 60_000,
    });
    managers.push(managerE);
    await managerE.initialize();
    await managerE.setFolder(provider);
    const orphanBundle = projectSnapshot(orphanIdentity, 'Recovered publish', 'durable outbox');
    const orphanEnvelope = {
      format: 'logosforge-pro-cloud-snapshot',
      version: '1.0',
      cloudProjectId: orphanCloudProjectId,
      snapshotId: orphanSnapshotId,
      deviceId: orphanDeviceId,
      parentSnapshotIds: [],
      generation: 0,
      createdAt: '2026-11-18T12:00:00.000Z',
      contentDigest: orphanBundle.digest,
      bundle: orphanBundle,
    };
    const orphanDirectory = path.join(
      userE,
      'cloud-sync-outbox',
      'Projects',
      orphanCloudProjectId,
      'snapshots',
    );
    await mkdir(orphanDirectory, { recursive: true });
    await writeFile(
      path.join(orphanDirectory, `${orphanSnapshotId}.lfsync`),
      JSON.stringify(orphanEnvelope),
      'utf8',
    );
    const adopted = await managerE.publish({
      localProjectId: '202',
      localIncarnation: orphanIdentity,
      bundle: orphanBundle,
      createNewProject: true,
    });
    assert.equal(adopted.created, false, 'publish retry adopts its durable orphan');
    assert.equal(adopted.delivered, true);
    assert.equal(adopted.binding.cloudProjectId, orphanCloudProjectId);
    assert.equal(adopted.snapshot.snapshotId, orphanSnapshotId);
    assert.equal((await managerE.getState()).pendingDeliveries, 0);

    const managerP = new CloudSyncManager(userP, {
      createId: sequenceFactory(['90000000-0000-4000-8000-000000000001']),
      pollIntervalMs: 60_000,
    });
    managers.push(managerP);
    await managerP.initialize();
    await managerP.setFolder(provider);
    let pollChanges = 0;
    managerP.onChanged(() => { pollChanges += 1; });
    await managerP.poll();
    assert.equal(pollChanges, 1, 'first provider poll publishes its inventory fingerprint');
    await managerP.poll();
    assert.equal(pollChanges, 1, 'an unchanged provider poll emits no redundant event');

    const restarted = new CloudSyncManager(userA, { createId: idFactory(12), pollIntervalMs: 60_000 });
    managers.push(restarted);
    await restarted.initialize();
    const restartedState = await restarted.getState();
    assert.equal(restartedState.deviceId, (await managerA.getState()).deviceId);
    assert.ok(restartedState.bindings.some((item) => item.localProjectId === '1'));

    // Provider files are immutable and canonical rather than pretty-printed.
    const bytes = await readFile(originalPath, 'utf8');
    const parsed = JSON.parse(bytes);
    assert.equal(parsed.snapshotId, rootPublish.snapshot.snapshotId);
    assert.equal(bytes.includes('\n'), false, 'provider snapshot is canonical compact JSON');
    assert.throws(
      () => validateCloudSyncSnapshot({ ...parsed, contentDigest: '0'.repeat(64) }),
      /does not match its project data/,
      'envelope digest tampering is rejected',
    );
    assert.throws(
      () => validateCloudSyncSnapshot({
        ...parsed,
        bundle: { ...parsed.bundle, digest: 'not-a-digest' },
      }),
      /must be a SHA-256 digest/,
      'malformed embedded Core digest is rejected',
    );

    await writeFile(path.join(userQ, 'cloud-sync-config.json'), '{broken-json', 'utf8');
    const quarantineManager = new CloudSyncManager(userQ, {
      createId: sequenceFactory([
        '50000000-0000-4000-8000-000000000001',
        '50000000-0000-4000-8000-000000000002',
      ]),
    });
    managers.push(quarantineManager);
    await quarantineManager.initialize();
    assert.match((await quarantineManager.getState()).lastError, /preserved in quarantine/);
    assert.ok(
      (await readdir(userQ)).some((name) => name.startsWith('cloud-sync-config.json.invalid-')),
      'corrupt durable config is quarantined rather than overwritten in place',
    );
  } finally {
    await Promise.allSettled(managers.map((manager) => manager.stop()));
    // The target is an isolated mkdtemp child created by this test.
    await rm(root, { recursive: true, force: true });
  }
}

main().then(
  () => console.log('cloud-sync-manager tests passed'),
  (error) => { console.error(error); process.exitCode = 1; },
);
