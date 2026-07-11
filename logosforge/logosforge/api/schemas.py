"""Pydantic DTOs — the stable contract between the Python core and React.

Internal ORM objects are never returned directly; routes map them onto these
DTOs via :mod:`logosforge.api.serializers`.  Field names are intended to stay
stable across releases.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


class ProjectDTO(BaseModel):
    id: int
    title: str
    description: str = ""
    narrative_engine: str = ""
    default_writing_format: str = ""
    format_mode: str = "novel"


class ProjectCreateDTO(BaseModel):
    title: str
    description: str = ""
    narrative_engine: str = ""
    default_writing_format: str = ""


class ProjectUpdateDTO(BaseModel):
    """PATCH a project — fields left None are unchanged."""
    title: str | None = None
    description: str | None = None


# --- Free-tier Whiteboard document import (blocks -> a new Pro project) ------
class WhiteboardImportBlockDTO(BaseModel):
    """One Whiteboard block (mirrors the Free app's WhiteboardBlock)."""
    id: str = ""
    type: str = "paragraph"          # 'paragraph' | 'heading'
    text: str = ""
    level: int | None = None
    sp: str | None = None            # legacy screenplay-element attr (usually null)
    marks: list[dict[str, Any]] | None = None  # [{type:'bold'|'italic', from, to}]


class WhiteboardImportDTO(BaseModel):
    """A Whiteboard document to graduate into a new Pro project."""
    title: str = ""
    mode: str = "novel"              # novel | screenplay | graphic_novel | stage_script
    blocks: list[WhiteboardImportBlockDTO] = Field(default_factory=list)


class WhiteboardImportResultDTO(BaseModel):
    project_id: int
    title: str = ""
    mode: str = "novel"
    scenes_created: int = 0
    scene_titles: list[str] = Field(default_factory=list)
    # For each source block index (0-based into the imported manuscript blocks),
    # the id of the scene that block landed in (-1 if it mapped to none). Lets a
    # caller resolve a block-anchored link (e.g. an outline node's) to a scene.
    scene_ids_by_block: list[int] = Field(default_factory=list)


class ManuscriptImportDTO(BaseModel):
    """A raw, unformatted manuscript file (.txt / .md / .docx) to import into a
    brand-new project, segmented into scenes. ``content_base64`` is the raw file
    bytes base64-encoded (so binary .docx survives transport)."""
    title: str = ""
    mode: str = "novel"              # novel | screenplay | graphic_novel | stage_script | series
    strategy: str = "smart"          # smart | chapter | scene_break | single
    filename: str = ""               # used to sniff .docx vs plain text
    content_base64: str = ""


class ManuscriptImportResultDTO(BaseModel):
    project_id: int
    title: str = ""
    mode: str = "novel"
    scenes_created: int = 0
    scene_titles: list[str] = Field(default_factory=list)


class VoiceStatusDTO(BaseModel):
    """Whether local Dexter voice (faster-whisper) is available on this core."""
    available: bool = False
    message: str = ""
    model_configured: bool = False
    device: str = "cpu"


class VoiceTranscribeDTO(BaseModel):
    """One PCM segment to transcribe (base64 of int16 mono little-endian)."""
    audio_base64: str
    sample_rate: int = 16000
    language: str | None = None


class VoiceTranscriptDTO(BaseModel):
    text: str = ""
    language: str = ""
    error: str = ""


# --- Full Dexter's Room facade (VoiceRoomService over HTTP) request bodies ---
# ``ctx`` carries the serializable commit-context fields the frontend knows
# (has_active_editor, writing_mode, psyke_entry_type, character_name, gn_* …);
# the core wires runtime callables (db / ai_complete / cursor sink) server-side.


class VoiceSegmentReqDTO(BaseModel):
    """A finalized PCM segment to transcribe + record in the session history."""
    audio_base64: str
    sample_rate: int = 16000


class VoiceCtxReqDTO(BaseModel):
    """Just the commit-context — used to list intents / Billy ops / commit targets."""
    ctx: dict[str, Any] | None = None


class VoiceIntentPreviewReqDTO(BaseModel):
    intent_id: str
    source_text: str
    commit_target_id: str = ""
    source_segment_ids: list[str] = Field(default_factory=list)
    ctx: dict[str, Any] | None = None


class VoiceIntentApplyReqDTO(BaseModel):
    preview_id: str
    ctx: dict[str, Any] | None = None


class VoiceBillyGenReqDTO(BaseModel):
    operation: str
    transcript_text: str
    source_segment_ids: list[str] = Field(default_factory=list)
    ctx: dict[str, Any] | None = None


class VoiceBillyApplyReqDTO(BaseModel):
    proposal_id: str
    ctx: dict[str, Any] | None = None


class VoiceCommitReqDTO(BaseModel):
    text: str
    target_id: str
    ctx: dict[str, Any] | None = None


class ModeSuggestionDTO(BaseModel):
    text: str
    category: str = ""


class AdaptDTO(BaseModel):
    """Adaptive-AI mode + actionable suggestions for the current story state."""
    mode: str
    stage: str
    health: str
    description: str = ""
    suggestions: list[ModeSuggestionDTO] = Field(default_factory=list)
    # "" = auto (mode derived from stage×health); else the forced mode name.
    override: str = ""


class ReviewRowDTO(BaseModel):
    scene_id: int
    number: str = ""
    title: str = ""
    word_count: int = 0
    overall_status: str = ""
    next_action: str = ""
    health_severity: str = ""
    continuity_severity: str = ""
    has_rewrite_candidate: bool = False


class FormatReviewCheckDTO(BaseModel):
    check_type: str
    message: str
    severity: str = "info"
    ref_id: int | None = None


class FormatReviewDTO(BaseModel):
    """Format-specific review findings (graphic novel / stage / series)."""
    format: str = ""
    checks: list[FormatReviewCheckDTO] = Field(default_factory=list)


class PluginDTO(BaseModel):
    name: str
    description: str = ""
    category: str = ""
    requires_scene: bool = False


class ReviewReportDTO(BaseModel):
    """Screenplay review dashboard: summary metrics + per-scene readiness rows."""
    format: str = "screenplay"
    project_title: str = ""
    total_scenes: int = 0
    written: int = 0
    planned: int = 0
    needs_work: int = 0
    with_health_warnings: int = 0
    with_continuity_warnings: int = 0
    with_export_warnings: int = 0
    timeline_linked: int = 0
    with_psyke_links: int = 0
    export_ready: bool = False
    rows: list[ReviewRowDTO] = Field(default_factory=list)


class SettingsDTO(BaseModel):
    settings: dict[str, Any] = Field(default_factory=dict)


class WritingModeDTO(BaseModel):
    id: str
    label: str
    structural_units: list[str]
    default_writing_format: str
    medium_constraints: str


class WritingModesResponseDTO(BaseModel):
    modes: list[WritingModeDTO]
    default_mode: str


# ---------------------------------------------------------------------------
# Scenes
# ---------------------------------------------------------------------------


class SceneDTO(BaseModel):
    id: int
    title: str
    summary: str = ""
    synopsis: str = ""
    goal: str = ""
    conflict: str = ""
    outcome: str = ""
    beat: str = ""
    act: str = ""
    chapter: str = ""
    plotline: str = ""
    color_label: str = ""
    tags: list[str] = Field(default_factory=list)
    content: str = ""
    sort_order: int = 0
    order_index: int = 0
    character_ids: list[int] = Field(default_factory=list)
    place_ids: list[int] = Field(default_factory=list)
    who_knows_what: str = ""


class SceneCreateDTO(BaseModel):
    title: str
    summary: str = ""
    synopsis: str = ""
    goal: str = ""
    conflict: str = ""
    outcome: str = ""
    beat: str = ""
    act: str = ""
    chapter: str = ""
    plotline: str = ""
    content: str = ""
    tags: list[str] = Field(default_factory=list)
    character_ids: list[int] = Field(default_factory=list)
    place_ids: list[int] = Field(default_factory=list)


class SceneUpdateDTO(BaseModel):
    """All fields optional — only provided fields are changed."""

    title: str | None = None
    summary: str | None = None
    synopsis: str | None = None
    goal: str | None = None
    conflict: str | None = None
    outcome: str | None = None
    beat: str | None = None
    act: str | None = None
    chapter: str | None = None
    plotline: str | None = None
    color_label: str | None = None
    content: str | None = None
    tags: list[str] | None = None
    sort_order: int | None = None
    time_of_day: str | None = None
    location: str | None = None
    estimated_duration_minutes: int | None = None
    # Graph-feeding structured fields (None = leave unchanged):
    who_knows_what: str | None = None   # screenplay — powers "knowledge" graph edges
    offstage_events: str | None = None  # stage — powers "offstage" graph edges


class ContinuityMemoryDTO(BaseModel):
    """A continuity note pinned to a scene (stored as memory_type 'continuity_<kind>').
    Two consecutive scenes sharing the same (target, kind) form a graph 'continuity'
    edge — the only screenplay edge type that previously had no in-app writer."""
    id: int | None = None
    scene_id: int | None = None
    target: str
    value: str = ""
    kind: str = "state"  # -> memory_type "continuity_<kind>" (state / object / wound / ...)


# ---------------------------------------------------------------------------
# Outline
# ---------------------------------------------------------------------------


class OutlineNodeDTO(BaseModel):
    id: int
    parent_id: int | None = None
    title: str
    description: str = ""
    sort_order: int = 0
    scene_id: int | None = None   # optional hard link to a manuscript scene
    children: list["OutlineNodeDTO"] = Field(default_factory=list)


class OutlineNodeCreateDTO(BaseModel):
    title: str
    description: str = ""
    parent_id: int | None = None
    sort_order: int = 0
    scene_id: int | None = None


class OutlineNodeUpdateDTO(BaseModel):
    title: str | None = None
    description: str | None = None
    sort_order: int | None = None
    # Present (even null) => set/clear the scene link; absent => leave unchanged.
    scene_id: int | None = None


class OutlineGenerateRequestDTO(BaseModel):
    """AI outline-generation request. ``scope`` picks the tier to generate
    (full | act | chapter | scene); ``parent_id`` applies the result under an
    existing node (scoped generation); ``instructions`` folds in extra guidance."""

    scope: str = "full"
    parent_id: int | None = None
    instructions: str = ""


class OutlineGenerateResultDTO(BaseModel):
    """Result of an AI outline generation. ``ok`` is false (with ``errors``) when
    the model's reply wasn't a usable outline — nothing is applied in that case.
    ``warnings`` report non-fatal repairs (filled placeholders, dropped
    meta-sections)."""

    ok: bool
    created: int
    node_ids: list[int] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------


class PlotSceneDTO(BaseModel):
    scene_id: int | None = None
    title: str
    act: str = ""
    summary: str = ""
    beat: str = ""
    color_label: str = ""
    order_index: int = 0


class PlotBlockDTO(BaseModel):
    id: str  # the plotline name (URL-safe stable identifier)
    plotline: str
    scenes: list[PlotSceneDTO] = Field(default_factory=list)


class PlotBlockUpdateDTO(BaseModel):
    plotline: str | None = None  # rename the block
    color_label: str | None = None  # recolour all scenes in the block


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------


class TimelineCharacterStateDTO(BaseModel):
    character: str
    state: str


class TimelineEventDTO(BaseModel):
    id: int  # scene id (timeline events are scene-derived)
    order_index: int = 0
    title: str
    act: str = ""
    chapter: str = ""
    time_of_day: str = ""
    location: str = ""
    duration_minutes: int = 0
    character_states: list[TimelineCharacterStateDTO] = Field(default_factory=list)


class TimelineEventCreateDTO(BaseModel):
    title: str
    act: str = ""
    chapter: str = ""
    time_of_day: str = ""
    location: str = ""
    duration_minutes: int = 0


class TimelineEventUpdateDTO(BaseModel):
    title: str | None = None
    act: str | None = None
    chapter: str | None = None
    time_of_day: str | None = None
    location: str | None = None
    duration_minutes: int | None = None
    sort_order: int | None = None


# ---------------------------------------------------------------------------
# PSYKE
# ---------------------------------------------------------------------------


class PsykeEntryDTO(BaseModel):
    id: int
    name: str
    type: str = "other"
    aliases: list[str] = Field(default_factory=list)
    notes: str = ""
    is_global: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class PsykeEntryCreateDTO(BaseModel):
    name: str
    type: str = "other"
    aliases: list[str] = Field(default_factory=list)
    notes: str = ""
    is_global: bool = False
    details: dict[str, Any] | None = None


class PsykeEntryUpdateDTO(BaseModel):
    name: str | None = None
    type: str | None = None
    aliases: list[str] | None = None
    notes: str | None = None
    is_global: bool | None = None
    details: dict[str, Any] | None = None


class PsykeRelationDTO(BaseModel):
    id: str  # synthetic "{source_id}:{target_id}"
    source_id: int
    target_id: int
    source: str = ""
    target: str = ""
    relation_type: str = ""


class PsykeRelationCreateDTO(BaseModel):
    source_id: int
    target_id: int
    relation_type: str = ""


class PsykeProgressionDTO(BaseModel):
    id: int
    entry_id: int
    text: str
    scene_id: int | None = None
    scene_title: str = ""
    sort_order: int = 0


class PsykeProgressionCreateDTO(BaseModel):
    entry_id: int
    text: str
    scene_id: int | None = None


class PsykeProgressionUpdateDTO(BaseModel):
    text: str
    scene_id: int | None = None


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------


class NoteDTO(BaseModel):
    id: int
    title: str
    content: str = ""
    tags: list[str] = Field(default_factory=list)
    pinned: bool = False
    psyke_links: list[int] = Field(default_factory=list)
    scene_links: list[int] = Field(default_factory=list)


class NoteCreateDTO(BaseModel):
    title: str
    content: str = ""
    tags: list[str] = Field(default_factory=list)
    pinned: bool = False


class NoteUpdateDTO(BaseModel):
    title: str | None = None
    content: str | None = None
    tags: list[str] | None = None
    pinned: bool | None = None


# ---------------------------------------------------------------------------
# Assistant / Connector
# ---------------------------------------------------------------------------


class ChatMessageDTO(BaseModel):
    role: str
    content: str


class AssistantRequestDTO(BaseModel):
    message: str
    history: list[ChatMessageDTO] = Field(default_factory=list)
    system_prompt: str = ""
    # Optional: the scene the writer has open, so Billy gets that scene's context
    # in addition to the project-level bundle. None => project-level context only.
    active_scene_id: int | None = None
    # Optional inline-editor context (e.g. the Whiteboard): the text the writer has
    # selected / nearby and the open document's title. Folded into the chat context
    # server-side so grounding stays in the core, not in a frontend/wrapper preamble.
    selected_text: str = ""
    nearby_text: str = ""
    document_title: str = ""
    # "Go Irrational" — inject surreal creative provocations for this one reply
    # (needs active_scene_id). Per-request; nothing is persisted.
    irrational: bool = False


class AssistantResponseDTO(BaseModel):
    reply: str
    cached: bool = False


class AiBehaviorDTO(BaseModel):
    """Global (app-level) AI behaviour the headless API actually honours: which
    grounding sources Billy folds in (build_chat_context), and the connector's
    safe-action governance (enforced in the connector execute route)."""

    # Chat grounding sources (build_chat_context)
    ctx_outline: bool = True
    ctx_bible: bool = True
    ctx_memory: bool = True
    # Connector governance (enforced server-side)
    connector_enabled: bool = False
    connector_allow_writes: bool = False
    connector_confirm_writes: bool = True
    connector_disabled_actions: list[str] = Field(default_factory=list)
    # Adaptive coaching mode override ("" = auto; else Structure|Balance|Refinement)
    adaptive_override: str = ""


class AiBehaviorUpdateDTO(BaseModel):
    ctx_outline: bool | None = None
    ctx_bible: bool | None = None
    ctx_memory: bool | None = None
    connector_enabled: bool | None = None
    connector_allow_writes: bool | None = None
    connector_confirm_writes: bool | None = None
    connector_disabled_actions: list[str] | None = None
    adaptive_override: str | None = None


class GrammarCheckRequestDTO(BaseModel):
    text: str
    language: str = ""   # "" = auto-detect (trigram)


class GrammarIssueDTO(BaseModel):
    start: int
    end: int
    issue_type: str      # spelling | grammar | style
    message: str
    suggestions: list[str] = Field(default_factory=list)


class GrammarCheckResultDTO(BaseModel):
    language: str
    issues: list[GrammarIssueDTO] = Field(default_factory=list)


class AssistantActionRequestDTO(BaseModel):
    action: str
    args: dict[str, Any] = Field(default_factory=dict)


class AssistantSettingsDTO(BaseModel):
    provider: str = ""
    model: str = ""
    base_url: str = ""
    # api_key is intentionally write-only; never returned.
    api_key: str | None = None
    timeout: int = 0


# -- Logos (inline / contextual assistant) -----------------------------------

class LogosActionDTO(BaseModel):
    """One entry of the core Logos action catalog (see logosforge.logos.actions)."""

    name: str
    label: str
    description: str = ""
    category: str = ""           # "diagnostic" | "generative"
    sections: list[str] = Field(default_factory=list)
    needs_selection: bool = False
    deterministic: bool = False
    # generative actions propose new prose a UI may apply; diagnostic ones only
    # report. Surfaced so callers read it from here, never re-deciding it.
    generative: bool = False


class LogosRunRequestDTO(BaseModel):
    action: str
    section: str = ""
    selected_text: str = ""
    nearby_context: str = ""
    writing_mode: str = ""
    current_scene_id: int | None = None
    # Optional non-manuscript node context (from a cross-panel selection) so Outline/
    # PSYKE/Plot/Timeline/Graph actions can operate on the focused node.
    current_outline_node_id: int | None = None
    current_psyke_entry_id: int | None = None
    current_timeline_event_id: int | None = None
    current_plot_block_id: str = ""
    current_graph_node_id: str = ""


class LogosResultDTO(BaseModel):
    """Serialized logosforge.logos.result.LogosResult plus a generative flag."""

    ok: bool
    action: str
    title: str = ""
    message: str = ""
    suggestions: list[str] = Field(default_factory=list)
    proposed_operations: list[dict[str, Any]] = Field(default_factory=list)
    generative: bool = False
    error: str | None = None


class LogosSuggestionDTO(BaseModel):
    """A proactive Logos signal (logosforge.logos.proactive.LogosSuggestion) —
    a non-destructive observation with the actions that could address it."""

    id: str
    type: str
    title: str
    message: str = ""
    section_name: str = ""
    evidence: str = ""
    confidence: float = 0.0
    severity: str = "info"            # info | warning | important
    target_type: str = ""
    target_id: str = ""
    suggested_actions: list[str] = Field(default_factory=list)


class ConnectorActionParamDTO(BaseModel):
    name: str
    param_type: str = "str"
    required: bool = True
    default: Any = None


class ConnectorActionDTO(BaseModel):
    name: str
    description: str = ""
    category: str = ""
    params: list[ConnectorActionParamDTO] = Field(default_factory=list)


class ConnectorExecuteDTO(BaseModel):
    action: str
    args: dict[str, Any] = Field(default_factory=dict)


class ConnectorResultDTO(BaseModel):
    ok: bool
    action: str = ""
    result: Any = None
    error: str = ""


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


class ExportRequestDTO(BaseModel):
    export_type: str = "story_elements"  # story_elements | psyke_data | full_project
    format: str = "json"  # json | markdown | csv
    # Optional section overrides (default = the preset for export_type).
    include_outline: bool | None = None
    include_plot: bool | None = None
    include_timeline: bool | None = None
    include_scenes: bool | None = None
    include_psyke_entries: bool | None = None
    include_psyke_relations: bool | None = None
    include_psyke_progressions: bool | None = None
    include_notes: bool | None = None
    include_project_metadata: bool | None = None
    include_ids: bool | None = None
    include_internal_metadata: bool | None = None
    summaries_only: bool | None = None


class ExportResponseDTO(BaseModel):
    export_type: str
    format: str
    # For json: the structured payload. For markdown/csv: text content (csv = a
    # map of filename -> text).
    payload: Any = None
    content: str | None = None
    files: dict[str, str] | None = None
    # For BINARY exports (PDF/DOCX): base64-encoded file bytes the client decodes
    # and saves. filename + mime_type accompany content / content_base64.
    content_base64: str | None = None
    filename: str | None = None
    mime_type: str | None = None


OutlineNodeDTO.model_rebuild()


# ---------------------------------------------------------------------------
# Narrative dashboard (derived, read-only analytics)
# ---------------------------------------------------------------------------


class SceneTensionDTO(BaseModel):
    scene_id: int
    scene_order: int
    scene_title: str
    score: float
    char_count: int
    relation_pairs: int
    keyword_hits: int
    progression_count: int


class TensionCurveDTO(BaseModel):
    points: list[SceneTensionDTO] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)


