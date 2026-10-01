import type { SceneDTO } from "@logosforge/ui-contracts";

/** A sort-order-only move is meaningful only inside one canonical group. */
export function sameStructuralGroup(
  left: SceneDTO | undefined,
  right: SceneDTO,
): boolean {
  return Boolean(
    left
    && left.act.trim() === right.act.trim()
    && left.chapter.trim() === right.chapter.trim(),
  );
}

/**
 * Translate a canonical adjacent scene back to the raw 0-based index expected
 * by PATCH `sort_order`. Persisted sort values are metadata and may be sparse.
 */
export function rawIndexForScene(
  scenes: readonly SceneDTO[],
  sceneId: number,
): number {
  return rawSceneRanks(scenes).get(sceneId) ?? -1;
}

/** Raw positions used by the legacy one-scene reorder mutation. */
export function rawSceneRanks(
  scenes: readonly SceneDTO[],
): ReadonlyMap<number, number> {
  return new Map(
    [...scenes]
      .sort((left, right) => left.sort_order - right.sort_order || left.id - right.id)
      .map((scene, index) => [scene.id, index]),
  );
}

/**
 * A one-row sort mutation is safe only for raw-adjacent structural siblings.
 * Canonical grouping can otherwise make two displayed siblings non-adjacent
 * in storage (A1, B1, A2 renders A1, A2, B1); moving just A1 or A2 across B1
 * would unexpectedly change the order of the surrounding structural groups.
 */
export function canMoveBySortOrder(
  ranks: ReadonlyMap<number, number>,
  neighbor: SceneDTO | undefined,
  scene: SceneDTO,
): boolean {
  if (!sameStructuralGroup(neighbor, scene)) return false;
  const neighborRank = ranks.get(neighbor!.id);
  const sceneRank = ranks.get(scene.id);
  return neighborRank != null
    && sceneRank != null
    && Math.abs(neighborRank - sceneRank) === 1;
}

/** Reject a stale click if the freshly loaded canonical order changed sides. */
export function isNeighborInMoveDirection(
  scenes: readonly SceneDTO[],
  sceneId: number,
  neighborId: number,
  direction: "up" | "down",
): boolean {
  const sceneIndex = scenes.findIndex((scene) => scene.id === sceneId);
  const neighborIndex = scenes.findIndex((scene) => scene.id === neighborId);
  return sceneIndex >= 0 && (
    direction === "up"
      ? neighborIndex === sceneIndex - 1
      : neighborIndex === sceneIndex + 1
  );
}
