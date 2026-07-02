import type { CSSProperties, ReactNode } from "react";

/**
 * The three dock regions shown in the Workspace Shell page. They are faithful,
 * slot-swappable defaults: when the Manuscript & Structure (T02), Project OS
 * (T06), and Spatial Canvases (T03) handoffs are implemented, the real,
 * ApiClient-bound panels replace these via the shell's slot props. Each carries
 * the design's data-screen-label for comment↔code mapping.
 */

// ── center: Manuscript editor ───────────────────────────────────────────────

function ToolbarSpan({ children }: { children: ReactNode }) {
  return (
    <span className="lf-hov" style={{ fontSize: 9.5, letterSpacing: ".14em", color: "var(--txt2)", cursor: "pointer" }}>
      {children}
    </span>
  );
}

const gutterDot = (top: number, color: string, size = 7, glow = false, diamond = false): CSSProperties => ({
  position: "absolute",
  top,
  width: size,
  height: size,
  borderRadius: diamond ? undefined : "50%",
  transform: diamond ? "rotate(45deg)" : undefined,
  background: color,
  boxShadow: glow ? `0 0 ${size + 1}px ${color}` : undefined,
});

export function ManuscriptRegion() {
  return (
    <div data-screen-label="Manuscript editor (center)" style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", background: "radial-gradient(120% 80% at 50% 0%,#080a10,#040609)", position: "relative" }}>
      {/* editor toolbar */}
      <div style={{ height: 36, flex: "none", display: "flex", alignItems: "center", gap: 12, padding: "0 16px", borderBottom: "1px solid var(--line2)", background: "rgba(6,8,12,.6)" }}>
        <span style={{ fontSize: 10, color: "var(--txt2)", letterSpacing: ".05em" }}>3,214 <span style={{ color: "var(--txt3)" }}>WORDS</span></span>
        <span style={{ width: 1, height: 14, background: "var(--line2)" }} />
        <div style={{ display: "flex", alignItems: "center", gap: 7, height: 22, padding: "0 9px", border: "1px solid var(--line2)", fontSize: 9, letterSpacing: ".12em", color: "var(--txt2)" }}>ELEMENT <span style={{ color: "var(--accent)", fontWeight: 600 }}>DIALOGUE</span> <span style={{ color: "var(--txt3)" }}>▾</span></div>
        <span style={{ fontSize: 9, color: "var(--txt3)", letterSpacing: ".08em" }}>TAB → PARENTHETICAL</span>
        <div style={{ flex: 1 }} />
        <ToolbarSpan>A▾</ToolbarSpan>
        <ToolbarSpan>REVIEW ▾</ToolbarSpan>
        <ToolbarSpan>⊹ FOCUS</ToolbarSpan>
        <ToolbarSpan>TEXT/BG ▾</ToolbarSpan>
      </div>

      {/* manuscript scroll */}
      <div style={{ flex: 1, overflowY: "auto", position: "relative", display: "flex", justifyContent: "center", padding: "30px 0 40px" }}>
        {/* energy gutter */}
        <div style={{ position: "absolute", left: "calc(50% - 430px)", top: 34, bottom: 30, width: 10, display: "flex", flexDirection: "column", alignItems: "center", gap: 0 }}>
          <div style={{ fontSize: 7, color: "var(--txt3)", letterSpacing: ".1em", writingMode: "vertical-rl", transform: "rotate(180deg)", height: 64 }}>TENSION</div>
          <div style={{ flex: 1, width: 2, background: "linear-gradient(180deg,var(--green),var(--amber) 55%,var(--blocking))", opacity: 0.55, margin: "6px 0" }} />
          <div style={gutterDot(84, "var(--green)", 7, true)} />
          <div style={gutterDot(150, "var(--green)", 7)} />
          <div style={gutterDot(220, "var(--amber)", 8, true, true)} />
          <div style={gutterDot(300, "var(--amber)", 7)} />
          <div style={gutterDot(372, "var(--blocking)", 9, true)} />
          <div style={gutterDot(452, "var(--blocking)", 8, false, true)} />
        </div>

        {/* review metrics overlay */}
        <div style={{ position: "absolute", top: 18, right: 26, width: 236, background: "rgba(8,11,17,.94)", border: "1px solid var(--line)", padding: "11px 12px", zIndex: 5, boxShadow: "0 8px 30px rgba(0,0,0,.6)" }}>
          <div style={{ position: "absolute", top: -1, right: -1, width: 8, height: 8, borderTop: "1px solid var(--crimson)", borderRight: "1px solid var(--crimson)" }} />
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--line2)", paddingBottom: 6, marginBottom: 8 }}>
            <span style={{ fontSize: 8.5, letterSpacing: ".24em", color: "var(--crimson)" }}>REVIEW METRICS</span>
            <span style={{ fontSize: 8, color: "var(--txt3)" }}>⊹ ✕</span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "7px 12px", fontSize: 9 }}>
            <div><div style={{ color: "var(--txt3)", fontSize: 7.5, letterSpacing: ".1em" }}>SHORTEST</div><div style={{ color: "var(--txt)", fontFamily: "'Chakra Petch'", fontSize: 13 }}>96<span style={{ fontSize: 8, color: "var(--txt3)" }}>w</span></div></div>
            <div><div style={{ color: "var(--txt3)", fontSize: 7.5, letterSpacing: ".1em" }}>LONGEST</div><div style={{ color: "var(--txt)", fontFamily: "'Chakra Petch'", fontSize: 13 }}>812<span style={{ fontSize: 8, color: "var(--txt3)" }}>w</span></div></div>
          </div>
          <div style={{ fontSize: 7.5, letterSpacing: ".14em", color: "var(--txt3)", margin: "9px 0 4px" }}>PACING BALANCE S / M / L</div>
          <div style={{ display: "flex", height: 7, gap: 2 }}>
            <div style={{ width: "34%", background: "var(--green)" }} /><div style={{ width: "46%", background: "var(--amber)" }} /><div style={{ width: "20%", background: "var(--blocking)" }} />
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 9, fontSize: 9 }}><span style={{ color: "var(--txt2)" }}>FLAGGED SCENES</span><span style={{ color: "var(--warning)", fontWeight: 600 }}>3</span></div>
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, fontSize: 9 }}><span style={{ color: "var(--txt2)" }}>STRUCTURAL ISSUES</span><span style={{ color: "var(--blocking)", fontWeight: 600 }}>2</span></div>
        </div>

        {/* screenplay column */}
        <div style={{ width: 660, fontFamily: "'Courier Prime',monospace", fontSize: 15, lineHeight: 1.55, color: "#cfd4dc" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
            <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 10, letterSpacing: ".3em", color: "var(--accent)" }}>ACT II · SEQUENCE D</span>
            <span style={{ flex: 1, height: 1, background: "var(--line2)" }} />
          </div>
          <div style={{ display: "flex", gap: 12, alignItems: "baseline", margin: "14px 0 16px", opacity: 0.92 }}>
            <span style={{ fontFamily: "'Chakra Petch'", color: "var(--txt3)", fontSize: 13 }}>12</span>
            <span style={{ fontWeight: 700, letterSpacing: ".04em", color: "#fff" }}>INT. <span style={{ color: "var(--accent)", borderBottom: "1px dotted var(--accent)" }}>HELIOS-9</span> — OBSERVATION RING — NIGHT CYCLE</span>
          </div>
          <p style={{ margin: "0 0 14px", opacity: 0.72 }}>The corridor breathes. Somewhere below, the reactor drops a half-step and holds. <span style={{ color: "var(--accent)", borderBottom: "1px dotted rgba(76,194,255,.6)" }}>MARLOW</span> floats at the viewport, watching a dead planet turn through the glass.</p>
          <div style={{ textAlign: "center", margin: "18px 0 0", fontWeight: 700, letterSpacing: ".06em", opacity: 0.78 }}>MARLOW</div>
          <div style={{ textAlign: "center", fontStyle: "italic", color: "var(--txt2)", opacity: 0.8 }}>(not turning)</div>
          <p style={{ margin: "2px auto 14px", width: "62%", textAlign: "center", opacity: 0.8 }}>You shouldn't be up here.</p>
          <p style={{ margin: "0 0 14px", opacity: 0.72 }}>A hatch cycles. <span style={{ color: "var(--green)", borderBottom: "1px dotted rgba(98,217,154,.6)" }}>VESPER</span> lets it seal behind her. The static between them is older than the station.</p>

          {/* active block + floating format toolbar */}
          <div style={{ position: "relative", background: "linear-gradient(90deg,rgba(76,194,255,.07),transparent 80%)", boxShadow: "inset 2px 0 0 var(--accent)", padding: "6px 0 6px 4px", margin: "46px 0 10px" }}>
            <div style={{ position: "absolute", top: -34, left: "50%", transform: "translateX(-50%)", display: "flex", alignItems: "center", gap: 2, height: 28, padding: "0 6px", background: "#0a0d14", border: "1px solid var(--line)", boxShadow: "0 6px 22px rgba(0,0,0,.7)", fontFamily: "'JetBrains Mono'", zIndex: 6 }}>
              <span style={{ padding: "0 7px", fontWeight: 700, color: "var(--txt)", fontSize: 11 }}>B</span>
              <span style={{ padding: "0 7px", fontStyle: "italic", color: "var(--txt2)", fontSize: 11 }}>I</span>
              <span style={{ padding: "0 7px", color: "var(--txt2)", fontSize: 11 }}>H</span>
              <span style={{ padding: "0 7px", color: "var(--txt2)", fontSize: 11 }}>❝</span>
              <span style={{ width: 1, height: 15, background: "var(--line2)", margin: "0 3px" }} />
              <span style={{ padding: "0 8px", color: "var(--accent)", fontSize: 9, letterSpacing: ".1em" }}>REWRITE</span>
              <span style={{ padding: "0 8px", color: "var(--txt2)", fontSize: 9, letterSpacing: ".1em" }}>EXPAND</span>
              <span style={{ padding: "0 8px", color: "var(--txt2)", fontSize: 9, letterSpacing: ".1em" }}>DIALOGUE</span>
              <span style={{ padding: "0 8px", color: "var(--amber)", fontSize: 9, letterSpacing: ".1em" }}>TENSION</span>
            </div>
            <div style={{ textAlign: "center", fontWeight: 700, letterSpacing: ".06em", color: "#fff" }}>VESPER</div>
            <p style={{ margin: "2px auto 0", width: "64%", textAlign: "center", color: "#eef1f6" }}>Neither should you. The Warden is counting heartbeats tonight<span style={{ display: "inline-block", width: 2, height: 16, background: "var(--accent)", verticalAlign: -3, marginLeft: 1, animation: "lf-blink 1.1s step-end infinite", boxShadow: "0 0 6px var(--accent)" }} /></p>
          </div>

          <p style={{ margin: "6px 0 14px", opacity: 0.7 }}>She means <span style={{ color: "var(--crimson)", borderBottom: "1px dotted rgba(232,68,58,.6)" }}>THE WARDEN</span> — the thing they no longer call a person.</p>
          <div style={{ textAlign: "right", fontWeight: 700, letterSpacing: ".08em", color: "var(--txt2)", opacity: 0.7, marginTop: 18 }}>SMASH CUT TO:</div>
          <div style={{ display: "flex", gap: 8, marginTop: 26, opacity: 0.6 }}>
            <span style={{ fontSize: 11, color: "var(--txt2)", border: "1px dashed var(--line2)", padding: "5px 12px" }}>+ NEW SCENE</span>
            <span style={{ fontSize: 11, color: "var(--txt2)", border: "1px dashed var(--line2)", padding: "5px 12px" }}>+ NEW SEQUENCE</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── right: Intelligence dock (Decision Radar + Story Health) ─────────────────

