import { useEffect, useRef, type CSSProperties } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
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

function buildDecorations(doc: PMNode, formatted: boolean, mode: string): DecorationSet {
  if (!formatted || !SCRIPT_MODES.has(mode)) return DecorationSet.empty;
  const items: { offset: number; size: number; text: string }[] = [];
  doc.forEach((node, offset) => { items.push({ offset, size: node.nodeSize, text: node.textContent }); });
  const classes = classifyLines(items.map((it) => it.text).join("\n"));
  const decos: Decoration[] = [];
  items.forEach((it, i) => {
    const style = styleFor(classes[i]?.type ?? "action");
    if (style) decos.push(Decoration.node(it.offset, it.offset + it.size, { style }));
  });
  return DecorationSet.create(doc, decos);
}

// ---- base stylesheet (injected once) ----
const PM_CSS = `
.pm-prose{outline:none;white-space:pre-wrap;word-break:break-word;color:var(--txt);font-family:'Courier Prime',monospace;font-size:15px;line-height:1.62;caret-color:var(--accent);min-height:1.6em;}
.pm-prose:focus{outline:none;}
.pm-prose p{margin:0;}
.pm-prose p.is-editor-empty:first-child::before{content:attr(data-placeholder);color:var(--txt3);float:left;height:0;pointer-events:none;}
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
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  onFocusActive: () => void;
  onSelectionText: (text: string) => void;
  onBlur: () => void;
  formatted: boolean;
  mode: string;
  placeholder?: string;
}) {
  useProseCss();
  // latest callbacks + format flags via refs, so the once-created editor never
  // runs a stale closure.
  const cb = useRef({ onChange, onFocusActive, onSelectionText, onBlur });
  cb.current = { onChange, onFocusActive, onSelectionText, onBlur };
  const fmt = useRef({ formatted, mode });
  fmt.current = { formatted, mode };
  const emitted = useRef(value);
  // Memoize decorations on doc identity: ProseMirror calls `decorations` on every
  // state change (incl. selection-only), but the classification only changes when
  // the doc does — so reuse the last set unless the doc / format inputs changed.
  const decoCache = useRef<{ doc: PMNode | null; formatted: boolean; mode: string; set: DecorationSet }>({ doc: null, formatted: false, mode: "", set: DecorationSet.empty });

  // Created ONCE (deps []) so undo/redo history survives prop changes. format/mode
  // reactivity is handled by the ref + the decoration-refresh effect below; the
  // `placeholder` is therefore captured once — keep it a constant per editor (it is).
  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: false, blockquote: false, bulletList: false, orderedList: false, listItem: false,
        codeBlock: false, code: false, bold: false, italic: false, strike: false,
        horizontalRule: false, hardBreak: false,
      }),
      Placeholder.configure({ placeholder: placeholder ?? "Write the scene…" }),
    ],
    content: textToDoc(value),
    editorProps: {
      attributes: { class: "pm-prose", "data-prose": "", spellcheck: "true" },
      decorations: (state) => {
        const c = decoCache.current;
        if (c.doc === state.doc && c.formatted === fmt.current.formatted && c.mode === fmt.current.mode) return c.set;
        const set = buildDecorations(state.doc, fmt.current.formatted, fmt.current.mode);
        decoCache.current = { doc: state.doc, formatted: fmt.current.formatted, mode: fmt.current.mode, set };
        return set;
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
      cb.current.onSelectionText(from === to ? "" : editor.state.doc.textBetween(from, to, "\n"));
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
    editor.commands.setContent(textToDoc(value), false);
    emitted.current = value;
  }, [value, editor]);

  // Re-run decorations when the format toggle / writing mode changes (no doc edit).
  useEffect(() => {
    if (editor) editor.view.dispatch(editor.state.tr);
  }, [formatted, mode, editor]);

  return <EditorContent editor={editor} />;
}
