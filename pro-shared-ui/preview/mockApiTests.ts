import { createMockApiClient } from "./mockApi";
import { ApiRequestError } from "../src/adapters/httpApiClient";
import { flushPendingProjectSaves, getProjectSaveStatusSnapshot } from "../src/adapters/projectSaveCoordinator";

let passed = 0;

function check(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
  passed += 1;
}

const api = createMockApiClient();
check(typeof api.health === "function", "preview mock must implement core health");
check(typeof api.writingModes === "function", "preview mock must implement the writing-mode catalog");
check(typeof api.openProject === "function", "preview mock must implement project opening");
check(typeof api.createProject === "function", "preview mock must implement project creation");
check(typeof api.updateProject === "function", "preview mock must implement project metadata updates");
check(typeof api.deleteProject === "function", "preview mock must implement project deletion");
check(typeof api.searchProject === "function", "preview mock must implement typed project search");
check(typeof api.getAdapt === "function", "preview mock must implement getAdapt");
check(typeof api.patchAiBehavior === "function", "preview mock must implement patchAiBehavior");
check(typeof api.voiceHistory === "function", "preview mock must implement Voice history");
check(typeof api.voiceIntentCancel === "function", "preview mock must implement Voice preview cancellation");
check(typeof api.voiceBillyCancel === "function", "preview mock must implement Billy preview cancellation");
check(typeof api.planPsykeConsoleCommand === "function", "preview mock must implement PSYKE command planning");
check(typeof api.executePsykeConsoleCommand === "function", "preview mock must implement PSYKE command execution");

const health = await api.health();
check(health.status === "ok" && health.api_version === "1.0.0", "preview health must satisfy the core contract");
const writingModes = await api.writingModes();
check(writingModes.default_mode === "novel" && writingModes.modes.length === 5,
  "preview writing-mode catalog must expose all five canonical modes");
check(writingModes.modes.find((mode) => mode.id === "series")?.default_writing_format === "screenplay",
  "preview Series mode must use the core's screenplay writing format");

const initialProjects = await api.listProjects();
const search = await api.searchProject(initialProjects[0]!.id, "Marlow", ["scene", "psyke"]);
check(search.matches.length > 0 && search.matches.every((match) => match.kind === "scene" || match.kind === "psyke"),
  "preview project search must respect its typed kind filter");
const fixtureText = await api.searchProject(initialProjects[0]!.id, "Marlow", ["note", "psyke"]);
check(new Set(fixtureText.matches.map((match) => match.kind)).size === 2,
  "preview fixture project search must expose its note and PSYKE matches");
const fixtureComment = await api.searchProject(initialProjects[0]!.id, "HELIOS-9", ["comment"]);
check(fixtureComment.matches.some((match) => match.kind === "comment"),
  "preview fixture project search must expose its comment matches");
const foreignText = await api.searchProject(initialProjects[1]!.id, "Marlow", ["note", "psyke"]);
const foreignComment = await api.searchProject(initialProjects[1]!.id, "HELIOS-9", ["comment"]);
check(foreignText.matches.length === 0 && foreignComment.matches.length === 0,
  "preview project search must not leak notes, PSYKE entries, or comments across projects");
const openedFixture = await api.openProject(initialProjects[0]!.id);
check(openedFixture.title === initialProjects[0]!.title, "preview project opening must return an existing project");
const pendingCreate = api.createProject({ title: "Project lifecycle test", narrative_engine: "series" });
check(getProjectSaveStatusSnapshot().inFlightCount === 1,
  "preview mock mutations must be visible to the global handoff barrier");
await flushPendingProjectSaves();
const createdProject = await pendingCreate;
check(getProjectSaveStatusSnapshot().inFlightCount === 0,
  "preview mock mutation tracking must settle after the write completes");
check(createdProject.default_writing_format === "screenplay" && createdProject.format_mode === "screenplay",
  "preview project creation must apply canonical mode defaults");
