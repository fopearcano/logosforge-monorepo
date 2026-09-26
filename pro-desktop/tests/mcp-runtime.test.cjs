const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const {
  MCP_RUNTIME_FILENAME,
  installMcpCompanion,
  mcpCompanionPath,
  removeRuntimeDescriptor,
  runtimeDescriptorPath,
  writeRuntimeDescriptor,
} = require('../dist-electron/mcp-runtime.js');

let passed = 0;
function check(label, condition) {
  if (!condition) throw new Error(`MCP runtime test failed: ${label}`);
  passed += 1;
}

const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'logosforge-mcp-runtime-'));
try {
  const userDataDir = path.join(tempRoot, 'user-data');
  const defaultPath = runtimeDescriptorPath(userDataDir, {});
  check('descriptor has a stable filename under the Pro user-data directory',
    MCP_RUNTIME_FILENAME === 'mcp-runtime-v1.json' &&
    defaultPath === path.join(userDataDir, MCP_RUNTIME_FILENAME));

  const overridePath = path.join(tempRoot, 'overrides', 'session.json');
  check('an explicit runtime-file environment override wins',
    runtimeDescriptorPath(userDataDir, {
      LOGOSFORGE_MCP_CONNECTION_FILE: overridePath,
    }) === overridePath);
  check('a blank runtime-file override falls back to user data',
    runtimeDescriptorPath(userDataDir, {
      LOGOSFORGE_MCP_CONNECTION_FILE: '   ',
    }) === defaultPath);

  const defaultCompanion = mcpCompanionPath(userDataDir, 'logosforge-mcp.exe', {});
  check('companion has a stable private per-user path',
    defaultCompanion === path.join(userDataDir, 'mcp', 'logosforge-mcp.exe'));
  const companionOverride = path.join(tempRoot, 'custom', 'logosforge-mcp.exe');
  check('an explicit companion-path override wins',
    mcpCompanionPath(userDataDir, 'logosforge-mcp.exe', {
      LOGOSFORGE_MCP_LAUNCHER_PATH: companionOverride,
    }) === companionOverride);
  const companionSource = path.join(tempRoot, 'source-mcp.exe');
  fs.writeFileSync(companionSource, 'companion-v1');
  check('companion installer atomically creates the stable launcher',
    installMcpCompanion(companionSource, defaultCompanion) === true &&
    fs.readFileSync(defaultCompanion, 'utf8') === 'companion-v1');
  check('identical companion install is a no-op',
    installMcpCompanion(companionSource, defaultCompanion) === false);
  fs.writeFileSync(companionSource, 'companion-v2');
  check('companion installer replaces an older launcher',
    installMcpCompanion(companionSource, defaultCompanion) === true &&
    fs.readFileSync(defaultCompanion, 'utf8') === 'companion-v2');
  check('companion installer leaves no credential or executable temporaries',
    fs.readdirSync(path.dirname(defaultCompanion)).join(',') === 'logosforge-mcp.exe');

  const first = {
    schema_version: 1,
    base_url: 'http://127.0.0.1:43117',
    auth_token: 'descriptor-secret-one-0000000000000000',
    instance_nonce: 'desktop-instance-one',
    app_pid: process.pid,
    core_pid: process.pid,
    created_at: '2026-09-24T10:00:00.000Z',
  };
  writeRuntimeDescriptor(defaultPath, first);
  check('writer creates a descriptor parent directory', fs.existsSync(userDataDir));
  check('writer persists the exact versioned connection descriptor',
    JSON.stringify(JSON.parse(fs.readFileSync(defaultPath, 'utf8'))) === JSON.stringify(first));
  if (process.platform !== 'win32') {
    check('descriptor is private to its operating-system user',
      (fs.statSync(defaultPath).mode & 0o777) === 0o600);
  }
  check('atomic writer leaves no temporary credential files behind',
    fs.readdirSync(userDataDir).includes(MCP_RUNTIME_FILENAME) &&
    !fs.readdirSync(userDataDir).some((name) => name.endsWith('.tmp')));

  const second = {
    ...first,
    base_url: 'http://127.0.0.1:43118',
    auth_token: 'descriptor-secret-two-0000000000000000',
    instance_nonce: 'desktop-instance-two',
    created_at: '2026-09-24T10:01:00.000Z',
  };
  writeRuntimeDescriptor(defaultPath, second);
  check('atomic writer replaces an earlier app session completely',
    JSON.stringify(JSON.parse(fs.readFileSync(defaultPath, 'utf8'))) === JSON.stringify(second));
  check('replacement also leaves no temporary credential files behind',
    fs.readdirSync(userDataDir).includes(MCP_RUNTIME_FILENAME) &&
    !fs.readdirSync(userDataDir).some((name) => name.endsWith('.tmp')));

  removeRuntimeDescriptor(defaultPath, 'desktop-instance-one');
  check('an old app session cannot remove a newer session descriptor',
    fs.existsSync(defaultPath));
  removeRuntimeDescriptor(defaultPath, 'desktop-instance-two');
  check('the owning app session removes its descriptor during shutdown',
    !fs.existsSync(defaultPath));

  const malformedSecret = 'must-not-appear-in-diagnostics';
  fs.writeFileSync(defaultPath, `{not-json:${malformedSecret}`, { mode: 0o600 });
  let malformedError = '';
  try {
    removeRuntimeDescriptor(defaultPath, 'desktop-instance-two');
  } catch (error) {
    malformedError = String(error);
  }
  check('nonce-guarded cleanup never deletes a malformed descriptor',
    fs.existsSync(defaultPath));
  check('malformed-descriptor diagnostics do not leak file contents or tokens',
    !malformedError.includes(malformedSecret));

  removeRuntimeDescriptor(defaultPath);
  check('unconditional cleanup can remove an unusable owned runtime file',
    !fs.existsSync(defaultPath));
} finally {
  fs.rmSync(tempRoot, { recursive: true, force: true });
}

