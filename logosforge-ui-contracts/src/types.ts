/**
 * Core DTO types — the stable data contract, mirrored 1:1 from the Python core's
 * `logosforge.api.schemas` (Pydantic). Field names stay stable across releases.
 * Frontends render these and never invent their own shapes.
 */

// ── Projects ───────────────────────────────────────────────────────────────
export interface ProjectDTO {
  id: number;
  title: string;
  description: string;
  /** = the writing mode (novel | screenplay | graphic_novel | stage_script | series). */
  narrative_engine: string;
  default_writing_format: string;
  format_mode: string;
}
export interface ProjectCreateDTO {
  title: string;
  description?: string;
  narrative_engine?: string;
  default_writing_format?: string;
}
export interface SettingsDTO {
  settings: Record<string, unknown>;
}

// ── Writing modes ──────────────────────────────────────────────────────────
export interface WritingModeDTO {
  id: string;
  label: string;
  structural_units: string[];
  default_writing_format: string;
  medium_constraints: string;
}
export interface WritingModesResponseDTO {
  modes: WritingModeDTO[];
  default_mode: string;
}

// ── Scenes (the primary writing unit) ──────────────────────────────────────
export interface SceneDTO {
  id: number;
  title: string;
  summary: string;
  synopsis: string;
  goal: string;
  conflict: string;
  outcome: string;
  beat: string;
  act: string;
  chapter: string;
  plotline: string;
  color_label: string;
  tags: string[];
  content: string;
  sort_order: number;
  order_index: number;
  character_ids: number[];
  place_ids: number[];
  who_knows_what: string;
}
export interface SceneCreateDTO {
  title: string;
  summary?: string;
  synopsis?: string;
  goal?: string;
  conflict?: string;
  outcome?: string;
  beat?: string;
  act?: string;
  chapter?: string;
  plotline?: string;
  content?: string;
  tags?: string[];
  character_ids?: number[];
  place_ids?: number[];
}
/** Partial — only provided fields change. */
export interface SceneUpdateDTO {
  title?: string;
  summary?: string;
  synopsis?: string;
  goal?: string;
  conflict?: string;
  outcome?: string;
  beat?: string;
  act?: string;
  chapter?: string;
  plotline?: string;
  color_label?: string;
  content?: string;
  tags?: string[];
  sort_order?: number;
  time_of_day?: string;
  location?: string;
  estimated_duration_minutes?: number;
  /** screenplay — feeds the graph "knowledge" edge; stage — "offstage" edge. */
  who_knows_what?: string;
  offstage_events?: string;
}

/** A continuity note pinned to a scene (memory_type "continuity_<kind>"). */
/** Consecutive scenes sharing the same (target, kind) form a graph "continuity" edge. */
export interface ContinuityMemoryDTO {
  id?: number;
  scene_id?: number;
  target: string;
  value?: string;
  kind?: string;
}

// ── Outline (nested nodes) ─────────────────────────────────────────────────
export interface OutlineNodeDTO {
  id: number;
  parent_id: number | null;
  title: string;
  description: string;
  sort_order: number;
  children: OutlineNodeDTO[];
}
export interface OutlineNodeCreateDTO {
  title: string;
  description?: string;
  parent_id?: number | null;
  sort_order?: number;
}
export interface OutlineNodeUpdateDTO {
  title?: string;
  description?: string;
  sort_order?: number;
}

// ── Plot (plot-lane blocks) ────────────────────────────────────────────────
export interface PlotSceneDTO {
  scene_id: number | null;
  title: string;
  act: string;
  summary: string;
  beat: string;
  color_label: string;
  order_index: number;
}
export interface PlotBlockDTO {
  /** the plotline name (URL-safe stable id). */
  id: string;
  plotline: string;
  scenes: PlotSceneDTO[];
}
export interface PlotBlockUpdateDTO {
  plotline?: string;
  color_label?: string;
}