class CharacterPresenceDTO(BaseModel):
    entry_id: int
    name: str
    present_scenes: list[int] = Field(default_factory=list)
    total_scenes: int
    flags: list[str] = Field(default_factory=list)


class ThemePresenceDTO(BaseModel):
    entry_id: int
    name: str
    present_scenes: list[int] = Field(default_factory=list)
    total_scenes: int
    flags: list[str] = Field(default_factory=list)
    # "prose" (presence inferred from name/alias mentions — heuristic) or
    # "controlling_idea" (at least partly backed by CI scene alignment — structural).
    presence_source: str = "prose"


class ActSegmentDTO(BaseModel):
    label: str
    scene_count: int
    word_count: int


class StructureDistributionDTO(BaseModel):
    segments: list[ActSegmentDTO] = Field(default_factory=list)
    total_scenes: int
    total_words: int
    flags: list[str] = Field(default_factory=list)
    inferred: bool = False


class NarrativeDashboardDTO(BaseModel):
    tension: TensionCurveDTO
    characters: list[CharacterPresenceDTO] = Field(default_factory=list)
    structure: StructureDistributionDTO
    themes: list[ThemePresenceDTO] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Continuity, pacing, balance, story health (derived, read-only)
# ---------------------------------------------------------------------------


class ContinuityIssueDTO(BaseModel):
    id: str  # stable issue_key
    issue_type: str
    dimension: str
    severity: str  # info | suggestion | warning | blocking
    confidence: str  # confirmed | likely | possible | unknown
    title: str
    explanation: str = ""
    suggested_action: str = ""
    related_scene_ids: list[int] = Field(default_factory=list)
    status: str = "open"