const electronMain = fs.readFileSync(path.join(process.cwd(), 'electron', 'main.ts'), 'utf8');
const coreEntry = fs.readFileSync(path.join(process.cwd(), 'core', 'core_entry.py'), 'utf8');
const coreSpec = fs.readFileSync(path.join(process.cwd(), 'core', 'logosforge-core.spec'), 'utf8');
const mcpEntry = fs.readFileSync(path.join(process.cwd(), 'core', 'mcp_entry.py'), 'utf8');
const mcpSpec = fs.readFileSync(path.join(process.cwd(), 'core', 'logosforge-mcp.spec'), 'utf8');
const packageConfig = JSON.parse(fs.readFileSync(path.join(process.cwd(), 'package.json'), 'utf8'));
const releaseWorkflow = fs.readFileSync(
  path.join(process.cwd(), '..', '.github', 'workflows', 'release-windows.yml'),
  'utf8',
);
const packagedWorkflow = fs.readFileSync(
  path.join(process.cwd(), '..', '.github', 'workflows', 'ci-packaged-windows.yml'),
  'utf8',
);
const packagedSmoke = fs.readFileSync(
  path.join(process.cwd(), 'scripts', 'smoke-packaged-mcp.py'),
  'utf8',
);

check('the installed app uses a stable per-user MCP companion path',
  electronMain.includes('mcpCompanionPath(') &&
  electronMain.includes('bundledMcpExecutableName(process.platform)'));
check('the frozen core has an explicit, argument-closed --mcp entrypoint',
  coreEntry.includes('if argv and argv[0] == "--mcp":') &&
  coreEntry.includes('if len(argv) != 1:') &&
  coreEntry.includes('return mcp_main()'));
check('the PyInstaller bundle explicitly collects the MCP SDK',
  coreSpec.includes('collect_submodules(') &&
  coreSpec.includes('not name.startswith("mcp.cli")'));
check('the standalone MCP entrypoint requires the packaged runtime connection',
  mcpEntry.includes('LOGOSFORGE_MCP_REQUIRE_CONNECTION') &&
  mcpEntry.includes('return mcp_main()'));
check('the standalone MCP spec is console one-file and excludes its optional CLI',
  mcpSpec.includes('name="logosforge-mcp"') &&
  mcpSpec.includes('console=True') &&
  mcpSpec.includes('not name.startswith("mcp.cli")'));
check('Electron packages the standalone MCP companion as a native resource',
  packageConfig.build.extraResources.some((entry) =>
    entry.from === 'core/dist' && entry.to === 'mcp' &&
    entry.filter?.includes('logosforge-mcp*')));
check('the GUI deploys the MCP companion before starting its core',
  electronMain.indexOf('installMcpCompanion(bundledMcpPath, installedMcpPath)') >= 0 &&
  electronMain.indexOf('installMcpCompanion(bundledMcpPath, installedMcpPath)') <
    electronMain.indexOf('void core.start()'));
check('every native release build installs the MCP packaging extra',
  (releaseWorkflow.match(/logosforge\[export,voice,mcp\]/g) || []).length === 3);
