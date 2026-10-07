import { ApiRequestError, createHttpApiClient } from '../src/adapters/httpApiClient';
import { flushPendingProjectSaves } from '../src/adapters/projectSaveCoordinator';

const originalFetch = globalThis.fetch;
const requests: Array<{ input: string; init: RequestInit }> = [];
const project = (id: number, title: string) => ({
  id,
  title,
  description: "",
  narrative_engine: "novel",
  default_writing_format: "prose",
  format_mode: "novel",
});
globalThis.fetch = async (input: RequestInfo | URL, init: RequestInit = {}) => {
  requests.push({ input: String(input), init });
  return new Response(JSON.stringify({ status: 'ok' }), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
};

try {
  const secured = createHttpApiClient('http://127.0.0.1:8765', 'session-secret');
  await secured.health();
  let headers = new Headers(requests.at(-1)?.init.headers);
  if (headers.get('authorization') !== 'Bearer session-secret') {
    throw new Error('Bearer token was not attached to the core request');
  }
  if (headers.get('content-type') !== 'application/json') {
    throw new Error('JSON content type was not preserved');
  }

  const browser = createHttpApiClient('');
  await browser.health();
  headers = new Headers(requests.at(-1)?.init.headers);
  if (headers.has('authorization')) {
    throw new Error('Unauthenticated browser client unexpectedly sent Authorization');
  }
  const suggestionAbort = new AbortController();
  await browser.getPsykeConsoleSuggestions(42, '/open Vesper', 7, suggestionAbort.signal);
  const consoleUrl = requests.at(-1)?.input ?? '';
  if (consoleUrl !== '/api/projects/42/psyke/console/suggestions?q=%2Fopen+Vesper&scene_id=7') {
    throw new Error(`PSYKE Console query was not encoded correctly: ${consoleUrl}`);
  }
  if (requests.at(-1)?.init.signal == null) {
    throw new Error('PSYKE Console request did not forward its cancellation signal');
  }

  globalThis.fetch = async (input: RequestInfo | URL, init: RequestInit = {}) => {
    requests.push({ input: String(input), init });
    return new Response(JSON.stringify({
      query: 'Vesper Vale',
      matches: [{ kind: 'psyke', id: 8, title: 'Vesper Vale', excerpt: 'A conflicted ally.' }],
      limit: 40,
    }), { status: 200, headers: { 'content-type': 'application/json' } });
  };
  const searchAbort = new AbortController();
  await browser.searchProject(42, 'Vesper Vale', ['scene', 'psyke'], searchAbort.signal);
  const searchUrl = requests.at(-1)?.input ?? '';
  if (searchUrl !== '/api/projects/42/search?q=Vesper+Vale&kinds=scene&kinds=psyke') {
    throw new Error(`Project search query was not encoded correctly: ${searchUrl}`);
  }
  if (requests.at(-1)?.init.signal == null) {
    throw new Error('Project search request did not forward its cancellation signal');
  }

  let releasePlan!: (response: Response) => void;
  globalThis.fetch = (input: RequestInfo | URL, init: RequestInit = {}) => {
    requests.push({ input: String(input), init });
    return new Promise<Response>((resolve) => { releasePlan = resolve; });
  };
  const planAbort = new AbortController();
  const pendingPlan = browser.planPsykeConsoleCommand(
    42,
    { command: '/create character Vesper Vale', active_scene_id: 7 },
    planAbort.signal,
  );
  for (let i = 0; i < 4; i++) await Promise.resolve();
  let planBarrierDone = false;
  await flushPendingProjectSaves().then(() => { planBarrierDone = true; });
  if (!planBarrierDone) throw new Error('Read-only command planning blocked the persistence barrier');
  const planRequest = requests.at(-1);
  if (planRequest?.input !== '/api/projects/42/psyke/console/plan'
      || planRequest.init.method !== 'POST'
      || planRequest.init.signal == null) {
    throw new Error('PSYKE command plan request was not routed as a cancellable POST');
  }
  const planBody = JSON.parse(String(planRequest.init.body));
  if (planBody.command !== '/create character Vesper Vale' || planBody.active_scene_id !== 7) {
    throw new Error('PSYKE command plan body was not preserved');
  }
  releasePlan(new Response(JSON.stringify({
    plan_id: 'lfcp_test', command: 'create', normalized_command: '/create character Vesper Vale',
    action: 'create_psyke_entry', summary: "Create character 'Vesper Vale'",
    effects: ['Add one entry.'], requires_confirmation: true, mutates: true,
    target_type: 'psyke_entry', target_id: null, expires_at: '2026-09-30T12:00:00Z',
  }), { status: 200, headers: { 'content-type': 'application/json' } }));
  const planned = await pendingPlan;
  if (planned.plan_id !== 'lfcp_test' || planned.mutates !== true) {
    throw new Error('PSYKE command plan response was not validated');
  }

  let releaseExecute!: (response: Response) => void;
  globalThis.fetch = (input: RequestInfo | URL, init: RequestInit = {}) => {
    requests.push({ input: String(input), init });
    return new Promise<Response>((resolve) => { releaseExecute = resolve; });
  };
  const pendingExecute = browser.executePsykeConsoleCommand(
    42,
    { plan_id: planned.plan_id, confirmed: true },
    planned.mutates,
  );
  let executeBarrierDone = false;
  const executeBarrier = flushPendingProjectSaves().then(() => { executeBarrierDone = true; });
  for (let i = 0; i < 6; i++) await Promise.resolve();
  if (executeBarrierDone) throw new Error('Confirmed command execution escaped the handoff barrier');
  const executeRequest = requests.at(-1);
  if (executeRequest?.input !== '/api/projects/42/psyke/console/execute'
      || executeRequest.init.method !== 'POST') {
    throw new Error('PSYKE command execute request used the wrong route or method');
  }
  const executeBody = JSON.parse(String(executeRequest.init.body));
  if (executeBody.plan_id !== 'lfcp_test' || executeBody.confirmed !== true
      || 'action' in executeBody || 'args' in executeBody) {
    throw new Error('PSYKE command execute body was not capability-only');
  }
  releaseExecute(new Response(JSON.stringify({
    ok: true, action: 'create_psyke_entry', message: 'Created Vesper Vale.',
    mutated: true, target_type: 'psyke_entry', target_id: 9,
  }), { status: 200, headers: { 'content-type': 'application/json' } }));
  await Promise.all([pendingExecute, executeBarrier]);
  if (!executeBarrierDone) throw new Error('Command execution did not release the handoff barrier');

  globalThis.fetch = async () => new Response(
    JSON.stringify({ error: { code: 'assistant_error', message: 'Provider unavailable' } }),
    { status: 502, headers: { 'content-type': 'application/json' } },
  );
  let structured = '';
  let structuredError: unknown = null;
  try { await browser.health(); } catch (error) {
    structuredError = error;
    structured = error instanceof Error ? error.message : '';
  }
  if (structured !== 'GET /api/health → 502 · Provider unavailable') {
    throw new Error(`Structured API error was not decoded: ${structured}`);
  }
  if (!(structuredError instanceof ApiRequestError)
      || structuredError.status !== 502 || structuredError.code !== 'assistant_error') {
    throw new Error('Structured API error metadata was not retained');
  }

  globalThis.fetch = async () => new Response(
    JSON.stringify({ detail: [{ loc: ['body', 'blocks', 0], msg: 'Input should be an object' }] }),
    { status: 422, headers: { 'content-type': 'application/json' } },
  );
  let validation = '';
  try { await browser.health(); } catch (error) { validation = error instanceof Error ? error.message : ''; }
  if (!validation.endsWith('body.blocks.0: Input should be an object')) {
    throw new Error(`Validation API error was not decoded: ${validation}`);
  }

  globalThis.fetch = async () => new Response('Disk is full', { status: 500 });
  let plain = '';
  try { await browser.health(); } catch (error) { plain = error instanceof Error ? error.message : ''; }
  if (!plain.endsWith('500 · Disk is full')) throw new Error(`Plain API error was not retained: ${plain}`);

  let releaseWrite!: (response: Response) => void;
  globalThis.fetch = () => new Promise<Response>((resolve) => { releaseWrite = resolve; });
  const pendingWrite = browser.updateProject(7, { title: 'Tracked' });
  let writeBarrierDone = false;
  const writeBarrier = flushPendingProjectSaves().then(() => { writeBarrierDone = true; });
  for (let i = 0; i < 6; i++) await Promise.resolve();
  if (writeBarrierDone) throw new Error('Save barrier did not wait for a mutating HTTP request');
  if (!releaseWrite) throw new Error('Queued mutating request did not start');
  releaseWrite(new Response(JSON.stringify(project(7, "Tracked")), {
    status: 200, headers: { 'content-type': 'application/json' },
  }));
  await Promise.all([pendingWrite, writeBarrier]);
  if (!writeBarrierDone) throw new Error('Save barrier did not resume after the mutating request');

  let releasePlacement!: (response: Response) => void;
  globalThis.fetch = (input: RequestInfo | URL, init: RequestInit = {}) => {
    requests.push({ input: String(input), init });
    return new Promise<Response>((resolve) => { releasePlacement = resolve; });
  };
  const expectedStructureRevision = 'a'.repeat(64);
  const pendingPlacement = browser.placeScene(7, 11, {
    expected_revision: expectedStructureRevision,
    act: 'Act Two',
    chapter: 'Chapter Three',
    index: 2,
  });
  for (let i = 0; i < 6; i++) await Promise.resolve();
  const placementRequest = requests.at(-1);
  if (placementRequest?.input !== '/api/projects/7/story-structure/scenes/11/placement'
      || placementRequest.init.method !== 'PUT') {
    throw new Error('Scene placement request used the wrong route or method');
  }
  const placementBody = JSON.parse(String(placementRequest.init.body));
  if (placementBody.expected_revision !== expectedStructureRevision
      || placementBody.act !== 'Act Two'
      || placementBody.chapter !== 'Chapter Three'
      || placementBody.index !== 2
      || 'episode_id' in placementBody) {
    throw new Error('Scene placement request did not preserve the revision-guarded body');
  }
  let placementBarrierDone = false;
  const placementBarrier = flushPendingProjectSaves().then(() => { placementBarrierDone = true; });
  for (let i = 0; i < 6; i++) await Promise.resolve();
  if (placementBarrierDone) throw new Error('Scene placement escaped the persistence barrier');
  releasePlacement(new Response(JSON.stringify({
    project_id: 7,
    revision: 'b'.repeat(64),
    chapter_level: true,
    scene_count: 0,
    orphan_count: 0,
    acts: [],
  }), { status: 200, headers: { 'content-type': 'application/json' } }));
  const placed = await pendingPlacement;
  await placementBarrier;
  if (placed.revision !== 'b'.repeat(64)) throw new Error('Scene placement response was not validated');

  let releaseStructureCommand!: (response: Response) => void;
  globalThis.fetch = (input: RequestInfo | URL, init: RequestInit = {}) => {
    requests.push({ input: String(input), init });
    return new Promise<Response>((resolve) => { releaseStructureCommand = resolve; });
  };
  const commandBody = {
    kind: 'rename_chapter' as const,
    expected_revision: 'b'.repeat(64),
    act: 'Act One',
    chapter: 'Chapter One',
    new_name: 'Chapter Prime',
    episode_id: 12,
  };
  const pendingStructureCommand = browser.executeStoryStructureCommand(7, commandBody);
  for (let i = 0; i < 6; i++) await Promise.resolve();
  const structureCommandRequest = requests.at(-1);
  if (structureCommandRequest?.input !== '/api/projects/7/story-structure/commands'
      || structureCommandRequest.init.method !== 'POST') {
    throw new Error('Story structure command used the wrong route or method');
  }
  const serializedStructureCommand = JSON.parse(String(structureCommandRequest.init.body));
  if (serializedStructureCommand.kind !== 'rename_chapter'
      || serializedStructureCommand.expected_revision !== 'b'.repeat(64)
      || serializedStructureCommand.act !== 'Act One'
      || serializedStructureCommand.chapter !== 'Chapter One'
      || serializedStructureCommand.new_name !== 'Chapter Prime'
      || serializedStructureCommand.episode_id !== 12) {
    throw new Error('Story structure command did not preserve its discriminated payload');
  }
  let structureCommandBarrierDone = false;
  const structureCommandBarrier = flushPendingProjectSaves().then(() => {
    structureCommandBarrierDone = true;
  });
  for (let i = 0; i < 6; i++) await Promise.resolve();
  if (structureCommandBarrierDone) throw new Error('Story structure command escaped the persistence barrier');
  releaseStructureCommand(new Response(JSON.stringify({
    structure: {
      project_id: 7,
      revision: 'c'.repeat(64),
      chapter_level: true,
      scene_count: 1,
      orphan_count: 0,
      acts: [{
        name: 'Act One',
        number: '1',
        unassigned: false,
        scene_count: 1,
        chapters: [{
          name: 'Chapter Prime',
          number: '1.1',
          unassigned: false,
          scene_count: 1,
          scenes: [{
            id: 11,
            episode_id: null,
            title: 'Scene',
            beat: '',
            number: '1.1.1',
            order_index: 1,
            is_orphan: false,
          }],
        }],
      }],
    },
    changed: true,
    created_scene_id: null,
    affected_scene_ids: [11],
  }), { status: 200, headers: { 'content-type': 'application/json' } }));
  const structureCommandResult = await pendingStructureCommand;
  await structureCommandBarrier;
  if (!structureCommandResult.changed
      || structureCommandResult.structure.revision !== 'c'.repeat(64)
      || structureCommandResult.affected_scene_ids[0] !== 11) {
    throw new Error('Story structure command response was not validated');
  }

  let releaseTimelineCommand!: (response: Response) => void;
  globalThis.fetch = (input: RequestInfo | URL, init: RequestInit = {}) => {
    requests.push({ input: String(input), init });
    return new Promise<Response>((resolve) => { releaseTimelineCommand = resolve; });
  };
  const timelineCommandBody = {
    kind: 'place_event' as const,
    expected_revision: 'd'.repeat(64),
    scene_id: 11,
    lane_id: 4,
    index: 0,
  };
  const pendingTimelineCommand = browser.executeTimelineCommand(7, timelineCommandBody);
  for (let i = 0; i < 6; i++) await Promise.resolve();
  const timelineCommandRequest = requests.at(-1);
  if (timelineCommandRequest?.input !== '/api/projects/7/timeline/commands'
      || timelineCommandRequest.init.method !== 'POST') {
    throw new Error('Timeline command used the wrong route or method');
  }
  const serializedTimelineCommand = JSON.parse(String(timelineCommandRequest.init.body));
  if (serializedTimelineCommand.kind !== 'place_event'
      || serializedTimelineCommand.expected_revision !== 'd'.repeat(64)
      || serializedTimelineCommand.scene_id !== 11
      || serializedTimelineCommand.lane_id !== 4
      || serializedTimelineCommand.index !== 0) {
    throw new Error('Timeline command did not preserve its discriminated payload');
  }
  let timelineBarrierDone = false;
  const timelineBarrier = flushPendingProjectSaves().then(() => { timelineBarrierDone = true; });
  for (let i = 0; i < 6; i++) await Promise.resolve();
  if (timelineBarrierDone) throw new Error('Timeline command escaped the persistence barrier');
  releaseTimelineCommand(new Response(JSON.stringify({
    timeline: {
      project_id: 7,
      revision: 'e'.repeat(64),
      order_mode: 'custom',
      lanes: [{
        id: 4, name: 'Main', color_label: 'cyan', order_index: 0,
        collapsed: false, event_count: 1,
      }],
      events: [{
        id: 11, order_index: 1, title: 'Scene', structural_number: '1.1.1',
        act: 'Act One', chapter: 'Chapter One', plotline: 'Main', color_label: '',
        lane_id: 4, time_of_day: '', location: '', duration_minutes: 0,
        character_states: [],
      }],
      off_timeline: [],
    },
    replayed: false,
    applied_revision: 'e'.repeat(64),
    changed: true,
    affected_scene_ids: [11],
  }), { status: 200, headers: { 'content-type': 'application/json' } }));
  const timelineCommandResult = await pendingTimelineCommand;
  await timelineBarrier;
  if (!timelineCommandResult.changed
      || timelineCommandResult.replayed
      || timelineCommandResult.applied_revision !== 'e'.repeat(64)
      || timelineCommandResult.timeline.order_mode !== 'custom'
      || timelineCommandResult.affected_scene_ids[0] !== 11) {
    throw new Error('Timeline command response was not validated');
  }

  let releaseCanvasCommand!: (response: Response) => void;
  globalThis.fetch = (input: RequestInfo | URL, init: RequestInit = {}) => {
    requests.push({ input: String(input), init });
    return new Promise<Response>((resolve) => { releaseCanvasCommand = resolve; });
  };
  const canvasCommandBody = {
    kind: 'create_node' as const,
    expected_revision: 'a'.repeat(64),
    title: 'Inciting signal',
    x: 40,
    y: 72,
  };
  const pendingCanvasCommand = browser.executeCanvasPlotCommand(7, canvasCommandBody);
  for (let i = 0; i < 6; i++) await Promise.resolve();
  const canvasCommandRequest = requests.at(-1);
  if (canvasCommandRequest?.input !== '/api/projects/7/canvas-plot/commands'
      || canvasCommandRequest.init.method !== 'POST') {
    throw new Error('Canvas Plot command used the wrong route or method');
  }
  const serializedCanvasCommand = JSON.parse(String(canvasCommandRequest.init.body));
  if (serializedCanvasCommand.kind !== 'create_node'
      || serializedCanvasCommand.expected_revision !== 'a'.repeat(64)
      || serializedCanvasCommand.title !== 'Inciting signal'
      || serializedCanvasCommand.x !== 40
      || serializedCanvasCommand.y !== 72) {
    throw new Error('Canvas Plot command did not preserve its discriminated payload');
  }
  let canvasBarrierDone = false;
  const canvasBarrier = flushPendingProjectSaves().then(() => { canvasBarrierDone = true; });
  for (let i = 0; i < 6; i++) await Promise.resolve();
  if (canvasBarrierDone) throw new Error('Canvas Plot command escaped the persistence barrier');
  releaseCanvasCommand(new Response(JSON.stringify({
    canvas_plot: {
      project_id: 7,
      revision: 'b'.repeat(64),
      nodes: [{
        id: 21, title: 'Inciting signal', body: '', x: 40, y: 72,
        width: 180, height: 110, color_label: '', group_label: '',
        scene_id: null, sort_order: 1, created_at: '2026-10-05T09:00:00Z',
      }],
      links: [],
      frames: [],
    },
    replayed: false,
    applied_revision: 'b'.repeat(64),
    changed: true,
    affected_node_ids: [21],
    affected_link_ids: [],
    affected_frame_ids: [],
    created_node_id: 21,
    created_link_id: null,
    created_frame_id: null,
  }), { status: 200, headers: { 'content-type': 'application/json' } }));
  const canvasCommandResult = await pendingCanvasCommand;
  await canvasBarrier;
  if (!canvasCommandResult.changed
      || canvasCommandResult.replayed
      || canvasCommandResult.applied_revision !== 'b'.repeat(64)
      || canvasCommandResult.canvas_plot.revision !== 'b'.repeat(64)
      || canvasCommandResult.created_node_id !== 21) {
    throw new Error('Canvas Plot command response was not validated');
  }

  let releaseContinuityCommand!: (response: Response) => void;
  globalThis.fetch = (input: RequestInfo | URL, init: RequestInit = {}) => {
    requests.push({ input: String(input), init });
    return new Promise<Response>((resolve) => { releaseContinuityCommand = resolve; });
  };
  const continuityCommandBody = {
    kind: 'resolve_issue' as const,
    expected_revision: 'a'.repeat(64),
    issue_id: '0123456789abcdef',
    expected_issue_fingerprint: 'f'.repeat(64),
  };
  const continuityKey = 'continuity-http-key-0001';
  const pendingContinuityCommand = browser.executeContinuityCommand(
    7,
    continuityCommandBody,
    continuityKey,
  );
  for (let i = 0; i < 6; i++) await Promise.resolve();
  const continuityCommandRequest = requests.at(-1);
  const continuityHeaders = new Headers(continuityCommandRequest?.init.headers);
  if (continuityCommandRequest?.input !== '/api/projects/7/continuity/commands'
      || continuityCommandRequest.init.method !== 'POST'
      || continuityHeaders.get('Idempotency-Key') !== continuityKey
      || String(continuityCommandRequest.init.body) !== JSON.stringify(continuityCommandBody)) {
    throw new Error('Continuity command did not preserve its route, body, and Idempotency-Key');
  }
  let continuityBarrierDone = false;
  const continuityBarrier = flushPendingProjectSaves().then(() => { continuityBarrierDone = true; });
  for (let i = 0; i < 6; i++) await Promise.resolve();
  if (continuityBarrierDone) throw new Error('Continuity command escaped the persistence barrier');
  const reviewedContinuity = {
    project_id: 7,
    review_revision: 'b'.repeat(64),
    writing_mode: 'novel',
    issues: [{
      id: continuityCommandBody.issue_id,
      review_fingerprint: continuityCommandBody.expected_issue_fingerprint,
      issue_type: 'continuity_gap',
      dimension: 'plot',
      severity: 'blocking',
      confidence: 'confirmed',
      title: 'Missing payoff',
      explanation: 'The payoff scene is absent.',
      suggested_action: 'Restore the payoff.',
      related_scene_ids: [11],
      status: 'resolved',
    }],
    blocking_count: 0,
    warning_count: 0,
    unavailable: [],
  };
  releaseContinuityCommand(new Response(JSON.stringify({
    continuity: reviewedContinuity,
    changed: true,
    affected_issue_id: continuityCommandBody.issue_id,
    previous_status: 'open',
    status: 'resolved',
    replayed: false,
    applied_revision: 'b'.repeat(64),
  }), { status: 200, headers: { 'content-type': 'application/json' } }));
  const continuityCommandResult = await pendingContinuityCommand;
  await continuityBarrier;
  if (!continuityCommandResult.changed
      || continuityCommandResult.replayed
      || continuityCommandResult.continuity.project_id !== 7
      || continuityCommandResult.applied_revision !== 'b'.repeat(64)) {
    throw new Error('Continuity command response was not request-bound and validated');
  }

  globalThis.fetch = async (input: RequestInfo | URL, init: RequestInit = {}) => {
    requests.push({ input: String(input), init });
    return new Response(JSON.stringify({
      project_id: 7,
      request_digest: 'c'.repeat(64),
      command_kind: continuityCommandBody.kind,
      expected_revision: continuityCommandBody.expected_revision,
      applied_revision: 'b'.repeat(64),
      original_changed: true,
      original_affected_issue_id: continuityCommandBody.issue_id,
      expected_issue_fingerprint: continuityCommandBody.expected_issue_fingerprint,
      previous_status: 'open',
      status: 'resolved',
      committed_at: '2026-10-07T12:00:00Z',
    }), { status: 200, headers: { 'content-type': 'application/json' } });
  };
  const continuityReceipt = await browser.getContinuityCommandReceipt(
    7,
    continuityKey,
    continuityCommandBody,
  );
  const receiptRequest = requests.at(-1);
  const receiptHeaders = new Headers(receiptRequest?.init.headers);
  if (receiptRequest?.input !== '/api/projects/7/continuity/command-receipt'
      || receiptRequest.init.method !== undefined
      || receiptHeaders.get('Idempotency-Key') !== continuityKey
      || receiptHeaders.get('Cache-Control') !== 'no-store'
      || continuityReceipt.original_affected_issue_id !== continuityCommandBody.issue_id) {
    throw new Error('Continuity receipt recovery did not use the exact no-store capability request');
  }

  const workflowRun = {
    id: 31, project_id: 7, title: 'Rewrite Pass', description: 'Guided rewrite',
    status: 'active', writing_mode: 'novel', template_id: 'rewrite', current_step_id: 'draft',
    total_steps: 1, completed_steps: 0, revision: 'a'.repeat(64), source_type: '', source_id: null,
    created_at: '2026-10-07T12:00:00Z', updated_at: '2026-10-07T12:00:00Z', completed_at: null,
    steps: [{
      step_id: 'draft', title: 'Draft the rewrite', description: 'Draft safely.', kind: 'creative',
      status: 'active', sort_index: 0, section_name: 'Manuscript', action_id: 'inline_rewrite',
      completion_check: '', notes: '', target_type: 'scene', target_id: 12,
      created_at: '2026-10-07T12:00:00Z', updated_at: '2026-10-07T12:00:00Z',
    }],
  };
  globalThis.fetch = async (input: RequestInfo | URL, init: RequestInit = {}) => {
    requests.push({ input: String(input), init });
    return new Response(JSON.stringify([workflowRun]), {
      status: 200, headers: { 'content-type': 'application/json' },
    });
  };
  const workflowRuns = await browser.getWorkflows(7);
  if (requests.at(-1)?.input !== '/api/projects/7/workflows'
      || workflowRuns[0]?.revision !== workflowRun.revision) {
    throw new Error('Guided Workflow list read did not use and validate the project route');
  }
  globalThis.fetch = async (input: RequestInfo | URL, init: RequestInit = {}) => {
    requests.push({ input: String(input), init });
    return new Response(JSON.stringify([{ id: 1, project_id: 7, workflow_run_id: 31, step_id: null,
      event_type: 'started', message: 'Started.', metadata: {}, created_at: '2026-10-07T12:00:00Z' }]), {
      status: 200, headers: { 'content-type': 'application/json' },
    });
  };
  await browser.getWorkflowEvents(7, 31, 999);
  if (requests.at(-1)?.input !== '/api/projects/7/workflows/31/events?limit=200') {
    throw new Error('Guided Workflow event reads did not clamp and encode the bounded limit');
  }

  let releaseWorkflowCommand!: (response: Response) => void;
  globalThis.fetch = (input: RequestInfo | URL, init: RequestInit = {}) => {
    requests.push({ input: String(input), init });
    return new Promise<Response>((resolve) => { releaseWorkflowCommand = resolve; });
  };
  const workflowCommand = {
    kind: 'pause' as const, run_id: 31, expected_revision: workflowRun.revision,
  };
  const workflowKey = 'workflow-http-key-0001';
  const pendingWorkflowCommand = browser.executeWorkflowCommand(7, workflowCommand, workflowKey);
  for (let i = 0; i < 6; i++) await Promise.resolve();
  const workflowCommandRequest = requests.at(-1);
  const workflowHeaders = new Headers(workflowCommandRequest?.init.headers);
  if (workflowCommandRequest?.input !== '/api/projects/7/workflows/commands'
      || workflowCommandRequest.init.method !== 'POST'
      || workflowHeaders.get('Idempotency-Key') !== workflowKey
      || String(workflowCommandRequest.init.body) !== JSON.stringify(workflowCommand)) {
    throw new Error('Guided Workflow command did not preserve its route, body, and Idempotency-Key');
  }
  let workflowBarrierDone = false;
  const workflowBarrier = flushPendingProjectSaves().then(() => { workflowBarrierDone = true; });
  for (let i = 0; i < 6; i++) await Promise.resolve();
  if (workflowBarrierDone) throw new Error('Guided Workflow command escaped the persistence barrier');
  const pausedWorkflow = { ...workflowRun, status: 'paused', revision: 'b'.repeat(64), updated_at: '2026-10-07T12:01:00Z' };
  releaseWorkflowCommand(new Response(JSON.stringify({
    workflow: pausedWorkflow, changed: true, replayed: false, applied_revision: pausedWorkflow.revision,
  }), { status: 200, headers: { 'content-type': 'application/json' } }));
  const workflowCommandResult = await pendingWorkflowCommand;
  await workflowBarrier;
  if (!workflowCommandResult.changed || workflowCommandResult.workflow.status !== 'paused') {
    throw new Error('Guided Workflow command response was not request-bound and validated');
  }

  globalThis.fetch = async (input: RequestInfo | URL, init: RequestInit = {}) => {
    requests.push({ input: String(input), init });
    return new Response(JSON.stringify({
      project_id: 7, request_digest: 'c'.repeat(64), command_kind: workflowCommand.kind,
      expected_revision: workflowCommand.expected_revision, applied_revision: pausedWorkflow.revision,
      original_changed: true, original_run_id: 31, committed_at: '2026-10-07T12:01:00Z',
    }), { status: 200, headers: { 'content-type': 'application/json' } });
  };
  const workflowReceipt = await browser.getWorkflowCommandReceipt(7, workflowKey, workflowCommand);
  const workflowReceiptRequest = requests.at(-1);
  const workflowReceiptHeaders = new Headers(workflowReceiptRequest?.init.headers);
  if (workflowReceiptRequest?.input !== '/api/projects/7/workflows/command-receipt'
      || workflowReceiptHeaders.get('Idempotency-Key') !== workflowKey
      || workflowReceiptHeaders.get('Cache-Control') !== 'no-store'
      || workflowReceipt.original_run_id !== 31) {
    throw new Error('Guided Workflow receipt recovery did not use the exact no-store capability request');
  }

  let releaseRead!: (response: Response) => void;
  globalThis.fetch = () => new Promise<Response>((resolve) => { releaseRead = resolve; });
  const pendingRead = browser.health();
  await flushPendingProjectSaves();
  releaseRead(new Response(JSON.stringify({ status: 'ok' }), {
    status: 200, headers: { 'content-type': 'application/json' },
  }));
  await pendingRead;

  const patchResolvers: Array<(response: Response) => void> = [];
  const patchBodies: string[] = [];
  let startedPatches = 0;
  globalThis.fetch = (_input: RequestInfo | URL, init: RequestInit = {}) => {
    startedPatches += 1;
    patchBodies.push(String(init.body ?? ''));
    return new Promise<Response>((resolve) => { patchResolvers.push(resolve); });
  };
  const firstPatch = browser.updateProject(11, { title: 'First' });
  const queuedBody = { title: 'Second' };
  const secondPatch = browser.updateProject(11, queuedBody);
  queuedBody.title = 'Mutated after enqueue';
  for (let i = 0; i < 6; i++) await Promise.resolve();
  if (startedPatches !== 1) throw new Error(`Same-resource PATCHes were not serialized: ${startedPatches} started`);
  patchResolvers[0]!(new Response(JSON.stringify(project(11, "First")), {
    status: 200, headers: { 'content-type': 'application/json' },
  }));
  await firstPatch;
  for (let i = 0; i < 6; i++) await Promise.resolve();
  if (startedPatches !== 2) throw new Error('Second PATCH did not start after the first settled');
  if (JSON.parse(patchBodies[1]!).title !== 'Second') throw new Error('Queued PATCH body was not captured at invocation time');
  patchResolvers[1]!(new Response(JSON.stringify(project(11, "Second")), {
    status: 200, headers: { 'content-type': 'application/json' },
  }));
  await secondPatch;

  let failureCalls = 0;
  globalThis.fetch = async () => {
    failureCalls += 1;
    return failureCalls === 1
      ? new Response('first failed', { status: 500 })
      : new Response(JSON.stringify(project(12, "Recovered")), {
          status: 200, headers: { 'content-type': 'application/json' },
        });
  };
  const failedPatch = browser.updateProject(12, { title: 'Fails' }).catch(() => undefined);
  const recoveredPatch = browser.updateProject(12, { title: 'Recovered' });
  await Promise.all([failedPatch, recoveredPatch]);
  if (failureCalls !== 2) throw new Error('PATCH queue stopped after a rejected request');

  console.log('HTTP API client tests: 34 passed, 0 failed');
} finally {
  globalThis.fetch = originalFetch;
}
