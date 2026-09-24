import * as path from 'node:path';

/** Console MCP companion name emitted by the native one-file build. */
export function bundledMcpExecutableName(platform: NodeJS.Platform): string {
  return platform === 'win32'
    ? 'logosforge-whiteboard-mcp.exe'
    : 'logosforge-whiteboard-mcp';
}

/** Runtime location populated by electron-builder's extraResources copy. */
export function resolveBundledMcpPath(
  resourcesPath: string,
  platform: NodeJS.Platform = process.platform,
): string {
  return path.join(resourcesPath, 'mcp', bundledMcpExecutableName(platform));
}
