import type {
  CloudSyncActionReceipt,
  CloudSyncBinding,
  CloudSyncProjectInventory,
} from "../src/adapters/platform";
import {
  completedReceiptPublish,
  decideCloudSync,
  isCloudAncestor,
  matchingDescendantHead,
} from "../src/features/cloudSync/model";
import {
  validateCloudProjectApplyResultDTO,
  validateCloudProjectSnapshotDTO,
} from "../src/adapters/runtimeDtoValidation";

function check(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

const binding: CloudSyncBinding = {
  localProjectId: "7",
  localIncarnation: "11111111-1111-4111-8111-111111111111",
  cloudProjectId: "22222222-2222-4222-8222-222222222222",
  lastSnapshotId: "33333333-3333-4333-8333-333333333333",
  lastDigest: "a".repeat(64),
};

const inventory: CloudSyncProjectInventory = {
  cloudProjectId: binding.cloudProjectId,
  title: "Novel",
  snapshots: [
    {
      snapshotId: binding.lastSnapshotId, parentSnapshotIds: [], generation: 1,
      digest: binding.lastDigest, createdAt: "2026-11-18T10:00:00Z",
      deviceId: "44444444-4444-4444-8444-444444444444", title: "Novel", queued: false,
    },
    {
      snapshotId: "55555555-5555-4555-8555-555555555555",
      parentSnapshotIds: [binding.lastSnapshotId], generation: 2,
      digest: "b".repeat(64), createdAt: "2026-11-18T11:00:00Z",
      deviceId: "66666666-6666-4666-8666-666666666666", title: "Novel", queued: false,
    },
  ],
  headSnapshotIds: [binding.lastSnapshotId],
};

check(decideCloudSync(binding.lastDigest, binding, inventory).kind === "idle", "matching head must be idle");
check(decideCloudSync("c".repeat(64), binding, inventory).kind === "push", "local-only change must push");

const advanced = { ...inventory, headSnapshotIds: [inventory.snapshots[1]!.snapshotId] };
check(isCloudAncestor(advanced, binding.lastSnapshotId, advanced.headSnapshotIds[0]!), "parent must be an ancestor");
check(decideCloudSync(binding.lastDigest, binding, advanced).kind === "pull", "unchanged local copy may safely pull one descendant");
check(decideCloudSync("c".repeat(64), binding, advanced).kind === "conflict", "two-sided changes must never auto-overwrite");
check(
  matchingDescendantHead("b".repeat(64), binding, advanced)?.snapshotId
    === inventory.snapshots[1]!.snapshotId,
  "a committed descendant with the exact local digest is safe to adopt after a binding-save crash",
);
check(
  matchingDescendantHead("c".repeat(64), binding, advanced) === null,
  "a descendant with different content must not be adopted",
);

const branched = {
  ...advanced,
  headSnapshotIds: [binding.lastSnapshotId, inventory.snapshots[1]!.snapshotId],
};
check(decideCloudSync(binding.lastDigest, binding, branched).kind === "conflict", "multiple provider heads require review");
check(decideCloudSync(binding.lastDigest, binding, null).kind === "remote-missing", "missing remote lineage must not be recreated silently");
check(decideCloudSync(binding.lastDigest, null, null).kind === "seed", "an unbound project should seed a new lineage");

const replaceReceipt: CloudSyncActionReceipt = {
  actionId: "88888888-8888-4888-8888-888888888888",
  kind: "replace-cloud",
  phase: "prepared",
  sourceLocalProjectId: binding.localProjectId,
  sourceLocalIncarnation: binding.localIncarnation,
  originalCloudProjectId: binding.cloudProjectId,
  intendedCloudProjectId: null,
  snapshotId: inventory.snapshots[1]!.snapshotId,
  snapshotDigest: inventory.snapshots[1]!.digest,
  parentSnapshotIds: [binding.lastSnapshotId],
  expectedSourceDigest: inventory.snapshots[1]!.digest,
  restoredLocalProjectId: null,
  restoredLocalIncarnation: null,
  createdAt: "2026-11-18T11:01:00Z",
  updatedAt: "2026-11-18T11:01:00Z",
};
check(
  completedReceiptPublish(replaceReceipt, advanced)?.snapshotId
    === inventory.snapshots[1]!.snapshotId,
  "receipt recovery finds the unique immutable publish by digest and complete parent set",
);
check(
  completedReceiptPublish(
    replaceReceipt,
    { ...advanced, snapshots: [...advanced.snapshots, { ...advanced.snapshots[1]!, snapshotId: "99999999-9999-4999-8999-999999999999" }] },
  ) === null,
  "receipt recovery refuses an ambiguous duplicate publish",
);

const identity = "77777777-7777-4777-8777-777777777777";
validateCloudProjectSnapshotDTO({
  format: "logosforge-pro-project-snapshot",
  version: "1.0",
  schema_version: 7,
  project_identity: identity,
  project: { title: "Novel", sync_id: identity },
  tables: { project: [{ key: "project", values: { title: "Novel" }, references: {} }] },
  digest: "d".repeat(64),
});
validateCloudProjectApplyResultDTO({
  project_id: 12,
  project_identity: identity,
  digest: "d".repeat(64),
  mode: "replace",
});
let rejectedIdentityMismatch = false;
try {
  validateCloudProjectSnapshotDTO({
    format: "logosforge-pro-project-snapshot", version: "1.0", schema_version: 7,
    project_identity: identity,
    project: { title: "Novel", sync_id: "another-project" }, tables: {}, digest: "d".repeat(64),
  });
} catch { rejectedIdentityMismatch = true; }
check(rejectedIdentityMismatch, "snapshot validation must reject mismatched portable identities");

console.log("cloud sync model tests passed");
