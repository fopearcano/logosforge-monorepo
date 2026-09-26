import { useEffect, useRef, type CSSProperties } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { Placeholder } from "@tiptap/extensions";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import type { Node as PMNode } from "@tiptap/pm/model";
import { classifyLines, fountainLineStyle, type FountainType } from "../../format/fountain";

/**
 * The true in-place writing surface — a TipTap/ProseMirror editor whose document
 * is one paragraph per line, backed by PLAIN TEXT (round-trips exactly to the
 * scene's `content` string). In script modes it applies live per-line Fountain
 * formatting as *node decorations* (indentation / uppercase / alignment) — which
 * are display-only, so the underlying text (incl. forced markers) is never
 * mutated and the caret stays put. Built on ProseMirror precisely because the
 * hand-rolled contentEditable prototype broke on Firefox caret/paste/<br>.
 */

const SCRIPT_MODES = new Set(["screenplay", "stage_script", "stage", "series"]);
const COMMENT_CONTEXT = 32;

export interface ProseCommentHighlight {
  commentId: number;
  fromOffset: number;
  toOffset: number;
  resolved: boolean;
}

export interface ProseSelectionRange {
  fromOffset: number;
  toOffset: number;
  quote: string;
  prefix: string;
  suffix: string;
}

// ---- plain-text ⇄ ProseMirror doc (1 line = 1 paragraph) ----
function docToText(doc: PMNode): string {
  const lines: string[] = [];
  doc.forEach((n) => { lines.push(n.textContent); });
  return lines.join("\n");
}
function textToDoc(text: string) {
  const lines = (text ?? "").split("\n");
  return {
    type: "doc",
    content: lines.map((l) => (l ? { type: "paragraph", content: [{ type: "text", text: l }] } : { type: "paragraph" })),
  };
}

function isUtf16Boundary(text: string, offset: number): boolean {
  if (offset <= 0 || offset >= text.length) return true;
  const before = text.charCodeAt(offset - 1);
  const after = text.charCodeAt(offset);
  return !(before >= 0xd800 && before <= 0xdbff && after >= 0xdc00 && after <= 0xdfff);
}

/** Convert a ProseMirror document position into the UTF-16 offset used by the
 * core comment contract. Paragraph boundaries count as one newline, matching
 * docToText(). */
export function proseDocumentPositionToTextOffset(doc: PMNode, position: number): number {
  const bounded = Math.max(0, Math.min(position, doc.content.size));
  let plainOffset = 0;
  let located: number | null = null;
  doc.forEach((node, nodeOffset, index) => {
    if (located != null) return;
    const contentStart = nodeOffset + 1;
    const contentEnd = contentStart + node.textContent.length;
    if (bounded <= contentEnd) {
      located = plainOffset + Math.max(0, Math.min(bounded - contentStart, node.textContent.length));
      return;
    }
    plainOffset += node.textContent.length;
    if (index < doc.childCount - 1) plainOffset += 1;
  });
  return located ?? plainOffset;
}

function proseTextOffsetToDocumentPosition(doc: PMNode, offset: number): number {
  const textLength = docToText(doc).length;
  const bounded = Math.max(0, Math.min(offset, textLength));
  let plainOffset = 0;
  let located: number | null = null;
  doc.forEach((node, nodeOffset, index) => {
    if (located != null) return;
    const length = node.textContent.length;
    const plainEnd = plainOffset + length;
    if (bounded <= plainEnd) {
      located = nodeOffset + 1 + (bounded - plainOffset);
      return;
    }
    plainOffset = plainEnd;
    if (index < doc.childCount - 1) {
      if (bounded === plainOffset + 1) {
        located = nodeOffset + node.nodeSize + 1;
        return;
      }
      plainOffset += 1;
    }
  });
  return located ?? doc.content.size;
}

