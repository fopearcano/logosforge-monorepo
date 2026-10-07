import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  defaultWhiteboardExecutable,
  isMatchingWhiteboardBackendHealth,
  isSameOrInside,
  packagedLaunchArguments,
  packagedWhiteboardLayout,
  validateWhiteboardExportBundle,
  validateWhiteboardRuntimeDescriptor,
} from '../scripts/whiteboard-packaged-acceptance-support.mjs';

const TEST_DIR = path.dirname(fileURLToPath(import.meta.url));
const DESKTOP_DIR = path.resolve(TEST_DIR, '..');

const winRoot = 'C:\\workspace\\whiteboard-desktop\\desktop';
assert.equal(
  defaultWhiteboardExecutable(winRoot, { platform: 'win32', pathApi: path.win32 }),
  'C:\\workspace\\whiteboard-desktop\\desktop\\release\\win-unpacked\\LogosForge Whiteboard.exe',
);
const winLayout = packagedWhiteboardLayout(
  'C:\\workspace\\whiteboard-desktop\\desktop\\release\\win-unpacked\\LogosForge Whiteboard.exe',
  { platform: 'win32', pathApi: path.win32 },
);
assert.equal(
  winLayout.backend,
  'C:\\workspace\\whiteboard-desktop\\desktop\\release\\win-unpacked\\resources\\backend\\logosforge-whiteboard-backend.exe',
);
assert.equal(
  winLayout.bundledMcp,
  'C:\\workspace\\whiteboard-desktop\\desktop\\release\\win-unpacked\\resources\\mcp\\logosforge-whiteboard-mcp.exe',
);

const posixRoot = '/workspace/whiteboard-desktop/desktop';
assert.equal(
  defaultWhiteboardExecutable(posixRoot, { platform: 'darwin', pathApi: path.posix }),
  '/workspace/whiteboard-desktop/desktop/release/mac/LogosForge Whiteboard.app/Contents/MacOS/LogosForge Whiteboard',
);
const macLayout = packagedWhiteboardLayout(
  '/workspace/whiteboard-desktop/desktop/release/mac/LogosForge Whiteboard.app/Contents/MacOS/LogosForge Whiteboard',
  { platform: 'darwin', pathApi: path.posix },
);
assert.equal(
  macLayout.resources,
  '/workspace/whiteboard-desktop/desktop/release/mac/LogosForge Whiteboard.app/Contents/Resources',
);
assert.equal(
  macLayout.backend,
  '/workspace/whiteboard-desktop/desktop/release/mac/LogosForge Whiteboard.app/Contents/Resources/backend/logosforge-whiteboard-backend',
);

assert.equal(
  defaultWhiteboardExecutable(posixRoot, { platform: 'linux', pathApi: path.posix }),
  '/workspace/whiteboard-desktop/desktop/release/linux-unpacked/logosforge-whiteboard-desktop',
);
const linuxLayout = packagedWhiteboardLayout(
  '/workspace/whiteboard-desktop/desktop/release/linux-unpacked/logosforge-whiteboard-desktop',
  { platform: 'linux', pathApi: path.posix },
);
assert.equal(
  linuxLayout.bundledMcp,
  '/workspace/whiteboard-desktop/desktop/release/linux-unpacked/resources/mcp/logosforge-whiteboard-mcp',
);
assert.throws(
  () => defaultWhiteboardExecutable(posixRoot, { platform: 'freebsd', pathApi: path.posix }),
  /does not support freebsd/,
);

assert.deepEqual(
  packagedLaunchArguments('/loader.js', '/profile', { platform: 'darwin', uid: 0 }),
  ['-r', '/loader.js', '--user-data-dir=/profile'],
);
assert.deepEqual(
  packagedLaunchArguments('/loader.js', '/profile', { platform: 'linux', uid: 0 }),
  ['-r', '/loader.js', '--user-data-dir=/profile', '--no-sandbox'],
);
assert.deepEqual(
  packagedLaunchArguments('/loader.js', '/profile', { platform: 'linux', uid: 1000 }),
  ['-r', '/loader.js', '--user-data-dir=/profile'],
);

const descriptor = {
  schema_version: 1,
  base_url: 'http://127.0.0.1:43117',
  auth_token: 'runtime-secret-000000000000000000',
  instance_nonce: 'whiteboard-instance-one',
  app_pid: 1234,
  backend_pid: 5678,
  created_at: '2026-10-07T10:00:00.000Z',
};
assert.deepEqual(
  validateWhiteboardRuntimeDescriptor(descriptor, { expectedPort: 43117, expectedAppPid: 1234 }),
  {
    baseUrl: 'http://127.0.0.1:43117',
    port: 43117,
    instanceNonce: 'whiteboard-instance-one',
    appPid: 1234,
    backendPid: 5678,
    createdAt: '2026-10-07T10:00:00.000Z',
  },
);
assert.equal(
  Object.hasOwn(validateWhiteboardRuntimeDescriptor(descriptor), 'authToken'),
  false,
  'The validated descriptor summary must not retain its bearer token',
);
const descriptorSummary = validateWhiteboardRuntimeDescriptor(descriptor);
assert.equal(
  isMatchingWhiteboardBackendHealth(
    {
      status: 'ok',
      service: 'logosforge-whiteboard-backend',
      instance_nonce: descriptorSummary.instanceNonce,
    },
    descriptorSummary,
  ),
  true,
);
for (const invalidHealth of [
  null,
  [],
  { status: 'starting', service: 'logosforge-whiteboard-backend', instance_nonce: descriptorSummary.instanceNonce },
  { status: 'ok', service: 'unexpected-service', instance_nonce: descriptorSummary.instanceNonce },
  { status: 'ok', service: 'logosforge-whiteboard-backend', instance_nonce: 'another-instance' },
]) {
  assert.equal(isMatchingWhiteboardBackendHealth(invalidHealth, descriptorSummary), false);
}

