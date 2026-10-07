import { ROUTES } from '../dist/routes.js';
import { KNOWN_EVENTS } from '../dist/events.js';
import { readFileSync } from 'node:fs';

const actual = ROUTES.plotBlock(42, 'A Plot / Main');
const expected = '/api/projects/42/plot/blocks/A%20Plot%20%2F%20Main';

if (actual !== expected) {
  throw new Error(`plotBlock route mismatch: expected ${expected}, got ${actual}`);
}

const commentRoutes = [
  ROUTES.comments(42),
  ROUTES.comment(42, 7),
  ROUTES.commentReplies(42, 7),
  ROUTES.commentReply(42, 7, 9),
];
const expectedCommentRoutes = [
  '/api/projects/42/comments',
  '/api/projects/42/comments/7',
  '/api/projects/42/comments/7/replies',
  '/api/projects/42/comments/7/replies/9',
];
if (JSON.stringify(commentRoutes) !== JSON.stringify(expectedCommentRoutes)) {
  throw new Error(`comment route mismatch: expected ${expectedCommentRoutes}, got ${commentRoutes}`);
}
if (!KNOWN_EVENTS.includes('comments_changed')) {
  throw new Error('comments_changed is missing from the known project events');
}

const psykeConsoleRoute = ROUTES.psykeConsoleSuggestions(42);
if (psykeConsoleRoute !== '/api/projects/42/psyke/console/suggestions') {
  throw new Error(`PSYKE Console route mismatch: ${psykeConsoleRoute}`);
}

const projectSearchRoute = ROUTES.projectSearch(42);
if (projectSearchRoute !== '/api/projects/42/search') {
  throw new Error(`project search route mismatch: ${projectSearchRoute}`);
}

const knowledgeGraphRoute = ROUTES.knowledgeGraph(42);
if (knowledgeGraphRoute !== '/api/projects/42/knowledge-graph') {
  throw new Error(`knowledge graph route mismatch: ${knowledgeGraphRoute}`);
}
const knowledgeGraphCommandRoutes = [
  ROUTES.knowledgeGraphCommands(42),
  ROUTES.knowledgeGraphCommandReceipt(42),
  ROUTES.knowledgeGraphHiddenEdges(42),
];
const expectedKnowledgeGraphCommandRoutes = [
  '/api/projects/42/knowledge-graph/commands',
  '/api/projects/42/knowledge-graph/command-receipt',
  '/api/projects/42/knowledge-graph/hidden-edges',
];
if (JSON.stringify(knowledgeGraphCommandRoutes) !== JSON.stringify(expectedKnowledgeGraphCommandRoutes)) {
  throw new Error(`knowledge graph command route mismatch: ${knowledgeGraphCommandRoutes}`);
}
if (!KNOWN_EVENTS.includes('knowledge_graph_changed')) {
  throw new Error('knowledge_graph_changed is missing from the known project events');
}
const pythonKnowledgeGraphRoute = readFileSync(
  '../logosforge/logosforge/api/routes/knowledge_graph.py',
  'utf8',
);
if (!pythonKnowledgeGraphRoute.includes('"/projects/{project_id}/knowledge-graph"')) {
  throw new Error('Python knowledge graph route is missing or drifted');
}

const continuityRoutes = [
  ROUTES.continuity(42),
  ROUTES.continuityCommands(42),
  ROUTES.continuityCommandReceipt(42),
];
const expectedContinuityRoutes = [
  '/api/projects/42/continuity',
  '/api/projects/42/continuity/commands',
  '/api/projects/42/continuity/command-receipt',
];
if (JSON.stringify(continuityRoutes) !== JSON.stringify(expectedContinuityRoutes)) {
  throw new Error(`Continuity command route mismatch: ${continuityRoutes}`);
}
if (!KNOWN_EVENTS.includes('continuity_changed')) {
  throw new Error('continuity_changed is missing from the known project events');
}
const pythonContinuityRoute = readFileSync(
  '../logosforge/logosforge/api/routes/intelligence.py',
  'utf8',
);
for (const route of [
  '"/projects/{project_id}/continuity"',
  '"/projects/{project_id}/continuity/commands"',
  '"/projects/{project_id}/continuity/command-receipt"',
]) {
  if (!pythonContinuityRoute.includes(route)) {
    throw new Error(`Python Continuity route is missing or drifted: ${route}`);
  }
}

