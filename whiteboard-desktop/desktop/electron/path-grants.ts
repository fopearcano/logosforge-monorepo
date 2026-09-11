import * as path from 'node:path';

/** Main-process capability set for files the user explicitly opened or saved. */
export class PathGrantRegistry {
  private readonly granted = new Set<string>();

  private normalize(filePath: string): string {
    const resolved = path.resolve(filePath);
    return process.platform === 'win32' ? resolved.toLocaleLowerCase('en-US') : resolved;
  }

  grant(filePath: string): void {
    if (typeof filePath !== 'string' || !filePath.trim()) return;
    this.granted.add(this.normalize(filePath));
  }

  allows(filePath: string): boolean {
    return typeof filePath === 'string'
      && !!filePath.trim()
      && this.granted.has(this.normalize(filePath));
  }
}
