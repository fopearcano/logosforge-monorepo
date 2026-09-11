import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import type { SceneDTO } from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useStudio, useManuscriptTarget } from "../../adapters/StudioProvider";
import { useSelection } from "../../adapters/selection";
import { useScenes } from "../../hooks";
import { classifyLines, renderLineText, fountainLineStyle } from "../../format/fountain";
import { ProseEditor } from "./ProseEditor";
import { createSceneSaveQueue, type SceneSaveQueue } from "./sceneSaveQueue";
import {
  flushPendingProjectSaves,
  markProjectSavePending,
  registerProjectFlusher,
  trackProjectWrite,
} from "../../adapters/projectSaveCoordinator";
import { ApiRequestError } from "../../adapters/httpApiClient";
import { useMountedRef } from "../../hooks/useMountedRef";
import { pruneSceneIds, pruneSceneRecord, touchWarmSceneIds } from "./manuscriptViewport";

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
 * Large manuscripts keep only visible, active, recently used, or unsaved
 * ProseMirror instances mounted; off-screen scenes retain their state/save queue
 * and render as lightweight readable text until approached or activated.
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
interface SceneDraft {
  title: string;
  content: string;
  act: string;
  chapter: string;
  plotline: string;
  summary: string;
}
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

function SceneStaticProse({
  content,
  title,
  onActivate,
}: {
  content: string;
  title: string;
  onActivate: () => void;
}) {
  return (
    <button
      type="button"
      data-prose-static
      onClick={onActivate}
      aria-label={`Activate prose editor for ${title || "untitled scene"}`}
      title="Click to edit this scene"
      style={{ display: "block", width: "100%", minHeight: "1.62em", border: "1px solid transparent", background: "transparent", color: "var(--txt)", padding: 0, textAlign: "left", fontFamily: "'Courier Prime',monospace", fontSize: 15, lineHeight: 1.62, cursor: "text" }}
    >
      {!content
        ? <span style={{ color: "var(--txt3)" }}>Write the scene…</span>
        : <span style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{content}</span>}
    </button>
  );
}

