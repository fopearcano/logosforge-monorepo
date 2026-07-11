import { useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import type { QuantumSettingsDTO, QuantumSettingsUpdateDTO } from "@logosforge/ui-contracts";
import { PanelShell, type PanelProps } from "../shell/PanelShell";
import { useQuantum } from "../../hooks";
import { useStudio, useNavigate } from "../../adapters/StudioProvider";

const STRUCTURE_MODES = ["auto", "classical", "quantum", "hybrid"];

const smallBtn: CSSProperties = { fontSize: 8.5, letterSpacing: ".06em", border: "1px solid var(--line2)", background: "transparent", padding: "3px 9px", cursor: "pointer", font: "inherit" };

const panelBox: CSSProperties = {
  position: "relative",
  width: "100%",
  height: "100%",
  background: "radial-gradient(60% 55% at 38% 46%,var(--panel2),var(--base) 76%)",
  border: "1px solid var(--line-v)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)",
  overflow: "hidden",
  display: "flex",
  flexDirection: "column",
};

const ACCENT = { ["--accent"]: "#b07cff", ["--line-v"]: "rgba(176,124,255,.3)" } as CSSProperties;

// The wavefunction summary shape inside QuantumResult.payload (loose dict on the wire).
interface QBranch {
  id: string;
  title?: string;
  description?: string;
  stakes?: string;
  consequence?: string;
  branch_type?: string;
  score?: number;
  probability?: number;
  is_pareto_optimal?: boolean;
}
interface QPayload {
  wavefunction_id?: string;
  anchor?: string;
  recommendation?: { branch_id?: string; title?: string; probability?: number; reason?: string } | null;
  branches?: QBranch[];
}

const BRANCH_COLORS = ["var(--violet)", "var(--cyan)", "var(--crimson)", "var(--green)", "var(--amber-b)", "var(--pink)"];
const FIELD_W = 1000;
const FIELD_H = 760;
const CX = FIELD_W / 2;
const CY = FIELD_H / 2;
const R = 250;

function Bar({ label, pct, color, mt = 0 }: { label: string; pct: number; color: string; mt?: number }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 7, color: "var(--txt3)", marginTop: mt }}>
      <span style={{ width: 40 }}>{label}</span>
      <div style={{ flex: 1, height: 3, background: "var(--tint2)" }}>
        <div style={{ width: `${Math.round(Math.max(0, Math.min(1, pct)) * 100)}%`, height: "100%", background: color }} />
      </div>
    </div>
  );
}

const message = (text: ReactNode): ReactNode => (
  <div style={{ position: "absolute", left: "50%", top: "58%", transform: "translate(-50%,-50%)", width: 320, textAlign: "center", fontSize: 11, color: "var(--txt3)", lineHeight: 1.6, letterSpacing: ".03em" }}>{text}</div>
);

