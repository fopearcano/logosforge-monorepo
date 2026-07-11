import type { CSSProperties, ReactNode } from "react";
import type { SceneDTO } from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useScenes } from "../../hooks";
import { useNavigate } from "../../adapters/StudioProvider";

/**
 * Scene-derived breakdown views — Acts / Chapters / Beats / Tags. Each is a
 * read-only lens over the live `useScenes` data (no separate store): group /
 * aggregate the manuscript and jump to any scene. Mirrors the Python app's
 * Acts / Beats / Tags / Chapters analysis views without needing new endpoints.
 */

const wc = (t: string) => (t.trim() ? t.trim().split(/\s+/).length : 0);
const num = (n: number) => n.toLocaleString();

const frame: CSSProperties = {
  position: "relative", width: "100%", height: "100%",
  background: "linear-gradient(180deg,var(--panel),var(--base))", border: "1px solid var(--line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)", overflow: "hidden", display: "flex", flexDirection: "column",
};
const headCss: CSSProperties = { flex: "none", height: 40, display: "flex", alignItems: "center", gap: 10, padding: "0 16px", borderBottom: "1px solid var(--line)" };
const titleCss: CSSProperties = { fontFamily: "'Chakra Petch',sans-serif", fontWeight: 600, fontSize: 12.5, letterSpacing: ".14em", color: "var(--strong)" };
const groupHead: CSSProperties = { display: "flex", alignItems: "baseline", gap: 8, marginBottom: 7 };
const chipRow: CSSProperties = { display: "flex", flexWrap: "wrap", gap: 6 };

const centered = (text: string, color = "var(--txt3)"): ReactNode => (
  <div style={{ padding: "48px 0", textAlign: "center", fontSize: 11, color, letterSpacing: ".04em", lineHeight: 1.6 }}>{text}</div>
);

interface Res { data: SceneDTO[] | undefined; loading: boolean; error: string | null }
function useSorted() {
  const scenes = useScenes() as Res;
  const sorted = [...(scenes.data ?? [])].sort((a, b) => a.sort_order - b.sort_order);
  return { scenes, sorted };
}

function Frame({ panelProps, screen, title, count, children }: { panelProps: PanelProps; screen: string; title: string; count?: ReactNode; children: ReactNode }) {
  return (
    <PanelShell {...panelProps}>
      <div data-screen-label={screen} style={frame}>
        <Corners />
        <div style={headCss}>
          <span style={{ width: 6, height: 6, background: "var(--accent)", boxShadow: "0 0 6px var(--accent)" }} />
          <span style={titleCss}>{title}</span>
          {count != null && <span style={{ fontSize: 9, color: "var(--txt3)", letterSpacing: ".1em" }}>{count}</span>}
        </div>
        <div style={{ flex: 1, overflowY: "auto", padding: 14 }}>{children}</div>
      </div>
    </PanelShell>
  );
}

