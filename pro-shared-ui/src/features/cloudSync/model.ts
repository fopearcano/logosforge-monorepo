import type {
  CloudSyncActionReceipt,
  CloudSyncBinding,
  CloudSyncProjectInventory,
  CloudSyncSnapshotMetadata,
} from "../../adapters/platform";

function sameIds(left: readonly string[], right: readonly string[]): boolean {
  if (left.length !== right.length) return false;
  const wanted = new Set(left);
  return wanted.size === left.length && right.every((id) => wanted.has(id));
}
export type CloudSyncDecisionKind =
  | "seed"
  | "idle"
  | "push"
  | "pull"
  | "conflict"
  | "remote-missing";

export interface CloudSyncDecision {
  kind: CloudSyncDecisionKind;
  heads: CloudSyncSnapshotMetadata[];
  localChanged: boolean;
  remoteChanged: boolean;
  reason: string;
}

export function cloudHeads(inventory: CloudSyncProjectInventory): CloudSyncSnapshotMetadata[] {
  const wanted = new Set(inventory.headSnapshotIds);
  return inventory.snapshots
    .filter((snapshot) => wanted.has(snapshot.snapshotId))
    .sort((left, right) => left.snapshotId.localeCompare(right.snapshotId));
}

export function newestCloudHead(
  heads: readonly CloudSyncSnapshotMetadata[],
): CloudSyncSnapshotMetadata | null {
  return [...heads].sort((left, right) => {
    const time = Date.parse(right.createdAt) - Date.parse(left.createdAt);
    return time || right.generation - left.generation || right.snapshotId.localeCompare(left.snapshotId);
  })[0] ?? null;
}

/**
 * Recover the immutable result of an interrupted Keep Both / Replace Cloud
 * publish. The match is intentionally unique and includes the complete parent
 * set, so unrelated prose with the same digest cannot satisfy a receipt.
 */
export function completedReceiptPublish(
  receipt: CloudSyncActionReceipt,
  inventory: CloudSyncProjectInventory | null,
): CloudSyncSnapshotMetadata | null {
  if (!inventory
    || (receipt.kind !== "keep-both" && receipt.kind !== "replace-cloud")
    || inventory.cloudProjectId !== receipt.originalCloudProjectId) return null;
  const matches = inventory.snapshots.filter((snapshot) => (
    snapshot.digest === receipt.expectedSourceDigest
    && sameIds(snapshot.parentSnapshotIds, receipt.parentSnapshotIds)
  ));
  return matches.length === 1 ? matches[0]! : null;
}

/** A crash may leave a committed child in the outbox before its binding save. */
export function matchingDescendantHead(
  localDigest: string,
  binding: CloudSyncBinding,
  inventory: CloudSyncProjectInventory,
): CloudSyncSnapshotMetadata | null {
  const matches = cloudHeads(inventory).filter((head) => (
    head.digest === localDigest
    && isCloudAncestor(inventory, binding.lastSnapshotId, head.snapshotId)
  ));
  return matches.length === 1 ? matches[0]! : null;
}

/** Whether `ancestorId` is reachable from `snapshotId` in this immutable DAG. */
export function isCloudAncestor(
  inventory: CloudSyncProjectInventory,
  ancestorId: string,
  snapshotId: string,
): boolean {
  if (ancestorId === snapshotId) return true;
  const byId = new Map(inventory.snapshots.map((snapshot) => [snapshot.snapshotId, snapshot]));
  const pending = [snapshotId];
  const visited = new Set<string>();
  while (pending.length) {
    const id = pending.pop()!;
    if (visited.has(id)) continue;
    visited.add(id);
    const snapshot = byId.get(id);
    if (!snapshot) continue;
    for (const parent of snapshot.parentSnapshotIds) {
      if (parent === ancestorId) return true;
      pending.push(parent);
    }
  }
  return false;
}

/**
 * Decide without mutating either side. Automatic pull is intentionally allowed
 * only when the complete local digest still equals the digest installed with
 * the binding and the provider has exactly one descendant head.
 */
export function decideCloudSync(
  localDigest: string,
  binding: CloudSyncBinding | null,
  inventory: CloudSyncProjectInventory | null,
): CloudSyncDecision {
  if (!binding) {
    return {
      kind: "seed", heads: [], localChanged: true, remoteChanged: false,
      reason: "This project has not been linked to a cloud history yet.",
    };
  }
  if (!inventory) {
    return {
      kind: "remote-missing", heads: [],
      localChanged: localDigest !== binding.lastDigest,
      remoteChanged: true,
      reason: "The linked cloud history is missing. It will not be recreated automatically.",
    };
  }
  const heads = cloudHeads(inventory);
  const localChanged = localDigest !== binding.lastDigest;
  if (heads.length === 0) {
    return {
      kind: "remote-missing", heads, localChanged, remoteChanged: true,
      reason: "The linked cloud history has no valid head snapshot.",
    };
  }
  const unchangedRemote = heads.length === 1 && heads[0]!.snapshotId === binding.lastSnapshotId;
  const remoteChanged = !unchangedRemote;

  if (!localChanged && !remoteChanged) {
    return { kind: "idle", heads, localChanged, remoteChanged, reason: "Local and cloud copies match." };
  }
  if (localChanged && !remoteChanged) {
    return { kind: "push", heads, localChanged, remoteChanged, reason: "Local changes are ready to publish." };
  }
  if (!localChanged && heads.length === 1
    && isCloudAncestor(inventory, binding.lastSnapshotId, heads[0]!.snapshotId)) {
    return { kind: "pull", heads, localChanged, remoteChanged, reason: "A newer cloud snapshot can be applied safely." };
  }
  return {
    kind: "conflict", heads, localChanged, remoteChanged,
    reason: heads.length > 1
      ? "The provider contains multiple preserved branches. Choose how to recover them."
      : "Local and cloud copies both changed. Nothing was overwritten.",
  };
}

