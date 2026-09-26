import {
  ApiRequestError,
  ApiResponseValidationError,
  createHttpApiClient,
} from "../src/adapters/httpApiClient";
import {
  PendingProjectSaveError,
  flushPendingProjectSaves,
} from "../src/adapters/projectSaveCoordinator";

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: boolean): void => {
  if (condition) passed += 1;
  else failures.push(label);
};

const json = (value: unknown, status = 200): Response => new Response(JSON.stringify(value), {
  status,
  headers: { "content-type": "application/json" },
});

const project = (overrides: Record<string, unknown> = {}) => ({
  id: 1,
  title: "Project",
  description: "",
  narrative_engine: "novel",
  default_writing_format: "prose",
  format_mode: "novel",
  ...overrides,
});

const scene = (overrides: Record<string, unknown> = {}) => ({
  id: 2,
  title: "Scene",
  summary: "",
  synopsis: "",
  goal: "",
  conflict: "",
  outcome: "",
  beat: "",
  act: "",
  chapter: "",
  plotline: "",
  color_label: "",
  tags: [],
  content: "Opening line",
  sort_order: 0,
  order_index: 0,
  character_ids: [],
  place_ids: [],
  who_knows_what: "",
  revision: "sha256",
  ...overrides,
});

const inlineCommentAnchor = (overrides: Record<string, unknown> = {}) => ({
  start_scene_id: 2,
  start_field: "content",
  from_offset: 0,
  end_scene_id: 2,
  end_field: "content",
  to_offset: 7,
  prefix: "",
  suffix: " line",
  ...overrides,
});

const commentReply = (overrides: Record<string, unknown> = {}) => ({
  id: 6,
  source_id: "whiteboard-reply-1",
  body: "Agreed.",
  author: "writer",
  sort_order: 0,
  created_at: "2026-09-01T10:01:00Z",
  ...overrides,
});

const inlineComment = (overrides: Record<string, unknown> = {}) => ({
  id: 5,
  source_id: "whiteboard-comment-1",
  anchor: inlineCommentAnchor(),
  quote: "Opening",
  body: "Sharpen this.",
  resolved: false,
  replies: [commentReply()],
  created_at: "2026-09-01T10:00:00Z",
  updated_at: "2026-09-01T10:01:00Z",
  revision: "a".repeat(64),
  ...overrides,
});

const whiteboardImportResult = (overrides: Record<string, unknown> = {}) => ({
  project_id: 1,
  title: "Imported",
  mode: "novel",
  scenes_created: 1,
  scene_titles: ["Imported"],
  scene_ids_by_block: [2],
  comments_created: 1,
  comments_skipped: 0,
  comment_replies_created: 1,
  comment_replies_skipped: 0,
  ...overrides,
});

const outline = (overrides: Record<string, unknown> = {}) => ({
  id: 3,
  parent_id: null,
  title: "Act I",
  description: "",
  sort_order: 0,
  scene_id: null,
  children: [],
  ...overrides,
});

const assistantSettings = (overrides: Record<string, unknown> = {}) => ({
  provider: "openai",
  model: "model",
  base_url: "",
  timeout: 60,
  api_key: null,
  ...overrides,
});

const aiBehavior = (overrides: Record<string, unknown> = {}) => ({
  ctx_outline: true,
  ctx_bible: true,
  ctx_memory: true,
  connector_enabled: false,
  connector_allow_writes: false,
  connector_confirm_writes: true,
  connector_disabled_actions: [],
  adaptive_override: "",
  ...overrides,
});

const logosAction = (overrides: Record<string, unknown> = {}) => ({
  name: "diagnose",
  label: "Diagnose",
  description: "",
  category: "diagnostic",
  sections: [],
  needs_selection: false,
  deterministic: true,
  generative: false,
  ...overrides,
});

const logosResult = (overrides: Record<string, unknown> = {}) => ({
  ok: true,
  action: "diagnose",
  title: "Result",
  message: "All clear",
  suggestions: [],
  proposed_operations: [],
  generative: false,
  error: null,
  ...overrides,
});

const logosSuggestion = (overrides: Record<string, unknown> = {}) => ({
  id: "suggestion-1",
  type: "structure",
  title: "Consider a turn",
  message: "",
  section_name: "",
  evidence: "",
  confidence: 0.75,
  severity: "info",
  target_type: "",
  target_id: "",
  suggested_actions: [],
  ...overrides,
});

const connectorResult = (overrides: Record<string, unknown> = {}) => ({
  ok: true,
  action: "lookup",
  result: null,
  error: "",
  ...overrides,
});

