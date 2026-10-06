import {
  SCENE_FOCUS_RETRY_ATTEMPTS,
  WARM_SCENE_LIMIT,
  pruneSceneIds,
  pruneSceneRecord,
  startSceneFocusRetry,
  touchWarmSceneIds,
} from "../src/components/manuscript/manuscriptViewport";

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

let nextHandle = 0;
const scheduled = new Map<number, () => void>();
const schedule = (callback: () => void): number => {
  nextHandle += 1;
  scheduled.set(nextHandle, callback);
  return nextHandle;
};
const cancel = (handle: number): void => { scheduled.delete(handle); };
const runNext = (): void => {
  const next = scheduled.entries().next().value as [number, () => void] | undefined;
  if (!next) throw new Error("No scheduled scene-focus attempt");
  scheduled.delete(next[0]);
  next[1]();
};

let editorReady = false;
let editorFocused = false;
let focusAttempts = 0;
startSceneFocusRetry({
  shouldContinue: () => true,
  tryFocus: () => {
    focusAttempts += 1;
    editorFocused = editorReady;
    return editorFocused;
  },
  isFocusStable: () => editorFocused,
  schedule,
  cancel,
});
runNext();
check("scene focus retries when the live editor has not mounted", focusAttempts === 1 && scheduled.size === 1);
editorReady = true;
runNext();
check("scene focus schedules stability confirmation after a delayed editor mount", focusAttempts === 2 && scheduled.size === 1);
runNext();
check("scene focus settles only after delayed focus remains stable", focusAttempts === 2 && scheduled.size === 0);

let racedFocusOwned = false;
let racedFocusAttempts = 0;
startSceneFocusRetry({
  shouldContinue: () => true,
  tryFocus: () => {
    racedFocusAttempts += 1;
    racedFocusOwned = true;
    return true;
  },
  isFocusStable: () => racedFocusOwned,
  schedule,
  cancel,
});
runNext();
racedFocusOwned = false;
runNext();
check("scene focus retries when modal teardown reclaims initial focus", racedFocusAttempts === 2 && scheduled.size === 1);
runNext();
check("scene focus settles after the replacement focus survives confirmation", racedFocusAttempts === 2 && scheduled.size === 0);

let scrollOnlyAttempts = 0;
startSceneFocusRetry({
  shouldContinue: () => true,
  tryFocus: () => { scrollOnlyAttempts += 1; return true; },
  isFocusStable: () => true,
  schedule,
  cancel,
});
runNext();
runNext();
check("scroll-only scene jumps settle without repeating their action", scrollOnlyAttempts === 1 && scheduled.size === 0);

let targetCurrent = true;
let staleFocusAttempts = 0;
startSceneFocusRetry({
  shouldContinue: () => targetCurrent,
  tryFocus: () => { staleFocusAttempts += 1; return false; },
  isFocusStable: () => false,
  schedule,
  cancel,
});
targetCurrent = false;
runNext();
check("scene focus abandons a superseded navigation", staleFocusAttempts === 0 && scheduled.size === 0);

let cancelledFocusAttempts = 0;
const cancelFocus = startSceneFocusRetry({
  shouldContinue: () => true,
  tryFocus: () => { cancelledFocusAttempts += 1; return false; },
  isFocusStable: () => false,
  schedule,
  cancel,
});
cancelFocus();
check("scene focus cancellation clears its pending timer", cancelledFocusAttempts === 0 && scheduled.size === 0);

let boundedFocusAttempts = 0;
startSceneFocusRetry({
  shouldContinue: () => true,
  tryFocus: () => { boundedFocusAttempts += 1; return false; },
  isFocusStable: () => false,
  schedule,
  cancel,
  maxAttempts: 2,
});
runNext();
runNext();
check("scene focus retry is bounded", boundedFocusAttempts === 2 && scheduled.size === 0);

let unstableFocusAttempts = 0;
let unstableFocusChecks = 0;
startSceneFocusRetry({
  shouldContinue: () => true,
  tryFocus: () => { unstableFocusAttempts += 1; return true; },
  isFocusStable: () => { unstableFocusChecks += 1; return false; },
  schedule,
  cancel,
  maxAttempts: 2,
});
runNext();
runNext();
runNext();
check(
  "scene focus stability retries remain bounded",
  unstableFocusAttempts === 2 && unstableFocusChecks === 2 && scheduled.size === 0,
);
check("scene focus default retry window stays finite", SCENE_FOCUS_RETRY_ATTEMPTS > 1 && SCENE_FOCUS_RETRY_ATTEMPTS <= 100);

console.log(`Manuscript viewport tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} manuscript viewport test(s) failed`);
console.log("MANUSCRIPT VIEWPORT TESTS: PASS");
