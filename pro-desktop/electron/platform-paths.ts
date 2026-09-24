import * as path from 'node:path';

/** Executable name emitted by a native PyInstaller onedir build. */
export function bundledCoreExecutableName(platform: NodeJS.Platform): string {
  return platform === 'win32' ? 'logosforge-core.exe' : 'logosforge-core';
}

/** Console MCP companion name emitted by its native one-file PyInstaller build. */
export function bundledMcpExecutableName(platform: NodeJS.Platform): string {
  return platform === 'win32' ? 'logosforge-mcp.exe' : 'logosforge-mcp';
}

/** Runtime location populated by electron-builder's `extraResources` copy. */
export function resolveBundledCorePath(
  resourcesPath: string,
  platform: NodeJS.Platform = process.platform,
): string {
  return path.join(resourcesPath, 'core', bundledCoreExecutableName(platform));
}

export function resolveBundledMcpPath(
  resourcesPath: string,
  platform: NodeJS.Platform = process.platform,
): string {
  return path.join(resourcesPath, 'mcp', bundledMcpExecutableName(platform));
}
