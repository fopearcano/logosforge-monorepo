import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import type { PluginDTO, SeasonDTO, EpisodeDTO, SeriesArcDTO } from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useStudio } from "../../adapters/StudioProvider";

/**
 * Two small read-only views: the installed analysis Plugins registry (/plugins)
 * and a Series Navigator (browse seasons → episodes + series arcs). Both mirror
 * the Python app's Plugins / Series-Navigator views over existing endpoints.
 */

const panelBox: CSSProperties = {
  position: "relative", width: "100%", height: "100%",
  background: "linear-gradient(180deg,var(--panel),var(--base))", border: "1px solid var(--line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)", overflow: "hidden", display: "flex", flexDirection: "column",
};
const headCss: CSSProperties = { flex: "none", height: 40, display: "flex", alignItems: "center", gap: 10, padding: "0 16px", borderBottom: "1px solid var(--line)" };
const titleCss: CSSProperties = { fontFamily: "'Chakra Petch',sans-serif", fontWeight: 600, fontSize: 12.5, letterSpacing: ".14em", color: "var(--strong)" };
const centered = (t: string, c = "var(--txt3)"): ReactNode => <div style={{ padding: "44px 0", textAlign: "center", fontSize: 11, color: c, lineHeight: 1.6 }}>{t}</div>;
const chip = (text: string, color: string): ReactNode => (
  <span style={{ fontSize: 8, letterSpacing: ".14em", textTransform: "uppercase", color, border: `1px solid ${color}`, borderRadius: 2, padding: "2px 7px", whiteSpace: "nowrap" }}>{text}</span>
);

/* ======================= PLUGINS ======================= */

const CAT_COLOR: Record<string, string> = { analysis: "var(--cyan)", structure: "var(--accent)", character: "var(--amber)" };

