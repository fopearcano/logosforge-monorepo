/** Shared types for the Writing Modes feature. Mirrors the backend DTOs. */

export interface WritingMode {
  id: string;
  label: string;
  structural_units: string[];
  default_writing_format: string;
  medium_constraints: string;
}

export interface WritingModesResponse {
  modes: WritingMode[];
  default_mode: string;
}
