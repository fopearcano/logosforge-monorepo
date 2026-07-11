/**
 * API adapter — the typed surface over the logosforge core API that the apps
 * inject. Desktop wraps the in-process core (localhost:8765); web talks to a
 * remote host. Shared-ui components call this interface; they never construct
 * URLs or perform raw fetches. All shapes come from `@logosforge/ui-contracts`.
 */
import type {
  ProjectDTO,
  ProjectCreateDTO,
  ProjectUpdateDTO,
  WhiteboardImportDTO,
  WhiteboardImportResultDTO,
  ManuscriptImportDTO,
  ManuscriptImportResultDTO,
  AdaptDTO,
  ReviewReportDTO,
  FormatReviewDTO,
  PluginDTO,
  VoiceStatusDTO,
  VoiceTranscribeDTO,
  VoiceTranscriptDTO,
  VoiceSegmentReqDTO,
  VoiceHistoryEntryDTO,
  VoiceHistoryDTO,
  VoiceCtxReqDTO,
  VoiceIntentsDTO,
  VoiceIntentPreviewReqDTO,
  VoiceIntentPreviewDTO,
  VoiceIntentApplyReqDTO,
  VoiceApplyResultDTO,
  VoiceBillyOpsDTO,
  VoiceBillyGenReqDTO,
  VoiceBillyProposalDTO,
  VoiceBillyApplyReqDTO,
  VoiceCommitTargetsDTO,
  VoiceCommitReqDTO,
  VoiceUndoStateDTO,
  VoiceUndoResultDTO,
  SettingsDTO,
  WritingModesResponseDTO,
  SceneDTO,
  SceneCreateDTO,
  SceneUpdateDTO,
  ContinuityMemoryDTO,
  OutlineNodeDTO,
  OutlineNodeCreateDTO,
  OutlineNodeUpdateDTO,
  OutlineGenerateRequestDTO,
  OutlineGenerateResultDTO,
  PlotBlockDTO,
  PlotBlockUpdateDTO,
  TimelineEventDTO,
  TimelineEventUpdateDTO,
  PsykeEntryDTO,
  PsykeEntryCreateDTO,
  PsykeEntryUpdateDTO,
  PsykeRelationDTO,
  PsykeRelationCreateDTO,
  PsykeProgressionDTO,
  PsykeProgressionCreateDTO,
  NoteDTO,
  NoteCreateDTO,
  NoteUpdateDTO,
  CharacterDTO,
  CharacterUpdateDTO,
  CharacterCreateDTO,
  PsykeProgressionUpdateDTO,
  TimelineEventCreateDTO,
  ThemeScenesDTO,
  AssistantRequestDTO,
  AssistantResponseDTO,
  AssistantActionRequestDTO,
  LogosActionDTO,
  LogosRunRequestDTO,
  LogosResultDTO,
  LogosSuggestionDTO,
  AssistantSettingsDTO,
  ConnectorActionDTO,
  ConnectorExecuteDTO,
  ConnectorResultDTO,
  ExportRequestDTO,
  ExportResponseDTO,
  NarrativeDashboardDTO,
  ContinuityReportDTO,
  PacingInsightDTO,
  BalanceDataDTO,
  StoryHealthDTO,
  StructuralAnalysisDTO,
  WorkflowRunDTO,
  DecisionRadarDTO,
  QuantumResultDTO,
  QuantumOutlineRequestDTO,
  QuantumBranchesRequestDTO,
  QuantumSettingsDTO,
  QuantumSettingsUpdateDTO,
  AiBehaviorDTO,
  AiBehaviorUpdateDTO,
  GrammarCheckRequestDTO,
  GrammarCheckResultDTO,
  GraphGravityDTO,
  CounterpartRequestDTO,
  ExtractionJobDTO,
  ExtractionModelsDTO,
  ExtractionApplyRequestDTO,
  ExtractionApplyReportDTO,
  ExtractionReceiptDTO,
  GnPageDTO,
  GnSyncResultDTO,
  GnContinuityItemDTO,
  GnContinuityAppearanceDTO,
  GnPanelDTO,
  StageCueDTO,
  StageEntranceExitDTO,
  StageBusinessDTO,
  StageSyncResultDTO,
  SeasonDTO,
  EpisodeDTO,
  SeriesArcDTO,
  EpisodePlotlineDTO,
  SeriesMemoryDTO,
  EventMessage,
} from "@logosforge/ui-contracts";

