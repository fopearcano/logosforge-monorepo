import { createMockApiClient } from "./mockApi";
import { ApiRequestError } from "../src/adapters/httpApiClient";

let passed = 0;

function check(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
  passed += 1;
}

const api = createMockApiClient();
check(typeof api.getAdapt === "function", "preview mock must implement getAdapt");
check(typeof api.patchAiBehavior === "function", "preview mock must implement patchAiBehavior");
check(typeof api.voiceHistory === "function", "preview mock must implement Voice history");
check(typeof api.voiceIntentCancel === "function", "preview mock must implement Voice preview cancellation");
check(typeof api.voiceBillyCancel === "function", "preview mock must implement Billy preview cancellation");

const initial = await api.getAdapt(1);
check(initial.mode === "Structure", "preview should start in automatic Structure mode");

await api.patchAiBehavior(1, { adaptive_override: "Refinement" });
const overridden = await api.getAdapt(1);
check(overridden.mode === "Refinement", "adaptive override must round-trip in preview");
check(overridden.override === "Refinement", "preview must expose the active override");

const voice = await api.voiceHistory(1);
check(voice.entries.length > 0, "preview Voice history should contain a reviewable segment");
const otherVoice = await api.voiceHistory(2);
check(otherVoice.entries.length === 0, "preview Voice history must stay project-scoped");

const scene = (await api.listScenes(1))[0]!;
const updatedScene = await api.updateScene(1, scene.id, {
  content: `${scene.content}\nrevision-safe`,
  expected_revision: scene.revision,
});
check(updatedScene.revision !== scene.revision, "scene mutation should advance its revision");
let staleConflict: unknown = null;
try {
  await api.updateScene(1, scene.id, { content: "stale", expected_revision: scene.revision });
} catch (error) {
  staleConflict = error;
}
check(staleConflict instanceof ApiRequestError && staleConflict.code === "scene_conflict",
  "preview mock should reject a stale scene revision like the core");

const initialComments = await api.listComments(1);
const rootComment = initialComments[0]!;
const withReply = await api.createCommentReply(1, rootComment.id, { body: "Native review reply", author: "you" });
const nativeReply = withReply.replies.find((reply) => reply.body === "Native review reply");
check(nativeReply?.source_id === "", "preview comment replies preserve native provenance");
await api.deleteCommentReply(1, rootComment.id, nativeReply!.id);
check(!(await api.listComments(1))[0]!.replies.some((reply) => reply.id === nativeReply!.id), "preview reply deletion round-trips");

const createdComment = await api.createComment(1, {
  anchor: { ...rootComment.anchor },
  quote: rootComment.quote,
  body: "Native panel comment",
});
check(createdComment.source_id === "" && createdComment.body === "Native panel comment", "preview comment creation uses native provenance");
const editedComment = await api.updateComment(1, createdComment.id, { body: "Edited native panel comment" });
check(editedComment.body === "Edited native panel comment", "preview comment editing round-trips");
await api.deleteComment(1, createdComment.id);
check(!(await api.listComments(1)).some((comment) => comment.id === createdComment.id), "preview thread deletion round-trips");
const editedImported = await api.updateComment(1, rootComment.id, { body: "Imported provenance stays immutable" });
check(editedImported.source_id === rootComment.source_id && editedImported.body === "Imported provenance stays immutable",
  "imported comment bodies remain editable without changing provenance");
const importedReply = editedImported.replies.find((reply) => reply.source_id)!;
await api.deleteCommentReply(1, rootComment.id, importedReply.id);
check(!(await api.listComments(1))[0]!.replies.some((reply) => reply.id === importedReply.id),
  "imported replies remain deletable while provenance is present");

console.log(`Preview API tests: ${passed} passed, 0 failed`);
