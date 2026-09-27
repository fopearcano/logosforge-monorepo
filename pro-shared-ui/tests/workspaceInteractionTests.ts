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
const runScheduled = () => {
  while (scheduled.length > 0) scheduled.shift()?.();
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
  const formerlyColliding = ["plugin.alpha", "plugin/alpha", "plugin:alpha", "plugin alpha"];
  const tokens = formerlyColliding.map(workspacePanelDomToken);
  check("panel DOM tokens are injective for allowed punctuation", new Set(tokens).size === tokens.length);
  check("panel DOM tokens are selector-safe", tokens.every((token) => /^[0-9a-f]+$/.test(token)));
}

console.log(`Workspace interaction tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} workspace interaction test(s) failed`);
