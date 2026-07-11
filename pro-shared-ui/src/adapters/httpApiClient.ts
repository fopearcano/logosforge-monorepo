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

  /** Polling fallback for live sync when SSE (EventSource) isn't available.
   * Learns the current cursor on the first tick (no replay of history), then
   * dispatches only newer events every few seconds. */
  function startPolling(p: number, onEvent: (e: EventMessage) => void): () => void {
    let cursor = 0;
    let primed = false;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      if (stopped) return;
      try {
        const r = await get(`${ROUTES.eventsPoll(p)}?since=${cursor}`);
        if (r && typeof r.cursor === "number") {
          if (primed) for (const ev of r.events ?? []) { try { onEvent(ev as EventMessage); } catch { /* ignore */ } }
          cursor = r.cursor;
          primed = true;
        }
      } catch { /* transient; try again next tick */ }
      if (!stopped) timer = setTimeout(tick, 3000);
    };
    void tick();
    return () => { stopped = true; if (timer) clearTimeout(timer); };
  }

  /**
   * One live-event transport per project, fanned out to every subscriber.
   * Browsers cap concurrent connections per host (~6 for HTTP/1.1). Opening a
   * separate EventSource per data-hook (and there are many) exhausts that budget
   * with idle SSE streams, after which ALL other API calls — GET, POST, PATCH —
   * stall forever waiting for a free socket. So subscribers to a project share a
   * SINGLE underlying stream: opened on the first subscribe, closed when the last
   * one leaves.
   */
  const streams = new Map<number, { listeners: Set<(e: EventMessage) => void>; close: () => void }>();
  function openTransport(p: number, dispatch: (e: EventMessage) => void): () => void {
    if (typeof EventSource !== "undefined") {
      let es: EventSource;
      try {
        es = new EventSource(baseUrl + ROUTES.events(p));
      } catch {
        return startPolling(p, dispatch);   // constructing failed → degrade
      }
      const handler = (e: MessageEvent) => {
        try {
          dispatch(JSON.parse(e.data) as EventMessage);
        } catch {
          /* ignore keep-alive / non-JSON frames */
        }
      };
      for (const name of [...KNOWN_EVENTS, "connected"]) es.addEventListener(name, handler as EventListener);
      return () => es.close();
    }
    // No EventSource (some non-browser/SSR/test envs): poll instead of silently
    // dropping live updates.
    return startPolling(p, dispatch);
  }

  return {
    health: () => get(ROUTES.health),
    writingModes: () => get(ROUTES.writingModes),
    listProjects: () => get(ROUTES.projects),
    createProject: (b) => post(ROUTES.projects, b),
    importWhiteboard: (b) => post(ROUTES.whiteboardImport, b),
    importManuscript: (b) => post(ROUTES.manuscriptImport, b),
    getProject: (id) => get(ROUTES.project(id)),
    updateProject: (id, b) => patch(ROUTES.project(id), b),
    deleteProject: (id) => del(ROUTES.project(id)),
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
    updateContinuity: (p, s, m, b) => patch(ROUTES.sceneContinuityItem(p, s, m), b),
    deleteContinuity: (p, s, m) => del(ROUTES.sceneContinuityItem(p, s, m)),

    getOutline: (p) => get(ROUTES.outline(p)),
    createOutlineNode: (p, b) => post(ROUTES.outlineNodes(p), b),
    updateOutlineNode: (p, n, b) => patch(ROUTES.outlineNode(p, n), b),
    deleteOutlineNode: (p, n) => del(ROUTES.outlineNode(p, n)),
    generateOutline: (p, b) => post(ROUTES.outlineGenerate(p), b),

    getPlot: (p) => get(ROUTES.plot(p)),
    updatePlotBlock: (p, id, b) => patch(`${ROUTES.plot(p)}/${encodeURIComponent(id)}`, b),
    getTimeline: (p) => get(ROUTES.timeline(p)),
    createTimelineEvent: (p, b) => post(ROUTES.timelineEvents(p), b),
    updateTimelineEvent: (p, id, b) => patch(ROUTES.timelineEvent(p, id), b),
    deleteTimelineEvent: (p, id) => del(ROUTES.timelineEvent(p, id)),

    listPsyke: (p) => get(ROUTES.psykeEntries(p)),
    searchPsyke: (p, q) => get(`${ROUTES.psykeSearch(p)}?q=${encodeURIComponent(q)}`),
    createPsyke: (p, b) => post(ROUTES.psykeEntries(p), b),
    updatePsyke: (p, e, b) => patch(ROUTES.psykeEntry(p, e), b),
    deletePsyke: (p, e) => del(ROUTES.psykeEntry(p, e)),
    listRelations: (p) => get(ROUTES.psykeRelations(p)),
    createRelation: (p, b) => post(ROUTES.psykeRelations(p), b),
    deleteRelation: (p, rid) => del(ROUTES.psykeRelation(p, rid)),
    listProgressions: (p) => get(ROUTES.psykeProgressions(p)),
    createProgression: (p, b) => post(ROUTES.psykeProgressions(p), b),
    updateProgression: (p, id, b) => patch(ROUTES.psykeProgression(p, id), b),
    deleteProgression: (p, id) => del(ROUTES.psykeProgression(p, id)),

    listNotes: (p) => get(ROUTES.notes(p)),
    createNote: (p, b) => post(ROUTES.notes(p), b),
    updateNote: (p, n, b) => patch(ROUTES.note(p, n), b),
    deleteNote: (p, n) => del(ROUTES.note(p, n)),
    linkNoteScene: (p, n, s) => post(ROUTES.noteSceneLink(p, n, s)),
    unlinkNoteScene: (p, n, s) => del(ROUTES.noteSceneLink(p, n, s)),
    linkNotePsyke: (p, n, e) => post(ROUTES.notePsykeLink(p, n, e)),
    unlinkNotePsyke: (p, n, e) => del(ROUTES.notePsykeLink(p, n, e)),

    listCharacters: (p) => get(ROUTES.characters(p)),
    createCharacter: (p, b) => post(ROUTES.characters(p), b),
    updateCharacter: (p, c, b) => patch(ROUTES.character(p, c), b),
    deleteCharacter: (p, c) => del(ROUTES.character(p, c)),
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
    getAiBehavior: (p) => get(ROUTES.aiBehavior(p)),
    patchAiBehavior: (p, b) => patch(ROUTES.aiBehavior(p), b),
    grammarCheck: (p, b) => post(ROUTES.grammarCheck(p), b),
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
    getAdapt: (p) => get(ROUTES.adapt(p)),
    getReview: (p) => get(ROUTES.review(p)),
    getFormatReview: (p) => get(ROUTES.formatReview(p)),
    listPlugins: () => get(ROUTES.plugins),
    voiceStatus: () => get(ROUTES.voiceStatus),
    voiceTranscribe: (p, b) => post(ROUTES.voiceTranscribe(p), b),
    voiceTranscribeSegment: (p, b) => post(ROUTES.voiceTranscribeSegment(p), b),
    voiceHistory: (p) => get(ROUTES.voiceHistory(p)),
    voiceIntents: (p, b) => post(ROUTES.voiceIntents(p), b),
    voiceIntentPreview: (p, b) => post(ROUTES.voiceIntentPreview(p), b),
    voiceIntentApply: (p, b) => post(ROUTES.voiceIntentApply(p), b),
    voiceBillyOps: (p, b) => post(ROUTES.voiceBillyOps(p), b),
    voiceBillyGenerate: (p, b) => post(ROUTES.voiceBillyGenerate(p), b),
    voiceBillyApply: (p, b) => post(ROUTES.voiceBillyApply(p), b),
    voiceCommitTargets: (p, b) => post(ROUTES.voiceCommitTargets(p), b),
    voiceCommit: (p, b) => post(ROUTES.voiceCommit(p), b),
    voiceCanUndo: (p) => get(ROUTES.voiceCanUndo(p)),
    voiceUndo: (p) => post(ROUTES.voiceUndo(p)),
    getGraphGravity: (p) => get(ROUTES.graphGravity(p)),
    generateQuantumOutline: (p, b) => post(ROUTES.quantumOutline(p), b),
    generateQuantumBranches: (p, b) => post(ROUTES.quantumBranches(p), b),
    getQuantumSettings: (p) => get(ROUTES.quantumSettings(p)),
    patchQuantumSettings: (p, b) => patch(ROUTES.quantumSettings(p), b),
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
    updateGnPage: (p, id, b) => patch(ROUTES.gnPage(p, id), b),
    deleteGnPage: (p, id) => del(ROUTES.gnPage(p, id)),
    updateGnPanel: (p, id, b) => patch(ROUTES.gnPanel(p, id), b),
    deleteGnPanel: (p, id) => del(ROUTES.gnPanel(p, id)),
    updateSeason: (p, id, b) => patch(ROUTES.seriesSeason(p, id), b),
    deleteSeason: (p, id) => del(ROUTES.seriesSeason(p, id)),
    updateEpisode: (p, id, b) => patch(ROUTES.seriesEpisode(p, id), b),
    deleteEpisode: (p, id) => del(ROUTES.seriesEpisode(p, id)),
    updateSeriesArc: (p, id, b) => patch(ROUTES.seriesArc(p, id), b),
    deleteStageEntrance: (p, id) => del(ROUTES.stageEntrance(p, id)),
    deleteStageCue: (p, id) => del(ROUTES.stageCue(p, id)),
    deleteSeriesArc: (p, id) => del(ROUTES.seriesArc(p, id)),
    updateEpisodePlotline: (p, id, b) => patch(ROUTES.seriesPlotline(p, id), b),
    deleteEpisodePlotline: (p, id) => del(ROUTES.seriesPlotline(p, id)),
    updateGnContinuityItem: (p, id, b) => patch(ROUTES.gnContinuityItem(p, id), b),
    deleteGnContinuityItem: (p, id) => del(ROUTES.gnContinuityItem(p, id)),
    updateGnContinuityAppearance: (p, id, b) => patch(ROUTES.gnContinuityAppearance(p, id), b),
    deleteGnContinuityAppearance: (p, id) => del(ROUTES.gnContinuityAppearance(p, id)),
    updateStageEntrance: (p, id, b) => patch(ROUTES.stageEntrance(p, id), b),
    updateStageCue: (p, id, b) => patch(ROUTES.stageCue(p, id), b),
    deleteStageBusiness: (p, id) => del(ROUTES.stageBusinessRow(p, id)),
    getSeriesMemory: (p, entryId) => get(ROUTES.psykeSeriesMemory(p, entryId)),
    setSeriesMemory: (p, entryId, b) => put(ROUTES.psykeSeriesMemory(p, entryId), b),

    subscribe: (p, onEvent) => {
      // Attach to the project's shared live-event stream (opening it on first
      // use), so N data-hooks cost ONE connection, not N. See `streams` above.
      let s = streams.get(p);
      if (!s) {
        const listeners = new Set<(e: EventMessage) => void>();
        const dispatch = (e: EventMessage) => {
          for (const fn of [...listeners]) { try { fn(e); } catch { /* one bad listener must not break the rest */ } }
        };
        s = { listeners, close: openTransport(p, dispatch) };
        streams.set(p, s);
      }
      s.listeners.add(onEvent);
      return () => {
        const cur = streams.get(p);
        if (!cur) return;
        cur.listeners.delete(onEvent);
        if (cur.listeners.size === 0) {   // last subscriber left → free the socket
          try { cur.close(); } catch { /* ignore */ }
          streams.delete(p);
        }
      };
    },
  };
}
