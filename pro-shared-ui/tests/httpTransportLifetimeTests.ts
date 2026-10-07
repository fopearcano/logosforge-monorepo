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

  // Polling has no native EventSource reconnect signal. The broker-instance
  // token and interrupted-request state must therefore create explicit
  // reconciliation boundaries while preserving ordinary incremental events.
  const realSetTimeout = globalThis.setTimeout;
  const realClearTimeout = globalThis.clearTimeout;
  let scheduledPoll: (() => void) | null = null;
  try {
    globalThis.setTimeout = ((handler: (...args: unknown[]) => void, _delay?: number, ...args: unknown[]) => {
      scheduledPoll = () => handler(...args);
      return 1 as unknown as ReturnType<typeof setTimeout>;
    }) as typeof setTimeout;
    globalThis.clearTimeout = (() => { scheduledPoll = null; }) as typeof clearTimeout;

    const pollResponses: Array<Record<string, unknown> | Error> = [
      {
        events: [{ id: 5, event: "timeline_changed", project_id: 5, data: {}, ts: 1 }],
        cursor: 5,
        broker_instance_id: "broker-a",
        reset_required: false,
        known_events: ["timeline_changed", "canvas_plot_changed"],
      },
      {
        events: [{ id: 6, event: "timeline_changed", project_id: 5, data: {}, ts: 2 }],
        cursor: 6,
        broker_instance_id: "broker-a",
        reset_required: false,
        known_events: ["timeline_changed", "canvas_plot_changed"],
      },
      new Error("temporary poll failure"),
      {
        events: [{ id: 7, event: "canvas_plot_changed", project_id: 5, data: {}, ts: 3 }],
        cursor: 7,
        broker_instance_id: "broker-a",
        reset_required: false,
        known_events: ["timeline_changed", "canvas_plot_changed"],
      },
      {
        events: [],
        cursor: 2508,
        broker_instance_id: "broker-a",
        reset_required: true,
        known_events: ["timeline_changed", "canvas_plot_changed"],
      },
      {
        events: [{ id: 1, event: "timeline_changed", project_id: 5, data: {}, ts: 4 }],
        cursor: 1,
        broker_instance_id: "broker-b",
        reset_required: false,
        known_events: ["timeline_changed", "canvas_plot_changed"],
      },
    ];
    const pollUrls: string[] = [];
    globalThis.fetch = async (input) => {
      pollUrls.push(String(input));
      const next = pollResponses.shift();
      if (next instanceof Error) throw next;
      if (!next) throw new Error("unexpected extra polling request");
      return new Response(JSON.stringify(next), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    };
    const flushPolling = async () => {
      for (let index = 0; index < 12; index += 1) await Promise.resolve();
    };
    const runScheduledPoll = async () => {
      const callback = scheduledPoll;
      scheduledPoll = null;
      if (callback == null) throw new Error("polling did not schedule its next tick");
      callback();
      await flushPolling();
    };

    const observedEvents: string[] = [];
    const reconciled = createHttpApiClient("", "session-token", { readTimeoutMs: 0 });
    const stopReconciled = reconciled.subscribe(5, (event) => { observedEvents.push(event.event); });
    await flushPolling();
    check(
      "initial poll dispatches connected and does not replay pre-subscription history",
      observedEvents.join(",") === "connected" && pollUrls[0] === "/api/projects/5/events/poll?since=0",
    );

    await runScheduledPoll();
    check(
      "same-broker polling dispatches only newer domain events",
      observedEvents.join(",") === "connected,timeline_changed",
    );

    await runScheduledPoll(); // rejected request: no dispatch, but marks recovery pending
    await runScheduledPoll();
    check(
      "poll recovery reconciles before dispatching retained incremental events",
      observedEvents.join(",") === "connected,timeline_changed,connected,canvas_plot_changed",
    );

    await runScheduledPoll();
    check(
      "same-broker ring truncation forces authoritative reconciliation",
      observedEvents.join(",") === "connected,timeline_changed,connected,canvas_plot_changed,connected",
    );

    await runScheduledPoll();
    check(
      "broker replacement reconciles and rejects the previous generation's cursor semantics",
      observedEvents.join(",") === "connected,timeline_changed,connected,canvas_plot_changed,connected,connected",
    );
    stopReconciled();
    reconciled.dispose?.();
  } finally {
    globalThis.setTimeout = realSetTimeout;
    globalThis.clearTimeout = realClearTimeout;
  }

  let opened = 0;
  let closed = 0;
  let latestEventSource: FakeEventSource | null = null;
  class FakeEventSource {
    private readonly listeners = new Map<string, EventListener[]>();
    constructor(_url: string | URL) { opened += 1; latestEventSource = this; }
    addEventListener(name: string, listener: EventListener): void {
      this.listeners.set(name, [...(this.listeners.get(name) ?? []), listener]);
    }
    emit(name: string, payload: unknown): void {
      const message = { data: JSON.stringify(payload) } as MessageEvent;
      for (const listener of this.listeners.get(name) ?? []) listener(message);
    }
    close(): void { closed += 1; }
  }
  Object.defineProperty(globalThis, "EventSource", { configurable: true, value: FakeEventSource });
  const streaming = createHttpApiClient();
  const streamingEvents: string[] = [];
  const unsubscribe = streaming.subscribe(4, (event) => { streamingEvents.push(event.event); });
  check("first subscriber opens one SSE transport", opened === 1 && closed === 0);
  latestEventSource?.emit("connected", {
    id: 0, event: "connected", project_id: 4, data: { broker_instance_id: "broker-sse" }, ts: 1,
  });
  check("SSE connected events reach subscribers as reconciliation boundaries", streamingEvents.join(",") === "connected");

  const readResolvers: Array<(response: Response) => void> = [];
  globalThis.fetch = async () => new Promise<Response>((resolve) => { readResolvers.push(resolve); });
  const staleRead = streaming.getAdapt(4);
  await Promise.resolve();
  latestEventSource?.emit("connected", {
    id: 0, event: "connected", project_id: 4, data: { broker_instance_id: "broker-sse" }, ts: 2,
  });
  const freshRead = streaming.getAdapt(4);
  await Promise.resolve();
  check("live invalidation prevents post-boundary GET from joining a stale in-flight read", readResolvers.length === 2);
  readResolvers[1]?.(new Response(JSON.stringify({ generation: "fresh" }), {
    status: 200, headers: { "content-type": "application/json" },
  }));
  check("post-boundary GET receives the fresh response", (await freshRead as unknown as { generation: string }).generation === "fresh");
  readResolvers[0]?.(new Response(JSON.stringify({ generation: "stale" }), {
    status: 200, headers: { "content-type": "application/json" },
  }));
  check("pre-boundary GET remains isolated", (await staleRead as unknown as { generation: string }).generation === "stale");

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
