import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import type { SceneDTO } from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useStudio, useManuscriptTarget } from "../../adapters/StudioProvider";
import { useSelection } from "../../adapters/selection";
import { useScenes } from "../../hooks";
import { classifyLines, renderLineText, fountainLineStyle } from "../../format/fountain";
import { ProseEditor } from "./ProseEditor";

/**
 * The Studio's genuine writing surface — a continuous, inline-editable manuscript.
 * Each scene autosaves to the core via `updateScene` (debounced) with per-scene save
 * state + live counts; reconciliation guards (edit-sequence + in-flight serialize)
 * keep a refetch from clobbering active typing. In script modes the FORMAT toggle
 * shows a LIVE screenplay-formatted preview of the active scene beside the plain
 * editor — edit on the left, see Fountain elements (scene heading / character /
 * dialogue / …) render live on the right. (A true in-textarea contentEditable was
 * prototyped but its cross-browser caret/paste/Firefox hazards made a read-only live
 * preview the robust choice.) Also: scene reorder/delete + cross-panel selection.
 */

const SAVE_DEBOUNCE_MS = 800;
const SCRIPT_MODES = new Set(["screenplay", "stage_script", "stage", "series"]);

const panelBox: CSSProperties = {
  position: "relative", width: "100%", height: "100%",
  background: "radial-gradient(120% 70% at 50% 0%,var(--panel),var(--base))",
  border: "1px solid var(--line)", boxShadow: "0 16px 60px rgba(0,0,0,.6)",
  overflow: "hidden", display: "flex", flexDirection: "column",
};

const wordCount = (t: string) => (t.trim() ? t.trim().split(/\s+/).length : 0);
const actLabel = (act: string) => (/^act\b/i.test(act.trim()) ? act.trim() : `ACT ${act.trim()}`);

const message = (text: string) => (
  <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: "34px 0", textAlign: "center", fontSize: 12, color: "var(--txt3)", letterSpacing: ".04em" }}>{text}</div>
);

const linkBtn: CSSProperties = { background: "transparent", border: "none", padding: 0, font: "inherit", cursor: "pointer", letterSpacing: ".14em", fontSize: 9.5 };
const iconBtn: CSSProperties = { background: "transparent", border: "none", padding: "0 3px", font: "inherit", cursor: "pointer", color: "var(--txt3)", fontSize: 12, lineHeight: 1 };

type SaveStatus = "idle" | "dirty" | "saving" | "saved" | "error";
type FlushHandlers = { flush: () => Promise<boolean>; cancel: () => void };
const STATUS_GLYPH: Record<SaveStatus, { g: string; c: string; t: string }> = {
  idle: { g: "", c: "var(--txt3)", t: "" },
  dirty: { g: "●", c: "var(--amber)", t: "unsaved" },
  saving: { g: "⋯", c: "var(--accent)", t: "saving…" },
  saved: { g: "✓", c: "var(--green)", t: "saved" },
  error: { g: "!", c: "var(--crimson)", t: "save failed — keeps the change; retries on the next edit / blur" },
};

const ActDivider = ({ scene }: { scene: SceneDTO }) => (
  <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "0 0 18px" }}>
    <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 10, letterSpacing: ".3em", color: "var(--accent)" }}>
      {actLabel(scene.act)}{scene.chapter ? ` · ${scene.chapter}` : ""}
    </span>
    <span style={{ flex: 1, height: 1, background: "var(--line2)" }} />
  </div>
);

