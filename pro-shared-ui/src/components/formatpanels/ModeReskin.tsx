import type { CSSProperties, ReactNode } from "react";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";

const panelBox: CSSProperties = {
  position: "relative",
  width: "100%",
  height: "100%",
  background: "linear-gradient(180deg,var(--panel),var(--base))",
  border: "1px solid var(--line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)",
  overflow: "hidden",
  display: "flex",
  flexDirection: "column",
};

const ACCENT = { ["--novel"]: "#c8a96a", ["--screen"]: "#4cc2ff", ["--gn"]: "#ff7ac6", ["--stage"]: "#ffb454", ["--series"]: "#62d99a" } as CSSProperties;

/** One of the five writing-mode hero columns. */
function ModeColumn({ color, name, structure, structureSpacing = ".12em", formatLabel, formatFont, bodyFont, bodyFontSize, bodyLineHeight, glow, body, signature, active = false, last = false }: { color: string; name: ReactNode; structure: string; structureSpacing?: string; formatLabel: string; formatFont: string; bodyFont: string; bodyFontSize: number; bodyLineHeight: number; glow: string; body: ReactNode; signature: string; active?: boolean; last?: boolean }) {
  return (
    <div style={{ flex: 1, borderRight: last ? undefined : "1px solid var(--line2)", display: "flex", flexDirection: "column", background: active ? "rgba(76,194,255,.03)" : undefined }}>
      <div style={{ height: 4, background: color, boxShadow: `0 0 ${glow}px ${color}` }} />
      <div style={{ padding: "13px 14px", borderBottom: "1px solid var(--line2)" }}>
        {name}
        <div style={{ fontSize: 8, color: "var(--txt3)", letterSpacing: structureSpacing, marginTop: 3 }}>{structure}</div>
      </div>
      <div style={{ flex: 1, padding: "13px 14px", fontFamily: bodyFont, fontSize: bodyFontSize, color: "var(--txt2)", lineHeight: bodyLineHeight }}>
        <div style={{ fontSize: 7, letterSpacing: ".16em", color: "var(--txt3)", fontFamily: formatFont, marginBottom: 9 }}>{formatLabel}</div>
        {body}
      </div>
      <div style={{ padding: "11px 14px", borderTop: "1px solid var(--line2)", fontSize: 8, color: "var(--txt3)", lineHeight: 1.7 }}>SIGNATURE<br /><span style={{ color: "var(--txt2)" }}>{signature}</span></div>
    </div>
  );
}

/** The Chakra-Petch mode-name title in its mode color. */
function ModeName({ color, children }: { color: string; children: ReactNode }) {
  return <div style={{ fontFamily: "'Chakra Petch'", fontWeight: 700, fontSize: 17, color, letterSpacing: ".04em" }}>{children}</div>;
}

