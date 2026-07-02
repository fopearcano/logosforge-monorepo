import type { PlatformAdapter } from '@logosforge/pro-shared-ui';

export type CoreStatus = {
  state: 'connecting' | 'connected' | 'error';
  baseUrl: string;
  managed: boolean;
  detail?: string;
};

/** The flat `window.logosforge` surface exposed by the Electron preload. */
export interface DesktopBridge {
  coreBaseUrl(): Promise<string>;
  getCoreStatus(): Promise<CoreStatus>;
  onCoreStatus(cb: (s: CoreStatus) => void): () => void;
  openFile(filters?: { name: string; extensions: string[] }[]): Promise<{ canceled: boolean; path?: string; content?: string }>;
  saveFile(p: { suggestedName?: string; content?: string; contentBase64?: string; mimeType?: string }): Promise<{ canceled: boolean; path?: string }>;
  openExternal(target: string): Promise<void>;
  loadLayout(projectId: number): Promise<unknown | null>;
  saveLayout(projectId: number, layout: unknown): Promise<void>;
}

declare global {
  interface Window {
    logosforge?: DesktopBridge;
  }
}

/** Present only when running inside the Electron shell (preload exposed it). */
export const desktop: DesktopBridge | undefined = window.logosforge;

/** The pro-shared-ui PlatformAdapter, backed by the Electron host. */
export const platform: PlatformAdapter = {
  isDesktop: true,
  openFile: (opts) => desktop!.openFile(opts?.filters),
  saveFile: (opts) => desktop!.saveFile(opts),
  openExternal: (target) => desktop!.openExternal(target),
  loadLayout: (projectId) => desktop!.loadLayout(projectId),
  saveLayout: (projectId, layout) => desktop!.saveLayout(projectId, layout),
};
