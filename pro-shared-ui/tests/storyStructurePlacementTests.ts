import type { StoryStructureDTO } from "@logosforge/ui-contracts";
import {
  createScenePlacementDraft,
  flattenStoryStructure,
  isImmediateScenePlacementNeighbor,
  placeScenePlacementDraft,
  scenePlacementPlan,
  stepScenePlacementDraft,
} from "../src/components/shell/storyStructurePlacement";
import {
  episodeChoicesForScenes,
  planStoryStructureCommand,
} from "../src/components/shell/storyStructureCommands";

let assertions = 0;
function check(condition: unknown, message: string): asserts condition {
  assertions += 1;
  if (!condition) throw new Error(message);
}

const scene = (
  id: number,
  orderIndex: number,
  episodeId: number | null = 10,
) => ({
  id,
  title: `Scene ${id}`,
  beat: "",
  episode_id: episodeId,
  number: String(orderIndex),
  order_index: orderIndex,
  is_orphan: false,
});

const structure: StoryStructureDTO = {
  project_id: 7,
  revision: "a".repeat(64),
  chapter_level: true,
  scene_count: 6,
  orphan_count: 1,
  acts: [
    {
      name: "Act I", number: "1", unassigned: false, scene_count: 3,
      chapters: [
        { name: "Chapter A", number: "1.1", unassigned: false, scene_count: 2, scenes: [scene(1, 1), scene(2, 2)] },
        { name: "Chapter B", number: "1.2", unassigned: false, scene_count: 1, scenes: [scene(3, 3)] },
      ],
    },
    {
      name: "Act II", number: "2", unassigned: false, scene_count: 2,
      chapters: [
        { name: "Chapter C", number: "2.1", unassigned: false, scene_count: 2, scenes: [scene(4, 4), scene(5, 5, 20)] },
      ],
    },
    {
      name: "Unassigned", number: "", unassigned: true, scene_count: 1,
      chapters: [
        { name: "Unassigned", number: "", unassigned: true, scene_count: 1, scenes: [{ ...scene(6, 6), is_orphan: true }] },
      ],
    },
  ],
};

check(
  flattenStoryStructure(structure).map((entry) => entry.sceneId).join(",") === "1,2,3,4,5,6",
  "flattening must preserve the server's nested canonical order",
);
check(
  flattenStoryStructure(structure).at(-1)?.act === ""
    && flattenStoryStructure(structure).at(-1)?.chapter === "",
  "unassigned display wrappers must map back to empty persisted labels",
);
const canonicalEntries = flattenStoryStructure(structure);
check(isImmediateScenePlacementNeighbor(canonicalEntries, 2, 1, -1),
  "fresh structure should confirm the exact neighbor that was visible when moving up");
check(!isImmediateScenePlacementNeighbor(canonicalEntries, 2, 3, -1),
  "fresh structure should reject a different neighbor after an intervening reorder");

const up = stepScenePlacementDraft(createScenePlacementDraft(structure, 2)!, -1);
const upPlan = scenePlacementPlan(up.draft)!;
check(up.moved && upPlan.body.act === "Act I" && upPlan.body.chapter === "Chapter A" && upPlan.body.index === 0,
  "keyboard up should produce a post-removal sibling index in the same parent");
check(upPlan.body.expected_revision === structure.revision && !("episode_id" in upPlan.body),
  "placement should carry the structure revision and preserve episode ownership by omission");

const downAcrossChapter = stepScenePlacementDraft(createScenePlacementDraft(structure, 2)!, 1);
const downAcrossChapterPlan = scenePlacementPlan(downAcrossChapter.draft)!;
check(
  downAcrossChapterPlan.body.act === "Act I"
    && downAcrossChapterPlan.body.chapter === "Chapter B"
    && downAcrossChapterPlan.body.index === 1,
  "keyboard down across a Chapter boundary should reparent after the adjacent scene",
);

