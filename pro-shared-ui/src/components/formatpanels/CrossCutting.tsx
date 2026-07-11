import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import type { ProjectDTO, AiBehaviorDTO } from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useProjects, useSettings } from "../../hooks";
import { useStudio } from "../../adapters/StudioProvider";

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
      background="var(--tint)"
      bandColor={band}
      title={p.title}
      titleColor="var(--strong)"
      meta={meta}
      sparkline={sparkline}
      chip={<span style={{ fontSize: 7, color: "var(--txt3)", border: "1px solid var(--line2)", padding: "1px 5px" }}>LOCAL</span>}
      status={<span style={{ fontSize: 7, color: "var(--txt3)" }}>—</span>}
    />
  );
}

/** A small on/off switch wired to a settings boolean. */
function Toggle({ on, label, onClick }: { on: boolean; label: ReactNode; onClick: () => void }) {
  return (
    <div onClick={onClick} style={{ display: "flex", alignItems: "center", gap: 9, cursor: "pointer", padding: "5px 0" }}>
      <span style={{ position: "relative", width: 28, height: 15, borderRadius: 8, background: on ? "var(--accent)" : "var(--line2)", flex: "none", transition: "background .15s" }}>
        <span style={{ position: "absolute", top: 2, left: on ? 15 : 2, width: 11, height: 11, borderRadius: "50%", background: "var(--strong)", transition: "left .15s" }} />
      </span>
      <span style={{ fontSize: 10, color: on ? "var(--strong)" : "var(--txt2)" }}>{label}</span>
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

  // AI behaviour (global): chat grounding sources + connector governance. These
  // are REAL controls the core honours (build_chat_context + connector execute),
  // not the former hardcoded chips.
  const { api, projectId } = useStudio();
  const [behavior, setBehavior] = useState<AiBehaviorDTO | null>(null);
  useEffect(() => {
    if (projectId == null) { setBehavior(null); return; }
    let alive = true;
    api.getAiBehavior(projectId).then((v) => { if (alive) setBehavior(v); }).catch(() => { if (alive) setBehavior(null); });
    return () => { alive = false; };
  }, [api, projectId]);
  const setB = (p: Partial<AiBehaviorDTO>) => {
    if (projectId == null) return;
    setBehavior((cur) => (cur ? { ...cur, ...p } : cur));   // optimistic
    api.patchAiBehavior(projectId, p).then((v) => setBehavior(v)).catch(() => {});
  };

  // Grammar / spelling / style check (stateless rule-based; the same core checker
  // the Qt manuscript editor uses). Auto-detects language.
  const [gramText, setGramText] = useState("");
  const [gramIssues, setGramIssues] = useState<{ lang: string; items: { issue_type: string; message: string }[] } | null>(null);
  const [gramBusy, setGramBusy] = useState(false);
  const runGrammar = () => {
    if (projectId == null || !gramText.trim() || gramBusy) return;
    setGramBusy(true);
    api.grammarCheck(projectId, { text: gramText })
      .then((r) => setGramIssues({ lang: r.language, items: r.issues.map((i) => ({ issue_type: i.issue_type, message: i.message })) }))
      .catch(() => setGramIssues(null))
      .finally(() => setGramBusy(false));
  };

  return (
    <PanelShell {...props} style={ACCENT}>
      <div data-screen-label="Cross-cutting" style={panelBox}>
        <Corners />

        {/* launchpad */}
        <div style={{ flex: "none", padding: "13px 16px", borderBottom: "1px solid var(--line)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 11 }}>
            <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".1em", color: "var(--strong)" }}>PROJECT LAUNCHPAD</span>
            <span style={{ fontSize: 8, color: "var(--txt3)" }}>{count} PROJECTS</span>
            <div style={{ flex: 1 }} />
            <span style={{ fontSize: 8, color: "var(--on-accent)", background: "var(--accent)", padding: "3px 9px", fontWeight: 600 }}>＋ NEW PROJECT</span>
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
                  <span style={{ width: 36, textAlign: "center", color: "var(--strong)" }}>{opacity}%</span>
                  <span onClick={() => setOpacity(opacity + 4)} style={{ cursor: "pointer", width: 18, height: 18, display: "grid", placeItems: "center", border: "1px solid var(--line2)", color: "var(--txt2)" }}>＋</span>
                </div>
                <div style={{ display: "flex", gap: 18, fontSize: 9, color: "var(--txt3)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}><span style={{ width: 16, height: 16, border: "1px solid var(--line2)", background: sStr("chat_bg_color", "#3a2a55") }} />background</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}><span style={{ width: 16, height: 16, border: "1px solid var(--line2)", background: sStr("chat_text_color", "#ffb000") }} />text</div>
                </div>
              </>
            )}
          </div>

          <div style={{ width: 380, flex: "none", padding: "12px 14px", background: "var(--panel2)", overflowY: "auto" }}>
            <div style={{ fontSize: 7.5, letterSpacing: ".16em", color: "var(--txt3)", marginBottom: 4 }}>WHAT THE AI SEES · chat grounding</div>
            {behavior == null ? (
              <div style={{ fontSize: 9, color: "var(--txt3)", marginBottom: 12 }}>{projectId == null ? "Open a project." : "Loading…"}</div>
            ) : (
              <div style={{ marginBottom: 12 }}>
                <Toggle on={behavior.ctx_outline} label="Outline" onClick={() => setB({ ctx_outline: !behavior.ctx_outline })} />
                <Toggle on={behavior.ctx_bible} label="Story bible (PSYKE)" onClick={() => setB({ ctx_bible: !behavior.ctx_bible })} />
                <Toggle on={behavior.ctx_memory} label="Story memory" onClick={() => setB({ ctx_memory: !behavior.ctx_memory })} />
                <div style={{ fontSize: 7, color: "var(--txt3)", marginTop: 3, lineHeight: 1.5 }}>What Billy folds into its prompt for this manuscript. Off = that source is left out.</div>
              </div>
            )}
            <div style={{ fontSize: 7.5, letterSpacing: ".16em", color: "var(--txt3)", marginBottom: 4 }}>CONNECTOR PERMISSIONS · AI actions</div>
            {behavior == null ? (
              <div style={{ fontSize: 9, color: "var(--txt3)" }}>{projectId == null ? "Open a project." : "Loading…"}</div>
            ) : (
              <>
                <Toggle on={behavior.connector_enabled} label="Connector enabled" onClick={() => setB({ connector_enabled: !behavior.connector_enabled })} />
                <Toggle on={behavior.connector_allow_writes} label="Allow write actions" onClick={() => setB({ connector_allow_writes: !behavior.connector_allow_writes })} />
                <Toggle on={behavior.connector_confirm_writes} label="Confirm before writes" onClick={() => setB({ connector_confirm_writes: !behavior.connector_confirm_writes })} />
                <div style={{ fontSize: 7, color: "var(--txt3)", marginTop: 4, lineHeight: 1.5, letterSpacing: ".04em" }}>
                  Enforced by the core: with the connector off, the AI can't run actions; write actions need "Allow write actions".
                  {behavior.connector_disabled_actions.length > 0 && ` · ${behavior.connector_disabled_actions.length} action(s) disabled`}
                </div>
              </>
            )}

            <div style={{ fontSize: 7.5, letterSpacing: ".16em", color: "var(--txt3)", margin: "16px 0 6px" }}>GRAMMAR · spelling / style check</div>
            <textarea
              value={gramText}
              onChange={(e) => setGramText(e.target.value)}
              placeholder="Paste a passage to check…"
              rows={3}
              disabled={projectId == null}
              style={{ width: "100%", boxSizing: "border-box", resize: "vertical", background: "var(--tint)", border: "1px solid var(--line2)", color: "var(--txt)", fontFamily: "inherit", fontSize: 10, padding: "6px 8px", outline: "none" }}
            />
            <div style={{ display: "flex", alignItems: "center", gap: 9, marginTop: 6 }}>
              <button type="button" onClick={runGrammar} disabled={projectId == null || !gramText.trim() || gramBusy}
                style={{ fontSize: 8.5, letterSpacing: ".08em", color: "var(--on-accent)", background: "var(--accent)", border: "none", padding: "4px 11px", fontWeight: 600, cursor: gramBusy ? "default" : "pointer", opacity: projectId == null || !gramText.trim() ? 0.4 : 1 }}>
                {gramBusy ? "CHECKING…" : "CHECK"}
              </button>
              {gramIssues && <span style={{ fontSize: 8, color: gramIssues.items.length ? "var(--amber-b,#ffb454)" : "var(--green)", letterSpacing: ".06em" }}>{gramIssues.items.length === 0 ? "✓ no issues" : `${gramIssues.items.length} issue(s)`} · {gramIssues.lang}</span>}
            </div>
            {gramIssues && gramIssues.items.length > 0 && (
              <div style={{ marginTop: 7, display: "flex", flexDirection: "column", gap: 4, maxHeight: 130, overflowY: "auto" }}>
                {gramIssues.items.slice(0, 40).map((it, i) => (
                  <div key={i} style={{ fontSize: 8.5, color: "var(--txt2)", lineHeight: 1.4 }}>
                    <span style={{ color: it.issue_type === "spelling" ? "var(--crimson)" : it.issue_type === "grammar" ? "var(--amber-b,#ffb454)" : "var(--txt3)", textTransform: "uppercase", fontSize: 7, letterSpacing: ".1em" }}>{it.issue_type}</span>{" "}{it.message}
                  </div>
                ))}
              </div>
            )}
            <div style={{ fontSize: 7, color: "var(--txt3)", marginTop: 6, lineHeight: 1.5 }}>Rule-based, offline, auto-detects language (en/es/fr/de/it). Inline highlighting in the editor is a later step.</div>
          </div>
        </div>
      </div>
    </PanelShell>
  );
}
