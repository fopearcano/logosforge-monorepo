/* =============================================================================
 * LogosForge Whiteboard — Syntax palettes (RESTYLE v3)
 * -----------------------------------------------------------------------------
 * Per-theme `--syn-*` token colours consumed by the Nerd-Mode syntax
 * highlighter (`.wb-syn-<token>`) and the screenplay element classes.
 *
 * Drop-in replacement for styles/themes/syntaxThemes.ts. The token KEYS and the
 * `--syn-*` variable NAMES are the contract; only the colour VALUES change.
 * One palette per shipped theme (keyed by theme id) so syntax tracks the theme.
 * ========================================================================== */

export type SynToken =
  | 'keyword'   // scene headings, chapter/heading markers, fountain sections
  | 'string'    // strings, character names
  | 'comment'   // comments, synopses, parentheticals, boneyard
  | 'heading'   // markdown headings
  | 'emphasis'  // bold/italic/underline emphasis ink
  | 'number'    // numbers, page breaks, transitions
  | 'tag'       // #tags, scene tags
  | 'note'      // [[notes]] / find-match highlight (this is a BG, see *-bg)
  | 'todo'      // TODO / checkbox-unchecked
  | 'link'      // links
  | 'function'  // function-ish accents (dialogue cue, derived nav)
  | 'punct';    // punctuation / dim structure

export type SynPalette = Record<SynToken, string> & {
  /** background wash for the [[note]] / find-match highlight */
  noteBg: string;
  /** ink that sits on noteBg */
  noteInk: string;
};

/* Manuscript — calm, low-saturation ink on chalk. */
/* comment/number darkened from #a3a098/#9a7d3a so parentheticals, synopses and
 * transitions clear WCAG AA (~4.5:1) on the white page instead of ghosting out. */
const MANUSCRIPT_SYN: SynPalette = {
  keyword: '#2b2a2e', string: '#7a6a3e', comment: '#6f6c63', heading: '#2b2a2e',
  emphasis: '#2b2a2e', number: '#8a6f2e', tag: '#5181a8', note: '#8a5a38',
  todo: '#b0653f', link: '#5181a8', function: '#8a5a38', punct: '#b8b4ab',
  noteBg: 'rgba(176,101,63,0.14)', noteInk: '#6e3c22',
};

/* Forge — ember on red-warm black, brighter + more separated than before:
 * ember headings, gold cues, amber transitions, a cool TEAL for caption labels
 * (so they pop out of the all-warm palette), legible warm-grey parentheticals. */
const FORGE_SYN: SynPalette = {
  keyword: '#ff8a66', string: '#f2c879', comment: '#9a8b80', heading: '#e8ddd6',
  emphasis: '#e8ddd6', number: '#e8a24a', tag: '#5cc2cc', note: '#ff7a6a',
  todo: '#ff5a45', link: '#5cc2cc', function: '#ff7a6a', punct: '#6a584f',
  noteBg: 'rgba(228,74,53,0.20)', noteInk: '#ffd9cf',
};

/* Deepdark — Luxcium, max color-coding on pure black: orange headings, gold
 * cues, green transitions, cyan caption labels, magenta find-match. Each element
 * gets a distinct, bright hue (was: amber+green+green — two greens collided). */
const DEEPDARK_SYN: SynPalette = {
  keyword: '#ff9d4d', string: '#ffd24a', comment: '#9a9a9a', heading: '#f2f2f2',
  emphasis: '#f2f2f2', number: '#5fd98a', tag: '#4fc3ff', note: '#ff6ea8',
  todo: '#ff9d4d', link: '#6bb6ff', function: '#d6d6d6', punct: '#5c5c5c',
  noteBg: 'rgba(233,80,162,0.32)', noteInk: '#ffa6da',
};

/* Violet — high-contrast on the deep-purple page. The old keyword (#caa9ff) and
 * comment (#8b93c4) sank into the violet bg; replaced with FUCHSIA headings/cues,
 * GOLD markdown heads, GREEN dialogue and a legible lavender for parentheticals
 * so colour-coding genuinely pops. */
const VIOLET_SYN: SynPalette = {
  keyword: '#ff79c6', string: '#c3e88d', comment: '#a9a4dc', heading: '#f5d479',
  emphasis: '#e7defb', number: '#ffb088', tag: '#8fd9ff', note: '#ff8a9e',
  todo: '#ffd866', link: '#8db0ff', function: '#8fd9ff', punct: '#6a6a92',
  noteBg: 'rgba(247,118,142,0.26)', noteInk: '#ff9aab',
};

/* Blueprint — on a saturated-blue page, cool tokens sink in; this uses WARM +
 * light hues that pop on blue: gold headings, peach cues, mint transitions,
 * lilac caption labels, light-periwinkle (legible) parentheticals. (Was: three
 * identical cyans that vanished into the page.) */
const BLUEPRINT_SYN: SynPalette = {
  keyword: '#ffe08a', string: '#ffc0a0', comment: '#bccdf4', heading: '#ffffff',
  emphasis: '#ffffff', number: '#9bf0c4', tag: '#e2c4ff', note: '#ffd08a',
  todo: '#ffdc6b', link: '#bfe0ff', function: '#d8e4ff', punct: '#7a93cf',
  noteBg: 'rgba(255,224,138,0.18)', noteInk: '#fff3d6',
};

/* Chroma — a LIGHT theme that keeps full colour-coding (unlike Manuscript's
 * near-B&W ink): saturated-but-dark hues that clear WCAG AA on white — blue
 * headings, amber cues, green transitions, teal caption labels, grey parens. */
const CHROMA_SYN: SynPalette = {
  keyword: '#1d4ed8', string: '#b45309', comment: '#646b78', heading: '#111827',
  emphasis: '#111827', number: '#047857', tag: '#0e7490', note: '#be185d',
  todo: '#c2410c', link: '#1d4ed8', function: '#7c3aed', punct: '#9aa0ad',
  noteBg: 'rgba(190,24,93,0.12)', noteInk: '#9d174d',
};

export const SYNTAX_THEMES: Record<string, SynPalette> = {
  manuscript: MANUSCRIPT_SYN,
  chroma: CHROMA_SYN,
  forge: FORGE_SYN,
  deepdark: DEEPDARK_SYN,
  violet: VIOLET_SYN,
  blueprint: BLUEPRINT_SYN,
};

/** Write the `--syn-*` vars for a theme id (falls back to manuscript). */
export function applySyntaxVars(themeId: string, root: HTMLElement = document.documentElement): void {
  const p = SYNTAX_THEMES[themeId] ?? MANUSCRIPT_SYN;
  const set = (k: string, v: string) => root.style.setProperty(k, v);
  set('--syn-keyword', p.keyword);
  set('--syn-string', p.string);
  set('--syn-comment', p.comment);
  set('--syn-heading', p.heading);
  set('--syn-emphasis', p.emphasis);
  set('--syn-number', p.number);
  set('--syn-tag', p.tag);
  set('--syn-note', p.note);
  set('--syn-todo', p.todo);
  set('--syn-link', p.link);
  set('--syn-function', p.function);
  set('--syn-punct', p.punct);
  set('--syn-note-bg', p.noteBg);
  set('--syn-note-ink', p.noteInk);
}