const exportBundle = {
  format: 'logosforge-project-bundle',
  version: '1.0',
  exportedAt: '2026-10-07T10:00:00+00:00',
  source: { app: 'logosforge-whiteboard' },
  project: {
    id: '17',
    title: 'Packaged lifecycle project',
    mode: 'novel',
    settings: {},
    manuscript: {
      blocks: [
        { id: 'heading-1', type: 'heading', level: 1, text: 'Lifecycle chapter' },
        { id: 'paragraph-1', type: 'paragraph', text: 'Durable export marker.' },
      ],
    },
    outline: [],
    comments: [],
    drafter: { pages: [] },
    psyke: { elements: [], relations: [], progressions: [] },
  },
};
assert.deepEqual(
  validateWhiteboardExportBundle(exportBundle, {
    expectedProjectId: '17',
    expectedTitle: 'Packaged lifecycle project',
    expectedMarker: 'Durable export marker.',
  }),
  {
    projectId: '17',
    title: 'Packaged lifecycle project',
    mode: 'novel',
    manuscriptBlockCount: 2,
    outlineCount: 0,
    commentCount: 0,
    drafterPageCount: 0,
    psykeElementCount: 0,
    psykeRelationCount: 0,
    psykeProgressionCount: 0,
  },
);
for (const [invalidBundle, expectedError] of [
  [{ ...exportBundle, format: 'unexpected' }, /unexpected format/],
  [{ ...exportBundle, version: '2.0' }, /unsupported version/],
  [{ ...exportBundle, project: { ...exportBundle.project, id: '18' } }, /created document/],
  [{
    ...exportBundle,
    project: {
      ...exportBundle.project,
      manuscript: { blocks: [{ id: 'paragraph-1', type: 'paragraph', text: 'No marker here.' }] },
    },
  }, /missing the lifecycle marker/],
  [{ ...exportBundle, project: { ...exportBundle.project, outline: undefined } }, /outline section/],
  [{ ...exportBundle, project: { ...exportBundle.project, comments: undefined } }, /comments section/],
  [{ ...exportBundle, project: { ...exportBundle.project, drafter: undefined } }, /Drafter section/],
  [{ ...exportBundle, project: { ...exportBundle.project, psyke: undefined } }, /PSYKE section/],
]) {
  assert.throws(
    () => validateWhiteboardExportBundle(invalidBundle, {
      expectedProjectId: '17',
      expectedTitle: 'Packaged lifecycle project',
      expectedMarker: 'Durable export marker.',
    }),
    expectedError,
  );
}
for (const invalid of [
  { ...descriptor, schema_version: 2 },
  { ...descriptor, base_url: 'https://127.0.0.1:43117' },
  { ...descriptor, base_url: 'http://example.test:43117' },
  { ...descriptor, base_url: 'http://127.0.0.1:43117/api' },
  { ...descriptor, auth_token: 'short' },
  { ...descriptor, instance_nonce: 'short' },
  { ...descriptor, app_pid: true },
  { ...descriptor, backend_pid: 0 },
  { ...descriptor, created_at: '2026-10-07T10:00:00' },
]) assert.throws(() => validateWhiteboardRuntimeDescriptor(invalid));
assert.throws(
  () => validateWhiteboardRuntimeDescriptor(descriptor, { expectedPort: 43118 }),
  /expected 43118/,
);
assert.throws(
  () => validateWhiteboardRuntimeDescriptor(descriptor, { expectedAppPid: 1235 }),
  /expected 1235/,
);

assert.equal(isSameOrInside('/safe/run/data', '/safe/run', path.posix), true);
assert.equal(isSameOrInside('/safe/runaway', '/safe/run', path.posix), false);
assert.equal(
  isSameOrInside('C:\\safe\\run\\data', 'C:\\safe\\run', path.win32),
  true,
);
assert.equal(
  isSameOrInside('C:\\safe\\runaway', 'C:\\safe\\run', path.win32),
  false,
);