/** Split one plain-text UTF-16 highlight into per-paragraph ProseMirror ranges. */
export function proseCommentDocumentRanges(
  doc: PMNode,
  fromOffset: number,
  toOffset: number,
): Array<{ from: number; to: number }> {
  const from = Math.max(0, Math.min(fromOffset, toOffset));
  const to = Math.max(from, Math.max(fromOffset, toOffset));
  if (from === to) {
    const position = proseTextOffsetToDocumentPosition(doc, from);
    return [{ from: position, to: position }];
  }
  const ranges: Array<{ from: number; to: number }> = [];
  let plainOffset = 0;
  doc.forEach((node, nodeOffset, index) => {
    const length = node.textContent.length;
    const plainEnd = plainOffset + length;
    const overlapFrom = Math.max(from, plainOffset);
    const overlapTo = Math.min(to, plainEnd);
    if (overlapTo > overlapFrom) {
      ranges.push({
        from: nodeOffset + 1 + (overlapFrom - plainOffset),
        to: nodeOffset + 1 + (overlapTo - plainOffset),
      });
    }
    plainOffset = plainEnd + (index < doc.childCount - 1 ? 1 : 0);
  });
  return ranges;
}

// ---- CSSProperties → inline CSS string (for the node decoration) ----
const UNITLESS = new Set(["fontWeight", "opacity", "lineHeight", "zIndex", "flexGrow", "flexShrink", "order"]);
function cssString(s: CSSProperties): string {
  return Object.entries(s)
    .map(([k, v]) => {
      if (v == null) return "";
      const prop = k.replace(/[A-Z]/g, (m) => "-" + m.toLowerCase());
      const val = typeof v === "number" && !UNITLESS.has(k) ? `${v}px` : String(v);
      return `${prop}:${val}`;
    })
    .filter(Boolean)
    .join(";");
}
const STYLE_CACHE: Partial<Record<FountainType, string>> = {};
function styleFor(type: FountainType): string {
  return (STYLE_CACHE[type] ??= cssString(fountainLineStyle(type)));
}

function buildDecorations(
  doc: PMNode,
  formatted: boolean,
  mode: string,
  commentHighlights: ProseCommentHighlight[],
): DecorationSet {
  const items: { offset: number; size: number; text: string }[] = [];
  doc.forEach((node, offset) => { items.push({ offset, size: node.nodeSize, text: node.textContent }); });
  const decos: Decoration[] = [];
  if (formatted && SCRIPT_MODES.has(mode)) {
    const classes = classifyLines(items.map((it) => it.text).join("\n"));
    items.forEach((it, i) => {
      const style = styleFor(classes[i]?.type ?? "action");
      if (style) decos.push(Decoration.node(it.offset, it.offset + it.size, { style }));
    });
  }

  // ProseMirror combines the attributes of overlapping inline decorations and
  // the last data attribute wins. Segment the ranges ourselves so an overlap
  // retains every thread id and one click can open the complete stack.
  const inlineRanges: Array<{ from: number; to: number; commentId: number; resolved: boolean }> = [];
  const pointRanges = new Map<number, Array<{ commentId: number; resolved: boolean }>>();
  for (const highlight of commentHighlights) {
    for (const range of proseCommentDocumentRanges(doc, highlight.fromOffset, highlight.toOffset)) {
      if (range.from === range.to) {
        const points = pointRanges.get(range.from);
        const value = { commentId: highlight.commentId, resolved: highlight.resolved };
        if (points) points.push(value); else pointRanges.set(range.from, [value]);
      } else {
        inlineRanges.push({ ...range, commentId: highlight.commentId, resolved: highlight.resolved });
      }
    }
  }

  const boundaries = [...new Set(inlineRanges.flatMap((range) => [range.from, range.to]))].sort((left, right) => left - right);
  for (let index = 0; index < boundaries.length - 1; index += 1) {
    const from = boundaries[index]!;
    const to = boundaries[index + 1]!;
    if (to <= from) continue;
    const active = inlineRanges.filter((range) => range.from <= from && range.to >= to);
    if (!active.length) continue;
    const ids = [...new Set(active.map((range) => range.commentId))].sort((left, right) => left - right);
    const resolved = active.every((range) => range.resolved);
    const label = ids.length === 1 ? "Open comment thread" : `Open ${ids.length} comment threads`;
    decos.push(Decoration.inline(from, to, {
      class: resolved ? "pm-comment-mark pm-comment-mark--resolved" : "pm-comment-mark",
      "data-comment-ids": ids.join(","),
      role: "button",
      tabindex: "0",
      title: label,
      "aria-label": label,
    }));
  }

  for (const [position, points] of pointRanges) {
    const ids = [...new Set(points.map((point) => point.commentId))].sort((left, right) => left - right);
    const resolved = points.every((point) => point.resolved);
    const className = resolved ? "pm-comment-mark pm-comment-mark--resolved" : "pm-comment-mark";
    const label = ids.length === 1 ? "Open comment thread" : `Open ${ids.length} comment threads`;
    decos.push(Decoration.widget(position, () => {
      const marker = document.createElement("span");
      marker.setAttribute("data-comment-ids", ids.join(","));
      marker.setAttribute("role", "button");
      marker.setAttribute("tabindex", "0");
      marker.setAttribute("title", label);
      marker.setAttribute("aria-label", label);
      marker.className = `${className} pm-comment-caret`;
      marker.textContent = "◈";
      return marker;
    }, { key: `comment-caret-${position}-${ids.join("-")}`, side: 1 }));
  }
  return DecorationSet.create(doc, decos);
}

