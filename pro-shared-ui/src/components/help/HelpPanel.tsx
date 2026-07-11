import type { CSSProperties, ReactNode } from "react";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";

/**
 * Help & Guide — an in-app user guide: quick start, the workspace map, the AI
 * companions, story intelligence, import/export, and the keyboard shortcuts.
 * Static content (no API); reachable from the left nav and the ⌘K palette.
 * Keep it accurate to the shipped app — every shortcut/feature here is real.
 */

const panelBox: CSSProperties = {
  position: "relative", width: "100%", height: "100%",
  background: "linear-gradient(180deg,var(--panel),var(--base))", border: "1px solid var(--line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)", overflow: "hidden", display: "flex", flexDirection: "column",
};

// ── Keyboard shortcuts (verified against the app) ──────────────────────────
const SHORTCUTS: [string, string][] = [
  ["⌘K  /  Ctrl+K", "Command palette — jump to any section, open an AI tool, or toggle Focus"],
  ["↑ ↓ · Enter · Esc", "In the palette: move · run the highlighted command · close"],
  ["⌘S  /  Ctrl+S", "Save now in the Manuscript (scenes also autosave as you type)"],
  ["Enter", "Send your message to Billy   (Shift+Enter = new line)"],
  ["⌘/Ctrl + Enter", "Apply an AI edit in the Controlled-Apply diff   (Esc = cancel)"],
  ["Enter  /  Esc", "Confirm / cancel an inline rename or field (Outline, Projects, PSYKE, Notes)"],
  ["Esc", "Leave Focus mode"],
];

// ── Guide sections ─────────────────────────────────────────────────────────
const GUIDE: { title: string; items: [string, string][] }[] = [
  { title: "① Get started", items: [
    ["Projects", "Create a project — pick a writing mode (novel · screenplay · graphic novel · stage) — or open one. You can also ⇩ Import Whiteboard (.json) or ⇩ Import Project (.lfbundle)."],
    ["AI Settings", "Point Studio at your AI model — a local server (LM Studio / Ollama) or a cloud provider. This powers Billy, Logos, Quantum and ✨ AI Generate."],
    ["Manuscript", "Write. Scenes autosave; formatting is live as you type (Fountain for screenplays). ＋ SCENE adds one; FOCUS hides everything but the page."],
  ] },
  { title: "② The workspace", items: [
    ["Left rail", "Every section, grouped: Plan · Structure · Analytics · Bible · Export. Click to switch — or press ⌘K and type where you want to go."],
    ["AI dock (right)", "Your AI companions, available in any section. Drag its left edge to resize (340–900px); click › to collapse it to a strip, ‹ AI to reopen."],
    ["FOCUS / COCKPIT", "Top-right toggle: FOCUS is distraction-free (just the page — Esc to exit); COCKPIT shows the full workstation."],
  ] },
  { title: "③ AI companions (right dock)", items: [
    ["◇ Billy", "Project-aware chat — he reads your scenes, outline and bible. Ask a question, then apply his suggestion straight to the active scene."],
    ["❖ Logos", "Targeted transforms — Rewrite / Expand / Compress / Improve Dialogue, plus analyzers. Pull in a selection, run it, then apply the result."],
    ["ψ Quantum", "Enter a premise → it fans out branching possibilities in superposition; inspect a branch and materialize it as a new scene."],
    ["☯ Counterpart", "A devil's-advocate second opinion that pressure-tests your draft."],
    ["⛭ Extract", "Reads your prose and proposes structured bible / plot data you can review and add."],
  ] },
  { title: "④ Plan & structure", items: [
    ["Outline", "Acts → Chapters → Scenes. Build it by hand (＋ ACT), or ✨ AI GENERATE a full outline. The ✨ on any act or chapter generates one level deeper under it."],
    ["PSYKE bible", "Characters, places, objects, lore and themes — each with the WANT · NEED · LIE · WOUND psychology and role."],
    ["Timeline · Canvas Plot · Story Grid", "See the same story as a timeline, plot lanes, or a scene grid."],
  ] },
  { title: "⑤ Story intelligence", items: [
    ["Dashboard · Health", "A live read on structure, characters, arc cover and scene density."],
    ["Pacing · Balance · Continuity", "Tension flow across scenes, cast balance, and continuity checks."],
    ["Decision Radar", "Ranked, advisory signals — unpaid setups, drifting acts, promotable motifs — each links to the section to fix it. Nothing changes without you."],
    ["Review · Adapt", "A format-aware readiness dashboard, plus adaptive-mode suggestions."],
  ] },
  { title: "⑥ Voice, import & export", items: [
    ["Voice — Dexter's Room", "Dictate: local GPU transcription (faster-whisper) turns speech into text you can commit to a scene."],
    ["Import", "From Projects: bring a Free Whiteboard draft (.json) or a whole project bundle (.lfbundle — manuscript + bible + outline) into a new Pro project."],
    ["Export", "Fountain / PDF / FDX / DOCX from the Export panel."],
  ] },
];