export function PluginsPanel(props: PanelProps) {
  const { api } = useStudio();
  const [plugins, setPlugins] = useState<PluginDTO[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    api.listPlugins().then((p) => { if (alive) setPlugins(p); }).catch((e) => { if (alive) setErr(String(e)); });
    return () => { alive = false; };
  }, [api]);
  return (
    <PanelShell {...props}>
      <div data-screen-label="Plugins" style={panelBox}>
        <Corners />
        <div style={headCss}>
          <span style={{ width: 6, height: 6, background: "var(--accent)", boxShadow: "0 0 6px var(--accent)" }} />
          <span style={titleCss}>PLUGINS</span>
          {plugins && <span style={{ fontSize: 9, color: "var(--txt3)", letterSpacing: ".1em" }}>{plugins.length}</span>}
        </div>
        <div style={{ flex: 1, overflowY: "auto", padding: 14 }}>
          {err ? centered(err, "var(--blocking)")
            : !plugins ? centered("Loading…")
            : plugins.length === 0 ? centered("No analysis plugins registered.")
            : <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {plugins.map((p) => (
                  <div key={p.name} style={{ border: "1px solid var(--line2)", background: "var(--tint)", padding: "10px 12px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
                      <span style={{ fontSize: 12, color: "var(--strong)", fontFamily: "'Courier Prime',monospace" }}>{p.name}</span>
                      {chip(p.category || "plugin", CAT_COLOR[p.category] || "var(--txt3)")}
                      {p.requires_scene && chip("scene", "var(--txt3)")}
                    </div>
                    <div style={{ fontSize: 10, color: "var(--txt2)", lineHeight: 1.5 }}>{p.description}</div>
                  </div>
                ))}
              </div>}
          <div style={{ marginTop: 14, fontSize: 8, color: "var(--txt3)", letterSpacing: ".06em" }}>Analysis plugins run inside the core; the Logos + Decision Radar panels surface their findings.</div>
        </div>
      </div>
    </PanelShell>
  );
}

/* ======================= SERIES NAVIGATOR ======================= */

export function SeriesNavigator(props: PanelProps) {
  const { api, projectId } = useStudio();
  const [seasons, setSeasons] = useState<SeasonDTO[]>([]);
  const [episodes, setEpisodes] = useState<EpisodeDTO[]>([]);
  const [arcs, setArcs] = useState<SeriesArcDTO[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (projectId == null) { setLoading(false); return; }
    let alive = true;
    setLoading(true);
    Promise.all([
      api.listSeasons(projectId).catch(() => [] as SeasonDTO[]),
      api.listEpisodes(projectId).catch(() => [] as EpisodeDTO[]),
      api.listSeriesArcs(projectId).catch(() => [] as SeriesArcDTO[]),
    ]).then(([s, e, a]) => { if (!alive) return; setSeasons(s); setEpisodes(e); setArcs(a); setLoading(false); });
    return () => { alive = false; };
  }, [api, projectId]);

  const epsOf = (seasonId?: number) => episodes.filter((e) => e.season_id === seasonId).sort((a, b) => (a.episode_number ?? 0) - (b.episode_number ?? 0));

  return (
    <PanelShell {...props}>
      <div data-screen-label="Series Navigator" style={panelBox}>
        <Corners />
        <div style={headCss}>
          <span style={{ width: 6, height: 6, background: "var(--accent)", boxShadow: "0 0 6px var(--accent)" }} />
          <span style={titleCss}>SERIES</span>
          {!loading && <span style={{ fontSize: 9, color: "var(--txt3)", letterSpacing: ".1em" }}>{seasons.length} seasons · {episodes.length} eps · {arcs.length} arcs</span>}
        </div>
        <div style={{ flex: 1, overflowY: "auto", padding: 14 }}>
          {projectId == null ? centered("Open a project.")
            : loading ? centered("Loading…")
            : seasons.length === 0 && arcs.length === 0 ? centered("No series structure yet — author seasons, episodes and arcs in Format Studio → SERIES.")
            : (
              <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                {seasons.sort((a, b) => (a.season_number ?? 0) - (b.season_number ?? 0)).map((s) => (
                  <div key={s.id}>
                    <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 8 }}>
                      <span style={{ fontFamily: "'Chakra Petch'", fontSize: 12, color: "var(--strong)", letterSpacing: ".04em" }}>S{s.season_number ?? "?"} · {s.title || "Untitled season"}</span>
                      {s.status && chip(s.status, "var(--txt3)")}
                    </div>
                    {s.central_question && <div style={{ fontSize: 9.5, color: "var(--txt3)", fontStyle: "italic", marginBottom: 8, marginLeft: 4 }}>“{s.central_question}”</div>}
                    <div style={{ display: "flex", flexDirection: "column", gap: 5, marginLeft: 4 }}>
                      {epsOf(s.id).length === 0 ? <div style={{ fontSize: 9, color: "var(--txt3)" }}>No episodes.</div>
                        : epsOf(s.id).map((e) => (
                          <div key={e.id} style={{ display: "flex", alignItems: "center", gap: 9, border: "1px solid var(--line2)", background: "var(--tint)", padding: "6px 10px" }}>
                            <span style={{ fontFamily: "'Chakra Petch'", fontSize: 10, color: "var(--accent)", width: 30, flex: "none" }}>E{e.episode_number ?? "?"}</span>
                            <span style={{ flex: 1, minWidth: 0, fontSize: 11, color: "var(--txt)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{e.title || "Untitled"}</span>
                            {e.cliffhanger && chip("cliff", "var(--amber)")}
                            {e.status && <span style={{ fontSize: 8, color: "var(--txt3)" }}>{e.status}</span>}
                          </div>
                        ))}
                    </div>
                  </div>
                ))}
                {arcs.length > 0 && (
                  <div>
                    <div style={{ fontSize: 8, letterSpacing: ".2em", color: "var(--txt3)", marginBottom: 9 }}>SERIES ARCS · {arcs.length}</div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                      {arcs.map((a) => (
                        <div key={a.id} style={{ display: "flex", alignItems: "center", gap: 8, border: "1px solid var(--line2)", borderLeft: "2px solid var(--cyan)", background: "var(--tint)", padding: "6px 10px" }}>
                          {chip(a.scope || "arc", "var(--cyan)")}
                          <span style={{ flex: 1, minWidth: 0, fontSize: 10.5, color: "var(--txt)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{a.title || "Untitled arc"}</span>
                          {a.status && <span style={{ fontSize: 8, color: "var(--txt3)" }}>{a.status}</span>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
        </div>
      </div>
    </PanelShell>
  );
}
