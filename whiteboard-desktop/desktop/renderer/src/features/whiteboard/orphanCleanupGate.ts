/** Identity of the exact live manuscript snapshot that found orphan comments. */
export interface OrphanCleanupSnapshot {
  documentId: string;
  incarnation: string;
  generation: number;
  orphanIds: readonly string[];
}

export type CurrentOrphanCleanupSnapshot = Omit<OrphanCleanupSnapshot, 'orphanIds'>;

/**
 * Revalidate delayed destructive cleanup after persistence finishes. A document
 * switch/recreation, any newer block snapshot, or an anchor restored meanwhile
 * makes the stale candidate ineligible.
 */
export function eligibleOrphanCleanupIds(
  captured: OrphanCleanupSnapshot,
  current: CurrentOrphanCleanupSnapshot,
  currentOrphanIds: readonly string[],
): string[] {
  if (
    captured.documentId !== current.documentId
    || captured.incarnation !== current.incarnation
    || captured.generation !== current.generation
  ) return [];

  const stillOrphaned = new Set(currentOrphanIds);
  return captured.orphanIds.filter((id) => stillOrphaned.has(id));
}
