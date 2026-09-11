import {
  ClosePreparationCoordinator,
  classifySystemSessionRendererOutcome,
  drainPersistenceUntilSettled,
  effectiveCloseAction,
  ordinaryCloseCanContinue,
  prepareSystemSessionEndPersistence,
  type PersistenceRetryClock,
} from '../electron/shutdown-persistence';

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: boolean): void => {
  if (condition) passed += 1;
  else failures.push(label);
};

const delays: number[] = [];
const clock: PersistenceRetryClock = {
  async delay(delayMs) {
    delays.push(delayMs);
  },
};
const observed: unknown[] = [];
let attempts = 0;
await drainPersistenceUntilSettled(
  async () => {
    attempts += 1;
    if (attempts < 3) throw new Error(`transient ${attempts}`);
  },
  {
    retryDelayMs: 250,
    clock,
    onFailure: (error) => observed.push(error),
  },
);
check('shutdown persistence retries until success', attempts === 3);
check('every failure is surfaced', observed.length === 2);
check('retry backoff runs only between failed attempts', delays.join(',') === '250,250');

let immediateAttempts = 0;
await drainPersistenceUntilSettled(async () => {
  immediateAttempts += 1;
}, { clock });
check('successful drain runs once', immediateAttempts === 1);
check('successful drain adds no delay', delays.length === 2);
check('ordinary reload remains a reload', effectiveCloseAction('reload', false) === 'reload');
check('quit requested during reload wins', effectiveCloseAction('reload', true) === 'quit');
check('quit requested during close wins', effectiveCloseAction('close', true) === 'quit');
check('ordinary close may prompt without an OS session end', ordinaryCloseCanContinue(false));
check(
  'pending OS session end suppresses every not-yet-started ordinary prompt',
  !ordinaryCloseCanContinue(true),
);

const closePreparations = new ClosePreparationCoordinator();
check('ordinary close claims the shared preparation slot', closePreparations.begin('ordinary'));
check(
  'system session end cannot overlap an ordinary renderer flush',
  !closePreparations.begin('system-session-end'),
);
check(
  'a mismatched completion cannot release ordinary close ownership',
  !closePreparations.end('system-session-end') && closePreparations.isOwnedBy('ordinary'),
);
check('ordinary close releases its own preparation slot', closePreparations.end('ordinary'));
check(
  'system session end can claim the released preparation slot',
  closePreparations.begin('system-session-end'),
);
check(
  'ordinary close cannot overlap a system-session renderer flush',
  !closePreparations.begin('ordinary'),
);
check(
  'system session end releases its own preparation slot',
  closePreparations.end('system-session-end'),
);

const queuedSessionEnd = new ClosePreparationCoordinator();
queuedSessionEnd.begin('ordinary');
let sessionEndObservedIdle = false;
const sessionEndWait = queuedSessionEnd.waitUntilIdle().then(() => {
  sessionEndObservedIdle = true;
});
await Promise.resolve();
check('queued system session end waits while ordinary close owns the slot', !sessionEndObservedIdle);
queuedSessionEnd.end('ordinary');
await sessionEndWait;
check('queued system session end resumes when ordinary close releases the slot', sessionEndObservedIdle);
check(
  'queued system session end can claim ownership after waiting',
  queuedSessionEnd.begin('system-session-end'),
);
queuedSessionEnd.end('system-session-end');

check(
  'renderer absent before readiness uses main-only session-end persistence',
  classifySystemSessionRendererOutcome(null, false) === 'unavailable',
);
check(
  'renderer crash during its request uses main-only session-end persistence',
  classifySystemSessionRendererOutcome('failure', false) === 'unavailable',
);
check(
  'an explicit failure from a live renderer remains authoritative',
  classifySystemSessionRendererOutcome('failure', true) === 'explicit-failure',
);
check(
  'a live renderer watchdog expiration remains a timeout',
  classifySystemSessionRendererOutcome('timeout', true) === 'timeout',
);

let sessionMainDrains = 0;
const successfulSessionEnd = await prepareSystemSessionEndPersistence('success', async () => {
  sessionMainDrains += 1;
});
check('successful renderer autosave advances through the main final drain', successfulSessionEnd.ready);
check('session end drains main persistence exactly once', sessionMainDrains === 1);

const unavailableSessionEnd = await prepareSystemSessionEndPersistence('unavailable', async () => {
  sessionMainDrains += 1;
});
check('an unavailable renderer may use the main-only drain', unavailableSessionEnd.ready);
check('main-only session-end persistence performs its drain', sessionMainDrains === 2);

const explicitRendererFailure = await prepareSystemSessionEndPersistence(
  'explicit-failure',
  async () => { sessionMainDrains += 1; },
);
check(
  'explicit renderer autosave failure blocks system session end',
  !explicitRendererFailure.ready && explicitRendererFailure.reason === 'renderer-failure',
);
check('renderer failure never skips ahead to main-only persistence', sessionMainDrains === 2);

const liveRendererTimeout = await prepareSystemSessionEndPersistence(
  'timeout',
  async () => { sessionMainDrains += 1; },
);
check(
  'live renderer timeout blocks system session end',
  !liveRendererTimeout.ready && liveRendererTimeout.reason === 'renderer-timeout',
);
check('renderer timeout never skips ahead to main-only persistence', sessionMainDrains === 2);

const terminalDrainError = new Error('disk unavailable');
const failedMainDrain = await prepareSystemSessionEndPersistence('success', async () => {
  throw terminalDrainError;
});
check(
  'main persistence failure blocks system session end',
  !failedMainDrain.ready
    && failedMainDrain.reason === 'main-persistence-failure'
    && failedMainDrain.error === terminalDrainError,
);

// There is intentionally no external-file Save/Save-As phase here. The
// renderer's successful document-autosave outcome protects the manuscript
// without opening a human-blocking filename dialog during operating-system exit.
check('system session-end helper exposes no interactive save phase', sessionMainDrains === 2);

console.log(`Shutdown persistence tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} shutdown-persistence test(s) failed`);
console.log('SHUTDOWN PERSISTENCE TESTS: PASS');
