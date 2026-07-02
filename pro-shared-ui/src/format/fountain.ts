import type { CSSProperties } from "react";

/**
 * A small, self-contained Fountain line classifier for the Pro writing surface's
 * screenplay FORMAT view. It re-implements the public Fountain spec heuristics
 * (scene heading / character / dialogue / parenthetical / transition / action / …)
 * — it does NOT import the Whiteboard's classifier (forbidden cross-line dep); both
 * lines independently implement the same standard format. Pure + deterministic.
 */

export type FountainType =
  | "scene_heading" | "action" | "character" | "dialogue" | "parenthetical"
  | "transition" | "section" | "synopsis" | "note" | "centered" | "lyrics"
  | "page_break" | "empty";

const SCENE_PREFIXES = ["INT./EXT.", "INT/EXT.", "I/E.", "INT.", "EXT.", "EST."];
// Emphatic all-caps lines / production tokens that are NOT speaker cues.
const NOT_A_CUE = new Set([
  "the end", "cut", "fade", "fade in", "fade out", "suddenly", "later", "moments later",
  "continuous", "meanwhile", "no", "yes", "what", "stop", "wait",
  "blackout", "black out", "intercut", "insert", "angle on", "angle", "back to scene",
  "back to", "montage", "smash cut", "match cut", "omitted", "end", "title card",
  "superimpose", "super", "reveal", "beat", "pause", "silence", "darkness",
]);

const isSceneHeading = (t: string) => /^\.[A-Za-z]/.test(t) || SCENE_PREFIXES.some((p) => t.toUpperCase().startsWith(p));
const isAllCaps = (t: string) => /[A-Za-z]/.test(t) && t === t.toUpperCase() && !/[a-z]/.test(t);
const isTransition = (t: string) => (t.startsWith(">") && !t.endsWith("<")) || (t.split(/\s+/).length <= 4 && /\bTO:$/.test(t.toUpperCase()));
const isParenthetical = (t: string) => t.startsWith("(") && t.endsWith(")");
const isNote = (t: string) => t.startsWith("[[") && t.endsWith("]]");
const isCentered = (t: string) => t.startsWith(">") && t.endsWith("<");
const isPageBreak = (t: string) => /^=+$/.test(t) && t.length >= 3;
const isSynopsis = (t: string) => t.startsWith("=") && !isPageBreak(t);
const isLyrics = (t: string) => t.startsWith("~");

function looksLikeCharacterCue(t: string): boolean {
  const name = t.replace(/\s*\([^)]*\)\s*$/, "").trim();
  if (!name) return false;
  if (/[.!?,:;]/.test(name)) return false;
  if (NOT_A_CUE.has(name.toLowerCase())) return false;
  return name.split(/\s+/).length <= 3;
}

export interface FountainLine { text: string; type: FountainType }

/** Classify each line of a scene's prose into a Fountain element type. */
export function classifyLines(text: string): FountainLine[] {
  const lines = (text || "").split("\n");
  const out: FountainLine[] = [];
  let prev: FountainType = "empty";
  const hasContentAfter = (i: number) => {
    const n = lines[i + 1];
    return n != null && n.trim() !== "" && !n.trim().startsWith("#");
  };

  for (let i = 0; i < lines.length; i += 1) {
    const raw = lines[i] ?? "";
    const t = raw.trim();
    let type: FountainType;
    if (t === "") type = "empty";
    else if (isPageBreak(t)) type = "page_break";
    else if (t.startsWith("#")) type = "section";
    else if (isSynopsis(t)) type = "synopsis";
    else if (isNote(t)) type = "note";
    else if (isCentered(t)) type = "centered";
    else if (isTransition(t)) type = "transition";
    else if (isSceneHeading(t)) type = "scene_heading";
    else if (t.startsWith("!")) type = "action";
    else if (t.startsWith("@")) type = "character";
    else if (isLyrics(t)) type = "lyrics";
    else if (isParenthetical(t) && (prev === "character" || prev === "parenthetical" || prev === "dialogue")) type = "parenthetical";
    else if (prev === "character") type = "dialogue";
    else if (prev === "parenthetical" || prev === "dialogue") type = isAllCaps(t) && looksLikeCharacterCue(t) && hasContentAfter(i) ? "character" : "dialogue";
    else if (isAllCaps(t) && looksLikeCharacterCue(t) && hasContentAfter(i)) type = "character";
    else type = "action";
    out.push({ text: raw, type });
    prev = type;
  }
  return out;
}

/** Strip a forced-element marker (. @ ! ~ > <) for the rendered view. */
export function renderLineText(line: FountainLine): string {
  const t = line.text;
  switch (line.type) {
    case "scene_heading": return t.replace(/^\s*\./, "");
    case "character": return t.replace(/^\s*@/, "").replace(/\s*\^\s*$/, "");
    case "action": return t.replace(/^\s*!/, "");
    case "lyrics": return t.replace(/^\s*~/, "");
    case "transition": return t.replace(/^\s*>/, "").trim();
    case "centered": return t.replace(/^\s*>/, "").replace(/<\s*$/, "").trim();
    case "section": return t.replace(/^\s*#+\s*/, "");
    case "synopsis": return t.replace(/^\s*=\s*/, "");
    default: return t;
  }
}

/** Screenplay indentation/emphasis per element (the manuscript column is the page). */
export function fountainLineStyle(type: FountainType): CSSProperties {
  switch (type) {
    case "scene_heading": return { fontWeight: 700, textTransform: "uppercase", marginTop: "1.3em", letterSpacing: ".02em" };
    case "character": return { marginLeft: "38%", textTransform: "uppercase", marginTop: ".7em" };
    case "parenthetical": return { marginLeft: "30%", color: "var(--txt2)" };
    case "dialogue": return { marginLeft: "18%", marginRight: "16%" };
    case "transition": return { textAlign: "right", textTransform: "uppercase", marginTop: ".7em", color: "var(--accent)" };
    case "section": return { fontFamily: "'Chakra Petch'", textTransform: "uppercase", letterSpacing: ".2em", color: "var(--accent)", fontSize: 11, marginTop: "1.2em" };
    case "synopsis": return { fontStyle: "italic", color: "var(--txt3)" };
    case "note": return { color: "var(--amber)", fontStyle: "italic", opacity: 0.8 };
    case "centered": return { textAlign: "center" };
    case "lyrics": return { marginLeft: "18%", fontStyle: "italic", color: "var(--txt2)" };
    default: return {}; // action
  }
}
