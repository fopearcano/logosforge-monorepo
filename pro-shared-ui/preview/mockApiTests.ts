import { createMockApiClient } from "./mockApi";
import { ApiRequestError } from "../src/adapters/httpApiClient";
import { flushPendingProjectSaves, getProjectSaveStatusSnapshot } from "../src/adapters/projectSaveCoordinator";
import type { StoryStructureDTO } from "@logosforge/ui-contracts";

let passed = 0;

function check(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
  passed += 1;
}

const structurePaths = (structure: StoryStructureDTO) => structure.acts.flatMap((act) => (
  act.chapters.flatMap((chapter) => chapter.scenes.map((scene) => ({
    act: act.name,
    chapter: chapter.name,
    ...scene,
  })))
));

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
check(health.status === "ok" && health.api_version === "1.4.0", "preview health must satisfy the core contract");
const previewStructure = await api.getStoryStructure(1);
check(
  previewStructure.project_id === 1
    && previewStructure.chapter_level === false
    && previewStructure.scene_count === 7
    && previewStructure.acts[0]?.number === "1"
    && previewStructure.acts[0]?.chapters[0]?.scenes[0]?.number === "1.1",
  "preview story structure must mirror the core-owned mode-aware hierarchy",
);
check(
  !("content" in (previewStructure.acts[0]?.chapters[0]?.scenes[0] ?? {})),
  "preview story structure scene references must stay compact",
);
const previewManuscript = await api.getManuscriptSnapshot(1);
const previewStructureOrder = previewStructure.acts.flatMap((act) =>
  act.chapters.flatMap((chapter) => chapter.scenes.map((scene) => scene.id)));
check(
  previewManuscript.project_id === 1
    && previewManuscript.scene_count === previewManuscript.scenes.length
    && previewManuscript.scenes.map((scene) => scene.id).join(",") === previewStructureOrder.join(",")
    && previewManuscript.scenes.every((scene, index) => scene.order_index === index + 1 && Boolean(scene.revision)),
  "preview manuscript snapshot must preserve canonical structure order and revisioned full scenes",
);
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
const seriesModeRevision = (await api.getStoryStructure(createdProject.id)).revision;
await api.updateProject(createdProject.id, { narrative_engine: "novel" });
const novelModeRevision = (await api.getStoryStructure(createdProject.id)).revision;
check(seriesModeRevision !== novelModeRevision,
  "preview structure revisions must include project mode even when the Scene set is unchanged");
await api.updateProject(createdProject.id, { narrative_engine: "series" });
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
const structuralPatchBaseline = (await api.listScenes(1)).find((candidate) => candidate.id === scene.id)!;
const structuralPatchCases: Array<{
  field: "act" | "chapter" | "sort_order";
  patch: Parameters<typeof api.updateScene>[2];
}> = [
  { field: "act", patch: { act: "Moved Act", expected_revision: "stale" } },
  { field: "chapter", patch: { chapter: "Moved Chapter", expected_revision: updatedScene.revision } },
  { field: "sort_order", patch: { sort_order: 0, expected_revision: updatedScene.revision } },
];
for (const { field, patch } of structuralPatchCases) {
  let structuralPatchError: unknown = null;
  try {
    await api.updateScene(1, scene.id, patch);
  } catch (error) {
    structuralPatchError = error;
  }
  check(
    structuralPatchError instanceof ApiRequestError
      && structuralPatchError.status === 400
      && structuralPatchError.code === "bad_request"
      && structuralPatchError.message.includes(field),
    `preview Scene PATCH must reject the explicit structural field ${field}`,
  );
}
const structuralPatchAfter = (await api.listScenes(1)).find((candidate) => candidate.id === scene.id)!;
check(
  structuralPatchAfter.act === structuralPatchBaseline.act
    && structuralPatchAfter.chapter === structuralPatchBaseline.chapter
    && structuralPatchAfter.sort_order === structuralPatchBaseline.sort_order
    && structuralPatchAfter.revision === structuralPatchBaseline.revision,
  "rejected structural Scene PATCHes must not mutate or reorder preview state",
);
let staleConflict: unknown = null;
try {
  await api.updateScene(1, scene.id, { content: "stale", expected_revision: scene.revision });
} catch (error) {
  staleConflict = error;
}
check(staleConflict instanceof ApiRequestError && staleConflict.code === "scene_conflict",
  "preview mock should reject a stale scene revision like the core");

