import { ROUTES, KNOWN_EVENTS, type EventMessage } from "@logosforge/ui-contracts";
import type { ApiClient } from "./api";
import { trackProjectWrite } from "./projectSaveCoordinator";
import {
  RuntimeDtoValidationError,
  validateAiBehaviorDTO,
  validateAssistantResponseDTO,
  validateAssistantSettingsDTO,
  validateConnectorActionListDTO,
  validateConnectorResultDTO,
  validateDeleteResultDTO,
  validateExtractionJobDTO,
  validateLogosActionListDTO,
  validateLogosResultDTO,
  validateLogosSuggestionListDTO,
  validateOutlineGenerateResultDTO,
  validateOutlineListDTO,
  validateOutlineNodeDTO,
  validateProjectDTO,
  validateProjectActionResultDTO,
  validateProjectListDTO,
  validateQuantumResultDTO,
  validateQuantumSettingsDTO,
  validateSceneDTO,
  validateSceneListDTO,
  validateSettingsDTO,
  validateVoiceBillyProposalDTO,
  type RuntimeDtoValidator,
} from "./runtimeDtoValidation";

function responseDetail(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) return "";
  try {
    const data = JSON.parse(trimmed) as {
      error?: string | { message?: string };
      detail?: string | Array<{ loc?: Array<string | number>; msg?: string }>;
    };
    if (typeof data.error === "string" && data.error.trim()) return data.error.trim();
    if (data.error && typeof data.error === "object" && typeof data.error.message === "string") {
      return data.error.message.trim();
    }
    if (typeof data.detail === "string" && data.detail.trim()) return data.detail.trim();
    if (Array.isArray(data.detail)) {
      const rows = data.detail
        .map((item) => {
          const message = typeof item?.msg === "string" ? item.msg.trim() : "";
          if (!message) return "";
          const location = Array.isArray(item.loc) ? item.loc.join(".") : "";
          return location ? `${location}: ${message}` : message;
        })
        .filter(Boolean);
      if (rows.length) return rows.join("; ");
    }
  } catch {
    /* plain-text response — use it below */
  }
  return trimmed.slice(0, 300);
}

function responseCode(text: string): string {
  try {
    const data = JSON.parse(text) as { error?: { code?: unknown } };
    return typeof data.error?.code === "string" ? data.error.code : "";
  } catch {
    return "";
  }
}

export class ApiRequestError extends Error {
  readonly method: string;
  readonly path: string;
  readonly status: number;
  readonly code: string;

  constructor(method: string, path: string, status: number, detail = "", code = "") {
    super(`${method} ${path} → ${status}${detail ? " · " + detail : ""}`);
    this.name = "ApiRequestError";
    this.method = method;
    this.path = path;
    this.status = status;
    this.code = code;
  }
}

export class ApiRequestTimeoutError extends Error {
  readonly method: string;
  readonly path: string;
  readonly timeoutMs: number;
  readonly code = "request_timeout";
  readonly outcomeUnknown: boolean;

  constructor(method: string, path: string, timeoutMs: number) {
    const outcomeUnknown = !["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase());
    super(`${method} ${path} timed out after ${timeoutMs} ms${outcomeUnknown ? " · the server may still have completed this change; refresh before retrying" : ""}`);
    this.name = "ApiRequestTimeoutError";
    this.method = method;
    this.path = path;
    this.timeoutMs = timeoutMs;
    this.outcomeUnknown = outcomeUnknown;
  }
}

export class ApiResponseValidationError extends Error {
  readonly method: string;
  readonly path: string;
  readonly code = "invalid_response";
  readonly detail: string;

