import path from 'node:path';

export const MCP_RUNTIME_FILENAME = 'mcp-runtime-v1.json';
export const WHITEBOARD_MCP_EXECUTABLE = 'logosforge-whiteboard-mcp';

/**
 * Resolve the unpacked executable produced alongside each release artifact.
 * The release artifact itself is still verified by the existing packaging
 * smoke; Playwright needs the unpacked Electron executable for its main-process
 * transport.
 */
export function defaultWhiteboardExecutable(
  desktopDir,
  { platform = process.platform, pathApi = path } = {},
) {
  if (platform === 'win32') {
    return pathApi.join(
      desktopDir,
      'release',
      'win-unpacked',
      'LogosForge Whiteboard.exe',
    );
  }
  if (platform === 'darwin') {
    return pathApi.join(
      desktopDir,
      'release',
      'mac',
      'LogosForge Whiteboard.app',
      'Contents',
      'MacOS',
      'LogosForge Whiteboard',
    );
  }
  if (platform === 'linux') {
    return pathApi.join(
      desktopDir,
      'release',
      'linux-unpacked',
      'logosforge-whiteboard-desktop',
    );
  }
  throw new Error(`Whiteboard packaged acceptance does not support ${platform}.`);
}

export function packagedWhiteboardLayout(
  executablePath,
  { platform = process.platform, pathApi = path } = {},
) {
  const executable = pathApi.resolve(executablePath);
  const resources = platform === 'darwin'
    ? pathApi.resolve(pathApi.dirname(executable), '..', 'Resources')
    : pathApi.join(pathApi.dirname(executable), 'resources');
  const executableSuffix = platform === 'win32' ? '.exe' : '';
  return Object.freeze({
    executable,
    resources,
    appArchive: pathApi.join(resources, 'app.asar'),
    backend: pathApi.join(
      resources,
      'backend',
      `logosforge-whiteboard-backend${executableSuffix}`,
    ),
    bundledMcp: pathApi.join(
      resources,
      'mcp',
      `${WHITEBOARD_MCP_EXECUTABLE}${executableSuffix}`,
    ),
    installedMcpName: `${WHITEBOARD_MCP_EXECUTABLE}${executableSuffix}`,
  });
}

export function packagedLaunchArguments(
  loaderPath,
  userDataDir,
  { platform = process.platform, uid = undefined } = {},
) {
  const args = ['-r', loaderPath, `--user-data-dir=${userDataDir}`];
  if (platform === 'linux' && uid === 0) args.push('--no-sandbox');
  return args;
}

function requiredPositiveInteger(value, label) {
  if (!Number.isSafeInteger(value) || value <= 0) {
    throw new Error(`The Whiteboard MCP descriptor has an invalid ${label}.`);
  }
  return value;
}

function requiredTrimmedText(value, label, minimum) {
  if (typeof value !== 'string' || value !== value.trim() || value.length < minimum) {
    throw new Error(`The Whiteboard MCP descriptor has an invalid ${label}.`);
  }
  return value;
}

/** Validate the public shape without returning or logging its bearer token. */
export function validateWhiteboardRuntimeDescriptor(
  value,
  { expectedPort, expectedAppPid } = {},
) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('The Whiteboard MCP descriptor is not a JSON object.');
  }
  if (value.schema_version !== 1) {
    throw new Error('The Whiteboard MCP descriptor has an unsupported schema.');
  }

  const rawBaseUrl = requiredTrimmedText(value.base_url, 'base_url', 1);
  let endpoint;
  try {
    endpoint = new URL(rawBaseUrl);
  } catch {
    throw new Error('The Whiteboard MCP descriptor has an invalid base_url.');
  }
  const port = Number(endpoint.port);
  if (
    endpoint.protocol !== 'http:'
    || !['127.0.0.1', '::1', '[::1]'].includes(endpoint.hostname)
    || endpoint.username
    || endpoint.password
    || endpoint.pathname !== '/'
    || endpoint.search
    || endpoint.hash
    || !Number.isInteger(port)
    || port < 1
    || port > 65_535
  ) {
    throw new Error('The Whiteboard MCP descriptor is not a strict loopback origin.');
  }
  if (expectedPort !== undefined && port !== expectedPort) {
    throw new Error(
      `The Whiteboard MCP descriptor used port ${port}, expected ${expectedPort}.`,
    );
  }

  // Validate the credential but deliberately omit it from the returned summary.
  requiredTrimmedText(value.auth_token, 'auth_token', 32);
  const instanceNonce = requiredTrimmedText(value.instance_nonce, 'instance_nonce', 16);
  const appPid = requiredPositiveInteger(value.app_pid, 'app_pid');
  const backendPid = requiredPositiveInteger(value.backend_pid, 'backend_pid');
  if (expectedAppPid !== undefined && appPid !== expectedAppPid) {
    throw new Error(
      `The Whiteboard MCP descriptor belongs to app PID ${appPid}, expected ${expectedAppPid}.`,
    );
  }
  const createdAt = requiredTrimmedText(value.created_at, 'created_at', 10);
  if (!createdAt.endsWith('Z') || !Number.isFinite(Date.parse(createdAt))) {
    throw new Error('The Whiteboard MCP descriptor created_at is not UTC.');
  }

  return Object.freeze({
    baseUrl: endpoint.origin,
    port,
    instanceNonce,
    appPid,
    backendPid,
    createdAt,
  });
}