// --------------------------------------------------------------- Scene editor
function SceneEditor({
  scene, index, showAct, formatted, mode, busy, onWords, onContent, onStatus, onActive, registerFlush,
  onDelete, onMoveUp, onMoveDown, isFirst, isLast, renderProse, registerSceneNode, onRequestEdit,
}: {
  scene: SceneDTO; index: number; showAct: boolean; formatted: boolean; mode: string; busy: boolean;
  onWords: (id: number, n: number) => void;
  onContent: (id: number, c: string) => void;
  onStatus: (id: number, s: SaveStatus) => void;
  onActive: (id: number) => void;
  registerFlush: (id: number, h: FlushHandlers | null) => void;
  onDelete: () => void; onMoveUp: () => void; onMoveDown: () => void;
  isFirst: boolean; isLast: boolean;
  renderProse: boolean;
  registerSceneNode: (id: number, node: HTMLDivElement | null) => void;
  onRequestEdit: (id: number) => void;
}) {
  const { api, projectId } = useStudio();
  // A SceneEditor belongs to the project it mounted under. Keep that owner id
  // even if a host accidentally rerenders once with a new active project before
  // this old scene unmounts.
  const ownerProjectId = useRef(projectId).current;
  const { setSelection } = useSelection();
  const [title, setTitle] = useState(scene.title ?? "");
  const [content, setContent] = useState(scene.content ?? "");
  const [act, setAct] = useState(scene.act ?? "");
  const [chapter, setChapter] = useState(scene.chapter ?? "");
  const [plotline, setPlotline] = useState(scene.plotline ?? "");
  const [summary, setSummary] = useState(scene.summary ?? "");
  const [showDetails, setShowDetails] = useState(false);
  const [status, setStatus] = useState<SaveStatus>("idle");
  const [saveConflict, setSaveConflict] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [resolvingConflict, setResolvingConflict] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  const timer = useRef<number | null>(null);
  const mounted = useMountedRef();
  const sceneNodeRef = useCallback((node: HTMLDivElement | null) => registerSceneNode(scene.id, node), [registerSceneNode, scene.id]);

  const setStat = useCallback((s: SaveStatus) => { if (!mounted.current) return; setStatus(s); onStatus(scene.id, s); }, [onStatus, scene.id]);
  const statusRef = useRef(setStat);
  statusRef.current = setStat;
  const draftRef = useRef<SceneDraft>({ title, content, act, chapter, plotline, summary });
  const revisionRef = useRef(scene.revision ?? "");
  const forceOverwriteRef = useRef(false);
  const writeRef = useRef<(draft: SceneDraft) => Promise<void>>(async () => {});
  writeRef.current = async (draft) => {
    if (ownerProjectId == null) throw new Error("No owning project for this scene.");
    const force = forceOverwriteRef.current;
    forceOverwriteRef.current = false;
    try {
      const updated = await trackProjectWrite(api.updateScene(ownerProjectId, scene.id, {
        ...draft,
        ...(!force && revisionRef.current ? { expected_revision: revisionRef.current } : {}),
      }));
      revisionRef.current = updated.revision ?? "";
      if (mounted.current) { setSaveConflict(false); setSaveError(""); }
    } catch (error) {
      if (mounted.current) {
        setSaveError(error instanceof Error ? error.message : String(error));
        if (error instanceof ApiRequestError && error.code === "scene_conflict") setSaveConflict(true);
      }
      throw error;
    }
  };
  const queueRef = useRef<SceneSaveQueue<SceneDraft> | null>(null);
  if (!queueRef.current) {
    queueRef.current = createSceneSaveQueue({
      initial: draftRef.current,
      write: (draft) => writeRef.current(draft),
      onStatus: (next) => statusRef.current(next),
      onDirty: markProjectSavePending,
    });
  }
  // report word count + live content (for the FORMAT preview) upward
  useEffect(() => { onWords(scene.id, wordCount(content)); onContent(scene.id, content); }, [content, onWords, onContent, scene.id]);
  useEffect(() => { onContent(scene.id, content); }, [formatted, onContent, scene.id]);

  useEffect(() => {
    const queue = queueRef.current!;
    if (!queue.isDirty()) {
      const next = {
        title: scene.title ?? "", content: scene.content ?? "",
        act: scene.act ?? "", chapter: scene.chapter ?? "",
        plotline: scene.plotline ?? "", summary: scene.summary ?? "",
      };
      setTitle(scene.title ?? ""); setContent(scene.content ?? "");
      setAct(scene.act ?? ""); setChapter(scene.chapter ?? ""); setPlotline(scene.plotline ?? ""); setSummary(scene.summary ?? "");
      draftRef.current = next;
      revisionRef.current = scene.revision ?? "";
      setSaveConflict(false); setSaveError("");
      queue.reset(next);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scene.id, scene.title, scene.content, scene.act, scene.chapter, scene.plotline, scene.summary, scene.revision]);

  const schedule = (patch: Partial<SceneDraft>) => {
    const next = { ...draftRef.current, ...patch };
    draftRef.current = next;
    queueRef.current!.update(next);
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      timer.current = null;
      void queueRef.current!.flush();
    }, SAVE_DEBOUNCE_MS);
  };
  const flushNow = useCallback(async (): Promise<boolean> => {
    if (timer.current !== null) { clearTimeout(timer.current); timer.current = null; }
    return queueRef.current?.flush() ?? true;
  }, []);
  const cancelSave = useCallback(() => {
    if (timer.current !== null) { clearTimeout(timer.current); timer.current = null; }
    queueRef.current?.cancel();
  }, []);
  const reloadAfterConflict = useCallback(async () => {
    if (ownerProjectId == null || resolvingConflict) return;
    const localAtStart = draftRef.current;
    setResolvingConflict(true);
    try {
      const latest = (await api.listScenes(ownerProjectId)).find((item) => item.id === scene.id);
      if (!latest) throw new Error("The scene no longer exists.");
      if (draftRef.current !== localAtStart) {
        throw new Error("The local draft changed while reloading. Review it and choose again.");
      }
      if (timer.current !== null) { clearTimeout(timer.current); timer.current = null; }
      const next: SceneDraft = {
        title: latest.title ?? "", content: latest.content ?? "", act: latest.act ?? "",
        chapter: latest.chapter ?? "", plotline: latest.plotline ?? "", summary: latest.summary ?? "",
      };
      setTitle(next.title); setContent(next.content); setAct(next.act);
      setChapter(next.chapter); setPlotline(next.plotline); setSummary(next.summary);
      draftRef.current = next;
      revisionRef.current = latest.revision ?? "";
      queueRef.current?.reset(next);
      setSaveConflict(false); setSaveError(""); setStat("saved");
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : String(error));
    } finally {
      setResolvingConflict(false);
    }
  }, [api, ownerProjectId, resolvingConflict, scene.id, setStat]);
  const overwriteAfterConflict = useCallback(async () => {
    if (resolvingConflict) return;
    setResolvingConflict(true);
    forceOverwriteRef.current = true;
    try {
      await flushNow();
    } finally {
      forceOverwriteRef.current = false;
      setResolvingConflict(false);
    }
  }, [flushNow, resolvingConflict]);
  useEffect(() => {
    registerFlush(scene.id, { flush: flushNow, cancel: cancelSave });
    const unregisterProjectFlusher = registerProjectFlusher(flushNow);
    return () => {
      unregisterProjectFlusher();
      registerFlush(scene.id, null);
      void flushNow();
    };
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
  const keepLiveEditor = renderProse || saveConflict || status === "dirty" || status === "saving" || status === "error";
  return (
    <div ref={sceneNodeRef} id={`ms-scene-${scene.id}`} data-scene-id={scene.id} data-scene-prose={keepLiveEditor ? "live" : "static"} style={{ marginBottom: 30, scrollMarginTop: 18, contentVisibility: "auto", containIntrinsicSize: "auto 360px" }}>
      {showAct && scene.act && <ActDivider scene={scene} />}
      <div style={{ display: "flex", gap: 12, alignItems: "baseline", marginBottom: 10 }}>
        <span style={{ fontFamily: "'Chakra Petch'", color: "var(--txt3)", fontSize: 13, flex: "none" }}>{index + 1}</span>
        <input
          value={title}
          onChange={(e) => { setTitle(e.target.value); schedule({ title: e.target.value }); }}
          onFocus={() => { onActive(scene.id); onContent(scene.id, content); }}
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
      {saveConflict && (
        <div role="alert" style={{ display: "flex", alignItems: "center", gap: 8, margin: "-2px 0 10px 25px", padding: "7px 9px", border: "1px solid var(--crimson)", background: "rgba(255,82,96,.08)", color: "var(--txt2)", fontSize: 9.5 }}>
          <span style={{ flex: 1 }}>This scene changed elsewhere. Your local draft is preserved.{saveError ? ` ${saveError}` : ""}</span>
          <button type="button" disabled={resolvingConflict} onClick={() => void reloadAfterConflict()} style={{ ...linkBtn, color: "var(--txt2)" }}>DISCARD LOCAL · RELOAD</button>
          <button type="button" disabled={resolvingConflict} onClick={() => void overwriteAfterConflict()} style={{ ...linkBtn, color: "var(--crimson)" }}>OVERWRITE NEWER VERSION</button>
        </div>
      )}
      {!saveConflict && status === "error" && saveError && (
        <div role="alert" style={{ margin: "-2px 0 10px 25px", color: "var(--crimson)", fontSize: 9.5 }}>Save failed · {saveError}</div>
      )}
      {showDetails && (
        <div style={{ display: "flex", gap: 10, margin: "0 0 12px", flexWrap: "wrap", alignItems: "center" }}>
          {([["ACT", act, setAct, "e.g. Act I", 90], ["CHAPTER", chapter, setChapter, "e.g. 1", 90], ["PLOTLINE", plotline, setPlotline, "e.g. A-plot", 110], ["SUMMARY", summary, setSummary, "one-line scene summary", 300]] as const).map(([label, val, setter, ph, w]) => (
            <label key={label} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 8, letterSpacing: ".14em", color: "var(--txt3)" }}>
              {label}
              <input
                value={val}
                onChange={(e) => {
                  setter(e.target.value);
                  const field = label === "ACT" ? "act" : label === "CHAPTER" ? "chapter" : label === "PLOTLINE" ? "plotline" : "summary";
                  schedule({ [field]: e.target.value });
                }}
                onFocus={() => { onActive(scene.id); onContent(scene.id, content); }}
                onBlur={() => void flushNow()}
                placeholder={ph}
                aria-label={`Scene ${index + 1} ${label.toLowerCase()}`}
                style={{ width: w, background: "var(--tint)", border: "1px solid var(--line2)", outline: "none", color: "var(--txt)", fontFamily: "inherit", fontSize: 11, padding: "5px 8px" }}
              />
            </label>
          ))}
        </div>
      )}
      {keepLiveEditor
        ? <ProseEditor
          value={content}
          onChange={(v) => { setContent(v); schedule({ content: v }); }}
          onFocusActive={() => { onActive(scene.id); onContent(scene.id, content); publishText(""); }}
          onSelectionText={publishText}
          onBlur={() => void flushNow()}
          formatted={formatted}
          mode={mode}
          placeholder="Write the scene…"
        />
        : <SceneStaticProse content={content} title={title} onActivate={() => onRequestEdit(scene.id)} />}
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
  const sorted = useMemo(() => [...(scenes ?? [])].sort((a, b) => a.sort_order - b.sort_order), [scenes]);
  const isScript = SCRIPT_MODES.has(String(writingMode ?? ""));

  const [focus, setFocus] = useState(false);
  const [format, setFormat] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [wordsById, setWordsById] = useState<Record<number, number>>({});
  const [activeContent, setActiveContent] = useState<{ id: number; content: string } | null>(null);
  const [statusById, setStatusById] = useState<Record<number, SaveStatus>>({});
  const [activeId, setActiveId] = useState<number | null>(null);
  const [warmSceneIds, setWarmSceneIds] = useState<number[]>([]);
  const [nearSceneIds, setNearSceneIds] = useState<Set<number>>(() => new Set());
  const flushers = useRef(new Map<number, FlushHandlers>());
  const focusAfter = useRef<number | null>(null);
  const jumpTimer = useRef<number | null>(null);
  const manuscriptScrollRef = useRef<HTMLDivElement | null>(null);
  const sceneNodesRef = useRef(new Map<number, HTMLDivElement>());
  const sceneObserverRef = useRef<IntersectionObserver | null>(null);
  const activeIdRef = useRef(activeId);
  activeIdRef.current = activeId;
  const showFormat = isScript && format && !focus;
  const showFormatRef = useRef(showFormat);
  showFormatRef.current = showFormat;
  const intersectionSupported = typeof IntersectionObserver !== "undefined";

  useEffect(() => {
    setWordsById({}); setActiveContent(null); setStatusById({}); setActiveId(null);
    setWarmSceneIds([]); setNearSceneIds(new Set()); setActionError(null);
    activeIdRef.current = null; focusAfter.current = null;
  }, [projectId]);

  const onWords = useCallback((id: number, n: number) => setWordsById((m) => (m[id] === n ? m : { ...m, [id]: n })), []);
  const onContent = useCallback((id: number, content: string) => {
    if (activeIdRef.current !== id || !showFormatRef.current) return;
    setActiveContent((current) => current?.id === id && current.content === content ? current : { id, content });
  }, []);
  const onStatus = useCallback((id: number, s: SaveStatus) => setStatusById((m) => (m[id] === s ? m : { ...m, [id]: s })), []);
  const onActive = useCallback((id: number) => {
    activeIdRef.current = id;
    setActiveId(id);
    setActiveContent((current) => current?.id === id ? current : null);
    setWarmSceneIds((current) => touchWarmSceneIds(current, id));
  }, []);
  const registerFlush = useCallback((id: number, h: FlushHandlers | null) => {
    if (h) flushers.current.set(id, h); else flushers.current.delete(id);
  }, []);

  const registerSceneNode = useCallback((id: number, node: HTMLDivElement | null) => {
    const previous = sceneNodesRef.current.get(id);
    if (previous === node) return;
    if (previous) sceneObserverRef.current?.unobserve(previous);
    if (node) {
      sceneNodesRef.current.set(id, node);
      sceneObserverRef.current?.observe(node);
    } else {
      sceneNodesRef.current.delete(id);
    }
  }, []);

  useEffect(() => {
    const root = manuscriptScrollRef.current;
    if (!root || typeof IntersectionObserver === "undefined") return undefined;
    const observer = new IntersectionObserver((entries) => {
      if (sceneObserverRef.current !== observer) return;
      setNearSceneIds((current) => {
        let next: Set<number> | null = null;
        for (const entry of entries) {
          const id = Number((entry.target as HTMLElement).dataset.sceneId);
          if (!Number.isInteger(id)) continue;
          const has = current.has(id);
          if (entry.isIntersecting === has) continue;
          if (!next) next = new Set(current);
          if (entry.isIntersecting) next.add(id); else next.delete(id);
        }
        return next ?? current;
      });
    }, { root, rootMargin: "900px 0px", threshold: 0 });
    sceneObserverRef.current = observer;
    for (const node of sceneNodesRef.current.values()) observer.observe(node);
    return () => {
      observer.disconnect();
      if (sceneObserverRef.current === observer) sceneObserverRef.current = null;
    };
  }, [projectId]);

  const sceneIdsKey = sorted.map((scene) => scene.id).join(",");
  useEffect(() => {
    const valid = new Set(sorted.map((scene) => scene.id));
    setWordsById((current) => pruneSceneRecord(current, valid));
    setStatusById((current) => pruneSceneRecord(current, valid));
    setActiveContent((current) => current && valid.has(current.id) ? current : null);
    setWarmSceneIds((current) => pruneSceneIds(current, valid));
    setNearSceneIds((current) => {
      const next = new Set([...current].filter((id) => valid.has(id)));
      return next.size === current.size ? current : next;
    });
    setActiveId((current) => {
      const next = current != null && valid.has(current) ? current : sorted[0]?.id ?? null;
      return next;
    });
  }, [sceneIdsKey]);

  useEffect(() => () => {
    if (jumpTimer.current !== null) window.clearTimeout(jumpTimer.current);
  }, []);

  const total = useMemo(() => sorted.reduce((n, s) => n + (wordsById[s.id] ?? wordCount(s.content)), 0), [sorted, wordsById]);
  const statuses = useMemo(() => sorted.map((s) => statusById[s.id]).filter(Boolean) as SaveStatus[], [sorted, statusById]);
  const saveLabel = statuses.includes("saving") ? "SAVING…" : statuses.some((s) => s === "dirty" || s === "error") ? "UNSAVED" : "ALL SAVED";
  const saveColor = saveLabel === "SAVING…" ? "var(--accent)" : saveLabel === "UNSAVED" ? "var(--amber)" : "var(--green)";

  const effectiveActiveId = activeId ?? sorted[0]?.id ?? null;
  const activeScene = sorted.find((s) => s.id === effectiveActiveId) ?? sorted[0];
  const previewContent = activeScene ? (activeContent?.id === activeScene.id ? activeContent.content : activeScene.content) : "";

  const jump = useCallback((id: number) => {
    onActive(id);
    const el = document.getElementById(`ms-scene-${id}`);
    el?.scrollIntoView({ block: "center", behavior: "smooth" });
    if (jumpTimer.current !== null) window.clearTimeout(jumpTimer.current);
    jumpTimer.current = window.setTimeout(() => {
      jumpTimer.current = null;
      const current = document.getElementById(`ms-scene-${id}`);
      current?.scrollIntoView({ block: "center", behavior: "smooth" });
      (current?.querySelector("[data-prose]") as HTMLElement | null)?.focus({ preventScroll: true });
    }, 40);
  }, [onActive]);

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
    setActionError(null);
    try {
      const created = await trackProjectWrite(api.createScene(projectId, { title: `Scene ${sorted.length + 1}` }));
      focusAfter.current = created.id; refetch();
    } catch (error) {
      setActionError(`Couldn't create the scene — ${error instanceof Error ? error.message : String(error)}`);
    } finally { setBusy(false); }
  };
  const removeScene = async (id: number) => {
    if (projectId == null || busy) return;
    setBusy(true);
    setActionError(null);
    try {
      const saved = await (flushers.current.get(id)?.flush() ?? Promise.resolve(true));
      if (!saved) throw new Error("Resolve this scene's save error before deleting it.");
      await trackProjectWrite(api.deleteScene(projectId, id));
      // Dispose local edits only after the destructive request succeeds. If the
      // API rejects, the editor remains live and its draft can still autosave.
      flushers.current.get(id)?.cancel();
      refetch();
    } catch (error) {
      setActionError(`Couldn't delete the scene — ${error instanceof Error ? error.message : String(error)}`);
    } finally { setBusy(false); }
  };
  const moveScene = async (id: number, toIndex: number) => {
    if (projectId == null || busy || toIndex < 0 || toIndex >= sorted.length) return;
    setBusy(true);
    setActionError(null);
    try {
      await flushPendingProjectSaves();
      const target = (await api.listScenes(projectId)).find((scene) => scene.id === id);
      if (!target) throw new Error("The scene no longer exists.");
      await trackProjectWrite(api.updateScene(projectId, id, {
        sort_order: toIndex,
        ...(target.revision ? { expected_revision: target.revision } : {}),
      }));
      refetch();
    } catch (error) {
      setActionError(`Couldn't reorder the scene — ${error instanceof Error ? error.message : String(error)}`);
    } finally { setBusy(false); }
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
      e.preventDefault();
      setActionError(null);
      void flushPendingProjectSaves().catch((error) => setActionError(
        `Save failed — ${error instanceof Error ? error.message : String(error)}`,
      ));
    }
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
        {actionError && <button type="button" role="alert" title="Dismiss" onClick={() => setActionError(null)} style={{ flex: "none", width: "100%", textAlign: "left", border: "none", borderBottom: "1px solid var(--crimson)", background: "rgba(255,82,96,.08)", color: "var(--crimson)", padding: "7px 18px", font: "inherit", fontSize: 9.5, cursor: "pointer" }}>{actionError}</button>}

        <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
          <div ref={manuscriptScrollRef} data-manuscript-scroll style={{ flex: 1, minWidth: 0, display: "flex", justifyContent: "center", padding: "26px 26px 60px", overflowY: "auto" }}>
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
                    renderProse={!intersectionSupported || s.id === effectiveActiveId || nearSceneIds.has(s.id) || warmSceneIds.includes(s.id)}
                    registerSceneNode={registerSceneNode} onRequestEdit={jump}
                  />
                ))}
            </div>
          </div>
          {!focus && sorted.length > 0 && (
            showFormat
              ? <FormatPreview scene={activeScene} content={previewContent} />
              : <ManuscriptRail scenes={sorted} wordsById={wordsById} statusById={statusById} total={total} onJump={jump} activeId={effectiveActiveId} />
          )}
        </div>
      </div>
    </PanelShell>
  );
}