function ConfidenceBars({ level }: { level: "HIGH" | "MED" | "LOW" }) {
  const fill = level === "HIGH" ? "var(--green)" : "var(--amber)";
  const n = level === "HIGH" ? 3 : level === "MED" ? 2 : 1;
  return (
    <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 7.5, color: "var(--txt3)", letterSpacing: ".1em" }}>
      <span style={{ display: "flex", gap: 1 }}>
        {[0, 1, 2].map((i) => (
          <span key={i} style={{ width: 3, height: 8, background: i < n ? fill : "rgba(255,255,255,.12)" }} />
        ))}
      </span>
      {level}
    </span>
  );
}

function RadarCard({
  severity,
  label,
  icon,
  confidence,
  title,
  desc,
  chips,
  emphatic = false,
  lastMargin = 8,
}: {
  severity: string;
  label: string;
  icon: ReactNode;
  confidence: "HIGH" | "MED" | "LOW";
  title: string;
  desc?: string;
  chips: { text: string; color: string; border: string; hover: string }[];
  emphatic?: boolean;
  lastMargin?: number;
}) {
  return (
    <div style={{ position: "relative", border: emphatic ? "1px solid rgba(255,82,96,.4)" : "1px solid var(--line2)", background: emphatic ? "linear-gradient(180deg,rgba(255,82,96,.07),transparent)" : "rgba(11,14,21,.5)", padding: "10px 11px 11px", marginBottom: lastMargin, boxShadow: emphatic ? "0 0 16px rgba(255,82,96,.07)" : undefined }}>
      <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 2, background: severity, boxShadow: emphatic ? `0 0 8px ${severity}` : undefined }} />
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 8, letterSpacing: ".18em", color: severity }}>{icon}{label}</span>
        <ConfidenceBars level={confidence} />
      </div>
      <div style={{ fontSize: 11.5, color: emphatic ? "#fff" : "var(--txt)", lineHeight: 1.4, marginBottom: desc ? 5 : 8 }}>{title}</div>
      {desc && <div style={{ fontSize: 9.5, color: "var(--txt2)", lineHeight: 1.4, marginBottom: 8 }}>{desc}</div>}
      <div style={{ display: "flex", gap: 6 }}>
        {chips.map((c, i) => (
          <span key={i} className={c.hover} style={{ fontSize: 8.5, letterSpacing: ".1em", color: c.color, border: `1px solid ${c.border}`, padding: "3px 8px", cursor: "pointer" }}>{c.text}</span>
        ))}
      </div>
    </div>
  );
}