class ContinuityReportDTO(BaseModel):
    writing_mode: str
    issues: list[ContinuityIssueDTO] = Field(default_factory=list)
    blocking_count: int = 0
    warning_count: int = 0
    unavailable: list[str] = Field(default_factory=list)


class PacingInsightDTO(BaseModel):
    text: str
    severity: float  # 0.0–1.0
    category: str  # disappearance | monotony | stagnation | neglect | clustering


class CharacterBalanceDTO(BaseModel):
    char_id: int
    name: str
    scene_count: int
    total_scenes: int
    flag: str = ""  # dominant | underused | ""


class ArcBalanceDTO(BaseModel):
    plotline: str
    scene_count: int
    acts_spanned: int
    flag: str = ""  # thin | ""


class BalanceDataDTO(BaseModel):
    characters: list[CharacterBalanceDTO] = Field(default_factory=list)
    arcs: list[ArcBalanceDTO] = Field(default_factory=list)
    total_scenes: int = 0


class HealthSignalDTO(BaseModel):
    label: str
    level: str  # balanced | sparse | problematic
    score: float  # 0.0–1.0


class StoryHealthDTO(BaseModel):
    structure: HealthSignalDTO
    characters: HealthSignalDTO
    arcs: HealthSignalDTO
    density: HealthSignalDTO


