import type {
  AssistantRequestDTO,
  AssistantResponseDTO,
  CommentReplyCreateDTO,
  CounterpartRequestDTO,
  InlineCommentDTO,
} from "@logosforge/ui-contracts";
import { trackProjectWrite } from "../../adapters/projectSaveCoordinator";

export type CommentAssistantHandle = "assistant" | "counterpart";

const MENTION = /(?:^|[^A-Za-z0-9._%+@-])@(assistant|counterpart)\b/i;

/** Pro-owned assistant handles. Whiteboard persona names intentionally do not match. */
export function detectCommentAssistantMention(value: string): CommentAssistantHandle | null {
  const match = MENTION.exec(value);
  return match ? match[1]!.toLowerCase() as CommentAssistantHandle : null;
}

export function buildCommentThreadContext(comment: InlineCommentDTO, writerMessage: string): string {
  const replies = [...comment.replies]
    .sort((left, right) => left.sort_order - right.sort_order || left.id - right.id)
    .map((reply) => `${reply.author || "Unknown author"}: ${reply.body}`);
  return [
    `Quoted manuscript text: ${comment.quote || "(none)"}`,
    `Root comment: ${comment.body || "(empty)"}`,
    ...(replies.length ? ["Existing replies:", ...replies] : []),
    `Writer's new reply: ${writerMessage}`,
  ].join("\n");
}

export function buildCommentAssistantPrompt(handle: CommentAssistantHandle, writerMessage: string): string {
  const label = handle === "counterpart" ? "Counterpart" : "Assistant";
  return [
    `The writer mentioned @${handle} in an anchored LogosForge comment thread.`,
    `Reply as the Pro ${label} with a concise, useful response to the request.`,
    "Write only the reply that belongs in the thread; do not restate these instructions.",
    "",
    writerMessage,
  ].join("\n");
}

export interface CommentAssistantReplyApi {
  assistantChat(projectId: number, body: AssistantRequestDTO): Promise<AssistantResponseDTO>;
  runCounterpart(projectId: number, body: CounterpartRequestDTO): Promise<AssistantResponseDTO>;
  createCommentReply(projectId: number, commentId: number, body: CommentReplyCreateDTO): Promise<InlineCommentDTO>;
}

/**
 * Complete the provider -> reply-write chain against captured IDs. This work is
 * deliberately independent of React lifetime: closing the panel must not throw
 * away a provider response after the writer's mention has already been saved.
 */
export function persistCommentAssistantReply(
  api: CommentAssistantReplyApi,
  ownerProjectId: number,
  comment: InlineCommentDTO,
  writerMessage: string,
  handle: CommentAssistantHandle,
): Promise<{ author: string; body: string }> {
  // Register before the provider request starts. A close/project handoff must
  // wait for generation *and* the eventual reply write, not merely notice the
  // final POST after an untracked provider request happens to finish.
  return trackProjectWrite((async () => {
    const author = handle === "counterpart" ? "Counterpart" : "Assistant";
    const threadContext = buildCommentThreadContext(comment, writerMessage);
    const response = handle === "counterpart"
      ? await api.runCounterpart(ownerProjectId, {
          mode: "Feedback",
          scene_context: comment.quote,
          user_note: writerMessage,
          custom_prompt: `${buildCommentAssistantPrompt(handle, writerMessage)}\n\n${threadContext}`,
        })
      : await api.assistantChat(ownerProjectId, {
          message: buildCommentAssistantPrompt(handle, writerMessage),
          active_scene_id: comment.anchor.start_scene_id,
          selected_text: comment.quote || undefined,
          nearby_text: threadContext,
        });
    const body = response.reply.trim();
    if (!body) throw new Error(`${author} returned an empty response`);
    await api.createCommentReply(ownerProjectId, comment.id, { body, author });
    return { author, body };
  })());
}
