import type { EpisodeDTO, SeasonDTO, SeriesArcDTO } from "@logosforge/ui-contracts";
import type { ApiClient } from "../adapters/api";

export interface SeriesSnapshot {
  seasons: SeasonDTO[];
  episodes: EpisodeDTO[];
  arcs: SeriesArcDTO[];
}

/** Load the Series navigator as one all-or-error snapshot. */
export async function loadSeriesSnapshot(api: ApiClient, projectId: number): Promise<SeriesSnapshot> {
  const [seasons, episodes, arcs] = await Promise.all([
    api.listSeasons(projectId),
    api.listEpisodes(projectId),
    api.listSeriesArcs(projectId),
  ]);
  return { seasons, episodes, arcs };
}
