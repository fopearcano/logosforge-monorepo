import {
  cloudSnapshotDescendsFrom,
  decideCloudSync,
  deterministicCloudRecoveryUuid,
  newestCloudHead,
  planCloudPreservation,
  planRemoteRecovery,
  staleRestoreSuccessorActionId,
  type CloudDocumentBinding,
  type CloudProjectInventory,
  type CloudSnapshotMetadata,
} from './cloudSyncModel';

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: boolean) => (
  condition ? (passed += 1) : failures.push(label)
);

const snapshot = (
  snapshotId: string,
  digest: string,
  generation: number,
  parentSnapshotIds: string[] = [],
  deviceId = 'device-a',
): CloudSnapshotMetadata => ({
  snapshotId,
  digest,
  generation,
  parentSnapshotIds,
  deviceId,
  createdAt: `2026-01-01T00:00:0${generation}.000Z`,
  title: 'Novel',
});

const a = snapshot('a', 'digest-a', 0);
const b = snapshot('b', 'digest-b', 1, ['a'], 'device-b');
const c = snapshot('c', 'digest-c', 2, ['b'], 'device-b');
const binding: CloudDocumentBinding = {
  localDocumentId: '1',
  localIncarnation: 'incarnation',
  cloudProjectId: 'project',
  lastSnapshotId: 'a',
  lastDigest: 'digest-a',
};
const inventory = (snapshots: CloudSnapshotMetadata[], headSnapshotIds: string[]): CloudProjectInventory => ({
  cloudProjectId: 'project',
  snapshots,
  headSnapshotIds,
});

check('unbound project seeds cloud history', decideCloudSync(null, 'digest-a', null).kind === 'seed');
check(
  'missing bound history waits rather than manufacturing a new root',
  decideCloudSync(binding, 'digest-a', null).kind === 'wait',
);
check(
  'unchanged local and remote is a no-op',
  decideCloudSync(binding, 'digest-a', inventory([a], ['a'])).kind === 'noop',
);
check(
  'local edit uploads from the current head',
  decideCloudSync(binding, 'digest-local', inventory([a], ['a'])).kind === 'upload',
);
check(
  'unchanged local fast-forwards by pulling a descendant',
  decideCloudSync(binding, 'digest-a', inventory([a, b], ['b'])).kind === 'pull',
);
check(
  'equal canonical content advances without restoring',
  decideCloudSync(binding, 'digest-b', inventory([a, b], ['b'])).kind === 'advance',
);
check(
  'concurrent local and remote edits conflict',
  decideCloudSync(binding, 'digest-local', inventory([a, b], ['b'])).kind === 'conflict',
);
check(
  'unrelated remote history conflicts',
  decideCloudSync(binding, 'digest-a', inventory([snapshot('x', 'digest-x', 0)], ['x'])).kind === 'conflict',
);
check(
  'different multiple heads conflict',
  decideCloudSync(binding, 'digest-a', inventory([a, b, snapshot('d', 'digest-d', 1, ['a'])], ['b', 'd'])).kind === 'conflict',
);
const bTwin = snapshot('b-twin', 'digest-b', 1, ['a'], 'device-c');
check(
  'identical multiple heads can be merged without data loss',
  decideCloudSync(binding, 'digest-b', inventory([a, b, bTwin], ['b', 'b-twin'])).kind === 'merge-identical',
);
check('DAG ancestry traverses more than one parent generation', cloudSnapshotDescendsFrom(inventory([a, b, c], ['c']), 'c', 'a'));
check('DAG ancestry rejects unrelated snapshots', !cloudSnapshotDescendsFrom(inventory([a, b, c], ['c']), 'a', 'c'));
check('newest head is deterministic', newestCloudHead([a, c, b])?.snapshotId === 'c');