const quantumResult = (overrides: Record<string, unknown> = {}) => ({
  kind: "outline",
  title: "Branches",
  body: "Three paths",
  payload: {},
  ...overrides,
});

const quantumSettings = (overrides: Record<string, unknown> = {}) => ({
  preset: "balanced",
  weights: { novelty: 1 },
  selection_mode: "weighted",
  show_tradeoffs: true,
  ensemble_alpha: 0.5,
  weight_learning: false,
  preset_names: ["balanced"],
  weight_keys: ["novelty"],
  ...overrides,
});

const voiceBillyProposal = (overrides: Record<string, unknown> = {}) => ({
  id: "proposal-1",
  proposal_type: "voice_billy",
  operation: "ask",
  project_id: 1,
  created_at: 1_700_000_000.25,
  source_segment_ids: ["segment-1"],
  prompt_text: "Question",
  response_text: "Answer",
  target_summary: "No mutation",
  before_text: null,
  after_text: null,
  diff: null,
  note_preview: null,
  psyke_preview: null,
  gn_ref: null,
  gn_field: "",
  can_apply: false,
  reason_if_blocked: "",
  applied: false,
  cancelled: false,
  applied_at: null,
  ...overrides,
});

const relationProposal = (overrides: Record<string, unknown> = {}) => ({
  source: "Setup",
  target: "Payoff",
  rel_type: "supports_setup",
  why: "",
  confidence: 0.6,
  source_status: "new",
  target_status: "existing",
  source_hint: null,
  target_hint: null,
  ...overrides,
});

const sceneExtraction = (overrides: Record<string, unknown> = {}) => ({
  scene_id: 2,
  title: "Scene",
  characters: ["Ada"],
  who_knows_what: "",
  relations: [],
  ...overrides,
});

const extractionResult = (overrides: Record<string, unknown> = {}) => ({
  project_id: 1,
  used_llm: true,
  scenes: [sceneExtraction()],
  setup_payoffs: [relationProposal()],
  ...overrides,
});

const extractionJob = (overrides: Record<string, unknown> = {}) => ({
  job_id: "job-1",
  status: "running",
  done: 0,
  total: 1,
  error: "",
  result: null,
  ...overrides,
});

const originalFetch = globalThis.fetch;
const client = createHttpApiClient("", "", {
  healthTimeoutMs: 0,
  readTimeoutMs: 0,
  writeTimeoutMs: 0,
  longRequestTimeoutMs: 0,
});

const installResponse = (factory: () => Response): void => {
  globalThis.fetch = async () => factory();
};

async function expectValid<T>(
  label: string,
  invoke: () => Promise<T>,
  response: unknown,
  inspect: (value: T) => boolean = () => true,
): Promise<void> {
  installResponse(() => json(response));
  try {
    check(label, inspect(await invoke()));
  } catch {
    failures.push(label + " unexpectedly rejected");
  }
}

async function expectInvalid(
  label: string,
  invoke: () => Promise<unknown>,
  response: Response,
  method: string,
  path: string,
  detail: string,
): Promise<ApiResponseValidationError | null> {
  installResponse(() => response.clone());
  let caught: unknown = null;
  try {
    await invoke();
  } catch (error) {
    caught = error;
  }
  check(label + " uses ApiResponseValidationError", caught instanceof ApiResponseValidationError);
  check(label + " retains endpoint metadata", caught instanceof ApiResponseValidationError
    && caught.method === method && caught.path === path && caught.code === "invalid_response");
  check(label + " reports the field path", caught instanceof ApiResponseValidationError
    && caught.detail.includes(detail));
  return caught instanceof ApiResponseValidationError ? caught : null;
}