const structureBeforeMove = await api.getStoryStructure(1);
const movedStructure = await api.placeScene(1, 3, {
  expected_revision: structureBeforeMove.revision,
  act: "ACT I",
  chapter: "1.2",
  index: 1,
});
const movedChapter = movedStructure.acts
  .find((act) => act.name === "ACT I")?.chapters
  .find((chapter) => chapter.name === "1.2");
check(
  movedStructure.revision !== structureBeforeMove.revision
    && movedChapter?.scenes.map((item) => item.id).join(",") === "2,3",
  "preview structure placement must atomically reparent, resequence, and advance its revision",
);
let staleStructureConflict: unknown = null;
try {
  await api.placeScene(1, 3, {
    expected_revision: structureBeforeMove.revision,
    act: "ACT I",
    chapter: "1.2",
    index: 0,
  });
} catch (error) {
  staleStructureConflict = error;
}
check(
  staleStructureConflict instanceof ApiRequestError
    && staleStructureConflict.code === "structure_conflict",
  "preview structure placement must reject a stale project-wide revision",
);

const emptyNovelStructure = await api.getStoryStructure(2);
const pendingActCreate = api.executeStoryStructureCommand(2, {
  kind: "create_act",
  expected_revision: emptyNovelStructure.revision,
  act: "Act One",
  index: 0,
});
check(getProjectSaveStatusSnapshot().inFlightCount === 1,
  "preview structure commands must participate in the global handoff barrier");
await flushPendingProjectSaves();
const createdAct = await pendingActCreate;
const actSeedId = createdAct.created_scene_id!;
check(
  createdAct.changed
    && createdAct.affected_scene_ids.join(",") === String(actSeedId)
    && createdAct.structure.acts[0]?.name === "Act One"
    && createdAct.structure.acts[0]?.chapters[0]?.name === "Chapter 1",
  "preview create_act must seed and position a valid canonical Act chain",
);

const createdChapter = await api.executeStoryStructureCommand(2, {
  kind: "create_chapter",
  expected_revision: createdAct.structure.revision,
  act: "Act One",
  chapter: "Chapter Two",
  index: 1,
});
const chapterSeedId = createdChapter.created_scene_id!;
check(
  createdChapter.structure.acts[0]?.chapters.map((chapter) => chapter.name).join(",")
    === "Chapter 1,Chapter Two",
  "preview create_chapter must seed a named Chapter at its zero-based position",
);

const createdCanonicalScene = await api.executeStoryStructureCommand(2, {
  kind: "create_scene",
  expected_revision: createdChapter.structure.revision,
  title: "Chapter Two Follow-up",
  act: "Act One",
  chapter: "Chapter Two",
  index: 1,
});
const canonicalSceneId = createdCanonicalScene.created_scene_id!;
check(
  createdCanonicalScene.structure.acts[0]?.chapters[1]?.scenes.map((item) => item.id).join(",")
    === `${chapterSeedId},${canonicalSceneId}`,
  "preview create_scene must insert within existing destination siblings",
);

const renamedAct = await api.executeStoryStructureCommand(2, {
  kind: "rename_act",
  expected_revision: createdCanonicalScene.structure.revision,
  act: "Act One",
  new_name: "Opening",
});
check(
  renamedAct.affected_scene_ids.length === 3
    && renamedAct.structure.acts[0]?.name === "Opening",
  "preview rename_act must rewrite every matching member without merging",
);
const renamedChapter = await api.executeStoryStructureCommand(2, {
  kind: "rename_chapter",
  expected_revision: renamedAct.structure.revision,
  act: "Opening",
  chapter: "Chapter Two",
  new_name: "Middle",
});
check(
  renamedChapter.affected_scene_ids.join(",") === `${chapterSeedId},${canonicalSceneId}`
    && renamedChapter.structure.acts[0]?.chapters[1]?.name === "Middle",
  "preview rename_chapter must stay scoped to its parent Act",
);