// ── Timeline (scene-derived events) ────────────────────────────────────────
export interface TimelineCharacterStateDTO {
  character: string;
  state: string;
}
export interface TimelineEventDTO {
  /** scene id (timeline events are scene-derived). */
  id: number;
  order_index: number;
  title: string;
  act: string;
  chapter: string;
  time_of_day: string;
  location: string;
  duration_minutes: number;
  character_states: TimelineCharacterStateDTO[];
}
export interface TimelineEventCreateDTO {
  title: string;
  act?: string;
  chapter?: string;
  time_of_day?: string;
  location?: string;
  duration_minutes?: number;
}
export interface TimelineEventUpdateDTO {
  title?: string;
  act?: string;
  chapter?: string;
  time_of_day?: string;
  location?: string;
  duration_minutes?: number;
  sort_order?: number;
}

// ── PSYKE (the story bible) ────────────────────────────────────────────────
export interface PsykeEntryDTO {
  id: number;
  name: string;
  /** character | place | object | lore | theme | other */
  type: string;
  aliases: string[];
  notes: string;
  is_global: boolean;
  /** per-type structured fields (schema varies by `type`). */
  details: Record<string, unknown>;
}
export interface PsykeEntryCreateDTO {
  name: string;
  type?: string;
  aliases?: string[];
  notes?: string;
  is_global?: boolean;
  details?: Record<string, unknown> | null;
}
export interface PsykeEntryUpdateDTO {
  name?: string;
  type?: string;
  aliases?: string[];
  notes?: string;
  is_global?: boolean;
  details?: Record<string, unknown> | null;
}
export interface PsykeRelationDTO {
  /** synthetic "{source_id}:{target_id}". */
  id: string;
  source_id: number;
  target_id: number;
  source: string;
  target: string;
  relation_type: string;
}
export interface PsykeRelationCreateDTO {
  source_id: number;
  target_id: number;
  relation_type?: string;
}
export interface PsykeProgressionDTO {
  id: number;
  entry_id: number;
  text: string;
  scene_id: number | null;
  scene_title: string;
  sort_order: number;
}
export interface PsykeProgressionCreateDTO {
  entry_id: number;
  text: string;
  scene_id?: number | null;
}

// ── Notes ──────────────────────────────────────────────────────────────────
export interface NoteDTO {
  id: number;
  title: string;
  content: string;
  tags: string[];
  pinned: boolean;
  psyke_links: number[];
  scene_links: number[];
}
export interface NoteCreateDTO {
  title: string;
  content?: string;
  tags?: string[];
  pinned?: boolean;
}
export interface NoteUpdateDTO {
  title?: string;
  content?: string;
  tags?: string[];
  pinned?: boolean;
}

// ── Characters (manuscript cast + the stable PSYKE bible link) ──────────────
export interface CharacterDTO {
  id: number;
  name: string;
  description: string;
  color: string;
  /** Stable link to this character's PSYKE 'character' bible entry (null = unlinked). */
  psyke_entry_id: number | null;
}
export interface CharacterUpdateDTO {
  name?: string;
  description?: string;
  /** An explicit null clears the link. */
  psyke_entry_id?: number | null;
}

/** The scenes a theme (PSYKE 'theme' entry) is structurally tagged in. */
export interface ThemeScenesDTO {
  entry_id: number;
  scene_ids: number[];
}
/** PUT body — the full replacement set of scenes for the theme. */
export interface ThemeScenesUpdateDTO {
  scene_ids: number[];
}

// ── Assistant / Connector ──────────────────────────────────────────────────
export interface ChatMessageDTO {
  role: string;
  content: string;
}
export interface AssistantRequestDTO {
  message: string;
  history?: ChatMessageDTO[];
  system_prompt?: string;
  /** Optional: the scene the writer has open, for that scene's context. */
  active_scene_id?: number | null;
  /** Optional inline-editor context, folded into the core's chat grounding. */
  selected_text?: string;
  nearby_text?: string;
  document_title?: string;
}
export interface AssistantResponseDTO {
  reply: string;
  cached: boolean;
}
export interface AssistantActionRequestDTO {
  action: string;
  args?: Record<string, unknown>;
}
export interface AssistantSettingsDTO {
  provider: string;
  model: string;
  base_url: string;
  /** write-only; never returned by the API. */
  api_key?: string | null;
  timeout: number;
}

