import type { CSSProperties, ReactNode } from "react";
import type { ProjectDTO } from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useProjects, useSettings } from "../../hooks";

const panelBox: CSSProperties = {
  position: "relative",
  width: "100%",
  height: "100%",
  background: "linear-gradient(180deg,#080a0f,#05070b)",
  border: "1px solid var(--line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)",
  overflow: "hidden",
  display: "flex",
  flexDirection: "column",
};

const ACCENT = { ["--accent"]: "#4cc2ff" } as CSSProperties;

/** Top accent-band color per writing/format mode. */
const MODE_COLOR: Record<string, string> = {
  novel: "#c8a96a",
  screenplay: "#4cc2ff",
  graphic_novel: "#ff7ac6",
  stage_script: "#ffb454",
  series: "#62d99a",
};

/** Title-case a format_mode token (e.g. `graphic_novel` → `Graphic Novel`). */
const titleCase = (s: string) =>
  s
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");

const message = (text: string) => (
  <div style={{ gridColumn: "1 / -1", padding: "26px 0", textAlign: "center", fontSize: 11, color: "var(--txt3)", letterSpacing: ".04em" }}>{text}</div>
);

/** A project card in the launchpad grid. */
function ProjectCard({
  border,
  background,
  bandColor,
  title,
  titleColor,
  meta,
  sparkline,
  chip,
  status,
}: {
  border: string;
  background: string;
  bandColor: string;
  title: string;
  titleColor: string;
  meta: string;
  sparkline: ReactNode;
  chip: ReactNode;
  status: ReactNode;
}) {
  return (
    <div style={{ border, background, padding: 11, position: "relative" }}>
      <div style={{ height: 3, background: bandColor, margin: "-11px -11px 9px" }} />
      <div style={{ fontFamily: "'Chakra Petch'", fontSize: 14, color: titleColor }}>{title}</div>
      <div style={{ fontSize: 8, color: "var(--txt3)", margin: "3px 0 8px" }}>{meta}</div>
      {sparkline}
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 7 }}>
        {chip}
        {status}
      </div>
    </div>
  );
}

/** A generic static sparkline (no per-project metric in the DTO). */
const sparkline = (
  <svg viewBox="0 0 120 18" style={{ width: "100%", height: 18 }}>
    <polyline points="0,14 20,10 40,12 60,6 80,9 100,4 120,8" fill="none" stroke="var(--accent)" strokeWidth="1.2" />
  </svg>
);

/** One launchpad card from a project DTO. */
function projectCard(p: ProjectDTO) {
  const band = MODE_COLOR[p.format_mode] ?? "var(--cyan)";
  const meta = `${titleCase(p.format_mode)} · ${titleCase(p.narrative_engine)}`;
  return (
    <ProjectCard
      key={p.id}
      border="1px solid var(--line2)"
      background="rgba(11,14,21,.4)"
      bandColor={band}
      title={p.title}
      titleColor="#fff"
      meta={meta}
      sparkline={sparkline}
      chip={<span style={{ fontSize: 7, color: "var(--txt3)", border: "1px solid var(--line2)", padding: "1px 5px" }}>LOCAL</span>}
      status={<span style={{ fontSize: 7, color: "var(--txt3)" }}>—</span>}
    />
  );
}

/** A context chip in the "WHAT THE AI SEES" board. */
function ContextChip({ text, color, border }: { text: string; color: string; border: string }) {
  return <span style={{ fontSize: 8, color, border, padding: "2px 7px" }}>{text}</span>;
}

/** A label row with a checkbox box in the connector permissions list. */
function PermRow({ box, children }: { box: ReactNode; children: ReactNode }) {
  return (
    <label style={{ display: "flex", alignItems: "center", gap: 7 }}>
      {box}
      {children}
    </label>
  );
}

