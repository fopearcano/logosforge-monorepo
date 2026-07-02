import type { CSSProperties } from "react";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";

const panelBox: CSSProperties = {
  position: "relative",
  width: "100%",
  height: "100%",
  background: "linear-gradient(180deg,#080a0f,#05070b)",
  border: "1px solid var(--line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)",
  overflow: "hidden",
  display: "flex",
};

const ACCENT = { ["--accent"]: "#4cc2ff" } as CSSProperties;

/** A stat cell in the 3-col review grid. */
function StatCard({ value, label, valueColor = "#fff", border = "1px solid var(--line2)" }: { value: string; label: string; valueColor?: string; border?: string }) {
  return (
    <div style={{ border, padding: 9, textAlign: "center" }}>
      <div style={{ fontFamily: "'Chakra Petch'", fontSize: 20, color: valueColor }}>{value}</div>
      <div style={{ fontSize: 7, color: "var(--txt3)", letterSpacing: ".1em" }}>{label}</div>
    </div>
  );
}

/** A per-scene status row with a colored left border. */
function SceneStatus({ scene, title, status, color }: { scene: string; title: string; status: string; color: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 9, color: "var(--txt2)", padding: "4px 8px", borderLeft: `2px solid ${color}`, background: "rgba(11,14,21,.4)" }}>
      <span style={{ color: "var(--cyan)" }}>{scene}</span>
      <span style={{ flex: 1 }}>{title}</span>
      <span style={{ color }}>{status}</span>
    </div>
  );
}

/** A review-check lint line: icon + text. */
function Check({ icon, color, text }: { icon: string; color: string; text: string }) {
  return (
    <div style={{ display: "flex", gap: 8 }}>
      <span style={{ color }}>{icon}</span>{text}
    </div>
  );
}

/** A beat row in the pipeline-confirm beat list. */
function BeatRow({ icon, iconColor, title, titleColor, reject = false, dim = false }: { icon: string; iconColor: string; title: string; titleColor: string; reject?: boolean; dim?: boolean }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, border: "1px solid var(--line2)", padding: "7px 9px", opacity: dim ? 0.5 : undefined }}>
      <span style={{ fontSize: 8, color: iconColor }}>{icon}</span>
      <span style={{ fontSize: 9.5, color: titleColor, flex: 1 }}>{title}</span>
      {reject && <span style={{ fontSize: 7, color: "var(--txt3)" }}>reject</span>}
    </div>
  );
}

export function ModeReviewDashboard(props: PanelProps) {
  return (
    <PanelShell {...props} style={ACCENT}>
      <div data-screen-label="Mode Review + Pipeline Confirm" style={panelBox}>
        <Corners />

        {/* review dashboard */}
        <div style={{ flex: 1, borderRight: "1px solid var(--line)", display: "flex", flexDirection: "column", minWidth: 0 }}>
          <div style={{ height: 40, flex: "none", display: "flex", alignItems: "center", gap: 10, padding: "0 16px", borderBottom: "1px solid var(--line)" }}>
            <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".1em", color: "#fff" }}>MODE REVIEW</span>
            <span style={{ fontSize: 8, color: "var(--cyan)", border: "1px solid var(--line-cy)", padding: "2px 7px" }}>SCREENPLAY</span>
          </div>
          <div style={{ flex: 1, overflowY: "auto", padding: "13px 16px" }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 9, marginBottom: 13 }}>
              <StatCard value="24" label="SCENES" />
              <StatCard value="112" label="EST PAGES" />
              <StatCard value="9" label="DIAGNOSTICS" valueColor="var(--warning)" border="1px solid rgba(255,180,84,.3)" />
            </div>
            <div style={{ fontSize: 7.5, letterSpacing: ".18em", color: "var(--txt3)", marginBottom: 7 }}>PER-SCENE STATUS</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 13 }}>
              <SceneStatus scene="SC.12" title="Observation Ring" status="strong" color="var(--green)" />
              <SceneStatus scene="SC.14" title="The Confession" status="weak" color="var(--warning)" />
              <SceneStatus scene="SC.18" title="Long monologue" status="critical" color="var(--blocking)" />
            </div>
            <div style={{ fontSize: 7.5, letterSpacing: ".18em", color: "var(--txt3)", marginBottom: 7 }}>REVIEW CHECKS · mode lint</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 9, color: "var(--txt2)" }}>
              <Check icon="✓" color="var(--green)" text="every scene has a turn" />
              <Check icon="△" color="var(--warning)" text="parenthetical overuse · SC.14" />
              <Check icon="✕" color="var(--blocking)" text="SC.18 single-voice monologue" />
            </div>
          </div>
        </div>

        {/* pipeline confirm */}
        <div style={{ width: 430, flex: "none", display: "flex", flexDirection: "column", background: "#06080c" }}>
          <div style={{ height: 40, flex: "none", display: "flex", alignItems: "center", gap: 8, padding: "0 14px", borderBottom: "1px solid var(--line2)" }}>
            <span style={{ fontSize: 9, letterSpacing: ".14em", color: "var(--amber)" }}>PLANNING PIPELINE · CONFIRM</span>
          </div>
          <div style={{ flex: 1, overflowY: "auto", padding: "13px 14px" }}>
            <div style={{ fontSize: 9, color: "var(--txt2)", lineHeight: 1.5, marginBottom: 11 }}>Generate <span style={{ color: "#fff" }}>Beat Plan</span> → preview → per-beat accept → <span style={{ color: "var(--amber)" }}>additive apply (separate artifact, never the body)</span></div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <BeatRow icon="✓" iconColor="var(--green)" title="B1 · Catalyst — the signal returns" titleColor="var(--txt)" />
              <BeatRow icon="✓" iconColor="var(--green)" title="B2 · Debate — should they answer?" titleColor="var(--txt)" />
              <BeatRow icon="○" iconColor="var(--txt3)" title="B3 · Break Into Two — open the box" titleColor="var(--txt2)" reject dim />
            </div>
            <div style={{ border: "1px solid rgba(98,217,154,.25)", background: "rgba(98,217,154,.04)", padding: "8px 10px", marginTop: 11, fontSize: 8, color: "var(--green)", lineHeight: 1.5 }}>✓ STAGE checkpoint · additive · 2 of 3 beats · stored in screenplay_beat_plans</div>
            <div style={{ display: "flex", gap: 8, marginTop: 11 }}>
              <span style={{ fontSize: 9, color: "#04060a", background: "var(--green)", padding: "7px 13px", fontWeight: 600 }}>APPLY 2 BEATS</span>
              <span style={{ fontSize: 9, color: "var(--txt2)", border: "1px solid var(--line2)", padding: "7px 13px" }}>CANCEL</span>
            </div>
          </div>
        </div>
      </div>
    </PanelShell>
  );
}