  constructor(method: string, path: string, detail: string) {
    super(method + " " + path + " returned an invalid response · " + detail);
    this.name = "ApiResponseValidationError";
    this.method = method;
    this.path = path;
    this.detail = detail;
  }
}

function validateResponse<T>(
  method: string,
  path: string,
  value: unknown,
  validate?: RuntimeDtoValidator<T>,
): T {
  if (!validate) return value as T;
  try {
    return validate(value);
  } catch (error) {
    if (error instanceof RuntimeDtoValidationError) {
      throw new ApiResponseValidationError(method, path, error.message);
    }
    throw error;
  }
}

export interface HttpApiClientOptions {
  healthTimeoutMs?: number;
  readTimeoutMs?: number;
  writeTimeoutMs?: number;
  longRequestTimeoutMs?: number;
}

export const DEFAULT_HTTP_TIMEOUTS = {
  healthTimeoutMs: 5_000,
  readTimeoutMs: 30_000,
  // Mutations are not aborted by default: disconnecting after the server commits
  // leaves an ambiguous outcome and can violate the same-resource PATCH order.
  // Hosts may opt into a limit, whose error explicitly marks outcomeUnknown.
  writeTimeoutMs: 0,
  longRequestTimeoutMs: 15 * 60_000,
} as const;

const LONG_REQUEST_PATHS = [
  "/assistant/chat",
  "/assistant/action",
  "/outline/generate",
  "/logos/run",
  "/connector/execute",
  "/grammar/check",
  "/export",
  "/voice/transcribe",
  "/voice/transcribe-segment",
  "/voice/intents/preview",
  "/voice/billy/generate",
  "/quantum/outline",
  "/quantum/branches",
  "/counterpart",
] as const;

function timeoutValue(candidate: number | undefined, fallback: number): number {
  if (candidate === 0) return 0;
  return typeof candidate === "number" && Number.isFinite(candidate) && candidate > 0
    ? Math.floor(candidate)
    : fallback;
}

export function requestTimeoutMs(
  path: string,
  method = "GET",
  options: HttpApiClientOptions = {},
): number {
  if (path === ROUTES.health) return timeoutValue(options.healthTimeoutMs, DEFAULT_HTTP_TIMEOUTS.healthTimeoutMs);
  if (LONG_REQUEST_PATHS.some((fragment) => path.includes(fragment))) {
    return timeoutValue(options.longRequestTimeoutMs, DEFAULT_HTTP_TIMEOUTS.longRequestTimeoutMs);
  }
  return ["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase())
    ? timeoutValue(options.readTimeoutMs, DEFAULT_HTTP_TIMEOUTS.readTimeoutMs)
    : timeoutValue(options.writeTimeoutMs, DEFAULT_HTTP_TIMEOUTS.writeTimeoutMs);
}

function abortError(message: string): Error {
  const error = new Error(message);
  error.name = "AbortError";
  return error;
}

function cloneTransportValue<T>(value: T): T {
  if (value == null || typeof value !== "object") return value;
  if (typeof structuredClone === "function") {
    try { return structuredClone(value); } catch { /* JSON fallback below */ }
  }
  try { return JSON.parse(JSON.stringify(value)) as T; } catch { return value; }
}

/**
 * `createHttpApiClient(baseUrl, authToken)` — the reference {@link ApiClient} over the
 * logosforge core HTTP API (FastAPI), built on `fetch` + `EventSource` (SSE).
 * Both are web standards available in an Electron renderer and a plain browser,
 * so this single implementation serves both Pro apps:
 *   - pro-desktop → baseUrl = the in-process core (e.g. "http://127.0.0.1:8765")
 *   - pro-web     → baseUrl = the configured remote host (or "" behind a proxy)
 *
 * The host app constructs it and injects it via `<StudioProvider services={{ api }}>`;
 * components only ever call the {@link ApiClient} interface. It knows only the
 * route map + DTOs from `@logosforge/ui-contracts`. The host may inject an
 * in-memory Bearer token; this adapter never persists or discovers credentials.
 */
export function createHttpApiClient(
  baseUrl = "",
  authToken = "",
  options: HttpApiClientOptions = {},
): ApiClient {
  const timeoutOptions = { ...options };
  const patchTails = new Map<string, Promise<void>>();
  const getInflight = new Map<string, Promise<unknown>>();
  const clientAbort = new AbortController();
  let disposed = false;
  async function req<T = any>(
    path: string,
    init?: RequestInit,
    validate?: RuntimeDtoValidator<T>,
  ): Promise<T> {
    const method = init?.method ?? "GET";
    const readMethod = ["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase());
    if (!readMethod) getInflight.clear();
    const timeoutMs = requestTimeoutMs(path, method, timeoutOptions);
    const headers = new Headers(init?.headers);
    if (!headers.has("content-type")) headers.set("content-type", "application/json");
    if (authToken) headers.set("authorization", `Bearer ${authToken}`);
    const requestAbort = new AbortController();
    const cleanups: Array<() => void> = [];
    let timedOut = false;
    const relay = (signal: AbortSignal | null | undefined) => {
      if (!signal) return;
      const abort = () => {
        if (!requestAbort.signal.aborted) requestAbort.abort(signal.reason ?? abortError("Request cancelled"));
      };
      if (signal.aborted) abort();
      else {
        signal.addEventListener("abort", abort, { once: true });
        cleanups.push(() => signal.removeEventListener("abort", abort));
      }
    };
    relay(clientAbort.signal);
    relay(init?.signal);
    let timeout: ReturnType<typeof setTimeout> | undefined;
    if (timeoutMs > 0 && !requestAbort.signal.aborted) {
      timeout = setTimeout(() => {
        if (requestAbort.signal.aborted) return;
        timedOut = true;
        requestAbort.abort();
      }, timeoutMs);
    }
    try {
      const res = await fetch(baseUrl + path, { ...init, headers, signal: requestAbort.signal });
      if (requestAbort.signal.aborted) throw requestAbort.signal.reason ?? abortError("Request cancelled");
      if (!res.ok) {
        const raw = await res.text().catch(() => "");
        const detail = responseDetail(raw);
        throw new ApiRequestError(method, path, res.status, detail, responseCode(raw));
      }
      if (res.status === 204) return validateResponse(method, path, undefined, validate);
      const ct = res.headers.get("content-type") ?? "";
      let value: unknown;
      if (ct.includes("application/json")) {
        try {
          value = await res.json();
        } catch {
          throw new ApiResponseValidationError(method, path, "response body is not valid JSON");
        }
      } else {
        value = await res.text();
      }
      return validateResponse(method, path, value, validate);
    } catch (error) {
      if (timedOut) throw new ApiRequestTimeoutError(method, path, timeoutMs);
      if (requestAbort.signal.aborted) {
        const reason = requestAbort.signal.reason;
        throw reason instanceof Error ? reason : abortError(disposed ? "API client disposed" : "Request cancelled");
      }
      throw error;
    } finally {
      if (timeout) clearTimeout(timeout);
      for (const cleanup of cleanups) cleanup();
      if (!readMethod) getInflight.clear();
    }
  }
  const get = <T = any>(p: string, validate?: RuntimeDtoValidator<T>): Promise<T> => {
    let pending = getInflight.get(p) as Promise<T> | undefined;
    if (!pending) {
      pending = req(p, undefined, validate);
      getInflight.set(p, pending);
      void pending.then(
        () => { if (getInflight.get(p) === pending) getInflight.delete(p); },
        () => { if (getInflight.get(p) === pending) getInflight.delete(p); },
      );
    }
    return pending.then((value) => cloneTransportValue(value));
  };
  const post = <T = any>(p: string, body?: unknown, validate?: RuntimeDtoValidator<T>) =>
    req(p, { method: "POST", body: body == null ? undefined : JSON.stringify(body) }, validate);
  const writePost = <T = any>(p: string, body?: unknown, validate?: RuntimeDtoValidator<T>) =>
    trackProjectWrite(post(p, body, validate));
  const patch = <T = any>(p: string, body: unknown, validate?: RuntimeDtoValidator<T>) => {
    // Preserve invocation order for one logical resource. This matters when two
    // mounted controls patch the same settings endpoint (e.g. Adaptive strip +
    // Cross-Cutting): network completion order must not reverse the user's intent.
    const payload = JSON.stringify(body);
    const previous = patchTails.get(p) ?? Promise.resolve();
    const request = previous
      .catch(() => undefined)
      .then(() => req(p, { method: "PATCH", body: payload }, validate));
    const settled = request.then(() => undefined, () => undefined);
    patchTails.set(p, settled);
    void settled.then(() => { if (patchTails.get(p) === settled) patchTails.delete(p); });
    return trackProjectWrite(request);
  };
  const put = (p: string, body: unknown) => trackProjectWrite(req(p, { method: "PUT", body: JSON.stringify(body) }));
  const del = <T = any>(p: string, validate?: RuntimeDtoValidator<T>) =>
    trackProjectWrite(req(p, { method: "DELETE" }, validate));

  /** Polling fallback for live sync when SSE (EventSource) isn't available.
   * Learns the current cursor on the first tick (no replay of history), then
   * dispatches only newer events every few seconds. */
  function startPolling(p: number, onEvent: (e: EventMessage) => void): () => void {
    let cursor = 0;
    let primed = false;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let activeAbort: AbortController | null = null;
    const tick = async () => {
      if (stopped) return;
      const controller = new AbortController();
      activeAbort = controller;
      try {
        const r = await req(`${ROUTES.eventsPoll(p)}?since=${cursor}`, { signal: controller.signal });
        if (r && typeof r.cursor === "number") {
          if (primed) for (const ev of r.events ?? []) { try { onEvent(ev as EventMessage); } catch { /* ignore */ } }
          cursor = r.cursor;
          primed = true;
        }
      } catch { /* transient/cancelled; try again only while still subscribed */ }
      finally { if (activeAbort === controller) activeAbort = null; }
      if (!stopped) timer = setTimeout(tick, 3000);
    };
    void tick();
    return () => {
      stopped = true;
      activeAbort?.abort(abortError("Event polling stopped"));
      activeAbort = null;
      if (timer) clearTimeout(timer);
    };
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
    // Native EventSource cannot attach an Authorization header. Authenticated
    // desktop sessions therefore use the existing polling transport, whose
    // requests flow through req() and carry the per-process Bearer token.
    if (!authToken && typeof EventSource !== "undefined") {
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
    dispose: () => {
      if (disposed) return;
      disposed = true;
      clientAbort.abort(abortError("API client disposed"));
      for (const stream of streams.values()) {
        try { stream.close(); } catch { /* best-effort transport shutdown */ }
      }
      streams.clear();
      patchTails.clear();
      getInflight.clear();
    },
    health: () => get(ROUTES.health),
    writingModes: () => get(ROUTES.writingModes),
    listProjects: () => get(ROUTES.projects, validateProjectListDTO),
    createProject: (b) => writePost(ROUTES.projects, b, validateProjectDTO),
    importWhiteboard: (b) => writePost(ROUTES.whiteboardImport, b),
    importManuscript: (b) => writePost(ROUTES.manuscriptImport, b),
    getProject: (id) => get(ROUTES.project(id), validateProjectDTO),
    updateProject: (id, b) => patch(ROUTES.project(id), b, validateProjectDTO),
    deleteProject: (id) => del(ROUTES.project(id), validateDeleteResultDTO),
    openProject: (id) => post(ROUTES.projectOpen(id), undefined, validateProjectDTO),
    saveProject: (id) => post(ROUTES.projectSave(id), undefined, validateProjectActionResultDTO),
    closeProject: (id) => post(ROUTES.projectClose(id), undefined, validateProjectActionResultDTO),
    getSettings: (id) => get(ROUTES.projectSettings(id), validateSettingsDTO),
    patchSettings: (id, b) => patch(ROUTES.projectSettings(id), b, validateSettingsDTO),

    listScenes: (p) => get(ROUTES.scenes(p), validateSceneListDTO),
    createScene: (p, b) => writePost(ROUTES.scenes(p), b, validateSceneDTO),
    updateScene: (p, s, b) => patch(ROUTES.scene(p, s), b, validateSceneDTO),
    deleteScene: (p, s) => del(ROUTES.scene(p, s), validateDeleteResultDTO),
    listContinuity: (p, s) => get(ROUTES.sceneContinuity(p, s)),
    addContinuity: (p, s, b) => writePost(ROUTES.sceneContinuity(p, s), b),
    updateContinuity: (p, s, m, b) => patch(ROUTES.sceneContinuityItem(p, s, m), b),
    deleteContinuity: (p, s, m) => del(ROUTES.sceneContinuityItem(p, s, m)),

    getOutline: (p) => get(ROUTES.outline(p), validateOutlineListDTO),
    createOutlineNode: (p, b) => writePost(ROUTES.outlineNodes(p), b, validateOutlineNodeDTO),
    updateOutlineNode: (p, n, b) => patch(ROUTES.outlineNode(p, n), b, validateOutlineNodeDTO),
    deleteOutlineNode: (p, n) => del(ROUTES.outlineNode(p, n), validateDeleteResultDTO),
    generateOutline: (p, b) => writePost(ROUTES.outlineGenerate(p), b, validateOutlineGenerateResultDTO),

    getPlot: (p) => get(ROUTES.plot(p)),
    updatePlotBlock: (p, id, b) => patch(ROUTES.plotBlock(p, id), b),
    getTimeline: (p) => get(ROUTES.timeline(p)),
    createTimelineEvent: (p, b) => writePost(ROUTES.timelineEvents(p), b),
    updateTimelineEvent: (p, id, b) => patch(ROUTES.timelineEvent(p, id), b),
    deleteTimelineEvent: (p, id) => del(ROUTES.timelineEvent(p, id)),

    listPsyke: (p) => get(ROUTES.psykeEntries(p)),
    searchPsyke: (p, q) => get(`${ROUTES.psykeSearch(p)}?q=${encodeURIComponent(q)}`),
    createPsyke: (p, b) => writePost(ROUTES.psykeEntries(p), b),
    updatePsyke: (p, e, b) => patch(ROUTES.psykeEntry(p, e), b),
    deletePsyke: (p, e) => del(ROUTES.psykeEntry(p, e)),
    listRelations: (p) => get(ROUTES.psykeRelations(p)),
    createRelation: (p, b) => writePost(ROUTES.psykeRelations(p), b),
    deleteRelation: (p, rid) => del(ROUTES.psykeRelation(p, rid)),
    listProgressions: (p) => get(ROUTES.psykeProgressions(p)),
    createProgression: (p, b) => writePost(ROUTES.psykeProgressions(p), b),
    updateProgression: (p, id, b) => patch(ROUTES.psykeProgression(p, id), b),
    deleteProgression: (p, id) => del(ROUTES.psykeProgression(p, id)),

    listNotes: (p) => get(ROUTES.notes(p)),
    createNote: (p, b) => writePost(ROUTES.notes(p), b),
    updateNote: (p, n, b) => patch(ROUTES.note(p, n), b),
    deleteNote: (p, n) => del(ROUTES.note(p, n)),
    linkNoteScene: (p, n, s) => writePost(ROUTES.noteSceneLink(p, n, s)),
    unlinkNoteScene: (p, n, s) => del(ROUTES.noteSceneLink(p, n, s)),
    linkNotePsyke: (p, n, e) => writePost(ROUTES.notePsykeLink(p, n, e)),
    unlinkNotePsyke: (p, n, e) => del(ROUTES.notePsykeLink(p, n, e)),

    listCharacters: (p) => get(ROUTES.characters(p)),
    createCharacter: (p, b) => writePost(ROUTES.characters(p), b),
    updateCharacter: (p, c, b) => patch(ROUTES.character(p, c), b),
    deleteCharacter: (p, c) => del(ROUTES.character(p, c)),
    backfillCharacterLinks: (p) => writePost(ROUTES.characterBackfillLinks(p)),

    getThemeScenes: (p, entryId) => get(ROUTES.themeScenes(p, entryId)),
    setThemeScenes: (p, entryId, sceneIds) => put(ROUTES.themeScenes(p, entryId), { scene_ids: sceneIds }),

    assistantChat: (p, b) => post(ROUTES.assistantChat(p), b, validateAssistantResponseDTO),
    assistantAction: (p, b) => writePost(ROUTES.assistantAction(p), b, validateConnectorResultDTO),
    listLogosActions: (p, section, writingMode) => {
      const q = new URLSearchParams();
      if (section) q.set("section", section);
      if (writingMode) q.set("writing_mode", writingMode);
      const qs = q.toString();
      return get(
        ROUTES.logosActions(p) + (qs ? `?${qs}` : ""),
        validateLogosActionListDTO,
      );
    },
    runLogos: (p, b) => post(ROUTES.logosRun(p), b, validateLogosResultDTO),
    listLogosProactive: (p, section) => get(
      ROUTES.logosProactive(p) + (section ? `?section=${encodeURIComponent(section)}` : ""),
      validateLogosSuggestionListDTO,
    ),
    getAssistantSettings: (p) => get(ROUTES.assistantSettings(p), validateAssistantSettingsDTO),
    patchAssistantSettings: (p, b) => patch(ROUTES.assistantSettings(p), b, validateAssistantSettingsDTO),
    getAiBehavior: (p) => get(ROUTES.aiBehavior(p), validateAiBehaviorDTO),
    patchAiBehavior: (p, b) => patch(ROUTES.aiBehavior(p), b, validateAiBehaviorDTO),
    grammarCheck: (p, b) => post(ROUTES.grammarCheck(p), b),
    listConnectorActions: (p) => get(ROUTES.connectorActions(p), validateConnectorActionListDTO),
    connectorExecute: (p, b) => writePost(ROUTES.connectorExecute(p), b, validateConnectorResultDTO),

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
    voiceTranscribeSegment: (p, b) => writePost(ROUTES.voiceTranscribeSegment(p), b),
    voiceHistory: (p) => get(ROUTES.voiceHistory(p)),
    voiceIntents: (p, b) => post(ROUTES.voiceIntents(p), b),
    voiceIntentPreview: (p, b) => writePost(ROUTES.voiceIntentPreview(p), b),
    voiceIntentApply: (p, b) => writePost(ROUTES.voiceIntentApply(p), b),
    voiceIntentCancel: (p, b) => writePost(ROUTES.voiceIntentCancel(p), b),
    voiceBillyOps: (p, b) => post(ROUTES.voiceBillyOps(p), b),
    voiceBillyGenerate: (p, b) =>
      writePost(ROUTES.voiceBillyGenerate(p), b, validateVoiceBillyProposalDTO),
    voiceBillyApply: (p, b) => writePost(ROUTES.voiceBillyApply(p), b),
    voiceBillyCancel: (p, b) => writePost(ROUTES.voiceBillyCancel(p), b),
    voiceCommitTargets: (p, b) => post(ROUTES.voiceCommitTargets(p), b),
    voiceCommit: (p, b) => writePost(ROUTES.voiceCommit(p), b),
    voiceCanUndo: (p) => get(ROUTES.voiceCanUndo(p)),
    voiceUndo: (p) => writePost(ROUTES.voiceUndo(p)),
    getGraphGravity: (p) => get(ROUTES.graphGravity(p)),
    generateQuantumOutline: (p, b) => post(ROUTES.quantumOutline(p), b, validateQuantumResultDTO),
    generateQuantumBranches: (p, b) => post(ROUTES.quantumBranches(p), b, validateQuantumResultDTO),
    getQuantumSettings: (p) => get(ROUTES.quantumSettings(p), validateQuantumSettingsDTO),
    patchQuantumSettings: (p, b) => patch(ROUTES.quantumSettings(p), b, validateQuantumSettingsDTO),
    runCounterpart: (p, b) => post(ROUTES.counterpart(p), b, validateAssistantResponseDTO),

    startExtract: (p, useLlm = true, model) =>
      post(
        `${ROUTES.extract(p)}?use_llm=${useLlm}${model ? `&model=${encodeURIComponent(model)}` : ""}`,
        undefined,
        validateExtractionJobDTO,
      ),
    listExtractionModels: (p) => get(ROUTES.extractModels(p)),
    getExtractJob: (p, jobId) => get(ROUTES.extractJob(p, jobId), validateExtractionJobDTO),
    cancelExtractJob: (p, jobId) => del(ROUTES.extractJob(p, jobId), validateExtractionJobDTO),
    applyExtraction: (p, b) => writePost(ROUTES.extractApply(p), b),
    revertExtraction: (p, receipt) => writePost(ROUTES.extractRevert(p), receipt),

    listGnPages: (p) => get(ROUTES.gnPages(p)),
    createGnPage: (p, b) => writePost(ROUTES.gnPages(p), b),
    syncGnFromScenes: (p) => writePost(ROUTES.gnSyncFromScenes(p)),
    listGnContinuityItems: (p) => get(ROUTES.gnContinuityItems(p)),
    createGnContinuityItem: (p, b) => writePost(ROUTES.gnContinuityItems(p), b),
    listGnContinuityAppearances: (p, itemId) => get(ROUTES.gnContinuityAppearances(p, itemId)),
    createGnContinuityAppearance: (p, itemId, b) => writePost(ROUTES.gnContinuityAppearances(p, itemId), b),
    listGnPanels: (p, pageId) => get(ROUTES.gnPanels(p, pageId)),
    createGnPanel: (p, pageId, b) => writePost(ROUTES.gnPanels(p, pageId), b),
    listStageCues: (p, sceneId) => get(ROUTES.stageCues(p, sceneId)),
    createStageCue: (p, sceneId, b) => writePost(ROUTES.stageCues(p, sceneId), b),
    listStageEntrances: (p, sceneId) => get(ROUTES.stageEntrances(p, sceneId)),
    createStageEntrance: (p, sceneId, b) => writePost(ROUTES.stageEntrances(p, sceneId), b),
    listStageBusiness: (p, sceneId) => get(ROUTES.stageBusiness(p, sceneId)),
    createStageBusiness: (p, sceneId, b) => writePost(ROUTES.stageBusiness(p, sceneId), b),
    syncStageFromScenes: (p) => writePost(ROUTES.stageSyncFromScenes(p)),
    listSeasons: (p) => get(ROUTES.seriesSeasons(p)),
    createSeason: (p, b) => writePost(ROUTES.seriesSeasons(p), b),
    listEpisodes: (p) => get(ROUTES.seriesEpisodes(p)),
    createEpisode: (p, seasonId, b) => writePost(ROUTES.seriesSeasonEpisodes(p, seasonId), b),
    listSeriesArcs: (p) => get(ROUTES.seriesArcs(p)),
    createSeriesArc: (p, b) => writePost(ROUTES.seriesArcs(p), b),
    listEpisodePlotlines: (p, episodeId) => get(ROUTES.episodePlotlines(p, episodeId)),
    createEpisodePlotline: (p, episodeId, b) => writePost(ROUTES.episodePlotlines(p, episodeId), b),
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
      if (disposed) return () => undefined;
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