const detachedChapter = await api.executeStoryStructureCommand(2, {
  kind: "detach_chapter",
  expected_revision: renamedChapter.structure.revision,
  act: "Opening",
  chapter: "Middle",
});
check(
  detachedChapter.structure.orphan_count === 2
    && detachedChapter.structure.acts[0]?.chapters.at(-1)?.unassigned === true,
  "preview detach_chapter must preserve Scenes while clearing only their Chapter label",
);
const detachedAct = await api.executeStoryStructureCommand(2, {
  kind: "detach_act",
  expected_revision: detachedChapter.structure.revision,
  act: "Opening",
});
check(
  detachedAct.affected_scene_ids.length === 3
    && detachedAct.structure.orphan_count === 3
    && detachedAct.structure.acts.at(-1)?.unassigned === true,
  "preview detach_act must preserve Scenes and Chapter labels while clearing their Act",
);
const repaired = await api.executeStoryStructureCommand(2, {
  kind: "repair_orphans",
  expected_revision: detachedAct.structure.revision,
});
check(
  repaired.changed
    && repaired.affected_scene_ids.length === 3
    && repaired.structure.orphan_count === 0
    && repaired.structure.acts[0]?.name === "Recovered Act",
  "preview repair_orphans must repair all and only missing canonical labels",
);

let duplicateRename: unknown = null;
try {
  await api.executeStoryStructureCommand(2, {
    kind: "rename_chapter",
    expected_revision: repaired.structure.revision,
    act: "Recovered Act",
    chapter: "Chapter 1",
    new_name: "Recovered Chapter",
  });
} catch (error) {
  duplicateRename = error;
}
check(
  duplicateRename instanceof ApiRequestError
    && duplicateRename.status === 400
    && duplicateRename.code === "bad_request"
    && (await api.getStoryStructure(2)).revision === repaired.structure.revision,
  "preview structure command validation must fail atomically before mutation",
);

const deletedCanonicalScene = await api.executeStoryStructureCommand(2, {
  kind: "delete_scene",
  expected_revision: repaired.structure.revision,
  scene_id: canonicalSceneId,
});
check(
  deletedCanonicalScene.created_scene_id === null
    && deletedCanonicalScene.affected_scene_ids.join(",") === String(canonicalSceneId)
    && !deletedCanonicalScene.structure.acts.some((act) => (
      act.chapters.some((chapter) => chapter.scenes.some((item) => item.id === canonicalSceneId))
    )),
  "preview delete_scene must remove exactly the requested Scene and return authoritative metadata",
);
const noRepairNeeded = await api.executeStoryStructureCommand(2, {
  kind: "repair_orphans",
  expected_revision: deletedCanonicalScene.structure.revision,
});
check(
  !noRepairNeeded.changed
    && noRepairNeeded.affected_scene_ids.length === 0
    && noRepairNeeded.structure.revision === deletedCanonicalScene.structure.revision,
  "preview repair_orphans must be idempotent",
);
let missingContainerError: unknown = null;
try {
  await api.executeStoryStructureCommand(2, {
    kind: "detach_act",
    expected_revision: noRepairNeeded.structure.revision,
    act: "Missing Act",
  });
} catch (error) {
  missingContainerError = error;
}
check(
  missingContainerError instanceof ApiRequestError
    && missingContainerError.status === 400
    && missingContainerError.code === "bad_request",
  "preview missing derived containers must be semantic 400 errors",
);
let missingSceneError: unknown = null;
try {
  await api.executeStoryStructureCommand(2, {
    kind: "delete_scene",
    expected_revision: noRepairNeeded.structure.revision,
    scene_id: 999_999,
  });
} catch (error) {
  missingSceneError = error;
}
check(
  missingSceneError instanceof ApiRequestError
    && missingSceneError.status === 404
    && missingSceneError.code === "not_found",
  "preview missing Scene resources must remain 404 errors",
);
let staleCommandConflict: unknown = null;
try {
  await api.executeStoryStructureCommand(2, {
    kind: "delete_scene",
    expected_revision: emptyNovelStructure.revision,
    scene_id: actSeedId,
  });
} catch (error) {
  staleCommandConflict = error;
}
check(
  staleCommandConflict instanceof ApiRequestError
    && staleCommandConflict.code === "structure_conflict",
  "preview structure commands must reject stale revisions before mutation",
);

