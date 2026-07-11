import type { CSSProperties, ReactNode } from "react";
import type { AdaptDTO, ReviewReportDTO, ReviewRowDTO, FormatReviewDTO } from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useAdapt, useReview, useFormatReview } from "../../hooks";
import { useNavigate, useStudio } from "../../adapters/StudioProvider";

/**
 * Adapt (adaptive-AI mode + suggestions) and the Screenplay Review dashboard —
 * both read-only lenses over the core's adaptive_mode / mode_suggestions and
 * screenplay_review engines, exposed via the /adapt and /review endpoints.
 */

const panelBox: CSSProperties = {
  position: "relative", width: "100%", height: "100%",
  background: "linear-gradient(180deg,var(--panel),var(--base))", border: "1px solid var(--line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)", overflow: "hidden", display: "flex", flexDirection: "column",
};
const headCss: CSSProperties = { flex: "none", height: 40, display: "flex", alignItems: "center", gap: 10, padding: "0 16px", borderBottom: "1px solid var(--line)" };
const titleCss: CSSProperties = { fontFamily: "'Chakra Petch',sans-serif", fontWeight: 600, fontSize: 12.5, letterSpacing: ".14em", color: "var(--strong)" };
const centered = (t: string, c = "var(--txt3)"): ReactNode => <div style={{ padding: "44px 0", textAlign: "center", fontSize: 11, color: c }}>{t}</div>;

const sevColor = (s: string): string => {
  const v = (s || "").toLowerCase();
  if (/(block|error|critical|missing)/.test(v)) return "var(--blocking)";
  if (/(warn|needs|sparse)/.test(v)) return "var(--amber)";
  if (/(ok|ready|balanced|written|good)/.test(v)) return "var(--green)";
  return "var(--txt3)";
};
const chip = (text: string, color: string): ReactNode => (
  <span style={{ fontSize: 8, letterSpacing: ".14em", textTransform: "uppercase", color, border: `1px solid ${color}`, borderRadius: 2, padding: "2px 7px", whiteSpace: "nowrap" }}>{text}</span>
);

/* ======================= ADAPT ======================= */

const CAT_COLOR: Record<string, string> = { structure: "var(--accent)", balance: "var(--amber)", refinement: "var(--cyan)" };

export function AdaptView(props: PanelProps) {
  const adapt = useAdapt();
  const d: AdaptDTO | undefined = adapt.data;
  return (
    <PanelShell {...props}>
      <div data-screen-label="Adapt" style={panelBox}>
        <Corners />
        <div style={headCss}>
          <span style={{ width: 6, height: 6, background: "var(--amber)", boxShadow: "0 0 6px var(--amber)" }} />
          <span style={titleCss}>ADAPTIVE MODE</span>
        </div>
        <div style={{ flex: 1, overflowY: "auto", padding: 16 }}>
          {adapt.loading && !d ? centered("Loading…")
            : adapt.error ? centered(adapt.error, "var(--blocking)")
            : !d ? centered("No project.")
            : (
              <>
                <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
                  <div style={{ fontFamily: "'Chakra Petch'", fontSize: 26, color: "var(--amber-b,var(--amber))", letterSpacing: ".06em" }}>{d.mode}</div>
                  {chip(`STAGE · ${d.stage}`, "var(--accent)")}
                  {chip(`HEALTH · ${d.health}`, sevColor(d.health))}
                </div>
                {d.description && <div style={{ fontSize: 11, color: "var(--txt2)", lineHeight: 1.6, marginBottom: 18, borderLeft: "2px solid var(--line2)", paddingLeft: 11 }}>{d.description}</div>}
                <div style={{ fontSize: 8, letterSpacing: ".2em", color: "var(--txt3)", marginBottom: 10 }}>SUGGESTIONS · {d.suggestions.length}</div>
                {d.suggestions.length === 0
                  ? <div style={{ fontSize: 10, color: "var(--txt3)" }}>No suggestions — the story state looks balanced.</div>
                  : <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
                      {d.suggestions.map((s, i) => (
                        <div key={i} style={{ display: "flex", gap: 10, border: "1px solid var(--line2)", background: "var(--tint)", padding: "10px 12px" }}>
                          <span style={{ flex: "none", marginTop: 2 }}>{chip(s.category, CAT_COLOR[s.category] || "var(--txt3)")}</span>
                          <span style={{ fontSize: 10.5, color: "var(--txt)", lineHeight: 1.5 }}>{s.text}</span>
                        </div>
                      ))}
                    </div>}
              </>
            )}
        </div>
      </div>
    </PanelShell>
  );
}

/* ======================= SCREENPLAY REVIEW ======================= */

function Metric({ label, value, accent }: { label: string; value: ReactNode; accent?: string }) {
  return (
    <div style={{ border: "1px solid var(--line2)", background: "var(--tint)", padding: "9px 11px" }}>
      <div style={{ fontFamily: "'Chakra Petch'", fontSize: 19, color: accent ?? "var(--strong)", lineHeight: 1 }}>{value}</div>
      <div style={{ fontSize: 7.5, letterSpacing: ".14em", color: "var(--txt3)", marginTop: 5 }}>{label}</div>
    </div>
  );
}