class StructuralIssueDTO(BaseModel):
    issue_type: str
    category: str
    severity: float  # 0.0–1.0
    message: str
    suggestion: str = ""


class StructuralAnalysisDTO(BaseModel):
    issues: list[StructuralIssueDTO] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class WorkflowStepDTO(BaseModel):
    step_id: str
    title: str
    status: str  # pending | active | completed | skipped
    sort_index: int = 0
    section_name: str = ""
    action_id: str = ""


class WorkflowRunDTO(BaseModel):
    id: int
    title: str
    status: str  # active | paused | completed | cancelled
    writing_mode: str = ""
    template_id: str = ""
    current_step_id: str = ""
    total_steps: int = 0
    completed_steps: int = 0
    steps: list[WorkflowStepDTO] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Decision radar (project intelligence) + Quantum outliner (generative)
# ---------------------------------------------------------------------------


class DecisionCardDTO(BaseModel):
    id: str
    category: str  # structure | psyke | continuity | rewrite | apply | export | production | graph | notes | writing_mode
    severity: str  # blocking | warning | suggestion | opportunity | info
    confidence: str  # confirmed | likely | possible | unknown
    title: str
    explanation: str = ""
    suggested_action: str = ""
    related_section: str = ""
    related_target_type: str = ""
    related_target_id: int | None = None
    created_from: str = "deterministic"