function HealthGauge({ value, label, status, color, pct, problem = false }: { value: number; label: string; status: string; color: string; pct: number; problem?: boolean }) {
  return (
    <div style={{ border: problem ? "1px solid rgba(255,82,96,.3)" : "1px solid var(--line2)", padding: 9, display: "flex", alignItems: "center", gap: 10, background: problem ? "rgba(255,82,96,.04)" : "rgba(11,14,21,.4)" }}>
      <div style={{ position: "relative", width: 34, height: 34, borderRadius: "50%", background: `conic-gradient(${color} 0 ${pct}%,rgba(255,255,255,.07) ${pct}%)`, display: "grid", placeItems: "center" }}>
        <div style={{ width: 24, height: 24, borderRadius: "50%", background: "var(--base)", display: "grid", placeItems: "center", fontFamily: "'Chakra Petch'", fontSize: 11, color }}>{value}</div>
      </div>
      <div><div style={{ fontSize: 9, color: "var(--txt)" }}>{label}</div><div style={{ fontSize: 7.5, letterSpacing: ".1em", color }}>{status}</div></div>
    </div>
  );
}

export function IntelligenceDock() {
  return (
    <div data-screen-label="Intelligence dock (right)" style={{ width: 372, flex: "none", display: "flex", flexDirection: "column", background: "linear-gradient(180deg,#07090e,#05070b)", borderLeft: "1px solid var(--line)" }}>
      {/* dock tabs */}
      <div style={{ height: 34, flex: "none", display: "flex", alignItems: "stretch", borderBottom: "1px solid var(--line)" }}>
        <div className="lf-hov" style={{ display: "flex", alignItems: "center", gap: 6, padding: "0 12px", color: "var(--txt3)", fontSize: 9, letterSpacing: ".14em", cursor: "pointer", borderRight: "1px solid var(--line2)" }}>⠿ ASSISTANT</div>
        <div style={{ position: "relative", display: "flex", alignItems: "center", gap: 6, padding: "0 13px", color: "var(--crimson)", fontSize: 9, letterSpacing: ".14em", background: "rgba(232,68,58,.06)", borderRight: "1px solid var(--line2)" }}>
          <div style={{ position: "absolute", left: 0, right: 0, bottom: -1, height: 2, background: "var(--crimson)", boxShadow: "0 0 8px var(--crimson)" }} />RADAR <span style={{ background: "var(--blocking)", color: "#fff", fontSize: 7.5, padding: "0 4px", borderRadius: 6, animation: "lf-glow 2.2s ease-in-out infinite" }}>1</span>
        </div>
        <div className="lf-hov" style={{ display: "flex", alignItems: "center", gap: 6, padding: "0 12px", color: "var(--txt3)", fontSize: 9, letterSpacing: ".14em", cursor: "pointer", borderRight: "1px solid var(--line2)" }}>HEALTH</div>
        <div className="lf-hov" style={{ display: "flex", alignItems: "center", gap: 6, padding: "0 12px", color: "var(--txt3)", fontSize: 9, letterSpacing: ".14em", cursor: "pointer" }}>CONTINUITY</div>
        <div style={{ flex: 1 }} />
        <div style={{ display: "flex", alignItems: "center", gap: 9, padding: "0 11px", color: "var(--txt3)", fontSize: 11 }}><span className="lf-hov" style={{ cursor: "pointer" }}>⤢</span><span className="lf-hov" style={{ cursor: "pointer" }}>⊟</span><span className="lf-hov" style={{ cursor: "pointer" }}>✕</span></div>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: 12 }}>
        {/* decision radar header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 11 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
            <div style={{ position: "relative", width: 24, height: 24, borderRadius: "50%", border: "1px solid var(--line)", overflow: "hidden" }}>
              <div style={{ position: "absolute", inset: 0, background: "conic-gradient(from 0deg,rgba(232,68,58,.55),transparent 28%)", animation: "lf-sweep 3.4s linear infinite" }} />
              <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", color: "var(--crimson)", fontSize: 9 }}>◎</div>
            </div>
            <div>
              <div style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".1em", color: "#fff" }}>DECISION RADAR</div>
              <div style={{ fontSize: 8, letterSpacing: ".1em", color: "var(--txt3)" }}>10 SIGNALS · RANKED · ADVISORY ONLY</div>
            </div>
          </div>
          <div style={{ display: "flex", gap: 5, alignItems: "center", fontSize: 8 }}>
            <span style={{ color: "var(--blocking)" }}>●1</span><span style={{ color: "var(--warning)" }}>●1</span><span style={{ color: "var(--suggestion)" }}>●1</span><span style={{ color: "var(--opportunity)" }}>●1</span>
          </div>
        </div>

        <RadarCard
          severity="var(--blocking)"
          label="BLOCKING"
          emphatic
          icon={<span style={{ width: 10, height: 10, background: "var(--blocking)", display: "inline-grid", placeItems: "center", color: "#fff", fontSize: 7 }}>!</span>}
          confidence="HIGH"
          title={"Unpaid setup — the “black box” planted in Scene 04 has no payoff."}
          desc="A promise this strong left open reads as a plot hole by the climax."
          chips={[
            { text: "→ SETUP / PAYOFF", color: "var(--blocking)", border: "rgba(255,82,96,.45)", hover: "lf-block" },
            { text: "START WORKFLOW", color: "var(--txt2)", border: "var(--line2)", hover: "lf-hov" },
          ]}
        />
        <RadarCard
          severity="var(--warning)"
          label="WARNING"
          icon={<span style={{ width: 8, height: 8, transform: "rotate(45deg)", background: "var(--warning)" }} />}
          confidence="MED"
          title="Act II runs 34% longer than Act I — the midpoint drifts late."
          chips={[{ text: "→ STRUCTURE", color: "var(--warning)", border: "rgba(255,180,84,.4)", hover: "lf-warn" }]}
        />
        <RadarCard
          severity="var(--suggestion)"
          label="SUGGESTION"
          icon={<span style={{ width: 8, height: 8, borderRadius: "50%", border: "2px solid var(--suggestion)" }} />}
          confidence="HIGH"
          title="MARLOW is absent for 5 consecutive scenes (14–18)."
          chips={[{ text: "→ CONTINUITY", color: "var(--suggestion)", border: "var(--line-cy)", hover: "lf-sug" }]}
        />
        <RadarCard
          severity="var(--opportunity)"
          label="OPPORTUNITY"
          icon={<span style={{ width: 8, height: 8, background: "var(--opportunity)", clipPath: "polygon(50% 0,100% 100%,0 100%)" }} />}
          confidence="MED"
          title={"The motif “static” recurs across 6 scenes — promote it to a theme?"}
          lastMargin={14}
          chips={[{ text: "→ PSYKE", color: "var(--opportunity)", border: "rgba(98,217,154,.4)", hover: "lf-opp" }]}
        />

        {/* story health */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderTop: "1px solid var(--line)", paddingTop: 11, marginBottom: 11 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ color: "var(--txt3)" }}>⠿</span>
            <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".1em", color: "#fff" }}>STORY HEALTH</span>
          </div>
          <span style={{ fontSize: 8, letterSpacing: ".1em", color: "var(--txt3)" }}>DETERMINISTIC ▾</span>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 9 }}>
          <HealthGauge value={72} label="Structure" status="BALANCED" color="var(--green)" pct={72} />
          <HealthGauge value={48} label="Characters" status="SPARSE" color="var(--amber)" pct={48} />
          <HealthGauge value={61} label="Arc Cover" status="BALANCED" color="var(--green)" pct={61} />
          <HealthGauge value={33} label="Density" status="PROBLEM" color="var(--blocking)" pct={33} problem />
        </div>

        {/* collapsed assistant */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderTop: "1px solid var(--line)", marginTop: 13, paddingTop: 11 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ color: "var(--txt3)" }}>⠿</span>
            <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".1em", color: "var(--txt2)" }}>ASSISTANT · BILLY</span>
          </div>
          <span style={{ fontSize: 11, color: "var(--txt3)" }}>▸</span>
        </div>
      </div>
    </div>
  );
}