// -- Logos (inline / contextual assistant) — mirrors logosforge.logos over HTTP --
export interface LogosActionDTO {
  name: string;
  label: string;
  description: string;
  /** "diagnostic" | "generative" */
  category: string;
  sections: string[];
  needs_selection: boolean;
  deterministic: boolean;
  /** generative actions propose new prose a UI may apply; diagnostic ones only report. */
  generative: boolean;
}
export interface LogosRunRequestDTO {
  action: string;
  section?: string;
  selected_text?: string;
  nearby_context?: string;
  writing_mode?: string;
  current_scene_id?: number | null;
  // Optional non-manuscript node context from a cross-panel selection.
  current_outline_node_id?: number | null;
  current_psyke_entry_id?: number | null;
  current_timeline_event_id?: number | null;
  current_plot_block_id?: string;
  current_graph_node_id?: string;
}
export interface LogosResultDTO {
  ok: boolean;
  action: string;
  title: string;
  message: string;
  suggestions: string[];
  proposed_operations: Record<string, unknown>[];
  generative: boolean;
  error?: string | null;
}
export interface LogosSuggestionDTO {
  id: string;
  type: string;
  title: string;
  message: string;
  section_name: string;
  evidence: string;
  confidence: number;
  /** "info" | "warning" | "important" */
  severity: string;
  target_type: string;
  target_id: string;
  suggested_actions: string[];
}

export interface ConnectorActionParamDTO {
  name: string;
  param_type: string;
  required: boolean;
  default: unknown;
}
export interface ConnectorActionDTO {
  name: string;
  description: string;
  category: string;
  params: ConnectorActionParamDTO[];
}
export interface ConnectorExecuteDTO {
  action: string;
  args?: Record<string, unknown>;
}
export interface ConnectorResultDTO {
  ok: boolean;
  action: string;
  result: unknown;
  error: string;
}

// ── Export ─────────────────────────────────────────────────────────────────
export interface ExportRequestDTO {
  /** Data: story_elements | psyke_data | full_project. Manuscript/screenplay:
   *  manuscript | screenplay | screenplay_fountain | production_fountain (text),
   *  screenplay_pdf | screenplay_docx | manuscript_docx (binary, base64), screenplay_fdx (XML). */
  export_type: string;
  /** For the DATA export_types: json | markdown | csv. The manuscript/screenplay
   *  export_types carry their own native format (text/fountain/pdf/docx/fdx) in the response. */
  format: string;
  include_outline?: boolean | null;
  include_plot?: boolean | null;
  include_timeline?: boolean | null;
  include_scenes?: boolean | null;
  include_psyke_entries?: boolean | null;
  include_psyke_relations?: boolean | null;
  include_psyke_progressions?: boolean | null;
  include_notes?: boolean | null;
  include_project_metadata?: boolean | null;
  include_ids?: boolean | null;
  include_internal_metadata?: boolean | null;
  summaries_only?: boolean | null;
}
export interface ExportResponseDTO {
  export_type: string;
  format: string;
  payload?: unknown;
  content?: string | null;
  files?: Record<string, string> | null;
  /** For binary exports (PDF/DOCX): base64-encoded file bytes the client decodes + saves. */
  content_base64?: string | null;
  filename?: string | null;
  mime_type?: string | null;
}