try {
  await expectValid(
    "project lists preserve additive response fields",
    () => client.listProjects(),
    [project({ future_flag: true })],
    (value) => (value[0] as unknown as { future_flag?: boolean }).future_flag === true,
  );
  await expectValid("project creation validates its mutation response", () =>
    client.createProject({ title: "Created" }), project({ title: "Created" }));
  await expectInvalid(
    "project detail rejects a wrong scalar",
    () => client.getProject(1),
    json(project({ title: { secret: "never echo this" } })),
    "GET",
    "/api/projects/1",
    "$.title",
  );
  await expectValid("project open validates its response", () => client.openProject(1), project());
  await expectValid("project save validates its action result", () => client.saveProject(1), {
    ok: true,
    project_id: 1,
  });
  await expectValid("project delete validates its result", () => client.deleteProject(1), {
    ok: true,
    deleted: 1,
  });
  await expectInvalid(
    "transported IDs must be safe integers",
    () => client.getProject(1),
    json(project({ id: Number.MAX_SAFE_INTEGER + 1 })),
    "GET",
    "/api/projects/1",
    "$.id",
  );
  await expectValid(
    "Whiteboard import validates comment migration counters",
    () => client.importWhiteboard({ blocks: [] }),
    whiteboardImportResult(),
  );
  await expectInvalid(
    "Whiteboard import rejects malformed comment migration counters",
    () => client.importWhiteboard({ blocks: [] }),
    json(whiteboardImportResult({ comments_skipped: false })),
    "POST",
    "/api/import/whiteboard",
    "$.comments_skipped",
  );

  await expectInvalid(
    "scene lists reject a malformed nested member",
    () => client.listScenes(1),
    json([scene({ tags: ["valid", 4] })]),
    "GET",
    "/api/projects/1/scenes",
    "$[0].tags[1]",
  );
  await expectValid("scene creation validates its response", () =>
    client.createScene(1, { title: "Scene" }), scene());
  await expectValid("scene updates accept an omitted legacy revision", () =>
    client.updateScene(1, 2, { title: "Changed" }), scene({ revision: undefined }));
  await expectValid("scene delete validates its result", () => client.deleteScene(1, 2), {
    ok: true,
    deleted: 2,
  });

  await expectValid(
    "inline comment lists validate cross-field anchors and ordered replies",
    () => client.listComments(1),
    [inlineComment({
      anchor: inlineCommentAnchor({ start_field: "title", end_field: "content" }),
    })],
  );
  await expectInvalid(
    "inline comment lists reject an unknown anchor field",
    () => client.listComments(1),
    json([inlineComment({ anchor: inlineCommentAnchor({ end_field: "summary" }) })]),
    "GET",
    "/api/projects/1/comments",
    "$[0].anchor.end_field",
  );
  await expectInvalid(
    "inline comment lists require the optimistic revision",
    () => client.listComments(1),
    json([inlineComment({ revision: undefined })]),
    "GET",
    "/api/projects/1/comments",
    "$[0].revision",
  );
  await expectValid(
    "inline comment creation validates its returned thread",
    () => client.createComment(1, { anchor: inlineCommentAnchor(), quote: "Opening" }),
    inlineComment(),
  );
  await expectInvalid(
    "inline comment replies reject malformed source ids",
    () => client.createCommentReply(1, 5, { body: "Reply" }),
    json(inlineComment({ replies: [commentReply({ source_id: 9 })] })),
    "POST",
    "/api/projects/1/comments/5/replies",
    "$.replies[0].source_id",
  );
  await expectValid(
    "inline comment updates validate the refreshed thread",
    () => client.updateComment(1, 5, { resolved: true }),
    inlineComment({ resolved: true }),
  );
  await expectValid(
    "inline comment delete validates its result",
    () => client.deleteComment(1, 5),
    { ok: true, deleted: 5 },
  );
  await expectValid(
    "inline comment reply delete validates its result",
    () => client.deleteCommentReply(1, 5, 6),
    { ok: true, deleted: 6 },
  );

  await expectValid("settings accept arbitrary values inside their open map", () =>
    client.getSettings(1), { settings: { nested: { enabled: true }, list: [1, "two"] } });
  await expectInvalid(
    "settings reject a non-object map",
    () => client.patchSettings(1, { settings: {} }),
    json({ settings: null }),
    "PATCH",
    "/api/projects/1/settings",
    "$.settings",
  );

  await expectInvalid(
    "outline validation reports a deeply nested field",
    () => client.getOutline(1),
    json([outline({ children: [outline({ id: 4, parent_id: 3, scene_id: "bad" })] })]),
    "GET",
    "/api/projects/1/outline",
    "$[0].children[0].scene_id",
  );
  await expectValid("outline node creation validates its response", () =>
    client.createOutlineNode(1, { title: "Act I" }), outline());
  await expectValid("outline node updates validate their response", () =>
    client.updateOutlineNode(1, 3, { title: "Act One" }), outline({ title: "Act One" }));
  await expectValid("outline delete validates its result", () => client.deleteOutlineNode(1, 3), {
    ok: true,
    deleted: 3,
  });
  await expectInvalid(
    "outline generation rejects malformed warnings",
    () => client.generateOutline(1, {}),
    json({ ok: true, created: 1, node_ids: [3], warnings: [false], errors: [] }),
    "POST",
    "/api/projects/1/outline/generate",
    "$.warnings[0]",
  );
  let deepOutline: Record<string, unknown> = outline({ id: 140 });
  for (let id = 139; id >= 1; id -= 1) {
    deepOutline = outline({ id, children: [deepOutline] });
  }
  await expectValid(
    "schema-valid deep outlines have no validator-only depth cap",
    () => client.getOutline(1),
    [deepOutline],
  );

  await expectInvalid(
    "assistant chat rejects a malformed response",
    () => client.assistantChat(1, { message: "Help" }),
    json({ reply: "Answer", cached: "false" }),
    "POST",
    "/api/projects/1/assistant/chat",
    "$.cached",
  );
  await expectValid("counterpart uses the assistant response validator", () =>
    client.runCounterpart(1, {}), { reply: "Reflection", cached: false });
  await expectInvalid(
    "assistant settings reject a leaked write-only key",
    () => client.getAssistantSettings(1),
    json(assistantSettings({ api_key: "ultra-secret-value" })),
    "GET",
    "/api/projects/1/assistant/settings",
    "$.api_key",
  ).then((error) => {
    check("validation errors never echo response values", !error?.message.includes("ultra-secret-value"));
  });
  await expectValid("assistant settings PATCH validates the redacted response", () =>
    client.patchAssistantSettings(1, assistantSettings()), assistantSettings());
  await expectInvalid(
    "AI behavior rejects a wrong flag type",
    () => client.getAiBehavior(1),
    json(aiBehavior({ connector_enabled: 1 })),
    "GET",
    "/api/projects/1/ai/behavior",
    "$.connector_enabled",
  );
  await expectValid(
    "Voice Billy proposals validate required nullable fields",
    () => client.voiceBillyGenerate(1, { operation: "ask", transcript_text: "Question" }),
    voiceBillyProposal({ future_metadata: { version: 2 } }),
    (value) =>
      (value as unknown as { future_metadata?: { version?: number } }).future_metadata?.version === 2,
  );
  await expectInvalid(
    "Voice Billy proposals reject malformed GN references",
    () => client.voiceBillyGenerate(1, { operation: "edit", transcript_text: "Revise" }),
    json(voiceBillyProposal({ gn_ref: [2, "unsafe"] })),
    "POST",
    "/api/projects/1/voice/billy/generate",
    "$.gn_ref[1]",
  );

  await expectInvalid(
    "Logos action catalogs reject malformed sections",
    () => client.listLogosActions(1),
    json([logosAction({ sections: ["scene", 2] })]),
    "GET",
    "/api/projects/1/logos/actions",
    "$[0].sections[1]",
  );
  await expectInvalid(
    "Logos results reject non-object operations",
    () => client.runLogos(1, { action: "diagnose" }),
    json(logosResult({ proposed_operations: [[]] })),
    "POST",
    "/api/projects/1/logos/run",
    "$.proposed_operations[0]",
  );
  await expectInvalid(
    "proactive Logos results reject malformed confidence",
    () => client.listLogosProactive(1),
    json([logosSuggestion({ confidence: "high" })]),
    "GET",
    "/api/projects/1/logos/proactive",
    "$[0].confidence",
  );
  await expectInvalid(
    "connector catalogs require parameter defaults",
    () => client.listConnectorActions(1),
    json([{ name: "lookup", description: "", category: "", params: [{
      name: "query",
      param_type: "str",
      required: true,
    }] }]),
    "GET",
    "/api/projects/1/connector/actions",
    "$[0].params[0].default",
  );
  await expectValid("connector execution validates its open result payload", () =>
    client.connectorExecute(1, { action: "lookup" }), connectorResult({ result: { rows: [1] } }));
  await expectInvalid(
    "assistant actions require the connector result envelope",
    () => client.assistantAction(1, { action: "lookup" }),
    json({ ok: true, action: "lookup", error: "" }),
    "POST",
    "/api/projects/1/assistant/action",
    "$.result",
  );

  await expectInvalid(
    "quantum generation requires an object payload",
    () => client.generateQuantumOutline(1, { premise: "A choice" }),
    json(quantumResult({ payload: [] })),
    "POST",
    "/api/projects/1/quantum/outline",
    "$.payload",
  );
  await expectValid("quantum branches use the same response validator", () =>
    client.generateQuantumBranches(1, { situation: "A choice" }), quantumResult({ kind: "branches" }));
  await expectInvalid(
    "quantum settings reject malformed weights",
    () => client.getQuantumSettings(1),
    json(quantumSettings({ weights: { novelty: "heavy" } })),
    "GET",
    "/api/projects/1/quantum/settings",
    "$.weights.novelty",
  );
  await expectValid(
    "extraction start accepts the real running-job null result",
    () => client.startExtract(1, true),
    extractionJob(),
  );
  await expectInvalid(
    "extraction start validates its job envelope",
    () => client.startExtract(1, true),
    json(extractionJob({ job_id: 7 })),
    "POST",
    "/api/projects/1/extract?use_llm=true",
    "$.job_id",
  );
  await expectInvalid(
    "extraction polling rejects malformed nested proposal hints",
    () => client.getExtractJob(1, "job-1"),
    json(extractionJob({
      status: "done",
      done: 1,
      result: extractionResult({
        scenes: [sceneExtraction({
          relations: [relationProposal({
            source_hint: {
              existing_id: 4,
              existing_name: "Setup",
              score: "close",
            },
          })],
        })],
      }),
    })),
    "GET",
    "/api/projects/1/extract/jobs/job-1",
    "$.result.scenes[0].relations[0].source_hint.score",
  );
  await expectInvalid(
    "extraction cancellation validates its returned job",
    () => client.cancelExtractJob(1, "job-1"),
    json(extractionJob({ status: "cancelling", total: 1.5 })),
    "DELETE",
    "/api/projects/1/extract/jobs/job-1",
    "$.total",
  );

  await expectInvalid(
    "validated endpoints reject the wrong content type",
    () => client.getProject(1),
    new Response(JSON.stringify(project()), { status: 200, headers: { "content-type": "text/plain" } }),
    "GET",
    "/api/projects/1",
    "$",
  );
  await expectInvalid(
    "malformed JSON becomes a stable validation error",
    () => client.getProject(1),
    new Response("{", { status: 200, headers: { "content-type": "application/json" } }),
    "GET",
    "/api/projects/1",
    "not valid JSON",
  );
  await expectInvalid(
    "unexpected 204 cannot masquerade as a DTO",
    () => client.getSettings(1),
    new Response(null, { status: 204 }),
    "GET",
    "/api/projects/1/settings",
    "$",
  );

  installResponse(() => json({ error: { code: "upstream", message: "Unavailable" } }, 502));
  let httpFailure: unknown = null;
  try {
    await client.getProject(1);
  } catch (error) {
    httpFailure = error;
  }
  check("HTTP errors take precedence over response validation", httpFailure instanceof ApiRequestError
    && !(httpFailure instanceof ApiResponseValidationError));

  let retryCalls = 0;
  globalThis.fetch = async () => {
    retryCalls += 1;
    return retryCalls === 1 ? json([project({ title: 7 })]) : json([project()]);
  };
  let invalidRead: unknown = null;
  try {
    await client.listProjects();
  } catch (error) {
    invalidRead = error;
  }
  const retriedProjects = await client.listProjects();
  check("an invalid coalesced GET is evicted for retry", invalidRead instanceof ApiResponseValidationError
    && retryCalls === 2 && retriedProjects.length === 1);

  let patchCalls = 0;
  globalThis.fetch = async () => {
    patchCalls += 1;
    return patchCalls === 1 ? json(project({ title: false })) : json(project({ title: "Recovered" }));
  };
  const rejectedPatch = client.updateProject(1, { title: "Invalid response" }).catch((error) => error);
  const recoveredPatch = client.updateProject(1, { title: "Recovered" });
  const [patchError, patchValue] = await Promise.all([rejectedPatch, recoveredPatch]);
  check("PATCH serialization continues after response validation fails",
    patchError instanceof ApiResponseValidationError
      && patchCalls === 2
      && patchValue.title === "Recovered");

  let releaseWrite: ((response: Response) => void) | undefined;
  globalThis.fetch = () => new Promise<Response>((resolve) => {
    releaseWrite = resolve;
  });
  const trackedWrite = client.createScene(1, { title: "Tracked" });
  const trackedResult = trackedWrite.catch((error) => error);
  const barrierResult = flushPendingProjectSaves().catch((error) => error);
  for (let index = 0; index < 6; index += 1) await Promise.resolve();
  releaseWrite?.(json(scene({ content: 99 })));
  const [writeError, barrierError] = await Promise.all([trackedResult, barrierResult]);
  check("invalid mutation responses remain visible to the save barrier",
    writeError instanceof ApiResponseValidationError && barrierError instanceof PendingProjectSaveError);
} finally {
  client.dispose?.();
  globalThis.fetch = originalFetch;
}

console.log("Runtime DTO validation tests: " + passed + " passed, " + failures.length + " failed");
for (const failure of failures) console.error("  FAIL: " + failure);
if (failures.length) throw new Error(failures.length + " runtime DTO validation test(s) failed");
console.log("RUNTIME DTO VALIDATION TESTS: PASS");
