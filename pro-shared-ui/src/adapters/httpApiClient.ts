import { ROUTES, KNOWN_EVENTS, type EventMessage } from "@logosforge/ui-contracts";
import type { ApiClient } from "./api";

/**
 * `createHttpApiClient(baseUrl)` — the reference {@link ApiClient} over the
 * logosforge core HTTP API (FastAPI), built on `fetch` + `EventSource` (SSE).
 * Both are web standards available in an Electron renderer and a plain browser,
 * so this single implementation serves both Pro apps:
 *   - pro-desktop → baseUrl = the in-process core (e.g. "http://127.0.0.1:8765")
 *   - pro-web     → baseUrl = the configured remote host (or "" behind a proxy)
 *
 * The host app constructs it and injects it via `<StudioProvider services={{ api }}>`;
 * components only ever call the {@link ApiClient} interface. It knows only the
 * route map + DTOs from `@logosforge/ui-contracts` — no auth, routing, or
 * storage (those stay in the app shell).
 */
export function createHttpApiClient(baseUrl = ""): ApiClient {
  async function req(path: string, init?: RequestInit): Promise<any> {
    const res = await fetch(baseUrl + path, { headers: { "content-type": "application/json" }, ...init });
    if (!res.ok) {
      const detail = await res.text().catch(() => "");
      throw new Error(`${init?.method ?? "GET"} ${path} → ${res.status}${detail ? " · " + detail.slice(0, 200) : ""}`);
    }
    if (res.status === 204) return undefined;
    const ct = res.headers.get("content-type") ?? "";
    return ct.includes("application/json") ? res.json() : res.text();
  }
  const get = (p: string) => req(p);
  const post = (p: string, body?: unknown) => req(p, { method: "POST", body: body == null ? undefined : JSON.stringify(body) });
  const patch = (p: string, body: unknown) => req(p, { method: "PATCH", body: JSON.stringify(body) });
  const put = (p: string, body: unknown) => req(p, { method: "PUT", body: JSON.stringify(body) });
  const del = (p: string) => req(p, { method: "DELETE" });

  return {
    health: () => get(ROUTES.health),
    writingModes: () => get(ROUTES.writingModes),
    listProjects: () => get(ROUTES.projects),
    createProject: (b) => post(ROUTES.projects, b),
    getProject: (id) => get(ROUTES.project(id)),
    openProject: (id) => post(ROUTES.projectOpen(id)),
    saveProject: (id) => post(ROUTES.projectSave(id)),
    closeProject: (id) => post(ROUTES.projectClose(id)),
    getSettings: (id) => get(ROUTES.projectSettings(id)),
    patchSettings: (id, b) => patch(ROUTES.projectSettings(id), b),

    listScenes: (p) => get(ROUTES.scenes(p)),
    createScene: (p, b) => post(ROUTES.scenes(p), b),
    updateScene: (p, s, b) => patch(ROUTES.scene(p, s), b),
    deleteScene: (p, s) => del(ROUTES.scene(p, s)),
    listContinuity: (p, s) => get(ROUTES.sceneContinuity(p, s)),
    addContinuity: (p, s, b) => post(ROUTES.sceneContinuity(p, s), b),

    getOutline: (p) => get(ROUTES.outline(p)),
    createOutlineNode: (p, b) => post(ROUTES.outlineNodes(p), b),
    updateOutlineNode: (p, n, b) => patch(ROUTES.outlineNode(p, n), b),
    deleteOutlineNode: (p, n) => del(ROUTES.outlineNode(p, n)),

    getPlot: (p) => get(ROUTES.plot(p)),
    updatePlotBlock: (p, id, b) => patch(`${ROUTES.plot(p)}/${encodeURIComponent(id)}`, b),
    getTimeline: (p) => get(ROUTES.timeline(p)),
    updateTimelineEvent: (p, id, b) => patch(`${ROUTES.timeline(p)}/${id}`, b),

    listPsyke: (p) => get(ROUTES.psykeEntries(p)),
    searchPsyke: (p, q) => get(`${ROUTES.psykeSearch(p)}?q=${encodeURIComponent(q)}`),
    createPsyke: (p, b) => post(ROUTES.psykeEntries(p), b),
    updatePsyke: (p, e, b) => patch(ROUTES.psykeEntry(p, e), b),
    deletePsyke: (p, e) => del(ROUTES.psykeEntry(p, e)),
    listRelations: (p) => get(ROUTES.psykeRelations(p)),
    createRelation: (p, b) => post(ROUTES.psykeRelations(p), b),
    listProgressions: (p) => get(ROUTES.psykeProgressions(p)),
    createProgression: (p, b) => post(ROUTES.psykeProgressions(p), b),

    listNotes: (p) => get(ROUTES.notes(p)),
    createNote: (p, b) => post(ROUTES.notes(p), b),
    updateNote: (p, n, b) => patch(ROUTES.note(p, n), b),
    deleteNote: (p, n) => del(ROUTES.note(p, n)),

    listCharacters: (p) => get(ROUTES.characters(p)),
    updateCharacter: (p, c, b) => patch(ROUTES.character(p, c), b),
    backfillCharacterLinks: (p) => post(ROUTES.characterBackfillLinks(p)),

    getThemeScenes: (p, entryId) => get(ROUTES.themeScenes(p, entryId)),
    setThemeScenes: (p, entryId, sceneIds) => put(ROUTES.themeScenes(p, entryId), { scene_ids: sceneIds }),

    assistantChat: (p, b) => post(ROUTES.assistantChat(p), b),
    assistantAction: (p, b) => post(ROUTES.assistantAction(p), b),
    listLogosActions: (p, section, writingMode) => {
      const q = new URLSearchParams();
      if (section) q.set("section", section);
      if (writingMode) q.set("writing_mode", writingMode);
      const qs = q.toString();
      return get(ROUTES.logosActions(p) + (qs ? `?${qs}` : ""));
    },
    runLogos: (p, b) => post(ROUTES.logosRun(p), b),
    listLogosProactive: (p, section) => get(ROUTES.logosProactive(p) + (section ? `?section=${encodeURIComponent(section)}` : "")),
    getAssistantSettings: (p) => get(ROUTES.assistantSettings(p)),
    patchAssistantSettings: (p, b) => patch(ROUTES.assistantSettings(p), b),
    listConnectorActions: (p) => get(ROUTES.connectorActions(p)),
    connectorExecute: (p, b) => post(ROUTES.connectorExecute(p), b),

    export: (p, b) => post(ROUTES.export(p), b),

    getDashboard: (p) => get(ROUTES.dashboard(p)),
    getContinuity: (p) => get(ROUTES.continuity(p)),
    getPacing: (p) => get(ROUTES.pacing(p)),
    getBalance: (p) => get(ROUTES.balance(p)),
    getStoryHealth: (p) => get(ROUTES.storyHealth(p)),
    getStructureAnalysis: (p) => get(ROUTES.structureAnalysis(p)),
    getWorkflows: (p) => get(ROUTES.workflows(p)),
    getDecisionRadar: (p) => get(ROUTES.decisionRadar(p)),
    getGraphGravity: (p) => get(ROUTES.graphGravity(p)),
    generateQuantumOutline: (p, b) => post(ROUTES.quantumOutline(p), b),
    generateQuantumBranches: (p, b) => post(ROUTES.quantumBranches(p), b),
    runCounterpart: (p, b) => post(ROUTES.counterpart(p), b),

    startExtract: (p, useLlm = true, model) =>
      post(`${ROUTES.extract(p)}?use_llm=${useLlm}${model ? `&model=${encodeURIComponent(model)}` : ""}`),
    listExtractionModels: (p) => get(ROUTES.extractModels(p)),
    getExtractJob: (p, jobId) => get(ROUTES.extractJob(p, jobId)),
    applyExtraction: (p, b) => post(ROUTES.extractApply(p), b),
    revertExtraction: (p, receipt) => post(ROUTES.extractRevert(p), receipt),

    listGnPages: (p) => get(ROUTES.gnPages(p)),
    createGnPage: (p, b) => post(ROUTES.gnPages(p), b),
    syncGnFromScenes: (p) => post(ROUTES.gnSyncFromScenes(p)),
    listGnContinuityItems: (p) => get(ROUTES.gnContinuityItems(p)),
    createGnContinuityItem: (p, b) => post(ROUTES.gnContinuityItems(p), b),
    listGnContinuityAppearances: (p, itemId) => get(ROUTES.gnContinuityAppearances(p, itemId)),
    createGnContinuityAppearance: (p, itemId, b) => post(ROUTES.gnContinuityAppearances(p, itemId), b),
    listGnPanels: (p, pageId) => get(ROUTES.gnPanels(p, pageId)),
    createGnPanel: (p, pageId, b) => post(ROUTES.gnPanels(p, pageId), b),
    listStageCues: (p, sceneId) => get(ROUTES.stageCues(p, sceneId)),
    createStageCue: (p, sceneId, b) => post(ROUTES.stageCues(p, sceneId), b),
    listStageEntrances: (p, sceneId) => get(ROUTES.stageEntrances(p, sceneId)),
    createStageEntrance: (p, sceneId, b) => post(ROUTES.stageEntrances(p, sceneId), b),
    listStageBusiness: (p, sceneId) => get(ROUTES.stageBusiness(p, sceneId)),
    createStageBusiness: (p, sceneId, b) => post(ROUTES.stageBusiness(p, sceneId), b),
    syncStageFromScenes: (p) => post(ROUTES.stageSyncFromScenes(p)),
    listSeasons: (p) => get(ROUTES.seriesSeasons(p)),
    createSeason: (p, b) => post(ROUTES.seriesSeasons(p), b),
    listEpisodes: (p) => get(ROUTES.seriesEpisodes(p)),
    createEpisode: (p, seasonId, b) => post(ROUTES.seriesSeasonEpisodes(p, seasonId), b),
    listSeriesArcs: (p) => get(ROUTES.seriesArcs(p)),
    createSeriesArc: (p, b) => post(ROUTES.seriesArcs(p), b),
    listEpisodePlotlines: (p, episodeId) => get(ROUTES.episodePlotlines(p, episodeId)),
    createEpisodePlotline: (p, episodeId, b) => post(ROUTES.episodePlotlines(p, episodeId), b),
    getSeriesMemory: (p, entryId) => get(ROUTES.psykeSeriesMemory(p, entryId)),
    setSeriesMemory: (p, entryId, b) => put(ROUTES.psykeSeriesMemory(p, entryId), b),

    subscribe: (p, onEvent) => {
      if (typeof EventSource === "undefined") return () => {};
      let es: EventSource;
      try {
        es = new EventSource(baseUrl + ROUTES.events(p));
      } catch {
        return () => {};
      }
      const handler = (e: MessageEvent) => {
        try {
          onEvent(JSON.parse(e.data) as EventMessage);
        } catch {
          /* ignore keep-alive / non-JSON frames */
        }
      };
      for (const name of [...KNOWN_EVENTS, "connected"]) es.addEventListener(name, handler as EventListener);
      return () => es.close();
    },
  };
}