const canonicalCommandApi = createMockApiClient();
const leadingOrphan = await canonicalCommandApi.createScene(2, { title: "Leading orphan" });
const trailingNamed = await canonicalCommandApi.createScene(2, {
  title: "Trailing named Scene",
  act: "Act One",
  chapter: "Chapter One",
});
check(
  (await canonicalCommandApi.listScenes(2)).map((sceneRow) => sceneRow.id).join(",")
    === `${leadingOrphan.id},${trailingNamed.id}`,
  "preview canonicalization regression must begin with a raw leading orphan",
);
const leadingOrphanStructure = await canonicalCommandApi.getStoryStructure(2);
const canonicalizedRename = await canonicalCommandApi.executeStoryStructureCommand(2, {
  kind: "rename_act",
  expected_revision: leadingOrphanStructure.revision,
  act: "Act One",
  new_name: "Opening",
});
check(
  canonicalizedRename.affected_scene_ids.join(",") === String(trailingNamed.id)
    && (await canonicalCommandApi.listScenes(2)).map((sceneRow) => sceneRow.id).join(",")
      === `${trailingNamed.id},${leadingOrphan.id}`,
  "preview non-Series commands must persist canonical order with Unassigned buckets last",
);

const episodeOne = await api.createEpisode(3, 1, { episode_number: 1, title: "Pilot" });
const episodeTwo = await api.createEpisode(3, 1, { episode_number: 2, title: "Aftermath" });
const episodeOneId = episodeOne.id!;
const episodeTwoId = episodeTwo.id!;
check(
  (await api.listEpisodes(3)).map((episode) => episode.id).join(",") === `${episodeOneId},${episodeTwoId}`,
  "preview Episodes must retain project ownership for Series command validation",
);

const emptySeriesStructure = await api.getStoryStructure(3);
let unknownEpisodeError: unknown = null;
try {
  await api.executeStoryStructureCommand(3, {
    kind: "create_act",
    expected_revision: emptySeriesStructure.revision,
    act: "Unknown Episode Act",
    index: 0,
    episode_id: 999_999,
  });
} catch (error) {
  unknownEpisodeError = error;
}
check(
  unknownEpisodeError instanceof ApiRequestError && unknownEpisodeError.status === 404,
  "preview Series commands must reject Episodes that are not owned by the project",
);

let nonSeriesEpisodeError: unknown = null;
try {
  await api.executeStoryStructureCommand(2, {
    kind: "create_act",
    expected_revision: noRepairNeeded.structure.revision,
    act: "Episode-only Act",
    index: 1,
    episode_id: episodeOneId,
  });
} catch (error) {
  nonSeriesEpisodeError = error;
}
check(
  nonSeriesEpisodeError instanceof ApiRequestError && nonSeriesEpisodeError.status === 400,
  "preview non-Series commands must reject a non-null episode_id",
);

let missingSeriesChapterError: unknown = null;
try {
  await api.executeStoryStructureCommand(3, {
    kind: "create_act",
    expected_revision: emptySeriesStructure.revision,
    act: "Missing Chapter",
    chapter: "",
    index: 0,
    episode_id: episodeOneId,
  });
} catch (error) {
  missingSeriesChapterError = error;
}
check(
  missingSeriesChapterError instanceof ApiRequestError && missingSeriesChapterError.status === 400,
  "preview Series groups must require a named Chapter parent",
);

const episodeOneShared = await api.executeStoryStructureCommand(3, {
  kind: "create_act",
  expected_revision: emptySeriesStructure.revision,
  act: "Shared Act",
  index: 0,
  episode_id: episodeOneId,
});
const episodeOneSharedId = episodeOneShared.created_scene_id!;
const episodeTwoShared = await api.executeStoryStructureCommand(3, {
  kind: "create_act",
  expected_revision: episodeOneShared.structure.revision,
  act: "Shared Act",
  index: 0,
  episode_id: episodeTwoId,
});
const episodeTwoSharedId = episodeTwoShared.created_scene_id!;
check(
  episodeTwoShared.structure.chapter_level === false
    && episodeTwoShared.structure.orphan_count === 0
    && structurePaths(episodeTwoShared.structure).filter((scene) => (
      scene.id === episodeOneSharedId || scene.id === episodeTwoSharedId
    )).every((scene) => scene.chapter === "Chapter 1"),
  "preview Series may reuse Act labels across Episodes while seeding required Chapter parents",
);

let duplicateSeriesAct: unknown = null;
try {
  await api.executeStoryStructureCommand(3, {
    kind: "create_act",
    expected_revision: episodeTwoShared.structure.revision,
    act: "Shared Act",
    index: 1,
    episode_id: episodeOneId,
  });
} catch (error) {
  duplicateSeriesAct = error;
}
check(
  duplicateSeriesAct instanceof ApiRequestError
    && duplicateSeriesAct.status === 400
    && duplicateSeriesAct.code === "bad_request",
  "preview Series duplicate checks must remain strict inside one Episode",
);