export function QuantumOutliner(props: PanelProps) {
  const { generate, running, result, error } = useQuantum();
  const { api, projectId } = useStudio();
  const navigate = useNavigate();
  const [premise, setPremise] = useState("");
  const [selId, setSelId] = useState<string | null>(null);
  const canRun = !running && premise.trim().length > 0;

  // Lambda scoring config (persisted per-project; the generate path honours it)
  // + the per-run compose strategy (structure_mode).
  const [qs, setQs] = useState<QuantumSettingsDTO | null>(null);
  const [structureMode, setStructureMode] = useState("auto");
  const [showTune, setShowTune] = useState(false);
  useEffect(() => {
    if (projectId == null) { setQs(null); return; }
    let alive = true;
    api.getQuantumSettings(projectId).then((v) => { if (alive) setQs(v); }).catch(() => { if (alive) setQs(null); });
    return () => { alive = false; };
  }, [api, projectId]);
  const tune = useCallback((patch: QuantumSettingsUpdateDTO) => {
    if (projectId == null) return;
    setQs((cur) => (cur ? { ...cur, ...patch } as QuantumSettingsDTO : cur));   // optimistic
    api.patchQuantumSettings(projectId, patch).then((v) => setQs(v)).catch(() => {});
  }, [api, projectId]);
  const run = () => { setSelId(null); generate(premise, 4, structureMode); };

  const payload = (result?.payload ?? {}) as QPayload;
  const branches = payload.branches ?? [];
  const rec = payload.recommendation ?? null;
  const selected = branches.find((b) => b.id === selId) ?? branches.find((b) => b.id === rec?.branch_id) ?? branches[0];

  // The one empty/loading/error/no-branch message (null once real branches exist).
  // Rendered readably (unscaled) in both layouts so the panel is never "blank".
  const stateMsg: ReactNode | null = running
    ? "Collapsing the possibility space…"
    : error
      ? <span style={{ color: "var(--blocking)" }}>Generation failed — {error}</span>
      : !result
        ? "Enter a premise above and ⟳ GENERATE to fan out branches in superposition."
        : branches.length === 0
          ? <>No branches came back — the model returned a single classical outline. <span style={{ color: "var(--txt2)" }}>{result.title}</span> — try a more open decision-point premise, or check that an AI provider is set in <span style={{ color: "var(--txt2)" }}>AI Settings</span> (λ-mode is always requested here).</>
          : null;

  // Materialize a branch into a real scene (the "collapse" — a non-destructive
  // create routed through a confirm, then jump to the new scene in the Manuscript).
  const [confirming, setConfirming] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createdId, setCreatedId] = useState<number | null>(null);
  const [createErr, setCreateErr] = useState<string | null>(null);

  // reset the collapse UI when the selection or the wavefunction changes
  useEffect(() => { setConfirming(false); setCreatedId(null); setCreateErr(null); }, [selId, result]);

  const materialize = useCallback(async () => {
    if (!selected || projectId == null || creating) return;
    setCreating(true);
    setCreateErr(null);
    try {
      const title = (selected.title || selected.description || "Untitled branch").slice(0, 120);
      const summary = [selected.stakes, selected.consequence].filter(Boolean).join(" — ");
      const body = [
        selected.description && selected.description !== title ? selected.description : "",
        selected.stakes ? `Stakes: ${selected.stakes}` : "",
        selected.consequence ? `Consequence: ${selected.consequence}` : "",
      ].filter(Boolean).join("\n\n");
      const created = await api.createScene(projectId, { title, summary: summary || undefined, content: body });
      setConfirming(false);
      setCreatedId(created.id);
    } catch (e) {
      setCreateErr(e instanceof Error ? e.message : String(e));
    } finally {
      setCreating(false);
    }
  }, [selected, projectId, creating, api]);

  // Scale the fixed-size radial field to fit its (possibly narrow, docked)
  // container, so the absolutely-positioned branch cards never clip. The SVG
  // rings already scale via viewBox; this makes the HTML overlays scale too.
  const panelRef = useRef<HTMLDivElement | null>(null);
  const fieldRef = useRef<HTMLDivElement | null>(null);
  const [fieldScale, setFieldScale] = useState(1);
  const [panelW, setPanelW] = useState(0);
  // `compact` MUST be decided from the STABLE outer panel width. Measuring the
  // FIELD (whose own width changes when the layout flips) fed back through the
  // ResizeObserver and made the panel flicker between the list and radial layouts
  // at threshold widths. The panel box is always the full dock width, so it never
  // oscillates. Below this width the radial is unreadable → show the branch list.
  useLayoutEffect(() => {
    const el = panelRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const measure = () => { const w = el.clientWidth; if (w > 0) setPanelW(w); };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const compact = panelW > 0 && panelW < 720;
  // Radial fit (wide layout only). Scaling via CSS transform never changes the
  // observed box size, so measuring the field for SCALE is loop-safe.
  useLayoutEffect(() => {
    const el = fieldRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const measure = () => { const w = el.clientWidth, h = el.clientHeight; if (w > 0 && h > 0) setFieldScale(Math.min(w / FIELD_W, h / FIELD_H, 1)); };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [compact]);

  return (
    <PanelShell {...props} style={ACCENT}>
      <div ref={panelRef} data-screen-label="Quantum Outliner" style={panelBox}>
        <div style={{ position: "absolute", top: -1, left: -1, width: 14, height: 14, borderTop: "1px solid var(--violet)", borderLeft: "1px solid var(--violet)", zIndex: 9 }} />
        <div style={{ position: "absolute", top: 3, left: 3, width: 5, height: 5, background: "var(--violet)", zIndex: 9 }} />

        {/* toolbar — premise input + generate */}
        <div style={{ height: 44, flex: "none", display: "flex", alignItems: "center", gap: 12, padding: "0 16px", borderBottom: "1px solid var(--line-v)", background: "var(--tint)", zIndex: 6 }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 14, letterSpacing: ".12em", color: "var(--strong)", flex: "none" }}>QUANTUM OUTLINER</span>
          <span style={{ fontSize: 9, color: "var(--violet)", letterSpacing: ".1em", flex: "none" }}>λ</span>
          <input
            value={premise}
            onChange={(e) => setPremise(e.target.value)}
            placeholder="premise / branch point — e.g. “She finally says the Warden's name”"
            style={{ flex: 1, minWidth: 0, background: "var(--tint)", border: "1px solid var(--line2)", color: "var(--txt)", fontSize: 11, padding: "5px 9px", outline: "none", fontFamily: "inherit" }}
          />
          <button type="button" onClick={() => setShowTune((v) => !v)} title="Tune the Lambda scoring engine (presets, weighting, compose strategy)"
            style={{ flex: "none", fontSize: 8.5, letterSpacing: ".08em", color: showTune ? "var(--violet)" : "var(--txt2)", background: "transparent", border: `1px solid ${showTune ? "var(--line-v)" : "var(--line2)"}`, padding: "4px 9px", cursor: "pointer", font: "inherit" }}>⚙ TUNE</button>
          <span
            onClick={canRun ? run : undefined}
            style={{ flex: "none", fontSize: 9, color: "var(--on-accent)", background: canRun ? "var(--violet)" : "var(--line2)", padding: "5px 11px", fontWeight: 600, letterSpacing: ".08em", cursor: canRun ? "pointer" : "default", boxShadow: canRun ? "0 0 14px rgba(176,124,255,.4)" : undefined }}
          >
            {running ? "⟳ GENERATING…" : "⟳ GENERATE POSSIBILITIES"}
          </span>
        </div>

        {/* Lambda tuning strip — real scoring config (persisted; honoured by the generate path) */}
        {showTune && (
          <div style={{ flex: "none", display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12, padding: "8px 16px", borderBottom: "1px solid var(--line-v)", background: "var(--tint)", zIndex: 6, fontSize: 9 }}>
            <label style={{ display: "flex", alignItems: "center", gap: 5, color: "var(--txt3)", letterSpacing: ".08em" }}>
              PRESET
              <select value={qs?.preset ?? "Balanced"} onChange={(e) => tune({ preset: e.target.value })}
                style={{ background: "var(--tint)", border: "1px solid var(--line2)", color: "var(--txt)", fontSize: 9, padding: "3px 5px", fontFamily: "inherit" }}>
                {(qs?.preset_names ?? ["Balanced"]).map((p) => <option key={p} value={p}>{p}</option>)}
                {qs && !(qs.preset_names ?? []).includes(qs.preset) && <option value={qs.preset}>{qs.preset}</option>}
              </select>
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 5, color: "var(--txt3)", letterSpacing: ".08em" }}>
              STRUCTURE
              <select value={structureMode} onChange={(e) => setStructureMode(e.target.value)}
                style={{ background: "var(--tint)", border: "1px solid var(--line2)", color: "var(--txt)", fontSize: 9, padding: "3px 5px", fontFamily: "inherit" }}>
                {STRUCTURE_MODES.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 5, color: "var(--txt3)", letterSpacing: ".08em" }}>
              SELECT
              <select value={qs?.selection_mode ?? "weighted"} onChange={(e) => tune({ selection_mode: e.target.value })}
                style={{ background: "var(--tint)", border: "1px solid var(--line2)", color: "var(--txt)", fontSize: 9, padding: "3px 5px", fontFamily: "inherit" }}>
                <option value="weighted">weighted</option>
                <option value="pareto">pareto</option>
              </select>
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 5, color: "var(--txt2)", cursor: "pointer" }}>
              <input type="checkbox" checked={!!qs?.show_tradeoffs} onChange={(e) => tune({ show_tradeoffs: e.target.checked })} />
              tradeoffs
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 5, color: "var(--txt2)", cursor: "pointer" }} title="Adapt the weights from which branch you collapse">
              <input type="checkbox" checked={qs?.weight_learning !== false} onChange={(e) => tune({ weight_learning: e.target.checked })} />
              learn
            </label>
            {qs?.preset === "Custom" && <span style={{ color: "var(--violet)", letterSpacing: ".08em" }}>· custom weights</span>}
          </div>
        )}

        {/* Always a single column (field on top, detail below). The field spans the
            full panel width in BOTH layouts — never split in half — so the radial
            gets the whole width when wide and the list is full-width when docked. */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
          {/* possibility field — radial when there's room, a readable list when docked narrow */}
          <div ref={fieldRef} style={{ flex: "1 1 auto", minWidth: 0, minHeight: compact ? 160 : 220, position: "relative", display: compact ? "block" : "grid", placeItems: compact ? undefined : "center", overflow: compact ? "auto" : "hidden" }}>
            {compact ? (
              /* ── compact (docked) layout: anchor summary + a full-width branch list ── */
              <div style={{ padding: "12px 12px 16px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
                  <div style={{ width: 34, height: 30, flex: "none", background: "linear-gradient(180deg,rgba(176,124,255,.3),rgba(176,124,255,.06))", border: "1px solid var(--violet)", clipPath: "polygon(50% 0,100% 100%,0 100%)", display: "grid", placeItems: "end center", paddingBottom: 3, boxShadow: "0 0 18px rgba(176,124,255,.4)" }}>
                    <span style={{ fontFamily: "'Chakra Petch'", fontSize: 12, color: "var(--strong)" }}>ψ</span>
                  </div>
                  <div style={{ lineHeight: 1.3 }}>
                    <div style={{ fontFamily: "'Chakra Petch'", fontSize: 11, color: "var(--strong)", letterSpacing: ".06em" }}>WAVEFUNCTION</div>
                    <div style={{ fontSize: 8, color: "var(--violet)", letterSpacing: ".16em" }}>{branches.length} SUPERPOSED FUTURE{branches.length === 1 ? "" : "S"}</div>
                  </div>
                </div>
                {stateMsg ? (
                  <div style={{ fontSize: 11, color: "var(--txt3)", lineHeight: 1.6, padding: "16px 2px" }}>{stateMsg}</div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {branches.map((b, i) => {
                      const recommended = rec?.branch_id === b.id;
                      const color = recommended ? "var(--violet)" : BRANCH_COLORS[i % BRANCH_COLORS.length] ?? "var(--cyan)";
                      const isSel = selected?.id === b.id;
                      return (
                        <button key={b.id} type="button" onClick={() => setSelId(b.id)} style={{ display: "block", width: "100%", textAlign: "left", font: "inherit", padding: 0, cursor: "pointer", border: `1px solid ${isSel || recommended ? "var(--violet)" : "var(--line2)"}`, background: recommended ? "linear-gradient(180deg,rgba(176,124,255,.12),var(--tint))" : "rgba(8,8,14,.9)", boxShadow: isSel ? "0 0 20px rgba(176,124,255,.3)" : undefined }}>
                          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "6px 9px", borderBottom: "1px solid var(--line2)" }}>
                            <span style={{ fontSize: 8, letterSpacing: ".14em", color }}>{recommended ? "◉ " : ""}{(b.branch_type || b.title || "BRANCH").toUpperCase().slice(0, 26)}</span>
                            <span style={{ fontFamily: "'Chakra Petch'", fontSize: 15, color: "var(--strong)" }}>{typeof b.score === "number" ? b.score.toFixed(1) : "—"}</span>
                          </div>
                          <div style={{ padding: "8px 9px" }}>
                            <div style={{ fontSize: 11, color: "var(--strong)", lineHeight: 1.35, marginBottom: 6 }}>{b.title || b.description || "(untitled branch)"}</div>
                            {typeof b.probability === "number" && <Bar label="prob" pct={b.probability} color={color} />}
                            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 8 }}>
                              <span style={{ fontSize: 8, color }}>{typeof b.probability === "number" ? `P ${b.probability.toFixed(2)}` : ""}{b.is_pareto_optimal ? " · pareto" : ""}</span>
                              <span style={{ fontSize: 8, color: isSel ? "var(--on-accent)" : "var(--txt2)", background: isSel ? "var(--violet)" : undefined, border: isSel ? undefined : "1px solid var(--line2)", padding: "3px 9px", fontWeight: isSel ? 600 : 400 }}>{isSel ? "SELECTED" : "INSPECT"}</span>
                            </div>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            ) : (
              /* ── wide layout: the radial "possibility field" (scaled) + a readable, unscaled state overlay ── */
              <>
                <div style={{ position: "relative", width: FIELD_W, height: FIELD_H, flex: "none", transform: `scale(${fieldScale})`, transformOrigin: "center center" }}>
                  {/* static rings + rotating tick ring (decorative) */}
                  <svg viewBox={`0 0 ${FIELD_W} ${FIELD_H}`} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", zIndex: 1 }}>
                    <g transform={`translate(${CX},${CY})`}>
                      <circle r="150" fill="none" stroke="rgba(176,124,255,.16)" strokeWidth="1" />
                      <circle r="250" fill="none" stroke="rgba(176,124,255,.1)" strokeWidth="1" strokeDasharray="2 6" />
                      <circle r="340" fill="none" stroke="rgba(245,177,51,.07)" strokeWidth="1" strokeDasharray="1 7" />
                      {branches.map((b, i) => {
                        const a = (i / Math.max(1, branches.length)) * Math.PI * 2 - Math.PI / 2;
                        return <line key={b.id} x1="0" y1="0" x2={R * Math.cos(a)} y2={R * Math.sin(a)} stroke="rgba(176,124,255,.3)" strokeWidth="1.2" />;
                      })}
                    </g>
                  </svg>
                  <div style={{ position: "absolute", left: CX, top: CY, width: 620, height: 620, transform: "translate(-50%,-50%)", borderRadius: "50%", border: "1px dashed rgba(176,124,255,.12)", animation: "lf-spin 60s linear infinite", zIndex: 1 }} />

                  {/* anchor (wavefunction) */}
                  <div style={{ position: "absolute", left: CX, top: CY, transform: "translate(-50%,-50%)", zIndex: 4, textAlign: "center" }}>
                    <div style={{ position: "absolute", left: "50%", top: "50%", transform: "translate(-50%,-50%)", width: 130, height: 130, borderRadius: "50%", border: "1px solid var(--violet)", animation: "lf-halo 3.4s ease-in-out infinite" }} />
                    <div style={{ width: 96, height: 88, background: "linear-gradient(180deg,rgba(176,124,255,.3),rgba(176,124,255,.06))", border: "1px solid var(--violet)", clipPath: "polygon(50% 0,100% 100%,0 100%)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end", paddingBottom: 12, boxShadow: "0 0 32px rgba(176,124,255,.5)" }}>
                      <span style={{ fontFamily: "'Chakra Petch'", fontSize: 18, color: "var(--strong)" }}>ψ</span>
                    </div>
                    <div style={{ fontFamily: "'Chakra Petch'", fontSize: 11, color: "var(--strong)", marginTop: 6, letterSpacing: ".06em" }}>WAVEFUNCTION</div>
                    <div style={{ fontSize: 8, color: "var(--violet)", letterSpacing: ".16em" }}>{branches.length} SUPERPOSED FUTURE{branches.length === 1 ? "" : "S"}</div>
                  </div>

                  {/* branch cards (only once real branches exist) */}
                  {!stateMsg && branches.map((b, i) => {
                    const a = (i / branches.length) * Math.PI * 2 - Math.PI / 2;
                    const x = CX + R * Math.cos(a);
                    const y = CY + R * Math.sin(a);
                    const recommended = rec?.branch_id === b.id;
                    const color = recommended ? "var(--violet)" : BRANCH_COLORS[i % BRANCH_COLORS.length] ?? "var(--cyan)";
                    const isSel = selected?.id === b.id;
                    return (
                      <div
                        key={b.id}
                        onClick={() => setSelId(b.id)}
                        style={{ position: "absolute", left: x, top: y, transform: "translate(-50%,-50%)", width: 228, zIndex: 5, cursor: "pointer", border: `1px solid ${isSel || recommended ? "var(--violet)" : "var(--line2)"}`, background: recommended ? "linear-gradient(180deg,rgba(176,124,255,.12),var(--tint))" : "rgba(8,8,14,.95)", boxShadow: isSel || recommended ? "0 0 26px rgba(176,124,255,.35)" : undefined }}
                      >
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "6px 9px", borderBottom: "1px solid var(--line2)" }}>
                          <span style={{ fontSize: 7.5, letterSpacing: ".14em", color }}>{recommended ? "◉ " : ""}{(b.branch_type || b.title || "BRANCH").toUpperCase().slice(0, 22)}</span>
                          <span style={{ fontFamily: "'Chakra Petch'", fontSize: 16, color: "var(--strong)" }}>{typeof b.score === "number" ? b.score.toFixed(1) : "—"}</span>
                        </div>
                        <div style={{ padding: "8px 9px" }}>
                          <div style={{ fontSize: 10.5, color: "var(--strong)", lineHeight: 1.35, marginBottom: 6 }}>{b.title || b.description || "(untitled branch)"}</div>
                          {typeof b.probability === "number" && <Bar label="prob" pct={b.probability} color={color} />}
                          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 8 }}>
                            <span style={{ fontSize: 8, color }}>{typeof b.probability === "number" ? `P ${b.probability.toFixed(2)}` : ""}{b.is_pareto_optimal ? " · pareto" : ""}</span>
                            <span style={{ fontSize: 8, color: isSel ? "var(--on-accent)" : "var(--txt2)", background: isSel ? "var(--violet)" : undefined, border: isSel ? undefined : "1px solid var(--line2)", padding: "3px 9px", fontWeight: isSel ? 600 : 400 }}>{isSel ? "SELECTED" : "INSPECT"}</span>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
                {stateMsg && message(stateMsg)}
              </>
            )}
          </div>

          {/* recommendation / selected-branch panel — always stacks BELOW the field and
              only appears once branches exist, so the field (or empty state) keeps the
              full width instead of losing space to an empty recommendation column. */}
          {!!selected && (
          <div style={{ flex: "0 0 auto", maxHeight: "48%", minWidth: 0, borderTop: "1px solid var(--line-v)", background: "var(--panel)", display: "flex", flexDirection: "column", overflowY: "auto", padding: 14 }}>
            <div style={{ fontSize: 8.5, letterSpacing: ".22em", color: "var(--violet)", marginBottom: 4 }}>{selected ? "BRANCH DETAIL" : "RECOMMENDATION"}</div>
            {rec && (
              <div style={{ fontSize: 9, color: "var(--txt3)", marginBottom: 13 }}>
                recommends <span style={{ color: "var(--violet)" }}>◉ {rec.title || rec.branch_id}</span>
                {typeof rec.probability === "number" ? ` · P ${rec.probability.toFixed(2)}` : ""}
              </div>
            )}
            {!result ? (
              <div style={{ fontSize: 10, color: "var(--txt3)", lineHeight: 1.6 }}>Generate possibilities, then click a branch to inspect its stakes, consequence, and score.</div>
            ) : !selected ? (
              <div style={{ fontSize: 10, color: "var(--txt3)" }}>{rec?.reason || "No branch selected."}</div>
            ) : (
              <>
                <div style={{ border: "1px solid var(--line2)", background: "var(--tint)", padding: 11, marginBottom: 11 }}>
                  <div style={{ fontSize: 11, color: "var(--strong)", lineHeight: 1.4, marginBottom: 7 }}>{selected.title || selected.description}</div>
                  {selected.description && selected.title && <div style={{ fontSize: 10, color: "var(--txt2)", lineHeight: 1.5, marginBottom: 7 }}>{selected.description}</div>}
                  <div style={{ display: "flex", gap: 14, fontSize: 8.5, color: "var(--txt3)" }}>
                    {typeof selected.score === "number" && <span>SCORE <span style={{ color: "var(--violet)" }}>{selected.score.toFixed(1)}</span></span>}
                    {typeof selected.probability === "number" && <span>PROB <span style={{ color: "var(--violet)" }}>{selected.probability.toFixed(2)}</span></span>}
                    {selected.is_pareto_optimal && <span style={{ color: "var(--green)" }}>PARETO-OPTIMAL</span>}
                  </div>
                </div>
                {selected.stakes && (
                  <div style={{ border: "1px solid var(--line2)", background: "var(--tint)", padding: 11, marginBottom: 11 }}>
                    <div style={{ fontSize: 8, letterSpacing: ".16em", color: "var(--txt3)", marginBottom: 6 }}>STAKES</div>
                    <div style={{ fontSize: 10, color: "var(--txt2)", lineHeight: 1.5 }}>{selected.stakes}</div>
                  </div>
                )}
                {selected.consequence && (
                  <div style={{ border: "1px solid var(--line2)", background: "var(--tint)", padding: 11 }}>
                    <div style={{ fontSize: 8, letterSpacing: ".16em", color: "var(--txt3)", marginBottom: 6 }}>CONSEQUENCE</div>
                    <div style={{ fontSize: 10, color: "var(--txt2)", lineHeight: 1.5 }}>{selected.consequence}</div>
                  </div>
                )}
              </>
            )}
            <div style={{ marginTop: "auto", paddingTop: 12 }}>
              {selected && projectId != null ? (
                createdId != null ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 9, color: "var(--green)" }}>✓ Collapsed into a new scene.</span>
                    <button type="button" onClick={() => navigate("Manuscript", { sceneId: createdId })} style={{ ...smallBtn, color: "var(--violet)", borderColor: "var(--line-v)" }}>OPEN IN MANUSCRIPT ›</button>
                    <button type="button" onClick={() => { setCreatedId(null); setConfirming(false); }} style={{ ...smallBtn, color: "var(--txt3)" }}>DONE</button>
                  </div>
                ) : confirming ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 8.5, color: "var(--txt3)" }}>Create a scene from “{(selected.title || selected.description || "branch").slice(0, 26)}”?</span>
                    <button type="button" onClick={() => void materialize()} disabled={creating} style={{ ...smallBtn, color: "var(--on-accent)", background: "var(--violet)", border: "none", fontWeight: 700, opacity: creating ? 0.6 : 1 }}>{creating ? "CREATING…" : "✓ CONFIRM"}</button>
                    <button type="button" onClick={() => setConfirming(false)} disabled={creating} style={{ ...smallBtn, color: "var(--txt2)" }}>✕</button>
                  </div>
                ) : (
                  <>
                    <button type="button" onClick={() => { setConfirming(true); setCreateErr(null); }} style={{ ...smallBtn, width: "100%", color: "var(--violet)", borderColor: "var(--line-v)", padding: "7px 0", letterSpacing: ".1em", boxShadow: "0 0 14px rgba(176,124,255,.15)" }}>＋ MATERIALIZE AS SCENE</button>
                    <div style={{ fontSize: 8, color: "var(--amber)", letterSpacing: ".04em", marginTop: 6 }}>↳ collapsing a branch creates a new scene · non-destructive</div>
                  </>
                )
              ) : (
                <div style={{ fontSize: 8, color: "var(--amber)", letterSpacing: ".04em" }}>↳ collapsing a branch routes through Controlled Apply · STAGE checkpoint</div>
              )}
              {createErr && <div style={{ fontSize: 9, color: "var(--crimson)", marginTop: 6 }}>⚠ {createErr}</div>}
            </div>
          </div>
          )}
        </div>
      </div>
    </PanelShell>
  );
}
