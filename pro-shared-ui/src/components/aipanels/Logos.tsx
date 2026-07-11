import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import type { LogosActionDTO, LogosResultDTO, LogosSuggestionDTO } from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useStudio } from "../../adapters/StudioProvider";
import { useSelection } from "../../adapters/selection";
import { useApplyToScene, ApplyDiffModal } from "./applyToScene";

/**
 * Logos — the inline/contextual action panel on the core `logosforge.logos` engine.
 * Loads the live action catalog for a chosen section, runs an action against the
 * writer's selection (read from the cross-panel selection bus, or a pasted passage)
 * with the active scene's context, and surfaces the proactive stream (rule-based
 * detectors). One engine, shared with the Whiteboard's Logos.
 */

const SECTIONS = ["Inline", "Manuscript", "Outline", "PSYKE", "Plot", "Timeline", "Graph"];
const SEV_COLOR: Record<string, string> = { important: "var(--crimson)", warning: "var(--amber)", info: "var(--cyan)" };

const panelBox: CSSProperties = {
  position: "relative", width: "100%", height: "100%",
  background: "linear-gradient(180deg,var(--panel),var(--base))",
  border: "1px solid var(--line)", boxShadow: "0 16px 60px rgba(0,0,0,.6)",
  overflow: "hidden", display: "flex", flexDirection: "column",
};
const actionBtn: CSSProperties = {
  display: "flex", alignItems: "center", gap: 7, width: "100%", textAlign: "left",
  border: "1px solid var(--line2)", background: "transparent", padding: "6px 9px",
  fontSize: 9.5, color: "var(--txt)", font: "inherit", letterSpacing: ".02em",
};
const grid2: CSSProperties = { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 };
const groupLabel: CSSProperties = { fontSize: 7.5, letterSpacing: ".2em", color: "var(--txt3)", margin: "0 0 7px" };

function glyph(a: LogosActionDTO) {
  if (a.deterministic) return { c: "var(--green)", g: "◆" };
  if (a.generative) return { c: "var(--violet)", g: "✦" };
  return { c: "var(--cyan)", g: "◇" };
}

function CatalogBtn({ a, on, disabled, busy }: { a: LogosActionDTO; on: () => void; disabled: boolean; busy: boolean }) {
  const gl = glyph(a);
  return (
    <button type="button" onClick={on} disabled={disabled} title={a.description || a.label}
      style={{ ...actionBtn, opacity: disabled ? 0.4 : 1, cursor: disabled ? "default" : "pointer" }}>
      <span style={{ color: gl.c, flex: "none" }}>{busy ? "⋯" : gl.g}</span>
      <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.label}</span>
    </button>
  );
}

