/**
 * Pure cloud-sync history decisions.
 *
 * Cloud-folder providers do not offer Whiteboard an atomic compare-and-swap
 * primitive.  Immutable snapshots therefore form a small DAG: every device
 * can publish without overwriting another device, and multiple heads are an
 * explicit conflict instead of a silent last-writer-wins data loss.
 */

export interface CloudSnapshotMetadata {
  snapshotId: string;
  parentSnapshotIds: string[];
  generation: number;
  digest: string;
  createdAt: string;
  deviceId: string;
  title: string;
}

export interface CloudProjectInventory {
  cloudProjectId: string;
  snapshots: CloudSnapshotMetadata[];
  headSnapshotIds: string[];
}

export interface CloudDocumentBinding {
  localDocumentId: string;
  localIncarnation: string;
  cloudProjectId: string;
  lastSnapshotId: string;
  lastDigest: string;
}

export type CloudSyncDecision =
  | { kind: 'seed'; reason: 'unbound' }
  | { kind: 'upload'; parentSnapshotIds: string[]; reason: 'local-changed' }
  | { kind: 'wait'; reason: 'remote-history-missing' }
  | { kind: 'pull'; snapshot: CloudSnapshotMetadata }
  | { kind: 'advance'; snapshot: CloudSnapshotMetadata }
  | { kind: 'merge-identical'; heads: CloudSnapshotMetadata[] }
  | { kind: 'conflict'; heads: CloudSnapshotMetadata[]; reason: string }
  | { kind: 'noop'; snapshot: CloudSnapshotMetadata };

function metadataMap(inventory: CloudProjectInventory): Map<string, CloudSnapshotMetadata> {
  return new Map(inventory.snapshots.map((snapshot) => [snapshot.snapshotId, snapshot]));
}

export function cloudProjectHeads(inventory: CloudProjectInventory): CloudSnapshotMetadata[] {
  const byId = metadataMap(inventory);
  return inventory.headSnapshotIds
    .map((id) => byId.get(id))
    .filter((snapshot): snapshot is CloudSnapshotMetadata => snapshot !== undefined)
    .sort((left, right) => (
      left.generation - right.generation
      || left.createdAt.localeCompare(right.createdAt)
      || left.snapshotId.localeCompare(right.snapshotId)
    ));
}

export function cloudSnapshotDescendsFrom(
  inventory: CloudProjectInventory,
  snapshotId: string,
  ancestorSnapshotId: string,
): boolean {
  if (snapshotId === ancestorSnapshotId) return true;
  const byId = metadataMap(inventory);
  const pending = [snapshotId];
  const visited = new Set<string>();
  while (pending.length) {
    const currentId = pending.pop() as string;
    if (visited.has(currentId)) continue;
    visited.add(currentId);
    const current = byId.get(currentId);
    if (!current) continue;
    for (const parentId of current.parentSnapshotIds) {
      if (parentId === ancestorSnapshotId) return true;
      if (!visited.has(parentId)) pending.push(parentId);
    }
  }
  return false;
}

export function decideCloudSync(
  binding: CloudDocumentBinding | null,
  localDigest: string,
  inventory: CloudProjectInventory | null,
): CloudSyncDecision {
  if (!binding) return { kind: 'seed', reason: 'unbound' };
  if (!inventory || inventory.snapshots.length === 0) {
    return { kind: 'wait', reason: 'remote-history-missing' };
  }

  const heads = cloudProjectHeads(inventory);
  if (heads.length === 0) {
    return { kind: 'conflict', heads: [], reason: 'The cloud history has no readable head.' };
  }

  if (heads.length > 1) {
    const digest = heads[0].digest;
    if (heads.every((head) => head.digest === digest) && localDigest === digest) {
      return { kind: 'merge-identical', heads };
    }
    return {
      kind: 'conflict',
      heads,
      reason: 'More than one device published a different project version.',
    };
  }

  const head = heads[0];
  if (head.snapshotId === binding.lastSnapshotId) {
    return localDigest === binding.lastDigest
      ? { kind: 'noop', snapshot: head }
      : { kind: 'upload', parentSnapshotIds: [head.snapshotId], reason: 'local-changed' };
  }

  // Equal content is always safe to advance even if a provider lost old parent
  // metadata: the complete canonical project bytes are already identical.
  if (localDigest === head.digest) return { kind: 'advance', snapshot: head };

  const remoteAdvanced = cloudSnapshotDescendsFrom(
    inventory,
    head.snapshotId,
    binding.lastSnapshotId,
  );
  if (!remoteAdvanced) {
    return {
      kind: 'conflict',
      heads,
      reason: 'The cloud project no longer descends from this device’s last synced version.',
    };
  }
  if (localDigest === binding.lastDigest) return { kind: 'pull', snapshot: head };
  return {
    kind: 'conflict',
    heads,
    reason: 'This device and another device both changed the project since the last sync.',
  };
}