export interface ApiClient {
  // Projects & meta
  health(): Promise<{ status: string; core_version: string; api_version: string }>;
  writingModes(): Promise<WritingModesResponseDTO>;
  listProjects(): Promise<ProjectDTO[]>;
  createProject(body: ProjectCreateDTO): Promise<ProjectDTO>;
  /** Graduate a Free Whiteboard document into a NEW project (blocks -> scenes). */
  importWhiteboard(body: WhiteboardImportDTO): Promise<WhiteboardImportResultDTO>;
  /** Import a raw, unformatted manuscript (.txt/.md/.docx) into a NEW project. */
  importManuscript(body: ManuscriptImportDTO): Promise<ManuscriptImportResultDTO>;
  getProject(id: number): Promise<ProjectDTO>;
  updateProject(id: number, body: ProjectUpdateDTO): Promise<ProjectDTO>;
  deleteProject(id: number): Promise<{ ok: boolean; deleted: number }>;
  openProject(id: number): Promise<ProjectDTO>;
  saveProject(id: number): Promise<void>;
  closeProject(id: number): Promise<void>;
  getSettings(id: number): Promise<SettingsDTO>;
  patchSettings(id: number, body: SettingsDTO): Promise<SettingsDTO>;

  // Scenes
  listScenes(p: number): Promise<SceneDTO[]>;
  createScene(p: number, body: SceneCreateDTO): Promise<SceneDTO>;
  updateScene(p: number, sceneId: number, body: SceneUpdateDTO): Promise<SceneDTO>;
  deleteScene(p: number, sceneId: number): Promise<void>;
  listContinuity(p: number, sceneId: number): Promise<ContinuityMemoryDTO[]>;
  addContinuity(p: number, sceneId: number, body: ContinuityMemoryDTO): Promise<ContinuityMemoryDTO>;

  // Outline
  getOutline(p: number): Promise<OutlineNodeDTO[]>;
  createOutlineNode(p: number, body: OutlineNodeCreateDTO): Promise<OutlineNodeDTO>;
  updateOutlineNode(p: number, nodeId: number, body: OutlineNodeUpdateDTO): Promise<OutlineNodeDTO>;
  deleteOutlineNode(p: number, nodeId: number): Promise<void>;
  generateOutline(p: number, body: OutlineGenerateRequestDTO): Promise<OutlineGenerateResultDTO>;

  // Plot & timeline
  getPlot(p: number): Promise<PlotBlockDTO[]>;
  updatePlotBlock(p: number, blockId: string, body: PlotBlockUpdateDTO): Promise<PlotBlockDTO>;
  getTimeline(p: number): Promise<TimelineEventDTO[]>;
  createTimelineEvent(p: number, body: TimelineEventCreateDTO): Promise<TimelineEventDTO>;
  updateTimelineEvent(p: number, eventId: number, body: TimelineEventUpdateDTO): Promise<TimelineEventDTO>;
  deleteTimelineEvent(p: number, eventId: number): Promise<{ ok: boolean; removed: number }>;

  // PSYKE
  listPsyke(p: number): Promise<PsykeEntryDTO[]>;
  searchPsyke(p: number, q: string): Promise<PsykeEntryDTO[]>;
  createPsyke(p: number, body: PsykeEntryCreateDTO): Promise<PsykeEntryDTO>;
  updatePsyke(p: number, entryId: number, body: PsykeEntryUpdateDTO): Promise<PsykeEntryDTO>;
  deletePsyke(p: number, entryId: number): Promise<void>;
  listRelations(p: number): Promise<PsykeRelationDTO[]>;
  createRelation(p: number, body: PsykeRelationCreateDTO): Promise<PsykeRelationDTO>;
  /** Change a relation's type: re-POST via createRelation (the core upserts by pair). */
  deleteRelation(p: number, relationId: string): Promise<{ ok: boolean; deleted: string }>;
  listProgressions(p: number): Promise<PsykeProgressionDTO[]>;
  createProgression(p: number, body: PsykeProgressionCreateDTO): Promise<PsykeProgressionDTO>;
  updateProgression(p: number, progressionId: number, body: PsykeProgressionUpdateDTO): Promise<PsykeProgressionDTO>;
  deleteProgression(p: number, progressionId: number): Promise<{ ok: boolean; deleted: number }>;

