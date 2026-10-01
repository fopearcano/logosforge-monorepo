import type { InlineCommentDTO, NoteDTO, SceneDTO } from "@logosforge/ui-contracts";
import { MessagePort } from "node:worker_threads";
import { act, create, type ReactTestInstance, type ReactTestRenderer } from "react-test-renderer";
import type { ApiClient } from "../src/adapters/api";
import type { PlatformAdapter } from "../src/adapters/platform";
import { PendingProjectSaveError, flushPendingProjectSaves } from "../src/adapters/projectSaveCoordinator";
import { StudioProvider } from "../src/adapters/StudioProvider";
import { CommentsPanel } from "../src/components/manuscript/CommentsPanel";
import { COMMENT_VISIBILITY_STORAGE_KEY } from "../src/components/manuscript/commentPreferences";
import { NotesPanel } from "../src/components/manuscript/NotesPanel";

let assertions = 0;
function check(condition: unknown, message: string): asserts condition {
  assertions += 1;
  if (!condition) throw new Error(message);
}

interface Deferred<T> {
  promise: Promise<T>;
  resolve(value: T): void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((next) => { resolve = next; });
  return { promise, resolve };
}

const frames = new Map<number, FrameRequestCallback>();
let nextFrame = 1;
const storage = new Map<string, string>([[COMMENT_VISIBILITY_STORAGE_KEY, "1"]]);
const storageWrites: Array<readonly [string, string]> = [];
const mockDocument = { activeElement: null as unknown, querySelector: (_selector: string) => null as unknown };
const previousWindow = globalThis.window;
const previousDocument = globalThis.document;
(globalThis as unknown as { window: Window }).window = {
  requestAnimationFrame(callback: FrameRequestCallback) {
    const id = nextFrame++;
    frames.set(id, callback);
    return id;
  },
  cancelAnimationFrame(id: number) { frames.delete(id); },
  setInterval: (() => 1) as unknown as typeof window.setInterval,
  clearInterval: (() => undefined) as unknown as typeof window.clearInterval,
  setTimeout: globalThis.setTimeout as unknown as typeof window.setTimeout,
  clearTimeout: globalThis.clearTimeout as unknown as typeof window.clearTimeout,
  addEventListener() {},
  removeEventListener() {},
  dispatchEvent() { return true; },
  localStorage: {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => {
      storage.set(key, value);
      storageWrites.push([key, value]);
    },
  },
} as unknown as Window;
(globalThis as unknown as { document: Document }).document = mockDocument as unknown as Document;

function runFrames(): void {
  while (frames.size > 0) {
    const pending = [...frames.entries()];
    frames.clear();
    act(() => {
      for (const [, callback] of pending) callback(0);
    });
  }
}

function focusNode(label: string) {
  return {
    label,
    focus() { mockDocument.activeElement = this; },
    scrollIntoView() {},
  };
}

const noteTitleNode = focusNode("note-title");
const commentNodes = new Map<string, ReturnType<typeof focusNode>>();
const editBodyNode = focusNode("edit-comment-body");
mockDocument.querySelector = (selector: string) => (
  selector === '[data-note-editor-id="12"]' ? noteTitleNode : null
);

const createNodeMock = (element: { type: unknown; props: Record<string, unknown> }) => {
  if (element.type === "input" && element.props["data-note-editor-id"] === 12) return noteTitleNode;
  if (element.type === "textarea" && element.props["aria-label"] === "Edit comment body") return editBodyNode;
  if (element.type === "button" && typeof element.props["aria-label"] === "string") {
    const label = element.props["aria-label"];
    if (label.startsWith("Open comment on")) {
      const node = focusNode(label);
      commentNodes.set(label, node);
      return node;
    }
  }
  if (element.type === "button" || element.type === "input" || element.type === "textarea") {
    return focusNode(String(element.props["aria-label"] ?? element.type));
  }
  return {};
};

const targetNote: NoteDTO = {
  id: 12,
  title: "Target note",
  content: "Exact note body",
  tags: [],
  pinned: false,
  psyke_links: [],
  scene_links: [],
};
const notesRequest = deferred<NoteDTO[]>();
const api = {
  listNotes: () => notesRequest.promise,
  listComments: async () => comments,
  listScenes: async () => scenes,
  subscribe: () => () => {},
} as unknown as ApiClient;
const platform = { isDesktop: false } as PlatformAdapter;

let noteClears = 0;
let notesRenderer!: ReactTestRenderer;
act(() => {
  notesRenderer = create(
    <StudioProvider
      services={{ api, platform }}
      projectId={1}
      nav={{ noteTargetId: 12, clearNoteTarget: (id) => { if (id === 12) noteClears += 1; } }}
    >
      <NotesPanel />
    </StudioProvider>,
    { createNodeMock },
  );
});
check(notesRenderer.root.findAllByProps({ "aria-label": "Note title" }).length === 0, "note target must wait for its canonical list row");
await act(async () => {
  notesRequest.resolve([targetNote]);
  await notesRequest.promise;
  await Promise.resolve();
});
runFrames();
const noteTitle = notesRenderer.root.findByProps({ "aria-label": "Note title" });
check(noteTitle.props.value === targetNote.title, "note target should open the exact canonical note editor");
check(mockDocument.activeElement === noteTitleNode, "note target should focus its title field");
check(noteClears === 1, "note target should be consumed exactly once after focus");
act(() => { notesRenderer.unmount(); });

