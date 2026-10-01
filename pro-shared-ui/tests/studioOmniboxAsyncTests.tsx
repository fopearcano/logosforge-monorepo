import type {
  ProjectSearchKind,
  ProjectSearchMatchDTO,
  ProjectSearchResponseDTO,
} from "@logosforge/ui-contracts";
import { act, create, type ReactTestInstance, type ReactTestRenderer } from "react-test-renderer";
import type { ApiClient } from "../src/adapters/api";
import type { PlatformAdapter } from "../src/adapters/platform";
import { StudioProvider } from "../src/adapters/StudioProvider";
import { createCommandRegistry } from "../src/commands";
import { StudioOmnibox } from "../src/components/shell/StudioOmnibox";

let assertions = 0;
function check(condition: unknown, message: string): asserts condition {
  assertions += 1;
  if (!condition) throw new Error(message);
}

interface Deferred<T> {
  readonly promise: Promise<T>;
  resolve(value: T): void;
  reject(reason: unknown): void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

class DeterministicTimers {
  private nextId = 1;
  private readonly callbacks = new Map<number, () => void>();

  readonly setTimeout = (handler: TimerHandler): number => {
    if (typeof handler !== "function") throw new Error("Test timers only accept callbacks.");
    const id = this.nextId++;
    this.callbacks.set(id, handler);
    return id;
  };

  readonly clearTimeout = (id?: number): void => {
    if (id != null) this.callbacks.delete(id);
  };

  runAll(): void {
    while (this.callbacks.size > 0) {
      const pending = [...this.callbacks.entries()];
      this.callbacks.clear();
      for (const [, callback] of pending) callback();
    }
  }

