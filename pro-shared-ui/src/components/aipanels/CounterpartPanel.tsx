import { useState, type CSSProperties } from "react";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useCounterpart } from "../../hooks";

const panelBox: CSSProperties = {
  position: "relative",
  width: "100%",
  height: "100%",
  background: "linear-gradient(180deg,var(--panel2),var(--base))",
  border: "1px solid var(--line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)",
  overflow: "hidden",
  display: "flex",
  flexDirection: "column",
};

// The core's five dialogic modes (logosforge.counterpart.DIALOGIC_MODES).
const MODES = ["Feedback", "Critique", "Interpret", "Ask Back", "Compare"];

export function CounterpartPanel(props: PanelProps) {
  const { reflect, running, result, error } = useCounterpart();
  const [mode, setMode] = useState("Critique");
  const [sceneText, setSceneText] = useState("");
  const canRun = !running && sceneText.trim().length > 0;

  return (
    <PanelShell {...props} style={{ ["--accent"]: "#b07cff" } as CSSProperties}>
      <div data-screen-label="Counterpart" style={panelBox}>
        <Corners />

        {/* header — title + mode tabs + contract badge */}
        <div style={{ height: 42, flex: "none", display: "flex", alignItems: "center", gap: 11, padding: "0 16px", borderBottom: "1px solid var(--line)" }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".1em", color: "var(--strong)" }}>COUNTERPART</span>
          <div style={{ display: "flex", gap: 0, border: "1px solid var(--line2)", fontSize: 8, letterSpacing: ".08em" }}>
            {MODES.map((m, i) => (
              <span
                key={m}
                onClick={() => setMode(m)}
                style={{ padding: "4px 8px", cursor: "pointer", borderLeft: i === 0 ? undefined : "1px solid var(--line2)", color: mode === m ? "var(--on-accent)" : "var(--txt3)", background: mode === m ? "var(--accent)" : undefined, fontWeight: mode === m ? 600 : 400 }}
              >
                {m.toUpperCase()}
              </span>
            ))}
          </div>
          <div style={{ flex: 1 }} />
          <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 8, color: "var(--amber)", border: "1px solid rgba(245,177,51,.35)", padding: "3px 9px", letterSpacing: ".1em" }}>⊘ REFLECTION ONLY · CANNOT EDIT</span>
        </div>

        {/* scene-context input */}
        <div style={{ flex: "none", padding: "11px 16px", borderBottom: "1px solid var(--line2)", background: "var(--tint2)" }}>
          <div style={{ fontSize: 8, letterSpacing: ".16em", color: "var(--txt3)", marginBottom: 6 }}>SCENE / EXCERPT TO REFLECT ON</div>
          <textarea
            value={sceneText}
            onChange={(e) => setSceneText(e.target.value)}
            placeholder="Paste the scene text or an excerpt…"
            style={{ width: "100%", height: 64, resize: "vertical", background: "var(--tint)", border: "1px solid var(--line2)", color: "var(--txt)", fontFamily: "'Courier Prime'", fontSize: 12, lineHeight: 1.5, padding: "8px 10px", outline: "none" }}
          />
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 8 }}>
            <span
              onClick={canRun ? () => reflect(mode, sceneText) : undefined}
              style={{ fontSize: 9.5, color: "var(--on-accent)", background: canRun ? "var(--accent)" : "var(--line2)", padding: "6px 13px", fontWeight: 600, letterSpacing: ".08em", cursor: canRun ? "pointer" : "default", boxShadow: canRun ? "0 0 14px rgba(176,124,255,.35)" : undefined }}
            >
              {running ? "REFLECTING…" : `↯ REFLECT · ${mode.toUpperCase()}`}
            </span>
            <span style={{ fontSize: 8, color: "var(--txt3)", letterSpacing: ".04em" }}>the {mode} stance reads your scene and responds — never rewrites</span>
          </div>
        </div>

        {/* reflection output */}
        <div style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "16px" }}>
          {running ? (
            <div style={{ color: "var(--accent)", fontSize: 12, letterSpacing: ".04em" }}>Counterpart is reading the scene…</div>
          ) : error ? (
            <div style={{ color: "var(--blocking)", fontSize: 11.5, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
              Counterpart is unavailable — it needs a running AI provider.{"\n"}
              <span style={{ color: "var(--txt3)", fontSize: 10 }}>{error}</span>
            </div>
          ) : result ? (
            <div style={{ borderLeft: "2px solid var(--accent)", paddingLeft: 13 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <span style={{ width: 9, height: 9, borderRadius: "50%", background: "var(--accent)", boxShadow: "0 0 7px var(--accent)" }} />
                <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 12, letterSpacing: ".1em", color: "var(--accent)" }}>{mode.toUpperCase()}</span>
                {result.cached && <span style={{ fontSize: 7.5, color: "var(--txt3)", border: "1px solid var(--line2)", padding: "1px 5px" }}>CACHED</span>}
              </div>
              <div style={{ fontFamily: "'Courier Prime'", fontSize: 13, color: "var(--txt)", lineHeight: 1.65, whiteSpace: "pre-wrap" }}>{result.reply}</div>
            </div>
          ) : (
            <div style={{ color: "var(--txt3)", fontSize: 11.5, lineHeight: 1.6, maxWidth: 560 }}>
              Choose a stance, paste a scene above, and press <span style={{ color: "var(--accent)" }}>Reflect</span>. Counterpart is a serious second reader — it critiques, questions, and interprets, but never rewrites your prose.
            </div>
          )}
        </div>

        {/* footer */}
        <div style={{ flex: "none", height: 30, display: "flex", alignItems: "center", justifyContent: "center", borderTop: "1px solid var(--line2)", fontSize: 8.5, letterSpacing: ".1em", color: "var(--txt3)" }}>COUNTERPART NEVER WRITES — IT ASKS · apply disabled by contract</div>
      </div>
    </PanelShell>
  );
}