// ---- base stylesheet (injected once) ----
const PM_CSS = `
.pm-prose{outline:none;white-space:pre-wrap;word-break:break-word;color:var(--txt);font-family:'Courier Prime',monospace;font-size:15px;line-height:1.62;caret-color:var(--accent);min-height:1.6em;}
.pm-prose:focus{outline:none;}
.pm-prose p{margin:0;}
.pm-prose p.is-editor-empty:first-child::before{content:attr(data-placeholder);color:var(--txt3);float:left;height:0;pointer-events:none;}
.pm-comment-mark{background:rgba(255,190,61,.2);border-bottom:1px solid var(--amber);border-radius:2px;cursor:pointer;box-decoration-break:clone;-webkit-box-decoration-break:clone;}
.pm-comment-mark:hover,.pm-comment-mark:focus{background:rgba(255,190,61,.34);outline:1px solid var(--amber);outline-offset:1px;}
.pm-comment-mark--resolved{background:rgba(84,212,158,.11);border-bottom-color:var(--green);}
.pm-comment-caret{display:inline-block;width:1.1em;margin:0 .12em;color:var(--amber);font-family:'Chakra Petch',sans-serif;font-size:.78em;line-height:1;text-align:center;vertical-align:middle;}
`;
let cssInjected = false;
function useProseCss() {
  useEffect(() => {
    if (cssInjected || typeof document === "undefined") return;
    cssInjected = true;
    if (document.getElementById("lf-pm-styles")) return; // survive HMR / module re-eval
    const el = document.createElement("style");
    el.id = "lf-pm-styles";
    el.textContent = PM_CSS;
    document.head.appendChild(el);
  }, []);
}

