const assert = require('node:assert/strict');
const http = require('node:http');

const {
  CoreManager,
  LIVE_CONTEXT_LABEL_MAX_CHARS,
  LIVE_CONTEXT_SELECTION_MAX_CHARS,
  normalizeRendererLiveContext,
} = require('../dist-electron/core-manager.js');

let passed = 0;
function check(label, condition) {
  assert.ok(condition, `Live-context bridge test failed: ${label}`);
  passed += 1;
}

function listen(server) {
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => resolve(server.address()));
  });
}

function close(server) {
  return new Promise((resolve, reject) => {
    server.close((error) => error ? reject(error) : resolve());
  });
}

async function main() {
  const oversized = 's'.repeat(LIVE_CONTEXT_SELECTION_MAX_CHARS + 50);
  const normalized = normalizeRendererLiveContext({
    projectId: 7,
    activePanelId: `  ${'p'.repeat(LIVE_CONTEXT_LABEL_MAX_CHARS + 10)}  `,
    activeSceneId: 9,
    selectionSection: '  manuscript  ',
    selection: oversized,
    source_id: 'renderer-must-not-own-this',
    revision: 9000,
  });
  check('selection is capped before transport',
    normalized.selection.length === LIVE_CONTEXT_SELECTION_MAX_CHARS);
  const unicodeBoundary = normalizeRendererLiveContext({
    projectId: 7,
    activePanelId: 'manuscript',
    activeSceneId: 9,
    selectionSection: 'body',
    selection: `${'s'.repeat(LIVE_CONTEXT_SELECTION_MAX_CHARS - 1)}😀`,
  }).selection;
  check('selection cap never splits a Unicode code point',
    Array.from(unicodeBoundary).length === LIVE_CONTEXT_SELECTION_MAX_CHARS &&
    unicodeBoundary.endsWith('😀'));
  check('labels are normalized and capped',
    normalized.activePanelId.length === LIVE_CONTEXT_LABEL_MAX_CHARS &&
    normalized.selectionSection === 'manuscript');
  check('unknown authority fields are not retained',
    !Object.hasOwn(normalized, 'source_id') && !Object.hasOwn(normalized, 'revision'));
  check('a null project normalizes to an unambiguous clear',
    JSON.stringify(normalizeRendererLiveContext({
      projectId: null,
      activePanelId: 'manuscript',
      activeSceneId: 2,
      selectionSection: 'body',
      selection: 'must be discarded',
    })) === JSON.stringify({
      projectId: null,
      activePanelId: null,
      activeSceneId: null,
      selectionSection: null,
      selection: '',
    }));
  assert.throws(
    () => normalizeRendererLiveContext({
      projectId: 0, activePanelId: null, activeSceneId: null,
      selectionSection: null, selection: '',
    }),
    /projectId/,
  );
  passed += 1;
  assert.throws(
    () => normalizeRendererLiveContext({
      projectId: 1, activePanelId: null, activeSceneId: -1,
      selectionSection: null, selection: '',
    }),
    /activeSceneId/,
  );
  passed += 1;

  const requests = [];
  let firstResponseReleased = false;
  const server = http.createServer((req, res) => {
    const chunks = [];
    req.on('data', (chunk) => chunks.push(chunk));
    req.on('end', () => {
      const body = JSON.parse(Buffer.concat(chunks).toString('utf8'));
      requests.push({
        method: req.method,
        url: req.url,
        authorization: req.headers.authorization,
        liveContextCapability: req.headers['x-logosforge-live-context'],
        body,
        firstResponseReleased,
      });
      const respond = () => {
        if (body.revision === 1) firstResponseReleased = true;
        res.writeHead(200, { 'content-type': 'application/json' });
        res.end(JSON.stringify({ ok: true, revision: body.revision }));
      };
      // If requests are not serialized, revision 2 reaches the server before
      // the delayed revision-1 acknowledgement.
      if (body.revision === 1) setTimeout(respond, 40);
      else respond();
    });
  });
  const address = await listen(server);
  const manager = new CoreManager();
  // TypeScript `private` fields remain ordinary runtime fields. Setting these
  // lets this test exercise the real authenticated transport without spawning
  // a Python core or publishing a runtime descriptor.
  manager.port = address.port;
  manager.endpoint = `http://127.0.0.1:${address.port}`;
  manager.status = {
    state: 'connected', baseUrl: manager.endpoint, managed: false,
    authToken: manager.authToken,
  };

  try {
    const first = manager.publishLiveContext({
      projectId: 7,
      activePanelId: 'manuscript',
      activeSceneId: 9,
      selectionSection: 'body',
      selection: oversized,
      source_id: 'malicious-renderer-source',
      revision: 999,
    });
    const coalesced = [];
    for (let index = 0; index < 40; index += 1) {
      coalesced.push(manager.publishLiveContext({
        projectId: 7,
        activePanelId: 'manuscript',
        activeSceneId: 10,
        selectionSection: 'body',
        selection: `pending selection ${index}`,
      }));
    }
    check('pending payloads and waiter closures stay bounded under renderer churn',
      manager.liveContextQueue.length === 1 &&
      manager.liveContextQueue[0].waiters.length === 1);
    await Promise.all([first, ...coalesced]);
    await manager.clearLiveContext();

    check('all requests use the loopback live-context PUT route',
      requests.every((request) =>
        request.method === 'PUT' && request.url === '/api/live-context'));
    check('all requests use the manager-owned bearer token',
      requests.every((request) =>
        request.authorization === `Bearer ${manager.authToken}`));
    check('all requests use the main-only live-context capability',
      requests.every((request) =>
        request.liveContextCapability === manager.liveContextToken) &&
      !Object.hasOwn(manager.getStatus(), 'liveContextToken'));
    check('main assigns strictly increasing revisions while coalescing renderer churn',
      requests.map((request) => request.body.revision).join(',') === '1,41,42');
    check('main replaces renderer-supplied source authority',
      requests[0].body.source_id === manager.instanceNonce &&
      requests[0].body.source_id !== 'malicious-renderer-source');
    check('transported selection remains capped',
      requests[0].body.selection.length === LIVE_CONTEXT_SELECTION_MAX_CHARS);
    check('updates are serialized through acknowledgement',
      requests[1].firstResponseReleased === true);
    check('only the newest pending renderer update crosses the loopback bridge',
      requests[1].body.selection === 'pending selection 39');
    check('clear is ordered and contains no stale editor values',
      requests[2].body.project_id === null &&
      requests[2].body.active_panel_id === null &&
      requests[2].body.active_scene_id === null &&
      requests[2].body.selection_section === null &&
      requests[2].body.selection === '');

    await manager.suspendLiveContext();
    const suspendedRequestCount = requests.length;
    await manager.publishLiveContext({
      projectId: 8,
      activePanelId: 'manuscript',
      activeSceneId: null,
      selectionSection: null,
      selection: 'must not survive window close',
    });
    await manager.clearLiveContextFromRenderer();
    check('suspension blocks renderer publishes and cleanup behind the final clear',
      requests.length === suspendedRequestCount && requests.at(-1).body.project_id === null);

    manager.resumeLiveContext();
    await manager.publishLiveContext({
      projectId: 8,
      activePanelId: 'outline',
      activeSceneId: null,
      selectionSection: 'Outline',
      selection: 'Act One',
    });
    check('a new macOS window can resume publication',
      requests.at(-1).body.project_id === 8 && requests.at(-1).body.revision === 44);

    await manager.stop();
    check('stop sends a final ordered clear before completing',
      requests.length === 6 && requests[5].body.project_id === null &&
      requests[5].body.revision === 45);
  } finally {
    await close(server);
  }

  const startupManager = new CoreManager();
  let startupChildKills = 0;
  startupManager.child = { kill: () => { startupChildKills += 1; } };
  await startupManager.stop();
  check('stop kills a manager-owned child even before its health probe succeeds',
    startupChildKills === 1 && startupManager.child === null);

  const racingManager = new CoreManager();
  let releasePing;
  let descriptorPublishes = 0;
  racingManager.ping = () => new Promise((resolve) => { releasePing = resolve; });
  racingManager.publishRuntimeDescriptor = () => {
    descriptorPublishes += 1;
    return null;
  };
  const starting = racingManager.start();
  await new Promise((resolve) => setImmediate(resolve));
  const stopping = racingManager.stop();
  releasePing(true);
  await Promise.all([starting, stopping]);
  check('a health response racing shutdown cannot republish a dead-core descriptor',
    descriptorPublishes === 0 && racingManager.getStatus().state !== 'connected');

  console.log(`Electron live-context bridge tests: ${passed} passed, 0 failed`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
