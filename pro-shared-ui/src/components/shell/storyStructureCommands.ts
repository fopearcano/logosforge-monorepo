import type {
  StoryStructureActDTO,
  StoryStructureChapterDTO,
  StoryStructureCommandDTO,
  StoryStructureDTO,
  StoryStructureSceneDTO,
} from "@logosforge/ui-contracts";

export type StoryStructureCommandIntent =
  | { kind: "create_scene"; act: string; chapter: string; title: string; episodeId: number | null }
  | { kind: "create_act"; act: string; chapter: string; title: string; episodeId: number | null }
  | { kind: "create_chapter"; act: string; chapter: string; title: string; episodeId: number | null }
  | { kind: "rename_act"; act: string; newName: string; episodeId: number | null }
  | { kind: "rename_chapter"; act: string; chapter: string; newName: string; episodeId: number | null }
  | { kind: "detach_act"; act: string; episodeId: number | null }
  | { kind: "detach_chapter"; act: string; chapter: string; episodeId: number | null }
  | { kind: "delete_scene"; sceneId: number }
  | { kind: "repair_orphans" };

export interface PlannedStoryStructureCommand {
  body: StoryStructureCommandDTO;
  focusSceneId: number | null;
}

export type StoryStructureCommandPlanResult =
  | { plan: PlannedStoryStructureCommand; error?: never }
  | { plan?: never; error: string };

export function storedStructureLabel(name: string, unassigned: boolean): string {
  return unassigned ? "" : name;
}

function comparable(value: string): string {
  return value.trim().toLocaleLowerCase();
}

function sameEpisode(scene: StoryStructureSceneDTO, episodeId: number | null): boolean {
  return scene.episode_id === episodeId;
}

function actStoredName(act: StoryStructureActDTO): string {
  return storedStructureLabel(act.name, act.unassigned);
}

function chapterStoredName(chapter: StoryStructureChapterDTO): string {
  return storedStructureLabel(chapter.name, chapter.unassigned);
}

function findAct(structure: StoryStructureDTO, name: string): StoryStructureActDTO | undefined {
  return structure.acts.find((act) => actStoredName(act) === name);
}

function findChapter(act: StoryStructureActDTO, name: string): StoryStructureChapterDTO | undefined {
  return act.chapters.find((chapter) => chapterStoredName(chapter) === name);
}

function actScenes(act: StoryStructureActDTO): StoryStructureSceneDTO[] {
  return act.chapters.flatMap((chapter) => chapter.scenes);
}

function scopedScenes(
  scenes: readonly StoryStructureSceneDTO[],
  episodeId: number | null,
  isSeries: boolean,
): StoryStructureSceneDTO[] {
  return isSeries ? scenes.filter((scene) => sameEpisode(scene, episodeId)) : [...scenes];
}

function firstSceneId(
  act: StoryStructureActDTO | undefined,
  chapter: StoryStructureChapterDTO | undefined,
  episodeId: number | null,
  isSeries: boolean,
): number | null {
  return scopedScenes(chapter?.scenes ?? (act ? actScenes(act) : []), episodeId, isSeries)[0]?.id
    ?? null;
}

function actExistsInScope(
  act: StoryStructureActDTO | undefined,
  episodeId: number | null,
  isSeries: boolean,
): act is StoryStructureActDTO {
  return Boolean(act && (!isSeries || scopedScenes(actScenes(act), episodeId, true).length > 0));
}

function chapterExistsInScope(
  chapter: StoryStructureChapterDTO | undefined,
  episodeId: number | null,
  isSeries: boolean,
): chapter is StoryStructureChapterDTO {
  return Boolean(chapter && (!isSeries || scopedScenes(chapter.scenes, episodeId, true).length > 0));
}

function trimmed(value: string, label: string): { value: string } | { error: string } {
  const next = value.trim();
  return next ? { value: next } : { error: `${label} cannot be empty.` };
}

function unavailable(noun: "Act" | "Chapter", isSeries: boolean): string {
  return isSeries
    ? `That ${noun} is no longer available in the selected Episode.`
    : `That ${noun} is no longer available.`;
}

/**
 * Build a command from the latest authoritative tree, never from the tree that
 * happened to be visible when an editor was opened. Indexes are calculated in
 * the selected Series episode and exclude the synthetic Unassigned wrappers.
 */
