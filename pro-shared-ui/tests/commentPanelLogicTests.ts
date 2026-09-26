import type { AssistantResponseDTO, InlineCommentDTO, SceneDTO } from "@logosforge/ui-contracts";
import {
  buildCommentAssistantPrompt,
  buildCommentThreadContext,
  detectCommentAssistantMention,
  persistCommentAssistantReply,
  type CommentAssistantReplyApi,
} from "../src/components/manuscript/commentAssistant";
import {
  COMMENT_VISIBILITY_STORAGE_KEY,
  readHideResolvedPreference,
  writeHideResolvedPreference,
} from "../src/components/manuscript/commentPreferences";
import {
  buildCommentReport,
  commentReportFilename,
  formatRelativeTime,
  isImportedSource,
} from "../src/components/manuscript/commentPresentation";
import { flushPendingProjectSaves } from "../src/adapters/projectSaveCoordinator";

let passed = 0;
function check(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
  passed += 1;
}

check(detectCommentAssistantMention("Please ask @assistant about this") === "assistant", "detects @assistant");
check(detectCommentAssistantMention("@Counterpart challenge this beat") === "counterpart", "detects @counterpart case-insensitively");
check(detectCommentAssistantMention("Could you (@assistant) test the turn?") === "assistant", "detects a mention after punctuation");
check(detectCommentAssistantMention("email@assistant.example") === null, "does not match handles inside an address");
check(detectCommentAssistantMention("email-@assistant.example") === null, "does not match handles after email punctuation");
check(detectCommentAssistantMention("@billy review this") === null, "does not inherit Whiteboard persona handles");
check(buildCommentAssistantPrompt("assistant", "@assistant help").includes("Pro Assistant"), "assistant prompt uses a Pro-owned label");

const comment: InlineCommentDTO = {
  id: 7,
  source_id: "whiteboard-thread-7",
  anchor: {
    start_scene_id: 12,
    start_field: "content",
    from_offset: 4,
    end_scene_id: 12,
    end_field: "content",
    to_offset: 11,
    prefix: "before ",
    suffix: " after",
  },
  quote: "the line",
  body: "Sharpen this turn.",
  resolved: false,
  replies: [{
    id: 8,
    source_id: "whiteboard-reply-8",
    body: "Try silence first.",
    author: "Imported reviewer",
    sort_order: 0,
    created_at: "2026-01-02T03:04:05.000Z",
  }],
  created_at: "2026-01-02T03:00:00.000Z",
  updated_at: "2026-01-02T03:04:05.000Z",
  revision: "a".repeat(64),
};
const scene = { id: 12, title: "Turning Point" } as SceneDTO;
const report = buildCommentReport([comment], new Map([[scene.id, scene]]), new Date("2026-02-03T04:05:06.000Z"));
check(report.includes("# LogosForge comment report"), "report has a portable Markdown heading");
check(report.includes("Threads: 1 (1 open, 0 resolved)"), "report summarizes thread status");
check(report.includes("> the line"), "report includes quoted manuscript text");
check(report.includes("Imported (whiteboard-thread-7)"), "report preserves root provenance");
check(report.includes("imported (whiteboard-reply-8)"), "report preserves reply provenance");
check(report.includes("**Imported reviewer**"), "report includes reply authorship");
check(buildCommentThreadContext(comment, "@assistant help").includes("Writer's new reply: @assistant help"), "assistant context includes the new reply");

let resolveProvider: ((response: AssistantResponseDTO) => void) | undefined;
const providerReply = new Promise<AssistantResponseDTO>((resolve) => { resolveProvider = resolve; });
let resolveReplyWrite: (() => void) | undefined;
const replyWrite = new Promise<void>((resolve) => { resolveReplyWrite = resolve; });
const replyWrites: Array<{ projectId: number; commentId: number; author: string; body: string }> = [];
const lifecycleApi: CommentAssistantReplyApi = {
  async assistantChat() { return providerReply; },
  async runCounterpart() { throw new Error("unexpected counterpart request"); },
  async createCommentReply(projectId, commentId, body) {
    replyWrites.push({ projectId, commentId, author: body.author ?? "", body: body.body ?? "" });
    await replyWrite;
    return comment;
  },
};
let visibleProjectId = 1;
const pendingAssistantReply = persistCommentAssistantReply(lifecycleApi, 1, comment, "@assistant help", "assistant");
// Simulate the panel unmounting or switching projects while the provider runs.
visibleProjectId = 2;
let handoffDrained = false;
const handoff = flushPendingProjectSaves().then(() => { handoffDrained = true; });
await Promise.resolve();
check(!handoffDrained, "project handoff waits while the assistant provider request is still running");
resolveProvider!({ reply: "  Keep the silence, then break it.  ", cached: false });
while (replyWrites.length === 0) await Promise.resolve();
await Promise.resolve();
check(!handoffDrained, "project handoff waits for a lifecycle-independent assistant reply write");
resolveReplyWrite!();
const [persistedAssistantReply] = await Promise.all([pendingAssistantReply, handoff]);
check(handoffDrained, "project handoff resumes after the assistant reply is persisted");
check(visibleProjectId === 2, "regression setup switches the visible project while the provider is running");
check(replyWrites.length === 1 && replyWrites[0]?.projectId === 1 && replyWrites[0]?.commentId === comment.id,
  "assistant reply persists to captured project and thread after panel lifetime changes");
check(replyWrites[0]?.body === "Keep the silence, then break it." && persistedAssistantReply.author === "Assistant",
  "persisted assistant reply is normalized and attributed");

check(commentReportFilename(42) === "logosforge-comments-42.md", "report filename is project-scoped");
check(isImportedSource(" source-id ") && !isImportedSource("  "), "source ids distinguish imported records");

const now = Date.parse("2026-01-02T04:00:00.000Z");
check(formatRelativeTime("2026-01-02T03:58:00.000Z", now) === "2 minutes ago", "relative past minutes are readable");
check(formatRelativeTime("2026-01-02T05:00:00.000Z", now) === "in 1 hour", "relative future hours are readable");
check(formatRelativeTime("not-a-date", now) === "Unknown time", "invalid timestamps degrade safely");

check(readHideResolvedPreference({ getItem: () => "1" }), "stored hide-resolved value is read");
check(!readHideResolvedPreference({ getItem: () => { throw new Error("blocked"); } }), "blocked storage reads fall back safely");
let writtenKey = "";
let writtenValue = "";
writeHideResolvedPreference(false, { setItem: (key, value) => { writtenKey = key; writtenValue = value; } });
check(writtenKey === COMMENT_VISIBILITY_STORAGE_KEY && writtenValue === "0", "preference writes use the shared stable key");
writeHideResolvedPreference(true, { setItem: () => { throw new Error("blocked"); } });
check(true, "blocked storage writes do not escape");

console.log(`Comment panel logic tests: ${passed} passed, 0 failed`);
