/**
 * Platform adapter — the boundary the apps inject so this package stays
 * platform-neutral. pro-desktop (Electron) and pro-web (browser) each provide
 * their own implementation; shared-ui components only call this interface, never
 * `electron`, Node, or browser-host APIs directly.
 */

export interface OpenFileResult {
  canceled: boolean;
  path?: string;
  /** text content if the host read it for us; else undefined. */
  content?: string;
  /** raw file bytes, base64-encoded — for binary imports (e.g. .docx) that a
   *  UTF-8 read would corrupt. Set by desktop alongside `content`. */
  contentBase64?: string;
}

export interface SaveFileResult {
  canceled: boolean;
  path?: string;
}

export interface PlatformAdapter {
  /** Local file open (desktop) / file picker or import (web). */
  openFile(opts?: { filters?: { name: string; extensions: string[] }[] }): Promise<OpenFileResult>;
  /**
   * Local file save (desktop) / download (web). Pass `content` for text exports,
   * or `contentBase64` for binary ones (PDF/DOCX) — the host decodes the base64 and
   * writes raw bytes (a UTF-8 string write would corrupt binary). At least one of
   * `content` / `contentBase64` should be set.
   */
  saveFile(opts: { suggestedName?: string; content?: string; contentBase64?: string; mimeType?: string }): Promise<SaveFileResult>;
  /** Reveal/open a path or URL in the host (best-effort). */
  openExternal(target: string): Promise<void>;
  /** App-level navigation (router on web; window/section on desktop). */
  navigate?(to: string): void;
  /** Persist + restore opaque per-project UI layout (docking). */
  loadLayout?(projectId: number): Promise<unknown | null>;
  saveLayout?(projectId: number, layout: unknown): Promise<void>;
  /** True on Electron desktop (enables local-only features like Dexter's Room). */
  readonly isDesktop: boolean;
}