export function ProseEditor({
  value,
  onChange,
  onFocusActive,
  onSelectionText,
  onBlur,
  formatted,
  mode,
  commentHighlights = [],
  onSelectionRange,
  onCommentActivate,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  onFocusActive: () => void;
  onSelectionText: (text: string) => void;
  onBlur: () => void;
  formatted: boolean;
  mode: string;
  commentHighlights?: ProseCommentHighlight[];
  onSelectionRange?: (range: ProseSelectionRange | null) => void;
  onCommentActivate?: (commentIds: number[]) => void;
  placeholder?: string;
}) {
  useProseCss();
  // latest callbacks + format flags via refs, so the once-created editor never
  // runs a stale closure.
  const cb = useRef({ onChange, onFocusActive, onSelectionText, onBlur, onSelectionRange, onCommentActivate });
  cb.current = { onChange, onFocusActive, onSelectionText, onBlur, onSelectionRange, onCommentActivate };
  const fmt = useRef({ formatted, mode, commentHighlights });
  fmt.current = { formatted, mode, commentHighlights };
  const emitted = useRef(value);
  // Memoize decorations on doc identity: ProseMirror calls `decorations` on every
  // state change (incl. selection-only), but the classification only changes when
  // the doc does — so reuse the last set unless the doc / format inputs changed.
  const decoCache = useRef<{ doc: PMNode | null; formatted: boolean; mode: string; commentsKey: string; set: DecorationSet }>({ doc: null, formatted: false, mode: "", commentsKey: "", set: DecorationSet.empty });

  // Created ONCE (deps []) so undo/redo history survives prop changes. format/mode
  // reactivity is handled by the ref + the decoration-refresh effect below; the
  // `placeholder` is therefore captured once — keep it a constant per editor (it is).
  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: false, blockquote: false, bulletList: false, orderedList: false, listItem: false,
        codeBlock: false, code: false, bold: false, italic: false, strike: false,
        horizontalRule: false, hardBreak: false, link: false, underline: false,
        listKeymap: false,
      }),
      Placeholder.configure({ placeholder: placeholder ?? "Write the scene…" }),
    ],
    content: textToDoc(value),
    editorProps: {
      attributes: { class: "pm-prose", "data-prose": "", spellcheck: "true" },
      decorations: (state) => {
        const c = decoCache.current;
        const commentsKey = fmt.current.commentHighlights
          .map((item) => `${item.commentId}:${item.fromOffset}:${item.toOffset}:${item.resolved ? 1 : 0}`)
          .join("|");
        if (c.doc === state.doc && c.formatted === fmt.current.formatted && c.mode === fmt.current.mode && c.commentsKey === commentsKey) return c.set;
        const set = buildDecorations(state.doc, fmt.current.formatted, fmt.current.mode, fmt.current.commentHighlights);
        decoCache.current = { doc: state.doc, formatted: fmt.current.formatted, mode: fmt.current.mode, commentsKey, set };
        return set;
      },
      handleDOMEvents: {
        click: (_view, event) => {
          const target = event.target instanceof Element ? event.target.closest<HTMLElement>("[data-comment-ids]") : null;
          if (!target) return false;
          const ids = (target.dataset.commentIds ?? "").split(",").map(Number).filter(Number.isSafeInteger);
          if (!ids.length) return false;
          cb.current.onCommentActivate?.(ids);
          event.preventDefault();
          return true;
        },
        keydown: (_view, event) => {
          if (event.key !== "Enter" && event.key !== " ") return false;
          const target = event.target instanceof Element ? event.target.closest<HTMLElement>("[data-comment-ids]") : null;
          if (!target) return false;
          const ids = (target.dataset.commentIds ?? "").split(",").map(Number).filter(Number.isSafeInteger);
          if (!ids.length) return false;
          cb.current.onCommentActivate?.(ids);
          event.preventDefault();
          return true;
        },
      },
    },
    onUpdate: ({ editor }) => {
      const text = docToText(editor.state.doc);
      emitted.current = text;
      cb.current.onChange(text);
    },
    onFocus: () => cb.current.onFocusActive(),
    onSelectionUpdate: ({ editor }) => {
      const { from, to } = editor.state.selection;
      if (from === to) {
        cb.current.onSelectionText("");
        cb.current.onSelectionRange?.(null);
        return;
      }
      const text = docToText(editor.state.doc);
      const fromOffset = proseDocumentPositionToTextOffset(editor.state.doc, from);
      const toOffset = proseDocumentPositionToTextOffset(editor.state.doc, to);
      const quote = text.slice(fromOffset, toOffset);
      cb.current.onSelectionText(quote);
      cb.current.onSelectionRange?.(
        quote && isUtf16Boundary(text, fromOffset) && isUtf16Boundary(text, toOffset)
          ? {
            fromOffset,
            toOffset,
            quote,
            prefix: text.slice(Math.max(0, fromOffset - COMMENT_CONTEXT), fromOffset),
            suffix: text.slice(toOffset, toOffset + COMMENT_CONTEXT),
          }
          : null,
      );
    },
    onBlur: () => cb.current.onBlur(),
  }, []);

  // External content changes (AI apply / refetch reconcile) — replace the doc,
  // but ONLY when it's a genuine outside change (not an echo of our own edit),
  // so active typing is never clobbered. Never touch the editor the writer is
  // currently in (belt-and-suspenders over SceneEditor's dirty-guard).
  useEffect(() => {
    if (!editor || editor.isFocused) return;
    if (value === emitted.current) return;
    if (value === docToText(editor.state.doc)) { emitted.current = value; return; }
    editor.commands.setContent(textToDoc(value), { emitUpdate: false });
    emitted.current = value;
  }, [value, editor]);

  // Re-run decorations when the format toggle / writing mode changes (no doc edit).
  const commentsKey = commentHighlights
    .map((item) => `${item.commentId}:${item.fromOffset}:${item.toOffset}:${item.resolved ? 1 : 0}`)
    .join("|");
  useEffect(() => {
    if (editor) editor.view.dispatch(editor.state.tr);
  }, [formatted, mode, commentsKey, editor]);

  return <EditorContent editor={editor} />;
}
