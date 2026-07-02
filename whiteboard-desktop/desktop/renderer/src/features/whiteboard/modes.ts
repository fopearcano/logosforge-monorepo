/**
 * Writing-mode behavior registry.
 *
 * Each mode defines how the editor behaves/looks. Screenplay uses Fountain
 * inference + a monospaced surface; the other modes are prose-first with a
 * Markdown-heading outline. The `measure` is the readable text-column width
 * inside the full-panel writing surface (mode-aware layout — not one-size CSS).
 *
 * Note: the backend exposes five narrative engines, but the Whiteboard
 * intentionally surfaces only novel/screenplay/graphic_novel/stage_script —
 * `series` is hidden in this product (filtered out of the mode list; any
 * incoming `series` is normalized to `novel`). "Notes"/"Scene" are StoryPlanner
 * *section* concepts, not writing modes here; prose entries are pre-registered
 * so they work if such modes are ever added.
 *
 * There is intentionally no placeholder text — an empty document shows only the
 * caret.
 */

export interface ModeBehavior {
  id: string;
  displayName: string;
  /** Editor typography family. */
  font: 'mono' | 'serif';
  /** Apply Fountain inference + screenplay keyboard behavior. */
  fountain: boolean;
  /** Outline extraction strategy. */
  outline: 'fountain' | 'headings';
  /** Readable text-column width within the (full-panel) writing surface. */
  measure: string;
}

function prose(id: string, displayName: string, measure = '48rem'): ModeBehavior {
  return {
    id,
    displayName,
    font: 'serif',
    fountain: false,
    outline: 'headings',
    measure,
  };
}

const REGISTRY: Record<string, ModeBehavior> = {
  screenplay: {
    id: 'screenplay',
    displayName: 'Screenplay',
    font: 'mono',
    fountain: true,
    outline: 'fountain',
    measure: '63ch', // screenplay-safe text column (Courier)
  },
  novel: prose('novel', 'Novel'),
  graphic_novel: prose('graphic_novel', 'Graphic Novel'),
  // Stage scripts use a dedicated stage classifier/formatter (see ../stage),
  // applied via the stage extension — not Fountain inference, hence fountain:false.
  stage_script: {
    id: 'stage_script',
    displayName: 'Stage Script',
    font: 'mono',
    fountain: false,
    outline: 'headings',
    measure: '60ch',
  },
  // Forward-compat prose foundations (not currently exposed as writing modes).
  notes: prose('notes', 'Notes', '56rem'),
  scene: prose('scene', 'Scene', '50rem'),
};

const DEFAULT = prose('novel', 'Novel');

export function modeBehavior(mode: string | null | undefined): ModeBehavior {
  return (mode && REGISTRY[mode]) || DEFAULT;
}
