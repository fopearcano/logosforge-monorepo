import { createDeferredDisposer } from "../src/adapters/clientLifetime";

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: boolean): void => {
  if (condition) passed += 1;
  else failures.push(label);
};

const scheduled: Array<() => void> = [];
const disposed: string[] = [];
const disposer = createDeferredDisposer<{ id: string }>((value) => disposed.push(value.id), (task) => scheduled.push(task));
const flush = () => { while (scheduled.length) scheduled.shift()!(); };

const strictClient = { id: "strict" };
const firstRelease = disposer.acquire(strictClient);
firstRelease();
const secondRelease = disposer.acquire(strictClient);
flush();
check("StrictMode reacquire cancels deferred disposal", disposed.length === 0);
secondRelease();
flush();
check("client disposes after the genuine final release", disposed.join(",") === "strict");
secondRelease();
flush();
check("release is idempotent", disposed.join(",") === "strict");

const sharedClient = { id: "shared" };
const releaseA = disposer.acquire(sharedClient);
const releaseB = disposer.acquire(sharedClient);
releaseA();
flush();
check("one remaining lease keeps the client alive", !disposed.includes("shared"));
releaseB();
flush();
check("last of multiple leases disposes exactly once", disposed.filter((id) => id === "shared").length === 1);

const replacement = { id: "replacement" };
const releaseReplacement = disposer.acquire(replacement);
releaseReplacement();
flush();
check("independent clients have independent lifetime", disposed.includes("replacement"));

console.log(`Client lifetime tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} client lifetime test(s) failed`);
console.log("CLIENT LIFETIME TESTS: PASS");