if (ROUTES.liveContext !== '/api/live-context') {
  throw new Error(`live context route mismatch: ${ROUTES.liveContext}`);
}

const storyStructureRoute = ROUTES.storyStructure(42);
if (storyStructureRoute !== '/api/projects/42/story-structure') {
  throw new Error(`story structure route mismatch: ${storyStructureRoute}`);
}
const storyStructureCommandsRoute = ROUTES.storyStructureCommands(42);
if (storyStructureCommandsRoute !== '/api/projects/42/story-structure/commands') {
  throw new Error(`story structure commands route mismatch: ${storyStructureCommandsRoute}`);
}
const scenePlacementRoute = ROUTES.scenePlacement(42, 7);
if (scenePlacementRoute !== '/api/projects/42/story-structure/scenes/7/placement') {
  throw new Error(`scene placement route mismatch: ${scenePlacementRoute}`);
}

const manuscriptSnapshotRoute = ROUTES.manuscriptSnapshot(42);
if (manuscriptSnapshotRoute !== '/api/projects/42/manuscript-snapshot') {
  throw new Error(`manuscript snapshot route mismatch: ${manuscriptSnapshotRoute}`);
}

const timelineCommandsRoute = ROUTES.timelineCommands(42);
if (timelineCommandsRoute !== '/api/projects/42/timeline/commands') {
  throw new Error(`timeline commands route mismatch: ${timelineCommandsRoute}`);
}
const timelineReceiptRoute = ROUTES.timelineCommandReceipt(42);
if (timelineReceiptRoute !== '/api/projects/42/timeline/command-receipt') {
  throw new Error(`timeline command receipt route mismatch: ${timelineReceiptRoute}`);
}
if ('timelineEvents' in ROUTES || 'timelineEvent' in ROUTES) {
  throw new Error('legacy unguarded Timeline mutation routes must not be advertised');
}

const canvasPlotRoutes = [
  ROUTES.canvasPlot(42),
  ROUTES.canvasPlotCommands(42),
  ROUTES.canvasPlotCommandReceipt(42),
];
const expectedCanvasPlotRoutes = [
  '/api/projects/42/canvas-plot',
  '/api/projects/42/canvas-plot/commands',
  '/api/projects/42/canvas-plot/command-receipt',
];
if (JSON.stringify(canvasPlotRoutes) !== JSON.stringify(expectedCanvasPlotRoutes)) {
  throw new Error(`Canvas Plot route mismatch: ${canvasPlotRoutes}`);
}
if (!KNOWN_EVENTS.includes('canvas_plot_changed')) {
  throw new Error('canvas_plot_changed is missing from the known project events');
}

const psykeCommandRoutes = [
  ROUTES.psykeConsolePlan(42),
  ROUTES.psykeConsoleExecute(42),
];
const expectedPsykeCommandRoutes = [
  '/api/projects/42/psyke/console/plan',
  '/api/projects/42/psyke/console/execute',
];
if (JSON.stringify(psykeCommandRoutes) !== JSON.stringify(expectedPsykeCommandRoutes)) {
  throw new Error(`PSYKE command route mismatch: ${psykeCommandRoutes}`);
}

const workflowRoutes = [
  ROUTES.workflowTemplates(42),
  ROUTES.workflowRecommendations(42),
  ROUTES.workflows(42),
  ROUTES.workflowRun(42, 7),
  ROUTES.workflowEvents(42, 7),
  ROUTES.workflowCommands(42),
  ROUTES.workflowCommandReceipt(42),
];
const expectedWorkflowRoutes = [
  '/api/projects/42/workflow-templates',
  '/api/projects/42/workflow-recommendations',
  '/api/projects/42/workflows',
  '/api/projects/42/workflows/7',
  '/api/projects/42/workflows/7/events',
  '/api/projects/42/workflows/commands',
  '/api/projects/42/workflows/command-receipt',
];
if (JSON.stringify(workflowRoutes) !== JSON.stringify(expectedWorkflowRoutes)) {
  throw new Error(`Guided Workflow route mismatch: ${workflowRoutes}`);
}
if (!KNOWN_EVENTS.includes('workflow_changed')) {
  throw new Error('workflow_changed is missing from the known project events');
}
const pythonWorkflowRoute = readFileSync(
  '../logosforge/logosforge/api/routes/workflows.py',
  'utf8',
);
for (const route of [
  '"/projects/{project_id}/workflow-templates"',
  '"/projects/{project_id}/workflow-recommendations"',
  '"/projects/{project_id}/workflows"',
  '"/projects/{project_id}/workflows/{run_id}"',
  '"/projects/{project_id}/workflows/{run_id}/events"',
  '"/projects/{project_id}/workflows/commands"',
  '"/projects/{project_id}/workflows/command-receipt"',
]) {
  if (!pythonWorkflowRoute.includes(route)) {
    throw new Error(`Python Guided Workflow route is missing or drifted: ${route}`);
  }
}