createdProject.title = "caller mutation";
check((await api.getProject(createdProject.id)).title === "Project lifecycle test",
  "preview project responses must not expose mutable backing records");
const updatedProject = await api.updateProject(createdProject.id, { title: "Renamed lifecycle test", description: "Round trip" });
check(updatedProject.title === "Renamed lifecycle test" && updatedProject.description === "Round trip",
  "preview project metadata updates must round-trip");
let invalidModeUpdate: unknown = null;
try {
  await api.updateProject(createdProject.id, { title: "Must not leak", narrative_engine: "invalid-mode" });
} catch (error) {
  invalidModeUpdate = error;
}
check(invalidModeUpdate instanceof ApiRequestError && (await api.getProject(createdProject.id)).title === "Renamed lifecycle test",
  "preview project updates must validate atomically before mutating metadata");
check((await api.saveProject(createdProject.id)).project_id === createdProject.id,
  "preview project save must return the authoritative project id");
check((await api.closeProject(createdProject.id)).ok, "preview project close must acknowledge the lifecycle action");
check((await api.deleteProject(createdProject.id)).deleted === createdProject.id,
  "preview project deletion must identify the deleted project");
let missingProject: unknown = null;
try {
  await api.openProject(createdProject.id);
} catch (error) {
  missingProject = error;
}
check(missingProject instanceof ApiRequestError && missingProject.status === 404,
  "preview project lifecycle must reject missing project ids like the core");

const whiteboardImport = await api.importWhiteboard({
  title: "Imported draft",
  mode: "novel",
  blocks: [{ id: "heading", type: "heading", text: "Opening" }, { id: "body", type: "paragraph", text: "A first paragraph." }],
});
check(whiteboardImport.scenes_created === 1 && whiteboardImport.scene_ids_by_block.every((id) => id > 0),
  "preview Whiteboard import must return usable scene mappings");
check((await api.openProject(whiteboardImport.project_id)).title === "Imported draft",
  "preview Whiteboard imports must create immediately openable projects");
check((await api.listScenes(whiteboardImport.project_id)).length === 1 && (await api.listScenes(2)).length === 0,
  "preview imported scenes must remain scoped to their destination project");
const manuscriptImport = await api.importManuscript({
  title: "Imported prose",
  mode: "novel",
  filename: "imported.md",
  content_base64: "IyBPcGVuaW5n",
});
check(manuscriptImport.scenes_created === 1 && (await api.getProject(manuscriptImport.project_id)).title === "Imported prose",
  "preview manuscript imports must create immediately readable projects");
const isolatedApi = createMockApiClient();
check(!(await isolatedApi.listProjects()).some((project) => project.id === whiteboardImport.project_id || project.id === manuscriptImport.project_id),
  "new preview clients must not inherit project mutations from replaced transports");

const psykeCount = (await api.listPsyke(1)).length;
const commandPlan = await api.planPsykeConsoleCommand(1, { command: "/create character Ione" });
check(commandPlan.mutates && commandPlan.requires_confirmation, "preview command plan must identify project writes");
check((await api.listPsyke(1)).length === psykeCount, "preview command planning must stay read-only");
const commandResult = await api.executePsykeConsoleCommand(1, { plan_id: commandPlan.plan_id, confirmed: true }, commandPlan.mutates);
check(commandResult.mutated && commandResult.target_type === "psyke_entry", "preview command execution must return an authoritative navigation target");
let commandReplay: unknown = null;
try {
  await api.executePsykeConsoleCommand(1, { plan_id: commandPlan.plan_id, confirmed: true }, commandPlan.mutates);
} catch (error) {
  commandReplay = error;
}
check(commandReplay instanceof ApiRequestError && commandReplay.status === 404, "preview command plans must be single-use");

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
check((await isolatedApi.listScenes(1))[0]!.content === scene.content,
  "replaced preview clients must not inherit scene mutations from the old transport");
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