const scenes: SceneDTO[] = [{
  id: 1,
  title: "Opening",
  summary: "",
  synopsis: "",
  goal: "",
  conflict: "",
  outcome: "",
  beat: "",
  act: "",
  chapter: "",
  plotline: "",
  color_label: "",
  tags: [],
  content: "Opening line",
  sort_order: 0,
  order_index: 0,
  character_ids: [],
  place_ids: [],
  who_knows_what: "",
}];
const comments: InlineCommentDTO[] = [
  {
    id: 1,
    source_id: "",
    anchor: { start_scene_id: 1, start_field: "content", from_offset: 0, end_scene_id: 1, end_field: "content", to_offset: 4, prefix: "", suffix: "" },
    quote: "Open quote",
    body: "Open body",
    resolved: false,
    replies: [],
    created_at: "2026-01-01T00:00:00.000Z",
    updated_at: "2026-01-01T00:00:00.000Z",
    revision: "1".repeat(64),
  },
  {
    id: 2,
    source_id: "",
    anchor: { start_scene_id: 1, start_field: "title", from_offset: 0, end_scene_id: 1, end_field: "title", to_offset: 7, prefix: "", suffix: "" },
    quote: "Resolved quote",
    body: "Resolved body",
    resolved: true,
    replies: [],
    created_at: "2026-01-02T00:00:00.000Z",
    updated_at: "2026-01-02T00:00:00.000Z",
    revision: "2".repeat(64),
  },
];

let commentClears = 0;
let commentsRenderer!: ReactTestRenderer;
await act(async () => {
  commentsRenderer = create(
    <StudioProvider
      services={{ api, platform }}
      projectId={1}
      nav={{ commentTargetId: 2, clearCommentTarget: (id) => { if (id === 2) commentClears += 1; } }}
    >
      <CommentsPanel />
    </StudioProvider>,
    { createNodeMock },
  );
  await Promise.resolve();
  await Promise.resolve();
});
runFrames();
const openLabel = "Open comment on “Open quote”";
const resolvedLabel = "Open comment on “Resolved quote”";
const resolvedRow = commentsRenderer.root.findByProps({ "aria-label": resolvedLabel });
check(resolvedRow.props["aria-pressed"] === true, "resolved comment target should select the exact thread");
check(mockDocument.activeElement === commentNodes.get(resolvedLabel), "resolved comment target should receive row focus");
check(commentsRenderer.root.findByProps({ "aria-label": "Show open comments" }).props["aria-pressed"] === true, "target reveal must leave OPEN-only selected");
check(storage.get(COMMENT_VISIBILITY_STORAGE_KEY) === "1" && storageWrites.length === 0, "target reveal must not mutate the persisted comment filter");
check(commentClears === 1, "comment target should be consumed exactly once after focus");

act(() => { commentsRenderer.root.findByProps({ "aria-label": "Edit comment body" }).props.onClick(); });
const editBody = commentsRenderer.root.findByProps({ "aria-label": "Edit comment body" });
act(() => { editBody.props.onChange({ target: { value: "Unsaved changed body" } }); });
let blocked: unknown = null;
try {
  await flushPendingProjectSaves();
} catch (error) {
  blocked = error;
}
check(blocked instanceof PendingProjectSaveError, "dirty comment edit should block the global project handoff barrier");
act(() => { commentsRenderer.root.findByProps({ "aria-label": openLabel }).props.onClick(); });
runFrames();
check(commentsRenderer.root.findByProps({ "aria-label": resolvedLabel }).props["aria-pressed"] === true, "dirty comment edit should block an internal thread switch");
check(mockDocument.activeElement === editBodyNode, "blocked thread switch should restore focus to the dirty comment draft");
act(() => {
  commentsRenderer.root.findAllByType("button")
    .find((button: ReactTestInstance) => button.children.join("") === "CANCEL")?.props.onClick();
});
await flushPendingProjectSaves();
act(() => { commentsRenderer.unmount(); });

if (previousWindow === undefined) delete (globalThis as unknown as { window?: Window }).window;
else (globalThis as unknown as { window: Window }).window = previousWindow;
if (previousDocument === undefined) delete (globalThis as unknown as { document?: Document }).document;
else (globalThis as unknown as { document: Document }).document = previousDocument;

console.log(`${assertions} panel navigation target assertions passed.`);

// React's Node scheduler can retain unreferenced MessagePorts after this test's
// two renderer roots have been cleanly unmounted. They carry no pending work,
// so do not let those scheduler handles keep the standalone test process alive.
for (const handle of process._getActiveHandles()) {
  if (handle instanceof MessagePort) handle.unref();
}