// ── Narrative dashboard (derived, read-only analytics) ──────────────────────
export interface SceneTensionDTO {
  scene_id: number;
  scene_order: number;
  scene_title: string;
  /** 0–100 composite (chars + relations + keyword hits + progressions). */
  score: number;
  char_count: number;
  relation_pairs: number;
  keyword_hits: number;
  progression_count: number;
}
export interface TensionCurveDTO {
  points: SceneTensionDTO[];
  flags: string[];
}
export interface CharacterPresenceDTO {
  entry_id: number;
  name: string;
  /** scene sort_orders the character appears in. */
  present_scenes: number[];
  total_scenes: number;
  flags: string[];
}
export interface ThemePresenceDTO {
  entry_id: number;
  name: string;
  present_scenes: number[];
  total_scenes: number;
  flags: string[];
  /** "prose" = presence inferred from name/alias mentions (heuristic); */
  /** "controlling_idea" = at least partly from CI scene alignment (structural). */
  presence_source: string;
}
export interface ActSegmentDTO {
  label: string;
  scene_count: number;
  word_count: number;
}
export interface StructureDistributionDTO {
  segments: ActSegmentDTO[];
  total_scenes: number;
  total_words: number;
  flags: string[];
  /** true when acts were inferred by word-count (no explicit Act labels). */
  inferred: boolean;
}
export interface NarrativeDashboardDTO {
  tension: TensionCurveDTO;
  characters: CharacterPresenceDTO[];
  structure: StructureDistributionDTO;
  themes: ThemePresenceDTO[];
}

// ── Continuity / pacing / balance / story health (derived, read-only) ───────
export interface ContinuityIssueDTO {
  /** stable issue_key. */
  id: string;
  issue_type: string;
  dimension: string;
  /** info | suggestion | warning | blocking */
  severity: string;
  /** confirmed | likely | possible | unknown */
  confidence: string;
  title: string;
  explanation: string;
  suggested_action: string;
  related_scene_ids: number[];
  /** open | dismissed | resolved | deferred */
  status: string;
}
export interface ContinuityReportDTO {
  writing_mode: string;
  issues: ContinuityIssueDTO[];
  blocking_count: number;
  warning_count: number;
  /** dimensions that are unavailable / deferred for this writing mode. */
  unavailable: string[];
}
export interface PacingInsightDTO {
  text: string;
  /** 0–1, higher = more important. */
  severity: number;
  /** disappearance | monotony | stagnation | neglect | clustering */
  category: string;
}
export interface CharacterBalanceDTO {
  char_id: number;
  name: string;
  scene_count: number;
  total_scenes: number;
  /** dominant | underused | "" */
  flag: string;
}
export interface ArcBalanceDTO {
  plotline: string;
  scene_count: number;
  acts_spanned: number;
  /** thin | "" */
  flag: string;
}
export interface BalanceDataDTO {
  characters: CharacterBalanceDTO[];
  arcs: ArcBalanceDTO[];
  total_scenes: number;
}
export interface HealthSignalDTO {
  label: string;
  /** balanced | sparse | problematic */
  level: string;
  /** 0–1 */
  score: number;
}
export interface StoryHealthDTO {
  structure: HealthSignalDTO;
  characters: HealthSignalDTO;
  arcs: HealthSignalDTO;
  density: HealthSignalDTO;
}
export interface StructuralIssueDTO {
  issue_type: string;
  category: string;
  /** 0–1 */
  severity: number;
  message: string;
  suggestion: string;
}
export interface StructuralAnalysisDTO {
  issues: StructuralIssueDTO[];
  suggestions: string[];
}
export interface WorkflowStepDTO {
  step_id: string;
  title: string;
  /** pending | active | completed | skipped */
  status: string;
  sort_index: number;
  section_name: string;
  action_id: string;
}
export interface WorkflowRunDTO {
  id: number;
  title: string;
  /** active | paused | completed | cancelled */
  status: string;
  writing_mode: string;
  template_id: string;
  current_step_id: string;
  total_steps: number;
  completed_steps: number;
  steps: WorkflowStepDTO[];
}

