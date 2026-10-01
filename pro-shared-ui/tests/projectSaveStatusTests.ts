/** Observable project-save status tests. */

import {
  discardProjectSavePending,
  flushPendingProjectSaves,
  getProjectSaveStatusSnapshot,
  markProjectSavePending,
  PendingProjectSaveError,
  registerProjectFlusher,
  resetProjectSaveStatus,
  subscribeProjectSaveStatus,
  trackProjectOperation,
  trackProjectWrite,
} from "../src/adapters/projectSaveCoordinator";

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: boolean): void => {
  if (condition) passed += 1;
  else failures.push(label);
};

const initial = getProjectSaveStatusSnapshot();
check("initial snapshot is immutable", Object.isFrozen(initial));
check(
  "initial snapshot is clean and idle",
  initial.dirtyRevision === 0
    && initial.savedRevision === 0
    && !initial.dirty
    && initial.inFlightCount === 0
    && !initial.flushing
    && initial.lastSavedAt === null
    && initial.lastError === null,
);

let notifications = 0;
const unsubscribe = subscribeProjectSaveStatus(() => { notifications += 1; });

markProjectSavePending("editor:primary");
let snapshot = getProjectSaveStatusSnapshot();
check("mark pending advances the dirty revision", snapshot.dirty && snapshot.dirtyRevision === 1);
check("mark pending notifies observers", notifications === 1);

let releaseFirst!: () => void;
const firstWrite = new Promise<void>((resolve) => { releaseFirst = resolve; });
const trackedFirst = trackProjectWrite(firstWrite, { saveKey: "editor:primary" });
const firstWriteRevision = getProjectSaveStatusSnapshot().dirtyRevision;
trackProjectWrite(firstWrite, { saveKey: "editor:primary" });
snapshot = getProjectSaveStatusSnapshot();
check("tracked write is observable in flight", snapshot.inFlightCount === 1);
check("duplicate tracking preserves promise identity and revision", snapshot.dirtyRevision === firstWriteRevision);

markProjectSavePending("editor:primary");
const editDuringWriteRevision = getProjectSaveStatusSnapshot().dirtyRevision;
releaseFirst();
await trackedFirst;
snapshot = getProjectSaveStatusSnapshot();
check("successful write records completion time", typeof snapshot.lastSavedAt === "number");
check(
  "edit during write remains dirty",
  snapshot.inFlightCount === 0
    && snapshot.savedRevision === firstWriteRevision
    && snapshot.dirtyRevision === editDuringWriteRevision
    && snapshot.dirty,
);

let releaseDrain!: () => void;
const drainGate = new Promise<void>((resolve) => { releaseDrain = resolve; });
let sawFlushing = false;
let drainSavedLatest = false;
const unregisterDrain = registerProjectFlusher(async () => {
  sawFlushing = getProjectSaveStatusSnapshot().flushing;
  await drainGate;
  if (!drainSavedLatest) {
    drainSavedLatest = true;
    await trackProjectWrite(Promise.resolve(), { saveKey: "editor:primary" });
  }
  return true;
});
const draining = flushPendingProjectSaves();
await Promise.resolve();
check("drain publishes flushing state", getProjectSaveStatusSnapshot().flushing && sawFlushing);
releaseDrain();
await draining;
unregisterDrain();
snapshot = getProjectSaveStatusSnapshot();
check(
  "successful drain marks the latest edit saved",
  !snapshot.flushing && !snapshot.dirty && snapshot.savedRevision === snapshot.dirtyRevision,
);

let releaseStale!: () => void;
const staleWrite = trackProjectWrite(
  new Promise<void>((resolve) => { releaseStale = resolve; }),
  { saveKey: "editor:stale" },
);
const failure = new Error("disk unavailable");
const failedWrite = trackProjectWrite(Promise.reject(failure), { saveKey: "editor:failed" });
await failedWrite.catch(() => undefined);
snapshot = getProjectSaveStatusSnapshot();
check("write failure remains observable", snapshot.lastError === failure && snapshot.dirty);

releaseStale();
await staleWrite;
snapshot = getProjectSaveStatusSnapshot();
check("older in-flight success cannot hide a newer failure", snapshot.lastError === failure && snapshot.dirty);

await trackProjectWrite(Promise.resolve(), { saveKey: "editor:unrelated" });
snapshot = getProjectSaveStatusSnapshot();
check("unrelated later success cannot clear a failed owner", snapshot.lastError === failure && snapshot.dirty);

const unregisterNoop = registerProjectFlusher(async () => true);
let noOpDrainError: unknown = null;
try { await flushPendingProjectSaves(); } catch (error) { noOpDrainError = error; }
unregisterNoop();
snapshot = getProjectSaveStatusSnapshot();
check(
  "no-op flusher cannot clear a failed write",
  noOpDrainError instanceof PendingProjectSaveError && snapshot.lastError === failure && snapshot.dirty,
);

await trackProjectWrite(Promise.resolve(), { saveKey: "editor:failed" });
snapshot = getProjectSaveStatusSnapshot();
check("same-owner retry clears its failure", snapshot.lastError === null && !snapshot.dirty);