  // Notes
  listNotes(p: number): Promise<NoteDTO[]>;
  createNote(p: number, body: NoteCreateDTO): Promise<NoteDTO>;
  updateNote(p: number, noteId: number, body: NoteUpdateDTO): Promise<NoteDTO>;
  deleteNote(p: number, noteId: number): Promise<void>;
  linkNoteScene(p: number, noteId: number, sceneId: number): Promise<{ ok: boolean; scene_links: number[] }>;
  unlinkNoteScene(p: number, noteId: number, sceneId: number): Promise<{ ok: boolean; scene_links: number[] }>;
  linkNotePsyke(p: number, noteId: number, entryId: number): Promise<{ ok: boolean; psyke_links: number[] }>;
  unlinkNotePsyke(p: number, noteId: number, entryId: number): Promise<{ ok: boolean; psyke_links: number[] }>;

  // Characters (manuscript cast + the stable PSYKE bible link)
  listCharacters(p: number): Promise<CharacterDTO[]>;
  createCharacter(p: number, body: CharacterCreateDTO): Promise<CharacterDTO>;
  updateCharacter(p: number, characterId: number, body: CharacterUpdateDTO): Promise<CharacterDTO>;
  deleteCharacter(p: number, characterId: number): Promise<{ ok: boolean; deleted: number }>;
  backfillCharacterLinks(p: number): Promise<{ ok: boolean; linked: number }>;

  // Theme <-> scene links (structured theme presence)
  getThemeScenes(p: number, entryId: number): Promise<ThemeScenesDTO>;
  setThemeScenes(p: number, entryId: number, sceneIds: number[]): Promise<ThemeScenesDTO>;

  // Assistant / connector
  assistantChat(p: number, body: AssistantRequestDTO): Promise<AssistantResponseDTO>;
  assistantAction(p: number, body: AssistantActionRequestDTO): Promise<ConnectorResultDTO>;
  // Logos — the core inline/contextual action engine (catalog + run)
  listLogosActions(p: number, section?: string, writingMode?: string): Promise<LogosActionDTO[]>;
  runLogos(p: number, body: LogosRunRequestDTO): Promise<LogosResultDTO>;
  listLogosProactive(p: number, section?: string): Promise<LogosSuggestionDTO[]>;
  getAssistantSettings(p: number): Promise<AssistantSettingsDTO>;
  patchAssistantSettings(p: number, body: AssistantSettingsDTO): Promise<AssistantSettingsDTO>;
  // AI behaviour — chat grounding sources + connector governance (all honoured by the core)
  getAiBehavior(p: number): Promise<AiBehaviorDTO>;
  patchAiBehavior(p: number, body: AiBehaviorUpdateDTO): Promise<AiBehaviorDTO>;
  // Grammar / spelling / style (stateless rule-based check)
  grammarCheck(p: number, body: GrammarCheckRequestDTO): Promise<GrammarCheckResultDTO>;
  listConnectorActions(p: number): Promise<ConnectorActionDTO[]>;
  connectorExecute(p: number, body: ConnectorExecuteDTO): Promise<ConnectorResultDTO>;

  // Export
  export(p: number, body: ExportRequestDTO): Promise<ExportResponseDTO>;

