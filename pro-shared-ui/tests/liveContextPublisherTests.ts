import {
  LIVE_CONTEXT_SELECTION_LIMIT,
  LiveContextPublishController,
  normalizeLiveContextSnapshot,
  type LiveContextSnapshot,
} from "../src/status/liveContextPublisher";

let passed = 0;
let failed = 0;
function check(condition: unknown, message: string): void {
  if (condition) passed += 1;
  else { failed += 1; console.error(`FAIL: ${message}`); }
}

type Task = { id: number; callback: () => void; interval: boolean };
class FakeScheduler {
  private nextId = 1;
  readonly tasks = new Map<number, Task>();
  setTimeout(callback: () => void): number { return this.add(callback, false); }
  clearTimeout(handle: unknown): void { this.tasks.delete(handle as number); }
  setInterval(callback: () => void): number { return this.add(callback, true); }
  clearInterval(handle: unknown): void { this.tasks.delete(handle as number); }
  runTimeouts(): void {
    for (const task of [...this.tasks.values()]) {
      if (task.interval) continue;
      this.tasks.delete(task.id);
      task.callback();
    }
  }
  tickIntervals(): void {
    [...this.tasks.values()].filter((task) => task.interval).forEach((task) => task.callback());
  }
  private add(callback: () => void, interval: boolean): number {
    const id = this.nextId++;
    this.tasks.set(id, { id, callback, interval });
    return id;
  }
}

const snapshot = (patch: Partial<LiveContextSnapshot> = {}): LiveContextSnapshot => ({
  projectId: 7,
  activePanelId: "manuscript",
  activeSceneId: 11,
  selectionSection: "Manuscript",
  selection: "distinctive selection",
  ...patch,
});

{
  const normalized = normalizeLiveContextSnapshot(snapshot({
    activePanelId: `  ${"p".repeat(200)}  `,
    selectionSection: ` ${"s".repeat(200)} `,
    selection: "x".repeat(LIVE_CONTEXT_SELECTION_LIMIT + 5),
  }));
  check(normalized.activePanelId.length === 128, "panel labels are bounded");
  check(normalized.selectionSection.length === 128, "selection sections are bounded");
  check(normalized.selection.length === LIVE_CONTEXT_SELECTION_LIMIT, "selection text is bounded");
  const unicodeBoundary = normalizeLiveContextSnapshot(snapshot({
    selection: `${"x".repeat(LIVE_CONTEXT_SELECTION_LIMIT - 1)}😀`,
  })).selection;
  check(Array.from(unicodeBoundary).length === LIVE_CONTEXT_SELECTION_LIMIT && unicodeBoundary.endsWith("😀"),
    "selection truncation preserves a Unicode code point at the limit");
  check(normalizeLiveContextSnapshot(snapshot({ projectId: 0, activeSceneId: 4 })).projectId === null,
    "invalid project ids become an unavailable context");
}

{
  const scheduler = new FakeScheduler();
  const events: string[] = [];
  const controller = new LiveContextPublishController({
    publishLiveContext: (value) => { events.push(`publish:${value.projectId}:${value.selection}`); },
    clearLiveContext: () => { events.push("clear"); },
  }, { scheduler });

  controller.update(snapshot({ selection: "first" }));
  controller.update(snapshot({ selection: "second" }));
  check(events.length === 0, "rapid renderer updates are debounced");
  scheduler.runTimeouts();
  check(events.join("|") === "publish:7:second", "the latest debounced context is published");

  scheduler.tickIntervals();
  check(events.at(-1) === "publish:7:second", "heartbeat republishes the current context");

  controller.update(snapshot({ projectId: 8, activeSceneId: null, selection: "new project" }));
  check(events.at(-1) === "clear", "project switches clear the previous context first");
  scheduler.runTimeouts();
  check(events.at(-1) === "publish:8:new project", "the new project publishes after the ordered clear");

  controller.update(snapshot({ projectId: null }));
  check(events.at(-1) === "clear", "closing a project clears live context");
  const beforeHeartbeat = events.length;
  scheduler.tickIntervals();
  check(events.length === beforeHeartbeat, "heartbeats do not resurrect a cleared context");

  controller.dispose();
  check(events.at(-1) === "clear", "disposing the publisher clears context");
  const afterDispose = events.length;
  scheduler.runTimeouts();
  scheduler.tickIntervals();
  check(events.length === afterDispose, "disposed publishers schedule no further work");
}

console.log(`Live-context publisher tests: ${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