class DecisionRadarDTO(BaseModel):
    project_id: int
    generated_light: bool = False
    summary_line: str = ""
    radar: list[DecisionCardDTO] = Field(default_factory=list)


class QuantumResultDTO(BaseModel):
    kind: str
    title: str
    body: str
    # The wavefunction summary (branches, recommendation, …) — already JSON-ready.
    payload: dict = Field(default_factory=dict)


class QuantumOutlineRequestDTO(BaseModel):
    premise: str
    n: int = 4
    source_scene_id: int | None = None
    structure_mode: str | None = None
    # Request the LLM-backed generative branches (LAMBDA). Default False keeps the
    # deterministic classical beat-sheet as the API default.
    generative: bool = False


class QuantumBranchesRequestDTO(BaseModel):
    situation: str
    n: int = 4
    extra_context: str = ""
    source_scene_id: int | None = None
    structure_mode: str | None = None
    # Request the LLM-backed generative branches (LAMBDA). Default False keeps the
    # deterministic classical beat-sheet as the API default.
    generative: bool = False


class QuantumSettingsDTO(BaseModel):
    """Per-project Lambda-mode scoring configuration — read by the generate path
    (``db.get_scoring_weights`` / ``get_selection_mode`` / … in
    ``quantum_outliner``). ``preset_names`` / ``weight_keys`` are read-only hints
    the UI uses to render pickers in a stable order."""

    preset: str = "Balanced"
    weights: dict[str, float] = Field(default_factory=dict)
    selection_mode: str = "weighted"   # weighted | pareto
    show_tradeoffs: bool = False
    ensemble_alpha: float = 0.7
    weight_learning: bool = True
    preset_names: list[str] = Field(default_factory=list)   # read-only (UI)
    weight_keys: list[str] = Field(default_factory=list)    # read-only (UI, canonical order)


