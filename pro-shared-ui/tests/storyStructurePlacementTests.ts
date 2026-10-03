import type { StoryStructureDTO } from "@logosforge/ui-contracts";
import {
  createScenePlacementDraft,
  flattenStoryStructure,
  isImmediateScenePlacementNeighbor,
  placeScenePlacementDraft,
  scenePlacementPlan,
  stepScenePlacementDraft,
} from "../src/components/shell/storyStructurePlacement";

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

console.log(`${assertions} story-structure placement assertions passed.`);
