import * as fs from 'node:fs';
import * as path from 'node:path';

import {
  bundledMcpExecutableName,
  resolveBundledMcpPath,
} from '../electron/platform-paths';
import { resolveBackendHost } from '../electron/service-identity';

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: boolean) => {
  if (condition) passed += 1;
  else failures.push(label);
};

const root = process.cwd();
const electronMain = fs.readFileSync(path.join(root, 'electron', 'main.ts'), 'utf8');
const backendManager = fs.readFileSync(path.join(root, 'electron', 'backend-manager.ts'), 'utf8');
const builderConfig = fs.readFileSync(path.join(root, 'electron-builder.yml'), 'utf8');

check(
  'Windows MCP companion uses the stable executable name',
  bundledMcpExecutableName('win32') === 'logosforge-whiteboard-mcp.exe',
);
check(
  'macOS MCP companion uses the stable executable name',
  bundledMcpExecutableName('darwin') === 'logosforge-whiteboard-mcp',
);
check(
  'Linux MCP companion uses the stable executable name',
  bundledMcpExecutableName('linux') === 'logosforge-whiteboard-mcp',
);
check(
  'Windows MCP companion resolves under resources/mcp',
  resolveBundledMcpPath(path.join('C:', 'app', 'resources'), 'win32')
    === path.join('C:', 'app', 'resources', 'mcp', 'logosforge-whiteboard-mcp.exe'),
);
check(
  'macOS MCP companion resolves under resources/mcp',
  resolveBundledMcpPath('/Applications/LogosForge Whiteboard.app/Contents/Resources', 'darwin')
    === path.join(
      '/Applications/LogosForge Whiteboard.app/Contents/Resources',
      'mcp',
      'logosforge-whiteboard-mcp',
    ),
);
check(
  'Linux MCP companion resolves under resources/mcp',
  resolveBundledMcpPath('/tmp/.mount/Resources', 'linux')
    === path.join('/tmp/.mount/Resources', 'mcp', 'logosforge-whiteboard-mcp'),
);

check(
  'electron-builder packages the native Whiteboard MCP companion',
  /- from: \.\.\/backend\/dist\s+to: mcp\s+filter:\s+- logosforge-whiteboard-mcp\*/m.test(
    builderConfig,
  ),
);
check(
  'production backend host is pinned to loopback',
  resolveBackendHost(undefined, true) === '127.0.0.1'
    && resolveBackendHost('0.0.0.0', true) === '127.0.0.1'
    && resolveBackendHost('192.168.1.25', true) === '127.0.0.1',
);
check(
  'source development retains an explicit LAN host',
  resolveBackendHost('0.0.0.0', false) === '0.0.0.0',
);
const appNameIndex = electronMain.indexOf("app.setName('LogosForge Whiteboard')");
const userDataIndex = electronMain.indexOf("app.getPath('userData')");
check(
  'Whiteboard product identity is set before resolving user data',
  appNameIndex >= 0 && userDataIndex >= 0 && appNameIndex < userDataIndex,
);
check(
  'the installed app uses a stable per-user MCP companion path',
  electronMain.includes("runtimeDescriptorPath(app.getPath('userData'))")
    && electronMain.includes('mcpCompanionPath(')
    && electronMain.includes('bundledMcpExecutableName(process.platform)'),
);
check(
  'the main process enables production host policy for packaged and --prod launches',
  electronMain.includes('new BackendManager({ production: isProd, mcpRuntimePath })'),
);
const installIndex = electronMain.indexOf('installMcpCompanion(bundledMcpPath, installedMcpPath)');
const startIndex = electronMain.indexOf('void backend.start()');
check(
  'the GUI deploys the MCP companion before starting its backend',
  installIndex >= 0 && startIndex >= 0 && installIndex < startIndex,
);
check(
  'backend startup removes only the owned descriptor path before health checks',
  backendManager.indexOf('this.clearRuntimeDescriptor(false)') >= 0
    && backendManager.indexOf('this.clearRuntimeDescriptor(false)')
      < backendManager.indexOf('if (await this.ping())'),
);
check(
  'runtime publication includes the complete versioned Whiteboard contract',
  [
    'schema_version: 1',
    'base_url: this.baseUrl',
    'auth_token: this.authToken',
    'instance_nonce: this.instanceNonce',
    'app_pid: process.pid',
    'backend_pid: backendPid',
    'created_at: new Date().toISOString()',
  ].every((marker) => backendManager.includes(marker)),
);
check(
  'descriptor publication is reached only through nonce-matching health paths',
  backendManager.includes('return isExpectedBackendHealth(json, this.instanceNonce)')
    && backendManager.includes('const bridgeError = this.publishRuntimeDescriptor();')
    && backendManager.indexOf('const bridgeError = this.publishRuntimeDescriptor();')
      > backendManager.indexOf('private async markConnected('),
);
check(
  'MCP publication rejects non-loopback backend connections',
  backendManager.includes("['127.0.0.1', '::1', '[::1]'].includes(descriptorUrl.hostname)"),
);
check(
  'descriptor is removed on stop and child failure',
  (backendManager.match(/this\.clearRuntimeDescriptor\(\);/g) ?? []).length >= 4
    && backendManager.indexOf('this.clearRuntimeDescriptor();')
      < backendManager.indexOf('// Only stop the backend if we launched it.'),
);

if (failures.length) {
  throw new Error(`${failures.length} MCP packaging test(s) failed:\n- ${failures.join('\n- ')}`);
}
console.log(`Whiteboard MCP packaging tests: ${passed} passed, 0 failed`);