const harnessSource = await readFile(
  path.join(DESKTOP_DIR, 'scripts', 'whiteboard-packaged-acceptance.mjs'),
  'utf8',
);
for (const forbidden of [
  'Import Project (.lfbundle)',
  'showOpenDialog',
  'LOGOSFORGE_PRO_ACCEPTANCE_EXE',
  'runProJourney',
]) {
  assert.equal(
    harnessSource.includes(forbidden),
    false,
    `Standalone Whiteboard acceptance unexpectedly contains ${forbidden}`,
  );
}
assert.match(
  harnessSource,
  /Export Project \(\.lfbundle\)…/,
  'Standalone Whiteboard acceptance must exercise its export-only project bundle path',
);
assert.match(
  harnessSource,
  /validateWhiteboardExportBundle\(JSON\.parse\(raw\.toString\('utf8'\)\)/,
  'Standalone Whiteboard acceptance must parse and validate the written bundle',
);
assert.match(
  harnessSource,
  /assertSamePath\(path\.dirname\(bundlePath\), session\.productRoot/,
  'Standalone Whiteboard export must remain at its exact isolated parent',
);
assert.match(
  harnessSource,
  /chromiumSandbox:\s*true/,
  'Packaged lifecycle must prevent Playwright from injecting --no-sandbox',
);
assert.match(
  harnessSource,
  /app\.commandLine\.hasSwitch\('no-sandbox'\)/,
  'Packaged lifecycle must assert the effective process-wide sandbox switch',
);
assert.match(
  harnessSource,
  /await removeFailureRuntimeDescriptor\(productRoot\)/,
  'Failure handling must remove the private MCP runtime descriptor',
);
assert.match(
  harnessSource,
  /session\.verifiedBackend = descriptor\.summary/,
  'Backend cleanup must retain only a successfully validated runtime summary',
);
assert.match(
  harnessSource,
  /isMatchingWhiteboardBackendHealth\(health, verified\)/,
  'Backend PID cleanup must re-check the live instance identity and nonce',
);

const packagedWindowsWorkflow = await readFile(
  path.resolve(DESKTOP_DIR, '..', '..', '.github', 'workflows', 'ci-packaged-windows.yml'),
  'utf8',
);
assert.match(
  packagedWindowsWorkflow,
  /logosforge-whiteboard-lifecycle-\$\{\{ github\.run_id \}\}-\$\{\{ github\.run_attempt \}\}\/diagnostics/,
  'CI must upload only sanitized Whiteboard lifecycle diagnostics',
);

const workflowDirectory = path.resolve(DESKTOP_DIR, '..', '..', '.github', 'workflows');
const [releaseWindowsWorkflow, releaseLinuxWorkflow, releaseMacWorkflow] = await Promise.all([
  readFile(path.join(workflowDirectory, 'release-whiteboard-windows.yml'), 'utf8'),
  readFile(path.join(workflowDirectory, 'release-whiteboard-linux.yml'), 'utf8'),
  readFile(path.join(workflowDirectory, 'release-whiteboard-macos.yml'), 'utf8'),
]);
for (const [platform, workflow] of [
  ['Windows', releaseWindowsWorkflow],
  ['Linux', releaseLinuxWorkflow],
  ['macOS', releaseMacWorkflow],
]) {
  assert.match(
    workflow,
    /ALLOW_PRE_GATE_SKIP: \$\{\{ github\.event_name == 'workflow_dispatch' && steps\.release\.outputs\.publish == 'true' \}\}/,
    `${platform} release must limit a missing lifecycle gate to manual old-tag repair`,
  );
  assert.match(
    workflow,
    /The manually repaired tag \$\{RELEASE_TAG\} predates the packaged lifecycle harness/,
    `${platform} release must warn when it skips a pre-gate tag`,
  );
  assert.match(
    workflow,
    /if: steps\.lifecycle_gate\.outputs\.available == 'true'/,
    `${platform} release lifecycle must honor gate detection`,
  );
}
for (const [platform, workflow] of [
  ['Windows', releaseWindowsWorkflow],
  ['Linux', releaseLinuxWorkflow],
]) {
  assert.match(
    workflow,
    /LOGOSFORGE_WHITEBOARD_PACKAGED_ACCEPTANCE_ROOT: \$\{\{ runner\.temp \}\}\/logosforge-whiteboard-release-lifecycle-\$\{\{ github\.run_id \}\}-\$\{\{ github\.run_attempt \}\}/,
    `${platform} release must use a stable hosted-runner lifecycle root`,
  );
  assert.match(
    workflow,
    /if: failure\(\) && steps\.lifecycle_gate\.outputs\.available == 'true'[\s\S]*?path: \$\{\{ runner\.temp \}\}\/logosforge-whiteboard-release-lifecycle-\$\{\{ github\.run_id \}\}-\$\{\{ github\.run_attempt \}\}\/diagnostics/,
    `${platform} release must upload only sanitized lifecycle diagnostics on failure`,
  );
}
assert.match(
  releaseMacWorkflow,
  /- "whiteboard-desktop\/desktop\/tests\/\*\*"/,
  'macOS branch release coverage must include lifecycle support-test changes',
);

console.log('Whiteboard packaged acceptance support tests passed.');
