import { useState, type CSSProperties, type ReactNode } from "react";
import { PanelShell, type PanelProps } from "../shell/PanelShell";
import { useQuantum } from "../../hooks";

const panelBox: CSSProperties = {
  position: "relative",
  width: "100%",
  height: "100%",
  background: "radial-gradient(60% 55% at 38% 46%,#0c0a16,#040408 76%)",
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
      <div style={{ flex: 1, height: 3, background: "rgba(255,255,255,.07)" }}>
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
  const [premise, setPremise] = useState("");
  const [selId, setSelId] = useState<string | null>(null);
  const canRun = !running && premise.trim().length > 0;

  const payload = (result?.payload ?? {}) as QPayload;
  const branches = payload.branches ?? [];
  const rec = payload.recommendation ?? null;
  const selected = branches.find((b) => b.id === selId) ?? branches.find((b) => b.id === rec?.branch_id) ?? branches[0];

  return (
    <PanelShell {...props} style={ACCENT}>
      <div data-screen-label="Quantum Outliner" style={panelBox}>
        <div style={{ position: "absolute", top: -1, left: -1, width: 14, height: 14, borderTop: "1px solid var(--violet)", borderLeft: "1px solid var(--violet)", zIndex: 9 }} />
        <div style={{ position: "absolute", top: 3, left: 3, width: 5, height: 5, background: "var(--violet)", zIndex: 9 }} />

        {/* toolbar — premise input + generate */}
        <div style={{ height: 44, flex: "none", display: "flex", alignItems: "center", gap: 12, padding: "0 16px", borderBottom: "1px solid var(--line-v)", background: "rgba(8,6,14,.7)", zIndex: 6 }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 14, letterSpacing: ".12em", color: "#fff", flex: "none" }}>QUANTUM OUTLINER</span>
          <span style={{ fontSize: 9, color: "var(--violet)", letterSpacing: ".1em", flex: "none" }}>λ</span>
          <input
            value={premise}
            onChange={(e) => setPremise(e.target.value)}
            placeholder="premise / branch point — e.g. “She finally says the Warden's name”"
            style={{ flex: 1, minWidth: 0, background: "rgba(11,8,18,.6)", border: "1px solid var(--line2)", color: "var(--txt)", fontSize: 11, padding: "5px 9px", outline: "none", fontFamily: "inherit" }}
          />
          <span
            onClick={canRun ? () => { setSelId(null); generate(premise); } : undefined}
            style={{ flex: "none", fontSize: 9, color: "#04060a", background: canRun ? "var(--violet)" : "var(--line2)", padding: "5px 11px", fontWeight: 600, letterSpacing: ".08em", cursor: canRun ? "pointer" : "default", boxShadow: canRun ? "0 0 14px rgba(176,124,255,.4)" : undefined }}
          >
            {running ? "⟳ GENERATING…" : "⟳ GENERATE POSSIBILITIES"}
          </span>
        </div>

        <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
          {/* radial field */}
          <div style={{ flex: 1, minWidth: 0, position: "relative", display: "grid", placeItems: "center", overflow: "hidden" }}>
            <div style={{ position: "relative", width: FIELD_W, height: FIELD_H, maxWidth: "100%", maxHeight: "100%" }}>
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
                  <span style={{ fontFamily: "'Chakra Petch'", fontSize: 18, color: "#fff" }}>ψ</span>
                </div>
                <div style={{ fontFamily: "'Chakra Petch'", fontSize: 11, color: "#fff", marginTop: 6, letterSpacing: ".06em" }}>WAVEFUNCTION</div>
                <div style={{ fontSize: 8, color: "var(--violet)", letterSpacing: ".16em" }}>{branches.length} SUPERPOSED FUTURE{branches.length === 1 ? "" : "S"}</div>
              </div>

              {/* states */}
              {running
                ? message("Collapsing the possibility space…")
                : error
                  ? message(<span style={{ color: "var(--blocking)" }}>Generation failed — {error}</span>)
                  : !result
                    ? message("Enter a premise above and ⟳ GENERATE to fan out branches in superposition.")
                    : branches.length === 0
                      ? message(<>The outliner returned a classical outline (no branches). <span style={{ color: "var(--txt2)" }}>{result.title}</span> — try a more open premise, or switch the project to λ-mode.</>)
                      : branches.map((b, i) => {
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
                              style={{ position: "absolute", left: x, top: y, transform: "translate(-50%,-50%)", width: 228, zIndex: 5, cursor: "pointer", border: `1px solid ${isSel || recommended ? "var(--violet)" : "var(--line2)"}`, background: recommended ? "linear-gradient(180deg,rgba(176,124,255,.12),rgba(8,6,14,.95))" : "rgba(8,8,14,.95)", boxShadow: isSel || recommended ? "0 0 26px rgba(176,124,255,.35)" : undefined }}
                            >
                              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "6px 9px", borderBottom: "1px solid var(--line2)" }}>
                                <span style={{ fontSize: 7.5, letterSpacing: ".14em", color }}>{recommended ? "◉ " : ""}{(b.branch_type || b.title || "BRANCH").toUpperCase().slice(0, 22)}</span>
                                <span style={{ fontFamily: "'Chakra Petch'", fontSize: 16, color: "#fff" }}>{typeof b.score === "number" ? b.score.toFixed(1) : "—"}</span>
                              </div>
                              <div style={{ padding: "8px 9px" }}>
                                <div style={{ fontSize: 10.5, color: "#fff", lineHeight: 1.35, marginBottom: 6 }}>{b.title || b.description || "(untitled branch)"}</div>
                                {typeof b.probability === "number" && <Bar label="prob" pct={b.probability} color={color} />}
                                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 8 }}>
                                  <span style={{ fontSize: 8, color }}>{typeof b.probability === "number" ? `P ${b.probability.toFixed(2)}` : ""}{b.is_pareto_optimal ? " · pareto" : ""}</span>
                                  <span style={{ fontSize: 8, color: isSel ? "#04060a" : "var(--txt2)", background: isSel ? "var(--violet)" : undefined, border: isSel ? undefined : "1px solid var(--line2)", padding: "3px 9px", fontWeight: isSel ? 600 : 400 }}>{isSel ? "SELECTED" : "INSPECT"}</span>
                                </div>
                              </div>
                            </div>
                          );
                        })}
            </div>
          </div>

          {/* recommendation / selected-branch panel */}
          <div style={{ width: 392, flex: "none", borderLeft: "1px solid var(--line-v)", background: "#08060e", display: "flex", flexDirection: "column", overflowY: "auto", padding: 14 }}>
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
                <div style={{ border: "1px solid var(--line2)", background: "rgba(11,8,18,.6)", padding: 11, marginBottom: 11 }}>
                  <div style={{ fontSize: 11, color: "#fff", lineHeight: 1.4, marginBottom: 7 }}>{selected.title || selected.description}</div>
                  {selected.description && selected.title && <div style={{ fontSize: 10, color: "var(--txt2)", lineHeight: 1.5, marginBottom: 7 }}>{selected.description}</div>}
                  <div style={{ display: "flex", gap: 14, fontSize: 8.5, color: "var(--txt3)" }}>
                    {typeof selected.score === "number" && <span>SCORE <span style={{ color: "var(--violet)" }}>{selected.score.toFixed(1)}</span></span>}
                    {typeof selected.probability === "number" && <span>PROB <span style={{ color: "var(--violet)" }}>{selected.probability.toFixed(2)}</span></span>}
                    {selected.is_pareto_optimal && <span style={{ color: "var(--green)" }}>PARETO-OPTIMAL</span>}
                  </div>
                </div>
                {selected.stakes && (
                  <div style={{ border: "1px solid var(--line2)", background: "rgba(11,8,18,.6)", padding: 11, marginBottom: 11 }}>
                    <div style={{ fontSize: 8, letterSpacing: ".16em", color: "var(--txt3)", marginBottom: 6 }}>STAKES</div>
                    <div style={{ fontSize: 10, color: "var(--txt2)", lineHeight: 1.5 }}>{selected.stakes}</div>
                  </div>
                )}
                {selected.consequence && (
                  <div style={{ border: "1px solid var(--line2)", background: "rgba(11,8,18,.6)", padding: 11 }}>
                    <div style={{ fontSize: 8, letterSpacing: ".16em", color: "var(--txt3)", marginBottom: 6 }}>CONSEQUENCE</div>
                    <div style={{ fontSize: 10, color: "var(--txt2)", lineHeight: 1.5 }}>{selected.consequence}</div>
                  </div>
                )}
              </>
            )}
            <div style={{ marginTop: "auto", paddingTop: 12 }}>
              <div style={{ fontSize: 8, color: "var(--amber)", letterSpacing: ".04em" }}>↳ collapsing a branch routes through Controlled Apply · STAGE checkpoint</div>
            </div>
          </div>
        </div>
      </div>
    </PanelShell>
  );
}