const sectionTitle = (children: ReactNode) => (
  <div style={{ fontFamily: "'Chakra Petch',sans-serif", fontWeight: 600, fontSize: 12, letterSpacing: ".1em", color: "var(--accent)", margin: "22px 0 10px" }}>{children}</div>
);

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div style={{ display: "flex", gap: 12, padding: "7px 0", borderTop: "1px solid var(--tint2)", alignItems: "baseline" }}>
      <span style={{ flex: "0 0 168px", fontSize: 10.5, color: "var(--strong)", letterSpacing: ".02em" }}>{k}</span>
      <span style={{ flex: 1, fontSize: 11, color: "var(--txt2)", lineHeight: 1.5 }}>{v}</span>
    </div>
  );
}

function Kbd({ children }: { children: ReactNode }) {
  return <span style={{ flex: "0 0 152px", fontFamily: "'Chakra Petch',sans-serif", fontSize: 10.5, color: "var(--strong)", background: "rgba(76,194,255,.08)", border: "1px solid var(--line-cy,#2b6f8f)", borderRadius: 3, padding: "3px 7px", letterSpacing: ".03em", textAlign: "center" }}>{children}</span>;
}

export function HelpPanel(props: PanelProps) {
  return (
    <PanelShell {...props}>
      <div data-screen-label="Help & Guide" style={panelBox}>
        <Corners />
        <div style={{ height: 42, flex: "none", display: "flex", alignItems: "center", gap: 10, padding: "0 16px", borderBottom: "1px solid var(--line)" }}>
          <span style={{ fontFamily: "'Chakra Petch',sans-serif", fontWeight: 600, fontSize: 13, letterSpacing: ".14em", color: "var(--strong)" }}>GUIDE</span>
          <span style={{ fontSize: 9, color: "var(--txt3)", letterSpacing: ".12em" }}>QUICK START · WORKSPACE · SHORTCUTS</span>
        </div>

        <div style={{ flex: 1, overflowY: "auto", padding: "8px 22px 30px" }}>
          <div style={{ maxWidth: 760 }}>
            <p style={{ fontSize: 12, color: "var(--txt2)", lineHeight: 1.6, marginTop: 16 }}>
              <span style={{ color: "var(--strong)", fontWeight: 600 }}>LogosForge Studio</span> is a complete writing workstation: a manuscript editor
              wrapped in story intelligence and a set of always-on AI companions. Everything is local-first — your work stays on your machine, and the
              AI runs against the model you choose in <span style={{ color: "var(--accent)" }}>AI Settings</span>.
            </p>

            {/* keyboard shortcuts — front and centre */}
            {sectionTitle("⌨  Keyboard shortcuts")}
            <div style={{ border: "1px solid var(--line2)", background: "var(--tint)", padding: "4px 12px 8px" }}>
              {SHORTCUTS.map(([k, v]) => (
                <div key={k} style={{ display: "flex", gap: 12, padding: "7px 0", borderTop: "1px solid var(--tint2)", alignItems: "center" }}>
                  <Kbd>{k}</Kbd>
                  <span style={{ flex: 1, fontSize: 11, color: "var(--txt2)", lineHeight: 1.5 }}>{v}</span>
                </div>
              ))}
            </div>

            {GUIDE.map((sec) => (
              <div key={sec.title}>
                {sectionTitle(sec.title)}
                <div>{sec.items.map(([k, v]) => <Row key={k} k={k} v={v} />)}</div>
              </div>
            ))}

            <div style={{ marginTop: 26, fontSize: 10, color: "var(--txt3)", letterSpacing: ".04em", lineHeight: 1.6, borderTop: "1px solid var(--line)", paddingTop: 12 }}>
              Tip: press <span style={{ color: "var(--accent)" }}>⌘K</span> (or Ctrl+K) anywhere and start typing a section name — it's the fastest way around the app.
            </div>
          </div>
        </div>
      </div>
    </PanelShell>
  );
}
