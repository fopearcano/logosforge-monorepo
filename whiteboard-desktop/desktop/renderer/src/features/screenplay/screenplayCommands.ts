/**
 * Pure text commands used by the Format menu / shortcuts (Capitalization,
 * Center). No editor/DOM imports — the editor wrappers live in
 * `screenplayKeyboard.ts`.
 */

/** lowercase → UPPERCASE → Sentence case (then back to lowercase). */
export function cycleCase(text: string): string {
  const hasLetters = /[A-Za-z]/.test(text);
  const isUpper = hasLetters && text === text.toUpperCase() && text !== text.toLowerCase();
  const isLower = hasLetters && text === text.toLowerCase() && text !== text.toUpperCase();
  if (isLower) return text.toUpperCase();
  if (isUpper) return toSentenceCase(text);
  return text.toLowerCase();
}

/** Lowercase everything, then capitalize the first letter of each sentence. */
export function toSentenceCase(text: string): string {
  return text
    .toLowerCase()
    .replace(/(^\s*[a-z])|([.!?]\s+[a-z])/g, (m) => m.toUpperCase());
}

/** Toggle a centered line: wrap with "> … <", or unwrap if already centered. */
export function toggleCenter(line: string): string {
  const t = line.trim();
  const m = t.match(/^>\s*(.*?)\s*<$/);
  return m ? m[1] : `> ${t} <`;
}