/** A small on/off switch wired to a settings boolean. */
function Toggle({ on, label, onClick }: { on: boolean; label: ReactNode; onClick: () => void }) {
  return (
    <div onClick={onClick} style={{ display: "flex", alignItems: "center", gap: 9, cursor: "pointer", padding: "5px 0" }}>
      <span style={{ position: "relative", width: 28, height: 15, borderRadius: 8, background: on ? "var(--accent)" : "var(--line2)", flex: "none", transition: "background .15s" }}>
        <span style={{ position: "absolute", top: 2, left: on ? 15 : 2, width: 11, height: 11, borderRadius: "50%", background: "#fff", transition: "left .15s" }} />
      </span>
      <span style={{ fontSize: 10, color: on ? "#fff" : "var(--txt2)" }}>{label}</span>
    </div>
  );
}

export function CrossCutting(props: PanelProps) {
  const { data: projects, loading, error } = useProjects();
  const count = projects?.length ?? 0;

  // project settings (getSettings) + write path (patchSettings)
  const { data: settings, loading: sLoading, error: sError, patch, saving } = useSettings();
  const sBool = (k: string) => settings?.[k] === true;
  const sNum = (k: string, d: number) => (typeof settings?.[k] === "number" ? (settings[k] as number) : d);
  const sStr = (k: string, d: string) => (typeof settings?.[k] === "string" ? (settings[k] as string) : d);
  const opacity = sNum("chat_opacity", 100);
  const lang = sStr("writing_language_code", sStr("current_language", "—")).toUpperCase();
  const setOpacity = (v: number) => patch({ chat_opacity: Math.max(0, Math.min(100, v)) });

  return (
    <PanelShell {...props} style={ACCENT}>
      <div data-screen-label="Cross-cutting" style={panelBox}>
        <Corners />

        {/* launchpad */}
        <div style={{ flex: "none", padding: "13px 16px", borderBottom: "1px solid var(--line)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 11 }}>
            <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".1em", color: "#fff" }}>PROJECT LAUNCHPAD</span>
            <span style={{ fontSize: 8, color: "var(--txt3)" }}>{count} PROJECTS</span>
            <div style={{ flex: 1 }} />
            <span style={{ fontSize: 8, color: "#04060a", background: "var(--accent)", padding: "3px 9px", fontWeight: 600 }}>＋ NEW PROJECT</span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 10 }}>
            {loading
              ? message("Loading projects…")
              : error
                ? message(`Couldn't load projects — ${error}`)
                : count === 0
                  ? message("No projects yet — create one with ＋ NEW PROJECT")
                  : projects!.map((p) => projectCard(p))}
            <div style={{ border: "1px dashed var(--line2)", background: "transparent", padding: 11, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 6, color: "var(--txt3)" }}>
              <span style={{ fontSize: 18 }}>＋</span>
              <span style={{ fontSize: 8, letterSpacing: ".1em" }}>OPEN · IMPORT</span>
            </div>
          </div>
        </div>

        {/* settings */}
        <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
          <div style={{ flex: 1, borderRight: "1px solid var(--line2)", padding: "12px 16px", overflowY: "auto" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 12 }}>
              <span style={{ fontSize: 9, letterSpacing: ".14em", color: "var(--txt2)", fontFamily: "'Chakra Petch'" }}>SETTINGS</span>
              {saving ? (
                <span style={{ fontSize: 7.5, color: "var(--accent)", letterSpacing: ".1em" }}>● SAVING…</span>
              ) : settings ? (
                <span style={{ fontSize: 7.5, color: "var(--green)", letterSpacing: ".1em" }}>● SAVED</span>
              ) : null}
            </div>

            {sLoading && !settings ? (
              <div style={{ fontSize: 10, color: "var(--txt3)" }}>Loading settings…</div>
            ) : sError ? (
              <div style={{ fontSize: 10, color: "var(--blocking)" }}>Couldn't load settings — {sError}</div>
            ) : (
              <>
                <div style={{ fontSize: 7.5, letterSpacing: ".16em", color: "var(--txt3)", marginBottom: 5 }}>WRITING</div>
                <div style={{ marginBottom: 14 }}>
                  <Toggle on={sBool("focus_mode")} label="Focus mode" onClick={() => patch({ focus_mode: !sBool("focus_mode") })} />
                  <Toggle on={sBool("typewriter_mode")} label="Typewriter mode" onClick={() => patch({ typewriter_mode: !sBool("typewriter_mode") })} />
                  <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 0 2px", fontSize: 10, color: "var(--txt2)" }}>
                    <span>Language</span><span style={{ fontSize: 8, color: "var(--accent)", border: "1px solid var(--line-cy)", padding: "1px 6px" }}>{lang}</span>
                  </div>
                </div>

                <div style={{ fontSize: 7.5, letterSpacing: ".16em", color: "var(--txt3)", marginBottom: 8 }}>CHAT APPEARANCE</div>
                <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 11, fontSize: 10, color: "var(--txt2)" }}>
                  <span style={{ width: 52 }}>Opacity</span>
                  <span onClick={() => setOpacity(opacity - 4)} style={{ cursor: "pointer", width: 18, height: 18, display: "grid", placeItems: "center", border: "1px solid var(--line2)", color: "var(--txt2)" }}>−</span>
                  <span style={{ width: 36, textAlign: "center", color: "#fff" }}>{opacity}%</span>
                  <span onClick={() => setOpacity(opacity + 4)} style={{ cursor: "pointer", width: 18, height: 18, display: "grid", placeItems: "center", border: "1px solid var(--line2)", color: "var(--txt2)" }}>＋</span>
                </div>
                <div style={{ display: "flex", gap: 18, fontSize: 9, color: "var(--txt3)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}><span style={{ width: 16, height: 16, border: "1px solid var(--line2)", background: sStr("chat_bg_color", "#3a2a55") }} />background</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}><span style={{ width: 16, height: 16, border: "1px solid var(--line2)", background: sStr("chat_text_color", "#ffb000") }} />text</div>
                </div>
              </>
            )}
          </div>

          <div style={{ width: 380, flex: "none", padding: "12px 14px", background: "#06080c", overflowY: "auto" }}>
            <div style={{ fontSize: 7.5, letterSpacing: ".16em", color: "var(--txt3)", marginBottom: 8 }}>WHAT THE AI SEES · context board</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginBottom: 11 }}>
              <ContextChip text="✓ Outline" color="var(--green)" border="1px solid rgba(98,217,154,.3)" />
              <ContextChip text="✓ Story Bible" color="var(--green)" border="1px solid rgba(98,217,154,.3)" />
              <ContextChip text="✓ Graph" color="var(--green)" border="1px solid rgba(98,217,154,.3)" />
              <ContextChip text="✓ Memory ×20" color="var(--green)" border="1px solid rgba(98,217,154,.3)" />
              <ContextChip text="✕ Health" color="var(--txt3)" border="1px solid var(--line2)" />
            </div>
            <div style={{ fontSize: 7.5, letterSpacing: ".16em", color: "var(--txt3)", marginBottom: 8 }}>CONNECTOR PERMISSIONS</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 5, fontSize: 9, color: "var(--txt2)" }}>
              <PermRow box={<span style={{ width: 10, height: 10, border: "1px solid var(--line-cy)", background: "var(--accent)" }} />}>connector enabled</PermRow>
              <PermRow box={<span style={{ width: 10, height: 10, border: "1px solid var(--line2)" }} />}>
                allow writes <span style={{ fontSize: 7, color: "var(--amber)" }}>· confirm each</span>
              </PermRow>
            </div>
            <div style={{ fontSize: 7, color: "var(--txt3)", marginTop: 10, lineHeight: 1.5, letterSpacing: ".04em" }}>17 actions · 13 reads · 4 writes · every write previews → confirms → undo</div>
          </div>
        </div>
      </div>
    </PanelShell>
  );
}