const onlyChildAcrossChapter = stepScenePlacementDraft(createScenePlacementDraft(structure, 3)!, -1);
const onlyChildPlan = scenePlacementPlan(onlyChildAcrossChapter.draft)!;
check(
  onlyChildPlan.body.chapter === "Chapter A" && onlyChildPlan.body.index === 1,
  "moving an only child should calculate its destination after removing the source group",
);

const pointerBefore = placeScenePlacementDraft(createScenePlacementDraft(structure, 4)!, 2, "before");
const pointerBeforePlan = scenePlacementPlan(pointerBefore.draft)!;
check(
  pointerBeforePlan.body.act === "Act I"
    && pointerBeforePlan.body.chapter === "Chapter A"
    && pointerBeforePlan.body.index === 1,
  "pointer-before should use the target scene's exact structural parent",
);

let staged = stepScenePlacementDraft(createScenePlacementDraft(structure, 1)!, 1).draft;
staged = stepScenePlacementDraft(staged, 1).draft;
const stagedPlan = scenePlacementPlan(staged)!;
check(
  stagedPlan.body.chapter === "Chapter B" && stagedPlan.body.index === 1 && stagedPlan.canonicalIndex === 2,
  "successive keyboard steps should stage one final transactional placement",
);

const episodeBoundary = stepScenePlacementDraft(createScenePlacementDraft(structure, 4)!, 1);
check(
  !episodeBoundary.moved && episodeBoundary.reason === "episode_boundary" && scenePlacementPlan(episodeBoundary.draft) == null,
  "relative moves across a Series episode boundary must be rejected without an episode reassignment",
);

const pointerEpisodeBoundary = placeScenePlacementDraft(createScenePlacementDraft(structure, 5)!, 4, "before");
check(!pointerEpisodeBoundary.moved && pointerEpisodeBoundary.reason === "episode_boundary",
  "pointer placement must enforce the same Series episode boundary as keyboard movement");

const noOp = placeScenePlacementDraft(createScenePlacementDraft(structure, 1)!, 2, "before");
check(noOp.moved && scenePlacementPlan(noOp.draft) == null,
  "dropping into the existing position should not emit a mutation");

const intoUnassigned = placeScenePlacementDraft(createScenePlacementDraft(structure, 4)!, 6, "before");
const intoUnassignedPlan = scenePlacementPlan(intoUnassigned.draft)!;
check(intoUnassignedPlan.body.act === "" && intoUnassignedPlan.body.chapter === "",
  "an existing Unassigned target must never persist its display label literally");

const createAct = planStoryStructureCommand(structure, {
  kind: "create_act",
  act: "Act III",
  chapter: "Chapter D",
  title: "A new beginning",
  episodeId: 20,
});
check(
  createAct.plan?.body.kind === "create_act"
    && createAct.plan.body.expected_revision === structure.revision
    && createAct.plan.body.index === 2
    && createAct.plan.body.episode_id === 20,
  "create Act should use the latest revision and a global named-Act index",
);

const createChapter = planStoryStructureCommand(structure, {
  kind: "create_chapter",
  act: "Act I",
  chapter: "Chapter C",
  title: "Seed",
  episodeId: 20,
});
check(
  createChapter.plan?.body.kind === "create_chapter"
    && createChapter.plan.body.index === 2
    && createChapter.plan.body.episode_id === 20,
  "create Chapter should use the Act's global named-Chapter index without requiring an existing episode sibling",
);

const createScene = planStoryStructureCommand(structure, {
  kind: "create_scene",
  act: "Act II",
  chapter: "Chapter C",
  title: "Episode-specific scene",
  episodeId: 20,
}, true);
check(
  createScene.plan?.body.kind === "create_scene"
    && createScene.plan.body.index === 1
    && createScene.plan.body.episode_id === 20,
  "create Scene should calculate its insertion index only among episode siblings",
);