  get size(): number {
    return this.callbacks.size;
  }
}

interface SearchCall extends Deferred<ProjectSearchResponseDTO> {
  readonly projectId: number;
  readonly query: string;
  readonly kinds: readonly ProjectSearchKind[] | undefined;
  readonly signal: AbortSignal | undefined;
}

const timers = new DeterministicTimers();
const previousWindow = globalThis.window;
(globalThis as unknown as { window: Window }).window = {
  setTimeout: timers.setTimeout,
  clearTimeout: timers.clearTimeout,
  requestAnimationFrame: (callback: FrameRequestCallback) => timers.setTimeout(() => callback(0)),
  cancelAnimationFrame: timers.clearTimeout,
} as unknown as Window;

const searchCalls: SearchCall[] = [];
const api = {
  searchProject(
    projectId: number,
    query: string,
    kinds?: readonly ProjectSearchKind[],
    signal?: AbortSignal,
  ): Promise<ProjectSearchResponseDTO> {
    const pending = deferred<ProjectSearchResponseDTO>();
    searchCalls.push({ projectId, query, kinds, signal, ...pending });
    // Deliberately ignore abort here. A transport is allowed to settle after
    // cancellation; the component still must reject stale publications.
    return pending.promise;
  },
} as unknown as ApiClient;

const platform = { isDesktop: false } as PlatformAdapter;
const registry = createCommandRegistry([]);
let projectId = 1;
let open = true;
let closeCalls = 0;

function renderOmnibox() {
  return (
    <StudioProvider services={{ api, platform }} projectId={projectId}>
      <StudioOmnibox
        open={open}
        onClose={() => { closeCalls += 1; }}
        registry={registry}
        panels={[]}
        projects={[]}
        onNavigate={async () => true}
        onSelectProject={async () => true}
      />
    </StudioProvider>
  );
}

function input(renderer: ReactTestRenderer): ReactTestInstance {
  return renderer.root.findByProps({ "aria-label": "Search the current project" });
}

function renderedText(renderer: ReactTestRenderer): string {
  const collect = (value: ReturnType<ReactTestRenderer["toJSON"]>): string => {
    if (value == null) return "";
    if (Array.isArray(value)) return value.map(collect).join(" ");
    return value.children?.map((child) => typeof child === "string" ? child : collect(child)).join(" ") ?? "";
  };
  return collect(renderer.toJSON());
}

function response(query: string, ...matches: ProjectSearchMatchDTO[]): ProjectSearchResponseDTO {
  return { query, matches, limit: 100 };
}

function scene(id: number, title: string): ProjectSearchMatchDTO {
  return { kind: "scene", id, title, excerpt: `${title} excerpt` };
}

function note(id: number, title: string): ProjectSearchMatchDTO {
  return { kind: "note", id, title, excerpt: `${title} excerpt` };
}

function comment(id: number, title: string, resolved = false): ProjectSearchMatchDTO {
  return {
    kind: "comment",
    id,
    title,
    excerpt: `${title} excerpt`,
    revision: String(id).padStart(64, "0"),
    resolved,
  };
}

function changeQuery(renderer: ReactTestRenderer, query: string, runDebounce = true): void {
  act(() => {
    input(renderer).props.onChange({ target: { value: query } });
  });
  if (runDebounce) act(() => { timers.runAll(); });
}

async function settle(run: () => void): Promise<void> {
  act(run);
  await Promise.resolve();
  await Promise.resolve();
  act(() => undefined);
}

let renderer!: ReactTestRenderer;
act(() => { renderer = create(renderOmnibox()); });
check(input(renderer).props.maxLength === 500, "search input should enforce the API query-length limit");

changeQuery(renderer, "alpha");
check(searchCalls.length === 1, "first query should issue one debounced search");
check(searchCalls[0]!.projectId === 1 && searchCalls[0]!.query === "alpha", "search should own its project and normalized query");
check(searchCalls[0]!.kinds?.join(",") === "scene,note,psyke,comment", "omnibox should request every navigable result kind");
check(renderedText(renderer).includes("SEARCHING PROJECT"), "pending search should publish a loading state");

changeQuery(renderer, "beta");
check(searchCalls[0]!.signal?.aborted === true, "changing the query should abort the prior request");
check(searchCalls.length === 2 && searchCalls[1]!.query === "beta", "replacement query should issue a new search");

await settle(() => searchCalls[1]!.resolve(response("beta", comment(202, "Beta current comment", true))));
check(renderedText(renderer).includes("Beta current comment"), "latest query response should render an actionable comment result");
check(!renderedText(renderer).includes("SEARCHING PROJECT"), "latest query response should clear loading");

await settle(() => searchCalls[0]!.resolve(response("alpha", note(101, "Alpha stale note"))));
check(renderedText(renderer).includes("Beta current comment"), "late prior-query response must not replace current results");
changeQuery(renderer, "alpha", false);
check(!renderedText(renderer).includes("Alpha stale note"), "late prior-query note response must not be cached for a later identical query");

changeQuery(renderer, "gamma");
check(searchCalls.length === 3, "project-change case should begin with a live search");
check(searchCalls[2]!.projectId === 1, "live search should belong to the original project");

projectId = 2;
act(() => { renderer.update(renderOmnibox()); });
check(searchCalls[2]!.signal?.aborted === true, "changing projects should abort the old project's request");
act(() => { timers.runAll(); });
check(searchCalls.length === 4 && searchCalls[3]!.projectId === 2, "same query should be reissued for the new project");

await settle(() => searchCalls[3]!.resolve(response("gamma", note(402, "Gamma project two note"))));
check(renderedText(renderer).includes("Gamma project two note"), "new-project note response should render");
await settle(() => searchCalls[2]!.resolve(response("gamma", comment(301, "Gamma stale project one comment"))));
check(renderedText(renderer).includes("Gamma project two note"), "late old-project comment response must not replace new-project results");

projectId = 1;
act(() => { renderer.update(renderOmnibox()); });
check(!renderedText(renderer).includes("Gamma stale project one comment"), "late old-project comment response must not be cached for a later project switch");

changeQuery(renderer, "closing");
check(searchCalls.length === 5 && searchCalls[4]!.query === "closing", "close case should have one in-flight search");
const modalLayer = renderer.root.findByProps({ "data-lf-modal-layer": true });
const backdrop = {};
act(() => { modalLayer.props.onMouseDown({ target: backdrop, currentTarget: backdrop }); });
check(closeCalls === 1, "backdrop close should notify the host exactly once");
check(searchCalls[4]!.signal?.aborted === true, "closing the omnibox should abort its active request immediately");

open = false;
act(() => { renderer.update(renderOmnibox()); });
check(renderer.root.findAllByProps({ "aria-label": "Studio omnibox" }).length === 0, "closed omnibox should render no dialog");
await settle(() => searchCalls[4]!.reject(new Error("late transport failure")));

open = true;
act(() => { renderer.update(renderOmnibox()); });
check(input(renderer).props.value === "", "reopened omnibox should reset its query");
check(!renderedText(renderer).includes("Project search failed"), "late close-time rejection must not surface an error after reopening");
check(!renderedText(renderer).includes("SEARCHING PROJECT"), "reopened omnibox must not retain a stale loading state");
check(timers.size === 0, "close/reopen should leave no stale debounce timer");

act(() => { renderer.unmount(); });
if (previousWindow === undefined) delete (globalThis as unknown as { window?: Window }).window;
else (globalThis as unknown as { window: Window }).window = previousWindow;

console.log(`${assertions} Studio omnibox async lifecycle assertions passed.`);
