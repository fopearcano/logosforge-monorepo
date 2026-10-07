import { WRITING_MODES } from "@logosforge/ui-contracts";
import type {
  WritingMode,
  NoteDTO,
  InlineCommentDTO,
  InlineCommentCreateDTO,
  InlineCommentUpdateDTO,
  CommentReplyCreateDTO,
  CharacterDTO,
  CharacterUpdateDTO,
  ProjectDTO,
  ProjectCreateDTO,
  ProjectUpdateDTO,
  ProjectSearchKind,
  ProjectSearchMatchDTO,
  WhiteboardImportDTO,
  WhiteboardImportResultDTO,
  ManuscriptImportDTO,
  ManuscriptImportResultDTO,
  WritingModesResponseDTO,
  SceneDTO,
  ManuscriptSnapshotDTO,
  StoryStructureDTO,
  StoryStructureCommandDTO,
  StoryStructureCommandResultDTO,
  StoryStructurePlacementDTO,
  OutlineNodeDTO,
  PsykeEntryDTO,
  PsykeRelationDTO,
  PsykeProgressionDTO,
  PsykeConsoleCommandPlanDTO,
  PsykeConsoleExecutionDTO,
  PsykeConsolePlanRequestDTO,
  TimelineEventDTO,
  TimelineLaneDTO,
  TimelineSnapshotDTO,
  TimelineCommandDTO,
  TimelineCommandResultDTO,
  CanvasPlotSnapshotDTO,
  CanvasPlotCommandDTO,
  CanvasPlotCommandResultDTO,
  KnowledgeGraphEdgeDTO,
  KnowledgeGraphNodeDTO,
  KnowledgeGraphQueryDTO,
  KnowledgeGraphReadDTO,
  KnowledgeGraphViewMode,
  KnowledgeGraphCommandDTO,
  KnowledgeGraphCommandResultDTO,
  KnowledgeGraphCommandReceiptDTO,
  ContinuityCommandDTO,
  ContinuityCommandResultDTO,
  ContinuityCommandReceiptDTO,
  ContinuityIssueDTO,
  ContinuityReportDTO,
  WorkflowCommandDTO,
  WorkflowCommandReceiptDTO,
  WorkflowCommandResultDTO,
  WorkflowEventDTO,
  WorkflowRecommendationDTO,
  WorkflowRunDTO,
  WorkflowTemplateDTO,
  PlotBlockDTO,
  PlotSceneDTO,
  ExportRequestDTO,
  ExportResponseDTO,
  VoiceHistoryEntryDTO,
  VoiceIntentPreviewDTO,
  VoiceBillyProposalDTO,
} from "@logosforge/ui-contracts";
import type { ApiClient } from "../src/adapters/api";
import { ApiRequestError } from "../src/adapters/httpApiClient";
import { trackProjectOperation } from "../src/adapters/projectSaveCoordinator";

const delay = (ms = 280) => new Promise<void>((r) => setTimeout(r, ms));

const KNOWLEDGE_GRAPH_VIEW_MODES = new Set<KnowledgeGraphViewMode>([
  "project_map",
  "structure",
  "recorded_risk",
  "revision_impact",
]);

// ── "Null Horizon" sample data — the same story the rest of the demo tells. ──

const PROJECTS: ProjectDTO[] = [
  { id: 1, title: "Null Horizon", description: "Screenplay · Feature", narrative_engine: "screenplay", default_writing_format: "screenplay", format_mode: "screenplay" },
  { id: 2, title: "Salt Flats", description: "Novel · Prose", narrative_engine: "novel", default_writing_format: "novel", format_mode: "novel" },
  { id: 3, title: "The Quiet Fleet", description: "Series · Teleplay", narrative_engine: "series", default_writing_format: "screenplay", format_mode: "screenplay" },
];

const MOCK_WRITING_MODES: WritingModesResponseDTO = {
  default_mode: "novel",
  modes: [
    {
      id: "novel",
      label: "Novel",
      structural_units: ["Acts", "Chapters", "Scenes"],
      default_writing_format: "novel",
      medium_constraints: "prose voice, interiority, chapter rhythm, character arc, thematic recurrence",
    },
    {
      id: "screenplay",
      label: "Screenplay",
      structural_units: ["Acts", "Sequences", "Scenes"],
      default_writing_format: "screenplay",
      medium_constraints: "visual action, scene economy, dialogue subtext, setup/payoff, cinematic pacing",
    },
    {
      id: "graphic_novel",
      label: "Graphic Novel",
      structural_units: ["Chapters", "Pages", "Panels"],
      default_writing_format: "graphic_novel",
      medium_constraints: "page turns, panel rhythm, visual motif, image/text balance, dialogue compression",
    },
    {
      id: "stage_script",
      label: "Stage Script",
      structural_units: ["Acts", "Scenes", "Beats", "Stage Directions"],
      default_writing_format: "stage_script",
      medium_constraints: "playable conflict, blocking, entrances/exits, performable dialogue, scene economy",
    },
    {
      id: "series",
      label: "Series",
      structural_units: ["Seasons", "Episodes", "A/B/C Plots", "Scenes"],
      default_writing_format: "screenplay",
      medium_constraints: "episode engine, A/B/C plots, season arc, recurring payoff, long-term continuity",
    },
  ],
};

const MOCK_DEFAULT_FORMAT: Record<WritingMode, string> = Object.fromEntries(
  MOCK_WRITING_MODES.modes.map((mode) => [mode.id, mode.default_writing_format]),
) as Record<WritingMode, string>;

function mockWritingMode(value: string | undefined, method: string, path: string): WritingMode {
  const candidate = value?.trim() || "novel";
  if ((WRITING_MODES as readonly string[]).includes(candidate)) return candidate as WritingMode;
  throw new ApiRequestError(method, path, 400, `Unknown writing mode: ${candidate}`, "bad_request");
}

function cloneProject(project: ProjectDTO): ProjectDTO {
  return { ...project };
}

function findMockProject(projects: ProjectDTO[], id: number, method: string, path = `/api/projects/${id}`): ProjectDTO {
  const project = projects.find((candidate) => candidate.id === id);
  if (!project) throw new ApiRequestError(method, path, 404, `Project ${id} not found`, "not_found");
  return project;
}

function createMockProject(projects: ProjectDTO[], body: ProjectCreateDTO): ProjectDTO {
  const mode = mockWritingMode(body.narrative_engine, "POST", "/api/projects");
  const format = body.default_writing_format?.trim() || MOCK_DEFAULT_FORMAT[mode];
  const project: ProjectDTO = {
    id: projects.reduce((maximum, candidate) => Math.max(maximum, candidate.id), 0) + 1,
    title: body.title,
    description: body.description ?? "",
    narrative_engine: mode,
    default_writing_format: format,
    format_mode: format,
  };
  projects.push(project);
  return cloneProject(project);
}

const MOCK_PERSISTENT_METHODS = new Set([
  "backfillCharacterLinks",
  "generateOutline",
  "assistantAction",
  "connectorExecute",
  "voiceTranscribeSegment",
  "voiceIntentPreview",
  "voiceIntentApply",
  "voiceIntentCancel",
  "voiceBillyGenerate",
  "voiceBillyApply",
  "voiceBillyCancel",
  "voiceCommit",
  "voiceUndo",
  "cancelExtractJob",
  "executeStoryStructureCommand",
  "executeTimelineCommand",
  "executeCanvasPlotCommand",
  "executeKnowledgeGraphCommand",
  "executeContinuityCommand",
]);

function mockMethodPersists(name: string): boolean {
  return /^(create|update|delete|patch|set|add|link|unlink|import|apply|revert|sync|place)/.test(name)
    || MOCK_PERSISTENT_METHODS.has(name);
}

/** Mirror the live HTTP client's handoff visibility for mock mutations. */
function trackMockApiOperations(client: ApiClient): ApiClient {
  return new Proxy(client, {
    get(target, property, receiver) {
      const value = Reflect.get(target, property, receiver);
      if (typeof property !== "string" || typeof value !== "function") return value;
      if (property === "executePsykeConsoleCommand") {
        return (...args: unknown[]) => trackProjectOperation(
          Promise.resolve(value.apply(target, args)),
          { persistence: args[2] === true },
        );
      }
      if (!mockMethodPersists(property)) return value.bind(target);
      return (...args: unknown[]) => trackProjectOperation(
        Promise.resolve(value.apply(target, args)),
        { persistence: true },
      );
    },
  });
}

let MOCK_SCENE_REVISION = 0;
const scene = (s: Partial<SceneDTO>): SceneDTO => ({
  id: 0, title: "", summary: "", synopsis: "", goal: "", conflict: "", outcome: "", beat: "", act: "",
  chapter: "", plotline: "", color_label: "", tags: [], content: "", sort_order: 0, order_index: 0,
  character_ids: [], place_ids: [], who_knows_what: "", revision: `mock-scene-${++MOCK_SCENE_REVISION}`, ...s,
});

const SCENE_FIXTURES: SceneDTO[] = [
  scene({ id: 1, title: "Cold Open", summary: "Marlow wakes the station. The planet is already wrong.", act: "ACT I", chapter: "1.1", beat: "Opening Image", content: "The corridor breathes...", sort_order: 1, tags: ["dawn"] }),
  scene({ id: 2, title: "Distress Loop", summary: "A 9-year-old signal repeats. Vesper recognizes the voice.", act: "ACT I", chapter: "1.2", beat: "Catalyst", content: "A hatch cycles.", sort_order: 2, tags: ["setup"] }),
  scene({ id: 3, title: "The Black Box", summary: "A sealed unit is logged, then never opened.", act: "ACT I", chapter: "1.3", beat: "Debate", sort_order: 3, tags: ["setup"] }),
  scene({ id: 12, title: "Observation Ring", summary: "Marlow and Vesper, the static, the Warden's count.", act: "ACT II", chapter: "2.4", beat: "Midpoint", content: "INT. HELIOS-9 — NIGHT...", sort_order: 12, tags: ["dialogue"] }),
  scene({ id: 14, title: "The Confession", summary: "Three exposition scenes in a row — tension flattens.", act: "ACT II", chapter: "2.5", beat: "Bad Guys Close In", sort_order: 14 }),
  scene({ id: 21, title: "All Is Lost", summary: "The reactor goes quiet. So does Vesper.", act: "ACT II", chapter: "2.7", beat: "All Is Lost", sort_order: 21, tags: ["climax"] }),
  scene({ id: 22, title: "Break Into Three", summary: "Marlow opens the box.", act: "ACT III", chapter: "3.1", beat: "Break Into Three", sort_order: 22 }),
];

function cloneScene(value: SceneDTO): SceneDTO {
  return {
    ...value,
    tags: [...value.tags],
    character_ids: [...value.character_ids],
    place_ids: [...value.place_ids],
  };
}

const node = (id: number, parent_id: number | null, title: string, description: string, sort_order: number, children: OutlineNodeDTO[] = []): OutlineNodeDTO =>
  ({ id, parent_id, title, description, sort_order, scene_id: null, children });

const OUTLINE: OutlineNodeDTO[] = [
  node(1, null, "ACT I", "Arrival on a dead station.", 0, [
    node(2, 1, "Chapter 1.1 · Arrival", "", 0, [
      node(3, 2, "Cold Open", "Marlow wakes the station. The planet is already wrong.", 0),
      node(4, 2, "Boot Sequence", "Systems come up one by one.", 1),
    ]),
    node(5, 1, "Chapter 1.2 · The Signal", "", 1, [
      node(6, 5, "Distress Loop", "A 9-year-old signal repeats.", 0),
    ]),
  ]),
  node(7, null, "ACT II", "The Warden tightens its grip.", 1, [
    node(8, 7, "Chapter 2.4 · Convergence", "", 0, [
      node(9, 8, "Observation Ring", "Marlow + Vesper. The static. The count.", 0),
    ]),
  ]),
  node(10, null, "ACT III", "Open the box.", 2, []),
];

// async-extraction mock jobs — getExtractJob ticks progress per poll for a visible bar
const MOCK_EXTRACT_JOBS: Record<string, { done: number; total: number; result: unknown }> = {};
let MOCK_EXTRACT_SEQ = 0;

// format-data authoring mock store (create-append + list)
let MOCK_FD_SEQ = 100;
const MOCK_GN_PAGES: Record<string, unknown>[] = [{ id: 1, page_number: 1, summary: "The vault at night", reveal_type: "", splash_page: false }];
const MOCK_GN_PANELS: Record<string, unknown>[] = [{ id: 2, page_id: 1, panel_number: 1, description: "Mara enters the dark", visual_motifs: ["silence"] }];
const MOCK_STAGE_CUES: Record<string, unknown>[] = [];
const MOCK_STAGE_ENTR: Record<string, unknown>[] = [];
const MOCK_STAGE_BIZ: Record<string, unknown>[] = [];
const MOCK_SEASONS: Record<string, unknown>[] = [{ id: 1, season_number: 1, title: "Descent" }];
const MOCK_EPISODES: Record<string, unknown>[] = [];
const MOCK_ARCS: Record<string, unknown>[] = [];
const MOCK_PLOTLINES: Record<string, unknown>[] = [];
const MOCK_SERIES_MEM: Record<number, { entry_id: number; continuity_flags: string; current_status_by_episode: Record<string, string> }> = {};
const MOCK_CONTINUITY: Record<number, Record<string, unknown>[]> = {};
const MOCK_GN_ITEMS: Record<string, unknown>[] = [];
const MOCK_GN_APPEAR: Record<string, unknown>[] = [];

const PSYKE: PsykeEntryDTO[] = [
  { id: 1, name: "MARLOW", type: "character", aliases: [], notes: "Ex-flight engineer. Carries the Kessler burn.", is_global: false, details: { role: "Protagonist" } },
  { id: 2, name: "VESPER", type: "character", aliases: ["Vess", "the Confidant"], notes: "Speaks in understatement; deflects with logistics.", is_global: true, details: { role: "Deuteragonist", want: "To be forgiven for the relay order she signed.", need: "To forgive herself.", lie: "Silence keeps people safe.", wound: "She stranded the Kessler crew." } },
  { id: 3, name: "THE WARDEN", type: "character", aliases: [], notes: "The thing they no longer call a person.", is_global: false, details: { role: "Antagonist" } },
  { id: 4, name: "HELIOS-9", type: "place", aliases: [], notes: "The station.", is_global: true, details: {} },
  { id: 5, name: "THE BLACK BOX", type: "object", aliases: [], notes: "Sealed unit, never opened.", is_global: false, details: {} },
  { id: 6, name: "STATIC", type: "theme", aliases: [], notes: "Grief motif.", is_global: false, details: {} },
];

const RELATIONS: PsykeRelationDTO[] = [
  { id: "1:2", source_id: 1, target_id: 2, source: "MARLOW", target: "VESPER", relation_type: "confides" },
  { id: "2:3", source_id: 2, target_id: 3, source: "VESPER", target: "THE WARDEN", relation_type: "deceives" },
];

const PROGRESSIONS: PsykeProgressionDTO[] = [
  { id: 1, entry_id: 2, text: "Recognizes the looping voice.", scene_id: 2, scene_title: "Distress Loop", sort_order: 0 },
  { id: 2, entry_id: 2, text: "Confesses, but only half of it.", scene_id: 12, scene_title: "Observation Ring", sort_order: 1 },
  { id: 3, entry_id: 2, text: "Goes silent. Pays off the motif.", scene_id: 21, scene_title: "All Is Lost", sort_order: 2 },
];

const tEvent = (e: Partial<TimelineEventDTO>): TimelineEventDTO => ({
  id: 0, order_index: 0, title: "", structural_number: "", act: "", chapter: "",
  plotline: "", color_label: "", lane_id: null, time_of_day: "", location: "",
  duration_minutes: 0, character_states: [], ...e,
});

const TIMELINE_LANES: TimelineLaneDTO[] = [
  { id: 1, name: "MAIN · Marlow", color_label: "cyan", order_index: 0, collapsed: false, event_count: 3 },
  { id: 2, name: "SUBPLOT · Vesper", color_label: "green", order_index: 1, collapsed: false, event_count: 2 },
  { id: 3, name: "THREAT · Warden", color_label: "crimson", order_index: 2, collapsed: false, event_count: 1 },
];

const TIMELINE: TimelineEventDTO[] = [
  tEvent({ id: 1, order_index: 1, title: "Cold Open", structural_number: "1.1", act: "ACT I", chapter: "1.1", plotline: "MAIN · Marlow", lane_id: 1, time_of_day: "DAWN", location: "Helios-9 · corridor", duration_minutes: 3, character_states: [{ character: "MARLOW", state: "alone, waking" }] }),
  tEvent({ id: 2, order_index: 2, title: "Distress Loop", structural_number: "1.2", act: "ACT I", chapter: "1.2", plotline: "SUBPLOT · Vesper", lane_id: 2, time_of_day: "DAY", location: "Comms", duration_minutes: 5, character_states: [{ character: "VESPER", state: "recognizes the voice" }] }),
  tEvent({ id: 12, order_index: 3, title: "Observation Ring", structural_number: "2.1", act: "ACT II", chapter: "2.4", plotline: "MAIN · Marlow", lane_id: 1, time_of_day: "NIGHT", location: "Observation deck", duration_minutes: 8, character_states: [{ character: "MARLOW", state: "pressing" }, { character: "VESPER", state: "deflecting" }] }),
  tEvent({ id: 14, order_index: 4, title: "The Confession", structural_number: "2.2", act: "ACT II", chapter: "2.5", plotline: "SUBPLOT · Vesper", lane_id: 2, character_states: [{ character: "VESPER", state: "half-truth" }] }),
  tEvent({ id: 21, order_index: 5, title: "All Is Lost", structural_number: "2.3", act: "ACT II", chapter: "2.7", plotline: "THREAT · Warden", lane_id: 3, time_of_day: "NIGHT", location: "Reactor", character_states: [{ character: "VESPER", state: "goes silent" }, { character: "THE WARDEN", state: "counts" }] }),
  tEvent({ id: 22, order_index: 6, title: "Break Into Three", structural_number: "3.1", act: "ACT III", chapter: "3.1", plotline: "MAIN · Marlow", lane_id: 1, character_states: [{ character: "MARLOW", state: "opens the box" }] }),
];

const pScene = (s: Partial<PlotSceneDTO>): PlotSceneDTO => ({ scene_id: null, title: "", act: "", summary: "", beat: "", color_label: "", order_index: 0, ...s });

const PLOT: PlotBlockDTO[] = [
  { id: "main", plotline: "MAIN · Marlow", scenes: [
    pScene({ scene_id: 1, title: "Cold Open", act: "ACT I", beat: "Opening Image", summary: "Marlow wakes the station.", order_index: 1, color_label: "#4cc2ff" }),
    pScene({ scene_id: 12, title: "Observation Ring", act: "ACT II", beat: "Midpoint", summary: "Marlow + Vesper. The static.", order_index: 5, color_label: "#4cc2ff" }),
    pScene({ scene_id: 22, title: "Break Into Three", act: "ACT III", beat: "Break Into Three", summary: "Marlow opens the box.", order_index: 10, color_label: "#4cc2ff" }),
  ] },
  { id: "vesper", plotline: "SUBPLOT · Vesper", scenes: [
    pScene({ scene_id: 2, title: "Distress Loop", act: "ACT I", beat: "Catalyst", summary: "Vesper knows the voice.", order_index: 2, color_label: "#62d99a" }),
    pScene({ scene_id: 21, title: "All Is Lost", act: "ACT II", beat: "All Is Lost", summary: "So does Vesper.", order_index: 9, color_label: "#62d99a" }),
  ] },
  { id: "warden", plotline: "THREAT · Warden", scenes: [
    pScene({ scene_id: 99, title: "The Count", act: "ACT II", beat: "Bad Guys Close In", summary: "The Warden counts down.", order_index: 7, color_label: "#e8443a" }),
  ] },
];

const DEFAULT_SETTINGS: Record<string, unknown> = {
  focus_mode: false,
  typewriter_mode: false,
  writing_language_code: "en",
  current_language: "en",
  chat_opacity: 92,
  chat_bg_color: "#3a2a55",
  chat_text_color: "#ffb000",
};

let AI_BEHAVIOR = {
  ctx_outline: true,
  ctx_bible: true,
  ctx_memory: true,
  connector_enabled: false,
  connector_allow_writes: false,
  connector_confirm_writes: true,
  connector_disabled_actions: [] as string[],
  adaptive_override: "",
};

const NOTES: NoteDTO[] = [
  { id: 1, title: "The Warden Rules", content: "No one says its name. It speaks only in counts. Never show its face before Act III.", tags: [], pinned: true, psyke_links: [3], scene_links: [21] },
  { id: 2, title: "Static = grief motif", content: "The interference grows louder near loss. Pay it off when Vesper goes quiet.", tags: ["theme"], pinned: false, psyke_links: [], scene_links: [] },
  { id: 3, title: "Kessler burn — backstory", content: "What Marlow did at the relay. Drip it; never a full flashback.", tags: ["backstory"], pinned: false, psyke_links: [1, 4], scene_links: [] },
  { id: 4, title: "Open the box?", content: "Decide before draft 2: does the black box pay off as device or as choice?", tags: [], pinned: false, psyke_links: [5], scene_links: [4] },
  { id: 5, title: "Cold-open candidates", content: "Either the distress loop or the dead-planet drift. Lean drift — quieter, lonelier.", tags: ["structure"], pinned: false, psyke_links: [], scene_links: [1] },
];

let MOCK_COMMENT_REVISION_SEQ = 3;
const nextMockCommentRevision = (): string =>
  (MOCK_COMMENT_REVISION_SEQ++).toString(16).padStart(64, "0");

const COMMENTS: InlineCommentDTO[] = [
  {
    id: 1,
    source_id: "wb-comment-open",
    anchor: {
      start_scene_id: 12,
      start_field: "content",
      from_offset: 5,
      end_scene_id: 12,
      end_field: "content",
      to_offset: 13,
      prefix: "INT. ",
      suffix: " — NIGHT...",
    },
    quote: "HELIOS-9",
    body: "Make the station feel less safe before Vesper answers.",
    resolved: false,
    replies: [
      {
        id: 1,
        source_id: "wb-reply-1",
        body: "The failing lights can carry that warning.",
        author: "Billy",
        sort_order: 0,
        created_at: "2026-03-11T10:08:00Z",
      },
    ],
    created_at: "2026-03-11T10:00:00Z",
    updated_at: "2026-03-11T10:08:00Z",
    revision: "1".padStart(64, "0"),
  },
  {
    id: 2,
    source_id: "wb-comment-resolved",
    anchor: {
      start_scene_id: 2,
      start_field: "title",
      from_offset: 0,
      end_scene_id: 2,
      end_field: "title",
      to_offset: 13,
      prefix: "",
      suffix: "",
    },
    quote: "Distress Loop",
    body: "Keep this scene title; it pays off the repeated signal.",
    resolved: true,
    replies: [],
    created_at: "2026-03-10T14:00:00Z",
    updated_at: "2026-03-12T09:30:00Z",
    revision: "2".padStart(64, "0"),
  },
];