class QuantumSettingsUpdateDTO(BaseModel):
    """Partial update — only provided fields are written. Setting ``preset`` to a
    known preset also applies its weights (unless ``weights`` is also provided);
    editing ``weights`` directly marks the preset ``Custom``."""

    preset: str | None = None
    weights: dict[str, float] | None = None
    selection_mode: str | None = None
    show_tradeoffs: bool | None = None
    ensemble_alpha: float | None = None
    weight_learning: bool | None = None


# ---------------------------------------------------------------------------
# Story gravity (graph node weights) + Counterpart (reflective AI)
# ---------------------------------------------------------------------------


class StoryGravityNodeDTO(BaseModel):
    node_id: str  # "etype:entity_id", e.g. "Character:5"
    etype: str
    name: str
    narrative: float
    thematic: float
    structural: float
    total: float


class GravityWeightsDTO(BaseModel):
    narrative: float = 0.45
    thematic: float = 0.35
    structural: float = 0.2


class GraphGravityDTO(BaseModel):
    weights: GravityWeightsDTO = Field(default_factory=GravityWeightsDTO)
    glow_threshold: float = 0.55
    # False when the graph-data builder is unavailable (Qt-less server).
    available: bool = True
    nodes: list[StoryGravityNodeDTO] = Field(default_factory=list)


