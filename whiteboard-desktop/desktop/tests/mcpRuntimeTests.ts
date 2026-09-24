import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';

import {
  MCP_RUNTIME_FILENAME,
  installMcpCompanion,
  mcpCompanionPath,
  removeRuntimeDescriptor,
  runtimeDescriptorPath,
  writeRuntimeDescriptor,
  type RuntimeDescriptor,
} from '../electron/mcp-runtime';

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: boolean) => {
  if (condition) passed += 1;
  else failures.push(label);
};

const throws = (action: () => unknown): boolean => {
  try {
    action();
    return false;
  } catch {
    return true;
  }
};

const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'logosforge-whiteboard-mcp-runtime-'));
try {
  const userDataDir = path.join(tempRoot, 'user-data');
  const defaultDescriptor = runtimeDescriptorPath(userDataDir, {});
  check(
    'descriptor has a stable versioned filename under Whiteboard user data',
    MCP_RUNTIME_FILENAME === 'mcp-runtime-v1.json'
      && defaultDescriptor === path.join(userDataDir, MCP_RUNTIME_FILENAME),
  );

  const overrideDescriptor = path.join(tempRoot, 'overrides', MCP_RUNTIME_FILENAME);
  check(
    'Whiteboard connection-file override wins',
    runtimeDescriptorPath(userDataDir, {
      LOGOSFORGE_WHITEBOARD_MCP_CONNECTION_FILE: overrideDescriptor,
    }) === overrideDescriptor,
  );
  check(
    'blank connection-file override falls back to user data',
    runtimeDescriptorPath(userDataDir, {
      LOGOSFORGE_WHITEBOARD_MCP_CONNECTION_FILE: '   ',
    }) === defaultDescriptor,
  );
  check(
    'relative connection-file override is rejected',
    throws(() => runtimeDescriptorPath(userDataDir, {
      LOGOSFORGE_WHITEBOARD_MCP_CONNECTION_FILE: MCP_RUNTIME_FILENAME,
    })),
  );
  check(
    'connection-file override must retain the versioned descriptor basename',
    throws(() => runtimeDescriptorPath(userDataDir, {
      LOGOSFORGE_WHITEBOARD_MCP_CONNECTION_FILE: path.join(tempRoot, 'important.json'),
    })),
  );

  const executableName = process.platform === 'win32'
    ? 'logosforge-whiteboard-mcp.exe'
    : 'logosforge-whiteboard-mcp';
  const defaultCompanion = mcpCompanionPath(userDataDir, executableName, {});
  check(
    'companion has a stable private per-user path',
    defaultCompanion === path.join(userDataDir, 'mcp', executableName),
  );
  const overrideCompanion = path.join(tempRoot, 'custom', executableName);
  check(
    'Whiteboard launcher-path override wins',
    mcpCompanionPath(userDataDir, executableName, {
      LOGOSFORGE_WHITEBOARD_MCP_LAUNCHER_PATH: overrideCompanion,
    }) === overrideCompanion,
  );
  check(
    'relative launcher-path override is rejected',
    throws(() => mcpCompanionPath(userDataDir, executableName, {
      LOGOSFORGE_WHITEBOARD_MCP_LAUNCHER_PATH: executableName,
    })),
  );
  check(
    'launcher-path override must retain the expected executable basename',
    throws(() => mcpCompanionPath(userDataDir, executableName, {
      LOGOSFORGE_WHITEBOARD_MCP_LAUNCHER_PATH: path.join(tempRoot, 'unrelated.exe'),
    })),
  );

  const companionSource = path.join(tempRoot, `source-${executableName}`);
  fs.writeFileSync(companionSource, 'whiteboard-companion-v1');
  check(
    'companion installer atomically creates the stable launcher',
    installMcpCompanion(companionSource, defaultCompanion) === true
      && fs.readFileSync(defaultCompanion, 'utf8') === 'whiteboard-companion-v1',
  );
  check(
    'identical companion install is a no-op',
    installMcpCompanion(companionSource, defaultCompanion) === false,
  );
  fs.writeFileSync(companionSource, 'whiteboard-companion-v2');
  check(
    'companion installer replaces an older launcher',
    installMcpCompanion(companionSource, defaultCompanion) === true
      && fs.readFileSync(defaultCompanion, 'utf8') === 'whiteboard-companion-v2',
  );
  check(
    'companion installer leaves no temporary executable behind',
    fs.readdirSync(path.dirname(defaultCompanion)).join(',') === executableName,
  );

  const companionDirectoryTarget = path.join(tempRoot, 'companion-directory-target');
  fs.mkdirSync(companionDirectoryTarget);
  check(
    'companion installer refuses a directory target',
    throws(() => installMcpCompanion(companionSource, companionDirectoryTarget))
      && fs.statSync(companionDirectoryTarget).isDirectory(),
  );

  const companionSymlinkTarget = path.join(tempRoot, 'companion-symlink-target');
  const companionSymlink = path.join(tempRoot, 'companion-symlink');
  fs.writeFileSync(companionSymlinkTarget, 'preserve-this-launcher-target');
  let companionSymlinkCreated = false;
  try {
    fs.symlinkSync(companionSymlinkTarget, companionSymlink, 'file');
    companionSymlinkCreated = true;
  } catch {
    // Creating symlinks may require an elevated token on local Windows hosts.
  }
  if (companionSymlinkCreated) {
    check(
      'companion installer refuses a symlink target',
      throws(() => installMcpCompanion(companionSource, companionSymlink))
        && fs.readFileSync(companionSymlinkTarget, 'utf8') === 'preserve-this-launcher-target',
    );
  }
  if (process.platform !== 'win32') {
    check(
      'installed companion is private and executable',
      (fs.statSync(defaultCompanion).mode & 0o777) === 0o700,
    );
  }

  const first: RuntimeDescriptor = {
    schema_version: 1,
    base_url: 'http://127.0.0.1:43117',
    auth_token: 'whiteboard-descriptor-secret-one-0000000000000000',
    instance_nonce: 'whiteboard-instance-one',
    app_pid: process.pid,
    backend_pid: process.pid,
    created_at: '2026-09-24T10:00:00.000Z',
  };
  writeRuntimeDescriptor(defaultDescriptor, first);
  check('writer creates the descriptor parent directory', fs.existsSync(userDataDir));
  check(
    'writer persists the exact Whiteboard connection descriptor',
    JSON.stringify(JSON.parse(fs.readFileSync(defaultDescriptor, 'utf8'))) === JSON.stringify(first),
  );
  if (process.platform !== 'win32') {
    check(
      'descriptor is private to its operating-system user',
      (fs.statSync(defaultDescriptor).mode & 0o777) === 0o600,
    );
  }
  check(
    'atomic writer leaves no temporary credential files behind',
    fs.readdirSync(userDataDir).includes(MCP_RUNTIME_FILENAME)
      && !fs.readdirSync(userDataDir).some((name) => name.endsWith('.tmp')),
  );

  const second: RuntimeDescriptor = {
    ...first,
    base_url: 'http://127.0.0.1:43118',
    auth_token: 'whiteboard-descriptor-secret-two-0000000000000000',
    instance_nonce: 'whiteboard-instance-two',
    created_at: '2026-09-24T10:01:00.000Z',
  };
  writeRuntimeDescriptor(defaultDescriptor, second);
  check(
    'atomic writer replaces an earlier app session completely',
    JSON.stringify(JSON.parse(fs.readFileSync(defaultDescriptor, 'utf8'))) === JSON.stringify(second),
  );

  removeRuntimeDescriptor(defaultDescriptor, first.instance_nonce);
  check(
    'an old app session cannot remove a newer session descriptor',
    fs.existsSync(defaultDescriptor),
  );
  removeRuntimeDescriptor(defaultDescriptor, second.instance_nonce);
  check(
    'the owning app session removes its descriptor during shutdown',
    !fs.existsSync(defaultDescriptor),
  );

  const malformedSecret = 'must-not-appear-in-diagnostics';
  fs.writeFileSync(defaultDescriptor, `{not-json:${malformedSecret}`, { mode: 0o600 });
  let malformedError = '';
  try {
    removeRuntimeDescriptor(defaultDescriptor, second.instance_nonce);
  } catch (error) {
    malformedError = String(error);
  }
  check(
    'nonce-guarded cleanup never deletes a malformed descriptor',
    fs.existsSync(defaultDescriptor),
  );
  check(
    'malformed-descriptor diagnostics do not leak credentials',
    !malformedError.includes(malformedSecret),
  );
  check(
    'startup cleanup refuses a malformed runtime file',
    throws(() => removeRuntimeDescriptor(defaultDescriptor))
      && fs.existsSync(defaultDescriptor),
  );
  check(
    'descriptor writer refuses to overwrite a malformed runtime file',
    throws(() => writeRuntimeDescriptor(defaultDescriptor, second))
      && fs.readFileSync(defaultDescriptor, 'utf8').includes(malformedSecret),
  );

  fs.rmSync(defaultDescriptor, { force: true });
  fs.writeFileSync(
    defaultDescriptor,
    JSON.stringify({ ...second, base_url: 'http://127.0.0.1:0' }),
    { mode: 0o600 },
  );
  check(
    'descriptor cleanup rejects loopback port zero',
    throws(() => removeRuntimeDescriptor(defaultDescriptor))
      && fs.existsSync(defaultDescriptor),
  );
  fs.rmSync(defaultDescriptor, { force: true });

  const protectedJson = path.join(tempRoot, 'protected.json');
  fs.writeFileSync(protectedJson, JSON.stringify({ schema_version: 1, keep: true }));
  check(
    'startup cleanup never deletes an arbitrary parseable JSON file',
    throws(() => removeRuntimeDescriptor(protectedJson))
      && fs.existsSync(protectedJson),
  );
  check(
    'descriptor writer never replaces an arbitrary regular file',
    throws(() => writeRuntimeDescriptor(protectedJson, first))
      && JSON.parse(fs.readFileSync(protectedJson, 'utf8')).keep === true,
  );

  const descriptorDirectory = path.join(tempRoot, 'descriptor-directory');
  fs.mkdirSync(descriptorDirectory);
  check(
    'startup cleanup refuses a directory target',
    throws(() => removeRuntimeDescriptor(descriptorDirectory))
      && fs.statSync(descriptorDirectory).isDirectory(),
  );
  check(
    'descriptor writer refuses a directory target',
    throws(() => writeRuntimeDescriptor(descriptorDirectory, first))
      && fs.statSync(descriptorDirectory).isDirectory(),
  );

  const descriptorSymlinkTarget = path.join(tempRoot, 'descriptor-symlink-target.json');
  const descriptorSymlink = path.join(tempRoot, MCP_RUNTIME_FILENAME);
  fs.writeFileSync(descriptorSymlinkTarget, JSON.stringify(first));
  let descriptorSymlinkCreated = false;
  try {
    fs.rmSync(defaultDescriptor, { force: true });
    fs.symlinkSync(descriptorSymlinkTarget, descriptorSymlink, 'file');
    descriptorSymlinkCreated = true;
  } catch {
    // Creating symlinks may require an elevated token on local Windows hosts.
  }
  if (descriptorSymlinkCreated) {
    check(
      'startup cleanup refuses a descriptor symlink',
      throws(() => removeRuntimeDescriptor(descriptorSymlink))
        && fs.lstatSync(descriptorSymlink).isSymbolicLink(),
    );
    check(
      'descriptor writer refuses a descriptor symlink',
      throws(() => writeRuntimeDescriptor(descriptorSymlink, second))
        && fs.lstatSync(descriptorSymlink).isSymbolicLink()
        && JSON.parse(fs.readFileSync(descriptorSymlinkTarget, 'utf8')).instance_nonce
          === first.instance_nonce,
    );
    fs.rmSync(descriptorSymlink, { force: true });
  } else {
    fs.rmSync(defaultDescriptor, { force: true });
  }

  writeRuntimeDescriptor(defaultDescriptor, first);
  check(
    'startup cleanup removes a valid stale Whiteboard descriptor',
    removeRuntimeDescriptor(defaultDescriptor) && !fs.existsSync(defaultDescriptor),
  );
} finally {
  fs.rmSync(tempRoot, { recursive: true, force: true });
}

if (failures.length) {
  throw new Error(`${failures.length} MCP runtime test(s) failed:\n- ${failures.join('\n- ')}`);
}
console.log(`Whiteboard MCP runtime tests: ${passed} passed, 0 failed`);