  // Derived intelligence (read-only, computed by the core)
  getDashboard(p: number): Promise<NarrativeDashboardDTO>;
  getContinuity(p: number): Promise<ContinuityReportDTO>;
  getPacing(p: number): Promise<PacingInsightDTO[]>;
  getBalance(p: number): Promise<BalanceDataDTO>;
  getStoryHealth(p: number): Promise<StoryHealthDTO>;
  getStructureAnalysis(p: number): Promise<StructuralAnalysisDTO>;
  getWorkflows(p: number): Promise<WorkflowRunDTO[]>;
  getDecisionRadar(p: number): Promise<DecisionRadarDTO>;
  getAdapt(p: number): Promise<AdaptDTO>;
  getReview(p: number): Promise<ReviewReportDTO>;
  getFormatReview(p: number): Promise<FormatReviewDTO>;
  listPlugins(): Promise<PluginDTO[]>;
  voiceStatus(): Promise<VoiceStatusDTO>;
  voiceTranscribe(p: number, body: VoiceTranscribeDTO): Promise<VoiceTranscriptDTO>;
  // Full Dexter's Room facade (VoiceRoomService): session history, Intent
  // cleanup, ask/edit-with-Billy, commit targets (editor/Note/PSYKE), undo.
  voiceTranscribeSegment(p: number, body: VoiceSegmentReqDTO): Promise<VoiceHistoryEntryDTO | { error: string } | { empty: true }>;
  voiceHistory(p: number): Promise<VoiceHistoryDTO>;
  voiceIntents(p: number, body: VoiceCtxReqDTO): Promise<VoiceIntentsDTO>;
  voiceIntentPreview(p: number, body: VoiceIntentPreviewReqDTO): Promise<VoiceIntentPreviewDTO>;
  voiceIntentApply(p: number, body: VoiceIntentApplyReqDTO): Promise<VoiceApplyResultDTO>;
  voiceBillyOps(p: number, body: VoiceCtxReqDTO): Promise<VoiceBillyOpsDTO>;
  voiceBillyGenerate(p: number, body: VoiceBillyGenReqDTO): Promise<VoiceBillyProposalDTO>;
  voiceBillyApply(p: number, body: VoiceBillyApplyReqDTO): Promise<VoiceApplyResultDTO>;
  voiceCommitTargets(p: number, body: VoiceCtxReqDTO): Promise<VoiceCommitTargetsDTO>;
  voiceCommit(p: number, body: VoiceCommitReqDTO): Promise<VoiceApplyResultDTO>;
  voiceCanUndo(p: number): Promise<VoiceUndoStateDTO>;
  voiceUndo(p: number): Promise<VoiceUndoResultDTO>;
  getGraphGravity(p: number): Promise<GraphGravityDTO>;

  // Generative (POST, LLM-backed; quantum degrades to deterministic stubs, counterpart does not)
  generateQuantumOutline(p: number, body: QuantumOutlineRequestDTO): Promise<QuantumResultDTO>;
  generateQuantumBranches(p: number, body: QuantumBranchesRequestDTO): Promise<QuantumResultDTO>;
  getQuantumSettings(p: number): Promise<QuantumSettingsDTO>;
  patchQuantumSettings(p: number, body: QuantumSettingsUpdateDTO): Promise<QuantumSettingsDTO>;
  runCounterpart(p: number, body: CounterpartRequestDTO): Promise<AssistantResponseDTO>;

  // Manuscript -> structured-data extraction (async job -> review -> apply)
  startExtract(p: number, useLlm?: boolean, model?: string): Promise<ExtractionJobDTO>;
  listExtractionModels(p: number): Promise<ExtractionModelsDTO>;
  getExtractJob(p: number, jobId: string): Promise<ExtractionJobDTO>;
  applyExtraction(p: number, body: ExtractionApplyRequestDTO): Promise<ExtractionApplyReportDTO>;
  revertExtraction(p: number, receipt: ExtractionReceiptDTO): Promise<ExtractionApplyReportDTO>;

