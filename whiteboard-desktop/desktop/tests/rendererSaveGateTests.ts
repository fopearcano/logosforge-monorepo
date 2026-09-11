import {
  createRendererSaveGate,
  RendererCloseCapabilities,
  RendererSaveRequestRegistry,
  type RendererSaveClock,
} from '../electron/renderer-save-gate';

class ManualClock implements RendererSaveClock {
  callback: (() => void) | null = null;
  delayMs: number | null = null;
  readonly handle = Symbol('timeout');
  cleared = 0;

  setTimeout(callback: () => void, delayMs: number): unknown {
    this.callback = callback;
    this.delayMs = delayMs;
    return this.handle;
  }

  clearTimeout(handle: unknown): void {
    if (handle === this.handle) this.cleared += 1;
  }

  expire(): void {
    this.callback?.();
  }
}

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: boolean): void => {
  if (condition) passed += 1;
  else failures.push(label);
};

const capabilities = new RendererCloseCapabilities();
check('a new renderer exposes no close capability', !capabilities.canFlushAutosave);
check('a new renderer exposes no external-file Save capability', !capabilities.canSaveExternalFile);
capabilities.setExternalSaveReady(true);
check(
  'the hook cannot publish external-file Save before module autosave readiness',
  !capabilities.canSaveExternalFile,
);
capabilities.setAutosaveReady(true);
check('module readiness enables renderer autosave', capabilities.canFlushAutosave);
check(
  'module readiness does not invent a hook-scoped external-file Save handler',
  !capabilities.canSaveExternalFile,
);
capabilities.setExternalSaveReady(true);
check('a mounted file hook enables external-file Save', capabilities.canSaveExternalFile);
capabilities.setExternalSaveReady(false);
check('an App error-boundary unmount disables external-file Save', !capabilities.canSaveExternalFile);
check('an App error-boundary unmount preserves module autosave', capabilities.canFlushAutosave);
capabilities.setExternalSaveReady(true);
capabilities.setAutosaveReady(false);
check('losing module readiness also disables external-file Save', !capabilities.canSaveExternalFile);
capabilities.setAutosaveReady(true);
capabilities.setExternalSaveReady(true);
capabilities.clearForRendererLoss();
check('renderer navigation or crash clears autosave readiness', !capabilities.canFlushAutosave);
check('renderer navigation or crash clears external-file Save readiness', !capabilities.canSaveExternalFile);

const replyClock = new ManualClock();
const replied = createRendererSaveGate(15_000, replyClock);
check('requested timeout is scheduled', replyClock.delayMs === 15_000);
check('first renderer response settles the gate', replied.complete(true));
check('successful renderer response resolves true', (await replied.result) === true);
check('renderer response cancels the timeout', replyClock.cleared === 1);
check('duplicate renderer response is ignored', !replied.complete(false));
replyClock.expire();
check('late timeout cannot replace renderer success', (await replied.result) === true);

const timeoutClock = new ManualClock();
const timedOut = createRendererSaveGate(15_000, timeoutClock);
timeoutClock.expire();
check('renderer silence resolves as save failure', (await timedOut.result) === false);
check('renderer silence is distinguishable from an explicit failure', (await timedOut.outcome) === 'timeout');
check('late renderer response after timeout is ignored', !timedOut.complete(true));

const synchronousTimeout = createRendererSaveGate(0, {
  setTimeout(callback) {
    callback();
    return Symbol('synchronous-timeout');
  },
  clearTimeout() {},
});
check('a synchronous custom watchdog still times out', (await synchronousTimeout.outcome) === 'timeout');

const retryClocks: ManualClock[] = [];
const retryRegistry = new RendererSaveRequestRegistry(15_000, {
  setTimeout(callback, delayMs) {
    const clock = new ManualClock();
    clock.setTimeout(callback, delayMs);
    retryClocks.push(clock);
    return clock;
  },
  clearTimeout(handle) {
    if (handle instanceof ManualClock) handle.clearTimeout(handle.handle);
  },
});
const attemptOne = retryRegistry.begin();
retryClocks[0]?.expire();
check('first correlated attempt times out', (await attemptOne.result) === false);
const attemptTwo = retryRegistry.begin();
check(
  'late reply from attempt one cannot resolve attempt two',
  !retryRegistry.complete(attemptOne.requestId, true),
);
let attemptTwoSettled = false;
void attemptTwo.result.then(() => { attemptTwoSettled = true; });
await Promise.resolve();
check('second attempt remains pending after stale reply', !attemptTwoSettled);
check('matching retry reply is accepted', retryRegistry.complete(attemptTwo.requestId, true));
check('matching retry result resolves true', (await attemptTwo.result) === true);

const overlapRegistry = new RendererSaveRequestRegistry(15_000);
const firstOverlappingRequest = overlapRegistry.begin();
let overlappingRequestRejected = false;
try {
  overlapRegistry.begin();
} catch (error) {
  overlappingRequestRejected = error instanceof Error
    && error.message.includes('already active');
}
check('a second active renderer request is rejected instead of replacing the first', overlappingRequestRejected);
check(
  'the rejected overlap leaves the original request completable',
  overlapRegistry.complete(firstOverlappingRequest.requestId, true),
);
check('the original request keeps its successful result', await firstOverlappingRequest.result);

const lostRendererRegistry = new RendererSaveRequestRegistry(15_000);
const lostRendererRequest = lostRendererRegistry.begin();
check('renderer loss releases its active close wait', lostRendererRegistry.failActive());
check('renderer loss resolves the active close wait as failed', !(await lostRendererRequest.result));
check('renderer loss is an explicit failure rather than a watchdog timeout', (await lostRendererRequest.outcome) === 'failure');
check('renderer loss release is idempotent', !lostRendererRegistry.failActive());

const dialogClocks: ManualClock[] = [];
const dialogRegistry = new RendererSaveRequestRegistry(15_000, {
  setTimeout(callback, delayMs) {
    const clock = new ManualClock();
    clock.setTimeout(callback, delayMs);
    dialogClocks.push(clock);
    return clock;
  },
  clearTimeout(handle) {
    if (handle instanceof ManualClock) handle.clearTimeout(handle.handle);
  },
});
dialogRegistry.suspendTimeouts();
const dialogRequest = dialogRegistry.begin();
dialogClocks[0]?.expire();
let dialogSettled = false;
void dialogRequest.result.then(() => { dialogSettled = true; });
await Promise.resolve();
check('a main-owned dialog pauses a newly-created close watchdog', !dialogSettled);
dialogRegistry.suspendTimeouts();
dialogRegistry.resumeTimeouts();
check('nested dialog suspension stays paused until the final release', !dialogSettled);
dialogRegistry.resumeTimeouts();
check('dialog completion re-arms a full close watchdog', dialogClocks.length === 2);
dialogClocks[1]?.expire();
check('re-armed watchdog still detects renderer silence', !(await dialogRequest.result));

console.log(`Renderer save gate tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} renderer save gate test(s) failed`);
console.log('RENDERER SAVE GATE TESTS: PASS');