export function newestCloudHead(heads: readonly CloudSnapshotMetadata[]): CloudSnapshotMetadata | null {
  return [...heads].sort((left, right) => (
    right.generation - left.generation
    || right.createdAt.localeCompare(left.createdAt)
    || right.snapshotId.localeCompare(left.snapshotId)
  ))[0] ?? null;
}

export interface RemoteRecoveryReceiptStatus {
  snapshotId: string;
  phase: string;
}

export interface RemoteRecoveryPlan {
  currentHeadIds: string[];
  missingHeadIds: string[];
  readyToIgnoreOriginal: boolean;
}

/**
 * Reconcile recovery against the provider folder's current heads, not the
 * head list captured by an earlier receipt. A branch arriving mid-recovery is
 * therefore planned before the original multi-head history can be ignored.
 */
export function planRemoteRecovery(
  inventory: CloudProjectInventory,
  receipts: readonly RemoteRecoveryReceiptStatus[],
  recoveredHeadIds: readonly string[] = [],
): RemoteRecoveryPlan {
  const currentHeadIds = cloudProjectHeads(inventory)
    .map((head) => head.snapshotId)
    .sort();
  const planned = new Set(receipts.map((receipt) => receipt.snapshotId));
  const recovered = new Set(recoveredHeadIds);
  const installed = new Set(
    receipts
      .filter((receipt) => receipt.phase === 'binding-installed')
      .map((receipt) => receipt.snapshotId),
  );
  return {
    currentHeadIds,
    missingHeadIds: currentHeadIds.filter((id) => !planned.has(id) && !recovered.has(id)),
    readyToIgnoreOriginal: currentHeadIds.length > 0
      && currentHeadIds.every((id) => installed.has(id) || recovered.has(id)),
  };
}

/** Stable UUID for a crash-replayed preservation fork. */
export async function deterministicCloudRecoveryUuid(seed: string): Promise<string> {
  const digest = new Uint8Array(await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(seed),
  ));
  digest[6] = (digest[6] & 0x0f) | 0x40;
  digest[8] = (digest[8] & 0x3f) | 0x80;
  const hex = [...digest.slice(0, 16)]
    .map((value) => value.toString(16).padStart(2, '0'))
    .join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function staleRestoreSuccessorActionId(actionId: string): string {
  return `retry:${actionId}`;
}

export type CloudPreservationPlan =
  | { kind: 'reuse'; snapshot: CloudSnapshotMetadata }
  | { kind: 'publish'; parentSnapshotIds: string[] };

/**
 * Decide how to make edited recovery bytes durable in an existing fork.
 * Multiple heads are always joined by a new child, even when one happens to
 * share the digest, so the replay does not leave a hidden divergent branch.
 */
export function planCloudPreservation(
  inventory: CloudProjectInventory | null,
  currentDigest: string,
): CloudPreservationPlan {
  if (!inventory) return { kind: 'publish', parentSnapshotIds: [] };
  const heads = cloudProjectHeads(inventory);
  if (heads.length === 1 && heads[0].digest === currentDigest) {
    return { kind: 'reuse', snapshot: heads[0] };
  }
  return {
    kind: 'publish',
    parentSnapshotIds: heads.map((head) => head.snapshotId).sort(),
  };
}