// ── Decision radar (project intelligence) + Quantum outliner (generative) ────
export interface DecisionCardDTO {
  id: string;
  /** structure | psyke | continuity | rewrite | apply | export | production | graph | notes | writing_mode */
  category: string;
  /** blocking | warning | suggestion | opportunity | info */
  severity: string;
  /** confirmed | likely | possible | unknown */
  confidence: string;
  title: string;
  explanation: string;
  suggested_action: string;
  related_section: string;
  related_target_type: string;
  related_target_id: number | null;
  created_from: string;
}
export interface DecisionRadarDTO {
  project_id: number;
  generated_light: boolean;
  summary_line: string;
  radar: DecisionCardDTO[];
}
export interface QuantumResultDTO {
  kind: string;
  title: string;
  body: string;
  /** wavefunction summary: branches, recommendation, anchor, … */
  payload: Record<string, unknown>;
}
export interface QuantumOutlineRequestDTO {
  premise: string;
  n?: number;
  source_scene_id?: number | null;
  structure_mode?: string | null;
}
export interface QuantumBranchesRequestDTO {
  situation: string;
  n?: number;
  extra_context?: string;
  source_scene_id?: number | null;
  structure_mode?: string | null;
}

// ── Story gravity (graph node weights) + Counterpart (reflective AI) ─────────
export interface StoryGravityNodeDTO {
  /** "etype:entity_id", e.g. "Character:5" */
  node_id: string;
  etype: string;
  name: string;
  narrative: number;
  thematic: number;
  structural: number;
  total: number;
}
export interface GravityWeightsDTO {
  narrative: number;
  thematic: number;
  structural: number;
}
export interface GraphGravityDTO {
  weights: GravityWeightsDTO;
  glow_threshold: number;
  /** false when the graph-data builder is unavailable (Qt-less server). */
  available: boolean;
  nodes: StoryGravityNodeDTO[];
}
export interface CounterpartRequestDTO {
  /** Feedback | Critique | Interpret | Ask Back | Compare */
  mode?: string;
  scene_context?: string;
  outline_context?: string;
  story_memory_context?: string;
  psyke_context?: string;
  graph_context?: string;
  user_note?: string;
  custom_prompt?: string;
}

// --- Manuscript -> structured-data extraction (AI-assisted; propose -> apply) ---
/** Advisory: an existing PSYKE entry a proposed name closely resembles (likely a */
/** typo). Display-only — the review UI surfaces it; apply never auto-merges. */
export interface NearDupHintDTO {
  existing_id: number;
  existing_name: string;
  score: number;
}
export interface RelationProposalDTO {
  source: string;
  target: string;
  /** supports_setup | payoff | subtext_opposition | visual_motif */
  rel_type: string;
  why?: string;
  confidence?: number;
  /** Advisory, display-only (apply ignores these): "existing" (reuses an entry) | */
  /** "new" (creates one) | "" (unknown), plus an optional near-dup typo hint. */
  source_status?: string;
  target_status?: string;
  source_hint?: NearDupHintDTO | null;
  target_hint?: NearDupHintDTO | null;
}
export interface SceneExtractionDTO {
  scene_id: number;
  title?: string;
  /** Tier 1 — deterministic character cues. */
  characters: string[];
  /** Tier 2 — LLM. */
  who_knows_what?: string;
  relations: RelationProposalDTO[];
}
export interface ExtractionResultDTO {
  project_id: number;
  used_llm: boolean;
  scenes: SceneExtractionDTO[];
  setup_payoffs: RelationProposalDTO[];
}
export interface ExtractionApplyRequestDTO {
  scenes: SceneExtractionDTO[];
  setup_payoffs: RelationProposalDTO[];
}
export interface RelationRefDTO {
  source_id: number;
  target_id: number;
  rel_type: string;
}
export interface ExtractionReceiptDTO {
  character_ids: number[];
  /** [[scene_id, character_id], ...] */
  links: number[][];
  wkw_scene_ids: number[];
  psyke_ids: number[];
  relations: RelationRefDTO[];
}
export interface ExtractionApplyReportDTO {
  characters_created: number;
  links_added: number;
  who_knows_what_set: number;
  psyke_created: number;
  relations_added: number;
  /** Provenance — pass back to POST /extract/revert to undo this apply. */
  receipt?: ExtractionReceiptDTO;
}
export interface ExtractionJobDTO {
  job_id: string;
  /** running | done | error */
  status: string;
  done: number;
  total: number;
  error?: string;
  result?: ExtractionResultDTO;
}
/** Models the active AI provider exposes, for the per-run model override picker. */
/** Best-effort: `models` is empty when the provider is unreachable/non-OpenAI. */
export interface ExtractionModelsDTO {
  models: string[];
  active: string;
}

