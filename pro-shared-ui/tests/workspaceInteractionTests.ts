import {
  focusAfterWorkspaceAction,
  workspacePanelDomToken,
  type WorkspaceFocusScheduler,
} from "../src/components/shell/workspaceInteraction";

let passed = 0;
const failures: string[] = [];

function check(label: string, condition: boolean): void {
  if (condition) passed += 1;
  else failures.push(label);
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

async function settle(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}

const scheduled: Array<() => void> = [];
const schedule: WorkspaceFocusScheduler = (work) => { scheduled.push(work); };
const runNextScheduled = () => { scheduled.shift()?.(); };
const runScheduled = () => {
  while (scheduled.length > 0) runNextScheduled();
};

{
  let selectedFocuses = 0;
  let previousFocuses = 0;
  const activation = deferred<void | boolean>();
  focusAfterWorkspaceAction(
    activation.promise,
    () => ({ focus: () => { selectedFocuses += 1; } }),
    () => ({ focus: () => { previousFocuses += 1; } }),
    schedule,
  );
  check("pending activation does not move focus early", scheduled.length === 0);
  activation.resolve(true);
  await settle();
  runScheduled();
  check("successful activation focuses the selected tab", selectedFocuses === 1 && previousFocuses === 0);
}

{
  let selectedFocuses = 0;
  let previousFocuses = 0;
  focusAfterWorkspaceAction(
    Promise.resolve(false),
    () => ({ focus: () => { selectedFocuses += 1; } }),
    () => ({ focus: () => { previousFocuses += 1; } }),
    schedule,
  );
  await settle();
  runScheduled();
  check("declined activation restores the selected tab", selectedFocuses === 0 && previousFocuses === 1);
}

{
  let previousFocuses = 0;
  focusAfterWorkspaceAction(
    Promise.reject(new Error("save barrier failed")),
    () => ({ focus: () => undefined }),
    () => ({ focus: () => { previousFocuses += 1; } }),
    schedule,
  );
  await settle();
  runScheduled();
  check("rejected activation restores the selected tab", previousFocuses === 1);
}

{
  let targetQueries = 0;
  let targetFocuses = 0;
  focusAfterWorkspaceAction(
    Promise.resolve(true),
    () => {
      targetQueries += 1;
      return targetQueries === 1
        ? null
        : { focus: () => { targetFocuses += 1; } };
    },
    undefined,
    schedule,
  );
  await settle();
  runNextScheduled();
  check(
    targetFocuses === 0 && scheduled.length === 1,
    "conditional workspace target is retried after the first render frame",
  );
  runNextScheduled();
  check(
    targetQueries === 2 && targetFocuses === 1 && scheduled.length === 0,
    "conditional workspace target receives focus after it mounts",
  );
}

{
  const ownerDocument: { activeElement: unknown } = { activeElement: null };
  let ready = false;
  let focusAttempts = 0;
  const candidate = {
    ownerDocument,
    isConnected: true,
    focus: () => {
      focusAttempts += 1;
      if (ready) ownerDocument.activeElement = candidate;
    },
  };
  focusAfterWorkspaceAction(Promise.resolve(true), () => candidate, undefined, schedule);
  await settle();
  runNextScheduled();
  check(
    focusAttempts === 1 && scheduled.length === 1,
    "workspace focus retries when a mounted target cannot receive focus yet",
  );
  ready = true;
  runNextScheduled();
  check(
    focusAttempts === 2 && ownerDocument.activeElement === candidate && scheduled.length === 0,
    "workspace focus stops retrying once the target owns DOM focus",
  );
}

{
  let targetQueries = 0;
  focusAfterWorkspaceAction(
    Promise.resolve(true),
    () => { targetQueries += 1; return null; },
    undefined,
    schedule,
  );
  await settle();
  runScheduled();
  check(
    targetQueries === 3 && scheduled.length === 0,
    "missing workspace focus targets use a bounded number of render retries",
  );
}

{
  const formerlyColliding = ["plugin.alpha", "plugin/alpha", "plugin:alpha", "plugin alpha"];
  const tokens = formerlyColliding.map(workspacePanelDomToken);
  check("panel DOM tokens are injective for allowed punctuation", new Set(tokens).size === tokens.length);
  check("panel DOM tokens are selector-safe", tokens.every((token) => /^[0-9a-f]+$/.test(token)));
}

console.log(`Workspace interaction tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} workspace interaction test(s) failed`);