check('packaged smoke tears down descriptor-owned processes before temp cleanup',
  packagedSmoke.includes('base_url, auth_token, nonce, app_pid, core_pid = _validate_descriptor(') &&
  packagedSmoke.includes('_stop_process_tree(process, app_pid, core_pid)') &&
  packagedSmoke.includes('ignore_cleanup_errors=True'));
check('packaged smoke confines direct MCP writes to its isolated test session',
  packagedSmoke.includes('"LOGOSFORGE_MCP_ALLOW_WRITES": "0"') &&
  packagedSmoke.includes('writable_mcp_env["LOGOSFORGE_MCP_ALLOW_WRITES"] = "1"') &&
  packagedSmoke.includes('mcp_servers.logosforge.env.LOGOSFORGE_MCP_ALLOW_WRITES=\\"0\\"') &&
  packagedSmoke.includes('"--sandbox", "read-only"'));
check('packaged smoke validates the exact descriptor endpoint before seeding writes',
  packagedSmoke.includes('expected_base_url = f"http://127.0.0.1:{expected_port}"') &&
  packagedSmoke.includes('or base_url.rstrip("/") != expected_base_url') &&
  packagedSmoke.includes('or len(auth_token) < 32') &&
  packagedSmoke.includes('parsed_created_at.utcoffset() != timedelta(0)') &&
  packagedSmoke.includes('not _process_is_alive(app_pid) or not _process_is_alive(core_pid)') &&
  packagedSmoke.includes('base_url, auth_token, nonce, app_pid, core_pid = _validate_descriptor(') &&
  packagedSmoke.indexOf('= _validate_descriptor(') <
    packagedSmoke.indexOf('project_id, comment_id, comment_revision = _seed_comment('));
check('packaged smoke applies comment proposals and rejects stale and replayed writes',
  packagedSmoke.includes('"logosforge_apply_proposal"') &&
  packagedSmoke.includes('installed MCP stale sibling apply') &&
  packagedSmoke.includes('after_stale != after_reply') &&
  packagedSmoke.includes('installed MCP applied proposal replay') &&
  packagedSmoke.includes('replies[0].get("author") != "MCP assistant"'));
check('Windows release CI exercises both unpacked and portable MCP companions',
  releaseWorkflow.includes('Exercise packaged Windows MCP companion') &&
  releaseWorkflow.includes('Exercise portable Windows MCP companion'));
check('required packaged CI pins every Pro MCP build and smoke input',
  [
    'pro-desktop/core/logosforge-mcp.spec',
    'pro-desktop/core/mcp_entry.py',
    'pro-desktop/scripts/smoke-frozen-mcp.py',
    'pro-desktop/scripts/smoke-packaged-mcp.py',
  ].every((requiredPath) => packagedWorkflow.includes(requiredPath)));
check('required packaged CI installs the Pro MCP runtime dependency',
  packagedWorkflow.includes('"./logosforge[export,mcp]"'));
check('required packaged CI freezes and smokes the standalone Pro MCP companion',
  packagedWorkflow.includes('Build fresh Pro core and MCP sidecars') &&
  packagedWorkflow.includes('logosforge-mcp.spec') &&
  packagedWorkflow.includes('Smoke-test frozen Pro MCP companion') &&
  packagedWorkflow.includes('--mcp-executable pro-desktop/core/dist/logosforge-mcp.exe'));
check('required packaged CI rejects a missing or wrong-architecture Pro MCP resource',
  packagedWorkflow.includes('Verify packaged Pro MCP resource and architecture') &&
  packagedWorkflow.includes('resources/mcp/logosforge-mcp.exe') &&
  packagedWorkflow.includes('(b"PE\\0\\0", 0x8664)'));
check('required packaged CI exercises the MCP companion from the unpacked Pro app',
  packagedWorkflow.includes('Exercise packaged Pro MCP companion') &&
  packagedWorkflow.includes('pro-desktop/scripts/smoke-packaged-mcp.py') &&
  packagedWorkflow.includes('pro-desktop/release/win-unpacked/LogosForge Pro.exe'));
check('required packaged CI orders MCP build, frozen smoke, package, and packaged smoke',
  packagedWorkflow.indexOf('Build fresh Pro core and MCP sidecars') <
    packagedWorkflow.indexOf('Smoke-test frozen Pro MCP companion') &&
  packagedWorkflow.indexOf('Smoke-test frozen Pro MCP companion') <
    packagedWorkflow.indexOf('Package unpacked Pro app') &&
  packagedWorkflow.indexOf('Package unpacked Pro app') <
    packagedWorkflow.indexOf('Exercise packaged Pro MCP companion'));

console.log(`MCP runtime descriptor tests: ${passed} passed, 0 failed`);
