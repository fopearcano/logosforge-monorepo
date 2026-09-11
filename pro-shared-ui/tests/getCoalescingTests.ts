import { createHttpApiClient } from "../src/adapters/httpApiClient";

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: boolean): void => {
  if (condition) passed += 1;
  else failures.push(label);
};

interface PendingCall {
  url: string;
  method: string;
  resolve: (response: Response) => void;
  reject: (error: unknown) => void;
}

const originalFetch = globalThis.fetch;
let calls: PendingCall[] = [];
const installPendingFetch = () => {
  calls = [];
  globalThis.fetch = (input, init = {}) => new Promise<Response>((resolve, reject) => {
    calls.push({ url: String(input), method: init.method ?? "GET", resolve, reject });
  });
};
const json = (value: unknown) => new Response(JSON.stringify(value), {
  status: 200,
  headers: { "content-type": "application/json" },
});

try {
  installPendingFetch();
  const client = createHttpApiClient("", "", { healthTimeoutMs: 0, readTimeoutMs: 0 });
  const first = client.health();
  const second = client.health();
  check("simultaneous identical GETs share one fetch", calls.length === 1);
  calls[0]!.resolve(json({ status: "ok", nested: { value: 1 } }));
  const [firstValue, secondValue] = await Promise.all([first, second]) as unknown as Array<{ nested: { value: number } }>;
  check("every coalesced caller receives the response", firstValue.nested.value === 1 && secondValue.nested.value === 1);
  check("coalesced callers receive distinct object graphs", firstValue !== secondValue && firstValue.nested !== secondValue.nested);
  firstValue.nested.value = 9;
  check("one caller cannot mutate another caller's value", secondValue.nested.value === 1);

  const afterSettle = client.health();
  check("settled GET is not cached", calls.length === 2);
  calls[1]!.resolve(json({ status: "fresh" }));
  await afterSettle;

  installPendingFetch();
  const health = client.health();
  const modes = client.writingModes();
  check("different paths never coalesce", calls.length === 2);
  calls[0]!.resolve(json({ status: "ok" }));
  calls[1]!.resolve(json({ modes: [] }));
  await Promise.all([health, modes]);

  installPendingFetch();
  const rejectedA = client.health().catch(() => undefined);
  const rejectedB = client.health().catch(() => undefined);
  check("concurrent rejection is still coalesced", calls.length === 1);
  calls[0]!.reject(new Error("offline"));
  await Promise.all([rejectedA, rejectedB]);
  const retry = client.health();
  check("rejected GET is evicted for retry", calls.length === 2);
  calls[1]!.resolve(json({ status: "recovered" }));
  await retry;

  installPendingFetch();
  const staleRead = client.listProjects();
  const mutation = client.createProject({ title: "Created", narrative_engine: "novel" });
  const postMutationRead = client.listProjects();
  check("starting a mutation prevents reuse of an older GET", calls.length === 3 && calls[1]!.method === "POST");
  calls[0]!.resolve(json([]));
  calls[1]!.resolve(json({ id: 1, title: "Created" }));
  calls[2]!.resolve(json([{ id: 1, title: "Created" }]));
  await Promise.all([staleRead, mutation, postMutationRead]);

  installPendingFetch();
  const mutation2 = client.createProject({ title: "Second", narrative_engine: "novel" });
  const duringMutation = client.listProjects();
  calls[0]!.resolve(json({ id: 2, title: "Second" }));
  await mutation2;
  const afterMutation = client.listProjects();
  check("mutation settlement evicts GETs started before commit", calls.length === 3);
  calls[1]!.resolve(json([{ id: 1, title: "Created" }]));
  calls[2]!.resolve(json([{ id: 1, title: "Created" }, { id: 2, title: "Second" }]));
  await Promise.all([duringMutation, afterMutation]);
  client.dispose?.();
} finally {
  globalThis.fetch = originalFetch;
}

console.log(`GET coalescing tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} GET coalescing test(s) failed`);
console.log("GET COALESCING TESTS: PASS");