markProjectSavePending();
let flusherFails = true;
const unregisterRetry = registerProjectFlusher(async () => !flusherFails);
let drainError: unknown = null;
try { await flushPendingProjectSaves(); } catch (error) { drainError = error; }
snapshot = getProjectSaveStatusSnapshot();
check(
  "failed drain remains dirty while throwing an aggregate",
  drainError instanceof PendingProjectSaveError
    && snapshot.lastError === null
    && snapshot.dirty,
);
flusherFails = false;
await flushPendingProjectSaves();
unregisterRetry();
snapshot = getProjectSaveStatusSnapshot();
check("later successful drain clears the failure", snapshot.lastError === null && !snapshot.dirty);

resetProjectSaveStatus();
snapshot = getProjectSaveStatusSnapshot();
check(
  "project transition resets the clean active-project snapshot",
  snapshot.dirtyRevision === 0
    && snapshot.savedRevision === 0
    && snapshot.lastSavedAt === null
    && snapshot.lastError === null,
);

await trackProjectOperation(Promise.reject(new Error("provider unavailable"))).catch(() => undefined);
snapshot = getProjectSaveStatusSnapshot();
check("barrier-only operation failure does not invent unsaved data", !snapshot.dirty && snapshot.lastError === null);

let releasePersistence!: () => void;
const persistence = trackProjectOperation(
  new Promise<void>((resolve) => { releasePersistence = resolve; }),
  { persistence: true },
);
snapshot = getProjectSaveStatusSnapshot();
check("ownerless persistence operation reports one in-flight save", snapshot.inFlightCount === 1 && !snapshot.dirty);
releasePersistence();
await persistence;
snapshot = getProjectSaveStatusSnapshot();
check("ownerless persistence success records completion without dirty state", snapshot.inFlightCount === 0 && !snapshot.dirty && snapshot.lastSavedAt !== null);

const ownerlessFailure = new Error("action rejected");
await trackProjectWrite(Promise.reject(ownerlessFailure)).catch(() => undefined);
snapshot = getProjectSaveStatusSnapshot();
check("ownerless write failure does not poison later handoffs", !snapshot.dirty && snapshot.lastError === null);

let releaseUpgrade!: () => void;
const upgradePromise = new Promise<void>((resolve) => { releaseUpgrade = resolve; });
trackProjectOperation(upgradePromise, { persistence: true });
trackProjectWrite(upgradePromise, { saveKey: "editor:upgrade" });
snapshot = getProjectSaveStatusSnapshot();
check("draft owner upgrades an HTTP barrier without double counting", snapshot.inFlightCount === 1);
releaseUpgrade();
await upgradePromise;
snapshot = getProjectSaveStatusSnapshot();
check("upgraded owner resolves cleanly", snapshot.inFlightCount === 0 && !snapshot.dirty);

resetProjectSaveStatus();
let rejectOlder!: (error: Error) => void;
let resolveNewer!: () => void;
const older = trackProjectWrite(
  new Promise<void>((_resolve, reject) => { rejectOlder = reject; }),
  { saveKey: "editor:ordered" },
);
const newer = trackProjectWrite(
  new Promise<void>((resolve) => { resolveNewer = resolve; }),
  { saveKey: "editor:ordered" },
);
resolveNewer();
await newer;
const newerSavedAt = getProjectSaveStatusSnapshot().lastSavedAt;
rejectOlder(new Error("stale request failed"));
await older.catch(() => undefined);
snapshot = getProjectSaveStatusSnapshot();
check(
  "older rejection cannot resurrect a resolved owner failure",
  !snapshot.dirty && snapshot.lastError === null && snapshot.lastSavedAt === newerSavedAt,
);

resetProjectSaveStatus();
let releaseDiscarded!: () => void;
const discarded = trackProjectWrite(
  new Promise<void>((resolve) => { releaseDiscarded = resolve; }),
  { saveKey: "editor:discarded" },
);
discardProjectSavePending("editor:discarded");
releaseDiscarded();
await discarded;
snapshot = getProjectSaveStatusSnapshot();
check(
  "discarded in-flight success cannot claim a save",
  snapshot.inFlightCount === 0 && !snapshot.dirty && snapshot.lastError === null && snapshot.lastSavedAt === null,
);

resetProjectSaveStatus();
let releaseOlderSuccess!: () => void;
let releaseNewerSuccess!: () => void;
const olderSuccess = trackProjectWrite(
  new Promise<void>((resolve) => { releaseOlderSuccess = resolve; }),
  { saveKey: "editor:success-order" },
);
const newerSuccess = trackProjectWrite(
  new Promise<void>((resolve) => { releaseNewerSuccess = resolve; }),
  { saveKey: "editor:success-order" },
);
releaseNewerSuccess();
await newerSuccess;
const orderedSavedAt = getProjectSaveStatusSnapshot().lastSavedAt;
releaseOlderSuccess();
await olderSuccess;
snapshot = getProjectSaveStatusSnapshot();
check(
  "older success clears its in-flight count without replacing the newer save time",
  snapshot.inFlightCount === 0 && !snapshot.dirty && snapshot.lastSavedAt === orderedSavedAt,
);

const notificationsBeforeUnsubscribe = notifications;
unsubscribe();
markProjectSavePending();
check("unsubscribe stops notifications", notifications === notificationsBeforeUnsubscribe);

console.log(`Project save status tests: ${passed} passed, ${failures.length} failed`);
for (const item of failures) console.error(`  FAIL: ${item}`);
if (failures.length) throw new Error(`${failures.length} project-save status test(s) failed`);
console.log("PROJECT SAVE STATUS TESTS: PASS");
