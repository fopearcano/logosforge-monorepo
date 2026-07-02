import type { CSSProperties } from "react";
import type { ContinuityIssueDTO, ContinuityReportDTO } from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useContinuity } from "../../hooks";

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

/** Severity → row palette (blocking→red, warning→amber, suggestion→cyan, info→muted). */
const SEV: Record<string, { color: string; border: string; bg: string }> = {
  blocking: { color: "var(--blocking)", border: "rgba(255,82,96,.35)", bg: "rgba(255,82,96,.04)" },
  warning: { color: "var(--warning)", border: "var(--line2)", bg: "rgba(11,14,21,.5)" },
  suggestion: { color: "var(--cyan)", border: "var(--line2)", bg: "rgba(11,14,21,.5)" },
  info: { color: "var(--txt3)", border: "var(--line2)", bg: "rgba(11,14,21,.5)" },
};
const sevOf = (s: string) => SEV[s] ?? SEV.info!;

/** Confidence → short badge label. */
const CONF: Record<string, string> = { confirmed: "CONFIRMED", likely: "LIKELY", possible: "POSSIBLE", unknown: "UNKNOWN" };
const confOf = (c: string) => CONF[c] ?? c.toUpperCase();

/** Dimension swatch colors for the breakdown legend / radial. */
const DIM_COLORS = ["var(--blocking)", "var(--warning)", "var(--cyan)", "var(--green)", "var(--accent)", "var(--txt2)"];

function GroupHead({ label, counts, mt = 0 }: { label: string; counts: { n: string; color: string }[]; mt?: number }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 9, margin: `${mt}px 0 8px` }}>
      <span style={{ fontSize: 9, letterSpacing: ".14em", color: "var(--txt2)" }}>{label}</span>
      {counts.map((c, i) => <span key={i} style={{ fontSize: 7.5, color: c.color }}>{c.n}</span>)}
      <span style={{ flex: 1, height: 1, background: "var(--line2)" }} />
    </div>
  );
}

function IssueCard({ issue }: { issue: ContinuityIssueDTO }) {
  const sev = sevOf(issue.severity);
  const blocking = issue.severity === "blocking";
  return (
    <div style={{ border: `1px solid ${sev.border}`, background: sev.bg, padding: "9px 11px", marginBottom: 7 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
        {blocking
          ? <span style={{ width: 9, height: 9, background: sev.color, display: "inline-grid", placeItems: "center", color: "#fff", fontSize: 6 }}>!</span>
          : <span style={{ width: 8, height: 8, transform: "rotate(45deg)", background: sev.color }} />}
        <span style={{ fontSize: 8, letterSpacing: ".12em", color: sev.color }}>{issue.severity.toUpperCase()} · {issue.issue_type}</span>
        <span style={{ fontSize: 7.5, color: "var(--txt3)" }}>conf {confOf(issue.confidence)}</span>
      </div>
      <div style={{ fontSize: 10.5, color: blocking ? "#fff" : "var(--txt)", lineHeight: 1.4, marginBottom: issue.explanation ? 4 : 6 }}>{issue.title}</div>
      {issue.explanation
        ? <div style={{ fontSize: 9, color: "var(--txt2)", lineHeight: 1.45, marginBottom: 6 }}>{issue.explanation}</div>
        : null}
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
        {issue.related_scene_ids.map((id) => (
          <span key={id} style={{ fontSize: 7.5, color: "var(--cyan)", border: "1px solid var(--line2)", padding: "1px 5px" }}>SC.{id}</span>
        ))}
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 7.5, letterSpacing: ".1em", color: "var(--txt3)" }}>{issue.status.toUpperCase()}</span>
      </div>
    </div>
  );
}

const message = (text: string) => (
  <div style={{ padding: "34px 0", textAlign: "center", fontSize: 11, color: "var(--txt3)", letterSpacing: ".04em" }}>{text}</div>
);

/** Group issues by dimension, preserving first-seen order. */
function byDimension(issues: ContinuityIssueDTO[]): { dimension: string; items: ContinuityIssueDTO[] }[] {
  const order: string[] = [];
  const map = new Map<string, ContinuityIssueDTO[]>();
  for (const it of issues) {
    let bucket = map.get(it.dimension);
    if (!bucket) {
      bucket = [];
      map.set(it.dimension, bucket);
      order.push(it.dimension);
    }
    bucket.push(it);
  }
  return order.map((dimension) => ({ dimension, items: map.get(dimension) ?? [] }));
}

/** Per-group severity tally → the chip row next to the group head. */
function groupCounts(items: ContinuityIssueDTO[]): { n: string; color: string }[] {
  const tally: Record<string, number> = {};
  for (const it of items) tally[it.severity] = (tally[it.severity] ?? 0) + 1;
  const out: { n: string; color: string }[] = [];
  for (const sev of ["blocking", "warning", "suggestion", "info"]) {
    const c = tally[sev] ?? 0;
    if (c > 0) out.push({ n: `${c} ${sev}${c > 1 ? "s" : ""}`, color: sevOf(sev).color });
  }
  return out;
}