const renameAct = planStoryStructureCommand(structure, {
  kind: "rename_act",
  act: "Act I",
  newName: "Act Prime",
  episodeId: null,
});
check(
  renameAct.plan?.body.kind === "rename_act" && renameAct.plan.body.new_name === "Act Prime",
  "rename Act should target the canonical stored label",
);
check(
  planStoryStructureCommand(structure, {
    kind: "rename_act", act: "Act I", newName: "Act II", episodeId: null,
  }).error?.includes("already exists"),
  "rename Act should reject a local label collision before mutation",
);

const renameChapter = planStoryStructureCommand(structure, {
  kind: "rename_chapter",
  act: "Act I",
  chapter: "Chapter A",
  newName: "Arrival",
  episodeId: null,
});
check(
  renameChapter.plan?.body.kind === "rename_chapter" && renameChapter.plan.body.new_name === "Arrival",
  "rename Chapter should preserve its parent Act target",
);
check(
  planStoryStructureCommand(structure, {
    kind: "detach_act", act: "Act I", episodeId: null,
  }).plan?.body.kind === "detach_act"
    && planStoryStructureCommand(structure, {
      kind: "detach_chapter", act: "Act I", chapter: "Chapter A", episodeId: null,
    }).plan?.body.kind === "detach_chapter",
  "detach planners should use dedicated manuscript-preserving structure commands",
);

const deleteScene = planStoryStructureCommand(structure, { kind: "delete_scene", sceneId: 2 });
check(
  deleteScene.plan?.body.kind === "delete_scene"
    && deleteScene.plan.body.scene_id === 2
    && deleteScene.plan.focusSceneId === 3,
  "delete Scene should choose the following canonical Scene as a focus fallback",
);
check(
  planStoryStructureCommand(structure, { kind: "repair_orphans" }).plan?.body.kind === "repair_orphans",
  "orphan repair should use its dedicated revision-guarded command",
);

const flatStructure = structuredClone(structure);
flatStructure.chapter_level = false;
flatStructure.acts[0]!.chapters[0]!.name = "Unassigned";
flatStructure.acts[0]!.chapters[0]!.unassigned = true;
const flatCreateScene = planStoryStructureCommand(flatStructure, {
  kind: "create_scene",
  act: "Act I",
  chapter: "",
  title: "Flat scene",
  episodeId: 10,
});
check(
  flatCreateScene.plan?.body.kind === "create_scene"
    && flatCreateScene.plan.body.chapter === ""
    && flatCreateScene.plan.body.index === 2,
  "flat modes should create Scenes in their synthetic empty Chapter bucket",
);
const modeSwitchedStructure = structuredClone(flatStructure);
modeSwitchedStructure.acts[0]!.chapters[0]!.scenes[1]!.episode_id = 20;
const modeSwitchedCreateScene = planStoryStructureCommand(modeSwitchedStructure, {
  kind: "create_scene",
  act: "Act I",
  chapter: "",
  title: "After mode switch",
  episodeId: 10,
});
check(
  modeSwitchedCreateScene.plan?.body.kind === "create_scene"
    && modeSwitchedCreateScene.plan.body.index === 2,
  "non-Series append must count every sibling even when legacy Episode ids remain after a mode switch",
);
check(
  planStoryStructureCommand(flatStructure, {
    kind: "create_chapter", act: "Act I", chapter: "Not used", title: "Seed", episodeId: 10,
  }).error?.includes("does not use Chapters"),
  "flat modes should not advertise a transactional Chapter creation",
);

const seriesCreateAct = planStoryStructureCommand(structure, {
  kind: "create_act",
  act: "Episode-only Act",
  chapter: "Chapter 1",
  title: "Seed",
  episodeId: 20,
}, true);
check(
  seriesCreateAct.plan?.body.kind === "create_act"
    && seriesCreateAct.plan.body.index === 1
    && seriesCreateAct.plan.body.chapter === "Chapter 1",
  "Series Act indexes should count only containers represented in the selected Episode",
);
check(
  planStoryStructureCommand(structure, {
    kind: "create_act", act: "Act I", chapter: "Chapter 1", title: "Seed", episodeId: 20,
  }, true).plan?.body.kind === "create_act",
  "an Act label used only by another Episode should not be treated as a Series collision",
);
check(
  planStoryStructureCommand(structure, {
    kind: "create_act", act: "Act II", chapter: "Chapter 1", title: "Seed", episodeId: 20,
  }, true).error?.includes("already exists"),
  "a Series Act label collision inside the selected Episode should be rejected",
);