// --------------------------------------------------------------- Scene editor
function SceneEditor({
  scene, index, showAct, formatted, mode, busy, onWords, onContent, onStatus, onActive, registerFlush,
  onDelete, onMoveUp, onMoveDown, isFirst, isLast,
}: {
  scene: SceneDTO; index: number; showAct: boolean; formatted: boolean; mode: string; busy: boolean;
  onWords: (id: number, n: number) => void;
  onContent: (id: number, c: string) => void;
  onStatus: (id: number, s: SaveStatus) => void;
  onActive: (id: number) => void;
  registerFlush: (id: number, h: FlushHandlers | null) => void;
  onDelete: () => void; onMoveUp: () => void; onMoveDown: () => void;
  isFirst: boolean; isLast: boolean;
}) {
  const { api, projectId } = useStudio();
  const { setSelection } = useSelection();
  const [title, setTitle] = useState(scene.title ?? "");
  const [content, setContent] = useState(scene.content ?? "");
  const [act, setAct] = useState(scene.act ?? "");
  const [chapter, setChapter] = useState(scene.chapter ?? "");
  const [plotline, setPlotline] = useState(scene.plotline ?? "");
  const [summary, setSummary] = useState(scene.summary ?? "");
  const [showDetails, setShowDetails] = useState(false);
  const [status, setStatus] = useState<SaveStatus>("idle");
  const [confirmDel, setConfirmDel] = useState(false);
  const dirty = useRef(false);
  const timer = useRef<number | null>(null);
  const editSeq = useRef(0);
  const inFlight = useRef(false);
  const pendingAgain = useRef(false);
  const disposed = useRef(false);
  const mounted = useRef(true);
  useEffect(() => () => { mounted.current = false; }, []);

  const setStat = useCallback((s: SaveStatus) => { if (!mounted.current) return; setStatus(s); onStatus(scene.id, s); }, [onStatus, scene.id]);
  // report word count + live content (for the FORMAT preview) upward
  useEffect(() => { onWords(scene.id, wordCount(content)); onContent(scene.id, content); }, [content, onWords, onContent, scene.id]);

  useEffect(() => {
    if (!dirty.current) {
      setTitle(scene.title ?? ""); setContent(scene.content ?? "");
      setAct(scene.act ?? ""); setChapter(scene.chapter ?? ""); setPlotline(scene.plotline ?? ""); setSummary(scene.summary ?? "");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scene.id, scene.title, scene.content, scene.act, scene.chapter, scene.plotline, scene.summary]);

  const saveRef = useRef<() => Promise<void>>(async () => {});
  saveRef.current = async () => {
    if (projectId == null || disposed.current) return;
    if (inFlight.current) { pendingAgain.current = true; return; }
    inFlight.current = true;
    const seq = editSeq.current;
    setStat("saving");
    try {
      await api.updateScene(projectId, scene.id, { title, content, act, chapter, plotline, summary });
      if (editSeq.current === seq) { dirty.current = false; setStat("saved"); }
    } catch {
      setStat("error");
    } finally {
      inFlight.current = false;
      if (pendingAgain.current && !disposed.current) { pendingAgain.current = false; void saveRef.current(); }
    }
  };
  const schedule = () => {
    editSeq.current += 1; dirty.current = true; setStat("dirty");
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = window.setTimeout(() => { timer.current = null; void saveRef.current(); }, SAVE_DEBOUNCE_MS);
  };
  const flushNow = useCallback(async (): Promise<boolean> => {
    if (timer.current !== null) { clearTimeout(timer.current); timer.current = null; }
    if (dirty.current && !disposed.current) await saveRef.current();
    return !dirty.current;
  }, []);
  const cancelSave = useCallback(() => {
    if (timer.current !== null) { clearTimeout(timer.current); timer.current = null; }
    disposed.current = true; dirty.current = false;
  }, []);
  useEffect(() => {
    registerFlush(scene.id, { flush: flushNow, cancel: cancelSave });
    return () => { registerFlush(scene.id, null); void flushNow(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const lastPub = useRef("");
  const publishText = useCallback((text: string) => {
    const key = `${scene.id}:${text}`;
    if (key === lastPub.current) return;
    lastPub.current = key;
    setSelection({ sceneId: scene.id, text, section: "Manuscript" });
  }, [scene.id, setSelection]);

  const st = STATUS_GLYPH[status];
  return (
    <div id={`ms-scene-${scene.id}`} style={{ marginBottom: 30, scrollMarginTop: 18 }}>
      {showAct && scene.act && <ActDivider scene={scene} />}
      <div style={{ display: "flex", gap: 12, alignItems: "baseline", marginBottom: 10 }}>
        <span style={{ fontFamily: "'Chakra Petch'", color: "var(--txt3)", fontSize: 13, flex: "none" }}>{index + 1}</span>
        <input
          value={title}
          onChange={(e) => { setTitle(e.target.value); schedule(); }}
          onFocus={() => onActive(scene.id)}
          onBlur={() => void flushNow()}
          placeholder="UNTITLED SCENE"
          aria-label={`Scene ${index + 1} title`}
          spellCheck={false}
          style={{ flex: 1, minWidth: 0, background: "transparent", border: "none", outline: "none", color: "var(--strong)", fontWeight: 700, letterSpacing: ".02em", fontSize: 15, fontFamily: "'Courier Prime',monospace", padding: 0 }}
        />
        <span title={st.t} style={{ flex: "none", fontSize: 11, color: st.c, minWidth: 12, textAlign: "right" }}>{st.g}</span>
        {confirmDel ? (
          <span style={{ display: "flex", gap: 4, alignItems: "center", flex: "none", fontSize: 9 }}>
            <span style={{ color: "var(--txt3)" }}>delete?</span>
            <button type="button" aria-label="Confirm delete scene" onClick={onDelete} style={{ ...iconBtn, color: "var(--crimson)" }}>✓</button>
            <button type="button" aria-label="Cancel delete" onClick={() => setConfirmDel(false)} style={iconBtn}>✗</button>
          </span>
        ) : (
          <span style={{ display: "flex", gap: 2, alignItems: "center", flex: "none" }}>
            <button type="button" aria-label="Scene details" title="Act / chapter / summary" onClick={() => setShowDetails((v) => !v)} style={{ ...iconBtn, color: showDetails ? "var(--accent)" : "var(--txt3)" }}>⋮</button>
            <button type="button" aria-label="Move scene up" disabled={isFirst || busy} onClick={onMoveUp} style={{ ...iconBtn, opacity: isFirst || busy ? 0.25 : 1 }}>↑</button>
            <button type="button" aria-label="Move scene down" disabled={isLast || busy} onClick={onMoveDown} style={{ ...iconBtn, opacity: isLast || busy ? 0.25 : 1 }}>↓</button>
            <button type="button" aria-label="Delete scene" onClick={() => setConfirmDel(true)} style={iconBtn}>✕</button>
          </span>
        )}
      </div>
      {showDetails && (
        <div style={{ display: "flex", gap: 10, margin: "0 0 12px", flexWrap: "wrap", alignItems: "center" }}>
          {([["ACT", act, setAct, "e.g. Act I", 90], ["CHAPTER", chapter, setChapter, "e.g. 1", 90], ["PLOTLINE", plotline, setPlotline, "e.g. A-plot", 110], ["SUMMARY", summary, setSummary, "one-line scene summary", 300]] as const).map(([label, val, setter, ph, w]) => (
            <label key={label} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 8, letterSpacing: ".14em", color: "var(--txt3)" }}>
              {label}
              <input
                value={val}
                onChange={(e) => { setter(e.target.value); schedule(); }}
                onFocus={() => onActive(scene.id)}
                onBlur={() => void flushNow()}
                placeholder={ph}
                aria-label={`Scene ${index + 1} ${label.toLowerCase()}`}
                style={{ width: w, background: "var(--tint)", border: "1px solid var(--line2)", outline: "none", color: "var(--txt)", fontFamily: "inherit", fontSize: 11, padding: "5px 8px" }}
              />
            </label>
          ))}
        </div>
      )}
      <ProseEditor
        value={content}
        onChange={(v) => { setContent(v); schedule(); }}
        onFocusActive={() => { onActive(scene.id); publishText(""); }}
        onSelectionText={publishText}
        onBlur={() => void flushNow()}
        formatted={formatted}
        mode={mode}
        placeholder="Write the scene…"
      />
    </div>
  );
}

// ------------------------------------------------- Live screenplay-format preview
function FormatPreview({ scene, content }: { scene: SceneDTO | undefined; content: string }) {
  const lines = classifyLines(content || "");
  return (
    <div style={{ width: 340, flex: "none", borderLeft: "1px solid var(--line)", background: "linear-gradient(180deg,var(--panel2),var(--base))", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <div style={{ height: 30, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 13px", borderBottom: "1px solid var(--line)", background: "rgba(76,194,255,.04)" }}>
        <span style={{ fontSize: 8.5, letterSpacing: ".24em", color: "var(--accent)" }}>FORMAT PREVIEW</span>
        <span style={{ fontSize: 8, color: "var(--txt3)", letterSpacing: ".1em" }}>◈ LIVE</span>
      </div>
      <div style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "16px 18px", fontFamily: "'Courier Prime',monospace", fontSize: 13, lineHeight: 1.6, color: "var(--txt)" }}>
        {!scene
          ? <div style={{ color: "var(--txt3)", fontStyle: "italic", fontSize: 11 }}>Click into a scene to preview it formatted.</div>
          : (
            <>
              <div style={{ fontWeight: 700, color: "var(--strong)", marginBottom: 12, letterSpacing: ".02em" }}>{scene.title || "UNTITLED SCENE"}</div>
              {content.trim() === ""
                ? <div style={{ opacity: 0.5, fontStyle: "italic" }}>(no prose yet)</div>
                : lines.map((l, i) =>
                  l.type === "page_break" ? <hr key={i} style={{ border: "none", borderTop: "1px dashed var(--line2)", margin: "14px 0" }} />
                    : l.type === "empty" ? <div key={i} style={{ height: ".8em" }} />
                    : <div key={i} style={fountainLineStyle(l.type)}>{renderLineText(l) || " "}</div>)}
            </>
          )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------ Manuscript rail
function ManuscriptRail({
  scenes, wordsById, statusById, total, onJump, activeId,
}: {
  scenes: SceneDTO[]; wordsById: Record<number, number>; statusById: Record<number, SaveStatus>;
  total: number; onJump: (id: number) => void; activeId: number | null;
}) {
  const maxWords = Math.max(1, ...scenes.map((s) => wordsById[s.id] ?? 0));
  const pages = Math.max(0, Math.round(total / 250));
  const mins = Math.max(0, Math.round(total / 200));
  const avg = scenes.length ? Math.round(total / scenes.length) : 0;
  const Stat = ({ label, value }: { label: string; value: string }) => (
    <div style={{ flex: 1 }}>
      <div style={{ fontFamily: "'Chakra Petch'", fontSize: 19, color: "var(--strong)", letterSpacing: ".02em" }}>{value}</div>
      <div style={{ fontSize: 8, color: "var(--txt3)", letterSpacing: ".16em", marginTop: 2 }}>{label}</div>
    </div>
  );
  return (
    <div style={{ width: 300, flex: "none", borderLeft: "1px solid var(--line)", background: "linear-gradient(180deg,var(--panel2),var(--base))", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <div style={{ height: 30, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 13px", borderBottom: "1px solid var(--line)", background: "rgba(76,194,255,.04)" }}>
        <span style={{ fontSize: 8.5, letterSpacing: ".24em", color: "var(--accent)" }}>MANUSCRIPT</span>
        <span style={{ fontSize: 8, color: "var(--txt3)", letterSpacing: ".1em" }}>◈ LIVE</span>
      </div>
      <div style={{ display: "flex", gap: 10, padding: 14, borderBottom: "1px solid var(--line2)" }}>
        <Stat label="WORDS" value={total.toLocaleString()} /><Stat label="SCENES" value={String(scenes.length)} /><Stat label="~PAGES" value={String(pages)} />
      </div>
      <div style={{ display: "flex", gap: 10, padding: "10px 14px", borderBottom: "1px solid var(--line2)", fontSize: 9, color: "var(--txt2)" }}>
        <span>~{mins} min read</span><span style={{ color: "var(--txt3)" }}>·</span><span>{avg} avg words/scene</span>
      </div>
      <div style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "8px 8px 14px" }}>
        <div style={{ fontSize: 8, color: "var(--txt3)", letterSpacing: ".2em", padding: "4px 6px 8px" }}>SCENES — JUMP</div>
        {scenes.map((s, i) => {
          const w = wordsById[s.id] ?? wordCount(s.content);
          const stt = STATUS_GLYPH[statusById[s.id] ?? "idle"];
          const active = s.id === activeId;
          return (
            <button key={s.id} type="button" onClick={() => onJump(s.id)} title={`Jump to scene ${i + 1}`}
              style={{ display: "block", width: "100%", textAlign: "left", background: active ? "rgba(76,194,255,.07)" : "transparent", border: "none", borderLeft: `2px solid ${active ? "var(--accent)" : "transparent"}`, padding: "6px 6px", cursor: "pointer", font: "inherit" }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 7 }}>
                <span style={{ fontFamily: "'Chakra Petch'", fontSize: 10, color: "var(--txt3)", flex: "none" }}>{i + 1}</span>
                <span style={{ flex: 1, minWidth: 0, fontSize: 11, color: active ? "var(--strong)" : "var(--txt2)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{s.title || "Untitled"}</span>
                {stt.g && <span style={{ fontSize: 9, color: stt.c, flex: "none" }}>{stt.g}</span>}
                <span style={{ fontSize: 9, color: "var(--txt3)", flex: "none" }}>{w}</span>
              </div>
              <div style={{ height: 3, marginTop: 4, background: "var(--tint2)" }}>
                <div style={{ width: `${Math.round((w / maxWords) * 100)}%`, height: "100%", background: active ? "var(--accent)" : "var(--line-cy,#2b6f8f)" }} />
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------- Manuscript
export function ManuscriptEditor(props: PanelProps) {
  const { api, projectId, writingMode } = useStudio();
  const { data: scenes, loading, error, refetch } = useScenes();
  const sorted = [...(scenes ?? [])].sort((a, b) => a.sort_order - b.sort_order);
  const isScript = SCRIPT_MODES.has(String(writingMode ?? ""));

  const [focus, setFocus] = useState(false);
  const [format, setFormat] = useState(false);
  const [busy, setBusy] = useState(false);
  const [wordsById, setWordsById] = useState<Record<number, number>>({});
  const [contentById, setContentById] = useState<Record<number, string>>({});
  const [statusById, setStatusById] = useState<Record<number, SaveStatus>>({});
  const [activeId, setActiveId] = useState<number | null>(null);
  const flushers = useRef(new Map<number, FlushHandlers>());
  const focusAfter = useRef<number | null>(null);
  const showFormat = isScript && format && !focus;

  useEffect(() => { setWordsById({}); setContentById({}); setStatusById({}); setActiveId(null); focusAfter.current = null; }, [projectId]);

  const onWords = useCallback((id: number, n: number) => setWordsById((m) => (m[id] === n ? m : { ...m, [id]: n })), []);
  const onContent = useCallback((id: number, c: string) => setContentById((m) => (m[id] === c ? m : { ...m, [id]: c })), []);
  const onStatus = useCallback((id: number, s: SaveStatus) => setStatusById((m) => ({ ...m, [id]: s })), []);
  const onActive = useCallback((id: number) => setActiveId(id), []);
  const registerFlush = useCallback((id: number, h: FlushHandlers | null) => {
    if (h) flushers.current.set(id, h); else flushers.current.delete(id);
  }, []);

  const total = sorted.reduce((n, s) => n + (wordsById[s.id] ?? wordCount(s.content)), 0);
  const statuses = sorted.map((s) => statusById[s.id]).filter(Boolean) as SaveStatus[];
  const saveLabel = statuses.includes("saving") ? "SAVING…" : statuses.some((s) => s === "dirty" || s === "error") ? "UNSAVED" : "ALL SAVED";
  const saveColor = saveLabel === "SAVING…" ? "var(--accent)" : saveLabel === "UNSAVED" ? "var(--amber)" : "var(--green)";

  const activeScene = sorted.find((s) => s.id === activeId) ?? sorted[0];
  const previewContent = activeScene ? (contentById[activeScene.id] ?? activeScene.content) : "";

  const jump = useCallback((id: number) => {
    setActiveId(id);
    const el = document.getElementById(`ms-scene-${id}`);
    el?.scrollIntoView({ block: "center", behavior: "smooth" });
    (el?.querySelector("[data-prose]") as HTMLElement | null)?.focus({ preventScroll: true });
  }, []);

  useEffect(() => {
    if (focusAfter.current != null && sorted.some((s) => s.id === focusAfter.current)) {
      jump(focusAfter.current); focusAfter.current = null;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sorted.map((s) => s.id).join(",")]);

  // Cross-panel nav: another panel asked to open a specific scene → jump to it.
  const { sceneId: navTarget, clear: clearNavTarget } = useManuscriptTarget();
  useEffect(() => {
    if (navTarget != null && sorted.some((s) => s.id === navTarget)) {
      // wait a tick so the scene DOM exists after a panel switch, THEN jump and
      // clear. Clearing must happen inside the timeout: clearing synchronously
      // flips navTarget→null, which re-runs this effect and its cleanup would
      // cancel the still-pending jump (a real race — the scene never activated).
      const target = navTarget;
      const t = window.setTimeout(() => { jump(target); clearNavTarget(); }, 60);
      return () => clearTimeout(t);
    }
    return undefined;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [navTarget, sorted.map((s) => s.id).join(",")]);

  const addScene = async () => {
    if (projectId == null || busy) return;
    setBusy(true);
    try {
      const created = await api.createScene(projectId, { title: `Scene ${sorted.length + 1}` });
      focusAfter.current = created.id; refetch();
    } catch { /* states */ } finally { setBusy(false); }
  };
  const removeScene = async (id: number) => {
    if (projectId == null) return;
    flushers.current.get(id)?.cancel();
    try { await api.deleteScene(projectId, id); refetch(); } catch { /* no-op */ }
  };
  const moveScene = async (id: number, toIndex: number) => {
    if (projectId == null || busy || toIndex < 0 || toIndex >= sorted.length) return;
    setBusy(true);
    try { await api.updateScene(projectId, id, { sort_order: toIndex }); refetch(); } catch { /* no-op */ } finally { setBusy(false); }
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") { e.preventDefault(); flushers.current.forEach((h) => void h.flush()); }
  };

  return (
    <PanelShell {...props}>
      <div data-screen-label="Manuscript Editor" style={panelBox} onKeyDown={onKeyDown}>
        <Corners br />
        <div style={{ height: 44, flex: "none", display: "flex", alignItems: "center", gap: 14, padding: "0 18px", borderBottom: "1px solid var(--line)", background: "var(--tint)" }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 14, letterSpacing: ".14em", color: "var(--strong)" }}>MANUSCRIPT</span>
          <span style={{ fontSize: 10, color: "var(--txt2)" }}>{total.toLocaleString()} <span style={{ color: "var(--txt3)" }}>WORDS</span> · {sorted.length} SCENES</span>
          <div style={{ display: "flex", alignItems: "center", gap: 6, height: 20, padding: "0 9px", border: `1px solid ${saveColor}`, color: saveColor, fontSize: 9, letterSpacing: ".14em" }}>
            <span style={{ width: 5, height: 5, borderRadius: "50%", background: saveColor }} />{saveLabel}
          </div>
          <div style={{ flex: 1 }} />
          {isScript && <button type="button" onClick={() => setFormat((f) => !f)} disabled={focus} aria-pressed={format} title="Live screenplay-format preview of the scene you're editing" style={{ ...linkBtn, color: format ? "var(--accent)" : "var(--txt2)", opacity: focus ? 0.4 : 1 }}>❏ FORMAT</button>}
          <button type="button" onClick={addScene} disabled={busy || projectId == null} style={{ ...linkBtn, color: "var(--txt2)", opacity: busy || projectId == null ? 0.5 : 1 }}>＋ SCENE</button>
          <button type="button" onClick={() => setFocus((f) => !f)} aria-pressed={focus} style={{ ...linkBtn, color: focus ? "var(--accent)" : "var(--txt2)" }}>⊹ FOCUS</button>
        </div>

        <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
          <div style={{ flex: 1, minWidth: 0, display: "flex", justifyContent: "center", padding: "26px 26px 60px", overflowY: "auto" }}>
            <div style={{ width: "100%", maxWidth: focus ? 720 : 660 }}>
              {projectId == null ? message("Open a project to start writing.")
                : loading ? message("Loading manuscript…")
                : error ? message(`Couldn't load manuscript — ${error}`)
                : sorted.length === 0 ? (
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 14, padding: "60px 0", color: "var(--txt3)" }}>
                    <div style={{ fontSize: 12, letterSpacing: ".04em" }}>No scenes yet — this manuscript is empty.</div>
                    <button type="button" onClick={addScene} disabled={busy} style={{ ...linkBtn, fontSize: 11, letterSpacing: ".16em", color: "var(--accent)", border: "1px solid var(--line-cy,#2b6f8f)", padding: "8px 16px" }}>＋ WRITE THE FIRST SCENE</button>
                  </div>
                )
                : sorted.map((s, i) => (
                  <SceneEditor
                    key={s.id} scene={s} index={i}
                    showAct={i === 0 || sorted[i - 1]!.act !== s.act}
                    formatted={isScript && format} mode={String(writingMode ?? "")} busy={busy}
                    onWords={onWords} onContent={onContent} onStatus={onStatus} onActive={onActive} registerFlush={registerFlush}
                    onDelete={() => removeScene(s.id)} onMoveUp={() => moveScene(s.id, i - 1)} onMoveDown={() => moveScene(s.id, i + 1)}
                    isFirst={i === 0} isLast={i === sorted.length - 1}
                  />
                ))}
            </div>
          </div>
          {!focus && sorted.length > 0 && (
            showFormat
              ? <FormatPreview scene={activeScene} content={previewContent} />
              : <ManuscriptRail scenes={sorted} wordsById={wordsById} statusById={statusById} total={total} onJump={jump} activeId={activeId} />
          )}
        </div>
      </div>
    </PanelShell>
  );
}
