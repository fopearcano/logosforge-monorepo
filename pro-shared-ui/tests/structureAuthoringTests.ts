import type { StoryStructureDTO } from "@logosforge/ui-contracts";
import { planAppendSceneCommand } from "../src/components/manuscript/structureAuthoring";

function check(value: unknown, message: string): asserts value {
  if (!value) throw new Error(message);
}

function structure(
  value: Partial<StoryStructureDTO> = {},
): StoryStructureDTO {
  return {
    project_id: 7,
    revision: "a".repeat(64),
    chapter_level: true,
    scene_count: 0,
    orphan_count: 0,
    acts: [],
    ...value,
  };
}

{
  const command = planAppendSceneCommand(structure(), "Scene 1", false);
  check(command.kind === "create_act", "empty manuscripts must seed an Act atomically");
  check(command.act === "Act 1" && command.chapter === "Chapter 1", "empty Novel must seed a complete parent path");
  check(command.index === 0 && !("episode_id" in command), "non-Series seed must use the first Act position without episode data");
}

{
  const command = planAppendSceneCommand(structure({
    acts: [{
      name: "Act 1", number: "1", unassigned: false, scene_count: 1,
      chapters: [{
        name: "Unassigned Chapter", number: "", unassigned: true, scene_count: 1,
        scenes: [{ id: 1, title: "Orphan", beat: "", number: "1.1", order_index: 0, is_orphan: true, episode_id: null }],
      }],
    }],
    scene_count: 1,
    orphan_count: 1,
  }), "Scene 2", false);
  check(command.kind === "create_chapter", "Novel with no named Chapter must seed one instead of adding another orphan");
  check(command.act === "Act 1" && command.chapter === "Chapter 1", "Chapter seed must stay in the existing Act");
}

const novel = structure({
  scene_count: 2,
  acts: [{
    name: "Act 1", number: "1", unassigned: false, scene_count: 2,
    chapters: [{
      name: "Chapter 1", number: "1.1", unassigned: false, scene_count: 2,
      scenes: [
        { id: 1, title: "One", beat: "", number: "1.1.1", order_index: 0, is_orphan: false, episode_id: null },
        { id: 2, title: "Two", beat: "", number: "1.1.2", order_index: 1, is_orphan: false, episode_id: null },
      ],
    }],
  }],
});

{
  const command = planAppendSceneCommand(novel, "Scene 3", false);
  check(command.kind === "create_scene", "complete structures must append a Scene rather than seed another parent");
  check(command.act === "Act 1" && command.chapter === "Chapter 1" && command.index === 2, "Novel append must target the last named sibling group");
}

{
  const command = planAppendSceneCommand(structure({
    chapter_level: false,
    scene_count: 1,
    acts: [{
      name: "Act 1", number: "1", unassigned: false, scene_count: 1,
      chapters: [{
        name: "Unassigned Chapter", number: "", unassigned: true, scene_count: 1,
        scenes: [{ id: 1, title: "One", beat: "", number: "1.1", order_index: 0, is_orphan: false, episode_id: null }],
      }],
    }],
  }), "Scene 2", false);
  check(command.kind === "create_scene" && command.chapter === "", "flat modes must map the display-only unassigned Chapter back to the stored empty label");
}

{
  const command = planAppendSceneCommand(structure({
    chapter_level: false,
    scene_count: 3,
    acts: [{
      name: "Act 1", number: "1", unassigned: false, scene_count: 3,
      chapters: [{
        name: "Chapter 1", number: "", unassigned: false, scene_count: 3,
        scenes: [
          { id: 1, title: "E1", beat: "", number: "1.1", order_index: 0, is_orphan: false, episode_id: 10 },
          { id: 2, title: "E2a", beat: "", number: "1.2", order_index: 1, is_orphan: false, episode_id: 20 },
          { id: 3, title: "E2b", beat: "", number: "1.3", order_index: 2, is_orphan: false, episode_id: 20 },
        ],
      }],
    }],
  }), "Scene 4", true);
  check(command.kind === "create_scene", "Series append must remain a scene command");
  check(command.chapter === "Chapter 1", "Series append must keep a named Chapter despite flat global numbering");
  check(command.episode_id === 20 && command.index === 2, "Series index must be counted only among destination Episode siblings");
}

{
  const command = planAppendSceneCommand(structure({
    chapter_level: false,
    scene_count: 2,
    orphan_count: 1,
    acts: [{
      name: "Act 1", number: "1", unassigned: false, scene_count: 2,
      chapters: [
        {
          name: "Chapter 1", number: "", unassigned: false, scene_count: 1,
          scenes: [{ id: 1, title: "E1", beat: "", number: "1.1", order_index: 0, is_orphan: false, episode_id: 10 }],
        },
        {
          name: "Unassigned", number: "", unassigned: true, scene_count: 1,
          scenes: [{ id: 2, title: "E2 orphan", beat: "", number: "1.2", order_index: 1, is_orphan: true, episode_id: 20 }],
        },
      ],
    }],
  }), "Scene 3", true);
  check(command.kind === "create_chapter", "Series with a Chapter orphan in the target Episode must seed a valid Chapter");
  check(command.act === "Act 1" && command.chapter === "Chapter 1", "Series Chapter seed must stay in the Episode-local Act");
  check(command.episode_id === 20, "Series parent seed must remain in the target Episode");
}

{
  const command = planAppendSceneCommand(structure({
    chapter_level: false,
    scene_count: 2,
    orphan_count: 1,
    acts: [
      {
        name: "Act 1", number: "1", unassigned: false, scene_count: 1,
        chapters: [{
          name: "Chapter 1", number: "", unassigned: false, scene_count: 1,
          scenes: [{ id: 1, title: "E1", beat: "", number: "1.1", order_index: 0, is_orphan: false, episode_id: 10 }],
        }],
      },
      {
        name: "Unassigned", number: "", unassigned: true, scene_count: 1,
        chapters: [{
          name: "Unassigned", number: "", unassigned: true, scene_count: 1,
          scenes: [{ id: 2, title: "E2 orphan", beat: "", number: "", order_index: 1, is_orphan: true, episode_id: 20 }],
        }],
      },
    ],
  }), "Scene 3", true);
  check(command.kind === "create_act", "Series with no named Act in the target Episode must seed a valid Act");
  check(command.act === "Act 1" && command.chapter === "Chapter 1", "Series Act seed must include a named Chapter");
  check(command.episode_id === 20, "Series Act seed must remain in the target Episode");
}

console.log("structure authoring tests passed");