export function Logos(props: PanelProps) {
  const { api, projectId, writingMode } = useStudio();
  const { selection } = useSelection();
  const { target, apply } = useApplyToScene();
  const mode = typeof writingMode === "string" ? writingMode : (writingMode ?? "");
  const [section, setSection] = useState("Inline");
  const [actions, setActions] = useState<LogosActionDTO[]>([]);
  const [text, setText] = useState("");
  const [running, setRunning] = useState<string | null>(null);
  const [result, setResult] = useState<LogosResultDTO | null>(null);
  const [err, setErr] = useState("");
  const [copied, setCopied] = useState(false);
  const [suggestions, setSuggestions] = useState<LogosSuggestionDTO[]>([]);
  const [ranPassage, setRanPassage] = useState("");
  const [applyOpen, setApplyOpen] = useState(false);

  // A generative result is a replacement for the PASSAGE that was transformed,
  // not the whole scene. Apply it surgically: splice the replacement in place of
  // that passage inside the active scene's content. If the passage isn't found in
  // the scene (e.g. a hand-pasted excerpt), applying precisely isn't possible.
  const applyProposed = useMemo<string | null>(() => {
    if (!target || !result?.generative || !result.message) return null;
    const passage = ranPassage;
    if (!passage) return null;
    const idx = target.content.indexOf(passage);
    if (idx < 0) return null;
    return target.content.slice(0, idx) + result.message + target.content.slice(idx + passage.length);
  }, [target, result, ranPassage]);

  useEffect(() => {
    if (projectId == null) { setActions([]); return; }
    let cancelled = false;
    api.listLogosActions(projectId, section, String(mode || ""))
      .then((a) => { if (!cancelled) setActions(a); }).catch(() => { if (!cancelled) setActions([]); });
    return () => { cancelled = true; };
  }, [api, projectId, mode, section]);

  const loadProactive = useCallback(() => {
    if (projectId == null) { setSuggestions([]); return; }
    api.listLogosProactive(projectId).then(setSuggestions).catch(() => setSuggestions([]));
  }, [api, projectId]);
  useEffect(() => { loadProactive(); }, [loadProactive]);

  // Auto re-scan the proactive stream when the project changes (debounced — the scan
  // is project-wide, so a burst of edits collapses into one re-scan).
  useEffect(() => {
    if (projectId == null || typeof api.subscribe !== "function") return;
    let t: ReturnType<typeof setTimeout> | undefined;
    const unsub = api.subscribe(projectId, (e) => {
      if (["scenes_changed", "scene_changed", "psyke_changed", "project_data_changed", "outline_changed", "plot_changed", "timeline_changed"].includes(e.event)) {
        if (t) clearTimeout(t);
        t = setTimeout(loadProactive, 1500);
      }
    });
    return () => { if (t) clearTimeout(t); unsub?.(); };
  }, [api, projectId, loadProactive]);

  const sel = text.trim();
  const busSel = (selection.text || "").trim();
  const canPull = busSel.length > 0 && selection.text !== text;

  // Map the cross-panel selection's section+nodeId onto the right run-context field,
  // so an Outline/PSYKE/Plot/Timeline/Graph selection lets those actions act on the node.
  const nodeContext = () => {
    const id = selection.nodeId;
    const asNum = typeof id === "number" ? id : id != null && id !== "" ? Number(id) : null;
    switch (selection.section) {
      case "Outline": return { current_outline_node_id: Number.isFinite(asNum as number) ? asNum : null };
      case "PSYKE": return { current_psyke_entry_id: Number.isFinite(asNum as number) ? asNum : null };
      case "Timeline": return { current_timeline_event_id: Number.isFinite(asNum as number) ? asNum : null };
      case "Plot": return { current_plot_block_id: id != null ? String(id) : "" };
      case "Graph": return { current_graph_node_id: id != null ? String(id) : "" };
      default: return {};
    }
  };

  const run = async (actionName: string, sectionOverride?: string) => {
    if (projectId == null || running) return;
    setRunning(actionName); setErr(""); setResult(null); setCopied(false); setApplyOpen(false); setRanPassage(text);
    try {
      const r = await api.runLogos(projectId, {
        // a proactive suggested-action can belong to any section, so it runs with an
        // empty section (no applies-to gate); catalog buttons pass the panel section.
        action: actionName, section: sectionOverride ?? section, selected_text: text,
        writing_mode: String(mode || ""), current_scene_id: selection.sceneId ?? null,
        ...nodeContext(),
      });
      setResult(r);
      if (!r.ok && r.error) setErr(r.error);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(null);
    }
  };

  const copyReplacement = async () => {
    if (!result?.message) return;
    try { await navigator.clipboard.writeText(result.message); setCopied(true); setTimeout(() => setCopied(false), 1600); } catch { /* blocked */ }
  };

  const generative = actions.filter((a) => a.generative);
  const diagnostic = actions.filter((a) => !a.generative);
  const disabledFor = (a: LogosActionDTO) => running != null || projectId == null || (a.needs_selection && !sel);

  return (
    <PanelShell {...props} style={{ ["--accent"]: "#4cc2ff" } as CSSProperties}>
      <div data-screen-label="Logos" style={panelBox}>
        <Corners />
        <div style={{ height: 42, flex: "none", display: "flex", alignItems: "center", gap: 11, padding: "0 16px", borderBottom: "1px solid var(--line)" }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".1em", color: "var(--strong)" }}>LOGOS</span>
          <span style={{ fontSize: 9, color: "var(--txt2)" }}>{actions.length} {section} actions{mode ? ` · ${mode}` : ""}</span>
          <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 8, color: "var(--green)", border: "1px solid rgba(98,217,154,.3)", padding: "2px 7px", letterSpacing: ".1em" }}>
            <span style={{ width: 5, height: 5, background: "var(--green)" }} />CORE ENGINE
          </span>
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 8, color: "var(--txt3)" }}>◆ rule · ✦ transform · ◇ analyze</span>
        </div>

        {projectId == null ? (
          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--txt3)", fontSize: 12 }}>Open a project to use Logos.</div>
        ) : (
          <div style={{ flex: 1, display: "flex", flexWrap: "wrap", minHeight: 0 }}>
            {/* section + passage + catalog */}
            <div style={{ flex: "1 1 300px", minWidth: 0, borderRight: "1px solid var(--line)", overflowY: "auto", padding: "13px 15px", display: "flex", flexDirection: "column", gap: 12 }}>
              {/* section switcher */}
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                {SECTIONS.map((s) => (
                  <button key={s} type="button" onClick={() => { setSection(s); setResult(null); setErr(""); setCopied(false); }} aria-pressed={section === s}
                    style={{ ...actionBtn, width: "auto", padding: "3px 8px", fontSize: 8.5, color: section === s ? "var(--on-accent)" : "var(--txt2)", background: section === s ? "var(--accent)" : "transparent", fontWeight: section === s ? 600 : 400, cursor: "pointer" }}>{s}</button>
                ))}
              </div>

              <div>
                <div style={{ ...groupLabel, display: "flex", justifyContent: "space-between" }}>
                  <span>PASSAGE {sel ? `· ${sel.split(/\s+/).length} words` : ""}</span>
                  {canPull && <button type="button" onClick={() => setText(selection.text)} style={{ ...actionBtn, width: "auto", padding: "1px 7px", fontSize: 8, color: "var(--accent)", cursor: "pointer" }}>↩ USE SELECTION ({busSel.split(/\s+/).length}w)</button>}
                </div>
                <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste/write the passage, or select text in the Manuscript and pull it in…" spellCheck
                  style={{ width: "100%", minHeight: 84, resize: "vertical", background: "var(--tint)", border: "1px solid var(--line2)", outline: "none", color: "var(--txt)", fontFamily: "'Courier Prime',monospace", fontSize: 11, lineHeight: 1.5, padding: "8px 9px", caretColor: "var(--accent)" }} />
              </div>

              {generative.length > 0 && (
                <div><div style={groupLabel}>TRANSFORM (apply-ready)</div>
                  <div style={grid2}>{generative.map((a) => <CatalogBtn key={a.name} a={a} on={() => run(a.name)} disabled={disabledFor(a)} busy={running === a.name} />)}</div></div>
              )}
              {diagnostic.length > 0 && (
                <div><div style={groupLabel}>ANALYZE</div>
                  <div style={grid2}>{diagnostic.map((a) => <CatalogBtn key={a.name} a={a} on={() => run(a.name)} disabled={disabledFor(a)} busy={running === a.name} />)}</div></div>
              )}
              {actions.length === 0 && <div style={{ fontSize: 9.5, color: "var(--txt3)", fontStyle: "italic" }}>No actions in {section} for this mode.</div>}
            </div>

            {/* result + proactive — wraps below the actions column when narrow */}
            <div style={{ flex: "1 1 300px", minWidth: 0, display: "flex", flexDirection: "column", background: "var(--panel2)" }}>
              <div style={{ flex: "none", padding: "12px 14px", borderBottom: "1px solid var(--line2)", display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 7.5, letterSpacing: ".2em", color: "var(--txt3)" }}>RESULT</span>
                {result && <span style={{ fontSize: 8.5, color: "var(--txt2)" }}>· {result.title || result.action}</span>}
                {result && <span style={{ fontSize: 7.5, letterSpacing: ".1em", color: result.generative ? "var(--violet)" : "var(--cyan)", border: `1px solid ${result.generative ? "rgba(176,124,255,.3)" : "var(--line-cy,#2b6f8f)"}`, padding: "1px 6px" }}>{result.generative ? "TRANSFORM" : "REPORT"}</span>}
              </div>
              <div style={{ flex: "1 1 50%", overflowY: "auto", padding: "12px 14px", minHeight: 0 }}>
                {running ? <div style={{ fontSize: 10, color: "var(--txt3)" }}>Running {running} through the core Logos engine…</div>
                  : err ? <div style={{ fontSize: 10, color: "var(--crimson)", lineHeight: 1.5 }}>⚠ {err}</div>
                  : !result ? <div style={{ fontSize: 9.5, color: "var(--txt3)", lineHeight: 1.5 }}>Pick a section + action. Transforms return apply-ready text; analyzers report. Nothing is auto-applied.</div>
                  : (
                    <>
                      {result.generative ? (
                        <div style={{ border: "1px solid var(--line-cy,#2b6f8f)", background: "rgba(76,194,255,.04)", padding: "9px 10px", marginBottom: 10 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                            <span style={{ fontSize: 7.5, letterSpacing: ".12em", color: "var(--cyan)" }}>SUGGESTED REPLACEMENT</span>
                            <div style={{ flex: 1 }} />
                            <button type="button" onClick={() => setApplyOpen(true)} disabled={applyProposed == null}
                              title={applyProposed != null ? `Apply to ${target?.title} (diff + confirm)` : target == null ? "Open a scene in the Manuscript to apply" : "Pull the passage from the open scene to apply it precisely"}
                              style={{ ...actionBtn, width: "auto", fontSize: 8, padding: "2px 9px", color: applyProposed != null ? "var(--green)" : "var(--txt3)", cursor: applyProposed != null ? "pointer" : "default", opacity: applyProposed != null ? 1 : 0.5, marginRight: 6 }}>✎ APPLY</button>
                            <button type="button" onClick={copyReplacement} style={{ ...actionBtn, width: "auto", fontSize: 8, padding: "2px 9px", color: copied ? "var(--green)" : "var(--accent)", cursor: "pointer" }}>{copied ? "✓ COPIED" : "⧉ COPY"}</button>
                          </div>
                          <div style={{ fontSize: 11, color: "var(--txt)", lineHeight: 1.55, whiteSpace: "pre-wrap", fontFamily: "'Courier Prime',monospace" }}>{result.message}</div>
                        </div>
                      ) : <div style={{ fontSize: 10.5, color: "var(--txt)", lineHeight: 1.55, whiteSpace: "pre-wrap" }}>{result.message}</div>}
                      {result.suggestions.length > 0 && (
                        <div style={{ marginTop: 10 }}><div style={groupLabel}>SUGGESTIONS</div>
                          {result.suggestions.map((s, i) => <div key={i} style={{ fontSize: 9.5, color: "var(--txt2)", borderLeft: "2px solid var(--line-cy,#2b6f8f)", padding: "3px 9px", marginBottom: 4, background: "var(--tint)" }}>{s}</div>)}</div>
                      )}
                    </>
                  )}
              </div>

              {/* proactive stream */}
              <div style={{ flex: "1 1 50%", borderTop: "1px solid var(--line2)", overflowY: "auto", padding: "10px 14px", minHeight: 0 }}>
                <div style={{ display: "flex", alignItems: "center", marginBottom: 8 }}>
                  <span style={{ fontSize: 7.5, letterSpacing: ".2em", color: "var(--txt3)" }}>PROACTIVE STREAM{suggestions.length ? ` · ${suggestions.length}` : ""}</span>
                  <div style={{ flex: 1 }} />
                  <button type="button" onClick={loadProactive} title="Re-scan the project" aria-label="Re-scan" style={{ background: "transparent", border: "none", color: "var(--txt3)", cursor: "pointer", fontSize: 11, padding: 0 }}>⟳</button>
                </div>
                {suggestions.length === 0 ? <div style={{ fontSize: 9, color: "var(--txt3)", fontStyle: "italic" }}>No proactive signals right now.</div>
                  : suggestions.map((s) => (
                    <div key={s.id} style={{ border: "1px solid var(--line2)", borderLeft: `2px solid ${SEV_COLOR[s.severity] || "var(--cyan)"}`, background: "var(--tint)", padding: "7px 9px", marginBottom: 7 }}>
                      <div style={{ fontSize: 9, color: "var(--txt2)", lineHeight: 1.4 }}><span style={{ color: SEV_COLOR[s.severity] || "var(--cyan)" }}>{s.title}</span> — {s.message}</div>
                      {s.evidence && <div style={{ fontSize: 8, color: "var(--txt3)", marginTop: 3 }}>{s.evidence}</div>}
                      {s.suggested_actions.length > 0 && (
                        <div style={{ display: "flex", gap: 5, marginTop: 6, flexWrap: "wrap" }}>
                          {s.suggested_actions.map((act) => {
                            const meta = actions.find((a) => a.name === act);
                            const gated = running != null || (!!meta?.needs_selection && !sel);
                            return (
                              <button key={act} type="button" onClick={() => run(act, "")} disabled={gated}
                                title={meta?.needs_selection && !sel ? "select a passage first" : undefined}
                                style={{ fontSize: 8, color: "var(--accent)", border: "1px solid var(--line-cy,#2b6f8f)", background: "transparent", padding: "2px 8px", cursor: gated ? "default" : "pointer", letterSpacing: ".06em", opacity: gated ? 0.45 : 1 }}>▸ {act}</button>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  ))}
              </div>
            </div>
          </div>
        )}

        {applyOpen && target && applyProposed != null && (
          <ApplyDiffModal
            title={target.title.toUpperCase()}
            badge="REWRITE"
            original={target.content}
            proposed={applyProposed}
            onConfirm={() => apply(applyProposed)}
            onClose={() => setApplyOpen(false)}
          />
        )}
      </div>
    </PanelShell>
  );
}