export function ContinuityPanel(props: PanelProps) {
  const { data, loading, error } = useContinuity();
  const report: ContinuityReportDTO | undefined = data;
  const issues = report?.issues ?? [];
  const total = issues.length;
  const blockingCount = report?.blocking_count ?? 0;
  const warningCount = report?.warning_count ?? 0;
  const unavailable = report?.unavailable ?? [];

  const groups = byDimension(issues);

  // Issue-breakdown legend: count per dimension (derived from the grouping).
  const breakdown = groups.map((g, i) => ({
    dimension: g.dimension,
    count: g.items.length,
    color: DIM_COLORS[i % DIM_COLORS.length]!,
  }));
  // Radial wedges proportional to each dimension's share of total issues.
  let acc = 0;
  const stops = breakdown
    .map((b) => {
      const start = total > 0 ? (acc / total) * 100 : 0;
      acc += b.count;
      const end = total > 0 ? (acc / total) * 100 : 0;
      return `${b.color} ${start}% ${end}%`;
    })
    .join(",");
  const conic = stops ? `conic-gradient(${stops})` : "var(--line2)";

  // Most-affected scenes: frequency of each scene across all related_scene_ids.
  const sceneFreq = new Map<number, number>();
  for (const it of issues) for (const id of it.related_scene_ids) sceneFreq.set(id, (sceneFreq.get(id) ?? 0) + 1);
  const topScenes = [...sceneFreq.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10);
  const maxFreq = topScenes.reduce((m, [, c]) => Math.max(m, c), 0);

  return (
    <PanelShell {...props}>
      <div data-screen-label="Continuity Panel" style={panelBox}>
        <Corners />
        {/* issues by dimension */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", borderRight: "1px solid var(--line)", minWidth: 0 }}>
          <div style={{ height: 42, flex: "none", display: "flex", alignItems: "center", gap: 11, padding: "0 16px", borderBottom: "1px solid var(--line)" }}>
            <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".1em", color: "#fff" }}>CONTINUITY</span>
            <span style={{ fontSize: 8, color: "var(--txt3)" }}>
              SCOPE · PROJECT · {total} finding{total === 1 ? "" : "s"}
              {blockingCount > 0 ? <> · <span style={{ color: "var(--blocking)" }}>{blockingCount} blocking</span></> : null}
              {warningCount > 0 ? <> · <span style={{ color: "var(--warning)" }}>{warningCount} warning</span></> : null}
            </span>
            <div style={{ flex: 1 }} /><span style={{ fontSize: 8, color: "var(--txt3)" }}>DIMENSION ▾ · SEVERITY ▾ · STATUS ▾</span>
          </div>
          <div style={{ flex: 1, overflowY: "auto", padding: "13px 16px" }}>
            {loading
              ? message("Loading continuity report…")
              : error
                ? message(`Couldn't load continuity — ${error}`)
                : total === 0
                  ? message("No continuity issues found")
                  : groups.map((g, gi) => (
                    <div key={g.dimension}>
                      <GroupHead label={`▾ ${g.dimension.toUpperCase()}`} counts={groupCounts(g.items)} mt={gi === 0 ? 0 : 14} />
                      {g.items.map((issue) => <IssueCard key={issue.id} issue={issue} />)}
                    </div>
                  ))}
            {unavailable.length > 0
              ? <div style={{ fontSize: 7.5, color: "var(--txt3)", marginTop: 12, letterSpacing: ".06em" }}>↳ deferred for {report?.writing_mode ?? "this mode"}: {unavailable.join(" · ")}</div>
              : null}
          </div>
        </div>

        {/* right: heat + radial breakdown */}
        <div style={{ width: 440, flex: "none", background: "#06080c", display: "flex", flexDirection: "column", overflowY: "auto" }}>
          <div style={{ padding: "13px 14px", borderBottom: "1px solid var(--line2)" }}>
            <div style={{ fontSize: 8, letterSpacing: ".18em", color: "var(--txt3)", marginBottom: 9 }}>MOST-AFFECTED SCENES</div>
            {topScenes.length === 0
              ? <div style={{ fontSize: 8.5, color: "var(--txt3)" }}>No scene-linked issues.</div>
              : (
                <>
                  <div style={{ display: "flex", gap: 3, height: 30, alignItems: "flex-end" }}>
                    {topScenes.map(([id, count]) => {
                      const ratio = maxFreq > 0 ? count / maxFreq : 0;
                      const color = ratio >= 0.8 ? "var(--blocking)" : ratio >= 0.45 ? "var(--amber)" : "var(--green)";
                      return <div key={id} style={{ flex: 1, background: color, height: `${Math.max(12, Math.round(ratio * 100))}%` }} />;
                    })}
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 7, color: "var(--txt3)", marginTop: 3 }}>
                    <span>SC.{topScenes[0]![0]}</span>
                    <span>SC.{topScenes[topScenes.length - 1]![0]}</span>
                  </div>
                </>
              )}
          </div>
          <div style={{ padding: "13px 14px", borderBottom: "1px solid var(--line2)" }}>
            <div style={{ fontSize: 8, letterSpacing: ".18em", color: "var(--txt3)", marginBottom: 10 }}>ISSUES BY DIMENSION</div>
            {breakdown.length === 0
              ? <div style={{ fontSize: 8.5, color: "var(--txt3)" }}>No issues to chart.</div>
              : (
                <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                  <div style={{ position: "relative", width: 74, height: 74, borderRadius: "50%", background: conic }}>
                    <div style={{ position: "absolute", inset: 13, borderRadius: "50%", background: "#06080c", display: "grid", placeItems: "center", fontFamily: "'Chakra Petch'", fontSize: 16, color: "#fff" }}>{total}</div>
                  </div>
                  <div style={{ fontSize: 8.5, color: "var(--txt2)", lineHeight: 1.7 }}>
                    {breakdown.map((b) => (
                      <div key={b.dimension}><span style={{ color: b.color }}>●</span> {b.dimension} {b.count}</div>
                    ))}
                  </div>
                </div>
              )}
          </div>
        </div>
      </div>
    </PanelShell>
  );
}
