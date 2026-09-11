export const WARM_SCENE_LIMIT = 6;

/** Most-recently-used scene ids whose editor history should stay mounted. */
export function touchWarmSceneIds(current: number[], id: number, limit = WARM_SCENE_LIMIT): number[] {
  const size = Math.max(0, Math.floor(limit));
  if (size === 0) return [];
  const next = [id, ...current.filter((candidate) => candidate !== id)].slice(0, size);
  return next.length === current.length && next.every((value, index) => value === current[index])
    ? current
    : next;
}

export function pruneSceneIds(current: number[], validIds: ReadonlySet<number>): number[] {
  const next = current.filter((id) => validIds.has(id));
  return next.length === current.length ? current : next;
}

export function pruneSceneRecord<T>(current: Record<number, T>, validIds: ReadonlySet<number>): Record<number, T> {
  const entries = Object.entries(current).filter(([id]) => validIds.has(Number(id)));
  return entries.length === Object.keys(current).length
    ? current
    : Object.fromEntries(entries) as Record<number, T>;
}