const episodeSplitChapters = structuredClone(structure);
episodeSplitChapters.acts[0]!.chapters[0]!.scenes[1]!.episode_id = 20;
const seriesCreateChapter = planStoryStructureCommand(episodeSplitChapters, {
  kind: "create_chapter",
  act: "Act I",
  chapter: "Chapter B",
  title: "Episode chapter seed",
  episodeId: 20,
}, true);
check(
  seriesCreateChapter.plan?.body.kind === "create_chapter"
    && seriesCreateChapter.plan.body.index === 1
    && seriesCreateChapter.plan.body.episode_id === 20,
  "Series Chapter duplicate and index calculations should ignore matching containers owned only by another Episode",
);
const seriesRenameChapter = planStoryStructureCommand(episodeSplitChapters, {
  kind: "rename_chapter",
  act: "Act I",
  chapter: "Chapter A",
  newName: "Chapter B",
  episodeId: 20,
}, true);
check(
  seriesRenameChapter.plan?.body.kind === "rename_chapter"
    && seriesRenameChapter.plan.body.episode_id === 20,
  "Series Chapter rename should allow a label that collides only outside the selected Episode",
);

const seriesRenameAct = planStoryStructureCommand(structure, {
  kind: "rename_act",
  act: "Act II",
  newName: "Act I",
  episodeId: 20,
}, true);
check(
  seriesRenameAct.plan?.body.kind === "rename_act"
    && seriesRenameAct.plan.body.episode_id === 20
    && seriesRenameAct.plan.focusSceneId === 5,
  "Series Act rename should scope its body and focus to the selected Episode",
);
check(
  planStoryStructureCommand(structure, {
    kind: "rename_act", act: "Act II", newName: "Act I", episodeId: 10,
  }, true).error?.includes("already exists"),
  "Series rename collisions should be checked inside, but not across, Episodes",
);

const seriesDetachChapter = planStoryStructureCommand(structure, {
  kind: "detach_chapter",
  act: "Act II",
  chapter: "Chapter C",
  episodeId: 20,
}, true);
check(
  seriesDetachChapter.plan?.body.kind === "detach_chapter"
    && seriesDetachChapter.plan.body.episode_id === 20
    && seriesDetachChapter.plan.focusSceneId === 5,
  "Series Chapter detach should never omit its selected Episode scope",
);
const seriesWithUnassignedEpisode = structuredClone(structure);
seriesWithUnassignedEpisode.acts[0]!.chapters[0]!.scenes[0]!.episode_id = null;
const unassignedEpisodeRename = planStoryStructureCommand(seriesWithUnassignedEpisode, {
  kind: "rename_act",
  act: "Act I",
  newName: "Unassigned Episode Act",
  episodeId: null,
}, true);
check(
  unassignedEpisodeRename.plan?.body.kind === "rename_act"
    && Object.hasOwn(unassignedEpisodeRename.plan.body, "episode_id")
    && unassignedEpisodeRename.plan.body.episode_id === null,
  "Series container commands should send explicit null for the unassigned Episode scope",
);
check(
  planStoryStructureCommand(structure, {
    kind: "rename_chapter",
    act: "Act I",
    chapter: "Chapter A",
    newName: "Episode chapter",
    episodeId: 20,
  }, true).error?.includes("selected Episode"),
  "Series container actions should reject a label that has no descendants in the selected Episode",
);

const episodeChoices = episodeChoicesForScenes([scene(1, 1, null), scene(2, 2, 10)], [10, 20], true);
check(
  episodeChoices.join(",") === ",10,20",
  "Series choices should merge scene ownership, empty catalog Episodes, and explicit unassigned scope",
);

console.log(`${assertions} story-structure placement assertions passed.`);