/**
 * Minimal mock of the logosforge core ApiClient for the preview. Returns the
 * sample data for the wired domains; the brief delay makes loading states visible.
 */
const MOCK_CHARACTERS: CharacterDTO[] = [
  { id: 1, name: "MARLOW", description: "", color: "#4cc2ff", psyke_entry_id: null },
  { id: 2, name: "VESPER", description: "", color: "#f5b133", psyke_entry_id: null },
];

// In-session scene-tags per theme entry id (mock seeds the STATIC theme, id 6).
const MOCK_THEME_SCENES: Record<number, number[]> = { 6: [1, 3] };

const MOCK_VOICE_HISTORY: VoiceHistoryEntryDTO[] = [{
  id: "voice-1", session_id: "preview-session", project_id_at_capture: 1,
  writing_mode_at_capture: "screenplay", text: "Open on the dead station.",
  original_text: "Open on the dead station.", preview: "Open on the dead station.",
  created_at: Date.now() / 1000, updated_at: Date.now() / 1000,
  language: "en", source: "preview", is_final: true, status: "pending",
  committed_target: "", committed_at: null, duration_ms: 1800,
  confidence: 0.96, error: "", merged_from: [], split_from: "",
  corrections: [], sent_to_billy: false, billy_proposal_id: "",
  billy_state: "", has_audio: false, sample_rate: 16000,
}];
const MOCK_VOICE_INTENTS = new Map<string, VoiceIntentPreviewDTO>();
const MOCK_VOICE_BILLY = new Map<string, VoiceBillyProposalDTO>();
let MOCK_VOICE_SEQ = 1;

const MOCK_WORKFLOW_TEMPLATES: readonly WorkflowTemplateDTO[] = [{
  id: "project_setup",
  title: "Project Setup",
  description: "Get a new project ready: title, logline, mode, and first structure.",
  category: "setup",
  modes: [],
  steps: [
    { id: "title", title: "Set a project title", description: "Name the project.", kind: "check", section_name: "Projects", action_id: "", completion_check: "project_has_title", modes: [] },
    { id: "logline", title: "Write the logline", description: "Capture the central dramatic promise.", kind: "creative", section_name: "Manuscript", action_id: "", completion_check: "", modes: [] },
  ],
}, {
  id: "rewrite",
  title: "Rewrite",
  description: "Generate, compare, and safely apply a rewrite.",
  category: "rewrite",
  modes: [],
  steps: [
    { id: "select", title: "Select the passage", description: "Choose the material to revise.", kind: "manual", section_name: "Manuscript", action_id: "", completion_check: "", modes: [] },
    { id: "strategy", title: "Choose a rewrite strategy", description: "Ask Logos for a bounded suggestion.", kind: "manual", section_name: "Manuscript", action_id: "rw_suggest_strategy", completion_check: "", modes: [] },
    { id: "apply", title: "Apply through Controlled Apply", description: "Review the diff and impact before applying.", kind: "check", section_name: "Manuscript", action_id: "", completion_check: "no_preferred_rewrite", modes: [] },
  ],
}, {
  id: "screenplay_production_prep",
  title: "Screenplay Production Prep",
  description: "Prepare a screenplay production draft.",
  category: "production",
  modes: ["screenplay"],
  steps: [
    { id: "validate", title: "Validate production export", description: "Check the production package.", kind: "check", section_name: "Export", action_id: "sp_validate_production", completion_check: "export_safe", modes: ["screenplay"] },
  ],
}];

