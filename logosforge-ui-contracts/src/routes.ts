/**
 * API route map (under the `/api` prefix). Mirrors `logosforge.api`. Almost
 * everything is project-scoped: `/api/projects/{project_id}/<domain>`. The same
 * paths serve desktop (in-process / localhost:8765) and web (remote host).
 *
 * This is a convenience map; an app's injected `ApiClient` is the source of
 * truth for request/response shapes (see `@logosforge/ui-contracts` types).
 */

export const API_PREFIX = "/api";

export const ROUTES = {
  health: "/api/health",
  writingModes: "/api/writing-modes",

  // Projects
  projects: "/api/projects",
  project: (id: number) => `/api/projects/${id}`,
  projectOpen: (id: number) => `/api/projects/${id}/open`,
  projectSave: (id: number) => `/api/projects/${id}/save`,
  projectClose: (id: number) => `/api/projects/${id}/close`,
  projectSettings: (id: number) => `/api/projects/${id}/settings`,

  // Per-project domains (p = project id)
  scenes: (p: number) => `/api/projects/${p}/scenes`,
  scene: (p: number, sceneId: number) => `/api/projects/${p}/scenes/${sceneId}`,
  sceneContinuity: (p: number, sceneId: number) => `/api/projects/${p}/scenes/${sceneId}/continuity`,
  outline: (p: number) => `/api/projects/${p}/outline`,
  outlineNodes: (p: number) => `/api/projects/${p}/outline/nodes`,
  outlineNode: (p: number, nodeId: number) => `/api/projects/${p}/outline/nodes/${nodeId}`,
  plot: (p: number) => `/api/projects/${p}/plot`,
  timeline: (p: number) => `/api/projects/${p}/timeline`,
  psykeEntries: (p: number) => `/api/projects/${p}/psyke/entries`,
  psykeEntry: (p: number, entryId: number) => `/api/projects/${p}/psyke/entries/${entryId}`,
  psykeRelations: (p: number) => `/api/projects/${p}/psyke/relations`,
  psykeProgressions: (p: number) => `/api/projects/${p}/psyke/progressions`,
  psykeSearch: (p: number) => `/api/projects/${p}/psyke/search`,
  notes: (p: number) => `/api/projects/${p}/notes`,
  note: (p: number, noteId: number) => `/api/projects/${p}/notes/${noteId}`,
  characters: (p: number) => `/api/projects/${p}/characters`,
  character: (p: number, characterId: number) => `/api/projects/${p}/characters/${characterId}`,
  characterBackfillLinks: (p: number) => `/api/projects/${p}/characters/backfill-links`,
  themeScenes: (p: number, entryId: number) => `/api/projects/${p}/themes/${entryId}/scenes`,
  assistantChat: (p: number) => `/api/projects/${p}/assistant/chat`,
  assistantAction: (p: number) => `/api/projects/${p}/assistant/action`,
  assistantSettings: (p: number) => `/api/projects/${p}/assistant/settings`,
  logosActions: (p: number) => `/api/projects/${p}/logos/actions`,
  logosRun: (p: number) => `/api/projects/${p}/logos/run`,
  logosProactive: (p: number) => `/api/projects/${p}/logos/proactive`,
  connectorActions: (p: number) => `/api/projects/${p}/connector/actions`,
  connectorExecute: (p: number) => `/api/projects/${p}/connector/execute`,
  export: (p: number) => `/api/projects/${p}/export`,

  // Derived, read-only intelligence
  dashboard: (p: number) => `/api/projects/${p}/dashboard`,
  continuity: (p: number) => `/api/projects/${p}/continuity`,
  pacing: (p: number) => `/api/projects/${p}/pacing`,
  balance: (p: number) => `/api/projects/${p}/balance`,
  storyHealth: (p: number) => `/api/projects/${p}/health`,
  structureAnalysis: (p: number) => `/api/projects/${p}/structure-analysis`,
  workflows: (p: number) => `/api/projects/${p}/workflows`,
  decisionRadar: (p: number) => `/api/projects/${p}/decision-radar`,
  graphGravity: (p: number) => `/api/projects/${p}/graph/gravity`,

  // Generative (POST)
  quantumOutline: (p: number) => `/api/projects/${p}/quantum/outline`,
  quantumBranches: (p: number) => `/api/projects/${p}/quantum/branches`,
  counterpart: (p: number) => `/api/projects/${p}/counterpart`,
  extract: (p: number) => `/api/projects/${p}/extract`,
  extractJob: (p: number, jobId: string) => `/api/projects/${p}/extract/jobs/${jobId}`,
  extractModels: (p: number) => `/api/projects/${p}/extract/models`,
  extractApply: (p: number) => `/api/projects/${p}/extract/apply`,
  extractRevert: (p: number) => `/api/projects/${p}/extract/revert`,

  // Format-specific structured data (POST to create, GET to list)
  gnPages: (p: number) => `/api/projects/${p}/gn/pages`,
  gnSyncFromScenes: (p: number) => `/api/projects/${p}/gn/sync-from-scenes`,
  gnContinuityItems: (p: number) => `/api/projects/${p}/gn/continuity-items`,
  gnContinuityAppearances: (p: number, itemId: number) => `/api/projects/${p}/gn/continuity-items/${itemId}/appearances`,
  gnPanels: (p: number, pageId: number) => `/api/projects/${p}/gn/pages/${pageId}/panels`,
  stageEntrances: (p: number, sceneId: number) => `/api/projects/${p}/stage/scenes/${sceneId}/entrances`,
  stageCues: (p: number, sceneId: number) => `/api/projects/${p}/stage/scenes/${sceneId}/cues`,
  stageBusiness: (p: number, sceneId: number) => `/api/projects/${p}/stage/scenes/${sceneId}/business`,
  stageSyncFromScenes: (p: number) => `/api/projects/${p}/stage/sync-from-scenes`,
  seriesSeasons: (p: number) => `/api/projects/${p}/series/seasons`,
  seriesSeasonEpisodes: (p: number, seasonId: number) => `/api/projects/${p}/series/seasons/${seasonId}/episodes`,
  seriesEpisodes: (p: number) => `/api/projects/${p}/series/episodes`,
  seriesArcs: (p: number) => `/api/projects/${p}/series/arcs`,
  episodePlotlines: (p: number, episodeId: number) => `/api/projects/${p}/series/episodes/${episodeId}/plotlines`,
  psykeSeriesMemory: (p: number, entryId: number) => `/api/projects/${p}/psyke/${entryId}/series-memory`,

  // Live change events
  events: (p: number) => `/api/projects/${p}/events`, // SSE
  eventsPoll: (p: number) => `/api/projects/${p}/events/poll`,
} as const;
