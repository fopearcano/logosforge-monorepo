import type {
  StoryStructureCommandDTO,
  StoryStructureDTO,
} from "@logosforge/ui-contracts";

/** Pick a stable human label without merging with an existing derived group. */
function nextNumberedLabel(prefix: string, existing: readonly string[]): string {
  const occupied = new Set(existing.map((value) => value.trim().toLocaleLowerCase()));
  let number = 1;
  while (occupied.has(`${prefix} ${number}`.toLocaleLowerCase())) number += 1;
  return `${prefix} ${number}`;
}

function episodeFields(isSeries: boolean, episodeId: number | null | undefined) {
  return isSeries ? { episode_id: episodeId ?? null } : {};
}

/**
 * Plan the Manuscript/Story Grid "add scene" action against one authoritative
 * structure revision. Empty or structurally incomplete projects are repaired by
 * seeding the missing parent, so these generic writing surfaces never create a
 * new orphan through the legacy Scene endpoint.
 */
export function planAppendSceneCommand(
  structure: StoryStructureDTO,
  title: string,
  isSeries: boolean,
): StoryStructureCommandDTO {
  const allScenes = structure.acts.flatMap((act) => (
    act.chapters.flatMap((chapter) => chapter.scenes)
  ));
  const episodeId = isSeries ? (allScenes.at(-1)?.episode_id ?? null) : null;
  const inEpisode = (scene: { episode_id: number | null }): boolean => (
    !isSeries || scene.episode_id === episodeId
  );
  const namedActs = structure.acts.filter((act) => (
    !act.unassigned
    && (!isSeries || act.chapters.some((chapter) => chapter.scenes.some(inEpisode)))
  ));
  const requiresChapter = structure.chapter_level || isSeries;

  if (namedActs.length === 0) {
    return {
      kind: "create_act",
      expected_revision: structure.revision,
      act: nextNumberedLabel("Act", namedActs.map((act) => act.name)),
      chapter: requiresChapter ? "Chapter 1" : undefined,
      title,
      index: 0,
      ...episodeFields(isSeries, episodeId),
    };
  }

  const act = namedActs.at(-1)!;
  if (requiresChapter) {
    const namedChapters = act.chapters.filter((chapter) => (
      !chapter.unassigned
      && (!isSeries || chapter.scenes.some(inEpisode))
    ));
    if (namedChapters.length === 0) {
      return {
        kind: "create_chapter",
        expected_revision: structure.revision,
        act: act.name,
        chapter: nextNumberedLabel(
          "Chapter",
          namedChapters.map((chapter) => chapter.name),
        ),
        title,
        index: 0,
        ...episodeFields(isSeries, episodeId),
      };
    }
    const chapter = namedChapters.at(-1)!;
    const index = chapter.scenes.filter(inEpisode).length;
    return {
      kind: "create_scene",
      expected_revision: structure.revision,
      act: act.name,
      chapter: chapter.name,
      title,
      index,
      ...episodeFields(isSeries, episodeId),
    };
  }

  // Non-chapter modes still use the canonical tree's internal chapter bucket;
  // its unassigned display label maps back to the stored empty string.
  const chapter = act.chapters.at(-1);
  if (!chapter) {
    return {
      kind: "create_chapter",
      expected_revision: structure.revision,
      act: act.name,
      chapter: "Chapter 1",
      title,
      index: 0,
      ...episodeFields(isSeries, episodeId),
    };
  }
  const index = chapter.scenes.filter(inEpisode).length;
  return {
    kind: "create_scene",
    expected_revision: structure.revision,
    act: act.name,
    chapter: chapter.unassigned ? "" : chapter.name,
    title,
    index,
    ...episodeFields(isSeries, episodeId),
  };
}