export function createMockApiClient(): ApiClient {
  // Keep project lifecycle state local to one preview transport. Recreating the
  // client (for example, when switching mock/live source) starts from the same
  // deterministic fixtures instead of inheriting mutations from an old client.
  const projects = PROJECTS.map(cloneProject);
  const settingsByProject = new Map<number, Record<string, unknown>>(
    projects.map((project) => [project.id, structuredClone(DEFAULT_SETTINGS)]),
  );
  const settingsFor = (projectId: number): Record<string, unknown> => {
    let settings = settingsByProject.get(projectId);
    if (!settings) {
      settings = structuredClone(DEFAULT_SETTINGS);
      settingsByProject.set(projectId, settings);
    }
    return settings;
  };
  const scenesByProject = new Map<number, SceneDTO[]>(
    projects.map((project) => [
      project.id,
      project.id === 1 ? SCENE_FIXTURES.map(cloneScene) : [],
    ]),
  );
  const fixtureTimelineById = new Map(TIMELINE.map((event) => [event.id, event]));
  for (const sceneRow of scenesByProject.get(PROJECTS[0]!.id) ?? []) {
    const event = fixtureTimelineById.get(sceneRow.id);
    if (!event) continue;
    sceneRow.plotline = event.plotline;
    sceneRow.color_label = event.color_label;
  }
  const episodesByProject = new Map<number, Map<number, number | null>>(
    [...scenesByProject.entries()].map(([projectId, projectScenes]) => [
      projectId,
      new Map(projectScenes.map((sceneRow) => [sceneRow.id, null])),
    ]),
  );
  const fixtureProjectId = projects[0]!.id;
  const scenesFor = (projectId: number): SceneDTO[] => {
    let values = scenesByProject.get(projectId);
    if (!values) {
      values = [];
      scenesByProject.set(projectId, values);
    }
    return values;
  };
  const episodesFor = (projectId: number): Map<number, number | null> => {
    let values = episodesByProject.get(projectId);
    if (!values) {
      values = new Map();
      episodesByProject.set(projectId, values);
    }
    return values;
  };
  const episodeFor = (projectId: number, sceneId: number): number | null =>
    episodesFor(projectId).get(sceneId) ?? null;
  interface MockTimelineDetails {
    time_of_day: string;
    location: string;
    slugline: string;
    estimated_duration_minutes: number;
    performance_duration_minutes: number;
    character_states: TimelineEventDTO["character_states"];
  }
  interface MockTimelineState {
    lanes: TimelineLaneDTO[];
    explicitEventIds: Set<number>;
    customOrder: number[];
    orderMode: "structural" | "custom";
    details: Map<number, MockTimelineDetails>;
  }
  const emptyTimelineState = (): MockTimelineState => ({
    lanes: [],
    explicitEventIds: new Set(),
    customOrder: [],
    orderMode: "structural",
    details: new Map(),
  });
  const timelineStates = new Map<number, MockTimelineState>(projects.map((project) => [
    project.id,
    project.id === PROJECTS[0]!.id
      ? {
          lanes: TIMELINE_LANES.map((lane) => ({ ...lane })),
          explicitEventIds: new Set<number>(),
          customOrder: TIMELINE.map((event) => event.id),
          orderMode: "structural" as const,
          details: new Map(TIMELINE.map((event) => [event.id, {
            time_of_day: event.time_of_day,
            location: event.location,
            slugline: "",
            estimated_duration_minutes: event.duration_minutes,
            performance_duration_minutes: 0,
            character_states: event.character_states.map((state) => ({ ...state })),
          }])),
        }
      : emptyTimelineState(),
  ]));
  const timelineStateFor = (projectId: number): MockTimelineState => {
    let state = timelineStates.get(projectId);
    if (!state) {
      state = emptyTimelineState();
      timelineStates.set(projectId, state);
    }
    return state;
  };
  const scrubTimelineScene = (projectId: number, sceneId: number): void => {
    const state = timelineStateFor(projectId);
    state.explicitEventIds.delete(sceneId);
    state.customOrder = state.customOrder.filter((id) => id !== sceneId);
    state.details.delete(sceneId);
  };
  const canvasSeed = (projectId: number): CanvasPlotSnapshotDTO => {
    const created_at = "2026-01-01T00:00:00Z";
    const nodes = projectId === fixtureProjectId ? [
      { id: 1, title: "Inciting signal", body: "A message arrives before it is sent.", x: -260, y: -90, width: 220, height: 132, color_label: "cyan", group_label: "ACT I", scene_id: 1, sort_order: 0, created_at },
      { id: 2, title: "Impossible choice", body: "Vesper must decide which timeline survives.", x: 60, y: 30, width: 230, height: 140, color_label: "violet", group_label: "ACT II", scene_id: 12, sort_order: 1, created_at },
      { id: 3, title: "The return", body: "The station remembers a different ending.", x: 390, y: -120, width: 220, height: 132, color_label: "amber", group_label: "ACT III", scene_id: 21, sort_order: 2, created_at },
    ] : [];
    const links = projectId === fixtureProjectId ? [
      { id: 1, source_node_id: 1, target_node_id: 2, label: "forces", color_label: "cyan", link_type: "causality", created_at },
      { id: 2, source_node_id: 2, target_node_id: 3, label: "echoes", color_label: "violet", link_type: "echo", created_at },
    ] : [];
    const frames = projectId === fixtureProjectId ? [
      { id: 1, title: "CORE CAUSAL CHAIN", color_label: "blue", x: -310, y: -170, width: 980, height: 390, created_at },
    ] : [];
    return { project_id: projectId, revision: "0".repeat(64), nodes, links, frames };
  };
  const canvasStates = new Map<number, CanvasPlotSnapshotDTO>(
    projects.map((project) => [project.id, canvasSeed(project.id)]),
  );
  interface MockCanvasIds {
    nextNodeId: number;
    nextLinkId: number;
    nextFrameId: number;
  }
  const canvasIdsFrom = (snapshot: CanvasPlotSnapshotDTO): MockCanvasIds => ({
    nextNodeId: snapshot.nodes.reduce((maximum, node) => Math.max(maximum, node.id), 0) + 1,
    nextLinkId: snapshot.links.reduce((maximum, link) => Math.max(maximum, link.id), 0) + 1,
    nextFrameId: snapshot.frames.reduce((maximum, frame) => Math.max(maximum, frame.id), 0) + 1,
  });
  const canvasIds = new Map<number, MockCanvasIds>(
    [...canvasStates.entries()].map(([projectId, snapshot]) => [projectId, canvasIdsFrom(snapshot)]),
  );
  const canvasIdsFor = (projectId: number): MockCanvasIds => {
    let ids = canvasIds.get(projectId);
    if (!ids) {
      ids = canvasIdsFrom(canvasFor(projectId));
      canvasIds.set(projectId, ids);
    }
    return ids;
  };
  const canvasRevision = (snapshot: Omit<CanvasPlotSnapshotDTO, "revision">): string => {
    let hash = 0x811c9dc5;
    for (const char of JSON.stringify(snapshot)) {
      hash ^= char.charCodeAt(0);
      hash = Math.imul(hash, 0x01000193) >>> 0;
    }
    return hash.toString(16).padStart(8, "0").repeat(8);
  };
  const canvasFor = (projectId: number): CanvasPlotSnapshotDTO => {
    let snapshot = canvasStates.get(projectId);
    if (!snapshot) {
      snapshot = canvasSeed(projectId);
      canvasStates.set(projectId, snapshot);
    }
    const revision = canvasRevision({
      project_id: snapshot.project_id,
      nodes: snapshot.nodes,
      links: snapshot.links,
      frames: snapshot.frames,
    });
    if (snapshot.revision !== revision) snapshot = { ...snapshot, revision };
    canvasStates.set(projectId, snapshot);
    return snapshot;
  };
  const structureRevisionFor = (projectId: number): string => {
    const payload = {
      project_id: projectId,
      narrative_engine: projects.find((project) => project.id === projectId)?.narrative_engine ?? "novel",
      scenes: [...scenesFor(projectId)]
        .sort((left, right) => left.sort_order - right.sort_order || left.id - right.id)
        .map((sceneRow) => [
          sceneRow.id,
          sceneRow.act.trim(),
          sceneRow.chapter.trim(),
          episodeFor(projectId, sceneRow.id),
          sceneRow.sort_order,
        ]),
    };
    let hash = 0x811c9dc5;
    for (const char of JSON.stringify(payload)) {
      hash ^= char.charCodeAt(0);
      hash = Math.imul(hash, 0x01000193) >>> 0;
    }
    return hash.toString(16).padStart(8, "0").repeat(8);
  };
  const storyStructureFor = (projectId: number): StoryStructureDTO => {
    const narrativeEngine = projects.find((project) => project.id === projectId)?.narrative_engine;
    const chapterLevel = narrativeEngine === "novel";
    const requiresChapterParents = chapterLevel || narrativeEngine === "series";
    const ordered = [...scenesFor(projectId)].sort((left, right) => left.sort_order - right.sort_order || left.id - right.id);
    const grouped = new Map<string, Map<string, SceneDTO[]>>();
    for (const sceneRow of ordered) {
      const actName = sceneRow.act.trim() || "Unassigned";
      const chapterName = sceneRow.chapter.trim() || "Unassigned";
      const chapters = grouped.get(actName) ?? new Map<string, SceneDTO[]>();
      const scenes = chapters.get(chapterName) ?? [];
      scenes.push(sceneRow);
      chapters.set(chapterName, scenes);
      grouped.set(actName, chapters);
    }
    const orderedEntries = <T,>(entries: Array<[string, T]>): Array<[string, T]> => [
      ...entries.filter(([name]) => name !== "Unassigned"),
      ...entries.filter(([name]) => name === "Unassigned"),
    ];
    let orderIndex = 0;
    let orphanCount = 0;
    let actNumber = 0;
    const acts = orderedEntries([...grouped.entries()]).map(([actName, chapterMap]) => {
      const unassigned = actName === "Unassigned";
      const number = unassigned ? "" : String(++actNumber);
      let chapterNumber = 0;
      let flatSceneNumber = 0;
      const chapters = orderedEntries([...chapterMap.entries()]).map(([chapterName, sceneRows]) => {
        const chapterUnassigned = chapterName === "Unassigned";
        const chapterRef = chapterUnassigned ? "" : `${number}.${++chapterNumber}`;
        const scenes = sceneRows.map((sceneRow, sceneIndex) => {
          orderIndex += 1;
          const isOrphan = !sceneRow.act.trim() || (requiresChapterParents && !sceneRow.chapter.trim());
          if (isOrphan) orphanCount += 1;
          flatSceneNumber += 1;
          return {
            id: sceneRow.id,
            title: sceneRow.title,
            beat: sceneRow.beat,
            episode_id: episodeFor(projectId, sceneRow.id),
            number: unassigned
              ? ""
              : chapterLevel && !chapterUnassigned
                ? `${chapterRef}.${sceneIndex + 1}`
                : `${number}.${chapterLevel ? sceneIndex + 1 : flatSceneNumber}`,
            order_index: orderIndex,
            is_orphan: isOrphan,
          };
        });
        return {
          name: chapterName,
          number: chapterRef,
          unassigned: chapterUnassigned,
          scene_count: scenes.length,
          scenes,
        };
      });
      return {
        name: actName,
        number,
        unassigned,
        scene_count: chapters.reduce((count, chapter) => count + chapter.scene_count, 0),
        chapters,
      };
    });
    return {
      project_id: projectId,
      revision: structureRevisionFor(projectId),
      chapter_level: chapterLevel,
      scene_count: orderIndex,
      orphan_count: orphanCount,
      acts,
    };
  };
  const manuscriptSnapshotFor = (projectId: number): ManuscriptSnapshotDTO => {
    const structure = storyStructureFor(projectId);
    const byId = new Map(scenesFor(projectId).map((sceneRow) => [sceneRow.id, sceneRow]));
    const scenes = structure.acts.flatMap((act) => act.chapters.flatMap((chapter) => (
      chapter.scenes.map((reference) => ({
        ...cloneScene(byId.get(reference.id)!),
        order_index: reference.order_index,
      }))
    )));
    return {
      project_id: projectId,
      chapter_level: structure.chapter_level,
      scene_count: structure.scene_count,
      orphan_count: structure.orphan_count,
      scenes,
    };
  };
  const executeStructureCommand = (
    projectId: number,
    command: StoryStructureCommandDTO,
  ): StoryStructureCommandResultDTO => {
    const path = `/api/projects/${projectId}/story-structure/commands`;
    const project = findMockProject(projects, projectId, "POST", path);
    const isSeries = project.narrative_engine === "series";
    const requiresChapterParents = project.narrative_engine === "novel" || isSeries;
    const current = storyStructureFor(projectId);
    if (command.expected_revision !== current.revision) {
      throw new ApiRequestError(
        "POST",
        path,
        409,
        "The story structure changed after it was loaded.",
        "structure_conflict",
      );
    }

    const reject = (detail: string, code = "bad_request", status = 400): never => {
      throw new ApiRequestError("POST", path, status, detail, code);
    };
    const label = (value: string, field: string): string => {
      const normalized = value.trim();
      if (!normalized || normalized.toLocaleLowerCase() === "unassigned") {
        return reject(`${field} must be a named structure label.`);
      }
      return normalized;
    };
    const chapterLabel = (value: string, field: string): string => {
      const normalized = value.trim();
      if (!normalized && !requiresChapterParents) return "";
      return label(normalized, field);
    };
    const insertionIndex = (value: number, maximum: number, field = "index"): number => {
      if (!Number.isSafeInteger(value) || value < 0 || value > maximum) {
        return reject(`${field} must be between 0 and ${maximum}.`);
      }
      return value;
    };
    const episodeId = (value: number | null | undefined): number | null => {
      if (value == null) return null;
      if (!Number.isSafeInteger(value) || value <= 0) {
        return reject("episode_id must be a positive integer or null.");
      }
      if (!isSeries) {
        return reject("episode_id is only valid for Series projects.");
      }
      const ownedEpisode = MOCK_EPISODES.some((episode) => (
        episode.id === value && episode.project_id === projectId
      ));
      if (!ownedEpisode) {
        return reject(`Episode ${value} does not belong to this project.`, "not_found", 404);
      }
      return value;
    };

    const rawOrdered = [...scenesFor(projectId)]
      .sort((left, right) => left.sort_order - right.sort_order || left.id - right.id);
    const rawById = new Map(rawOrdered.map((sceneRow) => [sceneRow.id, sceneRow]));
    const canonical = isSeries
      ? rawOrdered.map(cloneScene)
      : current.acts.flatMap((actRow) => actRow.chapters.flatMap((chapterRow) => (
          chapterRow.scenes.map((reference) => cloneScene(rawById.get(reference.id)!))
        )));
    const candidateEpisodes = new Map(episodesFor(projectId));
    const inEpisodeScope = (sceneRow: SceneDTO, episode: number | null): boolean => (
      !isSeries || (candidateEpisodes.get(sceneRow.id) ?? null) === episode
    );
    const distinctLabels = (values: string[]): string[] => [...new Set(values.filter(Boolean))];
    let changed = false;
    let createdSceneId: number | null = null;
    let affectedSceneIds: number[] = [];

    const createSeed = (title: string, act: string, chapter: string, episode: number | null): SceneDTO => {
      let id = 0;
      for (const projectScenes of scenesByProject.values()) {
        for (const sceneRow of projectScenes) id = Math.max(id, sceneRow.id);
      }
      const created = scene({
        id: id + 1,
        title: title.trim() || "Untitled Scene",
        act,
        chapter,
        content: "",
        sort_order: 0,
        order_index: 0,
      });
      candidateEpisodes.set(created.id, episode);
      createdSceneId = created.id;
      affectedSceneIds = [created.id];
      changed = true;
      return created;
    };

    switch (command.kind) {
      case "create_scene": {
        const act = label(command.act, "act");
        const chapter = chapterLabel(command.chapter, "chapter");
        const episode = episodeId(command.episode_id);
        const siblings = canonical.filter((sceneRow) => (
          sceneRow.act.trim() === act
          && sceneRow.chapter.trim() === chapter
          && inEpisodeScope(sceneRow, episode)
        ));
        if (siblings.length === 0) reject("The destination structure group does not exist.");
        const index = insertionIndex(command.index, siblings.length);
        const created = createSeed(command.title ?? "Untitled Scene", act, chapter, episode);
        const at = index < siblings.length
          ? canonical.indexOf(siblings[index]!)
          : canonical.indexOf(siblings.at(-1)!) + 1;
        canonical.splice(at, 0, created);
        break;
      }
      case "create_act": {
        const act = label(command.act, "act");
        const episode = episodeId(command.episode_id);
        const episodeRows = canonical.filter((sceneRow) => inEpisodeScope(sceneRow, episode));
        if (episodeRows.some((sceneRow) => sceneRow.act.trim() === act)) {
          reject(`Act '${act}' already exists.`);
        }
        const chapter = chapterLabel(
          command.chapter ?? (requiresChapterParents ? "Chapter 1" : ""),
          "chapter",
        );
        const namedActs = distinctLabels(episodeRows.map((sceneRow) => sceneRow.act.trim()));
        const index = insertionIndex(command.index, namedActs.length);
        const created = createSeed(
          command.title ?? "Untitled Scene",
          act,
          chapter,
          episode,
        );
        let at = canonical.length;
        if (index < namedActs.length) {
          at = canonical.findIndex((sceneRow) => (
            inEpisodeScope(sceneRow, episode) && sceneRow.act.trim() === namedActs[index]
          ));
        } else {
          const looseAct = episodeRows.find((sceneRow) => !sceneRow.act.trim());
          if (looseAct) at = canonical.indexOf(looseAct);
          else if (episodeRows.length > 0) at = canonical.indexOf(episodeRows.at(-1)!) + 1;
        }
        canonical.splice(at < 0 ? canonical.length : at, 0, created);
        break;
      }
      case "create_chapter": {
        if (project.narrative_engine !== "novel" && !isSeries) {
          reject("Chapters can only be created for Novel or Series projects.");
        }
        const act = label(command.act, "act");
        const chapter = label(command.chapter, "chapter");
        const episode = episodeId(command.episode_id);
        const actRows = canonical.filter((sceneRow) => (
          sceneRow.act.trim() === act && inEpisodeScope(sceneRow, episode)
        ));
        if (actRows.length === 0) reject(`Act '${act}' does not exist.`);
        if (actRows.some((sceneRow) => sceneRow.chapter.trim() === chapter)) {
          reject(`Chapter '${chapter}' already exists in Act '${act}'.`);
        }
        const namedChapters = distinctLabels(actRows.map((sceneRow) => sceneRow.chapter.trim()));
        const index = insertionIndex(command.index, namedChapters.length);
        const created = createSeed(
          command.title ?? "Untitled Scene",
          act,
          chapter,
          episode,
        );
        let at: number;
        if (index < namedChapters.length) {
          at = canonical.findIndex((sceneRow) => (
            sceneRow.act.trim() === act && sceneRow.chapter.trim() === namedChapters[index]
            && inEpisodeScope(sceneRow, episode)
          ));
        } else {
          const looseChapter = actRows.find((sceneRow) => !sceneRow.chapter.trim());
          at = looseChapter
            ? canonical.indexOf(looseChapter)
            : canonical.indexOf(actRows.at(-1)!) + 1;
        }
        canonical.splice(at, 0, created);
        break;
      }
      case "rename_act": {
        const act = label(command.act, "act");
        const newName = label(command.new_name, "new_name");
        const episode = episodeId(command.episode_id);
        const matches = canonical.filter((sceneRow) => (
          sceneRow.act.trim() === act && inEpisodeScope(sceneRow, episode)
        ));
        if (matches.length === 0) reject(`Act '${act}' does not exist.`);
        if (newName === act) break;
        if (canonical.some((sceneRow) => (
          sceneRow.act.trim() === newName && inEpisodeScope(sceneRow, episode)
        ))) {
          reject(`Act '${newName}' already exists.`);
        }
        for (const sceneRow of matches) sceneRow.act = newName;
        affectedSceneIds = matches.map((sceneRow) => sceneRow.id);
        changed = true;
        break;
      }
      case "rename_chapter": {
        const act = label(command.act, "act");
        const chapter = label(command.chapter, "chapter");
        const newName = label(command.new_name, "new_name");
        const episode = episodeId(command.episode_id);
        const matches = canonical.filter((sceneRow) => (
          sceneRow.act.trim() === act && sceneRow.chapter.trim() === chapter
          && inEpisodeScope(sceneRow, episode)
        ));
        if (matches.length === 0) reject(`Chapter '${chapter}' does not exist in Act '${act}'.`);
        if (newName === chapter) break;
        if (canonical.some((sceneRow) => (
          sceneRow.act.trim() === act && sceneRow.chapter.trim() === newName
          && inEpisodeScope(sceneRow, episode)
        ))) {
          reject(`Chapter '${newName}' already exists in Act '${act}'.`);
        }
        for (const sceneRow of matches) sceneRow.chapter = newName;
        affectedSceneIds = matches.map((sceneRow) => sceneRow.id);
        changed = true;
        break;
      }
      case "detach_act": {
        const act = label(command.act, "act");
        const episode = episodeId(command.episode_id);
        const matches = canonical.filter((sceneRow) => (
          sceneRow.act.trim() === act && inEpisodeScope(sceneRow, episode)
        ));
        if (matches.length === 0) reject(`Act '${act}' does not exist.`);
        for (const sceneRow of matches) sceneRow.act = "";
        affectedSceneIds = matches.map((sceneRow) => sceneRow.id);
        changed = true;
        break;
      }
      case "detach_chapter": {
        const act = label(command.act, "act");
        const chapter = label(command.chapter, "chapter");
        const episode = episodeId(command.episode_id);
        const matches = canonical.filter((sceneRow) => (
          sceneRow.act.trim() === act && sceneRow.chapter.trim() === chapter
          && inEpisodeScope(sceneRow, episode)
        ));
        if (matches.length === 0) reject(`Chapter '${chapter}' does not exist in Act '${act}'.`);
        for (const sceneRow of matches) sceneRow.chapter = "";
        affectedSceneIds = matches.map((sceneRow) => sceneRow.id);
        changed = true;
        break;
      }
      case "delete_scene": {
        if (!Number.isSafeInteger(command.scene_id) || command.scene_id <= 0) {
          reject("scene_id must be a positive integer.");
        }
        const at = canonical.findIndex((sceneRow) => sceneRow.id === command.scene_id);
        if (at < 0) reject(`Scene ${command.scene_id} does not exist.`, "not_found", 404);
        canonical.splice(at, 1);
        candidateEpisodes.delete(command.scene_id);
        affectedSceneIds = [command.scene_id];
        changed = true;
        break;
      }
      case "repair_orphans": {
        for (const sceneRow of canonical) {
          if (sceneRow.act.trim() && (!requiresChapterParents || sceneRow.chapter.trim())) continue;
          sceneRow.act = sceneRow.act.trim() || "Recovered Act";
          if (requiresChapterParents) {
            sceneRow.chapter = sceneRow.chapter.trim() || "Recovered Chapter";
          }
          affectedSceneIds.push(sceneRow.id);
        }
        changed = affectedSceneIds.length > 0;
        break;
      }
    }

    if (changed) {
      canonical.forEach((sceneRow, index) => {
        sceneRow.sort_order = index;
        sceneRow.order_index = index + 1;
        sceneRow.revision = `mock-scene-${++MOCK_SCENE_REVISION}`;
      });
      scenesFor(projectId).splice(0, scenesFor(projectId).length, ...canonical);
      episodesByProject.set(projectId, candidateEpisodes);
      if (command.kind === "delete_scene") {
        scrubTimelineScene(projectId, command.scene_id);
      }
    }
    return {
      structure: storyStructureFor(projectId),
      changed,
      created_scene_id: createdSceneId,
      affected_scene_ids: affectedSceneIds,
    };
  };
  const timelineSnapshotFrom = (
    projectId: number,
    state = timelineStateFor(projectId),
    projectScenes = scenesFor(projectId),
  ): TimelineSnapshotDTO => {
    const structure = storyStructureFor(projectId);
    const structureRefs = structure.acts.flatMap((act) => act.chapters.flatMap((chapter) => (
      chapter.scenes.map((sceneRef) => ({
        id: sceneRef.id,
        structuralNumber: sceneRef.number,
      }))
    )));
    const structuralOrder = structureRefs.map((sceneRef) => sceneRef.id);
    const structuralNumberById = new Map(
      structureRefs.map((sceneRef) => [sceneRef.id, sceneRef.structuralNumber]),
    );
    const byId = new Map(projectScenes.map((sceneRow) => [sceneRow.id, sceneRow]));
    const eventIds = new Set(projectScenes
      .filter((sceneRow) => sceneRow.plotline.trim() || state.explicitEventIds.has(sceneRow.id))
      .map((sceneRow) => sceneRow.id));
    const baseOrder = state.orderMode === "custom" ? state.customOrder : structuralOrder;
    const orderedEventIds = baseOrder.filter((sceneId, index) => (
      eventIds.has(sceneId) && baseOrder.indexOf(sceneId) === index
    ));
    const orderedSet = new Set(orderedEventIds);
    for (const sceneId of structuralOrder) {
      if (eventIds.has(sceneId) && !orderedSet.has(sceneId)) {
        orderedEventIds.push(sceneId);
        orderedSet.add(sceneId);
      }
    }
    const lanes = [...state.lanes]
      .sort((left, right) => left.order_index - right.order_index || left.id - right.id)
      .map((lane, index) => ({ ...lane, order_index: index, event_count: 0 }));
    const laneByName = new Map(lanes.map((lane) => [lane.name, lane]));
    const events = orderedEventIds.flatMap((sceneId, index) => {
      const sceneRow = byId.get(sceneId);
      if (!sceneRow) return [];
      const lane = laneByName.get(sceneRow.plotline.trim());
      if (lane) lane.event_count += 1;
      const details = state.details.get(sceneId);
      return [tEvent({
        id: sceneRow.id,
        order_index: index + 1,
        title: sceneRow.title,
        structural_number: structuralNumberById.get(sceneRow.id) ?? "",
        act: sceneRow.act,
        chapter: sceneRow.chapter,
        plotline: sceneRow.plotline,
        color_label: sceneRow.color_label,
        lane_id: lane?.id ?? null,
        time_of_day: details?.time_of_day ?? "",
        location: details?.location || details?.slugline || "",
        duration_minutes: details?.estimated_duration_minutes
          || details?.performance_duration_minutes
          || 0,
        character_states: details?.character_states.map((item) => ({ ...item })) ?? [],
      })];
    });
    const off_timeline = structuralOrder.flatMap((sceneId) => {
      if (eventIds.has(sceneId)) return [];
      const sceneRow = byId.get(sceneId);
      if (!sceneRow) return [];
      return [{
        id: sceneRow.id,
        title: sceneRow.title,
        structural_number: structuralNumberById.get(sceneRow.id) ?? "",
        act: sceneRow.act,
        chapter: sceneRow.chapter,
      }];
    });
    const revisionPayload = {
      project_id: projectId,
      narrative_engine: projects.find((project) => project.id === projectId)?.narrative_engine ?? "",
      order_mode: state.orderMode,
      lanes: lanes.map(({ event_count: _eventCount, ...lane }) => lane),
      explicit_event_ids: [...state.explicitEventIds].sort((left, right) => left - right),
      custom_order: state.customOrder,
      scenes: projectScenes.map((sceneRow) => [
        sceneRow.id,
        sceneRow.act.trim(),
        sceneRow.chapter.trim(),
        episodeFor(projectId, sceneRow.id),
        sceneRow.sort_order,
        sceneRow.plotline.trim(),
        sceneRow.color_label,
      ]),
    };
    let hash = 0x811c9dc5;
    for (const char of JSON.stringify(revisionPayload)) {
      hash ^= char.charCodeAt(0);
      hash = Math.imul(hash, 0x01000193) >>> 0;
    }
    return {
      project_id: projectId,
      revision: hash.toString(16).padStart(8, "0").repeat(8),
      order_mode: state.orderMode,
      lanes,
      events,
      off_timeline,
    };
  };
  const executeTimelineCommand = (
    projectId: number,
    command: TimelineCommandDTO,
  ): TimelineCommandResultDTO => {
    const path = `/api/projects/${projectId}/timeline/commands`;
    findMockProject(projects, projectId, "POST", path);
    const current = timelineSnapshotFrom(projectId);
    if (command.expected_revision !== current.revision) {
      throw new ApiRequestError(
        "POST",
        path,
        409,
        "The Timeline changed after it was loaded.",
        "timeline_conflict",
      );
    }
    const sourceState = timelineStateFor(projectId);
    const candidate: MockTimelineState = {
      lanes: sourceState.lanes.map((lane) => ({ ...lane })),
      explicitEventIds: new Set(sourceState.explicitEventIds),
      customOrder: [...sourceState.customOrder],
      orderMode: sourceState.orderMode,
      details: new Map([...sourceState.details.entries()].map(([sceneId, details]) => [sceneId, {
        ...details,
        character_states: details.character_states.map((state) => ({ ...state })),
      }])),
    };
    const candidateScenes = scenesFor(projectId).map(cloneScene);
    const reject = (detail: string, status = 400, code = "bad_request"): never => {
      throw new ApiRequestError("POST", path, status, detail, code);
    };
    const laneById = (laneId: number): TimelineLaneDTO => candidate.lanes.find(
      (lane) => lane.id === laneId,
    ) ?? reject(`Timeline lane ${laneId} not found.`, 404, "not_found");
    const sceneById = (sceneId: number): SceneDTO => candidateScenes.find(
      (sceneRow) => sceneRow.id === sceneId,
    ) ?? reject(`Scene ${sceneId} not found.`, 404, "not_found");
    const normalizeLaneOrder = (): void => {
      candidate.lanes.forEach((lane, index) => { lane.order_index = index; });
    };
    const laneName = (value: string): string => {
      const name = value.trim();
      return name || reject("Timeline lane name cannot be empty.");
    };
    const duplicateLane = (name: string, excludingId?: number): boolean => candidate.lanes.some(
      (lane) => lane.id !== excludingId
        && lane.name.trim().toLocaleLowerCase() === name.toLocaleLowerCase(),
    );
    const indexIn = (value: number, maximum: number, field = "index"): number => {
      if (!Number.isSafeInteger(value) || value < 0 || value > maximum) {
        return reject(`${field} must be between 0 and ${maximum}.`);
      }
      return value;
    };
    let changed = false;
    let affectedSceneIds: number[] = [];

    switch (command.kind) {
      case "create_lane": {
        const name = laneName(command.name);
        if (duplicateLane(name)) reject(`A Timeline lane named '${name}' already exists.`);
        const index = command.index == null
          ? candidate.lanes.length
          : indexIn(command.index, candidate.lanes.length);
        const id = candidate.lanes.reduce((maximum, lane) => Math.max(maximum, lane.id), 0) + 1;
        candidate.lanes.splice(index, 0, {
          id,
          name,
          color_label: command.color_label ?? "",
          order_index: index,
          collapsed: false,
          event_count: 0,
        });
        normalizeLaneOrder();
        changed = true;
        break;
      }
      case "update_lane": {
        const lane = laneById(command.lane_id);
        if (command.name === undefined && command.color_label === undefined
          && command.collapsed === undefined && command.index === undefined) {
          reject("update_lane requires at least one changed field.");
        }
        if (command.name !== undefined) {
          const name = laneName(command.name);
          if (duplicateLane(name, lane.id)) reject(`A Timeline lane named '${name}' already exists.`);
          if (name !== lane.name) {
            const oldName = lane.name;
            lane.name = name;
            for (const sceneRow of candidateScenes) {
              if (sceneRow.plotline.trim() !== oldName.trim()) continue;
              sceneRow.plotline = name;
              affectedSceneIds.push(sceneRow.id);
            }
            changed = true;
          }
        }
        if (command.color_label !== undefined && command.color_label !== lane.color_label) {
          lane.color_label = command.color_label;
          changed = true;
        }
        if (command.collapsed !== undefined && command.collapsed !== lane.collapsed) {
          lane.collapsed = command.collapsed;
          changed = true;
        }
        if (command.index !== undefined) {
          const oldIndex = candidate.lanes.findIndex((item) => item.id === lane.id);
          const remaining = candidate.lanes.filter((item) => item.id !== lane.id);
          const index = indexIn(command.index, remaining.length);
          if (index !== oldIndex) {
            candidate.lanes.splice(oldIndex, 1);
            candidate.lanes.splice(index, 0, lane);
            normalizeLaneOrder();
            changed = true;
          }
        }
        break;
      }
      case "delete_lane": {
        const lane = laneById(command.lane_id);
        const laneIndex = candidate.lanes.findIndex((item) => item.id === lane.id);
        for (const sceneRow of candidateScenes) {
          if (sceneRow.plotline.trim() !== lane.name.trim()) continue;
          candidate.explicitEventIds.add(sceneRow.id);
          sceneRow.plotline = "";
          affectedSceneIds.push(sceneRow.id);
        }
        candidate.lanes.splice(laneIndex, 1);
        normalizeLaneOrder();
        changed = true;
        break;
      }
      case "place_event": {
        const sceneRow = sceneById(command.scene_id);
        const destination = command.lane_id === null ? null : laneById(command.lane_id);
        const wasEvent = Boolean(sceneRow.plotline.trim()) || candidate.explicitEventIds.has(sceneRow.id);
        const wasExplicit = candidate.explicitEventIds.has(sceneRow.id);
        const nextPlotline = destination?.name ?? "";
        candidate.explicitEventIds.add(sceneRow.id);
        if (!wasEvent || !wasExplicit) changed = true;
        if (sceneRow.plotline !== nextPlotline) {
          sceneRow.plotline = nextPlotline;
          changed = true;
          affectedSceneIds = [sceneRow.id];
        }
        if (command.index != null) {
          const currentOrder = timelineSnapshotFrom(projectId, candidate, candidateScenes)
            .events.map((event) => event.id);
          const requestedOrder = currentOrder.filter((sceneId) => sceneId !== sceneRow.id);
          const index = indexIn(command.index, requestedOrder.length);
          requestedOrder.splice(index, 0, sceneRow.id);
          if (candidate.orderMode !== "custom"
            || requestedOrder.join(",") !== candidate.customOrder.join(",")) {
            candidate.orderMode = "custom";
            candidate.customOrder = requestedOrder;
            changed = true;
          }
        } else if (candidate.orderMode === "custom") {
          const currentOrder = timelineSnapshotFrom(projectId, candidate, candidateScenes)
            .events.map((event) => event.id);
          if (currentOrder.join(",") !== candidate.customOrder.join(",")) {
            candidate.customOrder = currentOrder;
            changed = true;
          }
        }
        break;
      }
      case "remove_event": {
        const sceneRow = sceneById(command.scene_id);
        const wasEvent = Boolean(sceneRow.plotline.trim()) || candidate.explicitEventIds.has(sceneRow.id);
        if (wasEvent) {
          const changedPlotline = Boolean(sceneRow.plotline);
          sceneRow.plotline = "";
          candidate.explicitEventIds.delete(sceneRow.id);
          candidate.customOrder = candidate.customOrder.filter((sceneId) => sceneId !== sceneRow.id);
          affectedSceneIds = changedPlotline ? [sceneRow.id] : [];
          changed = true;
        }
        break;
      }
      case "set_order_mode": {
        if (candidate.orderMode !== command.mode) {
          if (command.mode === "custom") {
            candidate.customOrder = current.events.map((event) => event.id);
          }
          candidate.orderMode = command.mode;
          changed = true;
        }
        break;
      }
    }

    if (changed) {
      affectedSceneIds = [...new Set(affectedSceneIds)];
      for (const sceneRow of candidateScenes) {
        if (affectedSceneIds.includes(sceneRow.id)) {
          sceneRow.revision = `mock-scene-${++MOCK_SCENE_REVISION}`;
        }
      }
      scenesFor(projectId).splice(0, scenesFor(projectId).length, ...candidateScenes);
      timelineStates.set(projectId, candidate);
    }
    const timeline = timelineSnapshotFrom(projectId);
    return {
      timeline,
      replayed: false,
      applied_revision: timeline.revision,
      changed,
      affected_scene_ids: changed ? affectedSceneIds : [],
    };
  };
  const executeCanvasPlotCommand = (
    projectId: number,
    command: CanvasPlotCommandDTO,
  ): CanvasPlotCommandResultDTO => {
    const requestPath = `/api/projects/${projectId}/canvas-plot/commands`;
    const current = structuredClone(canvasFor(projectId));
    if (command.expected_revision !== current.revision) {
      throw new ApiRequestError("POST", requestPath, 409, "The Canvas Plot changed after it was loaded.", "canvas_plot_conflict");
    }
    const next = structuredClone(current);
    const affectedNodeIds: number[] = [];
    const affectedLinkIds: number[] = [];
    const affectedFrameIds: number[] = [];
    let createdNodeId: number | null = null;
    let createdLinkId: number | null = null;
    let createdFrameId: number | null = null;
    let changed = false;
    const created_at = new Date().toISOString();
    const badRequest = (message: string): never => {
      throw new ApiRequestError("POST", requestPath, 400, message, "bad_request");
    };
    const missing = (kind: string, id: number): never => {
      throw new ApiRequestError("POST", requestPath, 404, `${kind} ${id} was not found.`, "not_found");
    };
    const checkedString = (value: unknown, label: string, maximum: number): string => {
      if (typeof value !== "string") return badRequest(`${label} must be a string`);
      if (value.length > maximum) return badRequest(`${label} cannot exceed ${maximum} characters`);
      return value;
    };
    const checkedNumber = (value: unknown, label: string): number => {
      if (typeof value !== "number" || !Number.isFinite(value)) {
        return badRequest(`${label} must be a finite number`);
      }
      return value;
    };
    const checkedDimension = (value: unknown, label: string): number => {
      const number = checkedNumber(value, label);
      if (number <= 0) return badRequest(`${label} must be greater than zero`);
      return number;
    };
    const checkedIndex = (value: unknown, maximum: number): number => {
      if (!Number.isInteger(value) || (value as number) < 0 || (value as number) > maximum) {
        return badRequest("Node index is outside the available range");
      }
      return value as number;
    };
    const checkedSceneReference = (value: number | null | undefined): number | null => {
      if (value == null) return null;
      if (!Number.isInteger(value) || value <= 0 || !scenesFor(projectId).some((sceneRow) => sceneRow.id === value)) {
        return missing("Scene", value);
      }
      return value;
    };
    const denseNodeOrder = (): void => {
      next.nodes.forEach((node, index) => { node.sort_order = index; });
    };
    const nodeById = (id: number) => next.nodes.find((node) => node.id === id) ?? missing("Canvas Plot node", id);
    const linkById = (id: number) => next.links.find((link) => link.id === id) ?? missing("Canvas Plot link", id);
    const frameById = (id: number) => next.frames.find((frame) => frame.id === id) ?? missing("Canvas Plot frame", id);

    switch (command.kind) {
      case "create_node": {
        const insertion = checkedIndex(command.index ?? next.nodes.length, next.nodes.length);
        const node = {
          id: canvasIdsFor(projectId).nextNodeId,
          title: checkedString(command.title ?? "", "title", 500),
          body: checkedString(command.body ?? "", "body", 100_000),
          x: checkedNumber(command.x ?? 0, "x"),
          y: checkedNumber(command.y ?? 0, "y"),
          width: checkedDimension(command.width ?? 180, "width"),
          height: checkedDimension(command.height ?? 110, "height"),
          color_label: checkedString(command.color_label ?? "", "color_label", 100),
          group_label: checkedString(command.group_label ?? "", "group_label", 500),
          scene_id: checkedSceneReference(command.scene_id),
          sort_order: insertion,
          created_at,
        };
        createdNodeId = node.id;
        canvasIdsFor(projectId).nextNodeId += 1;
        next.nodes.splice(insertion, 0, node);
        denseNodeOrder();
        affectedNodeIds.push(createdNodeId);
        changed = true;
        break;
      }
      case "update_node": {
        const updates = [
          command.title,
          command.body,
          command.x,
          command.y,
          command.width,
          command.height,
          command.color_label,
          command.group_label,
          command.scene_id,
          command.index,
        ];
        if (!updates.some((value) => value !== undefined)) {
          return badRequest("update_node must change at least one field");
        }
        const node = nodeById(command.node_id);
        const before = JSON.stringify(next.nodes);
        if (command.title !== undefined) node.title = checkedString(command.title, "title", 500);
        if (command.body !== undefined) node.body = checkedString(command.body, "body", 100_000);
        if (command.x !== undefined) node.x = checkedNumber(command.x, "x");
        if (command.y !== undefined) node.y = checkedNumber(command.y, "y");
        if (command.width !== undefined) node.width = checkedDimension(command.width, "width");
        if (command.height !== undefined) node.height = checkedDimension(command.height, "height");
        if (command.color_label !== undefined) node.color_label = checkedString(command.color_label, "color_label", 100);
        if (command.group_label !== undefined) node.group_label = checkedString(command.group_label, "group_label", 500);
        if (command.scene_id !== undefined) node.scene_id = checkedSceneReference(command.scene_id);
        if (command.index !== undefined) {
          const oldIndex = next.nodes.indexOf(node);
          const newIndex = checkedIndex(command.index, next.nodes.length - 1);
          if (oldIndex !== newIndex) {
            next.nodes.splice(oldIndex, 1);
            next.nodes.splice(newIndex, 0, node);
            denseNodeOrder();
          }
        }
        changed = before !== JSON.stringify(next.nodes);
        if (changed) affectedNodeIds.push(node.id);
        break;
      }
      case "delete_node": {
        nodeById(command.node_id);
        const removedLinks = next.links.filter((link) => link.source_node_id === command.node_id || link.target_node_id === command.node_id);
        next.links = next.links.filter((link) => !removedLinks.includes(link));
        next.nodes = next.nodes.filter((node) => node.id !== command.node_id);
        denseNodeOrder();
        affectedNodeIds.push(command.node_id);
        affectedLinkIds.push(...removedLinks.map((link) => link.id));
        changed = true;
        break;
      }
      case "create_link": {
        nodeById(command.source_node_id);
        nodeById(command.target_node_id);
        if (command.source_node_id === command.target_node_id) {
          return badRequest("A Canvas Plot node cannot link to itself");
        }
        const duplicate = next.links.some((link) => (
          (link.source_node_id === command.source_node_id && link.target_node_id === command.target_node_id)
          || (link.source_node_id === command.target_node_id && link.target_node_id === command.source_node_id)
        ));
        if (!duplicate) {
          const ids = canvasIdsFor(projectId);
          createdLinkId = ids.nextLinkId;
          ids.nextLinkId += 1;
          next.links.push({
            id: createdLinkId,
            source_node_id: command.source_node_id,
            target_node_id: command.target_node_id,
            label: checkedString(command.label ?? "", "label", 500),
            color_label: checkedString(command.color_label ?? "gray", "color_label", 100) || "gray",
            link_type: checkedString(command.link_type ?? "", "link_type", 100),
            created_at,
          });
          affectedLinkIds.push(createdLinkId);
          changed = true;
        }
        break;
      }
      case "update_link": {
        if (command.label === undefined && command.color_label === undefined && command.link_type === undefined) {
          return badRequest("update_link must change at least one field");
        }
        const link = linkById(command.link_id);
        const before = JSON.stringify(link);
        if (command.label !== undefined) link.label = checkedString(command.label, "label", 500);
        if (command.color_label !== undefined) {
          link.color_label = checkedString(command.color_label, "color_label", 100) || "gray";
        }
        if (command.link_type !== undefined) link.link_type = checkedString(command.link_type, "link_type", 100);
        changed = before !== JSON.stringify(link);
        if (changed) affectedLinkIds.push(link.id);
        break;
      }
      case "delete_link": {
        linkById(command.link_id);
        next.links = next.links.filter((link) => link.id !== command.link_id);
        affectedLinkIds.push(command.link_id);
        changed = true;
        break;
      }
      case "create_frame": {
        const ids = canvasIdsFor(projectId);
        createdFrameId = ids.nextFrameId;
        const frame = {
          id: createdFrameId,
          title: checkedString(command.title ?? "", "title", 500),
          color_label: checkedString(command.color_label ?? "", "color_label", 100),
          x: checkedNumber(command.x ?? 0, "x"),
          y: checkedNumber(command.y ?? 0, "y"),
          width: checkedDimension(command.width ?? 360, "width"),
          height: checkedDimension(command.height ?? 260, "height"),
          created_at,
        };
        ids.nextFrameId += 1;
        next.frames.push(frame);
        affectedFrameIds.push(createdFrameId);
        changed = true;
        break;
      }
      case "update_frame": {
        const updates = [command.title, command.color_label, command.x, command.y, command.width, command.height];
        if (!updates.some((value) => value !== undefined)) {
          return badRequest("update_frame must change at least one field");
        }
        const frame = frameById(command.frame_id);
        const before = JSON.stringify(frame);
        if (command.title !== undefined) frame.title = checkedString(command.title, "title", 500);
        if (command.color_label !== undefined) frame.color_label = checkedString(command.color_label, "color_label", 100);
        if (command.x !== undefined) frame.x = checkedNumber(command.x, "x");
        if (command.y !== undefined) frame.y = checkedNumber(command.y, "y");
        if (command.width !== undefined) frame.width = checkedDimension(command.width, "width");
        if (command.height !== undefined) frame.height = checkedDimension(command.height, "height");
        changed = before !== JSON.stringify(frame);
        if (changed) affectedFrameIds.push(frame.id);
        break;
      }
      case "delete_frame": {
        frameById(command.frame_id);
        next.frames = next.frames.filter((frame) => frame.id !== command.frame_id);
        affectedFrameIds.push(command.frame_id);
        changed = true;
        break;
      }
    }
    if (changed) {
      next.revision = canvasRevision({
        project_id: next.project_id,
        nodes: next.nodes,
        links: next.links,
        frames: next.frames,
      });
      canvasStates.set(projectId, next);
    }
    const canvasPlot = structuredClone(changed ? next : current);
    return {
      canvas_plot: canvasPlot,
      replayed: false,
      applied_revision: canvasPlot.revision,
      changed,
      affected_node_ids: affectedNodeIds,
      affected_link_ids: affectedLinkIds,
      affected_frame_ids: affectedFrameIds,
      created_node_id: createdNodeId,
      created_link_id: createdLinkId,
      created_frame_id: createdFrameId,
    };
  };
  const fixtureRowsFor = <T>(projectId: number, rows: readonly T[]): readonly T[] => (
    projectId === fixtureProjectId ? rows : []
  );
  interface MockKnowledgeGraphReview {
    is_hidden: boolean;
    is_user_confirmed: boolean;
  }
  interface MockKnowledgeGraphReceipt {
    serializedCommand: string;
    receipt: KnowledgeGraphCommandReceiptDTO;
  }
  const knowledgeGraphReviews = new Map<number, Map<string, MockKnowledgeGraphReview>>();
  const knowledgeGraphReceipts = new Map<string, MockKnowledgeGraphReceipt>();
  interface MockContinuityReceipt {
    serializedCommand: string;
    receipt: ContinuityCommandReceiptDTO;
  }
  const continuityStatuses = new Map<number, Map<string, ContinuityIssueDTO["status"]>>();
  const continuityReceipts = new Map<string, MockContinuityReceipt>();
  const continuityIssues: readonly ContinuityIssueDTO[] = [
    {
      id: "c200000000000002",
      review_fingerprint: "2".repeat(64),
      issue_type: "state_drift",
      dimension: "character",
      severity: "blocking",
      confidence: "confirmed",
      title: "Vesper's stance contradicts an earlier scene",
      explanation: "She withholds in Observation Ring but already confessed earlier.",
      suggested_action: "Reconcile the confession order.",
      related_scene_ids: [2, 12],
      status: "open",
    },
    {
      id: "c100000000000001",
      review_fingerprint: "1".repeat(64),
      issue_type: "location_jump",
      dimension: "spatial",
      severity: "warning",
      confidence: "likely",
      title: "Location jump without transition",
      explanation: "Scene moves to the reactor with no bridging beat.",
      suggested_action: "Add a transition or establish the move.",
      related_scene_ids: [12, 21],
      status: "open",
    },
  ];
  const knowledgeGraphEdgeKey = (edge: { source: string; target: string; edge_type: string }) => (
    [edge.source, edge.target, edge.edge_type].join("\u0000")
  );
  const knowledgeGraphReviewFor = (projectId: number) => {
    let reviews = knowledgeGraphReviews.get(projectId);
    if (!reviews) {
      reviews = new Map();
      knowledgeGraphReviews.set(projectId, reviews);
    }
    return reviews;
  };
  const mockSha256 = (payload: unknown): string => {
    let hash = 0x811c9dc5;
    for (const char of JSON.stringify(payload)) {
      hash ^= char.charCodeAt(0);
      hash = Math.imul(hash, 0x01000193) >>> 0;
    }
    return hash.toString(16).padStart(8, "0").repeat(8);
  };
  const knowledgeGraphRevision = (projectId: number): string => mockSha256([
    projectId,
    [...knowledgeGraphReviewFor(projectId).entries()]
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, state]) => [key, state.is_hidden, state.is_user_confirmed]),
  ]);
  const continuityStatusFor = (projectId: number) => {
    let statuses = continuityStatuses.get(projectId);
    if (!statuses) {
      statuses = new Map();
      continuityStatuses.set(projectId, statuses);
    }
    return statuses;
  };
  const continuityRevision = (projectId: number): string => mockSha256([
    projectId,
    [...continuityStatusFor(projectId).entries()].sort(([left], [right]) => left.localeCompare(right)),
  ]);
  const continuityReport = (projectId: number): ContinuityReportDTO => {
    const project = findMockProject(projects, projectId, "GET", `/api/projects/${projectId}/continuity`);
    const statuses = continuityStatusFor(projectId);
    const issues = fixtureRowsFor(projectId, continuityIssues).map((issue) => ({
      ...structuredClone(issue),
      status: statuses.get(issue.id) ?? issue.status,
    }));
    return {
      project_id: projectId,
      review_revision: continuityRevision(projectId),
      writing_mode: project.narrative_engine,
      issues,
      blocking_count: issues.filter((issue) => issue.status === "open" && issue.severity === "blocking").length,
      warning_count: issues.filter((issue) => issue.status === "open" && issue.severity === "warning").length,
      unavailable: [],
    };
  };
  interface MockWorkflowReceipt {
    serializedCommand: string;
    receipt: WorkflowCommandReceiptDTO;
    result: WorkflowCommandResultDTO;
  }
  const workflowRuns = new Map<number, WorkflowRunDTO[]>();
  const workflowEvents = new Map<number, WorkflowEventDTO[]>();
  const workflowReceipts = new Map<string, MockWorkflowReceipt>();
  let workflowRunSequence = 1;
  let workflowEventSequence = 1;
  const workflowRevision = (run: Omit<WorkflowRunDTO, "revision"> | WorkflowRunDTO): string => mockSha256({
    id: run.id,
    project_id: run.project_id,
    status: run.status,
    current_step_id: run.current_step_id,
    steps: run.steps.map((step) => [step.step_id, step.status, step.notes, step.updated_at]),
    updated_at: run.updated_at,
  });
  const workflowsFor = (projectId: number): WorkflowRunDTO[] => {
    let runs = workflowRuns.get(projectId);
    if (!runs) {
      runs = [];
      workflowRuns.set(projectId, runs);
    }
    return runs;
  };
  const addWorkflowEvent = (
    projectId: number,
    runId: number,
    eventType: string,
    message: string,
    stepId: string | null = null,
  ): void => {
    const events = workflowEvents.get(runId) ?? [];
    events.push({
      id: workflowEventSequence++, project_id: projectId, workflow_run_id: runId,
      step_id: stepId, event_type: eventType, message, metadata: {}, created_at: new Date().toISOString(),
    });
    workflowEvents.set(runId, events);
  };
  const createWorkflowRun = (
    projectId: number,
    template: WorkflowTemplateDTO,
    writingMode: string,
    title = template.title,
  ): WorkflowRunDTO => {
    const timestamp = new Date().toISOString();
    const applicable = template.steps.filter((step) => step.modes.length === 0 || step.modes.includes(writingMode));
    const runWithoutRevision: Omit<WorkflowRunDTO, "revision"> = {
      id: workflowRunSequence++, project_id: projectId, title,
      description: template.description, status: "active", writing_mode: writingMode,
      template_id: template.id, current_step_id: applicable[0]?.id ?? "",
      total_steps: applicable.length, completed_steps: 0, source_type: "",
      source_id: null, created_at: timestamp, updated_at: timestamp, completed_at: null,
      steps: applicable.map((step, index) => ({
        step_id: step.id, title: step.title, description: step.description, kind: step.kind,
        status: index === 0 ? "active" : "pending", sort_index: index,
        section_name: step.section_name, action_id: step.action_id,
        completion_check: step.completion_check, notes: "", target_type: "", target_id: null,
        created_at: timestamp, updated_at: timestamp,
      })),
    };
    const run: WorkflowRunDTO = { ...runWithoutRevision, revision: workflowRevision(runWithoutRevision) };
    workflowsFor(projectId).push(run);
    addWorkflowEvent(projectId, run.id, "started", `Started workflow '${run.title}'.`);
    return run;
  };
  const refreshWorkflowPointer = (run: WorkflowRunDTO, timestamp: string): void => {
    run.completed_steps = run.steps.filter((step) => step.status === "completed" || step.status === "skipped").length;
    const next = run.steps.find((step) => step.status === "pending" || step.status === "active" || step.status === "blocked");
    run.steps.forEach((step) => {
      if (step === next && step.status !== "active") {
        step.status = "active";
        step.updated_at = timestamp;
      } else if (step !== next && step.status === "active") {
        step.status = "pending";
        step.updated_at = timestamp;
      }
    });
    run.current_step_id = next?.step_id ?? "";
    if (!next && run.total_steps > 0) {
      run.status = "completed";
      run.completed_at = timestamp;
    }
  };
  const projectOne = projects.find((project) => project.id === fixtureProjectId)!;
  const seededRewrite = createWorkflowRun(
    fixtureProjectId,
    MOCK_WORKFLOW_TEMPLATES.find((template) => template.id === "rewrite")!,
    projectOne.narrative_engine,
    "Rewrite Pass",
  );
  const seededTimestamp = new Date().toISOString();
  seededRewrite.steps[0]!.status = "completed";
  seededRewrite.steps[0]!.updated_at = seededTimestamp;
  seededRewrite.steps[1]!.status = "active";
  seededRewrite.current_step_id = seededRewrite.steps[1]!.step_id;
  seededRewrite.completed_steps = 1;
  seededRewrite.updated_at = seededTimestamp;
  seededRewrite.revision = workflowRevision(seededRewrite);
  addWorkflowEvent(fixtureProjectId, seededRewrite.id, "step_completed", "Completed step 'Select the passage'.", seededRewrite.steps[0]!.step_id);
  let commandPlanSequence = 1;
  const commandPlans = new Map<string, PsykeConsoleCommandPlanDTO & { entry_type?: string; entry_name?: string }>();
  const client: ApiClient = {
    async health() {
      await delay(60);
      return {
        status: "ok",
        service: "logosforge-api",
        instance_nonce: "preview-mock",
        mode: "preview-mock",
        version: "1.13.0",
        api_version: "1.13.0",
        core_version: "preview",
      };
    },
    async writingModes() {
      await delay(60);
      return {
        default_mode: MOCK_WRITING_MODES.default_mode,
        modes: MOCK_WRITING_MODES.modes.map((mode) => ({
          ...mode,
          structural_units: [...mode.structural_units],
        })),
      };
    },
    async listProjects() {
      await delay();
      return projects.map(cloneProject);
    },
    async createProject(body: ProjectCreateDTO) {
      await delay(160);
      const project = createMockProject(projects, body);
      scenesByProject.set(project.id, []);
      episodesByProject.set(project.id, new Map());
      timelineStates.set(project.id, emptyTimelineState());
      const canvas = canvasSeed(project.id);
      canvasStates.set(project.id, canvas);
      canvasIds.set(project.id, canvasIdsFrom(canvas));
      settingsByProject.set(project.id, structuredClone(DEFAULT_SETTINGS));
      return project;
    },
    async importWhiteboard(body: WhiteboardImportDTO): Promise<WhiteboardImportResultDTO> {
      await delay(220);
      const title = body.title?.trim() || "Imported Whiteboard";
      const project = createMockProject(projects, {
        title,
        narrative_engine: body.mode,
      });
      const projectScenes = scenesFor(project.id);
      const populatedBlocks = body.blocks.filter((block) => String(block.text ?? "").trim().length > 0);
      const sceneId = populatedBlocks.length > 0
        ? projectScenes.reduce((maximum, candidate) => Math.max(maximum, candidate.id), 0) + 1
        : -1;
      const sceneTitle = populatedBlocks.find((block) => block.type === "heading")?.text?.trim()
        || project.title;
      if (sceneId > 0) {
        const content = populatedBlocks
          .filter((block) => block.type !== "heading")
          .map((block) => String(block.text ?? "").trim())
          .filter(Boolean)
          .join("\n\n");
        const order = projectScenes.reduce((maximum, candidate) => Math.max(maximum, candidate.sort_order), 0) + 1;
        projectScenes.push(scene({
          id: sceneId,
          title: sceneTitle,
          content,
          sort_order: order,
          order_index: order,
        }));
      }
      const comments = body.comments ?? [];
      const replies = comments.reduce((total, comment) => total + (comment.replies?.length ?? 0), 0);
      return {
        project_id: project.id,
        title: project.title,
        mode: project.narrative_engine,
        scenes_created: sceneId > 0 ? 1 : 0,
        scene_titles: sceneId > 0 ? [sceneTitle] : [],
        scene_ids_by_block: body.blocks.map((block) => String(block.text ?? "").trim() && sceneId > 0 ? sceneId : -1),
        comments_created: 0,
        comments_skipped: comments.length,
        comment_replies_created: 0,
        comment_replies_skipped: replies,
      };
    },
    async importManuscript(body: ManuscriptImportDTO): Promise<ManuscriptImportResultDTO> {
      await delay(220);
      const fallbackTitle = body.filename?.replace(/\.[^.]+$/, "").trim() || "Imported Manuscript";
      const project = createMockProject(projects, {
        title: body.title?.trim() || fallbackTitle,
        narrative_engine: body.mode,
      });
      const projectScenes = scenesFor(project.id);
      const sceneId = projectScenes.reduce((maximum, candidate) => Math.max(maximum, candidate.id), 0) + 1;
      const order = projectScenes.reduce((maximum, candidate) => Math.max(maximum, candidate.sort_order), 0) + 1;
      const sceneTitle = project.title;
      projectScenes.push(scene({ id: sceneId, title: sceneTitle, sort_order: order, order_index: order }));
      return {
        project_id: project.id,
        title: project.title,
        mode: project.narrative_engine,
        scenes_created: 1,
        scene_titles: [sceneTitle],
      };
    },
    async getProject(id: number) {
      await delay(100);
      return cloneProject(findMockProject(projects, id, "GET"));
    },
    async updateProject(id: number, body: ProjectUpdateDTO) {
      await delay(140);
      const project = findMockProject(projects, id, "PATCH");
      const requestedMode = body.narrative_engine !== undefined
        ? mockWritingMode(body.narrative_engine, "PATCH", `/api/projects/${id}`)
        : undefined;
      if (body.title !== undefined) project.title = body.title;
      if (body.description !== undefined) project.description = body.description;
      if (requestedMode !== undefined) {
        const format = MOCK_DEFAULT_FORMAT[requestedMode];
        project.narrative_engine = requestedMode;
        project.default_writing_format = format;
        project.format_mode = format;
      }
      return cloneProject(project);
    },
    async deleteProject(id: number) {
      await delay(140);
      findMockProject(projects, id, "DELETE");
      projects.splice(projects.findIndex((candidate) => candidate.id === id), 1);
      scenesByProject.delete(id);
      episodesByProject.delete(id);
      timelineStates.delete(id);
      canvasStates.delete(id);
      canvasIds.delete(id);
      settingsByProject.delete(id);
      return { ok: true, deleted: id };
    },
    async openProject(id: number) {
      await delay(100);
      return cloneProject(findMockProject(projects, id, "POST", `/api/projects/${id}/open`));
    },
    async saveProject(id: number) {
      await delay(80);
      findMockProject(projects, id, "POST", `/api/projects/${id}/save`);
      return { ok: true, project_id: id };
    },
    async closeProject(id: number) {
      await delay(80);
      findMockProject(projects, id, "POST", `/api/projects/${id}/close`);
      return { ok: true, project_id: id };
    },
    async searchProject(
      p: number,
      query: string,
      kinds?: readonly ProjectSearchKind[],
      signal?: AbortSignal,
    ) {
      await delay(80);
      if (signal?.aborted) throw signal.reason ?? new DOMException("Request cancelled", "AbortError");
      findMockProject(projects, p, "GET", `/api/projects/${p}/search`);
      const needle = query.trim().toLocaleLowerCase();
      const allowed = new Set<ProjectSearchKind>(kinds?.length ? kinds : ["scene", "note", "psyke", "comment"]);
      const matches: ProjectSearchMatchDTO[] = [];
      const add = (kind: ProjectSearchKind, id: number, title: string, text: string, extra: Partial<ProjectSearchMatchDTO> = {}) => {
        if (!allowed.has(kind) || !needle || !text.toLocaleLowerCase().includes(needle)) return;
        matches.push({ kind, id, title, excerpt: text.replace(/\s+/g, " ").trim().slice(0, 240), ...extra });
      };
      for (const sceneRow of scenesFor(p)) {
        add("scene", sceneRow.id, sceneRow.title, [
          sceneRow.title, sceneRow.summary, sceneRow.synopsis, sceneRow.goal,
          sceneRow.conflict, sceneRow.outcome, sceneRow.beat, sceneRow.act,
          sceneRow.chapter, sceneRow.plotline, sceneRow.content, ...sceneRow.tags,
        ].join("\n"));
      }
      for (const note of fixtureRowsFor(p, NOTES)) add("note", note.id, note.title, [note.title, note.content, ...note.tags].join("\n"));
      for (const entry of fixtureRowsFor(p, PSYKE)) add("psyke", entry.id, entry.name, [entry.name, entry.type, ...entry.aliases, entry.notes].join("\n"));
      for (const comment of fixtureRowsFor(p, COMMENTS)) {
        add("comment", comment.id, `Comment ${comment.id}: ${comment.quote.slice(0, 80)}`, [
          comment.quote, comment.body, ...comment.replies.map((reply) => `${reply.author}: ${reply.body}`),
        ].join("\n"), { revision: comment.revision, resolved: comment.resolved });
      }
      return { query, matches: matches.slice(0, 40), limit: 40 };
    },
    async listNotes() { await delay(); return NOTES.map((n) => ({ ...n })); },
    async listComments() {
      await delay();
      return COMMENTS.map((comment) => ({
        ...comment,
        anchor: { ...comment.anchor },
        replies: comment.replies.map((reply) => ({ ...reply })),
      }));
    },
    async createComment(_p: number, body: InlineCommentCreateDTO) {
      await delay(140);
      const id = COMMENTS.reduce((maximum, comment) => Math.max(maximum, comment.id), 0) + 1;
      const timestamp = new Date().toISOString();
      const nextReplyId = COMMENTS.flatMap((candidate) => candidate.replies)
        .reduce((maximum, candidate) => Math.max(maximum, candidate.id), 0) + 1;
      const comment: InlineCommentDTO = {
        id,
        source_id: body.source_id ?? "",
        anchor: { ...body.anchor },
        quote: body.quote,
        body: body.body ?? "",
        resolved: body.resolved ?? false,
        replies: (body.replies ?? []).map((reply, index) => ({
          id: nextReplyId + index,
          source_id: reply.source_id ?? "",
          body: reply.body ?? "",
          author: reply.author ?? "you",
          sort_order: reply.sort_order ?? index,
          created_at: reply.created_at ?? timestamp,
        })),
        created_at: body.created_at ?? timestamp,
        updated_at: body.updated_at ?? timestamp,
        revision: nextMockCommentRevision(),
      };
      COMMENTS.push(comment);
      return { ...comment, anchor: { ...comment.anchor }, replies: comment.replies.map((reply) => ({ ...reply })) };
    },
    async updateComment(_p: number, commentId: number, body: InlineCommentUpdateDTO) {
      await delay(140);
      const comment = COMMENTS.find((candidate) => candidate.id === commentId);
      if (!comment) throw new Error(`comment ${commentId} not found`);
      if (body.anchor !== undefined) comment.anchor = { ...body.anchor };
      if (body.body !== undefined) comment.body = body.body;
      if (body.resolved !== undefined) comment.resolved = body.resolved;
      comment.updated_at = new Date().toISOString();
      comment.revision = nextMockCommentRevision();
      return {
        ...comment,
        anchor: { ...comment.anchor },
        replies: comment.replies.map((reply) => ({ ...reply })),
      };
    },
    async deleteComment(_p: number, commentId: number) {
      await delay(120);
      const index = COMMENTS.findIndex((candidate) => candidate.id === commentId);
      if (index < 0) throw new Error(`comment ${commentId} not found`);
      COMMENTS.splice(index, 1);
      return { ok: true, deleted: commentId };
    },
    async createCommentReply(_p: number, commentId: number, body: CommentReplyCreateDTO) {
      await delay(140);
      const comment = COMMENTS.find((candidate) => candidate.id === commentId);
      if (!comment) throw new Error(`comment ${commentId} not found`);
      const id = COMMENTS.flatMap((candidate) => candidate.replies)
        .reduce((maximum, candidate) => Math.max(maximum, candidate.id), 0) + 1;
      comment.replies.push({
        id,
        source_id: body.source_id ?? "",
        body: body.body ?? "",
        author: body.author ?? "you",
        sort_order: body.sort_order ?? comment.replies.length,
        created_at: body.created_at ?? new Date().toISOString(),
      });
      comment.updated_at = new Date().toISOString();
      comment.revision = nextMockCommentRevision();
      return { ...comment, anchor: { ...comment.anchor }, replies: comment.replies.map((reply) => ({ ...reply })) };
    },
    async deleteCommentReply(_p: number, commentId: number, replyId: number) {
      await delay(120);
      const comment = COMMENTS.find((candidate) => candidate.id === commentId);
      if (!comment) throw new Error(`comment ${commentId} not found`);
      const index = comment.replies.findIndex((reply) => reply.id === replyId);
      if (index < 0) throw new Error(`reply ${replyId} not found`);
      comment.replies.splice(index, 1);
      comment.updated_at = new Date().toISOString();
      comment.revision = nextMockCommentRevision();
      return { ok: true, deleted: replyId };
    },
    async listCharacters() { await delay(); return MOCK_CHARACTERS.map((c) => ({ ...c })); },
    async updateCharacter(_p: number, characterId: number, body: CharacterUpdateDTO) {
      await delay();
      const c = MOCK_CHARACTERS.find((x) => x.id === characterId);
      if (!c) throw new Error(`character ${characterId} not found`);
      if (body.name !== undefined) c.name = body.name;
      if (body.description !== undefined) c.description = body.description;
      if ("psyke_entry_id" in body) c.psyke_entry_id = body.psyke_entry_id ?? null;
      return { ...c };
    },
    async backfillCharacterLinks() { await delay(); return { ok: true, linked: 0 }; },
    async getThemeScenes(_p: number, entryId: number) { await delay(140); return { entry_id: entryId, scene_ids: [...(MOCK_THEME_SCENES[entryId] ?? [])] }; },
    async setThemeScenes(_p: number, entryId: number, sceneIds: number[]) { await delay(160); MOCK_THEME_SCENES[entryId] = [...sceneIds]; return { entry_id: entryId, scene_ids: [...sceneIds] }; },
    async listScenes(p: number) { await delay(); return scenesFor(p).map(cloneScene); },
    async getManuscriptSnapshot(p: number) { await delay(); return manuscriptSnapshotFor(p); },
    async getStoryStructure(p: number) { await delay(); return storyStructureFor(p); },
    async placeScene(p: number, sceneId: number, body: StoryStructurePlacementDTO) {
      await delay(120);
      const path = `/api/projects/${p}/story-structure/scenes/${sceneId}/placement`;
      const current = storyStructureFor(p);
      if (body.expected_revision !== current.revision) {
        throw new ApiRequestError(
          "PUT",
          path,
          409,
          "The story structure changed after it was loaded.",
          "structure_conflict",
        );
      }
      const projectScenes = scenesFor(p);
      const source = projectScenes.find((sceneRow) => sceneRow.id === sceneId);
      if (!source) throw new ApiRequestError("PUT", path, 404, `Scene ${sceneId} not found`, "not_found");
      const act = body.act.trim();
      const chapter = body.chapter.trim();
      const seriesProject = projects.find((project) => project.id === p)?.narrative_engine === "series";
      if (!seriesProject && body.episode_id != null) {
        throw new ApiRequestError("PUT", path, 400, "episode_id is only valid for Series projects.", "bad_request");
      }
      const updatesEpisode = Object.prototype.hasOwnProperty.call(body, "episode_id");
      const destinationEpisode = seriesProject
        ? updatesEpisode
          ? body.episode_id ?? null
          : episodeFor(p, sceneId)
        : null;
      if (seriesProject && destinationEpisode !== null && !MOCK_EPISODES.some((episode) => (
        episode.id === destinationEpisode && episode.project_id === p
      ))) {
        throw new ApiRequestError(
          "PUT",
          path,
          404,
          `Episode ${destinationEpisode} does not belong to this project.`,
          "not_found",
        );
      }
      const canonical = seriesProject
        ? [...projectScenes].sort((left, right) => left.sort_order - right.sort_order || left.id - right.id)
        : current.acts.flatMap((actRow) => actRow.chapters.flatMap((chapterRow) => (
            chapterRow.scenes.map((reference) => projectScenes.find((sceneRow) => sceneRow.id === reference.id)!)
          )));
      const sourceIndex = canonical.findIndex((sceneRow) => sceneRow.id === sceneId);
      canonical.splice(sourceIndex, 1);
      const siblings = canonical.filter((sceneRow) => (
        sceneRow.act.trim() === act && sceneRow.chapter.trim() === chapter
        && (!seriesProject || episodeFor(p, sceneRow.id) === destinationEpisode)
      ));
      const sameParent = source.act.trim() === act
        && source.chapter.trim() === chapter
        && (!seriesProject || episodeFor(p, source.id) === destinationEpisode);
      if (!siblings.length && !sameParent) {
        throw new ApiRequestError("PUT", path, 400, "The destination group no longer exists.", "bad_request");
      }
      if (!Number.isInteger(body.index) || body.index < 0 || body.index > siblings.length) {
        throw new ApiRequestError(
          "PUT",
          path,
          400,
          "The destination index is outside the destination group.",
          "bad_request",
        );
      }
      source.act = act;
      source.chapter = chapter;
      if (updatesEpisode) episodesFor(p).set(sceneId, destinationEpisode);
      let insertionIndex: number;
      if (siblings.length === 0) {
        insertionIndex = Math.max(0, Math.min(sourceIndex, canonical.length));
      } else if (body.index < siblings.length) {
        insertionIndex = canonical.indexOf(siblings[body.index]!);
      } else {
        insertionIndex = canonical.indexOf(siblings.at(-1)!) + 1;
      }
      canonical.splice(insertionIndex, 0, source);
      canonical.forEach((sceneRow, index) => {
        sceneRow.sort_order = index;
        sceneRow.revision = `mock-scene-${++MOCK_SCENE_REVISION}`;
      });
      projectScenes.splice(0, projectScenes.length, ...canonical);
      return storyStructureFor(p);
    },
    async executeStoryStructureCommand(p: number, body: StoryStructureCommandDTO) {
      await delay(120);
      return executeStructureCommand(p, body);
    },
    async updateScene(_p: number, sceneId: number, patch: Record<string, unknown>) {
      await delay(120);
      const path = `/api/projects/${_p}/scenes/${sceneId}`;
      const structuralFields = ["act", "chapter", "sort_order"]
        .filter((field) => Object.prototype.hasOwnProperty.call(patch, field))
        .sort();
      if (structuralFields.length > 0) {
        throw new ApiRequestError(
          "PATCH",
          path,
          400,
          `Scene PATCH cannot change structural field(s): ${structuralFields.join(", ")}. Use the revision-guarded story-structure placement or command endpoint.`,
          "bad_request",
        );
      }
      const projectScenes = scenesFor(_p);
      const s = projectScenes.find((x) => x.id === sceneId);
      if (!s) throw new ApiRequestError("PATCH", path, 404, `Scene ${sceneId} not found`, "not_found");
      const { expected_revision: expectedRevision, ...writePatch } = patch;
      if (expectedRevision && expectedRevision !== s.revision) {
        throw new ApiRequestError("PATCH", path, 409,
          "The scene changed after it was loaded.", "scene_conflict");
      }
      Object.assign(s, writePatch);
      const hasChronologyPatch = [
        "time_of_day",
        "location",
        "slugline",
        "estimated_duration_minutes",
        "performance_duration_minutes",
      ]
        .some((field) => Object.prototype.hasOwnProperty.call(writePatch, field));
      if (hasChronologyPatch) {
        const state = timelineStateFor(_p);
        const currentDetails = state.details.get(sceneId) ?? {
          time_of_day: "",
          location: "",
          slugline: "",
          estimated_duration_minutes: 0,
          performance_duration_minutes: 0,
          character_states: [],
        };
        state.details.set(sceneId, {
          time_of_day: Object.prototype.hasOwnProperty.call(writePatch, "time_of_day")
            ? String(writePatch.time_of_day ?? "")
            : currentDetails.time_of_day,
          location: Object.prototype.hasOwnProperty.call(writePatch, "location")
            ? String(writePatch.location ?? "")
            : currentDetails.location,
          slugline: Object.prototype.hasOwnProperty.call(writePatch, "slugline")
            ? String(writePatch.slugline ?? "")
            : currentDetails.slugline,
          estimated_duration_minutes: Object.prototype.hasOwnProperty.call(
            writePatch,
            "estimated_duration_minutes",
          )
            ? Number(writePatch.estimated_duration_minutes ?? 0)
            : currentDetails.estimated_duration_minutes,
          performance_duration_minutes: Object.prototype.hasOwnProperty.call(
            writePatch,
            "performance_duration_minutes",
          )
            ? Number(writePatch.performance_duration_minutes ?? 0)
            : currentDetails.performance_duration_minutes,
          character_states: currentDetails.character_states.map((stateRow) => ({ ...stateRow })),
        });
      }
      s.revision = `mock-scene-${++MOCK_SCENE_REVISION}`;
      return { ...s };
    },
    async createScene(_p: number, body: Record<string, unknown>) { await delay(140); const projectScenes = scenesFor(_p); const id = projectScenes.reduce((mx, s) => Math.max(mx, s.id), 0) + 1; const s = scene({ id, title: String((body.title as string) ?? "New Scene"), act: String((body.act as string) ?? ""), chapter: String((body.chapter as string) ?? ""), content: String((body.content as string) ?? ""), sort_order: projectScenes.length + 1, order_index: projectScenes.length + 1 }); projectScenes.push(s); return cloneScene(s); },
    async deleteScene(_p: number, sceneId: number) {
      await delay(120);
      const projectScenes = scenesFor(_p);
      const i = projectScenes.findIndex((x) => x.id === sceneId);
      if (i >= 0) projectScenes.splice(i, 1);
      episodesFor(_p).delete(sceneId);
      scrubTimelineScene(_p, sceneId);
      return { ok: true, deleted: sceneId };
    },
    async listLogosActions(_p: number, section?: string) {
      await delay(120);
      const defs: [string, string, string][] = [
        ["inline_rewrite", "Rewrite", "generative"], ["inline_expand", "Expand", "generative"],
        ["inline_compress", "Compress", "generative"], ["inline_improve_dialogue", "Improve Dialogue", "generative"],
        ["inline_improve_action", "Improve Action", "generative"], ["inline_make_visual", "Make More Visual", "generative"],
        ["inline_summarize", "Summarize", "diagnostic"], ["inline_suggest", "Suggest", "diagnostic"],
        ["inline_explain", "Explain", "diagnostic"], ["connect_to_psyke", "Connect to PSYKE", "diagnostic"],
      ];
      const noSel = new Set(["inline_suggest", "inline_explain", "connect_to_psyke"]);
      return defs.map(([name, label, category]) => ({
        name, label, description: `${label} the selection`, category, sections: [section || "Inline"],
        needs_selection: !noSel.has(name), deterministic: name === "connect_to_psyke",
        generative: category === "generative",
      }));
    },
    async runLogos(_p: number, body: Record<string, unknown>) {
      await delay(280);
      const action = String(body.action ?? "");
      const sel = String(body.selected_text ?? "").trim();
      if (action === "connect_to_psyke") {
        return { ok: true, action, title: "Connect to PSYKE", message: sel ? "Related PSYKE entries:\n- Marlow (character)\n- Vesper (character)" : "Select some text first.", suggestions: ["Marlow", "Vesper"], proposed_operations: [], generative: false, error: null };
      }
      const generative = /rewrite|expand|compress|improve|make_visual/.test(action);
      const message = generative ? (sel ? `${sel} — [mock ${action}]` : "Select text to transform.") : `[mock] ${action} — a short ${action.includes("summar") ? "summary" : "note"} for the passage.`;
      return { ok: true, action, title: action, message, suggestions: generative ? [] : ["A mock suggestion."], proposed_operations: [], generative, error: null };
    },
    async listLogosProactive(_p: number, section?: string) {
      await delay(180);
      const all = [
        { id: "s1", type: "character", title: "VESPER thinning out", message: "Vesper hasn't appeared in 4 scenes — re-thread her?", section_name: "Manuscript", evidence: "absent in SC.10–13", confidence: 0.78, severity: "warning", target_type: "psyke_entry", target_id: "2", suggested_actions: ["connect_to_psyke"] },
        { id: "s2", type: "pacing", title: "Echoing scenes", message: "SC.14 echoes SC.10 — tighten or cut?", section_name: "Manuscript", evidence: "similar beats", confidence: 0.66, severity: "info", target_type: "scene", target_id: "14", suggested_actions: ["inline_compress"] },
        { id: "s3", type: "psyke", title: "Unlinked cast", message: "MARLOW has no PSYKE bible entry.", section_name: "PSYKE", evidence: "1 of 5 unlinked", confidence: 0.71, severity: "info", target_type: "psyke_entry", target_id: "1", suggested_actions: [] },
      ];
      return section ? all.filter((s) => s.section_name === section) : all;
    },
    async listContinuity(_p: number, sceneId: number) { await delay(120); return (MOCK_CONTINUITY[sceneId] ?? []).map((m) => ({ ...m })); },
    async addContinuity(_p: number, sceneId: number, body: Record<string, unknown>) { await delay(140); const row = { id: 1000 + (MOCK_CONTINUITY[sceneId]?.length ?? 0), scene_id: sceneId, target: "", kind: "state", value: "", ...body }; (MOCK_CONTINUITY[sceneId] ??= []).push(row); return { ...row }; },
    async listGnContinuityItems() { await delay(120); return MOCK_GN_ITEMS.map((i) => ({ ...i })); },
    async createGnContinuityItem(_p: number, body: Record<string, unknown>) { await delay(140); const row = { id: 2000 + MOCK_GN_ITEMS.length, name: "", item_type: "prop", ...body }; MOCK_GN_ITEMS.push(row); return { ...row }; },
    async listGnContinuityAppearances(_p: number, itemId: number) { await delay(120); return MOCK_GN_APPEAR.filter((a) => a.continuity_item_id === itemId).map((a) => ({ ...a })); },
    async createGnContinuityAppearance(_p: number, itemId: number, body: Record<string, unknown>) { await delay(140); const row = { id: 3000 + MOCK_GN_APPEAR.length, continuity_item_id: itemId, ...body }; MOCK_GN_APPEAR.push(row); return { ...row }; },
    async getOutline() { await delay(); return OUTLINE; },
    async listPsyke() { await delay(); return PSYKE.map((e) => ({ ...e })); },
    async getPsykeConsoleSuggestions(_p: number, query: string, _sceneId?: number | null, _signal?: AbortSignal) {
      await delay(100);
      const q = query.trim().toLowerCase();
      if (!q) return [];
      if (q.startsWith("/")) {
        return ["/create", "/open", "/go", "/ai"]
          .filter((command) => command.startsWith(q))
          .map((command, index) => ({
            text: command,
            description: "PSYKE Console command",
            icon: "⌘",
            category: "command",
            score: 1 - index * 0.01,
            entry_id: 0,
          }));
      }
      return PSYKE
        .filter((entry) => [entry.name, ...entry.aliases, entry.notes].join(" ").toLowerCase().includes(q))
        .slice(0, 8)
        .map((entry, index) => ({
          text: entry.name,
          description: entry.type,
          icon: "ψ",
          category: "entity",
          score: 1 - index * 0.01,
          entry_id: entry.id,
        }));
    },
    async planPsykeConsoleCommand(_p: number, body: PsykeConsolePlanRequestDTO, signal?: AbortSignal) {
      await delay(120);
      if (signal?.aborted) throw signal.reason ?? new DOMException("Aborted", "AbortError");
      const projectScenes = scenesFor(_p);
      const input = body.command.trim();
      const parts = input.split(/\s+/);
      const command = (parts.shift() ?? "").replace(/^\//, "").toLowerCase();
      let plan: PsykeConsoleCommandPlanDTO & { entry_type?: string; entry_name?: string };
      const plan_id = `mock-plan-${commandPlanSequence++}`;
      const expires_at = new Date(Date.now() + 120_000).toISOString();
      if (command === "create") {
        const entry_type = (parts.shift() ?? "").toLowerCase();
        const entry_name = parts.join(" ").trim();
        if (!entry_type || !entry_name) throw new ApiRequestError("POST", "/psyke/console/plan", 400, "Usage: /create <type> <name>", "bad_request");
        const existing = PSYKE.find((entry) => entry.type.toLowerCase() === entry_type && entry.name.toLowerCase() === entry_name.toLowerCase());
        plan = existing ? {
          plan_id, command: "create", normalized_command: `/create ${entry_type} ${existing.name}`,
          action: "open_psyke_entry", summary: `Open existing ${entry_type} '${existing.name}'`,
          effects: ["No duplicate will be created.", `Open PSYKE entry #${existing.id} in this project.`],
          requires_confirmation: false, mutates: false, target_type: "psyke_entry", target_id: existing.id, expires_at,
        } : {
          plan_id, command: "create", normalized_command: `/create ${entry_type} ${entry_name}`,
          action: "create_psyke_entry", summary: `Create ${entry_type} '${entry_name}'`,
          effects: [`Add one ${entry_type} entry named '${entry_name}' to this project's PSYKE Bible.`, "Open the resulting entry after creation."],
          requires_confirmation: true, mutates: true, target_type: "psyke_entry", target_id: null, expires_at,
          entry_type, entry_name,
        };
      } else if (command === "open" && parts[0]?.toLowerCase() === "scene") {
        const target = projectScenes.find((scene) => scene.id === Number(parts[1]));
        if (!target) throw new ApiRequestError("POST", "/psyke/console/plan", 400, "Scene not found", "bad_request");
        plan = {
          plan_id, command: "open", normalized_command: `/open scene ${target.id}`,
          action: "open_scene", summary: `Open scene #${target.id} '${target.title}'`,
          effects: [`Open scene #${target.id}; project data will not change.`],
          requires_confirmation: false, mutates: false, target_type: "scene", target_id: target.id, expires_at,
        };
      } else if (command === "open" && parts[0]?.toLowerCase() === "psyke") {
        const name = parts.slice(1).join(" ").toLowerCase();
        const target = PSYKE.find((entry) => entry.name.toLowerCase() === name || entry.aliases.some((alias) => alias.toLowerCase() === name));
        if (!target) throw new ApiRequestError("POST", "/psyke/console/plan", 400, "PSYKE entry not found", "bad_request");
        plan = {
          plan_id, command: "open", normalized_command: `/open psyke ${target.name}`,
          action: "open_psyke_entry", summary: `Open PSYKE entry '${target.name}'`,
          effects: [`Open ${target.type} entry #${target.id}; project data will not change.`],
          requires_confirmation: false, mutates: false, target_type: "psyke_entry", target_id: target.id, expires_at,
        };
      } else if ((command === "go" || command === "goto") && parts[0]?.toLowerCase() === "scene") {
        const currentIndex = projectScenes.findIndex((scene) => scene.id === body.active_scene_id);
        const direction = parts[1]?.toLowerCase();
        const target = direction === "next" && currentIndex >= 0 ? projectScenes[currentIndex + 1]
          : (direction === "previous" || direction === "prev") && currentIndex > 0 ? projectScenes[currentIndex - 1]
            : projectScenes.find((scene) => scene.id === Number(direction));
        if (!target) throw new ApiRequestError("POST", "/psyke/console/plan", 400, "Scene target is unavailable", "bad_request");
        plan = {
          plan_id, command: "go", normalized_command: `/go scene ${direction}`,
          action: "open_scene", summary: `Open scene #${target.id} '${target.title}'`,
          effects: [`Open scene #${target.id}; project data will not change.`],
          requires_confirmation: false, mutates: false, target_type: "scene", target_id: target.id, expires_at,
        };
      } else {
        throw new ApiRequestError("POST", "/psyke/console/plan", 400, `/${command || "?"} is not available in the safe command pipeline yet.`, "bad_request");
      }
      commandPlans.set(plan.plan_id, plan);
      return { ...plan, effects: [...plan.effects] };
    },
    async executePsykeConsoleCommand(_p: number, body: { plan_id: string; confirmed: true }, _mutates: boolean): Promise<PsykeConsoleExecutionDTO> {
      await delay(180);
      const plan = commandPlans.get(body.plan_id);
      if (!plan) throw new ApiRequestError("POST", "/psyke/console/execute", 404, "Command plan was not found or has expired.", "not_found");
      commandPlans.delete(body.plan_id);
      if (plan.action === "create_psyke_entry") {
        const entry: PsykeEntryDTO = {
          id: Math.max(...PSYKE.map((candidate) => candidate.id)) + 1,
          name: plan.entry_name ?? "New Entry", type: plan.entry_type ?? "other",
          aliases: [], notes: "", is_global: false, details: {},
        };
        PSYKE.push(entry);
        return { ok: true, action: plan.action, message: `Created ${entry.type} '${entry.name}' and opened it in PSYKE.`, mutated: true, target_type: "psyke_entry", target_id: entry.id };
      }
      const target_id = plan.target_id;
      if (target_id == null) throw new ApiRequestError("POST", "/psyke/console/execute", 409, "Command target became stale", "stale_command_plan");
      return { ok: true, action: plan.action, message: plan.summary.replace(/^Open /, "Opened "), mutated: false, target_type: plan.target_type, target_id };
    },
    async listRelations() { await delay(); return RELATIONS.map((r) => ({ ...r })); },
    async listProgressions() { await delay(); return PROGRESSIONS.map((p) => ({ ...p })); },
    async getTimeline(p: number) {
      await delay();
      findMockProject(projects, p, "GET", `/api/projects/${p}/timeline`);
      return timelineSnapshotFrom(p);
    },
    async executeTimelineCommand(p: number, body: TimelineCommandDTO) {
      await delay(120);
      return executeTimelineCommand(p, body);
    },
    async getCanvasPlot(p: number) {
      await delay();
      findMockProject(projects, p, "GET", `/api/projects/${p}/canvas-plot`);
      return structuredClone(canvasFor(p));
    },
    async executeCanvasPlotCommand(p: number, body: CanvasPlotCommandDTO) {
      await delay(120);
      findMockProject(projects, p, "POST", `/api/projects/${p}/canvas-plot/commands`);
      return executeCanvasPlotCommand(p, body);
    },
    async getPlot() { await delay(); return PLOT.map((b) => ({ ...b })); },
    async getDashboard(p: number) {
      await delay();
      const projectScenes = scenesFor(p);
      const n = projectScenes.length;
      return {
        tension: {
          points: projectScenes.map((s, i) => ({ scene_id: s.id, scene_order: s.sort_order, scene_title: s.title, score: 30 + (i % 4) * 18, char_count: 1 + (i % 3), relation_pairs: i % 2, keyword_hits: i % 3, progression_count: i === n - 1 ? 1 : 0 })),
          flags: ["Flat section: scenes 3–5", "Weak buildup in first third"],
        },
        characters: PSYKE.filter((e) => e.type === "character").map((e) => ({ entry_id: e.id, name: e.name, present_scenes: [1, 5], total_scenes: n, flags: e.name === "THE WARDEN" ? ["Absent for 4 consecutive scenes"] : [] })),
        structure: { segments: [{ label: "ACT I", scene_count: 3, word_count: 140 }, { label: "ACT II", scene_count: 3, word_count: 260 }, { label: "ACT III", scene_count: 1, word_count: 60 }], total_scenes: n, total_words: 460, flags: [], inferred: false },
        themes: PSYKE.filter((e) => e.type === "theme").map((e, i) => ({ entry_id: e.id, name: e.name, present_scenes: [2], total_scenes: n, flags: ["Underused"], presence_source: i === 0 ? "controlling_idea" : "prose" })),
      };
    },
    async getContinuity(p: number) {
      await delay();
      return structuredClone(continuityReport(p));
    },
    async executeContinuityCommand(
      p: number,
      command: ContinuityCommandDTO,
      idempotencyKey: string,
    ): Promise<ContinuityCommandResultDTO> {
      const path = `/api/projects/${p}/continuity/commands`;
      await delay(120);
      findMockProject(projects, p, "POST", path);
      if (!/^[\x21-\x7e]{16,128}$/.test(idempotencyKey)) {
        throw new ApiRequestError("POST", path, 400, "Invalid Idempotency-Key", "bad_request");
      }
      const receiptKey = `${p}\u0000${idempotencyKey}`;
      const serializedCommand = JSON.stringify(command);
      const previous = continuityReceipts.get(receiptKey);
      if (previous) {
        if (previous.serializedCommand !== serializedCommand) {
          throw new ApiRequestError("POST", path, 409, "Idempotency-Key was already used for a different Continuity command", "idempotency_key_conflict");
        }
        return {
          continuity: structuredClone(continuityReport(p)),
          changed: false,
          affected_issue_id: previous.receipt.original_affected_issue_id,
          previous_status: "open",
          status: previous.receipt.status,
          replayed: true,
          applied_revision: previous.receipt.applied_revision,
        };
      }
      const current = continuityReport(p);
      if (command.expected_revision !== current.review_revision) {
        throw new ApiRequestError("POST", path, 409, "Continuity review state changed", "continuity_conflict");
      }
      const issue = current.issues.find((candidate) => candidate.id === command.issue_id);
      if (!issue || issue.status !== "open") {
        throw new ApiRequestError("POST", path, 404, "Open Continuity issue not found", "continuity_issue_not_found");
      }
      if (command.expected_issue_fingerprint !== issue.review_fingerprint) {
        throw new ApiRequestError("POST", path, 409, "Continuity issue changed", "continuity_conflict");
      }
      const status = command.kind === "defer_issue"
        ? "deferred" as const
        : command.kind === "dismiss_issue"
          ? "dismissed" as const
          : "resolved" as const;
      continuityStatusFor(p).set(command.issue_id, status);
      const next = continuityReport(p);
      const receipt: ContinuityCommandReceiptDTO = {
        project_id: p,
        request_digest: mockSha256(command),
        command_kind: command.kind,
        expected_revision: command.expected_revision,
        applied_revision: next.review_revision,
        original_changed: true,
        original_affected_issue_id: command.issue_id,
        expected_issue_fingerprint: command.expected_issue_fingerprint,
        previous_status: "open",
        status,
        committed_at: new Date().toISOString(),
      };
      continuityReceipts.set(receiptKey, { serializedCommand, receipt });
      return {
        continuity: structuredClone(next),
        changed: true,
        affected_issue_id: command.issue_id,
        previous_status: "open",
        status,
        replayed: false,
        applied_revision: next.review_revision,
      };
    },
    async getContinuityCommandReceipt(
      p: number,
      idempotencyKey: string,
      expectedCommand: ContinuityCommandDTO,
    ): Promise<ContinuityCommandReceiptDTO> {
      const path = `/api/projects/${p}/continuity/command-receipt`;
      await delay(80);
      findMockProject(projects, p, "GET", path);
      const saved = continuityReceipts.get(`${p}\u0000${idempotencyKey}`);
      if (!saved) {
        throw new ApiRequestError("GET", path, 404, "Continuity command receipt not found", "continuity_receipt_not_found");
      }
      if (saved.serializedCommand !== JSON.stringify(expectedCommand)) {
        throw new ApiRequestError("GET", path, 409, "Idempotency-Key was used for a different Continuity command", "idempotency_key_conflict");
      }
      return structuredClone(saved.receipt);
    },
    async getPacing() {
      await delay();
      return [
        { text: "THE WARDEN disappears for 4 scenes in a row (~40% of the story).", severity: 0.6, category: "disappearance" },
        { text: "4 consecutive scenes use the same character set (reads as repetitive).", severity: 0.5, category: "monotony" },
      ];
    },
    async getBalance() {
      await delay();
      const chars = PSYKE.filter((e) => e.type === "character");
      return {
        characters: chars.map((c, i) => ({ char_id: c.id, name: c.name, scene_count: [5, 3, 1][i] ?? 1, total_scenes: 7, flag: i === 0 ? "dominant" : i === 2 ? "underused" : "" })),
        arcs: [{ plotline: "MAIN · Marlow", scene_count: 3, acts_spanned: 3, flag: "" }, { plotline: "THREAT · Warden", scene_count: 1, acts_spanned: 1, flag: "thin" }],
        total_scenes: 7,
      };
    },
    async getStoryHealth() {
      await delay();
      return {
        structure: { label: "Partial", level: "sparse", score: 0.55 },
        characters: { label: "Balanced", level: "balanced", score: 0.72 },
        arcs: { label: "Partial", level: "sparse", score: 0.5 },
        density: { label: "Developed", level: "balanced", score: 0.66 },
      };
    },
    async getStructureAnalysis() {
      await delay();
      return {
        issues: [
          { issue_type: "weak_middle", category: "act_balance", severity: 0.6, message: "Middle section (Act II) is thin compared to outer acts.", suggestion: "Add subplots, reversals, or deeper conflict to the middle." },
          { issue_type: "flat_pacing", category: "tension_curve", severity: 0.5, message: "Tension is flat — scenes have similar intensity throughout.", suggestion: "Alternate high-tension and reflective scenes." },
          { issue_type: "missing_beats", category: "beat_placement", severity: 0.35, message: "Missing beats: All Is Lost, Finale.", suggestion: "Add a scene for All Is Lost to strengthen structure." },
        ],
        suggestions: ["Add subplots, reversals, or deeper conflict to the middle.", "Alternate high-tension and reflective scenes."],
      };
    },
    async getWorkflowTemplates(p: number) {
      await delay();
      const project = findMockProject(projects, p, "GET", `/api/projects/${p}/workflow-templates`);
      return MOCK_WORKFLOW_TEMPLATES
        .filter((template) => template.modes.length === 0 || template.modes.includes(project.narrative_engine))
        .map((template) => structuredClone(template));
    },
    async getWorkflowRecommendations(p: number) {
      await delay();
      const project = findMockProject(projects, p, "GET", `/api/projects/${p}/workflow-recommendations`);
      const unavailable = new Set(
        workflowsFor(p)
          .filter((run) => run.status === "active" || run.status === "paused" || run.status === "blocked")
          .map((run) => run.template_id),
      );
      const candidate = MOCK_WORKFLOW_TEMPLATES.find((template) => (
        !unavailable.has(template.id)
        && (template.modes.length === 0 || template.modes.includes(project.narrative_engine))
      ));
      return candidate ? [{
        template_id: candidate.id,
        title: candidate.title,
        reason: "The current project state has an unfinished next step this workflow can guide.",
        severity: "suggestion",
      }] : [];
    },
    async getWorkflows(p: number) {
      await delay();
      findMockProject(projects, p, "GET", `/api/projects/${p}/workflows`);
      return structuredClone(workflowsFor(p));
    },
    async getWorkflowRun(p: number, runId: number) {
      await delay();
      findMockProject(projects, p, "GET", `/api/projects/${p}/workflows/${runId}`);
      const run = workflowsFor(p).find((candidate) => candidate.id === runId);
      if (!run) {
        throw new ApiRequestError(
          "GET", `/api/projects/${p}/workflows/${runId}`, 404,
          "Workflow run not found", "not_found",
        );
      }
      return structuredClone(run);
    },
    async getWorkflowEvents(p: number, runId: number, limit = 40) {
      await delay();
      findMockProject(projects, p, "GET", `/api/projects/${p}/workflows/${runId}/events`);
      if (!workflowsFor(p).some((candidate) => candidate.id === runId)) {
        throw new ApiRequestError(
          "GET", `/api/projects/${p}/workflows/${runId}/events`, 404,
          "Workflow run not found", "not_found",
        );
      }
      const cap = Math.max(1, Math.min(200, Math.floor(limit) || 40));
      return structuredClone((workflowEvents.get(runId) ?? []).slice(-cap));
    },
    async executeWorkflowCommand(p: number, command: WorkflowCommandDTO, idempotencyKey: string) {
      await delay(120);
      const path = `/api/projects/${p}/workflows/commands`;
      const project = findMockProject(projects, p, "POST", path);
      if (!/^[\x21-\x7e]{16,128}$/.test(idempotencyKey)) {
        throw new ApiRequestError("POST", path, 400, "Idempotency-Key must contain 16 to 128 visible ASCII characters.", "bad_request");
      }
      const receiptKey = `${p}:${idempotencyKey}`;
      const serializedCommand = JSON.stringify(command);
      const replay = workflowReceipts.get(receiptKey);
      if (replay) {
        if (replay.serializedCommand !== serializedCommand) {
          throw new ApiRequestError("POST", path, 409, "This Idempotency-Key was already used for another workflow command.", "idempotency_key_conflict");
        }
        return { ...structuredClone(replay.result), changed: false, replayed: true };
      }

      let run: WorkflowRunDTO;
      let changed = true;
      let eventType = "";
      let eventMessage = "";
      let eventStepId: string | null = null;
      if (command.kind === "start_workflow") {
        const template = MOCK_WORKFLOW_TEMPLATES.find((candidate) => candidate.id === command.template_id);
        if (!template || (template.modes.length > 0 && !template.modes.includes(project.narrative_engine))) {
          throw new ApiRequestError("POST", path, 400, "Workflow template is unavailable for this writing mode.", "bad_request");
        }
        if (workflowsFor(p).some((candidate) => candidate.template_id === template.id
          && (candidate.status === "active" || candidate.status === "paused" || candidate.status === "blocked"))) {
          throw new ApiRequestError("POST", path, 409, "This workflow template already has an unfinished run.", "workflow_conflict");
        }
        run = createWorkflowRun(p, template, project.narrative_engine, command.title?.trim() || template.title);
      } else {
        const candidate = workflowsFor(p).find((item) => item.id === command.run_id);
        if (!candidate) {
          throw new ApiRequestError("POST", path, 404, "Workflow run not found.", "not_found");
        }
        if (candidate.revision !== command.expected_revision) {
          throw new ApiRequestError("POST", path, 409, "The workflow changed after it was loaded.", "workflow_conflict");
        }
        run = candidate;
        const timestamp = new Date().toISOString();
        if (command.kind === "complete_step" || command.kind === "skip_step") {
          const step = run.steps.find((item) => item.step_id === command.step_id);
          if (run.status !== "active" || !step || step.status !== "active" || run.current_step_id !== step.step_id) {
            throw new ApiRequestError("POST", path, 409, "Only the current active step can be changed.", "workflow_conflict");
          }
          step.status = command.kind === "complete_step" ? "completed" : "skipped";
          step.notes = command.notes?.trim() || step.notes;
          step.updated_at = timestamp;
          eventType = command.kind === "complete_step" ? "step_completed" : "step_skipped";
          eventMessage = `${command.kind === "complete_step" ? "Completed" : "Skipped"} step '${step.title}'.`;
          eventStepId = step.step_id;
          refreshWorkflowPointer(run, timestamp);
        } else if (command.kind === "advance") {
          if (run.status !== "active") {
            throw new ApiRequestError("POST", path, 409, "Only an active workflow can advance.", "workflow_conflict");
          }
          const currentIndex = run.steps.findIndex((step) => step.step_id === run.current_step_id && step.status === "active");
          if (currentIndex < 0) {
            throw new ApiRequestError("POST", path, 409, "The active workflow has no current step.", "workflow_conflict");
          }
          const current = run.steps[currentIndex]!;
          const next = run.steps.find((step, index) => index > currentIndex && step.status === "pending")
            ?? run.steps.find((step, index) => index < currentIndex && step.status === "pending");
          if (!next) {
            changed = false;
          } else {
            current.status = "pending";
            current.updated_at = timestamp;
            next.status = "active";
            next.updated_at = timestamp;
            run.current_step_id = next.step_id;
            eventType = "advanced";
            eventMessage = `Advanced to step '${next.title}'.`;
            eventStepId = next.step_id;
          }
        } else if (command.kind === "refresh") {
          if (run.status !== "active") {
            throw new ApiRequestError("POST", path, 409, "Only an active workflow can refresh checks.", "workflow_conflict");
          }
          const verifiable = run.steps.filter((step) => (
            step.kind === "check"
            && Boolean(step.completion_check)
            && step.status !== "completed"
            && step.status !== "skipped"
          ));
          if (verifiable.length === 0) {
            changed = false;
          } else {
            verifiable.forEach((step) => {
              step.status = "completed";
              step.updated_at = timestamp;
              addWorkflowEvent(p, run.id, "step_auto_completed", `Auto-completed verifiable step '${step.title}'.`, step.step_id);
            });
            refreshWorkflowPointer(run, timestamp);
            eventType = "refreshed";
            eventMessage = "Refreshed deterministic workflow checks.";
          }
        } else if (command.kind === "pause") {
          if (run.status !== "active") throw new ApiRequestError("POST", path, 409, "Only an active workflow can pause.", "workflow_conflict");
          run.status = "paused";
          eventType = "paused";
          eventMessage = "Workflow paused.";
        } else if (command.kind === "resume") {
          if (run.status !== "paused" && run.status !== "blocked") throw new ApiRequestError("POST", path, 409, "Only a paused or blocked workflow can resume.", "workflow_conflict");
          run.status = "active";
          eventType = "resumed";
          eventMessage = "Workflow resumed.";
        } else {
          if (run.status === "completed" || run.status === "cancelled") {
            throw new ApiRequestError("POST", path, 409, "The workflow is already terminal.", "workflow_conflict");
          }
          run.status = "cancelled";
          run.current_step_id = "";
          eventType = "cancelled";
          eventMessage = "Workflow cancelled.";
        }
        if (changed) {
          run.updated_at = timestamp;
          run.revision = workflowRevision(run);
          if (eventType) addWorkflowEvent(p, run.id, eventType, eventMessage, eventStepId);
          if (run.completed_at === timestamp) addWorkflowEvent(p, run.id, "completed", "Workflow completed.");
        }
      }

      const appliedRevision = run.revision;
      const result: WorkflowCommandResultDTO = {
        workflow: structuredClone(run), changed, replayed: false, applied_revision: appliedRevision,
      };
      const expectedRevision = command.kind === "start_workflow" ? "" : command.expected_revision;
      workflowReceipts.set(receiptKey, {
        serializedCommand,
        result: structuredClone(result),
        receipt: {
          project_id: p, request_digest: mockSha256(command), command_kind: command.kind,
          expected_revision: expectedRevision, applied_revision: appliedRevision,
          original_changed: changed, original_run_id: run.id, committed_at: new Date().toISOString(),
        },
      });
      return result;
    },
    async getWorkflowCommandReceipt(p: number, idempotencyKey: string, expectedCommand: WorkflowCommandDTO) {
      await delay();
      const path = `/api/projects/${p}/workflows/command-receipt`;
      findMockProject(projects, p, "GET", path);
      const stored = workflowReceipts.get(`${p}:${idempotencyKey}`);
      if (!stored) {
        throw new ApiRequestError("GET", path, 404, "No committed Guided Workflow command exists for this Idempotency-Key.", "workflow_receipt_not_found");
      }
      if (stored.serializedCommand !== JSON.stringify(expectedCommand)) {
        throw new ApiRequestError("GET", path, 409, "The receipt does not belong to the expected workflow command.", "idempotency_key_conflict");
      }
      return structuredClone(stored.receipt);
    },
    async getDecisionRadar(p: number) {
      await delay();
      return {
        project_id: p,
        generated_light: false,
        summary_line: "Decision radar: 1 blocking, 2 warning, 1 suggestion.",
        radar: [
          { id: "d1", category: "continuity", severity: "blocking", confidence: "confirmed", title: "Vesper's stance contradicts an earlier scene", explanation: "She withholds in Observation Ring but confessed earlier.", suggested_action: "Reconcile the confession order.", related_section: "Continuity", related_target_type: "scene", related_target_id: 12, related_target_key: "", created_from: "deterministic", graph_focus_key: "", graph_view_mode: null, graph_include_inferred: true, graph_depth: 1 as const, evidence: [], evidence_total: 0 },
          { id: "d2", category: "structure", severity: "warning", confidence: "likely", title: "Middle act is underdeveloped", explanation: "Act II is thin compared to the outer acts.", suggested_action: "Add complications or a subplot.", related_section: "Structure", related_target_type: "", related_target_id: null, related_target_key: "", created_from: "deterministic", graph_focus_key: "", graph_view_mode: null, graph_include_inferred: true, graph_depth: 1 as const, evidence: [], evidence_total: 0 },
          { id: "d3", category: "psyke", severity: "warning", confidence: "possible", title: "THE WARDEN has no progression", explanation: "Static arc — no scene-pinned states.", suggested_action: "Add progression milestones.", related_section: "PSYKE", related_target_type: "psyke", related_target_id: 3, related_target_key: "", created_from: "deterministic", graph_focus_key: "", graph_view_mode: null, graph_include_inferred: true, graph_depth: 1 as const, evidence: [], evidence_total: 0 },
          { id: "d4", category: "export", severity: "suggestion", confidence: "likely", title: "2 scenes missing slug lines", explanation: "Fountain export flagged missing slugs.", suggested_action: "Add scene headings.", related_section: "Export", related_target_type: "", related_target_id: null, related_target_key: "", created_from: "deterministic", graph_focus_key: "", graph_view_mode: null, graph_include_inferred: true, graph_depth: 1 as const, evidence: [], evidence_total: 0 },
        ],
        knowledge_graph_available: true,
        knowledge_graph_cards: [{
          id: "kg_theme_theme:psyke:6", category: "psyke", severity: "opportunity", confidence: "likely",
          title: "Theme 'Static' is not connected to any scene.", explanation: "The canonical graph has no scene edge for this theme.",
          suggested_action: "Tie the theme to the scenes that express it.", related_section: "PSYKE", related_target_type: "", related_target_id: null, related_target_key: "",
          created_from: "knowledge_graph", graph_focus_key: "theme:psyke:6", graph_view_mode: "project_map" as const,
          graph_include_inferred: true, graph_depth: 1 as const, evidence_total: 1,
          evidence: [{ kind: "node", label: "Static", detail: "theme source psyke:6.", graph_focus_key: "theme:psyke:6", source_key: "", target_key: "", edge_type: "", confidence: "confirmed", source_system: "psyke", provenance: "psyke:6", related_section: "", related_target_type: "", related_target_id: null, related_target_key: "" }],
        }],
        continuity_available: true,
        continuity_cards: [{
          id: "continuity_0123456789abcdef", category: "continuity", severity: "warning", confidence: "likely",
          title: "Location jump without transition", explanation: "The later scene has no travel cue.",
          suggested_action: "Add a transition or confirm the jump is intentional.", related_section: "Continuity",
          related_target_type: "continuity_issue", related_target_id: null, related_target_key: "0123456789abcdef",
          created_from: "semantic_continuity", graph_focus_key: "", graph_view_mode: null,
          graph_include_inferred: true, graph_depth: 1 as const, evidence_total: 2,
          evidence: [{ kind: "continuity_issue", label: "Location jump without transition", detail: "location jump · spatial", graph_focus_key: "", source_key: "", target_key: "", edge_type: "", confidence: "likely", source_system: "semantic_continuity", provenance: "continuity:location_jump", related_section: "Continuity", related_target_type: "continuity_issue", related_target_id: null, related_target_key: "0123456789abcdef" }, { kind: "scene", label: "Observation Ring", detail: "Scene #12 is explicitly related to this issue.", graph_focus_key: "", source_key: "", target_key: "", edge_type: "", confidence: "likely", source_system: "manuscript", provenance: "scene:12", related_section: "Manuscript", related_target_type: "scene", related_target_id: 12, related_target_key: "" }],
        }],
      };
    },
    async getAdapt() {
      await delay(120);
      return {
        mode: AI_BEHAVIOR.adaptive_override || "Structure",
        stage: "early",
        health: "balanced",
        description: "Shape the major turns before polishing individual scenes.",
        suggestions: [
          { text: "Clarify the Act II turn.", category: "structure" },
          { text: "Tie the black-box payoff to Vesper's choice.", category: "continuity" },
        ],
        override: AI_BEHAVIOR.adaptive_override,
      };
    },
    async getAiBehavior() {
      await delay(80);
      return { ...AI_BEHAVIOR, connector_disabled_actions: [...AI_BEHAVIOR.connector_disabled_actions] };
    },
    async patchAiBehavior(_p: number, body: Partial<typeof AI_BEHAVIOR>) {
      await delay(80);
      AI_BEHAVIOR = { ...AI_BEHAVIOR, ...body };
      return { ...AI_BEHAVIOR, connector_disabled_actions: [...AI_BEHAVIOR.connector_disabled_actions] };
    },
    async generateQuantumOutline(_p: number, body: { premise?: string }) {
      await delay(500);
      return {
        kind: "wavefunction",
        title: "Quantum outline · " + (body.premise || "untitled").slice(0, 40),
        body: "Generated 4 opening branches in superposition.",
        payload: {
          wavefunction_id: "wf_mock_1", anchor: body.premise || "",
          recommendation: { branch_id: "b2", title: "Deviation", probability: 0.42, reason: "Highest tension gain with consistent PSYKE state." },
          branches: [
            { id: "b1", title: "Intensification", description: "Marlow forces the confrontation now.", stakes: "high", consequence: "Vesper retreats further.", score: 7.4, probability: 0.31, branch_type: "escalate", is_pareto_optimal: true, factors: {} },
            { id: "b2", title: "Deviation", description: "A new signal pulls focus to the black box.", stakes: "medium", consequence: "The Warden's count pauses.", score: 8.1, probability: 0.42, branch_type: "swerve", is_pareto_optimal: true, factors: {} },
            { id: "b3", title: "Resolution", description: "Vesper finally confesses.", stakes: "high", consequence: "Static goes quiet.", score: 6.8, probability: 0.27, branch_type: "resolve", is_pareto_optimal: false, factors: {} },
          ],
        },
      };
    },
    async generateQuantumBranches(_p: number, body: { situation?: string }) {
      await delay(500);
      return {
        kind: "wavefunction",
        title: "Next moves · " + (body.situation || "").slice(0, 40),
        body: "Generated next-move branches.",
        payload: {
          wavefunction_id: "wf_mock_2", anchor: body.situation || "",
          branches: [
            { id: "n1", title: "Press", description: "Push the interrogation.", score: 7.0, probability: 0.5, factors: {} },
            { id: "n2", title: "Withdraw", description: "Let the silence work.", score: 6.5, probability: 0.5, factors: {} },
          ],
        },
      };
    },
    async getKnowledgeGraph(p: number, query: KnowledgeGraphQueryDTO = {}): Promise<KnowledgeGraphReadDTO> {
      await delay();
      const path = `/api/projects/${p}/knowledge-graph`;
      const project = findMockProject(projects, p, "GET", path);
      const includeInferred = query.include_inferred ?? true;
      const requestedViewMode = query.view_mode ?? "project_map";
      if (!KNOWLEDGE_GRAPH_VIEW_MODES.has(requestedViewMode as KnowledgeGraphViewMode)) {
        throw new ApiRequestError(
          "GET",
          path,
          422,
          "Invalid Knowledge Graph view mode",
          "validation_error",
        );
      }
      const viewMode = requestedViewMode as KnowledgeGraphViewMode;
      const storyDiagnosticsAvailable = viewMode === "project_map";
      const depth = Math.max(1, Math.min(2, query.depth ?? 1));
      const limit = Math.max(1, Math.min(200, query.limit ?? 100));
      const projectKey = `project:project:${p}`;
      const nodes: KnowledgeGraphNodeDTO[] = [{
        key: projectKey, node_type: "project", source_type: "project", source_id: String(p),
        label: project.title, summary: project.description, metadata: {}, degree: 0,
        story_gravity: null,
      }];
      const edges: KnowledgeGraphEdgeDTO[] = [];
      const orderedScenes = scenesFor(p);
      const storyOrderBand = (index: number): "beginning" | "middle" | "ending" => {
        const position = orderedScenes.length <= 1 ? 0 : index / (orderedScenes.length - 1);
        return position <= 0.34 ? "beginning" : position >= 0.67 ? "ending" : "middle";
      };
      for (const [sceneIndex, sceneRow] of orderedScenes.entries()) {
        const key = `scene:scene:${sceneRow.id}`;
        nodes.push({
          key, node_type: "scene", source_type: "scene", source_id: String(sceneRow.id),
          label: sceneRow.title, summary: sceneRow.summary, metadata: { act: sceneRow.act, chapter: sceneRow.chapter }, degree: 0,
          story_gravity: Math.min(1, 0.36 + sceneIndex * 0.18),
        });
        edges.push({
          source: projectKey, target: key, edge_type: "contains", confidence: "confirmed",
          provenance: "project structure", source_system: "structure", explanation: "The Scene belongs to this project.",
          is_user_confirmed: true, is_inferred: false, is_hidden: false, metadata: {},
        });
        const nextScene = orderedScenes[sceneIndex + 1];
        if (nextScene) {
          edges.push({
            source: key,
            target: `scene:scene:${nextScene.id}`,
            edge_type: "precedes",
            confidence: "likely",
            provenance: "scene order",
            source_system: "timeline",
            explanation: "Current manuscript order — sequential, not causal.",
            is_user_confirmed: false,
            is_inferred: true,
            is_hidden: false,
            metadata: {
              story_order_index: sceneIndex,
              story_order_total: orderedScenes.length,
              story_order_band: storyOrderBand(sceneIndex),
              act_boundary: Boolean(
                sceneRow.act
                && nextScene.act
                && sceneRow.act !== nextScene.act
              ),
            },
          });
        }
      }
      if (p === fixtureProjectId) {
        for (const entry of PSYKE) {
          const nodeType = entry.type === "location" ? "place" : entry.type;
          nodes.push({
            key: `${nodeType}:psyke:${entry.id}`, node_type: nodeType, source_type: "psyke",
            source_id: String(entry.id), label: entry.name, summary: entry.notes,
            metadata: { is_global: entry.is_global }, degree: 0,
            story_gravity: entry.type === "theme" ? 0.82 : entry.type === "character" ? 0.72 : 0.44,
          });
        }
        for (const relation of RELATIONS) {
          const sourceEntry = PSYKE.find((entry) => entry.id === relation.source_id);
          const targetEntry = PSYKE.find((entry) => entry.id === relation.target_id);
          if (!sourceEntry || !targetEntry) continue;
          const sourceType = sourceEntry.type === "location" ? "place" : sourceEntry.type;
          const targetType = targetEntry.type === "location" ? "place" : targetEntry.type;
          edges.push({
            source: `${sourceType}:psyke:${sourceEntry.id}`,
            target: `${targetType}:psyke:${targetEntry.id}`,
            edge_type: "relates_to", confidence: "confirmed", provenance: "explicit PSYKE relation",
            source_system: "psyke", explanation: relation.relation_type,
            is_user_confirmed: true, is_inferred: false, is_hidden: false, metadata: {},
          });
        }
        const firstScene = scenesFor(p)[0];
        const firstCharacter = PSYKE.find((entry) => entry.type === "character");
        if (firstScene && firstCharacter) {
          edges.push({
            source: `scene:scene:${firstScene.id}`, target: `character:psyke:${firstCharacter.id}`,
            edge_type: "mentions", confidence: "possible", provenance: "scene text match",
            source_system: "manuscript", explanation: "The name appears in the Scene text.",
            is_user_confirmed: false, is_inferred: true, is_hidden: false, metadata: {},
          });

          const revisionKey = "revision_impact:revision:1";
          nodes.push({
            key: revisionKey, node_type: "revision_impact", source_type: "revision",
            source_id: "1", label: "Saved impact report", summary: "A recorded revision risk.",
            metadata: { impact_level: "medium" }, degree: 0, story_gravity: null,
          });
          edges.push({
            source: revisionKey, target: `scene:scene:${firstScene.id}`,
            edge_type: "risks", confidence: "possible", provenance: "revision impact report",
            source_system: "revision_intelligence", explanation: "A saved impact report touches this Scene.",
            is_user_confirmed: false, is_inferred: true, is_hidden: false, metadata: {},
          });

          const applyKey = "controlled_apply_operation:apply:1";
          nodes.push({
            key: applyKey, node_type: "controlled_apply_operation", source_type: "apply",
            source_id: "1", label: "Pending apply", summary: "A recorded apply conflict.",
            metadata: { status: "previewed" }, degree: 0, story_gravity: null,
          });
          edges.push({
            source: applyKey, target: `scene:scene:${firstScene.id}`,
            edge_type: "contradicts", confidence: "likely", provenance: "controlled apply conflict",
            source_system: "controlled_apply", explanation: "A pending apply conflicts with this Scene.",
            is_user_confirmed: false, is_inferred: true, is_hidden: false, metadata: {},
          });
        }
      }

      const reviews = knowledgeGraphReviewFor(p);
      const reviewedEdges = edges.map((edge) => {
        const review = reviews.get(knowledgeGraphEdgeKey(edge));
        return review ? { ...edge, ...review } : edge;
      });
      const allNodeKeys = new Set(nodes.map((node) => node.key));
      const hiddenQueryEdges = reviewedEdges.filter((edge) => (
        edge.is_hidden && allNodeKeys.has(edge.source) && allNodeKeys.has(edge.target)
      ));
      const visibleEdges = reviewedEdges.filter((edge) => (
        !edge.is_hidden
        && (includeInferred || !edge.is_inferred)
        && allNodeKeys.has(edge.source)
        && allNodeKeys.has(edge.target)
      ));

      let projectedNodes = nodes;
      let projectedEdges = visibleEdges;
      if (viewMode === "structure") {
        const structuralNodeTypes = new Set([
          "project", "act", "chapter", "scene", "plot_block", "timeline_event",
        ]);
        const structuralEdgeTypes = new Set([
          "contains", "belongs_to", "precedes", "follows",
        ]);
        projectedNodes = nodes.filter((node) => structuralNodeTypes.has(node.node_type));
        const structuralKeys = new Set(projectedNodes.map((node) => node.key));
        projectedEdges = visibleEdges.filter((edge) => (
          structuralEdgeTypes.has(edge.edge_type)
          && structuralKeys.has(edge.source)
          && structuralKeys.has(edge.target)
        ));
      } else if (viewMode === "recorded_risk") {
        projectedEdges = visibleEdges.filter((edge) => (
          edge.edge_type === "risks" || edge.edge_type === "contradicts"
        ));
        const riskKeys = new Set(projectedEdges.flatMap((edge) => [edge.source, edge.target]));
        projectedNodes = nodes.filter((node) => riskKeys.has(node.key));
      } else if (viewMode === "revision_impact") {
        projectedEdges = visibleEdges.filter((edge) => (
          edge.source_system === "revision_intelligence"
          && (edge.edge_type === "revises" || edge.edge_type === "risks")
        ));
        const revisionKeys = new Set(projectedEdges.flatMap((edge) => [edge.source, edge.target]));
        projectedNodes = nodes.filter((node) => revisionKeys.has(node.key));
      }

      const fullDegree = new Map(projectedNodes.map((node) => [node.key, 0]));
      for (const edge of projectedEdges) {
        fullDegree.set(edge.source, (fullDegree.get(edge.source) ?? 0) + 1);
        fullDegree.set(edge.target, (fullDegree.get(edge.target) ?? 0) + 1);
      }
      const storyNodeTypes = new Set([
        "scene", "character", "place", "object", "lore", "theme", "motif",
        "psyke_entry", "note", "plot_block",
      ]);
      const canonicalOrphanKeys = new Set(storyDiagnosticsAvailable ? nodes.filter((node) => (
        storyNodeTypes.has(node.node_type)
        && !visibleEdges.some((edge) => {
          if (edge.source !== node.key && edge.target !== node.key) return false;
          const otherKey = edge.source === node.key ? edge.target : edge.source;
          const other = nodes.find((candidate) => candidate.key === otherKey);
          return !(other?.node_type === "project" && edge.edge_type === "contains");
        })
      )).map((node) => node.key) : []);
      let queryNodes = projectedNodes;
      let queryEdges = projectedEdges;
      const focusKey = query.focus_key ?? null;
      if (focusKey) {
        if (!projectedNodes.some((node) => node.key === focusKey)) {
          throw new ApiRequestError("GET", path, 404, "Knowledge Graph node not found", "not_found");
        }
        const visible = new Set([focusKey]);
        let frontier = new Set([focusKey]);
        const seenEdges = new Set<string>();
        const neighborhoodEdges: KnowledgeGraphEdgeDTO[] = [];
        for (let hop = 0; hop < depth; hop += 1) {
          const next = new Set<string>();
          for (const edge of projectedEdges) {
            if (!frontier.has(edge.source) && !frontier.has(edge.target)) continue;
            const edgeKey = `${edge.source}\u0000${edge.target}\u0000${edge.edge_type}`;
            if (!seenEdges.has(edgeKey)) {
              seenEdges.add(edgeKey);
              neighborhoodEdges.push(edge);
            }
            if (frontier.has(edge.source)) next.add(edge.target);
            if (frontier.has(edge.target)) next.add(edge.source);
          }
          for (const key of next) visible.add(key);
          frontier = next;
        }
        queryNodes = projectedNodes.filter((node) => visible.has(node.key));
        queryEdges = neighborhoodEdges;
      }
      queryNodes = queryNodes.map((node) => ({ ...node, degree: fullDegree.get(node.key) ?? 0 }));
      const orphanNodes = queryNodes.filter((node) => canonicalOrphanKeys.has(node.key));
      const rankNodes = (left: KnowledgeGraphNodeDTO, right: KnowledgeGraphNodeDTO) => (
        (focusKey && left.key === focusKey ? -1 : focusKey && right.key === focusKey ? 1 : 0)
        || right.degree - left.degree
        || left.node_type.localeCompare(right.node_type)
        || left.key.localeCompare(right.key)
      );
      let returnedNodes: KnowledgeGraphNodeDTO[];
      if (focusKey) {
        returnedNodes = [...queryNodes].sort(rankNodes).slice(0, limit);
      } else {
        const orphanBudget = orphanNodes.length === 0
          ? 0
          : Math.min(orphanNodes.length, 25, Math.max(1, Math.floor(limit / 4)));
        const reservedOrphans = [...orphanNodes].sort((left, right) => left.key.localeCompare(right.key)).slice(0, orphanBudget);
        const reservedKeys = new Set(reservedOrphans.map((node) => node.key));
        returnedNodes = [
          ...queryNodes.filter((node) => !reservedKeys.has(node.key)).sort(rankNodes).slice(0, Math.max(0, limit - orphanBudget)),
          ...reservedOrphans,
        ];
      }
      const returnedKeys = new Set(returnedNodes.map((node) => node.key));
      const returnedEdges = queryEdges.filter((edge) => returnedKeys.has(edge.source) && returnedKeys.has(edge.target)).slice(0, limit);
      const weakLinks = storyDiagnosticsAvailable
        ? queryEdges.filter((edge) => edge.is_inferred)
        : [];
      const returnedWeakLinks = weakLinks.filter((edge) => returnedKeys.has(edge.source) && returnedKeys.has(edge.target)).slice(0, Math.min(limit, 25));
      const returnedHiddenEdges = viewMode === "project_map"
        ? hiddenQueryEdges.filter((edge) => returnedKeys.has(edge.source) && returnedKeys.has(edge.target)).slice(0, Math.min(limit, 25))
        : [];
      const returnedOrphanKeys = orphanNodes.filter((node) => returnedKeys.has(node.key)).map((node) => node.key);
      return {
        project_id: p, revision: knowledgeGraphRevision(p), writing_mode: project.narrative_engine, focus_key: focusKey,
        depth, include_inferred: includeInferred, view_mode: viewMode,
        story_diagnostics_available: storyDiagnosticsAvailable,
        story_gravity_available: true,
        nodes: structuredClone(returnedNodes), edges: structuredClone(returnedEdges),
        node_count: queryNodes.length, edge_count: queryEdges.length,
        returned_node_count: returnedNodes.length, returned_edge_count: returnedEdges.length,
        truncated: returnedNodes.length < queryNodes.length
          || returnedEdges.length < queryEdges.length
          || returnedOrphanKeys.length < orphanNodes.length
          || returnedWeakLinks.length < weakLinks.length
          || (viewMode === "project_map" && returnedHiddenEdges.length < hiddenQueryEdges.length),
        orphan_keys: returnedOrphanKeys,
        orphan_count: orphanNodes.length,
        weak_links: structuredClone(returnedWeakLinks),
        weak_link_count: weakLinks.length,
        hidden_edges: structuredClone(returnedHiddenEdges),
        hidden_edge_count: hiddenQueryEdges.length,
        warnings: [], unavailable: ["revision_intelligence", "rewrite_sandbox"],
      };
    },
    async executeKnowledgeGraphCommand(
      p: number,
      command: KnowledgeGraphCommandDTO,
      idempotencyKey: string,
    ): Promise<KnowledgeGraphCommandResultDTO> {
      const path = `/api/projects/${p}/knowledge-graph/commands`;
      await delay();
      findMockProject(projects, p, "POST", path);
      if (!/^[\x21-\x7e]{16,128}$/.test(idempotencyKey)) {
        throw new ApiRequestError("POST", path, 400, "Invalid Idempotency-Key", "bad_request");
      }
      const receiptKey = `${p}\u0000${idempotencyKey}`;
      const serializedCommand = JSON.stringify(command);
      const previous = knowledgeGraphReceipts.get(receiptKey);
      if (previous) {
        if (previous.serializedCommand !== serializedCommand) {
          throw new ApiRequestError("POST", path, 409, "Idempotency-Key was already used for a different graph command", "idempotency_key_conflict");
        }
        return {
          knowledge_graph: await client.getKnowledgeGraph(p, { focus_key: null, depth: 1, limit: 100, include_inferred: true }),
          changed: false,
          affected_edge: structuredClone(previous.receipt.original_affected_edge),
          replayed: true,
          applied_revision: previous.receipt.applied_revision,
        };
      }

      const current = await client.getKnowledgeGraph(p, { focus_key: null, depth: 1, limit: 100, include_inferred: true });
      if (command.expected_revision !== current.revision) {
        throw new ApiRequestError("POST", path, 409, "Knowledge Graph review state changed", "knowledge_graph_conflict");
      }
      const identity = knowledgeGraphEdgeKey(command);
      const collection = command.kind === "unhide_edge" ? current.hidden_edges : current.edges;
      const edge = collection.find((candidate) => knowledgeGraphEdgeKey(candidate) === identity);
      if (!edge) {
        throw new ApiRequestError("POST", path, 404, "Knowledge Graph edge not found", "knowledge_graph_edge_not_found");
      }
      if (command.kind === "confirm_edge" && !edge.is_inferred) {
        throw new ApiRequestError("POST", path, 400, "Only inferred edges can be confirmed", "bad_request");
      }
      if (command.kind === "confirm_edge" && edge.is_user_confirmed) {
        throw new ApiRequestError("POST", path, 400, "That inferred edge is already confirmed", "bad_request");
      }
      if (command.kind === "hide_edge" && (!edge.is_inferred || edge.is_user_confirmed)) {
        throw new ApiRequestError("POST", path, 400, "Only visible, unconfirmed inferred edges can be hidden", "bad_request");
      }

      const reviews = knowledgeGraphReviewFor(p);
      const nextReview: MockKnowledgeGraphReview = {
        is_hidden: command.kind === "hide_edge" ? true : command.kind === "unhide_edge" ? false : edge.is_hidden,
        is_user_confirmed: command.kind === "confirm_edge" ? true : edge.is_user_confirmed,
      };
      const changed = nextReview.is_hidden !== edge.is_hidden
        || nextReview.is_user_confirmed !== edge.is_user_confirmed;
      if (changed) reviews.set(identity, nextReview);
      const knowledgeGraph = await client.getKnowledgeGraph(p, { focus_key: null, depth: 1, limit: 100, include_inferred: true });
      const appliedRevision = changed ? knowledgeGraph.revision : command.expected_revision;
      const affectedEdge = { source: command.source, target: command.target, edge_type: command.edge_type };
      const receipt: KnowledgeGraphCommandReceiptDTO = {
        project_id: p,
        request_digest: mockSha256(command),
        command_kind: command.kind,
        expected_revision: command.expected_revision,
        applied_revision: appliedRevision,
        original_changed: changed,
        original_affected_edge: affectedEdge,
        committed_at: new Date().toISOString(),
      };
      knowledgeGraphReceipts.set(receiptKey, { serializedCommand, receipt });
      return {
        knowledge_graph: knowledgeGraph,
        changed,
        affected_edge: affectedEdge,
        replayed: false,
        applied_revision: appliedRevision,
      };
    },
    async getKnowledgeGraphCommandReceipt(
      p: number,
      idempotencyKey: string,
      _expectedCommand: KnowledgeGraphCommandDTO,
    ): Promise<KnowledgeGraphCommandReceiptDTO> {
      const path = `/api/projects/${p}/knowledge-graph/command-receipt`;
      await delay(80);
      findMockProject(projects, p, "GET", path);
      const saved = knowledgeGraphReceipts.get(`${p}\u0000${idempotencyKey}`);
      if (!saved) {
        throw new ApiRequestError("GET", path, 404, "Knowledge Graph command receipt not found", "knowledge_graph_receipt_not_found");
      }
      return structuredClone(saved.receipt);
    },
    async getKnowledgeGraphHiddenEdges(p: number, offset = 0, limit = 25) {
      const path = `/api/projects/${p}/knowledge-graph/hidden-edges`;
      findMockProject(projects, p, "GET", path);
      const map = await client.getKnowledgeGraph(p, { focus_key: null, depth: 1, limit: 200, include_inferred: true });
      const edges = map.hidden_edges.slice(offset, offset + limit);
      const endpointKeys = new Set(edges.flatMap((edge) => [edge.source, edge.target]));
      return {
        project_id: p,
        revision: map.revision,
        offset,
        limit,
        hidden_edge_count: map.hidden_edge_count,
        returned_edge_count: edges.length,
        nodes: structuredClone(map.nodes.filter((node) => endpointKeys.has(node.key))),
        edges: structuredClone(edges),
      };
    },
    async getGraphGravity() {
      await delay();
      const chars = PSYKE.filter((e) => e.type === "character");
      const nodes = [
        ...chars.map((c, i) => ({ node_id: `PSYKE:${c.id}`, etype: "PSYKE", name: c.name, narrative: Math.max(0, 0.85 - i * 0.18), thematic: 0.2, structural: Math.max(0, 0.45 - i * 0.1), total: Math.max(0.1, 0.62 - i * 0.14) })),
        { node_id: "Scene:12", etype: "Scene", name: "Observation Ring", narrative: 0.7, thematic: 0.5, structural: 0.8, total: 0.66 },
        { node_id: "Act:1", etype: "Act", name: "ACT II", narrative: 0.1, thematic: 0.0, structural: 0.6, total: 0.17 },
      ].sort((a, b) => b.total - a.total);
      return { weights: { narrative: 0.45, thematic: 0.35, structural: 0.2 }, glow_threshold: 0.55, available: true, nodes };
    },
    async voiceStatus() {
      await delay(80);
      return { available: true, message: "Preview voice service", model_configured: true, device: "cpu" };
    },
    async voiceTranscribe() {
      await delay(180);
      return { text: "Preview transcription.", language: "en", error: "" };
    },
    async voiceTranscribeSegment(p: number) {
      await delay(220);
      const now = Date.now() / 1000;
      const entry: VoiceHistoryEntryDTO = {
        ...MOCK_VOICE_HISTORY[0]!, id: `voice-${++MOCK_VOICE_SEQ}`,
        project_id_at_capture: p, text: "Preview transcription.",
        original_text: "Preview transcription.", preview: "Preview transcription.",
        created_at: now, updated_at: now, status: "pending", committed_target: "",
        committed_at: null, sent_to_billy: false, billy_proposal_id: "", billy_state: "",
      };
      MOCK_VOICE_HISTORY.push(entry);
      return { ...entry };
    },
    async voiceHistory(p: number) {
      await delay(100);
      return { entries: MOCK_VOICE_HISTORY.filter((entry) => entry.project_id_at_capture === p).map((entry) => ({ ...entry })) };
    },
    async voiceIntents() {
      await delay(80);
      return { intents: [{ id: "cleanup_transcript", type: "cleanup", label: "Clean transcript", enabled: true, requires_ai: false, requires_confirmation: true, reason_if_disabled: "", target_type: "transcript" }] };
    },
    async voiceIntentPreview(p: number, body: { intent_id: string; source_text: string; source_segment_ids?: string[] }) {
      await delay(180);
      const id = `intent-${++MOCK_VOICE_SEQ}`;
      const after = body.source_text.replace(/\bcomma\b/gi, ",").replace(/\s+,/g, ",");
      const preview: VoiceIntentPreviewDTO = {
        id, intent_id: body.intent_id, intent_type: "cleanup_transcript", project_id: p,
        created_at: Date.now() / 1000, target_summary: "Clean the selected transcript",
        before_text: body.source_text, after_text: after, diff: null,
        created_note_preview: null, created_psyke_entry_preview: null,
        risk_level: "low", can_apply: true, reason_if_blocked: "",
        commit_target_id: "", gn_field: "", gn_ref: null,
        source_segment_ids: [...(body.source_segment_ids ?? [])],
      };
      MOCK_VOICE_INTENTS.set(id, preview);
      return { ...preview };
    },
    async voiceIntentApply(p: number, body: { preview_id: string }) {
      await delay(140);
      const preview = MOCK_VOICE_INTENTS.get(body.preview_id);
      if (!preview || preview.project_id !== p) return { applied: false, message: "Unknown intent preview." };
      for (const id of preview.source_segment_ids) {
        const entry = MOCK_VOICE_HISTORY.find((item) => item.id === id);
        if (entry?.project_id_at_capture === p) { entry.text = preview.after_text ?? entry.text; entry.status = "edited"; entry.updated_at = Date.now() / 1000; }
      }
      MOCK_VOICE_INTENTS.delete(body.preview_id);
      return { applied: true, message: "Cleanup applied.", cleaned_text: preview.after_text ?? "" };
    },
    async voiceIntentCancel(p: number, body: { preview_id: string }) {
      await delay(80);
      const preview = MOCK_VOICE_INTENTS.get(body.preview_id);
      const cancelled = Boolean(preview?.project_id === p && MOCK_VOICE_INTENTS.delete(body.preview_id));
      return { cancelled, message: cancelled ? "Intent preview dismissed." : "Unknown intent preview." };
    },
    async voiceBillyOps() {
      await delay(80);
      return { operations: [
        { id: "billy_ask", label: "Ask Billy", enabled: true, reason_if_disabled: "" },
        { id: "billy_continue_cursor", label: "Continue in scene", enabled: true, reason_if_disabled: "" },
      ] };
    },
    async voiceBillyGenerate(p: number, body: { operation: string; transcript_text: string; source_segment_ids?: string[] }) {
      await delay(240);
      const id = `billy-${++MOCK_VOICE_SEQ}`;
      const canApply = body.operation === "billy_continue_cursor";
      const proposal: VoiceBillyProposalDTO = {
        id, proposal_type: canApply ? "insert_at_cursor" : "chat_only",
        operation: body.operation, project_id: p, created_at: Date.now() / 1000,
        source_segment_ids: [...(body.source_segment_ids ?? [])], prompt_text: body.transcript_text,
        response_text: canApply ? "The station answers with a second, impossible heartbeat." : "The opening works best if the silence establishes the threat before exposition.",
        target_summary: canApply ? "Append to active scene" : "Billy response",
        before_text: null, after_text: canApply ? "The station answers with a second, impossible heartbeat." : null,
        diff: null, note_preview: null, psyke_preview: null, gn_ref: null, gn_field: "",
        can_apply: canApply, reason_if_blocked: canApply ? "" : "Nothing to apply.",
        applied: false, cancelled: false, applied_at: null,
      };
      MOCK_VOICE_BILLY.set(id, proposal);
      for (const entryId of proposal.source_segment_ids) {
        const entry = MOCK_VOICE_HISTORY.find((item) => item.id === entryId);
        if (entry?.project_id_at_capture === p) { entry.sent_to_billy = true; entry.billy_proposal_id = id; entry.billy_state = "proposed"; }
      }
      return { ...proposal };
    },
    async voiceBillyApply(p: number, body: { proposal_id: string }) {
      await delay(160);
      const proposal = MOCK_VOICE_BILLY.get(body.proposal_id);
      if (!proposal || proposal.project_id !== p) return { applied: false, message: "Unknown Billy proposal." };
      if (!proposal.can_apply) return { applied: false, message: "Nothing to apply." };
      MOCK_VOICE_BILLY.delete(body.proposal_id);
      return { applied: true, message: "Billy's edit applied.", inserted_text: proposal.after_text ?? "" };
    },
    async voiceBillyCancel(p: number, body: { proposal_id: string }) {
      await delay(80);
      const proposal = MOCK_VOICE_BILLY.get(body.proposal_id);
      const cancelled = Boolean(proposal?.project_id === p && MOCK_VOICE_BILLY.delete(body.proposal_id));
      if (cancelled) {
        for (const entryId of proposal?.source_segment_ids ?? []) {
          const entry = MOCK_VOICE_HISTORY.find((item) => item.id === entryId);
          if (entry?.project_id_at_capture === p && entry.billy_state === "proposed") entry.billy_state = "cancelled";
        }
      }
      return { cancelled, message: cancelled ? "Billy proposal dismissed." : "Unknown Billy proposal." };
    },
    async voiceCommitTargets() {
      await delay(80);
      return { targets: [
        { id: "active_cursor", label: "Active scene", mode: "all", enabled: true, target_type: "cursor", reason_if_disabled: "" },
        { id: "note", label: "New Note", mode: "all", enabled: true, target_type: "note", reason_if_disabled: "" },
      ] };
    },
    async voiceCommit(p: number, body: { text: string; target_id: string; source_segment_ids?: string[] }) {
      await delay(140);
      for (const entryId of body.source_segment_ids ?? []) {
        const entry = MOCK_VOICE_HISTORY.find((item) => item.id === entryId);
        if (entry?.project_id_at_capture === p) { entry.status = "committed"; entry.committed_target = body.target_id; entry.committed_at = Date.now() / 1000; }
      }
      return body.target_id === "active_cursor"
        ? { applied: true, message: "Committed to active scene.", inserted_text: body.text }
        : { applied: true, message: "Note created." };
    },
    async voiceCanUndo() {
      await delay(60);
      return { can_undo: false, reason: "Nothing to undo in preview." };
    },
    async voiceUndo() {
      await delay(80);
      return { undone: false, message: "Nothing to undo in preview." };
    },
    async assistantChat(_p: number, body: { message: string; selected_text?: string }) {
      await delay(500);
      return {
        reply: `The request is clear. I would sharpen ${body.selected_text ? `“${body.selected_text}”` : "this passage"} by making the character's immediate choice carry the tension, then let the next line reveal its cost.`,
        cached: false,
      };
    },
    async runCounterpart(_p: number, body: { mode?: string }) {
      await delay(500);
      return {
        reply: `[COUNTERPART · ${body.mode || "Feedback"}]\n\nThe scene leans on the static as a mood device, but the Warden's count is stated, not felt — it never lands as a threat. Vesper's competence reads as a wall, which is good; the reader just needs one crack in it. What does she lose if she finally names the Warden?`,
        cached: false,
      };
    },
    async listExtractionModels() {
      await delay(120);
      return { models: ["llama-3.2-8x3b-moe-dark-champion-18.4b", "davidau.l3.2-8x4b-moe-v2-dark-champion-21b", "qwen/qwen2.5-coder-32b", "qwen/qwen3.6-27b"], active: "llama-3.2-8x3b-moe-dark-champion-18.4b" };
    },
    async startExtract(p: number, useLlm = true) {
      await delay(300);
      const sc = scenesFor(p).slice(0, 4);
      const result = {
        project_id: p,
        used_llm: useLlm,
        scenes: sc.map((s, i) => ({
          scene_id: s.id,
          title: s.title,
          characters: i % 2 === 0 ? ["VESPER", "MARLOW"] : ["MARLOW", "THE WARDEN"],
          who_knows_what: useLlm
            ? i === 0 ? "Vesper knows the relay order was hers; Marlow does not."
              : i === 1 ? "Marlow suspects the Warden is counting heartbeats." : ""
            : "",
          relations: useLlm && i === 0
            ? [
                { source: "Vesper", target: "Marlow", rel_type: "subtext_opposition", why: "she deflects to keep her confession at arm's length", confidence: 0.72, source_status: "existing", target_status: "existing" },
                // a typo'd name carries an advisory near-dup hint (display-only)
                { source: "Marlowe", target: "Vesper", rel_type: "visual_motif", why: "the misspelled cue would mint a stray entry", confidence: 0.6, source_status: "new", source_hint: { existing_id: 1, existing_name: "MARLOW", score: 0.91 }, target_status: "existing" },
              ]
            : [],
        })),
        setup_payoffs: useLlm
          ? [{ source: "the relay order", target: "the Kessler crew's fate", rel_type: "supports_setup", why: "planted as Vesper's secret, pays off as her wound", confidence: 0.6 }]
          : [],
      };
      const jobId = `mockjob${++MOCK_EXTRACT_SEQ}`;
      MOCK_EXTRACT_JOBS[jobId] = { done: 0, total: 6, result };
      return { job_id: jobId, status: "running", done: 0, total: 6 };
    },
    async getExtractJob(_p: number, jobId: string) {
      await delay(350);
      const j = MOCK_EXTRACT_JOBS[jobId];
      if (!j) return { job_id: jobId, status: "error", done: 0, total: 0, error: "unknown job" };
      j.done = Math.min(j.total, j.done + 2);
      return j.done < j.total
        ? { job_id: jobId, status: "running", done: j.done, total: j.total }
        : { job_id: jobId, status: "done", done: j.total, total: j.total, result: j.result };
    },
    async cancelExtractJob(_p: number, jobId: string) {
      await delay(80);
      const job = MOCK_EXTRACT_JOBS[jobId];
      if (!job) return { job_id: jobId, status: "error", done: 0, total: 0, error: "unknown job" };
      delete MOCK_EXTRACT_JOBS[jobId];
      return { job_id: jobId, status: "cancelled", done: job.done, total: job.total };
    },
    async applyExtraction(_p: number, body: { scenes?: { scene_id?: number; characters?: string[]; who_knows_what?: string; relations?: unknown[] }[]; setup_payoffs?: unknown[] }) {
      await delay(500);
      const scenes = body?.scenes ?? [];
      const sp = body?.setup_payoffs ?? [];
      const names = new Set<string>();
      scenes.forEach((s) => (s.characters ?? []).forEach((c) => names.add(c.toLowerCase())));
      const links = scenes.reduce((n, s) => n + (s.characters?.length ?? 0), 0);
      const wkw = scenes.filter((s) => (s.who_knows_what ?? "").trim()).length;
      const rels = scenes.reduce((n, s) => n + (s.relations?.length ?? 0), 0) + sp.length;
      const receipt = {
        character_ids: Array.from(names, (_, i) => 900 + i),
        links: scenes.flatMap((s) => (s.characters ?? []).map((_, j) => [s.scene_id ?? 0, 900 + j])),
        wkw_scene_ids: scenes.filter((s) => (s.who_knows_what ?? "").trim()).map((s) => s.scene_id ?? 0),
        psyke_ids: [] as number[],
        relations: [] as unknown[],
      };
      return { characters_created: names.size, links_added: links, who_knows_what_set: wkw, psyke_created: rels, relations_added: rels, receipt };
    },
    async revertExtraction(_p: number, receipt: { character_ids?: number[]; links?: number[][]; wkw_scene_ids?: number[]; psyke_ids?: number[]; relations?: unknown[] }) {
      await delay(400);
      return {
        characters_created: (receipt.character_ids ?? []).length,
        links_added: (receipt.links ?? []).length,
        who_knows_what_set: (receipt.wkw_scene_ids ?? []).length,
        psyke_created: (receipt.psyke_ids ?? []).length,
        relations_added: (receipt.relations ?? []).length,
      };
    },
    // --- format-specific structured data (authoring) ---
    async listGnPages() { await delay(); return MOCK_GN_PAGES.slice(); },
    async syncGnFromScenes() { await delay(300); return { pages: MOCK_GN_PAGES.length, panels: 0, skipped: MOCK_GN_PAGES.length > 0 }; },
    async createGnPage(_p: number, b: Record<string, unknown>) { await delay(300); const row = { id: ++MOCK_FD_SEQ, page_number: (b.page_number as number) || MOCK_GN_PAGES.length + 1, summary: (b.summary as string) || "", reveal_type: (b.reveal_type as string) || "", splash_page: !!b.splash_page }; MOCK_GN_PAGES.push(row); return row; },
    async listGnPanels(_p: number, pageId: number) { await delay(); return MOCK_GN_PANELS.filter((x) => x.page_id === pageId); },
    async createGnPanel(_p: number, pageId: number, b: Record<string, unknown>) { await delay(300); const row = { id: ++MOCK_FD_SEQ, page_id: pageId, panel_number: (b.panel_number as number) || 0, description: (b.description as string) || "", visual_motifs: (b.visual_motifs as string[]) || [] }; MOCK_GN_PANELS.push(row); return row; },
    async listStageCues(_p: number, sceneId: number) { await delay(); return MOCK_STAGE_CUES.filter((x) => x.scene_id === sceneId); },
    async createStageCue(_p: number, sceneId: number, b: Record<string, unknown>) { await delay(300); const row = { id: ++MOCK_FD_SEQ, scene_id: sceneId, cue_type: (b.cue_type as string) || "other", cue_text: (b.cue_text as string) || "" }; MOCK_STAGE_CUES.push(row); return row; },
    async listStageEntrances(_p: number, sceneId: number) { await delay(); return MOCK_STAGE_ENTR.filter((x) => x.scene_id === sceneId); },
    async createStageEntrance(_p: number, sceneId: number, b: Record<string, unknown>) { await delay(300); const row = { id: ++MOCK_FD_SEQ, scene_id: sceneId, type: (b.type as string) || "entrance", character_id: (b.character_id as number) ?? null, cue_text: (b.cue_text as string) || "" }; MOCK_STAGE_ENTR.push(row); return row; },
    async syncStageFromScenes() { await delay(300); return { cues: MOCK_STAGE_CUES.length, entrances: MOCK_STAGE_ENTR.length, offstage: 0 }; },
    async listStageBusiness(_p: number, sceneId: number) { await delay(); return MOCK_STAGE_BIZ.filter((x) => x.scene_id === sceneId); },
    async createStageBusiness(_p: number, sceneId: number, b: Record<string, unknown>) { await delay(300); const row = { id: ++MOCK_FD_SEQ, scene_id: sceneId, prop_psyke_entry_id: (b.prop_psyke_entry_id as number) ?? null, character_id: (b.character_id as number) ?? null, stage_action: (b.stage_action as string) || "" }; MOCK_STAGE_BIZ.push(row); return row; },
    async listSeasons() { await delay(); return MOCK_SEASONS.slice(); },
    async createSeason(_p: number, b: Record<string, unknown>) { await delay(300); const row = { id: ++MOCK_FD_SEQ, season_number: (b.season_number as number) || MOCK_SEASONS.length + 1, title: (b.title as string) || "" }; MOCK_SEASONS.push(row); return row; },
    async listEpisodes(_p: number) { await delay(); return MOCK_EPISODES.filter((row) => row.project_id === _p); },
    async createEpisode(_p: number, seasonId: number, b: Record<string, unknown>) { await delay(300); const row = { id: ++MOCK_FD_SEQ, project_id: _p, season_id: seasonId, episode_number: (b.episode_number as number) || MOCK_EPISODES.filter((episode) => episode.project_id === _p).length + 1, title: (b.title as string) || "", logline: (b.logline as string) || "" }; MOCK_EPISODES.push(row); return row; },
    async listSeriesArcs() { await delay(); return MOCK_ARCS.slice(); },
    async createSeriesArc(_p: number, b: Record<string, unknown>) { await delay(300); const row = { id: ++MOCK_FD_SEQ, scope: (b.scope as string) || "series", title: (b.title as string) || "", setup_episode_id: (b.setup_episode_id as number) ?? null, payoff_episode_id: (b.payoff_episode_id as number) ?? null, status: (b.status as string) || "active" }; MOCK_ARCS.push(row); return row; },
    async listEpisodePlotlines(_p: number, episodeId: number) { await delay(); return MOCK_PLOTLINES.filter((x) => x.episode_id === episodeId); },
    async createEpisodePlotline(_p: number, episodeId: number, b: Record<string, unknown>) { await delay(300); const row = { id: ++MOCK_FD_SEQ, episode_id: episodeId, type: (b.type as string) || "A", title: (b.title as string) || "", resolution_state: "" }; MOCK_PLOTLINES.push(row); return row; },
    async getSeriesMemory(_p: number, entryId: number) { await delay(); return MOCK_SERIES_MEM[entryId] ?? { entry_id: entryId, continuity_flags: "", current_status_by_episode: {} }; },
    async setSeriesMemory(_p: number, entryId: number, b: Record<string, unknown>) { await delay(200); const row = { entry_id: entryId, continuity_flags: (b.continuity_flags as string) || "", current_status_by_episode: (b.current_status_by_episode as Record<string, string>) || {} }; MOCK_SERIES_MEM[entryId] = row; return row; },
    async getSettings(p: number) {
      await delay();
      findMockProject(projects, p, "GET", `/api/projects/${p}/settings`);
      return { settings: structuredClone(settingsFor(p)) };
    },
    async patchSettings(p: number, body: { settings?: Record<string, unknown> }) {
      await delay();
      findMockProject(projects, p, "PATCH", `/api/projects/${p}/settings`);
      const settings = {
        ...structuredClone(settingsFor(p)),
        ...structuredClone(body?.settings ?? {}),
      };
      settingsByProject.set(p, settings);
      return { settings: structuredClone(settings) };
    },
    async export(_p: number, req: ExportRequestDTO): Promise<ExportResponseDTO> {
      await delay();
      const projectScenes = scenesFor(_p);
      if (req.format === "json") {
        const payload = { export_type: req.export_type, project: "Null Horizon", scenes: projectScenes.map((s) => ({ id: s.id, title: s.title, act: s.act })), psyke: PSYKE.map((e) => ({ name: e.name, type: e.type })) };
        return { export_type: req.export_type, format: "json", payload, content: null, files: null };
      }
      if (req.format === "csv") {
        const content = "id,title,act\n" + projectScenes.map((s) => `${s.id},"${s.title}","${s.act}"`).join("\n");
        return { export_type: req.export_type, format: "csv", content, payload: null, files: null };
      }
      const content =
        `# Null Horizon\n\n_${req.export_type} · markdown_\n\n## Scenes (${projectScenes.length})\n` +
        projectScenes.map((s) => `- **${s.title}** — ${s.summary}`).join("\n") +
        `\n\n## PSYKE (${PSYKE.length})\n` + PSYKE.map((e) => `- ${e.name} (${e.type})`).join("\n");
      return { export_type: req.export_type, format: "markdown", content, payload: null, files: null };
    },
  } as unknown as ApiClient;
  return trackMockApiOperations(client);
}