console.log('Contract route/event tests: 16 passed, 0 failed');

const pythonSchemas = readFileSync('../logosforge/logosforge/api/schemas.py', 'utf8');
const typescriptSchemas = readFileSync('src/types.ts', 'utf8');
const pythonDtos = new Set([
  ...[...pythonSchemas.matchAll(/^class\s+(\w+DTO)\b/gm)].map((match) => match[1]),
  ...[...pythonSchemas.matchAll(/^(\w+DTO)\s*=\s*Annotated\[/gm)].map((match) => match[1]),
]);
const typescriptDtos = new Set(
  [...typescriptSchemas.matchAll(/^export\s+(?:interface|type)\s+(\w+DTO)\b/gm)]
    .map((match) => match[1]),
);
const onlyPython = [...pythonDtos].filter((name) => !typescriptDtos.has(name)).sort();
const onlyTypescript = [...typescriptDtos].filter((name) => !pythonDtos.has(name)).sort();
if (onlyPython.length || onlyTypescript.length) {
  throw new Error(
    `DTO drift detected. Python-only: ${onlyPython.join(', ') || '(none)'}; `
    + `TypeScript-only: ${onlyTypescript.join(', ') || '(none)'}`,
  );
}

console.log(`DTO parity tests: ${pythonDtos.size} Python = ${typescriptDtos.size} TypeScript`);

const episodeScopedStructureCommands = [
  'StoryStructureRenameActCommandDTO',
  'StoryStructureRenameChapterCommandDTO',
  'StoryStructureDetachActCommandDTO',
  'StoryStructureDetachChapterCommandDTO',
];
for (const dtoName of episodeScopedStructureCommands) {
  const pythonBody = pythonSchemas.match(new RegExp(
    `class ${dtoName}\\([^)]*\\):([\\s\\S]*?)\\n\\nclass `,
  ))?.[1] ?? '';
  const typescriptBody = typescriptSchemas.match(new RegExp(
    `export interface ${dtoName}[^\\{]*\\{([\\s\\S]*?)\\n\\}`,
  ))?.[1] ?? '';
  if (!pythonBody.includes('episode_id:')) {
    throw new Error(`Python ${dtoName} is missing episode_id`);
  }
  if (!typescriptBody.includes('episode_id?: number | null')) {
    throw new Error(`TypeScript ${dtoName} is missing optional nullable episode_id`);
  }
}

console.log('Series structure command parity tests: 4 episode-scoped DTOs mirrored');

const pythonWhiteboardAnchor = pythonSchemas.match(
  /class WhiteboardImportCommentAnchorDTO\(BaseModel\):([\s\S]*?)\n\nclass /,
)?.[1] ?? '';
const typescriptWhiteboardAnchor = typescriptSchemas.match(
  /export interface WhiteboardImportCommentAnchorDTO \{([\s\S]*?)\n\}/,
)?.[1] ?? '';
for (const field of ['surface', 'drafter_page_id']) {
  if (!pythonWhiteboardAnchor.includes(`${field}:`)) {
    throw new Error(`Python WhiteboardImportCommentAnchorDTO is missing ${field}`);
  }
  if (!typescriptWhiteboardAnchor.includes(`${field}?`)) {
    throw new Error(`TypeScript WhiteboardImportCommentAnchorDTO is missing optional ${field}`);
  }
}

console.log('Whiteboard comment-scope parity tests: 2 fields mirrored');

const workflowDtoFields = {
  WorkflowTemplateStepDTO: [
    'id', 'title', 'description', 'kind', 'section_name', 'action_id',
    'completion_check', 'modes',
  ],
  WorkflowTemplateDTO: [
    'id', 'title', 'description', 'category', 'modes', 'steps',
  ],
  WorkflowRecommendationDTO: ['template_id', 'title', 'reason', 'severity'],
  WorkflowStepDTO: [
    'step_id', 'title', 'description', 'kind', 'status', 'sort_index',
    'section_name', 'action_id', 'completion_check', 'notes', 'target_type',
    'target_id', 'created_at', 'updated_at',
  ],
  WorkflowRunDTO: [
    'id', 'project_id', 'title', 'description', 'status', 'writing_mode',
    'template_id', 'current_step_id', 'total_steps', 'completed_steps',
    'revision', 'source_type', 'source_id', 'created_at', 'updated_at',
    'completed_at', 'steps',
  ],
  WorkflowEventDTO: [
    'id', 'project_id', 'workflow_run_id', 'step_id', 'event_type', 'message',
    'metadata', 'created_at',
  ],
  WorkflowStartCommandDTO: ['kind', 'template_id', 'title'],
  WorkflowCompleteStepCommandDTO: ['kind', 'step_id', 'notes'],
  WorkflowSkipStepCommandDTO: ['kind', 'step_id', 'notes'],
  WorkflowAdvanceCommandDTO: ['kind'],
  WorkflowRefreshCommandDTO: ['kind'],
  WorkflowPauseCommandDTO: ['kind'],
  WorkflowResumeCommandDTO: ['kind'],
  WorkflowCancelCommandDTO: ['kind'],
  WorkflowCommandResultDTO: [
    'workflow', 'changed', 'replayed', 'applied_revision',
  ],
  WorkflowCommandReceiptDTO: [
    'project_id', 'request_digest', 'command_kind', 'expected_revision',
    'applied_revision', 'original_changed', 'original_run_id', 'committed_at',
  ],
};
for (const [dtoName, fields] of Object.entries(workflowDtoFields)) {
  const pythonBody = pythonSchemas.match(new RegExp(
    `class ${dtoName}\\([^)]*\\):([\\s\\S]*?)\\n\\n(?:class |WorkflowCommandKind = )`,
  ))?.[1] ?? '';
  const typescriptBody = typescriptSchemas.match(new RegExp(
    `export interface ${dtoName}[^\\{]*\\{([\\s\\S]*?)\\n\\}`,
  ))?.[1] ?? '';
  for (const field of fields) {
    if (!pythonBody.includes(`${field}:`)) {
      throw new Error(`Python ${dtoName} is missing ${field}`);
    }
    if (!typescriptBody.includes(field)) {
      throw new Error(`TypeScript ${dtoName} is missing ${field}`);
    }
  }
}

const workflowKinds = [
  'start_workflow', 'complete_step', 'skip_step', 'advance', 'refresh',
  'pause', 'resume', 'cancel',
];
for (const kind of workflowKinds) {
  if (!pythonSchemas.includes(`Literal["${kind}"]`)) {
    throw new Error(`Python WorkflowCommandDTO is missing kind ${kind}`);
  }
  if (!typescriptSchemas.includes(`kind: "${kind}"`)) {
    throw new Error(`TypeScript WorkflowCommandDTO is missing kind ${kind}`);
  }
}

const pythonWorkflowRevisionBase = pythonSchemas.match(
  /class _WorkflowRevisionCommandBase\(BaseModel\):([\s\S]*?)\n\nclass /,
)?.[1] ?? '';
const typescriptWorkflowRevisionBase = typescriptSchemas.match(
  /interface WorkflowRevisionCommandBase \{([\s\S]*?)\n\}/,
)?.[1] ?? '';
for (const field of ['run_id', 'expected_revision']) {
  if (!pythonWorkflowRevisionBase.includes(`${field}:`)) {
    throw new Error(`Python Workflow revision command base is missing ${field}`);
  }
  if (!typescriptWorkflowRevisionBase.includes(`${field}:`)) {
    throw new Error(`TypeScript Workflow revision command base is missing ${field}`);
  }
}

const pythonApiApp = readFileSync('../logosforge/logosforge/api/app.py', 'utf8');
if (!pythonApiApp.includes('API_CONTRACT_VERSION = "1.16.0"')) {
  throw new Error('Transactional event outbox reconciliation must ship as HTTP contract 1.16.0');
}
const pythonEventsPoll = pythonSchemas.match(
  /class EventsPollDTO\(BaseModel\):([\s\S]*?)\n\nclass /,
)?.[1] ?? '';
const typescriptEventsPoll = typescriptSchemas.match(
  /export interface EventsPollDTO \{([\s\S]*?)\n\}/,
)?.[1] ?? '';
for (const field of ['events', 'cursor', 'broker_instance_id', 'reset_required', 'known_events']) {
  if (!pythonEventsPoll.includes(`${field}:`)) {
    throw new Error(`Python EventsPollDTO is missing ${field}`);
  }
  if (!typescriptEventsPoll.includes(`${field}:`)) {
    throw new Error(`TypeScript EventsPollDTO is missing ${field}`);
  }
}

console.log('Guided Workflow contract parity tests: routes/event + 16 DTOs mirrored');

const timelineRelationshipDtoFields = {
  TimelineLinkDTO: [
    'id', 'source_scene_id', 'target_scene_id', 'link_type', 'color_label',
    'label', 'created_at',
  ],
  TimelineStructureLinkDTO: [
    'id', 'source_scene_id', 'target_type', 'target_ref', 'target_exists',
    'created_at',
  ],
  TimelineSnapshotDTO: [
    'project_id', 'revision', 'order_mode', 'lanes', 'events', 'links',
    'structure_links', 'off_timeline', 'story_flow', 'mode_projection',
  ],
  TimelineCreateLinkCommandDTO: [
    'kind', 'source_scene_id', 'target_scene_id',
    'link_type', 'color_label', 'label',
  ],
  TimelineUpdateLinkCommandDTO: [
    'kind', 'link_id', 'link_type', 'color_label', 'label',
  ],
  TimelineDeleteLinkCommandDTO: ['kind', 'link_id'],
  TimelineCreateStructureLinkCommandDTO: [
    'kind', 'source_scene_id', 'target_type', 'target_ref',
  ],
  TimelineUpdateStructureLinkCommandDTO: [
    'kind', 'structure_link_id', 'target_type', 'target_ref',
  ],
  TimelineDeleteStructureLinkCommandDTO: [
    'kind', 'structure_link_id',
  ],
  TimelineCommandResultDTO: [
    'timeline', 'changed', 'affected_scene_ids', 'affected_link_ids',
    'affected_structure_link_ids', 'created_link_id',
    'created_structure_link_id', 'replayed', 'applied_revision',
  ],
  TimelineCommandReceiptDTO: [
    'project_id', 'request_digest', 'command_kind', 'expected_revision',
    'applied_revision', 'original_changed', 'original_affected_scene_ids',
    'original_affected_link_ids', 'original_affected_structure_link_ids',
    'original_created_link_id', 'original_created_structure_link_id',
    'committed_at',
  ],
};
for (const [dtoName, fields] of Object.entries(timelineRelationshipDtoFields)) {
  const pythonBody = pythonSchemas.match(new RegExp(
    `class ${dtoName}\\([^)]*\\):([\\s\\S]*?)\\n\\n(?:class |#|_)`,
  ))?.[1] ?? '';
  const typescriptBody = typescriptSchemas.match(new RegExp(
    `export interface ${dtoName}[^\\{]*\\{([\\s\\S]*?)\\n\\}`,
  ))?.[1] ?? '';
  for (const field of fields) {
    if (!pythonBody.includes(`${field}:`)) {
      throw new Error(`Python ${dtoName} is missing ${field}`);
    }
    if (!typescriptBody.includes(field)) {
      throw new Error(`TypeScript ${dtoName} is missing ${field}`);
    }
  }
}
const pythonTimelineCommandBase = pythonSchemas.match(
  /class _TimelineCommandBase\(BaseModel\):([\s\S]*?)\n\nclass /,
)?.[1] ?? '';
const typescriptTimelineCommandBase = typescriptSchemas.match(
  /interface TimelineCommandBase \{([\s\S]*?)\n\}/,
)?.[1] ?? '';
if (!pythonTimelineCommandBase.includes('expected_revision:')
    || !typescriptTimelineCommandBase.includes('expected_revision:')) {
  throw new Error('Timeline command bases must mirror expected_revision');
}
const expectedTimelineLinkTypes = [
  'custom', 'causality', 'setup_payoff', 'echo', 'conflict', 'dependency',
];
const pythonTimelineLinkTypeBody = pythonSchemas.match(
  /class TimelineLinkDTO\(BaseModel\):[\s\S]*?link_type: Literal\[([\s\S]*?)\]\n/,
)?.[1] ?? '';
const typescriptTimelineLinkTypeBody = typescriptSchemas.match(
  /export type TimelineLinkType =([\s\S]*?);/,
)?.[1] ?? '';
const timelineLiteralValues = (body) => [...body.matchAll(/"([^"]+)"/g)].map((match) => match[1]);
if (JSON.stringify(timelineLiteralValues(pythonTimelineLinkTypeBody))
    !== JSON.stringify(expectedTimelineLinkTypes)
    || JSON.stringify(timelineLiteralValues(typescriptTimelineLinkTypeBody))
      !== JSON.stringify(expectedTimelineLinkTypes)) {
  throw new Error('TimelineLinkType must mirror the exact six supported semantics');
}
for (const kind of [
  'create_link', 'update_link', 'delete_link',
  'create_structure_link', 'update_structure_link', 'delete_structure_link',
]) {
  if (!pythonSchemas.includes(`Literal["${kind}"]`)) {
    throw new Error(`Python TimelineCommandDTO is missing kind ${kind}`);
  }
  if (!typescriptSchemas.includes(`kind: "${kind}"`)) {
    throw new Error(`TypeScript TimelineCommandDTO is missing kind ${kind}`);
  }
}

console.log('Timeline relationship contract parity tests: 11 DTOs + 6 commands mirrored');

const timelineProjectionDtoFields = {
  TimelineStoryFlowPointDTO: [
    'scene_id', 'order_index', 'tension_value', 'tension_source', 'scene_type',
    'dialogue_ratio', 'action_ratio',
  ],
  TimelinePacingWarningDTO: [
    'start_scene_id', 'end_scene_id', 'scene_ids', 'reason',
  ],
  TimelineStoryFlowDTO: ['points', 'warnings'],
  TimelineNovelModeProjectionDTO: ['kind'],
  TimelineScreenplaySceneProjectionDTO: [
    'scene_id', 'interior_exterior', 'cinematic_pacing', 'dramatic_turn',
    'emotional_turn', 'objective', 'conflict', 'turning_point',
    'emotional_shift', 'visual_beat_count',
  ],
  TimelineScreenplayModeProjectionDTO: ['kind', 'scenes'],
  TimelineGraphicNovelPageProjectionDTO: [
    'page_id', 'page_number', 'sequence_id', 'issue_id', 'issue_title',
    'density', 'rhythm', 'reveal_timing', 'splash_page', 'panel_count',
    'action_density', 'text_load', 'pacing', 'is_silence', 'is_action',
  ],
  TimelineGraphicNovelPageTurnDTO: [
    'setup_page_id', 'setup_page_number', 'reveal_page_id',
    'reveal_page_number', 'reveal_type',
  ],
  TimelineGraphicNovelModeProjectionDTO: ['kind', 'pages', 'page_turns'],
  TimelineStageEntranceExitProjectionDTO: [
    'character', 'type', 'moment_order', 'cue_text',
  ],
  TimelineStageCueProjectionDTO: ['type', 'text', 'moment_order'],
  TimelineStageSceneProjectionDTO: [
    'scene_id', 'order_index', 'act', 'title', 'entrances_exits', 'cues',
    'offstage_events', 'has_offstage_events', 'props', 'emotional_pressure',
  ],
  TimelineStageScriptModeProjectionDTO: ['kind', 'scenes'],
  TimelineSeriesArcProjectionDTO: ['arc_id', 'title', 'scope', 'status'],
  TimelineSeriesEpisodeProjectionDTO: [
    'episode_id', 'order_index', 'season_id', 'season', 'episode_number',
    'title', 'cliffhanger', 'scene_ids', 'active_arcs', 'setup_arc_ids',
    'payoff_arc_ids',
  ],
  TimelineSeriesArcChainDTO: [
    'arc_id', 'title', 'scope', 'setup_episode_id', 'payoff_episode_id',
    'setup_order_index', 'payoff_order_index',
  ],
  TimelineSeriesModeProjectionDTO: [
    'kind', 'episodes', 'arc_chains', 'unassigned_scene_ids',
  ],
};
for (const [dtoName, fields] of Object.entries(timelineProjectionDtoFields)) {
  const pythonBody = pythonSchemas.match(new RegExp(
    `class ${dtoName}\\([^)]*\\):([\\s\\S]*?)\\n\\n(?:class |TimelineModeProjectionDTO)`,
  ))?.[1] ?? '';
  const typescriptBody = typescriptSchemas.match(new RegExp(
    `export interface ${dtoName}[^\\{]*\\{([\\s\\S]*?)\\n\\}`,
  ))?.[1] ?? '';
  for (const field of fields) {
    if (!pythonBody.includes(`${field}:`)) {
      throw new Error(`Python ${dtoName} is missing ${field}`);
    }
    if (!typescriptBody.includes(`${field}:`)) {
      throw new Error(`TypeScript ${dtoName} is missing ${field}`);
    }
  }
}
for (const kind of ['novel', 'screenplay', 'graphic_novel', 'stage_script', 'series']) {
  if (!pythonSchemas.includes(`kind: Literal["${kind}"]`)
      || !typescriptSchemas.includes(`kind: "${kind}"`)) {
    throw new Error(`TimelineModeProjectionDTO is missing discriminator ${kind}`);
  }
}
if (!pythonSchemas.includes('Field(discriminator="kind")')
    || !typescriptSchemas.includes('export type TimelineModeProjectionDTO =')) {
  throw new Error('TimelineModeProjectionDTO must remain a required discriminated union');
}

console.log('Timeline Phase 7C contract parity tests: story-flow + 5 mode projections mirrored');

const decisionRadarDtoFields = {
  DecisionEvidenceDTO: [
    'kind', 'label', 'detail', 'graph_focus_key', 'source_key', 'target_key',
    'edge_type', 'confidence', 'source_system', 'provenance',
    'related_section', 'related_target_type', 'related_target_id',
    'related_target_key',
  ],
  DecisionCardDTO: [
    'id', 'category', 'severity', 'confidence', 'title', 'explanation',
    'suggested_action', 'related_section', 'related_target_type',
    'related_target_id', 'related_target_key', 'created_from',
    'graph_focus_key', 'graph_view_mode',
    'graph_include_inferred', 'graph_depth', 'evidence', 'evidence_total',
  ],
  DecisionRadarDTO: [
    'project_id', 'generated_light', 'summary_line', 'radar',
    'knowledge_graph_available', 'knowledge_graph_cards',
    'continuity_available', 'continuity_cards',
  ],
};
for (const [dtoName, fields] of Object.entries(decisionRadarDtoFields)) {
  const pythonBody = pythonSchemas.match(new RegExp(
    `class ${dtoName}\\([^)]*\\):([\\s\\S]*?)\\n\\nclass `,
  ))?.[1] ?? '';
  const typescriptBody = typescriptSchemas.match(new RegExp(
    `export interface ${dtoName}[^\\{]*\\{([\\s\\S]*?)\\n\\}`,
  ))?.[1] ?? '';
  for (const field of fields) {
    if (!pythonBody.includes(`${field}:`)) {
      throw new Error(`Python ${dtoName} is missing ${field}`);
    }
    if (!typescriptBody.includes(`${field}`)) {
      throw new Error(`TypeScript ${dtoName} is missing ${field}`);
    }
  }
}

console.log('Decision Radar contract parity tests: traceable graph evidence mirrored');

const graphDtoFields = {
  KnowledgeGraphQueryDTO: ['focus_key', 'depth', 'limit', 'include_inferred', 'view_mode'],
  KnowledgeGraphNodeDTO: [
    'key', 'node_type', 'source_type', 'source_id', 'label', 'summary', 'metadata', 'degree',
  ],
  KnowledgeGraphEdgeDTO: [
    'source', 'target', 'edge_type', 'confidence', 'provenance', 'source_system',
    'explanation', 'is_user_confirmed', 'is_inferred', 'is_hidden', 'metadata',
  ],
  KnowledgeGraphReadDTO: [
    'project_id', 'revision', 'writing_mode', 'focus_key', 'depth', 'include_inferred',
    'view_mode', 'story_diagnostics_available', 'nodes', 'edges',
    'node_count', 'edge_count', 'returned_node_count', 'returned_edge_count', 'truncated',
    'orphan_keys', 'orphan_count', 'weak_links', 'weak_link_count', 'hidden_edges',
    'hidden_edge_count', 'warnings', 'unavailable',
  ],
  KnowledgeGraphEdgeIdentityDTO: ['source', 'target', 'edge_type'],
  KnowledgeGraphCommandResultDTO: [
    'knowledge_graph', 'changed', 'affected_edge', 'replayed', 'applied_revision',
  ],
  KnowledgeGraphCommandReceiptDTO: [
    'project_id', 'request_digest', 'command_kind', 'expected_revision', 'applied_revision',
    'original_changed', 'original_affected_edge', 'committed_at',
  ],
  KnowledgeGraphHiddenEdgePageDTO: [
    'project_id', 'revision', 'offset', 'limit', 'hidden_edge_count',
    'returned_edge_count', 'nodes', 'edges',
  ],
};
for (const [dtoName, fields] of Object.entries(graphDtoFields)) {
  const pythonBody = pythonSchemas.match(new RegExp(
    `class ${dtoName}\\([^)]*\\):([\\s\\S]*?)\\n\\n(?:class |[A-Z][A-Za-z]+ = )`,
  ))?.[1] ?? '';
  const typescriptBody = typescriptSchemas.match(new RegExp(
    `export interface ${dtoName}[^\\{]*\\{([\\s\\S]*?)\\n\\}`,
  ))?.[1] ?? '';
  for (const field of fields) {
    if (!pythonBody.includes(`${field}:`)) {
      throw new Error(`Python ${dtoName} is missing ${field}`);
    }
    if (!typescriptBody.includes(`${field}`)) {
      throw new Error(`TypeScript ${dtoName} is missing ${field}`);
    }
  }
}

console.log('Knowledge Graph contract parity tests: routes/events + 8 DTOs mirrored');

const continuityDtoFields = {
  ContinuityReportDTO: [
    'project_id', 'review_revision', 'writing_mode', 'issues',
    'blocking_count', 'warning_count', 'unavailable',
  ],
  ContinuityCommandResultDTO: [
    'continuity', 'changed', 'affected_issue_id', 'previous_status',
    'status', 'replayed', 'applied_revision',
  ],
  ContinuityCommandReceiptDTO: [
    'project_id', 'request_digest', 'command_kind', 'expected_revision',
    'applied_revision', 'original_changed', 'original_affected_issue_id',
    'expected_issue_fingerprint',
    'previous_status', 'status', 'committed_at',
  ],
};
for (const [dtoName, fields] of Object.entries(continuityDtoFields)) {
  const pythonBody = pythonSchemas.match(new RegExp(
    `class ${dtoName}\\([^)]*\\):([\\s\\S]*?)\\n\\nclass `,
  ))?.[1] ?? '';
  const typescriptBody = typescriptSchemas.match(new RegExp(
    `export interface ${dtoName}[^\\{]*\\{([\\s\\S]*?)\\n\\}`,
  ))?.[1] ?? '';
  for (const field of fields) {
    if (!pythonBody.includes(`${field}:`)) {
      throw new Error(`Python ${dtoName} is missing ${field}`);
    }
    if (!typescriptBody.includes(`${field}`)) {
      throw new Error(`TypeScript ${dtoName} is missing ${field}`);
    }
  }
}

console.log('Continuity contract parity tests: routes/events + 3 DTOs mirrored');

const knowledgeGraphViewModes = [
  'project_map', 'structure', 'recorded_risk', 'revision_impact',
];
const pythonViewMode = pythonSchemas.match(
  /KnowledgeGraphViewMode\s*=\s*Literal\[([^\]]+)\]/,
)?.[1] ?? '';
const typescriptViewMode = typescriptSchemas.match(
  /export type KnowledgeGraphViewMode\s*=([\s\S]*?);/,
)?.[1] ?? '';
const literalValues = (source) => [...source.matchAll(/["']([^"']+)["']/g)]
  .map((match) => match[1]);
for (const [surface, actual] of [
  ['Python', literalValues(pythonViewMode)],
  ['TypeScript', literalValues(typescriptViewMode)],
]) {
  if (JSON.stringify(actual) !== JSON.stringify(knowledgeGraphViewModes)) {
    throw new Error(
      `${surface} KnowledgeGraphViewMode must exactly match ${knowledgeGraphViewModes.join(', ')}; got ${actual.join(', ')}`,
    );
  }
}

console.log('Knowledge Graph view-mode parity tests: 4 literal modes mirrored');
