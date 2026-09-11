import {
  ApiRequestTimeoutError,
  createHttpApiClient,
  requestTimeoutMs,
} from "../src/adapters/httpApiClient";

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: boolean): void => {
  if (condition) passed += 1;
  else failures.push(label);
};

check("health uses its dedicated timeout", requestTimeoutMs("/api/health", "GET", { healthTimeoutMs: 7 }) === 7);
check("ordinary reads use the read timeout", requestTimeoutMs("/api/projects", "GET", { readTimeoutMs: 11 }) === 11);
check("ordinary writes use the write timeout", requestTimeoutMs("/api/projects", "POST", { writeTimeoutMs: 13 }) === 13);
check("writes are not aborted by default", requestTimeoutMs("/api/projects", "PATCH") === 0);
check("AI generation uses the long timeout", requestTimeoutMs("/api/projects/1/assistant/chat", "POST", { longRequestTimeoutMs: 17 }) === 17);
check("zero explicitly disables a timeout class", requestTimeoutMs("/api/projects", "GET", { readTimeoutMs: 0 }) === 0);

const originalFetch = globalThis.fetch;
const eventSourceDescriptor = Object.getOwnPropertyDescriptor(globalThis, "EventSource");

const pendingFetch: typeof fetch = (_input, init = {}) => new Promise<Response>((_resolve, reject) => {
  const signal = init.signal;
  if (!signal) { reject(new Error("request had no AbortSignal")); return; }
  const abort = () => reject(signal.reason ?? new Error("aborted"));
  if (signal.aborted) abort();
  else signal.addEventListener("abort", abort, { once: true });
});

try {
  globalThis.fetch = pendingFetch;
  const timed = createHttpApiClient("", "", { healthTimeoutMs: 8 });
  let timeoutError: unknown = null;
  try { await timed.health(); } catch (error) { timeoutError = error; }
  check("expired fetch becomes a structured timeout", timeoutError instanceof ApiRequestTimeoutError
    && timeoutError.method === "GET" && timeoutError.path === "/api/health" && timeoutError.timeoutMs === 8
    && timeoutError.outcomeUnknown === false);
  timed.dispose?.();

  const ambiguous = new ApiRequestTimeoutError("PATCH", "/api/projects/2", 20);
  check("opt-in write timeout declares an ambiguous outcome", ambiguous.outcomeUnknown && ambiguous.message.includes("refresh before retrying"));

  const disposable = createHttpApiClient("", "", { readTimeoutMs: 60_000 });
  const pending = disposable.listProjects();
  await Promise.resolve();
  disposable.dispose?.();
  disposable.dispose?.();
  let abortName = "";
  try { await pending; } catch (error) { abortName = error instanceof Error ? error.name : ""; }
  check("dispose aborts an in-flight fetch", abortName === "AbortError");
  let afterDisposeName = "";
  try { await disposable.health(); } catch (error) { afterDisposeName = error instanceof Error ? error.name : ""; }
  check("requests started after dispose fail as cancellations", afterDisposeName === "AbortError");

  let pollingSignal: AbortSignal | null = null;
  globalThis.fetch = (_input, init = {}) => {
    pollingSignal = init.signal ?? null;
    return pendingFetch(_input, init);
  };
  const polling = createHttpApiClient("", "session-token", { readTimeoutMs: 60_000 });
  const stopPolling = polling.subscribe(3, () => undefined);
  await Promise.resolve();
  stopPolling();
  await Promise.resolve();
  check("last polling unsubscribe aborts the active fetch", pollingSignal?.aborted === true);
  polling.dispose?.();

  let opened = 0;
  let closed = 0;
  class FakeEventSource {
    constructor(_url: string | URL) { opened += 1; }
    addEventListener(): void {}
    close(): void { closed += 1; }
  }
  Object.defineProperty(globalThis, "EventSource", { configurable: true, value: FakeEventSource });
  const streaming = createHttpApiClient();
  const unsubscribe = streaming.subscribe(4, () => undefined);
  check("first subscriber opens one SSE transport", opened === 1 && closed === 0);
  streaming.dispose?.();
  streaming.dispose?.();
  check("dispose closes SSE exactly once", closed === 1);
  unsubscribe();
  check("late unsubscribe after dispose is harmless", closed === 1);
  streaming.subscribe(4, () => undefined)();
  check("disposed client cannot reopen a transport", opened === 1);
} finally {
  globalThis.fetch = originalFetch;
  if (eventSourceDescriptor) Object.defineProperty(globalThis, "EventSource", eventSourceDescriptor);
  else delete (globalThis as { EventSource?: unknown }).EventSource;
}

console.log(`HTTP transport lifetime tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} HTTP transport lifetime test(s) failed`);
console.log("HTTP TRANSPORT LIFETIME TESTS: PASS");