/**
 * Confirm that a live health response still belongs to the backend instance
 * whose descriptor was validated. Cleanup code must pass this check before it
 * may terminate the captured backend PID.
 */
export function isMatchingWhiteboardBackendHealth(value, descriptorSummary) {
  return Boolean(
    value
      && typeof value === 'object'
      && !Array.isArray(value)
      && descriptorSummary
      && typeof descriptorSummary === 'object'
      && value.status === 'ok'
      && value.service === 'logosforge-whiteboard-backend'
      && typeof descriptorSummary.instanceNonce === 'string'
      && value.instance_nonce === descriptorSummary.instanceNonce,
  );
}

function requiredRecord(value, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`The Whiteboard export has an invalid ${label}.`);
  }
  return value;
}

function requiredArray(value, label) {
  if (!Array.isArray(value)) {
    throw new Error(`The Whiteboard export has an invalid ${label}.`);
  }
  return value;
}

/**
 * Validate the standalone Whiteboard export boundary without retaining bundle
 * contents. This deliberately covers export only; importing and Pro behavior
 * belong to separate product journeys.
 */
export function validateWhiteboardExportBundle(
  value,
  { expectedProjectId, expectedTitle, expectedMarker } = {},
) {
  const root = requiredRecord(value, 'bundle envelope');
  if (root.format !== 'logosforge-project-bundle') {
    throw new Error('The Whiteboard export has an unexpected format.');
  }
  if (root.version !== '1.0') {
    throw new Error('The Whiteboard export has an unsupported version.');
  }
  if (typeof root.exportedAt !== 'string' || !Number.isFinite(Date.parse(root.exportedAt))) {
    throw new Error('The Whiteboard export has an invalid timestamp.');
  }
  const source = requiredRecord(root.source, 'source envelope');
  if (source.app !== 'logosforge-whiteboard') {
    throw new Error('The Whiteboard export has an unexpected source application.');
  }

  const project = requiredRecord(root.project, 'project envelope');
  if (typeof project.id !== 'string' || project.id.length === 0) {
    throw new Error('The Whiteboard export has an invalid project id.');
  }
  if (expectedProjectId !== undefined && project.id !== String(expectedProjectId)) {
    throw new Error('The Whiteboard export does not belong to the created document.');
  }
  if (typeof project.title !== 'string') {
    throw new Error('The Whiteboard export has an invalid project title.');
  }
  if (expectedTitle !== undefined && project.title !== expectedTitle) {
    throw new Error('The Whiteboard export title does not match the created document.');
  }
  if (typeof project.mode !== 'string' || project.mode.length === 0) {
    throw new Error('The Whiteboard export has an invalid writing mode.');
  }
  requiredRecord(project.settings, 'project settings');

  const manuscript = requiredRecord(project.manuscript, 'manuscript section');
  const blocks = requiredArray(manuscript.blocks, 'manuscript block list');
  for (const [index, block] of blocks.entries()) {
    requiredRecord(block, `manuscript block ${index}`);
  }
  if (
    typeof expectedMarker !== 'string'
    || expectedMarker.length === 0
    || !blocks.some((block) => typeof block.text === 'string' && block.text.includes(expectedMarker))
  ) {
    throw new Error('The Whiteboard export manuscript is missing the lifecycle marker.');
  }

  const outline = requiredArray(project.outline, 'outline section');
  const comments = requiredArray(project.comments, 'comments section');
  const drafter = requiredRecord(project.drafter, 'Drafter section');
  const drafterPages = requiredArray(drafter.pages, 'Drafter page list');
  const psyke = requiredRecord(project.psyke, 'PSYKE section');
  const psykeElements = requiredArray(psyke.elements, 'PSYKE element list');
  const psykeRelations = requiredArray(psyke.relations, 'PSYKE relation list');
  const psykeProgressions = requiredArray(psyke.progressions, 'PSYKE progression list');

  return Object.freeze({
    projectId: project.id,
    title: project.title,
    mode: project.mode,
    manuscriptBlockCount: blocks.length,
    outlineCount: outline.length,
    commentCount: comments.length,
    drafterPageCount: drafterPages.length,
    psykeElementCount: psykeElements.length,
    psykeRelationCount: psykeRelations.length,
    psykeProgressionCount: psykeProgressions.length,
  });
}

export function isSameOrInside(candidate, parent, pathApi = path) {
  const relative = pathApi.relative(pathApi.resolve(parent), pathApi.resolve(candidate));
  return relative === '' || (!relative.startsWith('..') && !pathApi.isAbsolute(relative));
}
