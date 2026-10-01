import {
  WARM_SCENE_LIMIT,
  pruneSceneIds,
  pruneSceneRecord,
  touchWarmSceneIds,
} from "../src/components/manuscript/manuscriptViewport";
import type { SceneDTO } from "@logosforge/ui-contracts";
import {
  canMoveBySortOrder,
  isNeighborInMoveDirection,
  rawIndexForScene,
  rawSceneRanks,
  sameStructuralGroup,
} from "../src/components/manuscript/manuscriptOrdering";

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: boolean): void => {
  if (condition) passed += 1;
  else failures.push(label);
};

const original = [4, 3, 2, 1];
const touched = touchWarmSceneIds(original, 2, 4);
check("touch moves an existing scene to most-recent", touched.join(",") === "2,4,3,1");
check("touch never mutates its input", original.join(",") === "4,3,2,1");
check("repeat touch preserves reference when order is unchanged", touchWarmSceneIds(touched, 2, 4) === touched);

let warm: number[] = [];
for (let id = 1; id <= WARM_SCENE_LIMIT + 4; id += 1) warm = touchWarmSceneIds(warm, id);
check("warm history is bounded", warm.length === WARM_SCENE_LIMIT);
check("warm history keeps newest ids first", warm[0] === WARM_SCENE_LIMIT + 4 && warm.at(-1) === 5);
check("zero limit keeps no editor warm", touchWarmSceneIds([1, 2], 3, 0).length === 0);

const valid = new Set([2, 4]);
check("scene-id pruning removes deleted scenes", pruneSceneIds([4, 3, 2, 1], valid).join(",") === "4,2");
const alreadyValid = [4, 2];
check("scene-id no-op preserves the actual input", pruneSceneIds(alreadyValid, valid) === alreadyValid);

const record = { 1: "old", 2: "keep", 4: "also keep" };
const pruned = pruneSceneRecord(record, valid);
check("scene-record pruning removes deleted keys", JSON.stringify(pruned) === JSON.stringify({ 2: "keep", 4: "also keep" }));
const validRecord = { 2: "keep", 4: "also keep" };
check("scene-record no-op preserves reference", pruneSceneRecord(validRecord, valid) === validRecord);

const orderedScene = (id: number, act: string, chapter: string, sortOrder: number): SceneDTO => ({
  id, title: String(id), content: "", summary: "", synopsis: "", goal: "", conflict: "", outcome: "",
  beat: "", act, chapter, plotline: "", color_label: "", tags: [], sort_order: sortOrder,
  order_index: id, character_ids: [], place_ids: [], who_knows_what: "", revision: `r${id}`,
});
const a1 = orderedScene(1, " Act A ", "One", 10);
const b1 = orderedScene(2, "Act B", "One", 20);
const a2 = orderedScene(3, "Act A", "One", 30);
check("trimmed Act and Chapter labels identify one move group", sameStructuralGroup(a1, a2));
check("cross-Act neighbors cannot advertise a sort-only move", !sameStructuralGroup(b1, a2));
check("raw move targets use array rank rather than sparse sort_order", rawIndexForScene([a1, a2, b1], b1.id) === 1);
check("missing raw move targets are rejected", rawIndexForScene([a1, a2], 999) === -1);
const divergentRanks = rawSceneRanks([a1, a2, b1]);
check("canonical siblings separated in raw storage cannot use a one-row move", !canMoveBySortOrder(divergentRanks, a1, a2));
const contiguousRanks = rawSceneRanks([a1, a2]);
check("raw-adjacent structural siblings can use a one-row move", canMoveBySortOrder(contiguousRanks, a1, a2));
check("fresh canonical order confirms the requested down neighbor", isNeighborInMoveDirection([a1, a2], a1.id, a2.id, "down"));
check("reversed fresh order rejects a stale down click", !isNeighborInMoveDirection([a2, a1], a1.id, a2.id, "down"));
check("fresh canonical order confirms the requested up neighbor", isNeighborInMoveDirection([a1, a2], a2.id, a1.id, "up"));

console.log(`Manuscript viewport tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} manuscript viewport test(s) failed`);
console.log("MANUSCRIPT VIEWPORT TESTS: PASS");