export function planStoryStructureCommand(
  structure: StoryStructureDTO,
  intent: StoryStructureCommandIntent,
  isSeries = false,
): StoryStructureCommandPlanResult {
  const expected_revision = structure.revision;

  if (intent.kind === "create_act") {
    const actName = trimmed(intent.act, "Act name");
    if ("error" in actName) return { error: actName.error };
    if (structure.acts.some((act) => !act.unassigned
      && comparable(act.name) === comparable(actName.value)
      && (!isSeries || scopedScenes(actScenes(act), intent.episodeId, true).length > 0))) {
      return { error: `An Act named “${actName.value}” already exists.` };
    }
    const chapterName = intent.chapter.trim();
    const title = intent.title.trim();
    return {
      plan: {
        body: {
          kind: "create_act",
          expected_revision,
          act: actName.value,
          ...(chapterName ? { chapter: chapterName } : {}),
          ...(title ? { title } : {}),
          index: structure.acts.filter((act) => !act.unassigned
            && (!isSeries || scopedScenes(actScenes(act), intent.episodeId, true).length > 0)).length,
          episode_id: intent.episodeId,
        },
        focusSceneId: null,
      },
    };
  }

  if (intent.kind === "create_chapter") {
    if (!structure.chapter_level && !isSeries) return { error: "This project type does not use Chapters." };
    const act = findAct(structure, intent.act);
    if (!actExistsInScope(act, intent.episodeId, isSeries) || act.unassigned) {
      return { error: unavailable("Act", isSeries) };
    }
    const chapterName = trimmed(intent.chapter, "Chapter name");
    if ("error" in chapterName) return { error: chapterName.error };
    if (act.chapters.some((chapter) => !chapter.unassigned
      && comparable(chapter.name) === comparable(chapterName.value)
      && (!isSeries || scopedScenes(chapter.scenes, intent.episodeId, true).length > 0))) {
      return { error: `A Chapter named “${chapterName.value}” already exists in this Act.` };
    }
    const title = intent.title.trim();
    return {
      plan: {
        body: {
          kind: "create_chapter",
          expected_revision,
          act: intent.act,
          chapter: chapterName.value,
          ...(title ? { title } : {}),
          index: act.chapters.filter((chapter) => !chapter.unassigned
            && (!isSeries || scopedScenes(chapter.scenes, intent.episodeId, true).length > 0)).length,
          episode_id: intent.episodeId,
        },
        focusSceneId: firstSceneId(act, undefined, intent.episodeId, isSeries),
      },
    };
  }

  if (intent.kind === "create_scene") {
    const act = findAct(structure, intent.act);
    const chapter = act ? findChapter(act, intent.chapter) : undefined;
    if (!actExistsInScope(act, intent.episodeId, isSeries)
      || act.unassigned
      || !chapterExistsInScope(chapter, intent.episodeId, isSeries)
      || ((structure.chapter_level || isSeries) && chapter.unassigned)) {
      return { error: "That Act or Chapter is no longer available." };
    }
    const title = intent.title.trim();
    return {
      plan: {
        body: {
          kind: "create_scene",
          expected_revision,
          ...(title ? { title } : {}),
          act: intent.act,
          chapter: intent.chapter,
          index: scopedScenes(chapter.scenes, intent.episodeId, isSeries).length,
          episode_id: intent.episodeId,
        },
        focusSceneId: firstSceneId(act, chapter, intent.episodeId, isSeries),
      },
    };
  }

  if (intent.kind === "rename_act") {
    const act = findAct(structure, intent.act);
    if (!actExistsInScope(act, intent.episodeId, isSeries) || act.unassigned) {
      return { error: unavailable("Act", isSeries) };
    }
    const nextName = trimmed(intent.newName, "Act name");
    if ("error" in nextName) return { error: nextName.error };
    if (comparable(nextName.value) === comparable(intent.act)) return { error: "Enter a different Act name." };
    if (structure.acts.some((item) => item !== act && !item.unassigned
      && comparable(item.name) === comparable(nextName.value)
      && (!isSeries || scopedScenes(actScenes(item), intent.episodeId, true).length > 0))) {
      return { error: `An Act named “${nextName.value}” already exists.` };
    }
    return {
      plan: {
        body: {
          kind: "rename_act",
          expected_revision,
          act: intent.act,
          new_name: nextName.value,
          ...(isSeries ? { episode_id: intent.episodeId } : {}),
        },
        focusSceneId: firstSceneId(act, undefined, intent.episodeId, isSeries),
      },
    };
  }

  if (intent.kind === "rename_chapter") {
    const act = findAct(structure, intent.act);
    const chapter = act ? findChapter(act, intent.chapter) : undefined;
    if (!actExistsInScope(act, intent.episodeId, isSeries)
      || !chapterExistsInScope(chapter, intent.episodeId, isSeries)
      || chapter.unassigned) {
      return { error: unavailable("Chapter", isSeries) };
    }
    const nextName = trimmed(intent.newName, "Chapter name");
    if ("error" in nextName) return { error: nextName.error };
    if (comparable(nextName.value) === comparable(intent.chapter)) return { error: "Enter a different Chapter name." };
    if (act.chapters.some((item) => item !== chapter && !item.unassigned
      && comparable(item.name) === comparable(nextName.value)
      && (!isSeries || scopedScenes(item.scenes, intent.episodeId, true).length > 0))) {
      return { error: `A Chapter named “${nextName.value}” already exists in this Act.` };
    }
    return {
      plan: {
        body: {
          kind: "rename_chapter",
          expected_revision,
          act: intent.act,
          chapter: intent.chapter,
          new_name: nextName.value,
          ...(isSeries ? { episode_id: intent.episodeId } : {}),
        },
        focusSceneId: firstSceneId(act, chapter, intent.episodeId, isSeries),
      },
    };
  }

  if (intent.kind === "detach_act") {
    const act = findAct(structure, intent.act);
    if (!actExistsInScope(act, intent.episodeId, isSeries) || act.unassigned) {
      return { error: unavailable("Act", isSeries) };
    }
    return {
      plan: {
        body: {
          kind: "detach_act",
          expected_revision,
          act: intent.act,
          ...(isSeries ? { episode_id: intent.episodeId } : {}),
        },
        focusSceneId: firstSceneId(act, undefined, intent.episodeId, isSeries),
      },
    };
  }

  if (intent.kind === "detach_chapter") {
    const act = findAct(structure, intent.act);
    const chapter = act ? findChapter(act, intent.chapter) : undefined;
    if (!actExistsInScope(act, intent.episodeId, isSeries)
      || !chapterExistsInScope(chapter, intent.episodeId, isSeries)
      || chapter.unassigned) {
      return { error: unavailable("Chapter", isSeries) };
    }
    return {
      plan: {
        body: {
          kind: "detach_chapter",
          expected_revision,
          act: intent.act,
          chapter: intent.chapter,
          ...(isSeries ? { episode_id: intent.episodeId } : {}),
        },
        focusSceneId: firstSceneId(act, chapter, intent.episodeId, isSeries),
      },
    };
  }

  if (intent.kind === "delete_scene") {
    const entries = structure.acts.flatMap((act) => act.chapters.flatMap((chapter) => chapter.scenes));
    const index = entries.findIndex((scene) => scene.id === intent.sceneId);
    if (index < 0) return { error: "That Scene is no longer available." };
    return {
      plan: {
        body: { kind: "delete_scene", expected_revision, scene_id: intent.sceneId },
        focusSceneId: entries[index + 1]?.id ?? entries[index - 1]?.id ?? null,
      },
    };
  }

  return {
    plan: {
      body: { kind: "repair_orphans", expected_revision },
      focusSceneId: structure.acts
        .flatMap((act) => act.chapters.flatMap((chapter) => chapter.scenes))
        .find((scene) => scene.is_orphan)?.id ?? null,
    },
  };
}

export function episodeChoicesForScenes(
  scenes: readonly StoryStructureSceneDTO[],
  availableEpisodeIds: readonly number[] = [],
  includeUnassigned = false,
): Array<number | null> {
  const choices: Array<number | null> = [];
  for (const scene of scenes) {
    if (!choices.includes(scene.episode_id)) choices.push(scene.episode_id);
  }
  for (const episodeId of availableEpisodeIds) {
    if (!choices.includes(episodeId)) choices.push(episodeId);
  }
  if (includeUnassigned && !choices.includes(null)) choices.push(null);
  return choices.length > 0 ? choices : [null];
}