// --- Format-specific structured data (GN pages/panels, stage tables, series) ---
// Each DTO doubles as create-request (omit id) and response.
/** Result of syncing GN-script scene text into structured page/panel rows. */
export interface GnSyncResultDTO {
  pages: number;
  panels: number;
  skipped: boolean;
}
/** Result of parsing stage-direction scene text into cues / entrances / offstage. */
export interface StageSyncResultDTO {
  cues: number;
  entrances: number;
  offstage: number;
}
/** A recurring GN object tracked for continuity across pages. */
export interface GnContinuityItemDTO {
  id?: number;
  name?: string;
  item_type?: string;
  description?: string;
  linked_psyke_entry_id?: number | null;
  notes?: string;
}
/** One appearance of a continuity item on a page/panel (feeds object-continuity edges). */
export interface GnContinuityAppearanceDTO {
  id?: number;
  continuity_item_id?: number;
  page_id?: number | null;
  panel_id?: number | null;
  state_description?: string;
  continuity_status?: string;
}
export interface GnPageDTO {
  id?: number;
  page_number?: number;
  summary?: string;
  emotional_beat?: string;
  density_level?: string;
  reveal_type?: string;
  splash_page?: boolean;
  notes?: string;
}
export interface GnPanelDTO {
  id?: number;
  page_id?: number;
  panel_number?: number;
  description?: string;
  shot_type?: string;
  camera_angle?: string;
  emotional_tone?: string;
  action?: string;
  visual_motifs?: string[];
  transition_type?: string;
}
export interface StageEntranceExitDTO {
  id?: number;
  scene_id?: number;
  character_id?: number | null;
  /** entrance | exit */
  type?: string;
  moment_order?: number | null;
  cue_text?: string;
  notes?: string;
}
export interface StageCueDTO {
  id?: number;
  scene_id?: number;
  /** light | sound | music | prop | movement | other */
  cue_type?: string;
  moment_order?: number | null;
  cue_text?: string;
  notes?: string;
}
export interface StageBusinessDTO {
  id?: number;
  scene_id?: number;
  prop_psyke_entry_id?: number | null;
  character_id?: number | null;
  stage_action?: string;
  continuity_note?: string;
  moment_order?: number | null;
}
export interface SeasonDTO {
  id?: number;
  season_number?: number;
  title?: string;
  summary?: string;
  central_question?: string;
  finale_payoff?: string;
  status?: string;
}
export interface EpisodeDTO {
  id?: number;
  season_id?: number;
  episode_number?: number;
  title?: string;
  logline?: string;
  summary?: string;
  cliffhanger?: string;
  status?: string;
}
export interface SeriesArcDTO {
  id?: number;
  /** series | season | character */
  scope?: string;
  title?: string;
  summary?: string;
  setup_episode_id?: number | null;
  payoff_episode_id?: number | null;
  status?: string;
  notes?: string;
}
/** An A/B/C plotline within an episode — feeds episode->plotline containment edges. */
export interface EpisodePlotlineDTO {
  id?: number;
  episode_id?: number;
  type?: string;
  title?: string;
  summary?: string;
  resolution_state?: string;
}
/** A PSYKE character's series memory: per-episode status feeds 'echo' edges; */
/** non-empty continuity_flags feeds 'contradict' edges. */
export interface SeriesMemoryDTO {
  entry_id?: number;
  continuity_flags?: string;
  current_status_by_episode?: Record<string, string>;
}