const divergent = snapshot('d', 'digest-d', 1, ['a'], 'device-d');
const recoveryInventory = inventory([a, b, divergent], ['b', 'd']);
const partialRecovery = planRemoteRecovery(recoveryInventory, [
  { snapshotId: 'b', phase: 'binding-installed' },
]);
check(
  'remote recovery plans every current unrecorded head',
  partialRecovery.missingHeadIds.length === 1 && partialRecovery.missingHeadIds[0] === 'd',
);
check('remote history is not ignored while a head is missing', !partialRecovery.readyToIgnoreOriginal);
check(
  'remote history is not ignored while a planned head is unfinished',
  !planRemoteRecovery(recoveryInventory, [
    { snapshotId: 'b', phase: 'binding-installed' },
    { snapshotId: 'd', phase: 'restored' },
  ]).readyToIgnoreOriginal,
);
check(
  'remote history is ignored only after every current head is forked',
  planRemoteRecovery(recoveryInventory, [
    { snapshotId: 'b', phase: 'binding-installed' },
    { snapshotId: 'd', phase: 'binding-installed' },
  ]).readyToIgnoreOriginal,
);
check(
  'durable recovered-head ledger satisfies already imported heads',
  planRemoteRecovery(
    recoveryInventory,
    [{ snapshotId: 'b', phase: 'binding-installed' }],
    ['d'],
  ).readyToIgnoreOriginal,
);
const arriving = snapshot('e', 'digest-e', 2, ['b'], 'device-e');
const changedInventory = inventory([a, b, divergent, arriving], ['d', 'e']);
const changedPlan = planRemoteRecovery(changedInventory, [
  { snapshotId: 'b', phase: 'binding-installed' },
  { snapshotId: 'd', phase: 'binding-installed' },
]);
check(
  'a branch arriving mid-recovery blocks ignore and is added to the plan',
  !changedPlan.readyToIgnoreOriginal
    && changedPlan.missingHeadIds.length === 1
    && changedPlan.missingHeadIds[0] === 'e',
);
const ledgerPlan = planRemoteRecovery(changedInventory, [], ['b', 'd']);
check(
  'ignored recovered history reopens only for an unseen current head',
  !ledgerPlan.readyToIgnoreOriginal
    && ledgerPlan.missingHeadIds.length === 1
    && ledgerPlan.missingHeadIds[0] === 'e',
);

const retrySeed = 'stale:action:document:incarnation';
const retryUuid = await deterministicCloudRecoveryUuid(retrySeed);
check(
  'stale restore preservation UUID is deterministic and validator-compatible',
  retryUuid === await deterministicCloudRecoveryUuid(retrySeed)
    && /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(retryUuid),
);
check(
  'stale restore successor action id is deterministic',
  staleRestoreSuccessorActionId('action-1') === 'retry:action-1',
);
const manyHeads = Array.from({ length: 40 }, (_, index) => (
  snapshot(`wide-${String(index).padStart(2, '0')}`, `digest-wide-${index}`, 1, ['a'], `device-${index}`)
));
const widePlan = planRemoteRecovery(
  inventory([a, ...manyHeads], manyHeads.map((head) => head.snapshotId)),
  [],
);
check(
  'remote recovery planning is not capped by the 32-parent merge limit',
  widePlan.currentHeadIds.length === 40 && widePlan.missingHeadIds.length === 40,
);
check(
  'edited restore reuses a single matching durable head',
  planCloudPreservation(inventory([a], ['a']), 'digest-a').kind === 'reuse',
);
const changedPreservation = planCloudPreservation(inventory([a], ['a']), 'digest-edited');
check(
  'edited restore extends an existing deterministic root with current bytes',
  changedPreservation.kind === 'publish'
    && changedPreservation.parentSnapshotIds.length === 1
    && changedPreservation.parentSnapshotIds[0] === 'a',
);
const mergePreservation = planCloudPreservation(
  inventory([a, b, divergent], ['b', 'd']),
  'digest-b',
);
check(
  'edited restore merges every current fork head instead of hiding divergence',
  mergePreservation.kind === 'publish'
    && mergePreservation.parentSnapshotIds.join(',') === 'b,d',
);

console.log(`Cloud sync model tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.log(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} cloud sync model test(s) failed`);
console.log('CLOUD SYNC MODEL TESTS: PASS');