export function ModeReskin(props: PanelProps) {
  return (
    <PanelShell {...props} style={ACCENT}>
      <div data-screen-label="Mode Re-skin" style={panelBox}>
        <Corners />

        {/* header bar */}
        <div style={{ height: 42, flex: "none", display: "flex", alignItems: "center", gap: 13, padding: "0 18px", borderBottom: "1px solid var(--line)" }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 14, letterSpacing: ".1em", color: "var(--strong)" }}>WRITING-MODE RE-SKIN</span>
          <span style={{ fontSize: 9, color: "var(--txt3)" }}>same shell · vocabulary · scene-body · structure labels · accent band change per mode</span>
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 8, color: "var(--stage)", border: "1px solid rgba(255,180,84,.35)", padding: "3px 9px", letterSpacing: ".1em" }}>⊘ ONE-WAY LOCK · set on empty scaffold</span>
        </div>

        {/* 5-column hero */}
        <div style={{ flex: 1, display: "flex" }}>
          {/* NOVEL */}
          <ModeColumn
            color="var(--novel)" structure="ACT · CHAPTER · SCENE" formatLabel="PROSE" glow="12"
            formatFont="'JetBrains Mono'" bodyFont="'Courier Prime'" bodyFontSize={11.5} bodyLineHeight={1.6}
            signature="chapter rhythm · story grid"
            name={<ModeName color="var(--novel)">NOVEL</ModeName>}
            body={<>The corridor breathed. Marlow had stopped counting the days, but the station counted for him — a low hum, dropping a half-step each night.</>}
          />

          {/* SCREENPLAY (current) */}
          <ModeColumn
            active color="var(--screen)" structure="ACT · SEQUENCE · SCENE · BEAT" formatLabel="8-ELEMENT TAXONOMY" glow="14"
            formatFont="'JetBrains Mono'" bodyFont="'Courier Prime'" bodyFontSize={11} bodyLineHeight={1.5}
            signature="beat plan · subtext · Fountain / FDX"
            name={
              <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                <ModeName color="var(--screen)">SCREENPLAY</ModeName>
                <span style={{ fontSize: 7, color: "var(--screen)" }}>● ACTIVE</span>
              </div>
            }
            body={
              <>
                <div style={{ color: "var(--strong)", fontWeight: 700 }}>INT. HELIOS-9 — NIGHT</div>
                <div style={{ margin: "5px 0", opacity: 0.8 }}>Marlow floats at the viewport.</div>
                <div style={{ textAlign: "center", fontWeight: 700, color: "var(--strong)" }}>VESPER</div>
                <div style={{ textAlign: "center", opacity: 0.85 }}>He's counting heartbeats.</div>
              </>
            }
          />

          {/* GRAPHIC NOVEL */}
          <ModeColumn
            color="var(--gn)" structure="ACT · PAGE · SCENE · PANEL" formatLabel="PAGE / PANEL SCRIPT" glow="12"
            formatFont="'JetBrains Mono'" bodyFont="'JetBrains Mono'" bodyFontSize={10} bodyLineHeight={1.55}
            signature="page canvas · image-prompt export"
            name={<ModeName color="var(--gn)">GRAPHIC NOVEL</ModeName>}
            body={
              <>
                <div style={{ color: "var(--gn)" }}>PAGE 4 · PANEL 1</div>
                <div style={{ margin: "3px 0" }}><span style={{ color: "var(--txt3)" }}>VISUAL:</span> Wide. The dead planet fills the glass.</div>
                <div><span style={{ color: "var(--txt3)" }}>CAPTION:</span> Nine years of silence.</div>
                <div><span style={{ color: "var(--txt3)" }}>SFX:</span> hmmmmm</div>
              </>
            }
          />

          {/* STAGE SCRIPT */}
          <ModeColumn
            color="var(--stage)" structure="ACT · SCENE · BEAT" formatLabel="13 TYPED BLOCKS" glow="12"
            formatFont="'JetBrains Mono'" bodyFont="'Courier Prime'" bodyFontSize={10.5} bodyLineHeight={1.55}
            signature="blocking / cue board"
            name={<ModeName color="var(--stage)">STAGE SCRIPT</ModeName>}
            body={
              <>
                <div style={{ fontStyle: "italic", opacity: 0.8 }}>(Marlow at the port. Vesper enters.)</div>
                <div style={{ textAlign: "center", fontWeight: 700, color: "var(--strong)", marginTop: 5 }}>VESPER</div>
                <div style={{ textAlign: "center", opacity: 0.85 }}>You shouldn't be up here.</div>
                <div style={{ color: "var(--stage)", marginTop: 5 }}>[LIGHT CUE 12 — fade amber]</div>
              </>
            }
          />

          {/* SERIES */}
          <ModeColumn
            last color="var(--series)" structure="SEASON · EPISODE · ACT · SCENE" structureSpacing=".1em" formatLabel="TELEPLAY + SERIAL MARKERS" glow="12"
            formatFont="'JetBrains Mono'" bodyFont="'Courier Prime'" bodyFontSize={10.5} bodyLineHeight={1.55}
            signature="Series Navigator · A/B/C lanes"
            name={<div style={{ fontFamily: "'Chakra Petch'", fontWeight: 700, fontSize: 17, color: "var(--series)", letterSpacing: ".04em" }}>SERIES</div>}
            body={
              <>
                <div style={{ color: "var(--series)" }}>EP.103 · TEASER</div>
                <div style={{ color: "var(--strong)", fontWeight: 700, marginTop: 4 }}>INT. HELIOS-9 — NIGHT</div>
                <div style={{ margin: "4px 0", opacity: 0.8 }}>The signal repeats. Vesper freezes.</div>
                <div style={{ fontFamily: "'JetBrains Mono'", fontSize: 8, color: "var(--series)" }}>[A-STORY] [CLIFFHANGER]</div>
              </>
            }
          />
        </div>
      </div>
    </PanelShell>
  );
}
