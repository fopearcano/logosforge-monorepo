import { randomUUID } from 'node:crypto';
import { promises as fs } from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';

import {
  CLOUD_SYNC_FOLDER_NAME,
  CloudSyncManager,
  canonicalCloudSyncBundle,
  cloudSyncContentDigest,
} from '../electron/cloud-sync-manager';

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: boolean): void => {
  if (condition) passed += 1;
  else failures.push(label);
};

function bundle(id: string, exportedAt: string, text: string) {
  return {
    format: 'logosforge-project-bundle',
    version: '1.0',
    exportedAt,
    source: { app: 'logosforge-whiteboard' },
    project: {
      id,
      title: 'Cloud Novel',
      mode: 'novel',
      settings: {},
      manuscript: { blocks: [{ type: 'body', text }] },
      outline: [],
      comments: [],
      drafter: { pages: [] },
      psyke: { elements: [], relations: [], progressions: [] },
      progression_tracks: [],
    },
  };
}

const equivalentA = bundle('1', '2026-01-01T00:00:00.000Z', 'same text');
const equivalentB = bundle('999', '2030-02-02T00:00:00.000Z', 'same text');
check(
  'canonical content excludes device-local project id and export clock',
  canonicalCloudSyncBundle(equivalentA) === canonicalCloudSyncBundle(equivalentB),
);
check(
  'canonical digest converges for the same project on different devices',
  cloudSyncContentDigest(equivalentA) === cloudSyncContentDigest(equivalentB),
);
check(
  'canonical digest changes with manuscript content',
  cloudSyncContentDigest(equivalentA) !== cloudSyncContentDigest(bundle('1', '2026-01-01T00:00:00.000Z', 'changed')),
);

const coreOwnedA = bundle('1', '2026-01-01T00:00:00.000Z', 'same text');
coreOwnedA.project.psyke.elements = [
  { id: '41', name: 'Ada', entry_type: 'character', aliases: [], description: '', notes: '', created_at: '2026-01-01', updated_at: '2026-01-02' },
  { id: '77', name: 'Bex', entry_type: 'character', aliases: [], description: '', notes: '', created_at: '2026-01-01', updated_at: '2026-01-02' },
];
coreOwnedA.project.psyke.relations = [
  { id: '41:77', source_id: 41, target_id: 77, source: 'Ada', target: 'Bex', relation_type: 'trusts' },
];
coreOwnedA.project.psyke.progressions = [
  { id: 900, entry_id: 41, text: 'Learns the truth', scene_id: null, scene_title: '', sort_order: 0 },
];
coreOwnedA.project.progression_tracks = [{
  id: 301,
  kind: 'character',
  title: 'Ada arc',
  description: '',
  color_label: '',
  sort_order: 0,
  legacy_compatibility: false,
  primary_psyke_entry_id: 41,
  primary_psyke_entry_name: 'Ada',
  primary_psyke_entry_type: 'character',
  secondary_psyke_entry_id: null,
  secondary_psyke_entry_name: '',
  secondary_psyke_entry_type: '',
  beats: [{
    id: 700,
    track_id: 301,
    text: 'Learns the truth',
    sort_order: 0,
    anchor_kind: 'unanchored',
    scene_id: null,
    scene_title: '',
    anchor_ref: null,
    anchor_label: '',
  }],
}];
const coreOwnedB = structuredClone(coreOwnedA);
coreOwnedB.project.id = '92';
coreOwnedB.exportedAt = '2031-01-01T00:00:00.000Z';
coreOwnedB.project.psyke.elements[0].id = '501';
coreOwnedB.project.psyke.elements[0].created_at = '2031-01-01';
coreOwnedB.project.psyke.elements[0].updated_at = '2031-01-01';
coreOwnedB.project.psyke.elements[1].id = '502';
coreOwnedB.project.psyke.elements[1].created_at = '2031-01-01';
coreOwnedB.project.psyke.elements[1].updated_at = '2031-01-01';
coreOwnedB.project.psyke.relations[0].id = '501:502';
coreOwnedB.project.psyke.relations[0].source_id = 501;
coreOwnedB.project.psyke.relations[0].target_id = 502;
coreOwnedB.project.psyke.progressions[0].id = 990;
coreOwnedB.project.psyke.progressions[0].entry_id = 501;
coreOwnedB.project.progression_tracks[0].id = 801;
coreOwnedB.project.progression_tracks[0].primary_psyke_entry_id = 501;
coreOwnedB.project.progression_tracks[0].beats[0].id = 880;
coreOwnedB.project.progression_tracks[0].beats[0].track_id = 801;
check(
  'canonical digest converges after core-owned ids and timestamps are remapped',
  cloudSyncContentDigest(coreOwnedA) === cloudSyncContentDigest(coreOwnedB),
);