const episodeOneFirst = await api.executeStoryStructureCommand(3, {
  kind: "create_act",
  expected_revision: episodeTwoShared.structure.revision,
  act: "Episode One First",
  index: 0,
  episode_id: episodeOneId,
});
const episodeTwoFirst = await api.executeStoryStructureCommand(3, {
  kind: "create_act",
  expected_revision: episodeOneFirst.structure.revision,
  act: "Episode Two First",
  index: 0,
  episode_id: episodeTwoId,
});
check(
  structurePaths(episodeTwoFirst.structure).find((scene) => scene.id === episodeOneFirst.created_scene_id)?.episode_id
      === episodeOneId
    && structurePaths(episodeTwoFirst.structure).find((scene) => scene.id === episodeTwoFirst.created_scene_id)?.episode_id
      === episodeTwoId,
  "preview Series Act creation must retain the selected Episode scope",
);
let episodeLocalActIndexError: unknown = null;
try {
  await api.executeStoryStructureCommand(3, {
    kind: "create_act",
    expected_revision: episodeTwoFirst.structure.revision,
    act: "Outside Episode One",
    index: 3,
    episode_id: episodeOneId,
  });
} catch (error) {
  episodeLocalActIndexError = error;
}
check(
  episodeLocalActIndexError instanceof ApiRequestError && episodeLocalActIndexError.status === 400,
  "preview Series Act index bounds must count only Acts in the selected Episode",
);

const episodeOneChapter = await api.executeStoryStructureCommand(3, {
  kind: "create_chapter",
  expected_revision: episodeTwoFirst.structure.revision,
  act: "Shared Act",
  chapter: "Episode Chapter",
  index: 1,
  episode_id: episodeOneId,
});
const episodeOneChapterId = episodeOneChapter.created_scene_id!;
let episodeLocalChapterIndexError: unknown = null;
try {
  await api.executeStoryStructureCommand(3, {
    kind: "create_chapter",
    expected_revision: episodeOneChapter.structure.revision,
    act: "Shared Act",
    chapter: "Outside Episode Two",
    index: 2,
    episode_id: episodeTwoId,
  });
} catch (error) {
  episodeLocalChapterIndexError = error;
}
check(
  episodeLocalChapterIndexError instanceof ApiRequestError && episodeLocalChapterIndexError.status === 400,
  "preview Series Chapter index bounds must count only Chapters in the selected Episode",
);
let missingEpisodeDestination: unknown = null;
try {
  await api.executeStoryStructureCommand(3, {
    kind: "create_scene",
    expected_revision: episodeOneChapter.structure.revision,
    act: "Shared Act",
    chapter: "Episode Chapter",
    index: 1,
    episode_id: episodeTwoId,
  });
} catch (error) {
  missingEpisodeDestination = error;
}
check(
  missingEpisodeDestination instanceof ApiRequestError
    && missingEpisodeDestination.status === 400
    && missingEpisodeDestination.code === "bad_request",
  "preview Series create_scene must require its destination in the selected Episode",
);

const episodeTwoChapter = await api.executeStoryStructureCommand(3, {
  kind: "create_chapter",
  expected_revision: episodeOneChapter.structure.revision,
  act: "Shared Act",
  chapter: "Episode Chapter",
  index: 1,
  episode_id: episodeTwoId,
});
const episodeTwoChapterId = episodeTwoChapter.created_scene_id!;
check(
  structurePaths(episodeTwoChapter.structure).filter((scene) => (
    scene.id === episodeOneChapterId || scene.id === episodeTwoChapterId
  )).every((scene) => scene.chapter === "Episode Chapter"),
  "preview Series Chapter existence and duplicate checks must be Episode-scoped",
);

const rawSeriesOrderBeforePlacement = (await api.listScenes(3)).map((sceneRow) => sceneRow.id).join(",");
const placedSeriesStructure = await api.placeScene(3, episodeTwoChapterId, {
  expected_revision: episodeTwoChapter.structure.revision,
  act: "Shared Act",
  chapter: "Episode Chapter",
  index: 0,
  episode_id: episodeTwoId,
});
const rawSeriesOrderAfterPlacement = (await api.listScenes(3)).map((sceneRow) => sceneRow.id).join(",");
check(
  rawSeriesOrderAfterPlacement === rawSeriesOrderBeforePlacement,
  "preview Series placement must preserve raw cross-Episode order instead of flattening the collapsed DTO",
);