export function ReviewDashboard(props: PanelProps) {
  const { writingMode } = useStudio();
  const isScreenplay = String(writingMode ?? "") === "screenplay";
  const review = useReview();
  const fmt = useFormatReview();
  const navigate = useNavigate();
  const d: ReviewReportDTO | undefined = review.data;
  // Non-screenplay formats (graphic novel / stage / series) get the /format-review
  // checks list instead of the scene-readiness report.
  if (!isScreenplay) return <FormatReviewView props={props} res={fmt} />;
  return (
    <PanelShell {...props}>
      <div data-screen-label="Screenplay Review" style={panelBox}>
        <Corners />
        <div style={headCss}>
          <span style={{ width: 6, height: 6, background: "var(--accent)", boxShadow: "0 0 6px var(--accent)" }} />
          <span style={titleCss}>REVIEW</span>
          {d && chip(d.export_ready ? "EXPORT READY" : "NOT READY", d.export_ready ? "var(--green)" : "var(--amber)")}
        </div>
        <div style={{ flex: 1, overflowY: "auto", padding: 14 }}>
          {review.loading && !d ? centered("Loading…")
            : review.error ? centered(review.error, "var(--blocking)")
            : !d ? centered("No project.")
            : d.total_scenes === 0 ? centered("No scenes yet — the review reads your manuscript scenes.")
            : (
              <>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 9, marginBottom: 16 }}>
                  <Metric label="SCENES" value={d.total_scenes} />
                  <Metric label="WRITTEN" value={d.written} accent="var(--green)" />
                  <Metric label="PLANNED" value={d.planned} accent="var(--amber)" />
                  <Metric label="NEEDS WORK" value={d.needs_work} accent={d.needs_work ? "var(--blocking)" : "var(--strong)"} />
                  <Metric label="HEALTH ⚠" value={d.with_health_warnings} />
                  <Metric label="CONTINUITY ⚠" value={d.with_continuity_warnings} />
                  <Metric label="TIMELINE" value={d.timeline_linked} />
                  <Metric label="PSYKE LINKS" value={d.with_psyke_links} />
                </div>
                <div style={{ fontSize: 8, letterSpacing: ".2em", color: "var(--txt3)", marginBottom: 9 }}>SCENES · {d.rows.length}</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                  {d.rows.map((r: ReviewRowDTO) => (
                    <button key={r.scene_id} type="button" onClick={() => navigate("Manuscript", { sceneId: r.scene_id })} title="Open in the Manuscript"
                      style={{ display: "flex", alignItems: "center", gap: 9, textAlign: "left", border: "1px solid var(--line2)", borderLeft: `2px solid ${sevColor(r.overall_status)}`, background: "var(--tint)", padding: "7px 10px", cursor: "pointer", font: "inherit" }}>
                      <span style={{ fontFamily: "'Chakra Petch'", fontSize: 10, color: "var(--txt3)", width: 26, flex: "none" }}>{r.number || "—"}</span>
                      <span style={{ flex: 1, minWidth: 0, fontSize: 11, color: "var(--txt)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.title || "Untitled"}</span>
                      <span style={{ fontSize: 8.5, color: "var(--txt3)", flex: "none" }}>{r.word_count}w</span>
                      {r.has_rewrite_candidate && <span style={{ flex: "none" }}>{chip("rewrite", "var(--violet)")}</span>}
                      {r.next_action && <span style={{ fontSize: 8.5, color: "var(--txt2)", flex: "none", maxWidth: 200, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.next_action}</span>}
                      <span style={{ flex: "none" }}>{chip(r.overall_status || "ok", sevColor(r.overall_status))}</span>
                    </button>
                  ))}
                </div>
              </>
            )}
        </div>
      </div>
    </PanelShell>
  );
}

/* ---- format-specific review (graphic novel / stage / series) — checks list ---- */

const FMT_LABEL: Record<string, string> = { graphic_novel: "GRAPHIC NOVEL", stage_script: "STAGE SCRIPT", series: "SERIES" };

function FormatReviewView({ props, res }: { props: PanelProps; res: { data: FormatReviewDTO | undefined; loading: boolean; error: string | null } }) {
  const d = res.data;
  const warnings = d ? d.checks.filter((c) => (c.severity || "").toLowerCase() === "warning").length : 0;
  return (
    <PanelShell {...props}>
      <div data-screen-label="Format Review" style={panelBox}>
        <Corners />
        <div style={headCss}>
          <span style={{ width: 6, height: 6, background: "var(--accent)", boxShadow: "0 0 6px var(--accent)" }} />
          <span style={titleCss}>REVIEW</span>
          {d && chip(FMT_LABEL[d.format] || d.format || "FORMAT", "var(--accent)")}
          {d && chip(warnings ? `${warnings} WARNING${warnings === 1 ? "" : "S"}` : "CLEAN", warnings ? "var(--amber)" : "var(--green)")}
        </div>
        <div style={{ flex: 1, overflowY: "auto", padding: 14 }}>
          {res.loading && !d ? centered("Loading…")
            : res.error ? centered(res.error, "var(--blocking)")
            : !d ? centered("No project.")
            : d.checks.length === 0 ? centered("No review findings — the format structure looks sound.")
            : (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {[...d.checks].sort((a, b) => sevRank(b.severity) - sevRank(a.severity)).map((c, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 9, border: "1px solid var(--line2)", borderLeft: `2px solid ${sevColor(c.severity)}`, background: "var(--tint)", padding: "8px 11px" }}>
                    <span style={{ flex: "none", marginTop: 1 }}>{chip(c.check_type, sevColor(c.severity))}</span>
                    <span style={{ fontSize: 10.5, color: "var(--txt)", lineHeight: 1.5 }}>{c.message}</span>
                  </div>
                ))}
              </div>
            )}
        </div>
      </div>
    </PanelShell>
  );
}
const sevRank = (s: string) => ({ warning: 2, info: 1 }[(s || "").toLowerCase()] ?? 0);