const root = await fs.mkdtemp(path.join(os.tmpdir(), 'lf-cloud-sync-'));
const userA = path.join(root, 'user-a');
const userB = path.join(root, 'user-b');
const providerFolder = path.join(root, 'provider');
await fs.mkdir(providerFolder, { recursive: true });

const managerA = new CloudSyncManager(userA, { pollIntervalMs: 60_000, createId: randomUUID });
const managerB = new CloudSyncManager(userB, { pollIntervalMs: 60_000, createId: randomUUID });

try {
  await managerA.initialize();
  const initialA = await managerA.getState();
  check('new installation begins disabled', !initialA.enabled && initialA.folderPath === null);
  await managerA.setFolder(providerFolder);
  check(
    'selected provider receives only the fixed Whiteboard projects subtree',
    (await fs.lstat(path.join(providerFolder, CLOUD_SYNC_FOLDER_NAME, 'Projects'))).isDirectory(),
  );

  const rootPublish = await managerA.publish({
    localDocumentId: '1',
    localIncarnation: 'inc-a',
    bundle: equivalentA,
  });
  check('first publish creates and delivers an immutable snapshot', rootPublish.created && rootPublish.delivered);
  check('first snapshot is a root generation', rootPublish.snapshot.generation === 0
    && rootPublish.snapshot.parentSnapshotIds.length === 0);

  const idempotent = await managerA.publish({
    localDocumentId: '1',
    localIncarnation: 'inc-a',
    bundle: equivalentB,
  });
  check('same content and binding is idempotent', !idempotent.created
    && idempotent.snapshot.snapshotId === rootPublish.snapshot.snapshotId);

  let stateA = await managerA.getState();
  check('inventory exposes the complete one-node graph', stateA.projects[0]?.snapshots.length === 1
    && stateA.projects[0]?.heads.length === 1);
  const readRoot = await managerA.readSnapshot({
    cloudProjectId: rootPublish.binding.cloudProjectId,
    snapshotId: rootPublish.snapshot.snapshotId,
  });
  check('snapshot payload is read on demand', cloudSyncContentDigest(readRoot.bundle) === rootPublish.snapshot.contentDigest);

  await managerB.initialize();
  await managerB.setFolder(providerFolder);
  const discovered = await managerB.getState();
  check('second device discovers the remote project without a local binding', discovered.projects.length === 1
    && discovered.bindings.length === 0);
  await managerB.setBinding({
    localDocumentId: '81',
    localIncarnation: 'inc-b',
    cloudProjectId: rootPublish.binding.cloudProjectId,
    lastSnapshotId: rootPublish.snapshot.snapshotId,
    lastContentDigest: rootPublish.snapshot.contentDigest,
  });
  const remoteChild = await managerB.publish({
    localDocumentId: '81',
    localIncarnation: 'inc-b',
    bundle: bundle('81', '2026-01-02T00:00:00.000Z', 'remote edit'),
  });
  check('second-device update is a child of its baseline', remoteChild.snapshot.generation === 1
    && remoteChild.snapshot.parentSnapshotIds[0] === rootPublish.snapshot.snapshotId);

  const localChild = await managerA.publish({
    localDocumentId: '1',
    localIncarnation: 'inc-a',
    bundle: bundle('1', '2026-01-03T00:00:00.000Z', 'local edit'),
  });
  stateA = await managerA.getState();
  const originalProject = stateA.projects.find((project) => project.cloudProjectId === rootPublish.binding.cloudProjectId);
  check('concurrent edits are preserved as two graph heads', originalProject?.snapshots.length === 3
    && originalProject.heads.length === 2);
  check('inventory exposes parent metadata for descendant classification', originalProject?.snapshots.some((row) => (
    row.snapshotId === remoteChild.snapshot.snapshotId
    && row.parentSnapshotIds[0] === rootPublish.snapshot.snapshotId
  )) === true);

  const merge = await managerA.publish({
    localDocumentId: '1',
    localIncarnation: 'inc-a',
    bundle: bundle('1', '2026-01-04T00:00:00.000Z', 'resolved edit'),
    parentSnapshotIds: [localChild.snapshot.snapshotId, remoteChild.snapshot.snapshotId],
  });
  stateA = await managerA.getState();
  const resolvedProject = stateA.projects.find((project) => project.cloudProjectId === rootPublish.binding.cloudProjectId);
  check('multi-parent resolution collapses divergent heads without deleting history', merge.snapshot.generation === 2
    && resolvedProject?.snapshots.length === 4 && resolvedProject.heads.length === 1);

  const forkProjectId = randomUUID();
  const keepBothRequest = {
    localDocumentId: '1',
    localIncarnation: 'inc-a',
    bundle: bundle('1', '2026-01-05T00:00:00.000Z', 'local branch kept separately'),
    createNewProject: true,
    newCloudProjectId: forkProjectId,
  } as const;
  const keepBoth = await managerA.publish(keepBothRequest);
  const keepBothReplay = await managerA.publish(keepBothRequest);
  stateA = await managerA.getState();
  check('Keep both can move a bound local document to a preallocated fresh cloud project', keepBoth.binding.cloudProjectId === forkProjectId
    && keepBoth.snapshot.generation === 0 && stateA.projects.length === 2);
  check('preallocated fork publish is idempotent after a crash-window replay', !keepBothReplay.created
    && keepBothReplay.binding.cloudProjectId === forkProjectId
    && keepBothReplay.snapshot.snapshotId === keepBoth.snapshot.snapshotId);
  let reusedForkRejected = false;
  try {
    await managerA.publish({
      ...keepBothRequest,
      bundle: bundle('1', '2026-01-05T01:00:00.000Z', 'different fork content'),
    });
  } catch {
    reusedForkRejected = true;
  }
  check('preallocated fork id cannot be replayed with different project bytes', reusedForkRejected);
  check('Keep both leaves original cloud history intact', stateA.projects.some((project) => (
    project.cloudProjectId === rootPublish.binding.cloudProjectId && project.snapshots.length === 4
  )));

  const actionId = 'keep-both:test-action';
  const actionBase = {
    actionId,
    kind: 'keep-both' as const,
    sourceLocalDocumentId: '1',
    sourceLocalIncarnation: 'inc-a',
    originalCloudProjectId: rootPublish.binding.cloudProjectId,
    intendedCloudProjectId: forkProjectId,
    snapshotId: remoteChild.snapshot.snapshotId,
    snapshotContentDigest: remoteChild.snapshot.contentDigest,
    parentSnapshotIds: [localChild.snapshot.snapshotId, remoteChild.snapshot.snapshotId],
    expectedSourceDigest: keepBoth.snapshot.contentDigest,
  };
  const preparedAction = await managerA.saveActionReceipt({ ...actionBase, phase: 'prepared' });
  const forkedAction = await managerA.saveActionReceipt({ ...actionBase, phase: 'local-forked' });
  check('durable action receipt updates monotonically without changing caller action id',
    preparedAction.actionId === actionId && forkedAction.phase === 'local-forked');
  let actionRegressionRejected = false;
  try {
    await managerA.saveActionReceipt({ ...actionBase, phase: 'prepared' });
  } catch {
    actionRegressionRejected = true;
  }
  check('durable action receipt rejects phase regression', actionRegressionRejected);
  let actionIdentityChangeRejected = false;
  try {
    await managerA.saveActionReceipt({
      ...actionBase,
      phase: 'local-forked',
      expectedSourceDigest: rootPublish.snapshot.contentDigest,
    });
  } catch {
    actionIdentityChangeRejected = true;
  }
  check('durable action receipt rejects immutable identity changes', actionIdentityChangeRejected);

  await managerA.recordRecoveredRemoteHeads(
    rootPublish.binding.cloudProjectId,
    [localChild.snapshot.snapshotId],
  );
  const recoveredHeads = await managerA.recordRecoveredRemoteHeads(
    rootPublish.binding.cloudProjectId,
    [remoteChild.snapshot.snapshotId],
  );
  check('recovered remote head ledger unions independently preserved branches',
    recoveredHeads.snapshotIds.length === 2
      && recoveredHeads.snapshotIds.includes(localChild.snapshot.snapshotId)
      && recoveredHeads.snapshotIds.includes(remoteChild.snapshot.snapshotId));

  await managerA.moveBinding({
    fromLocalDocumentId: '1',
    fromLocalIncarnation: 'inc-a',
    toLocalDocumentId: '101',
    toLocalIncarnation: 'inc-restored',
    expectedRetiredContentDigest: keepBoth.snapshot.contentDigest,
  });
  stateA = await managerA.getState();
  check('copy-on-write binding move durably retires the superseded local identity', stateA.retiredLocalDocuments
    .some((identity) => identity.localDocumentId === '1'
      && identity.localIncarnation === 'inc-a'
      && identity.expectedContentDigest === keepBoth.snapshot.contentDigest));

  const deviceId = stateA.deviceId;
  await managerA.stop();
  const configPath = path.join(userA, 'cloud-sync-config.json');
  const legacyConfig = JSON.parse(await fs.readFile(configPath, 'utf8')) as {
    retiredLocalDocuments: Array<Record<string, unknown>>;
  };
  legacyConfig.retiredLocalDocuments.push({
    localDocumentId: 'legacy-doc',
    localIncarnation: 'legacy-incarnation',
  });
  await fs.writeFile(configPath, `${JSON.stringify(legacyConfig, null, 2)}\n`, 'utf8');
  const restartedA = new CloudSyncManager(userA, { pollIntervalMs: 60_000, createId: randomUUID });
  await restartedA.initialize();
  const restartedState = await restartedA.getState();
  check('configuration, device identity, and bindings survive restart', restartedState.deviceId === deviceId
    && restartedState.bindings[0]?.cloudProjectId === keepBoth.binding.cloudProjectId);
  check('retired local identity survives restart until deletion is confirmed', restartedState.retiredLocalDocuments
    .some((identity) => identity.localDocumentId === '1' && identity.localIncarnation === 'inc-a'));
  check('legacy retirement tombstone survives restart as unsafe instead of being discarded', restartedState.retiredLocalDocuments
    .some((identity) => identity.localDocumentId === 'legacy-doc'
      && identity.localIncarnation === 'legacy-incarnation'
      && identity.expectedContentDigest === null));
  check('pending action receipt survives restart for deterministic reconciliation', restartedState.actionReceipts
    .some((receipt) => receipt.actionId === actionId && receipt.phase === 'local-forked'));
  check('recovered remote head ledger survives restart independently of ignore state',
    restartedState.recoveredRemoteHeads.some((entry) => (
      entry.cloudProjectId === rootPublish.binding.cloudProjectId
      && entry.snapshotIds.length === 2
    )));
  check('completing an action receipt is idempotent',
    await restartedA.completeActionReceipt(actionId)
      && !(await restartedA.completeActionReceipt(actionId)));
  check('clearing a recovered remote project ledger is idempotent',
    await restartedA.clearRecoveredRemoteHeads(rootPublish.binding.cloudProjectId)
      && !(await restartedA.clearRecoveredRemoteHeads(rootPublish.binding.cloudProjectId)));
  let retiredPublishRejected = false;
  try {
    await restartedA.publish({
      localDocumentId: '1',
      localIncarnation: 'inc-a',
      bundle: bundle('1', '2026-01-05T01:00:00.000Z', 'must not reseed'),
      createNewProject: true,
    });
  } catch {
    retiredPublishRejected = true;
  }
  check('retired local identity cannot be accidentally reseeded', retiredPublishRejected);
  check('confirmed deletion clears a retirement tombstone', await restartedA.forgetBinding({
    localDocumentId: '1',
    localIncarnation: 'inc-a',
    ignoreRemote: false,
  }));

  const unavailableProvider = path.join(root, 'temporarily-offline');
  await fs.mkdir(unavailableProvider);
  await restartedA.setFolder(unavailableProvider);
  await fs.rm(unavailableProvider, { recursive: true, force: true });
  const queued = await restartedA.publish({
    localDocumentId: '2',
    localIncarnation: 'inc-offline',
    bundle: bundle('2', '2026-01-06T00:00:00.000Z', 'offline edit'),
  });
  check('provider outage leaves a durable pending snapshot', !queued.delivered && queued.snapshot.pendingDelivery);
  check('pending outbox is visible while provider folder is absent', (await restartedA.getState()).pendingDeliveries === 1);
  await fs.mkdir(unavailableProvider);
  const retry = await restartedA.retryOutbox();
  check('outbox retries after provider folder returns', retry.delivered === 1 && retry.pending === 0);

  const forgottenCloudId = queued.binding.cloudProjectId;
  check('local binding can be forgotten', await restartedA.forgetBinding({
    localDocumentId: '2',
    localIncarnation: 'inc-offline',
    cloudProjectId: forgottenCloudId,
    ignoreRemote: true,
  }));
  check('deleted local project can ignore its retained remote backup', (await restartedA.getState())
    .ignoredCloudProjectIds.includes(forgottenCloudId));

  const badPath = path.join(
    unavailableProvider,
    CLOUD_SYNC_FOLDER_NAME,
    'Projects',
    forgottenCloudId,
    'snapshots',
    'malformed.lfsync',
  );
  await fs.writeFile(badPath, '{bad json', 'utf8');
  check('malformed provider files are isolated as warnings', (await restartedA.getState()).warnings
    .some((warning) => warning.includes('ignored')));

  await restartedA.stop();
  await managerB.stop();
  const configBPath = path.join(userB, 'cloud-sync-config.json');
  const preLedgerConfig = JSON.parse(await fs.readFile(configBPath, 'utf8')) as Record<string, unknown>;
  delete preLedgerConfig.recoveredRemoteHeads;
  await fs.writeFile(configBPath, `${JSON.stringify(preLedgerConfig, null, 2)}\n`, 'utf8');
  const upgradedB = new CloudSyncManager(userB, { pollIntervalMs: 60_000, createId: randomUUID });
  await upgradedB.initialize();
  check('pre-ledger version-one configuration upgrades in place with an empty recovered-head set',
    (await upgradedB.getState()).recoveredRemoteHeads.length === 0);
  await upgradedB.stop();
  await managerA.stop();
} finally {
  await fs.rm(root, { recursive: true, force: true });
}

console.log(`Cloud sync manager tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} cloud-sync manager test(s) failed`);
console.log('CLOUD SYNC MANAGER TESTS: PASS');
