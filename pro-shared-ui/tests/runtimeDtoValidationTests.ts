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

const projectSearch = (overrides: Record<string, unknown> = {}) => ({
  query: "hero",
  matches: [
    { kind: "scene", id: 2, title: "Arrival", excerpt: "The hero arrives." },
    { kind: "comment", id: 5, title: "Comment 5", excerpt: "Sharpen this.", revision: null, resolved: false },
  ],
  limit: 40,
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

const storyStructure = (sceneOverrides: Record<string, unknown> = {}, overrides: Record<string, unknown> = {}) => ({
  project_id: 1,
  revision: "b".repeat(64),
  chapter_level: true,
  scene_count: 1,
  orphan_count: 0,
  acts: [{
    name: "Act One",
    number: "1",
    unassigned: false,
    scene_count: 1,
    chapters: [{
      name: "Chapter One",
      number: "1.1",
      unassigned: false,
      scene_count: 1,
      scenes: [{
        id: 2,
        title: "Scene",
        beat: "Opening Image",
        episode_id: null,
        number: "1.1.1",
        order_index: 1,
        is_orphan: false,
        ...sceneOverrides,
      }],
    }],
  }],
  ...overrides,
});

const storyStructureCommandResult = (overrides: Record<string, unknown> = {}) => ({
  structure: storyStructure(),
  changed: true,
  created_scene_id: 2,
  affected_scene_ids: [2],
  ...overrides,
});

const manuscriptSnapshot = (sceneOverrides: Record<string, unknown> = {}, overrides: Record<string, unknown> = {}) => ({
  project_id: 1,
  chapter_level: true,
  scene_count: 1,
  orphan_count: 0,
  scenes: [scene({ order_index: 1, ...sceneOverrides })],
  ...overrides,
});

const timelineSnapshot = (
  eventOverrides: Record<string, unknown> = {},
  overrides: Record<string, unknown> = {},
) => ({
  project_id: 1,
  revision: "c".repeat(64),
  order_mode: "structural",
  lanes: [{
    id: 4,
    name: "Main",
    color_label: "cyan",
    order_index: 0,
    collapsed: false,
    event_count: 1,
  }],
  events: [{
    id: 2,
    order_index: 1,
    title: "Scene",
    structural_number: "1.1.1",
    act: "Act One",
    chapter: "Chapter One",
    plotline: "Main",
    color_label: "",
    lane_id: 4,
    time_of_day: "DAY",
    location: "Station",
    duration_minutes: 5,
    character_states: [{ character: "Marlow", state: "alert" }],
    ...eventOverrides,
  }],
  off_timeline: [{
    id: 3,
    title: "Later",
    structural_number: "1.1.2",
    act: "Act One",
    chapter: "Chapter One",
  }],
  ...overrides,
});

const timelineCommandResult = (overrides: Record<string, unknown> = {}) => {
  const timeline = overrides.timeline ?? timelineSnapshot({}, { revision: "d".repeat(64) });
  return {
    timeline,
    replayed: false,
    applied_revision: (timeline as { revision: string }).revision,
    changed: true,
    affected_scene_ids: [2],
    ...overrides,
  };
};

const canvasPlotSnapshot = (overrides: Record<string, unknown> = {}) => ({
  project_id: 1,
  revision: "d".repeat(64),
  nodes: [{
    id: 10, title: "Signal", body: "A message arrives.", x: 10, y: 20,
    width: 180, height: 110, color_label: "cyan", group_label: "Act I",
    scene_id: 2, sort_order: 1, created_at: "2026-10-05T09:00:00Z",
  }, {
    id: 11, title: "Choice", body: "", x: 320, y: 40,
    width: 190, height: 120, color_label: "violet", group_label: "Act II",
    scene_id: null, sort_order: 2, created_at: "2026-10-05T09:01:00Z",
  }],
  links: [{
    id: 20, source_node_id: 10, target_node_id: 11, label: "causes",
    color_label: "amber", link_type: "causality", created_at: "2026-10-05T09:02:00Z",
  }],
  frames: [{
    id: 30, title: "Act I", color_label: "blue", x: 0, y: 0,
    width: 600, height: 340, created_at: "2026-10-05T09:03:00Z",
  }],
  ...overrides,
});

const canvasPlotCommandResult = (overrides: Record<string, unknown> = {}) => {
  const canvasPlot = overrides.canvas_plot ?? canvasPlotSnapshot({ revision: "e".repeat(64) });
  return {
    canvas_plot: canvasPlot,
    replayed: false,
    applied_revision: (canvasPlot as { revision: string }).revision,
    changed: true,
    affected_node_ids: [10],
    affected_link_ids: [],
    affected_frame_ids: [],
    created_node_id: null,
    created_link_id: null,
    created_frame_id: null,
    ...overrides,
  };
};

const knowledgeGraph = (overrides: Record<string, unknown> = {}) => ({
  project_id: 1,
  revision: "a".repeat(64),
  writing_mode: "novel",
  focus_key: null,
  depth: 1,
  include_inferred: true,
  view_mode: "project_map",
  story_diagnostics_available: true,
  story_gravity_available: true,
  nodes: [{
    key: "project:project:1", node_type: "project", source_type: "project",
    source_id: "1", label: "Project", summary: "", metadata: {}, degree: 1,
    story_gravity: null,
  }, {
    key: "scene:scene:2", node_type: "scene", source_type: "scene",
    source_id: "2", label: "Scene", summary: "", metadata: {}, degree: 1,
    story_gravity: 0.75,
  }],
  edges: [{
    source: "project:project:1", target: "scene:scene:2", edge_type: "contains",
    confidence: "confirmed", provenance: "project structure", source_system: "structure",
    explanation: "Scene membership.", is_user_confirmed: false, is_inferred: false,
    is_hidden: false, metadata: {},
  }],
  node_count: 2,
  edge_count: 1,
  returned_node_count: 2,
  returned_edge_count: 1,
  truncated: false,
  orphan_keys: [],
  orphan_count: 0,
  weak_links: [],
  weak_link_count: 0,
  hidden_edges: [],
  hidden_edge_count: 0,
  warnings: [],
  unavailable: [],
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

const psykeCommandPlan = (overrides: Record<string, unknown> = {}) => ({
  plan_id: "lfcp_test",
  command: "create",
  normalized_command: "/create character Vesper",
  action: "create_psyke_entry",
  summary: "Create character 'Vesper'",
  effects: ["Add one character."],
  requires_confirmation: true,
  mutates: true,
  target_type: "psyke_entry",
  target_id: null,
  expires_at: "2026-09-30T12:00:00Z",
  ...overrides,
});

const psykeCommandExecution = (overrides: Record<string, unknown> = {}) => ({
  ok: true,
  action: "create_psyke_entry",
  message: "Created Vesper.",
  mutated: true,
  target_type: "psyke_entry",
  target_id: 7,
  ...overrides,
});

const decisionCard = (overrides: Record<string, unknown> = {}) => ({
  id: "missing_description",
  category: "structure",
  severity: "suggestion",
  confidence: "confirmed",
  title: "Project has no description.",
  explanation: "",
  suggested_action: "Add a description.",
  related_section: "Projects",
  related_target_type: "",
  related_target_id: null,
  related_target_key: "",
  created_from: "deterministic",
  graph_focus_key: "",
  graph_view_mode: null,
  graph_include_inferred: true,
  graph_depth: 1,
  evidence: [],
  evidence_total: 0,
  ...overrides,
});

const graphDecisionCard = (overrides: Record<string, unknown> = {}) => decisionCard({
  id: "kg_isolated_theme:psyke:6",
  category: "psyke",
  severity: "opportunity",
  confidence: "likely",
  title: "Theme is isolated.",
  created_from: "knowledge_graph",
  graph_focus_key: "theme:psyke:6",
  graph_view_mode: "project_map",
  graph_include_inferred: true,
  evidence: [{
    kind: "node",
    label: "Static",
    detail: "theme source psyke:6.",
    graph_focus_key: "theme:psyke:6",
    source_key: "",
    target_key: "",
    edge_type: "",
    confidence: "confirmed",
    source_system: "psyke",
    provenance: "psyke:6",
    related_section: "",
    related_target_type: "",
    related_target_id: null,
    related_target_key: "",
  }],
  evidence_total: 1,
  ...overrides,
});

const continuityDecisionCard = (overrides: Record<string, unknown> = {}) => decisionCard({
  id: "continuity_0123456789abcdef",
  category: "continuity",
  severity: "warning",
  confidence: "likely",
  title: "Location jump without transition.",
  related_section: "Continuity",
  related_target_type: "continuity_issue",
  related_target_key: "0123456789abcdef",
  created_from: "semantic_continuity",
  evidence: [{
    kind: "continuity_issue",
    label: "Location jump without transition.",
    detail: "location jump · spatial",
    graph_focus_key: "",
    source_key: "",
    target_key: "",
    edge_type: "",
    confidence: "likely",
    source_system: "semantic_continuity",
    provenance: "continuity:location_jump",
    related_section: "Continuity",
    related_target_type: "continuity_issue",
    related_target_id: null,
    related_target_key: "0123456789abcdef",
  }],
  evidence_total: 1,
  ...overrides,
});

const decisionRadar = (overrides: Record<string, unknown> = {}) => ({
  project_id: 1,
  generated_light: false,
  summary_line: "Radar",
  radar: [decisionCard()],
  knowledge_graph_available: true,
  knowledge_graph_cards: [graphDecisionCard()],
  continuity_available: true,
  continuity_cards: [continuityDecisionCard()],
  ...overrides,
});

const continuityIssue = (overrides: Record<string, unknown> = {}) => ({
  id: "0123456789abcdef",
  review_fingerprint: "f".repeat(64),
  issue_type: "continuity_gap",
  dimension: "plot",
  severity: "blocking",
  confidence: "confirmed",
  title: "A setup points to a missing payoff.",
  explanation: "The linked payoff no longer exists.",
  suggested_action: "Repair the setup/payoff link.",
  related_scene_ids: [2],
  status: "open",
  ...overrides,
});

const continuityReport = (overrides: Record<string, unknown> = {}) => ({
  project_id: 1,
  review_revision: "a".repeat(64),
  writing_mode: "novel",
  issues: [continuityIssue()],
  blocking_count: 1,
  warning_count: 0,
  unavailable: [],
  ...overrides,
});

const continuityCommand = {
  kind: "resolve_issue" as const,
  expected_revision: "a".repeat(64),
  issue_id: "0123456789abcdef",
  expected_issue_fingerprint: "f".repeat(64),
};

const continuityCommandResult = (overrides: Record<string, unknown> = {}) => ({
  continuity: continuityReport({
    review_revision: "b".repeat(64),
    issues: [continuityIssue({ status: "resolved" })],
    blocking_count: 0,
  }),
  changed: true,
  affected_issue_id: continuityCommand.issue_id,
  previous_status: "open",
  status: "resolved",
  replayed: false,
  applied_revision: "b".repeat(64),
  ...overrides,
});

const continuityCommandReceipt = (overrides: Record<string, unknown> = {}) => ({
  project_id: 1,
  request_digest: "c".repeat(64),
  command_kind: "resolve_issue",
  expected_revision: continuityCommand.expected_revision,
  applied_revision: "b".repeat(64),
  original_changed: true,
  original_affected_issue_id: continuityCommand.issue_id,
  expected_issue_fingerprint: continuityCommand.expected_issue_fingerprint,
  previous_status: "open",
  status: "resolved",
  committed_at: "2026-10-07T12:00:00Z",
  ...overrides,
});

const originalFetch = globalThis.fetch;
let lastRequestUrl = "";
const client = createHttpApiClient("", "", {
  healthTimeoutMs: 0,
  readTimeoutMs: 0,
  writeTimeoutMs: 0,
  longRequestTimeoutMs: 0,
});

const installResponse = (factory: () => Response): void => {
  globalThis.fetch = async (input) => {
    lastRequestUrl = String(input);
    return factory();
  };
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
  await expectValid(
    "project search validates typed matches with optional metadata",
    () => client.searchProject(1, "hero", ["scene", "psyke"]),
    projectSearch(),
  );
  await expectInvalid(
    "project search rejects an unknown match kind",
    () => client.searchProject(1, "hero", ["scene", "psyke"]),
    json(projectSearch({ matches: [{ kind: "file", id: 2, title: "Wrong", excerpt: "Wrong" }] })),
    "GET",
    "/api/projects/1/search?q=hero&kinds=scene&kinds=psyke",
    "$.matches[0].kind",
  );
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

  await expectValid(
    "PSYKE command planning validates its typed preview",
    () => client.planPsykeConsoleCommand(1, { command: "/create character Vesper" }),
    psykeCommandPlan(),
  );
  await expectInvalid(
    "PSYKE command planning rejects an unrecognized action",
    () => client.planPsykeConsoleCommand(1, { command: "/create character Vesper" }),
    json(psykeCommandPlan({ action: "delete_everything" })),
    "POST",
    "/api/projects/1/psyke/console/plan",
    "$.action",
  );
  await expectValid(
    "PSYKE command execution validates its typed directive",
    () => client.executePsykeConsoleCommand(1, { plan_id: "lfcp_test", confirmed: true }, true),
    psykeCommandExecution(),
  );
  await expectInvalid(
    "PSYKE command execution rejects a malformed target id",
    () => client.executePsykeConsoleCommand(1, { plan_id: "lfcp_test", confirmed: true }, true),
    json(psykeCommandExecution({ target_id: "7" })),
    "POST",
    "/api/projects/1/psyke/console/execute",
    "$.target_id",
  );

  await expectInvalid(
    "scene lists reject a malformed nested member",
    () => client.listScenes(1),
    json([scene({ tags: ["valid", 4] })]),
    "GET",
    "/api/projects/1/scenes",
    "$[0].tags[1]",
  );
  await expectValid(
    "manuscript snapshots validate full revisioned canonical scenes",
    () => client.getManuscriptSnapshot(1),
    manuscriptSnapshot(),
    (value) => value.scenes[0]?.content === "Opening line",
  );
  await expectInvalid(
    "manuscript snapshots reject a malformed nested scene",
    () => client.getManuscriptSnapshot(1),
    json(manuscriptSnapshot({ character_ids: ["2"] })),
    "GET",
    "/api/projects/1/manuscript-snapshot",
    "$.scenes[0].character_ids[0]",
  );
  await expectInvalid(
    "manuscript snapshots require optimistic revisions",
    () => client.getManuscriptSnapshot(1),
    json(manuscriptSnapshot({ revision: "" })),
    "GET",
    "/api/projects/1/manuscript-snapshot",
    "$.scenes[0].revision",
  );
  await expectInvalid(
    "manuscript snapshots reject a count that disagrees with the array",
    () => client.getManuscriptSnapshot(1),
    json(manuscriptSnapshot({}, { scene_count: 2 })),
    "GET",
    "/api/projects/1/manuscript-snapshot",
    "$.scene_count",
  );
  await expectInvalid(
    "manuscript snapshots reject non-canonical order indexes",
    () => client.getManuscriptSnapshot(1),
    json(manuscriptSnapshot({ order_index: 2 })),
    "GET",
    "/api/projects/1/manuscript-snapshot",
    "$.scenes[0].order_index",
  );
  await expectInvalid(
    "manuscript snapshots reject duplicate scene ids",
    () => client.getManuscriptSnapshot(1),
    json(manuscriptSnapshot({}, {
      scene_count: 2,
      scenes: [scene({ order_index: 1 }), scene({ order_index: 2 })],
    })),
    "GET",
    "/api/projects/1/manuscript-snapshot",
    "$.scenes[1].id",
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
    "story structure validates its compact nested projection",
    () => client.getStoryStructure(1),
    storyStructure(),
    (value) => value.acts[0]?.chapters[0]?.scenes[0]?.number === "1.1.1",
  );
  await expectValid(
    "story structure placement validates its refreshed projection",
    () => client.placeScene(1, 2, {
      expected_revision: "b".repeat(64),
      act: "Act One",
      chapter: "Chapter One",
      index: 0,
    }),
    storyStructure(),
  );
  await expectValid(
    "story structure commands validate their transactional result",
    () => client.executeStoryStructureCommand(1, {
      kind: "create_scene",
      expected_revision: "b".repeat(64),
      title: "New Scene",
      act: "Act One",
      chapter: "Chapter One",
      index: 1,
    }),
    storyStructureCommandResult(),
    (value) => value.changed && value.created_scene_id === 2 && value.affected_scene_ids[0] === 2,
  );
  await expectValid(
    "unchanged structure commands carry no mutation metadata",
    () => client.executeStoryStructureCommand(1, {
      kind: "repair_orphans",
      expected_revision: "b".repeat(64),
    }),
    storyStructureCommandResult({ changed: false, created_scene_id: null, affected_scene_ids: [] }),
    (value) => !value.changed && value.affected_scene_ids.length === 0,
  );
  await expectValid(
    "delete commands may return their removed id plus surviving dependency updates",
    () => client.executeStoryStructureCommand(1, {
      kind: "delete_scene",
      expected_revision: "b".repeat(64),
      scene_id: 2,
    }),
    storyStructureCommandResult({
      structure: storyStructure({ id: 3 }),
      created_scene_id: null,
      affected_scene_ids: [2, 3],
    }),
  );
  await expectInvalid(
    "unchanged structure commands reject affected ids",
    () => client.executeStoryStructureCommand(1, {
      kind: "repair_orphans",
      expected_revision: "b".repeat(64),
    }),
    json(storyStructureCommandResult({ changed: false, created_scene_id: null, affected_scene_ids: [2] })),
    "POST",
    "/api/projects/1/story-structure/commands",
    "$.affected_scene_ids",
  );
  await expectInvalid(
    "unchanged structure commands reject a created id",
    () => client.executeStoryStructureCommand(1, {
      kind: "repair_orphans",
      expected_revision: "b".repeat(64),
    }),
    json(storyStructureCommandResult({ changed: false, affected_scene_ids: [] })),
    "POST",
    "/api/projects/1/story-structure/commands",
    "$.created_scene_id",
  );
  await expectInvalid(
    "changed structure commands require affected ids",
    () => client.executeStoryStructureCommand(1, {
      kind: "repair_orphans",
      expected_revision: "b".repeat(64),
    }),
    json(storyStructureCommandResult({ created_scene_id: null, affected_scene_ids: [] })),
    "POST",
    "/api/projects/1/story-structure/commands",
    "$.affected_scene_ids",
  );
  await expectInvalid(
    "created structure scenes must be affected",
    () => client.executeStoryStructureCommand(1, {
      kind: "create_scene",
      expected_revision: "b".repeat(64),
      act: "Act One",
      chapter: "Chapter One",
      index: 1,
    }),
    json(storyStructureCommandResult({ affected_scene_ids: [3] })),
    "POST",
    "/api/projects/1/story-structure/commands",
    "$.created_scene_id",
  );
  await expectInvalid(
    "created structure scene ids must be positive",
    () => client.executeStoryStructureCommand(1, {
      kind: "create_scene",
      expected_revision: "b".repeat(64),
      act: "Act One",
      chapter: "Chapter One",
      index: 1,
    }),
    json(storyStructureCommandResult({ created_scene_id: 0, affected_scene_ids: [0] })),
    "POST",
    "/api/projects/1/story-structure/commands",
    "$.created_scene_id",
  );
  await expectInvalid(
    "created structure scenes must be present in the refreshed structure",
    () => client.executeStoryStructureCommand(1, {
      kind: "create_scene",
      expected_revision: "b".repeat(64),
      act: "Act One",
      chapter: "Chapter One",
      index: 1,
    }),
    json(storyStructureCommandResult({ created_scene_id: 3, affected_scene_ids: [3] })),
    "POST",
    "/api/projects/1/story-structure/commands",
    "$.created_scene_id",
  );
  await expectInvalid(
    "structure command responses must belong to the requested project",
    () => client.executeStoryStructureCommand(1, {
      kind: "create_scene",
      expected_revision: "b".repeat(64),
      act: "Act One",
      chapter: "Chapter One",
      index: 1,
    }),
    json(storyStructureCommandResult({ structure: storyStructure({}, { project_id: 7 }) })),
    "POST",
    "/api/projects/1/story-structure/commands",
    "$.structure.project_id",
  );
  await expectInvalid(
    "non-delete affected scenes must survive in the refreshed structure",
    () => client.executeStoryStructureCommand(1, {
      kind: "rename_act",
      expected_revision: "b".repeat(64),
      act: "Act One",
      new_name: "Opening",
    }),
    json(storyStructureCommandResult({ created_scene_id: null, affected_scene_ids: [3] })),
    "POST",
    "/api/projects/1/story-structure/commands",
    "$.affected_scene_ids[0]",
  );
  await expectInvalid(
    "story structure commands require the nested authoritative projection",
    () => client.executeStoryStructureCommand(1, {
      kind: "repair_orphans",
      expected_revision: "b".repeat(64),
    }),
    json(storyStructureCommandResult({
      structure: storyStructure({}, { revision: "invalid" }),
    })),
    "POST",
    "/api/projects/1/story-structure/commands",
    "$.structure.revision",
  );
  await expectInvalid(
    "story structure commands require nullable created scene ids",
    () => client.executeStoryStructureCommand(1, {
      kind: "create_act",
      expected_revision: "b".repeat(64),
      act: "Act Two",
      index: 1,
    }),
    json(storyStructureCommandResult({ created_scene_id: undefined })),
    "POST",
    "/api/projects/1/story-structure/commands",
    "$.created_scene_id",
  );
  await expectInvalid(
    "story structure commands reject duplicate affected scene ids",
    () => client.executeStoryStructureCommand(1, {
      kind: "rename_act",
      expected_revision: "b".repeat(64),
      act: "Act One",
      new_name: "Opening",
    }),
    json(storyStructureCommandResult({ created_scene_id: null, affected_scene_ids: [2, 2] })),
    "POST",
    "/api/projects/1/story-structure/commands",
    "$.affected_scene_ids[1]",
  );
  await expectInvalid(
    "story structure requires its project-wide revision",
    () => client.getStoryStructure(1),
    json(storyStructure({}, { revision: "" })),
    "GET",
    "/api/projects/1/story-structure",
    "$.revision",
  );
  await expectInvalid(
    "story structure requires nullable episode ownership",
    () => client.getStoryStructure(1),
    json(storyStructure({ episode_id: undefined })),
    "GET",
    "/api/projects/1/story-structure",
    "$.acts[0].chapters[0].scenes[0].episode_id",
  );
  await expectInvalid(
    "story structure reports a malformed deeply nested scene",
    () => client.getStoryStructure(1),
    json(storyStructure({ is_orphan: "false" })),
    "GET",
    "/api/projects/1/story-structure",
    "$.acts[0].chapters[0].scenes[0].is_orphan",
  );

  await expectValid(
    "Timeline snapshots validate lanes, effective order, and off-Timeline refs",
    () => client.getTimeline(1),
    timelineSnapshot(),
    (value) => value.lanes[0]?.event_count === 1 && value.events[0]?.lane_id === 4,
  );
  await expectValid(
    "Timeline durations follow the Core integer contract",
    () => client.getTimeline(1),
    timelineSnapshot({ duration_minutes: -1 }),
    (value) => value.events[0]?.duration_minutes === -1,
  );
  await expectInvalid(
    "Timeline snapshots belong to the requested project",
    () => client.getTimeline(1),
    json(timelineSnapshot({}, { project_id: 7 })),
    "GET",
    "/api/projects/1/timeline",
    "$.project_id",
  );
  await expectValid(
    "Timeline commands validate their committed snapshot",
    () => client.executeTimelineCommand(1, {
      kind: "place_event",
      expected_revision: "c".repeat(64),
      scene_id: 2,
      lane_id: 4,
      index: 0,
    }),
    timelineCommandResult(),
    (value) => value.changed && value.timeline.events[0]?.id === 2,
  );
  await expectValid(
    "unchanged Timeline commands retain the guarded revision",
    () => client.executeTimelineCommand(1, {
      kind: "set_order_mode",
      expected_revision: "c".repeat(64),
      mode: "structural",
    }),
    timelineCommandResult({
      timeline: timelineSnapshot(),
      changed: false,
      affected_scene_ids: [],
    }),
  );
  await expectValid(
    "replayed Timeline commands may return a newer coherent board",
    () => client.executeTimelineCommand(1, {
      kind: "create_lane",
      expected_revision: "c".repeat(64),
      name: "Subplot",
    }),
    timelineCommandResult({
      timeline: timelineSnapshot({}, { revision: "e".repeat(64) }),
      replayed: true,
      applied_revision: "d".repeat(64),
      changed: false,
      affected_scene_ids: [],
    }),
    (value) => value.replayed && value.applied_revision === "d".repeat(64),
  );
  await expectInvalid(
    "replayed Timeline commands cannot claim a fresh mutation",
    () => client.executeTimelineCommand(1, {
      kind: "create_lane",
      expected_revision: "c".repeat(64),
      name: "Subplot",
    }),
    json(timelineCommandResult({ replayed: true })),
    "POST",
    "/api/projects/1/timeline/commands",
    "$.changed",
  );
  await expectInvalid(
    "changed Timeline commands require a new revision",
    () => client.executeTimelineCommand(1, {
      kind: "create_lane",
      expected_revision: "c".repeat(64),
      name: "Subplot",
    }),
    json(timelineCommandResult({ timeline: timelineSnapshot() })),
    "POST",
    "/api/projects/1/timeline/commands",
    "$.timeline.revision",
  );
  await expectInvalid(
    "unchanged Timeline commands cannot invent a revision",
    () => client.executeTimelineCommand(1, {
      kind: "set_order_mode",
      expected_revision: "c".repeat(64),
      mode: "structural",
    }),
    json(timelineCommandResult({ changed: false, affected_scene_ids: [] })),
    "POST",
    "/api/projects/1/timeline/commands",
    "$.timeline.revision",
  );
  await expectInvalid(
    "Timeline snapshots require a content revision",
    () => client.getTimeline(1),
    json(timelineSnapshot({}, { revision: "stale" })),
    "GET",
    "/api/projects/1/timeline",
    "$.revision",
  );
  await expectInvalid(
    "Timeline snapshots require dense lane indexes",
    () => client.getTimeline(1),
    json(timelineSnapshot({}, {
      lanes: [{
        id: 4, name: "Main", color_label: "cyan", order_index: 2,
        collapsed: false, event_count: 1,
      }],
    })),
    "GET",
    "/api/projects/1/timeline",
    "$.lanes[0].order_index",
  );
  await expectInvalid(
    "Timeline events must reference a returned lane",
    () => client.getTimeline(1),
    json(timelineSnapshot({ lane_id: 99 })),
    "GET",
    "/api/projects/1/timeline",
    "$.events[0].lane_id",
  );
  await expectInvalid(
    "Timeline event lane ids must match the trimmed plotline",
    () => client.getTimeline(1),
    json(timelineSnapshot({ plotline: "Other" })),
    "GET",
    "/api/projects/1/timeline",
    "$.events[0].lane_id",
  );
  await expectInvalid(
    "Timeline events cannot be Unassigned when a matching lane is returned",
    () => client.getTimeline(1),
    json(timelineSnapshot({ plotline: " Main ", lane_id: null }, {
      lanes: [{
        id: 4, name: "Main", color_label: "cyan", order_index: 0,
        collapsed: false, event_count: 0,
      }],
    })),
    "GET",
    "/api/projects/1/timeline",
    "$.events[0].lane_id",
  );
  await expectValid(
    "legacy unmatched Timeline plotlines remain valid as Unassigned",
    () => client.getTimeline(1),
    timelineSnapshot({ plotline: "Legacy lane", lane_id: null }, {
      lanes: [{
        id: 4, name: "Main", color_label: "cyan", order_index: 0,
        collapsed: false, event_count: 0,
      }],
    }),
  );
  await expectInvalid(
    "Timeline lane counts must match returned events",
    () => client.getTimeline(1),
    json(timelineSnapshot({}, {
      lanes: [{
        id: 4, name: "Main", color_label: "cyan", order_index: 0,
        collapsed: false, event_count: 2,
      }],
    })),
    "GET",
    "/api/projects/1/timeline",
    "$.lanes[0].event_count",
  );
  await expectInvalid(
    "Timeline off-Timeline refs cannot duplicate events",
    () => client.getTimeline(1),
    json(timelineSnapshot({}, {
      off_timeline: [{
        id: 2, title: "Scene", structural_number: "1.1.1",
        act: "Act One", chapter: "Chapter One",
      }],
    })),
    "GET",
    "/api/projects/1/timeline",
    "$.off_timeline[0].id",
  );
  await expectInvalid(
    "unchanged Timeline commands carry no affected Scene ids",
    () => client.executeTimelineCommand(1, {
      kind: "set_order_mode",
      expected_revision: "c".repeat(64),
      mode: "structural",
    }),
    json(timelineCommandResult({ changed: false, affected_scene_ids: [2] })),
    "POST",
    "/api/projects/1/timeline/commands",
    "$.affected_scene_ids",
  );
  await expectInvalid(
    "Timeline command affected ids must belong to the returned Timeline",
    () => client.executeTimelineCommand(1, {
      kind: "remove_event",
      expected_revision: "c".repeat(64),
      scene_id: 99,
    }),
    json(timelineCommandResult({ affected_scene_ids: [99] })),
    "POST",
    "/api/projects/1/timeline/commands",
    "$.affected_scene_ids[0]",
  );
  await expectInvalid(
    "Timeline command responses belong to the requested project",
    () => client.executeTimelineCommand(1, {
      kind: "create_lane",
      expected_revision: "c".repeat(64),
      name: "Subplot",
    }),
    json(timelineCommandResult({
      timeline: timelineSnapshot({}, { project_id: 7 }),
      affected_scene_ids: [],
    })),
    "POST",
    "/api/projects/1/timeline/commands",
    "$.timeline.project_id",
  );

  await expectValid(
    "Canvas Plot snapshots validate project-owned nodes, links, and frames",
    () => client.getCanvasPlot(1),
    canvasPlotSnapshot(),
    (value) => value.nodes.length === 2 && value.links[0]?.target_node_id === 11,
  );
  await expectInvalid(
    "Canvas Plot links must reference returned nodes",
    () => client.getCanvasPlot(1),
    json(canvasPlotSnapshot({
      links: [{
        id: 20, source_node_id: 10, target_node_id: 99, label: "causes",
        color_label: "amber", link_type: "causality", created_at: "2026-10-05T09:02:00Z",
      }],
    })),
    "GET",
    "/api/projects/1/canvas-plot",
    "$.links[0].target_node_id",
  );
  await expectInvalid(
    "Canvas Plot snapshots reject non-finite geometry",
    () => client.getCanvasPlot(1),
    json(canvasPlotSnapshot({
      nodes: [{
        id: 10, title: "Signal", body: "", x: null, y: 20,
        width: 180, height: 110, color_label: "", group_label: "",
        scene_id: null, sort_order: 1, created_at: "2026-10-05T09:00:00Z",
      }],
      links: [],
    })),
    "GET",
    "/api/projects/1/canvas-plot",
    "$.nodes[0].x",
  );
  await expectValid(
    "Canvas Plot commands validate revision transitions and created ids",
    () => client.executeCanvasPlotCommand(1, {
      kind: "create_node",
      expected_revision: "d".repeat(64),
      title: "Signal",
    }),
    canvasPlotCommandResult({
      affected_node_ids: [10],
      created_node_id: 10,
    }),
    (value) => value.created_node_id === 10,
  );
  await expectInvalid(
    "changed Canvas Plot commands require a new revision",
    () => client.executeCanvasPlotCommand(1, {
      kind: "update_node",
      expected_revision: "d".repeat(64),
      node_id: 10,
      x: 50,
    }),
    json(canvasPlotCommandResult({ canvas_plot: canvasPlotSnapshot() })),
    "POST",
    "/api/projects/1/canvas-plot/commands",
    "$.canvas_plot.revision",
  );
  await expectInvalid(
    "Canvas Plot created ids must match the command kind",
    () => client.executeCanvasPlotCommand(1, {
      kind: "update_node",
      expected_revision: "d".repeat(64),
      node_id: 10,
      x: 50,
    }),
    json(canvasPlotCommandResult({ created_node_id: 10 })),
    "POST",
    "/api/projects/1/canvas-plot/commands",
    "$.created_node_id",
  );
  await expectValid(
    "unchanged Canvas Plot commands retain the guarded revision",
    () => client.executeCanvasPlotCommand(1, {
      kind: "update_node",
      expected_revision: "d".repeat(64),
      node_id: 10,
      x: 10,
    }),
    canvasPlotCommandResult({
      canvas_plot: canvasPlotSnapshot(),
      changed: false,
      affected_node_ids: [],
    }),
  );
  await expectValid(
    "replayed Canvas Plot commands may return a newer coherent board",
    () => client.executeCanvasPlotCommand(1, {
      kind: "update_node",
      expected_revision: "d".repeat(64),
      node_id: 10,
      x: 50,
    }),
    canvasPlotCommandResult({
      canvas_plot: canvasPlotSnapshot({ revision: "f".repeat(64) }),
      replayed: true,
      applied_revision: "e".repeat(64),
      changed: false,
      affected_node_ids: [],
    }),
    (value) => value.replayed && value.applied_revision === "e".repeat(64),
  );
  await expectInvalid(
    "replayed Canvas Plot commands cannot claim a fresh mutation",
    () => client.executeCanvasPlotCommand(1, {
      kind: "update_node",
      expected_revision: "d".repeat(64),
      node_id: 10,
      x: 50,
    }),
    json(canvasPlotCommandResult({ replayed: true })),
    "POST",
    "/api/projects/1/canvas-plot/commands",
    "$.changed",
  );
  await expectInvalid(
    "fresh Canvas Plot commands bind applied revision to the returned board",
    () => client.executeCanvasPlotCommand(1, {
      kind: "update_node",
      expected_revision: "d".repeat(64),
      node_id: 10,
      x: 50,
    }),
    json(canvasPlotCommandResult({ applied_revision: "f".repeat(64) })),
    "POST",
    "/api/projects/1/canvas-plot/commands",
    "$.applied_revision",
  );

  await expectValid(
    "Continuity reports bind the canonical project and review revision",
    () => client.getContinuity(1),
    continuityReport(),
    (value) => value.project_id === 1 && value.review_revision === "a".repeat(64),
  );
  await expectInvalid(
    "Continuity reports reject a response for another project",
    () => client.getContinuity(1),
    json(continuityReport({ project_id: 2 })),
    "GET",
    "/api/projects/1/continuity",
    "$.project_id",
  );
  await expectInvalid(
    "Continuity reports reject non-canonical issue keys",
    () => client.getContinuity(1),
    json(continuityReport({ issues: [continuityIssue({ id: "short" })] })),
    "GET",
    "/api/projects/1/continuity",
    "$.issues[0].id",
  );
  await expectInvalid(
    "Continuity reports reject counts that include reviewed issues",
    () => client.getContinuity(1),
    json(continuityReport({
      issues: [continuityIssue({ status: "deferred" })],
      blocking_count: 1,
    })),
    "GET",
    "/api/projects/1/continuity",
    "$.blocking_count",
  );
  await expectValid(
    "Continuity command results bind the exact issue and fresh revision",
    () => client.executeContinuityCommand(1, continuityCommand, "continuity-test-key-0001"),
    continuityCommandResult(),
    (value) => value.status === "resolved" && value.continuity.review_revision === value.applied_revision,
  );
  await expectInvalid(
    "fresh Continuity command results require a new applied revision",
    () => client.executeContinuityCommand(1, continuityCommand, "continuity-test-key-0001"),
    json(continuityCommandResult({
      applied_revision: continuityCommand.expected_revision,
    })),
    "POST",
    "/api/projects/1/continuity/commands",
    "$.applied_revision",
  );
  await expectInvalid(
    "Continuity command results reject a different affected issue",
    () => client.executeContinuityCommand(1, continuityCommand, "continuity-test-key-0001"),
    json(continuityCommandResult({ affected_issue_id: "fedcba9876543210" })),
    "POST",
    "/api/projects/1/continuity/commands",
    "$.affected_issue_id",
  );
  await expectValid(
    "Continuity receipts bind the exact reviewed command",
    () => client.getContinuityCommandReceipt(1, "continuity-test-key-0001", continuityCommand),
    continuityCommandReceipt(),
    (value) => value.original_affected_issue_id === continuityCommand.issue_id,
  );
  await expectInvalid(
    "Continuity receipts reject a mismatched command kind",
    () => client.getContinuityCommandReceipt(1, "continuity-test-key-0001", continuityCommand),
    json(continuityCommandReceipt({ command_kind: "dismiss_issue", status: "dismissed" })),
    "GET",
    "/api/projects/1/continuity/command-receipt",
    "$.command_kind",
  );

  await expectValid(
    "Decision Radar accepts bounded traceable Graph and Continuity evidence",
    () => client.getDecisionRadar(1),
    decisionRadar(),
    (value) => value.knowledge_graph_cards[0]?.graph_focus_key === "theme:psyke:6"
      && value.continuity_cards[0]?.related_target_key === "0123456789abcdef",
  );
  await expectInvalid(
    "Decision Radar rejects a response for another project",
    () => client.getDecisionRadar(1),
    json(decisionRadar({ project_id: 2 })),
    "GET",
    "/api/projects/1/decision-radar",
    "$.project_id",
  );
  await expectInvalid(
    "Decision Radar rejects an unscoped graph deep link",
    () => client.getDecisionRadar(1),
    json(decisionRadar({
      knowledge_graph_cards: [graphDecisionCard({ graph_view_mode: null })],
    })),
    "GET",
    "/api/projects/1/decision-radar",
    "$.knowledge_graph_cards[0].graph_view_mode",
  );
  await expectInvalid(
    "Decision Radar rejects graph cards when graph availability is false",
    () => client.getDecisionRadar(1),
    json(decisionRadar({ knowledge_graph_available: false })),
    "GET",
    "/api/projects/1/decision-radar",
    "$.knowledge_graph_cards",
  );
  await expectInvalid(
    "Decision Radar rejects an understated evidence total",
    () => client.getDecisionRadar(1),
    json(decisionRadar({
      knowledge_graph_cards: [graphDecisionCard({ evidence_total: 0 })],
    })),
    "GET",
    "/api/projects/1/decision-radar",
    "$.knowledge_graph_cards[0].evidence_total",
  );
  await expectInvalid(
    "Decision Radar rejects continuity cards when continuity is unavailable",
    () => client.getDecisionRadar(1),
    json(decisionRadar({ continuity_available: false })),
    "GET",
    "/api/projects/1/decision-radar",
    "$.continuity_cards",
  );
  await expectInvalid(
    "Decision Radar rejects continuity cards without a canonical issue key",
    () => client.getDecisionRadar(1),
    json(decisionRadar({
      continuity_cards: [continuityDecisionCard({ related_target_key: "not-an-issue" })],
    })),
    "GET",
    "/api/projects/1/decision-radar",
    "$.continuity_cards[0]",
  );
  await expectInvalid(
    "Decision Radar rejects continuity cards carrying graph navigation",
    () => client.getDecisionRadar(1),
    json(decisionRadar({
      continuity_cards: [continuityDecisionCard({
        graph_focus_key: "scene:scene:1",
        graph_view_mode: "project_map",
      })],
    })),
    "GET",
    "/api/projects/1/decision-radar",
    "$.continuity_cards[0]",
  );
  await expectInvalid(
    "Decision Radar rejects invalid continuity scene destinations",
    () => client.getDecisionRadar(1),
    json(decisionRadar({
      continuity_cards: [continuityDecisionCard({
        evidence: [{
          ...(continuityDecisionCard().evidence as Array<Record<string, unknown>>)[0],
          related_target_type: "scene",
          related_target_id: 0,
          related_target_key: "",
        }],
      })],
    })),
    "GET",
    "/api/projects/1/decision-radar",
    "$.continuity_cards[0].evidence[0]",
  );
  await expectInvalid(
    "Decision Radar rejects continuity evidence carrying graph navigation",
    () => client.getDecisionRadar(1),
    json(decisionRadar({
      continuity_cards: [continuityDecisionCard({
        evidence: [{
          ...(continuityDecisionCard().evidence as Array<Record<string, unknown>>)[0],
          graph_focus_key: "scene:scene:1",
        }],
      })],
    })),
    "GET",
    "/api/projects/1/decision-radar",
    "$.continuity_cards[0]",
  );

  await expectValid(
    "Knowledge Graph defaults an omitted view mode to Project Map",
    () => client.getKnowledgeGraph(1),
    knowledgeGraph(),
    (value) => value.view_mode === "project_map" && value.story_diagnostics_available,
  );
  check(
    "default Knowledge Graph transport omits the defaulted view query",
    lastRequestUrl === "/api/projects/1/knowledge-graph",
  );
  await expectValid(
    "Knowledge Graph validates and echoes a requested Structure view",
    () => client.getKnowledgeGraph(1, { view_mode: "structure" }),
    knowledgeGraph({
      view_mode: "structure",
      story_diagnostics_available: false,
      hidden_edge_count: 3,
    }),
    (value) => value.view_mode === "structure" && !value.story_diagnostics_available,
  );
  check(
    "Knowledge Graph transport serializes the requested view mode",
    lastRequestUrl === "/api/projects/1/knowledge-graph?view_mode=structure",
  );
  await expectInvalid(
    "Knowledge Graph rejects an unknown response view mode",
    () => client.getKnowledgeGraph(1),
    json(knowledgeGraph({ view_mode: "future_mode" })),
    "GET",
    "/api/projects/1/knowledge-graph",
    "$.view_mode",
  );
  await expectInvalid(
    "Knowledge Graph rejects a response for a different requested view",
    () => client.getKnowledgeGraph(1, { view_mode: "recorded_risk" }),
    json(knowledgeGraph()),
    "GET",
    "/api/projects/1/knowledge-graph?view_mode=recorded_risk",
    "$.view_mode",
  );
  await expectInvalid(
    "Knowledge Graph requires the story-diagnostics availability signal",
    () => client.getKnowledgeGraph(1),
    json(knowledgeGraph({ story_diagnostics_available: undefined })),
    "GET",
    "/api/projects/1/knowledge-graph",
    "$.story_diagnostics_available",
  );
  await expectInvalid(
    "Knowledge Graph requires the Story Gravity availability signal",
    () => client.getKnowledgeGraph(1),
    json(knowledgeGraph({ story_gravity_available: undefined })),
    "GET",
    "/api/projects/1/knowledge-graph",
    "$.story_gravity_available",
  );
  const excessiveGravity = knowledgeGraph();
  excessiveGravity.nodes[1] = { ...excessiveGravity.nodes[1], story_gravity: 1.01 };
  await expectInvalid(
    "Knowledge Graph bounds per-node Story Gravity",
    () => client.getKnowledgeGraph(1),
    json(excessiveGravity),
    "GET",
    "/api/projects/1/knowledge-graph",
    "$.nodes[1].story_gravity",
  );
  const unavailableGravity = knowledgeGraph({ story_gravity_available: false });
  unavailableGravity.nodes = unavailableGravity.nodes.map((node) => ({ ...node, story_gravity: null }));
  unavailableGravity.nodes[1] = { ...unavailableGravity.nodes[1], story_gravity: 0.2 };
  await expectInvalid(
    "Knowledge Graph rejects mapped gravity when Core reports the enhancement unavailable",
    () => client.getKnowledgeGraph(1),
    json(unavailableGravity),
    "GET",
    "/api/projects/1/knowledge-graph",
    "$.nodes[1].story_gravity",
  );
  const invalidFlowBand = knowledgeGraph();
  invalidFlowBand.edges[0] = {
    ...invalidFlowBand.edges[0],
    edge_type: "precedes",
    metadata: {
      story_order_index: 0,
      story_order_total: 2,
      story_order_band: "epilogue",
      act_boundary: false,
    },
  };
  await expectInvalid(
    "Knowledge Graph strictly validates annotated story-order bands",
    () => client.getKnowledgeGraph(1),
    json(invalidFlowBand),
    "GET",
    "/api/projects/1/knowledge-graph",
    "$.edges[0].metadata.story_order_band",
  );
  const partialFlowMetadata = knowledgeGraph();
  partialFlowMetadata.edges[0] = {
    ...partialFlowMetadata.edges[0],
    edge_type: "precedes",
    metadata: { story_order_index: 0 },
  };
  await expectInvalid(
    "Knowledge Graph rejects partial story-order metadata",
    () => client.getKnowledgeGraph(1),
    json(partialFlowMetadata),
    "GET",
    "/api/projects/1/knowledge-graph",
    "$.edges[0].metadata",
  );
  const validFollowsFlow = knowledgeGraph();
  validFollowsFlow.edges[0] = {
    ...validFollowsFlow.edges[0],
    edge_type: "follows",
    metadata: {
      story_order_index: 1,
      story_order_total: 2,
      story_order_band: "ending",
      act_boundary: true,
    },
  };
  await expectValid(
    "Knowledge Graph accepts a complete follows segment whose source is the later Scene",
    () => client.getKnowledgeGraph(1),
    validFollowsFlow,
    (value) => value.edges[0]?.metadata.story_order_index === 1,
  );
  await expectInvalid(
    "specialty graph views cannot claim Project Map story diagnostics",
    () => client.getKnowledgeGraph(1, { view_mode: "revision_impact" }),
    json(knowledgeGraph({
      view_mode: "revision_impact",
      story_diagnostics_available: false,
      orphan_keys: ["scene:scene:2"],
      orphan_count: 1,
    })),
    "GET",
    "/api/projects/1/knowledge-graph?view_mode=revision_impact",
    "$.orphan_count",
  );

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