  // Format-specific structured data (authoring the writers)
  listGnPages(p: number): Promise<GnPageDTO[]>;
  createGnPage(p: number, body: GnPageDTO): Promise<GnPageDTO>;
  syncGnFromScenes(p: number): Promise<GnSyncResultDTO>;
  listGnContinuityItems(p: number): Promise<GnContinuityItemDTO[]>;
  createGnContinuityItem(p: number, body: GnContinuityItemDTO): Promise<GnContinuityItemDTO>;
  listGnContinuityAppearances(p: number, itemId: number): Promise<GnContinuityAppearanceDTO[]>;
  createGnContinuityAppearance(p: number, itemId: number, body: GnContinuityAppearanceDTO): Promise<GnContinuityAppearanceDTO>;
  listGnPanels(p: number, pageId: number): Promise<GnPanelDTO[]>;
  createGnPanel(p: number, pageId: number, body: GnPanelDTO): Promise<GnPanelDTO>;
  listStageCues(p: number, sceneId: number): Promise<StageCueDTO[]>;
  createStageCue(p: number, sceneId: number, body: StageCueDTO): Promise<StageCueDTO>;
  listStageEntrances(p: number, sceneId: number): Promise<StageEntranceExitDTO[]>;
  createStageEntrance(p: number, sceneId: number, body: StageEntranceExitDTO): Promise<StageEntranceExitDTO>;
  listStageBusiness(p: number, sceneId: number): Promise<StageBusinessDTO[]>;
  createStageBusiness(p: number, sceneId: number, body: StageBusinessDTO): Promise<StageBusinessDTO>;
  syncStageFromScenes(p: number): Promise<StageSyncResultDTO>;
  listSeasons(p: number): Promise<SeasonDTO[]>;
  createSeason(p: number, body: SeasonDTO): Promise<SeasonDTO>;
  listEpisodes(p: number): Promise<EpisodeDTO[]>;
  createEpisode(p: number, seasonId: number, body: EpisodeDTO): Promise<EpisodeDTO>;
  listSeriesArcs(p: number): Promise<SeriesArcDTO[]>;
  createSeriesArc(p: number, body: SeriesArcDTO): Promise<SeriesArcDTO>;
  listEpisodePlotlines(p: number, episodeId: number): Promise<EpisodePlotlineDTO[]>;
  createEpisodePlotline(p: number, episodeId: number, body: EpisodePlotlineDTO): Promise<EpisodePlotlineDTO>;
  // Format-structure edit/delete (correct or prune a wrong entry, not only append)
  updateGnPage(p: number, pageId: number, body: Partial<GnPageDTO>): Promise<{ ok: boolean; updated: number }>;
  deleteGnPage(p: number, pageId: number): Promise<{ ok: boolean; deleted: number }>;
  updateGnPanel(p: number, panelId: number, body: Partial<GnPanelDTO>): Promise<{ ok: boolean; updated: number }>;
  deleteGnPanel(p: number, panelId: number): Promise<{ ok: boolean; deleted: number }>;
  updateSeason(p: number, seasonId: number, body: Partial<SeasonDTO>): Promise<{ ok: boolean; updated: number }>;
  deleteSeason(p: number, seasonId: number): Promise<{ ok: boolean; deleted: number }>;
  updateEpisode(p: number, episodeId: number, body: Partial<EpisodeDTO>): Promise<{ ok: boolean; updated: number }>;
  deleteEpisode(p: number, episodeId: number): Promise<{ ok: boolean; deleted: number }>;
  updateSeriesArc(p: number, arcId: number, body: Partial<SeriesArcDTO>): Promise<{ ok: boolean; updated: number }>;
  deleteStageEntrance(p: number, rowId: number): Promise<{ ok: boolean; deleted: number }>;
  deleteStageCue(p: number, rowId: number): Promise<{ ok: boolean; deleted: number }>;
  // Class-C feature completions (update/delete the DB previously lacked)
  deleteSeriesArc(p: number, arcId: number): Promise<{ ok: boolean; deleted: number }>;
  updateEpisodePlotline(p: number, plotlineId: number, body: Partial<EpisodePlotlineDTO>): Promise<{ ok: boolean; updated: number }>;
  deleteEpisodePlotline(p: number, plotlineId: number): Promise<{ ok: boolean; deleted: number }>;
  updateGnContinuityItem(p: number, itemId: number, body: Partial<GnContinuityItemDTO>): Promise<{ ok: boolean; updated: number }>;
  deleteGnContinuityItem(p: number, itemId: number): Promise<{ ok: boolean; deleted: number }>;
  updateGnContinuityAppearance(p: number, appearanceId: number, body: Partial<GnContinuityAppearanceDTO>): Promise<{ ok: boolean; updated: number }>;
  deleteGnContinuityAppearance(p: number, appearanceId: number): Promise<{ ok: boolean; deleted: number }>;
  updateStageEntrance(p: number, rowId: number, body: Partial<StageEntranceExitDTO>): Promise<{ ok: boolean; updated: number }>;
  updateStageCue(p: number, rowId: number, body: Partial<StageCueDTO>): Promise<{ ok: boolean; updated: number }>;
  deleteStageBusiness(p: number, rowId: number): Promise<{ ok: boolean; deleted: number }>;
  updateContinuity(p: number, sceneId: number, memoryId: number, body: ContinuityMemoryDTO): Promise<ContinuityMemoryDTO>;
  deleteContinuity(p: number, sceneId: number, memoryId: number): Promise<{ ok: boolean; deleted: number }>;
  getSeriesMemory(p: number, entryId: number): Promise<SeriesMemoryDTO>;
  setSeriesMemory(p: number, entryId: number, body: SeriesMemoryDTO): Promise<SeriesMemoryDTO>;

  // Live events — subscribe; returns an unsubscribe fn.
  subscribe(p: number, onEvent: (e: EventMessage) => void): () => void;
}