function SceneChip({ s, go }: { s: SceneDTO; go: (id: number) => void }) {
  return (
    <button type="button" onClick={() => go(s.id)} title={`Open “${s.title || "Untitled"}” in the Manuscript`}
      style={{ display: "inline-flex", alignItems: "center", gap: 6, maxWidth: 240, border: "1px solid var(--line2)", background: "var(--tint)", color: "var(--txt2)", font: "inherit", fontSize: 10, padding: "4px 9px", cursor: "pointer", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
      <span style={{ color: "var(--txt3)", flex: "none" }}>{wc(s.content)}w</span>
      <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{s.title || "Untitled"}</span>
    </button>
  );
}

/** Preserve manuscript order; group by a computed key. */
function grouped(scenes: SceneDTO[], key: (s: SceneDTO) => string): [string, SceneDTO[]][] {
  const order: string[] = [];
  const m = new Map<string, SceneDTO[]>();
  for (const s of scenes) {
    const k = key(s);
    let arr = m.get(k);
    if (!arr) { arr = []; m.set(k, arr); order.push(k); }
    arr.push(s);
  }
  return order.map((k) => [k, m.get(k)!] as [string, SceneDTO[]]);
}

/* ===================== ACTS / CHAPTERS (group by a scene field) ===================== */

function GroupByField({ panelProps, screen, title, field, unit, empty }: { panelProps: PanelProps; screen: string; title: string; field: "act" | "chapter"; unit: string; empty: string }) {
  const { scenes, sorted } = useSorted();
  const navigate = useNavigate();
  const go = (id: number) => navigate("Manuscript", { sceneId: id });
  const groups = grouped(sorted, (s) => (s[field] || "").trim() || "— Unassigned —");
  const maxWords = Math.max(1, ...groups.map(([, ss]) => ss.reduce((n, s) => n + wc(s.content), 0)));

  return (
    <Frame panelProps={panelProps} screen={screen} title={title} count={sorted.length ? `${groups.length} ${unit} · ${sorted.length} scenes` : undefined}>
      {scenes.loading && !scenes.data ? centered("Loading…")
        : scenes.error ? centered(scenes.error, "var(--blocking)")
        : sorted.length === 0 ? centered(empty)
        : (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {groups.map(([label, ss]) => {
              const words = ss.reduce((n, s) => n + wc(s.content), 0);
              return (
                <div key={label}>
                  <div style={groupHead}>
                    <span style={{ fontFamily: "'Chakra Petch'", fontSize: 12, color: "var(--strong)", letterSpacing: ".04em" }}>{label}</span>
                    <span style={{ fontSize: 8.5, color: "var(--txt3)" }}>{ss.length} sc · {num(words)}w</span>
                  </div>
                  <div style={{ height: 4, background: "var(--tint2)", marginBottom: 8 }}>
                    <div style={{ width: `${Math.round((words / maxWords) * 100)}%`, height: "100%", background: "var(--accent)" }} />
                  </div>
                  <div style={chipRow}>{ss.map((s) => <SceneChip key={s.id} s={s} go={go} />)}</div>
                </div>
              );
            })}
          </div>
        )}
    </Frame>
  );
}

export const ActsView = (props: PanelProps) => <GroupByField panelProps={props} screen="acts-view" title="ACTS" field="act" unit="acts" empty="No acts assigned yet — set an Act on scenes (the ⋮ details row in the Manuscript)." />;
export const ChaptersView = (props: PanelProps) => <GroupByField panelProps={props} screen="chapters-view" title="CHAPTERS" field="chapter" unit="chapters" empty="No chapters yet — set a Chapter on scenes (the ⋮ details row in the Manuscript)." />;

/* ===================== BEATS (coverage + grouping by scene.beat) ===================== */

export function BeatsView(props: PanelProps) {
  const { scenes, sorted } = useSorted();
  const navigate = useNavigate();
  const go = (id: number) => navigate("Manuscript", { sceneId: id });
  const withBeat = sorted.filter((s) => (s.beat || "").trim());
  const groups = grouped(withBeat, (s) => (s.beat || "").trim());
  const noBeat = sorted.length - withBeat.length;
  const pct = sorted.length ? Math.round((withBeat.length / sorted.length) * 100) : 0;

  return (
    <Frame panelProps={props} screen="beats-view" title="BEATS" count={sorted.length ? `${groups.length} beats · ${pct}% covered` : undefined}>
      {scenes.loading && !scenes.data ? centered("Loading…")
        : scenes.error ? centered(scenes.error, "var(--blocking)")
        : sorted.length === 0 ? centered("No scenes yet — beats read the scene's Beat field.")
        : (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ fontSize: 9.5, color: "var(--txt2)" }}>{withBeat.length} of {sorted.length} scenes carry a beat{noBeat > 0 ? ` · ${noBeat} unbeat` : ""}.</div>
            {groups.length === 0
              ? centered("No beats assigned — set a Beat on scenes (the ⋮ details row in the Manuscript).")
              : groups.map(([beat, ss]) => (
                <div key={beat}>
                  <div style={groupHead}>
                    <span style={{ fontSize: 11, color: "var(--accent)", letterSpacing: ".02em" }}>◆ {beat}</span>
                    <span style={{ fontSize: 8.5, color: "var(--txt3)" }}>{ss.length} sc</span>
                  </div>
                  <div style={chipRow}>{ss.map((s) => <SceneChip key={s.id} s={s} go={go} />)}</div>
                </div>
              ))}
            {noBeat > 0 && (
              <div style={{ borderTop: "1px solid var(--line2)", paddingTop: 10 }}>
                <div style={{ ...groupHead }}><span style={{ fontSize: 10.5, color: "var(--amber)" }}>△ No beat · {noBeat}</span></div>
                <div style={chipRow}>{sorted.filter((s) => !(s.beat || "").trim()).map((s) => <SceneChip key={s.id} s={s} go={go} />)}</div>
              </div>
            )}
          </div>
        )}
    </Frame>
  );
}

/* ===================== TAGS (aggregate scene.tags) ===================== */

export function TagsView(props: PanelProps) {
  const { scenes, sorted } = useSorted();
  const navigate = useNavigate();
  const go = (id: number) => navigate("Manuscript", { sceneId: id });
  const m = new Map<string, SceneDTO[]>();
  for (const s of sorted) for (const raw of s.tags ?? []) {
    const t = raw.trim();
    if (!t) continue;
    let arr = m.get(t);
    if (!arr) { arr = []; m.set(t, arr); }
    arr.push(s);
  }
  const tags = [...m.entries()].sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]));
  const untagged = sorted.filter((s) => !(s.tags ?? []).some((t) => t.trim())).length;
  const maxN = Math.max(1, ...tags.map(([, ss]) => ss.length));

  return (
    <Frame panelProps={props} screen="tags-view" title="TAGS" count={sorted.length ? `${tags.length} tags · ${sorted.length} scenes` : undefined}>
      {scenes.loading && !scenes.data ? centered("Loading…")
        : scenes.error ? centered(scenes.error, "var(--blocking)")
        : sorted.length === 0 ? centered("No scenes yet — tags aggregate the scene Tags field.")
        : tags.length === 0 ? centered("No tags yet — add tags to scenes to see their distribution here.")
        : (
          <div style={{ display: "flex", flexDirection: "column", gap: 13 }}>
            {tags.map(([tag, ss]) => (
              <div key={tag}>
                <div style={groupHead}>
                  <span style={{ fontSize: 10.5, color: "var(--cyan)", border: "1px solid var(--line-cy,#2b6f8f)", padding: "2px 8px", letterSpacing: ".04em" }}>#{tag}</span>
                  <span style={{ fontSize: 8.5, color: "var(--txt3)" }}>{ss.length}</span>
                  <div style={{ flex: 1, height: 4, background: "var(--tint2)", maxWidth: 160 }}>
                    <div style={{ width: `${Math.round((ss.length / maxN) * 100)}%`, height: "100%", background: "var(--cyan)" }} />
                  </div>
                </div>
                <div style={chipRow}>{ss.map((s) => <SceneChip key={s.id} s={s} go={go} />)}</div>
              </div>
            ))}
            {untagged > 0 && <div style={{ fontSize: 9, color: "var(--txt3)", borderTop: "1px solid var(--line2)", paddingTop: 9 }}>{untagged} untagged scene{untagged === 1 ? "" : "s"}.</div>}
          </div>
        )}
    </Frame>
  );
}
