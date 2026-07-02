/**
 * Shared cue-detection heuristics for the screenplay / stage / graphic-novel
 * classifiers. Centralised so the three formats agree on what is — and, just as
 * important, what is NOT — a character cue. The old per-classifier rule accepted
 * any short Title-Case line, so ordinary description prose ("A Long Silence
 * Follows") and ALL-CAPS interstitials ("SUDDENLY", "THE END") were mis-centered
 * as character cues, cascading the following lines into wrong dialogue/action.
 */

/** True when `t` is genuinely ALL-CAPS letters (the strongest cue signal). */
export function isAllCapsName(t: string): boolean {
  return /[A-Z]/.test(t) && t === t.toUpperCase() && !/[a-z]/.test(t);
}

/**
 * Common ALL-CAPS interstitials / transitions / stage beats that look name-like
 * but are never character cues. Compared case-insensitively against the whole
 * candidate name.
 */
export const NOT_A_CUE = new Set([
  'suddenly', 'meanwhile', 'later', 'moments later', 'continuous', 'intercut',
  'cut', 'cut to', 'smash cut', 'dissolve', 'dissolve to', 'fade', 'fade in',
  'fade out', 'the end', 'end', 'beat', 'pause', 'silence', 'blackout',
  'curtain', 'lights up', 'lights down', 'establishing', 'angle on', 'close on',
  'wide', 'insert', 'title', 'omitted',
]);

/**
 * Words that, when they BEGIN a Title-Case line, signal description prose or
 * dialogue rather than a character name ("The Storm Rages On", "She Runs",
 * "Yes I Will"). Real names rarely begin with an article / pronoun /
 * conjunction / preposition / interjection.
 */
export const NON_NAME_FIRST = new Set([
  'a', 'an', 'the', 'this', 'that', 'these', 'those', 'he', 'she', 'it', 'they',
  'we', 'you', 'i', 'his', 'her', 'its', 'their', 'our', 'your', 'my', 'when',
  'while', 'then', 'there', 'here', 'as', 'at', 'in', 'on', 'of', 'to', 'for',
  'with', 'from', 'by', 'and', 'but', 'or', 'so', 'if', 'after', 'before',
  'because', 'now', 'soon', 'once', 'again', 'into', 'onto', 'over', 'under',
  'yes', 'no', 'okay', 'ok', 'well', 'oh', 'hey', 'hi', 'please', 'thanks',
]);

/**
 * Whether `name` (already stripped of any trailing "(…)" / ":") reads like a
 * character name rather than prose. ALL-CAPS names up to 3 words pass; Title-Case
 * names must be ≤2 words and not begin with a prose/interjection word; known
 * interstitials never pass.
 */
export function looksLikeName(name: string): boolean {
  if (!name || name.length > 28) return false;
  if (/[.!?,;:]/.test(name)) return false;
  const words = name.split(/\s+/);
  if (!words.every((w) => /^[A-Z]/.test(w))) return false;
  if (NOT_A_CUE.has(name.toLowerCase())) return false;
  if (isAllCapsName(name)) return words.length <= 3;
  // Title-Case (mixed case): only tight, name-shaped lines, never prose phrases.
  return words.length <= 2 && !NON_NAME_FIRST.has(words[0].toLowerCase());
}
