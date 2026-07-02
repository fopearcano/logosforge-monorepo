/** Stable vocabulary / enum names shared across frontends. */

export const WRITING_MODES = [
  "novel",
  "screenplay",
  "graphic_novel",
  "stage_script",
  "series",
] as const;
export type WritingMode = (typeof WRITING_MODES)[number];

export const PSYKE_TYPES = [
  "character",
  "place",
  "object",
  "lore",
  "theme",
  "other",
] as const;
export type PsykeType = (typeof PSYKE_TYPES)[number];

export const EXPORT_TYPES = ["story_elements", "psyke_data", "full_project"] as const;
export type ExportType = (typeof EXPORT_TYPES)[number];

/** json/markdown/csv are the structured-data formats; fountain/pdf/docx/fdx are
 *  served via the manuscript/screenplay export_types (binary returned as base64). */
export const EXPORT_FORMATS = [
  "json",
  "markdown",
  "csv",
  "docx",
  "fountain",
  "pdf",
  "html",
  "fdx",
] as const;
export type ExportFormat = (typeof EXPORT_FORMATS)[number];

/**
 * Connector actions (safe app actions the AI may invoke) are **dynamic** — do
 * NOT hard-code them. Fetch the live list (`ConnectorActionDTO[]`) from the
 * core and execute via the connector route, so the UI always matches the core.
 */