const renamedSeriesAct = await api.executeStoryStructureCommand(3, {
  kind: "rename_act",
  expected_revision: placedSeriesStructure.revision,
  act: "Shared Act",
  new_name: "Episode One Act",
  episode_id: episodeOneId,
});
check(
  renamedSeriesAct.affected_scene_ids.join(",") === `${episodeOneSharedId},${episodeOneChapterId}`
    && structurePaths(renamedSeriesAct.structure).find((scene) => scene.id === episodeTwoSharedId)?.act === "Shared Act",
  "preview Series Act renames must mutate only the selected Episode",
);

const renamedSeriesChapter = await api.executeStoryStructureCommand(3, {
  kind: "rename_chapter",
  expected_revision: renamedSeriesAct.structure.revision,
  act: "Shared Act",
  chapter: "Episode Chapter",
  new_name: "Episode Two Chapter",
  episode_id: episodeTwoId,
});
check(
  renamedSeriesChapter.affected_scene_ids.join(",") === String(episodeTwoChapterId)
    && structurePaths(renamedSeriesChapter.structure).find((scene) => scene.id === episodeOneChapterId)?.chapter
      === "Episode Chapter",
  "preview Series Chapter renames must mutate only the selected Episode",
);

const detachedSeriesChapter = await api.executeStoryStructureCommand(3, {
  kind: "detach_chapter",
  expected_revision: renamedSeriesChapter.structure.revision,
  act: "Shared Act",
  chapter: "Episode Two Chapter",
  episode_id: episodeTwoId,
});
check(
  detachedSeriesChapter.affected_scene_ids.join(",") === String(episodeTwoChapterId)
    && detachedSeriesChapter.structure.orphan_count === 1
    && structurePaths(detachedSeriesChapter.structure).find((scene) => scene.id === episodeTwoChapterId)?.is_orphan,
  "preview Series Chapter detachment must be Episode-scoped and produce a repairable orphan",
);

const repairedSeries = await api.executeStoryStructureCommand(3, {
  kind: "repair_orphans",
  expected_revision: detachedSeriesChapter.structure.revision,
});
check(
  repairedSeries.affected_scene_ids.join(",") === String(episodeTwoChapterId)
    && repairedSeries.structure.orphan_count === 0
    && structurePaths(repairedSeries.structure).find((scene) => scene.id === episodeTwoChapterId)?.chapter
      === "Recovered Chapter",
  "preview Series orphan repair must restore missing Chapter parents",
);

const detachedSeriesAct = await api.executeStoryStructureCommand(3, {
  kind: "detach_act",
  expected_revision: repairedSeries.structure.revision,
  act: "Shared Act",
  episode_id: episodeTwoId,
});
check(
  detachedSeriesAct.affected_scene_ids.join(",") === `${episodeTwoSharedId},${episodeTwoChapterId}`
    && structurePaths(detachedSeriesAct.structure).find((scene) => scene.id === episodeOneSharedId)?.act
      === "Episode One Act",
  "preview Series Act detachment must preserve same-named groups in other Episodes",
);

const legacyEpisodeSibling = await api.executeStoryStructureCommand(3, {
  kind: "create_scene",
  expected_revision: detachedSeriesAct.structure.revision,
  title: "Legacy Episode sibling",
  act: "Episode One First",
  chapter: "Chapter 1",
  index: 1,
  episode_id: episodeOneId,
});
const legacyEpisodeSiblingId = legacyEpisodeSibling.created_scene_id!;
await api.updateProject(3, { narrative_engine: "screenplay" });
const convertedFlatStructure = await api.getStoryStructure(3);
const clearedLegacyEpisode = await api.placeScene(3, legacyEpisodeSiblingId, {
  expected_revision: convertedFlatStructure.revision,
  act: "Episode One First",
  chapter: "Chapter 1",
  index: 0,
  episode_id: null,
});
const preservedLegacyEpisode = await api.placeScene(3, episodeOneFirst.created_scene_id!, {
  expected_revision: clearedLegacyEpisode.revision,
  act: "Episode One First",
  chapter: "Chapter 1",
  index: 0,
});
check(
  structurePaths(preservedLegacyEpisode).find((scene) => scene.id === legacyEpisodeSiblingId)?.episode_id === null
    && structurePaths(preservedLegacyEpisode).find((scene) => scene.id === episodeOneFirst.created_scene_id)?.episode_id
      === episodeOneId,
  "preview non-Series placement must clear a legacy Episode only for explicit episode_id null",
);

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