class CounterpartRequestDTO(BaseModel):
    mode: str = "Feedback"  # Feedback | Critique | Interpret | Ask Back | Compare
    scene_context: str = ""
    outline_context: str = ""
    story_memory_context: str = ""
    psyke_context: str = ""
    graph_context: str = ""
    user_note: str = ""
    custom_prompt: str = ""


# ---------------------------------------------------------------------------
# Manuscript -> structured-data extraction (AI-assisted; propose -> apply)
# ---------------------------------------------------------------------------


class ExtractionModelsDTO(BaseModel):
    """The models the active AI provider exposes, for the extractor's per-run model
    override picker. Best-effort: ``models`` is empty when the provider is
    unreachable or non-OpenAI. ``active`` is the configured default model."""
    models: list[str] = Field(default_factory=list)
    active: str = ""


class NearDupHintDTO(BaseModel):
    """Advisory: an existing PSYKE entry a proposed name closely resembles (likely a
    typo). Display-only — the review UI surfaces it; apply never auto-merges."""
    existing_id: int
    existing_name: str
    score: float


class RelationProposalDTO(BaseModel):
    source: str
    target: str
    rel_type: str  # supports_setup | payoff | subtext_opposition | visual_motif
    why: str = ""
    confidence: float = 0.6
    # Advisory, display-only (computed at propose time; apply ignores these): per
    # entity, "existing" (reuses an entry) | "new" (creates one) | "" (unknown), and
    # — when "new" — an optional near-duplicate hint flagging a likely typo.
    source_status: str = ""
    target_status: str = ""
    source_hint: NearDupHintDTO | None = None
    target_hint: NearDupHintDTO | None = None


class SceneExtractionDTO(BaseModel):
    scene_id: int
    title: str = ""
    characters: list[str] = Field(default_factory=list)  # Tier 1 (deterministic cues)
    who_knows_what: str = ""                              # Tier 2 (LLM)
    relations: list[RelationProposalDTO] = Field(default_factory=list)


class ExtractionResultDTO(BaseModel):
    """Read-only proposals from the manuscript — reviewed before they are applied."""
    project_id: int
    used_llm: bool = False
    scenes: list[SceneExtractionDTO] = Field(default_factory=list)
    setup_payoffs: list[RelationProposalDTO] = Field(default_factory=list)


class ExtractionApplyRequestDTO(BaseModel):
    """The human-reviewed/accepted subset of proposals to write."""
    scenes: list[SceneExtractionDTO] = Field(default_factory=list)
    setup_payoffs: list[RelationProposalDTO] = Field(default_factory=list)


class RelationRefDTO(BaseModel):
    source_id: int
    target_id: int
    rel_type: str


class ExtractionReceiptDTO(BaseModel):
    """Provenance record of exactly what an apply wrote — POST /extract/revert undoes it."""
    character_ids: list[int] = Field(default_factory=list)
    links: list[list[int]] = Field(default_factory=list)  # [[scene_id, character_id], ...]
    wkw_scene_ids: list[int] = Field(default_factory=list)
    psyke_ids: list[int] = Field(default_factory=list)
    relations: list[RelationRefDTO] = Field(default_factory=list)


class ExtractionApplyReportDTO(BaseModel):
    characters_created: int = 0
    links_added: int = 0
    who_knows_what_set: int = 0
    psyke_created: int = 0
    relations_added: int = 0
    receipt: ExtractionReceiptDTO | None = None


class ExtractionJobDTO(BaseModel):
    """Async extraction job: POST /extract starts it; GET /extract/jobs/{id} polls it."""
    job_id: str
    status: str = "running"  # running | done | error
    done: int = 0
    total: int = 0
    error: str = ""
    result: ExtractionResultDTO | None = None


# ---------------------------------------------------------------------------
# Format-specific structured data — the writers the audit found had no API path
# (graphic-novel pages/panels, stage entrances/cues/business, series seasons/
# episodes/arcs). Each DTO doubles as create-request (id=0) and response body.
# ---------------------------------------------------------------------------