// ── bottom: Analysis dock (Plot · Timeline) ──────────────────────────────────

function LaneChip({ w, border, bg, color, text, ml, dashed = false, glow = false }: { w?: number; border: string; bg: string; color: string; text: string; ml?: number; dashed?: boolean; glow?: boolean }) {
  return (
    <div className={dashed ? "lf-chip" : undefined} style={{ flex: "none", width: w, height: 20, border: `1px ${dashed ? "dashed" : "solid"} ${border}`, background: bg, fontSize: 8, color, display: "flex", alignItems: "center", padding: dashed ? "0 11px" : "0 6px", marginLeft: ml, boxShadow: glow ? "0 0 10px rgba(76,194,255,.2)" : undefined, letterSpacing: dashed ? ".08em" : undefined, cursor: dashed ? "pointer" : undefined }}>
      {text}
    </div>
  );
}

function LaneLabel({ color, text }: { color: string; text: string }) {
  return (
    <div style={{ width: 118, flex: "none", padding: "0 10px", fontSize: 8.5, letterSpacing: ".1em", color, borderRight: "1px solid var(--line2)", display: "flex", alignItems: "center", gap: 6 }}>
      <span style={{ width: 6, height: 6, background: color }} />{text}
    </div>
  );
}

export function BottomDock() {
  return (
    <div data-screen-label="Analysis dock (bottom)" style={{ position: "relative", zIndex: 20, height: 200, flex: "none", display: "flex", flexDirection: "column", background: "linear-gradient(180deg,#07090e,#040609)", borderTop: "1px solid var(--line)" }}>
      <div style={{ position: "absolute", top: -1, left: 232, width: 10, height: 10, borderTop: "1px solid var(--crimson)", borderLeft: "1px solid var(--crimson)" }} />
      {/* dock tabs */}
      <div style={{ height: 30, flex: "none", display: "flex", alignItems: "stretch", borderBottom: "1px solid var(--line2)" }}>
        <div style={{ position: "relative", display: "flex", alignItems: "center", gap: 7, padding: "0 14px", color: "var(--accent)", fontSize: 9, letterSpacing: ".14em", background: "rgba(76,194,255,.05)" }}>
          <div style={{ position: "absolute", left: 0, right: 0, bottom: -1, height: 2, background: "var(--accent)", boxShadow: "0 0 8px var(--accent)" }} />☰ PLOT · TIMELINE
        </div>
        {["∿ PACING / TENSION", "◇ BEATS", "# TAGS", "◍ VOICE"].map((t) => (
          <div key={t} className="lf-hov" style={{ display: "flex", alignItems: "center", gap: 7, padding: "0 14px", color: "var(--txt3)", fontSize: 9, letterSpacing: ".14em", cursor: "pointer" }}>{t}</div>
        ))}
        <div style={{ flex: 1 }} />
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "0 12px", color: "var(--txt3)", fontSize: 8, letterSpacing: ".14em" }}>STRUCTURAL <span style={{ color: "var(--accent)" }}>⇄</span> CUSTOM ORDER · ⠿ ⊟</div>
      </div>

      {/* tension EKG ribbon */}
      <div style={{ height: 42, flex: "none", position: "relative", borderBottom: "1px solid var(--line2)", overflow: "hidden" }}>
        <svg viewBox="0 0 1688 42" preserveAspectRatio="none" style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}>
          <defs>
            <linearGradient id="lf-ten" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="rgba(245,177,51,.35)" /><stop offset="1" stopColor="rgba(245,177,51,0)" />
            </linearGradient>
          </defs>
          <polyline points="0,30 120,28 240,22 360,26 480,16 600,20 720,12 840,18 960,8 1080,22 1200,14 1320,6 1440,18 1560,30 1688,24" fill="none" stroke="#f5b133" strokeWidth="1.5" style={{ filter: "drop-shadow(0 0 4px rgba(245,177,51,.7))" }} />
          <polygon points="0,30 120,28 240,22 360,26 480,16 600,20 720,12 840,18 960,8 1080,22 1200,14 1320,6 1440,18 1560,30 1688,24 1688,42 0,42" fill="url(#lf-ten)" />
          <circle cx="1320" cy="6" r="3" fill="#ff5260" style={{ filter: "drop-shadow(0 0 5px #ff5260)" }} />
        </svg>
        <span style={{ position: "absolute", left: 12, top: 5, fontSize: 7.5, letterSpacing: ".18em", color: "var(--txt3)" }}>TENSION 0–10 · STORY EKG</span>
        <span style={{ position: "absolute", left: 1190, top: 5, fontSize: 7.5, letterSpacing: ".14em", color: "var(--blocking)" }}>▲ CLIMAX PEAK · SC.21</span>
      </div>

      {/* swimlanes */}
      <div style={{ flex: 1, overflow: "hidden", position: "relative", padding: "7px 0 0" }}>
        <div style={{ display: "flex", alignItems: "center", height: 30 }}>
          <LaneLabel color="var(--accent)" text="A · MARLOW" />
          <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 7, padding: "0 14px", overflow: "hidden" }}>
            <LaneChip w={78} border="var(--line-cy)" bg="rgba(76,194,255,.07)" color="var(--txt2)" text="08 · Drift" />
            <LaneChip w={78} border="var(--line-cy)" bg="rgba(76,194,255,.07)" color="var(--txt2)" text="10 · Signal" />
            <LaneChip w={88} border="var(--accent)" bg="rgba(76,194,255,.16)" color="#fff" text="12 · Obs. Ring ●" glow />
            <LaneChip w={78} border="var(--line2)" bg="rgba(255,255,255,.02)" color="var(--txt3)" text="15 · Descent" />
            <LaneChip border="var(--line2)" bg="transparent" color="var(--txt3)" text="＋ 9 SCENES OFF TIMELINE" dashed />
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", height: 30 }}>
          <LaneLabel color="var(--green)" text="B · VESPER" />
          <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 7, padding: "0 14px", overflow: "hidden" }}>
            <LaneChip w={78} border="rgba(98,217,154,.3)" bg="rgba(98,217,154,.06)" color="var(--txt2)" text="11 · Hatch" ml={90} />
            <LaneChip w={96} border="var(--warning)" bg="rgba(255,180,84,.1)" color="var(--amber-b)" text="13 · Midpoint ◆" />
            <LaneChip w={78} border="rgba(98,217,154,.3)" bg="rgba(98,217,154,.06)" color="var(--txt2)" text="17 · Confide" />
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", height: 30 }}>
          <LaneLabel color="var(--crimson)" text="C · WARDEN" />
          <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 7, padding: "0 14px", overflow: "hidden" }}>
            <LaneChip w={78} border="rgba(232,68,58,.3)" bg="rgba(232,68,58,.06)" color="var(--txt2)" text="16 · Watch" ml={300} />
            <LaneChip w={104} border="var(--blocking)" bg="rgba(255,82,96,.12)" color="#fff" text="21 · All Is Lost ◆" />
          </div>
        </div>
        {/* amber numbered ruler */}
        <div style={{ position: "absolute", left: 118, right: 0, bottom: 0, height: 18, borderTop: "1px solid var(--line2)", backgroundImage: "repeating-linear-gradient(90deg,rgba(245,177,51,.45) 0 1px,transparent 1px 4px)" }}>
          <div style={{ position: "absolute", inset: 0, display: "flex", justifyContent: "space-between", padding: "3px 22px 0", fontSize: 7, letterSpacing: ".1em", color: "rgba(245,177,51,.7)" }}>
            {["08", "09", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22"].map((n) => <span key={n}>{n}</span>)}
          </div>
        </div>
      </div>
    </div>
  );
}