class GnSyncResultDTO(BaseModel):
    """Result of syncing GN-script scene text into structured page/panel rows."""
    pages: int = 0
    panels: int = 0
    skipped: bool = False


class StageSyncResultDTO(BaseModel):
    """Result of parsing stage-direction scene text into cues / entrances / offstage."""
    cues: int = 0
    entrances: int = 0
    offstage: int = 0


class GnPageDTO(BaseModel):
    id: int = 0
    page_number: int = 0
    summary: str = ""
    emotional_beat: str = ""
    density_level: str = ""
    reveal_type: str = ""
    splash_page: bool = False
    notes: str = ""


class GnContinuityItemDTO(BaseModel):
    """A recurring GN object/prop tracked for continuity across pages."""
    id: int = 0
    name: str = ""
    item_type: str = "other"
    description: str = ""
    linked_psyke_entry_id: int | None = None
    notes: str = ""


class GnContinuityAppearanceDTO(BaseModel):
    """One appearance of a continuity item on a page/panel — feeds the GN graph's
    object-continuity edges (object <-> page)."""
    id: int = 0
    continuity_item_id: int = 0
    page_id: int | None = None
    panel_id: int | None = None
    state_description: str = ""
    continuity_status: str = "consistent"


class GnPanelDTO(BaseModel):
    id: int = 0
    page_id: int = 0
    panel_number: int = 0
    description: str = ""
    shot_type: str = ""
    camera_angle: str = ""
    emotional_tone: str = ""
    action: str = ""
    visual_motifs: list[str] = Field(default_factory=list)
    transition_type: str = ""


class StageEntranceExitDTO(BaseModel):
    id: int = 0
    scene_id: int = 0
    character_id: int | None = None
    type: str = "entrance"  # entrance | exit
    moment_order: int | None = None
    cue_text: str = ""
    notes: str = ""


class StageCueDTO(BaseModel):
    id: int = 0
    scene_id: int = 0
    cue_type: str = "other"  # light | sound | music | prop | movement | other
    moment_order: int | None = None
    cue_text: str = ""
    notes: str = ""


class StageBusinessDTO(BaseModel):
    id: int = 0
    scene_id: int = 0
    prop_psyke_entry_id: int | None = None
    character_id: int | None = None
    stage_action: str = ""
    continuity_note: str = ""
    moment_order: int | None = None


class SeasonDTO(BaseModel):
    id: int = 0
    season_number: int = 0
    title: str = ""
    summary: str = ""
    central_question: str = ""
    finale_payoff: str = ""
    status: str = ""


class EpisodeDTO(BaseModel):
    id: int = 0
    season_id: int = 0
    episode_number: int = 0
    title: str = ""
    logline: str = ""
    summary: str = ""
    cliffhanger: str = ""
    status: str = ""


class SeriesArcDTO(BaseModel):
    id: int = 0
    scope: str = "series"  # series | season | character
    title: str = ""
    summary: str = ""
    setup_episode_id: int | None = None
    payoff_episode_id: int | None = None
    status: str = "active"
    notes: str = ""


class EpisodePlotlineDTO(BaseModel):
    """An A/B/C plotline within an episode — feeds the series graph's episode->plotline
    containment edges."""
    id: int = 0
    episode_id: int = 0
    type: str = "A"  # A | B | C ...
    title: str = ""
    summary: str = ""
    resolution_state: str = ""


class SeriesMemoryDTO(BaseModel):
    """A PSYKE character's long-form series memory. ``current_status_by_episode``
    (episode-id -> status) feeds the graph's character->episode 'echo' edges;
    ``continuity_flags`` (non-empty) feeds 'contradict' edges."""
    entry_id: int = 0
    continuity_flags: str = ""
    current_status_by_episode: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Characters (manuscript cast) + the stable Character <-> PSYKE bible link
# ---------------------------------------------------------------------------


class CharacterDTO(BaseModel):
    id: int
    name: str
    description: str = ""
    color: str = "#3498db"
    # Stable link to this character's PSYKE 'character' bible entry (null = unlinked).
    psyke_entry_id: int | None = None


class CharacterUpdateDTO(BaseModel):
    # All-optional PATCH; an explicit psyke_entry_id: null clears the link.
    name: str | None = None
    description: str | None = None
    psyke_entry_id: int | None = None


class CharacterCreateDTO(BaseModel):
    name: str
    description: str = ""


class ThemeScenesDTO(BaseModel):
    """The scenes a theme (PSYKE 'theme' entry) is structurally tagged in."""
    entry_id: int
    scene_ids: list[int] = Field(default_factory=list)


class ThemeScenesUpdateDTO(BaseModel):
    """PUT body — the full replacement set of scenes for the theme."""
    scene_ids: list[int] = Field(default_factory=list)
