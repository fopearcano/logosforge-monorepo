import { useEffect, useState, type CSSProperties } from "react";
import type { GnPageDTO, GnPanelDTO, GnContinuityItemDTO, GnContinuityAppearanceDTO, StageCueDTO, StageEntranceExitDTO, StageBusinessDTO, SeasonDTO, EpisodeDTO, SeriesArcDTO, EpisodePlotlineDTO, ContinuityMemoryDTO, SceneDTO, CharacterDTO, PsykeEntryDTO } from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useStudio } from "../../adapters/StudioProvider";

const panelBox: CSSProperties = {
  position: "relative", width: "100%", height: "100%",
  background: "linear-gradient(180deg,#0a0810,#05050a)", border: "1px solid var(--line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)", overflow: "hidden", display: "flex", flexDirection: "column",
};
const inp: CSSProperties = { background: "rgba(11,8,18,.6)", border: "1px solid var(--line2)", color: "var(--txt)", fontSize: 10.5, padding: "4px 8px", outline: "none", fontFamily: "inherit", minWidth: 0 };
const lbl: CSSProperties = { fontSize: 8, letterSpacing: ".14em", color: "var(--txt3)", marginBottom: 6 };

function Add({ on, busy }: { on: () => void; busy?: boolean }) {
  return <span onClick={busy ? undefined : on} style={{ fontSize: 9, color: "#04060a", background: busy ? "var(--line2)" : "var(--accent)", padding: "4px 11px", fontWeight: 600, letterSpacing: ".06em", cursor: busy ? "default" : "pointer", flex: "none" }}>{busy ? "…" : "+ ADD"}</span>;
}
const card: CSSProperties = { border: "1px solid var(--line2)", background: "rgba(11,8,18,.5)", padding: "8px 10px", marginBottom: 7 };
const row: CSSProperties = { display: "flex", gap: 7, alignItems: "center", marginBottom: 9 };

// ----------------------------------------------------------------- Graphic novel
function GnAuthoring({ pid }: { pid: number }) {
  const { api } = useStudio();
  const [pages, setPages] = useState<GnPageDTO[]>([]);
  const [panels, setPanels] = useState<Record<number, GnPanelDTO[]>>({});
  const [summary, setSummary] = useState("");
  const [draft, setDraft] = useState<Record<number, string>>({});
  const loadPages = () => api.listGnPages(pid).then(setPages).catch(() => {});
  useEffect(() => { loadPages(); }, [pid]);
  useEffect(() => { pages.forEach((p) => p.id && api.listGnPanels(pid, p.id).then((ps) => setPanels((m) => ({ ...m, [p.id!]: ps }))).catch(() => {})); }, [pages]);
  const [syncMsg, setSyncMsg] = useState("");
  const [items, setItems] = useState<GnContinuityItemDTO[]>([]);
  const [appears, setAppears] = useState<Record<number, GnContinuityAppearanceDTO[]>>({});
  const [itemName, setItemName] = useState("");
  const [itemType, setItemType] = useState("prop");
  const [apPage, setApPage] = useState<Record<number, number | "">>({});
  const loadItems = () => api.listGnContinuityItems(pid).then(setItems).catch(() => {});
  useEffect(() => { loadItems(); }, [pid]);
  useEffect(() => { items.forEach((it) => it.id != null && api.listGnContinuityAppearances(pid, it.id).then((a) => setAppears((m) => ({ ...m, [it.id!]: a }))).catch(() => {})); }, [items]);
  const pageNum = (id?: number | null) => { const p = pages.find((x) => x.id === id); return p ? `p${p.page_number}` : `#${id}`; };
  const addItem = async () => { if (!itemName.trim()) return; await api.createGnContinuityItem(pid, { name: itemName, item_type: itemType }); setItemName(""); loadItems(); };
  const addAppearance = async (itemId: number) => { const pg = apPage[itemId]; if (pg === "" || pg == null) return; await api.createGnContinuityAppearance(pid, itemId, { page_id: pg }); setApPage((m) => ({ ...m, [itemId]: "" })); api.listGnContinuityAppearances(pid, itemId).then((a) => setAppears((m) => ({ ...m, [itemId]: a }))).catch(() => {}); };
  const addPage = async () => { if (!summary.trim()) return; await api.createGnPage(pid, { summary }); setSummary(""); loadPages(); };
  // Bridge authored GN-script scene text into structured page/panel rows the graph reads.
  const syncFromScenes = async () => {
    setSyncMsg("syncing…");
    try {
      const r = await api.syncGnFromScenes(pid);
      setSyncMsg(r.skipped ? "already synced (pages exist)" : `synced ${r.pages} pages · ${r.panels} panels`);
      loadPages();
    } catch (e) {
      setSyncMsg(`sync failed — ${e instanceof Error ? e.message : String(e)}`);
    }
  };
  const addPanel = async (pageId: number) => { const d = (draft[pageId] || "").trim(); if (!d) return; const [description, motifs] = d.split("|"); await api.createGnPanel(pid, pageId, { description: (description ?? "").trim(), visual_motifs: (motifs || "").split(",").map((s) => s.trim()).filter(Boolean) }); setDraft((m) => ({ ...m, [pageId]: "" })); api.listGnPanels(pid, pageId).then((ps) => setPanels((m) => ({ ...m, [pageId]: ps }))); };
  return (
    <>
      <div style={{ ...row, justifyContent: "space-between" }}>
        <span style={{ fontSize: 8.5, color: "var(--txt3)", letterSpacing: ".06em" }}>parse PAGE/PANEL scene text → structured rows the graph reads</span>
        <span onClick={syncFromScenes} style={{ fontSize: 9, color: "var(--accent)", border: "1px solid var(--line-cy)", background: "rgba(176,124,255,.08)", padding: "4px 10px", cursor: "pointer", letterSpacing: ".06em" }}>⟳ SYNC FROM SCENES</span>
      </div>
      {syncMsg && <div style={{ fontSize: 9, color: "var(--txt2)", marginBottom: 8 }}>{syncMsg}</div>}
      <div style={lbl}>ADD PAGE</div>
      <div style={row}><input value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="page summary, e.g. “The vault at night”" style={{ ...inp, flex: 1 }} /><Add on={addPage} /></div>
      {pages.map((p) => (
        <div key={p.id} style={card}>
          <div style={{ fontFamily: "'Chakra Petch'", fontSize: 11, color: "#fff" }}>PAGE {p.page_number} <span style={{ color: "var(--txt2)", fontWeight: 400 }}>· {p.summary}</span></div>
          <div style={{ marginTop: 6, paddingLeft: 10, borderLeft: "1px solid var(--line2)" }}>
            {(panels[p.id ?? -1] || []).map((pn) => (
              <div key={pn.id} style={{ fontSize: 10, color: "var(--txt2)", marginBottom: 3 }}>▸ {pn.description}{(pn.visual_motifs || []).length ? <span style={{ color: "var(--cyan)" }}> · {(pn.visual_motifs || []).join(", ")}</span> : null}</div>
            ))}
            <div style={{ display: "flex", gap: 6, marginTop: 5 }}>
              <input value={draft[p.id ?? -1] || ""} onChange={(e) => setDraft((m) => ({ ...m, [p.id!]: e.target.value }))} placeholder="panel description | motif, motif" style={{ ...inp, flex: 1, fontSize: 9.5 }} />
              <Add on={() => p.id && addPanel(p.id)} />
            </div>
          </div>
        </div>
      ))}

      <div style={{ ...lbl, marginTop: 12 }}>CONTINUITY OBJECTS (object → page edges)</div>
      <div style={row}>
        <input value={itemName} onChange={(e) => setItemName(e.target.value)} placeholder="object name, e.g. “the watch”" style={{ ...inp, flex: 1 }} />
        <select value={itemType} onChange={(e) => setItemType(e.target.value)} style={{ ...inp, width: 88 }}>{["prop", "setting", "character", "other"].map((t) => <option key={t} value={t}>{t}</option>)}</select>
        <Add on={addItem} />
      </div>
      {items.map((it) => (
        <div key={it.id} style={{ ...card, padding: "7px 10px" }}>
          <div style={{ fontSize: 10.5, color: "#fff" }}>◆ {it.name} <span style={{ color: "var(--txt3)", fontWeight: 400 }}>· {it.item_type}</span>
            {(appears[it.id ?? -1] || []).length ? <span style={{ color: "var(--cyan)", fontSize: 9 }}> — {(appears[it.id ?? -1] || []).map((a) => pageNum(a.page_id)).join(", ")}</span> : null}
          </div>
          {pages.length > 0 && (
            <div style={{ display: "flex", gap: 5, marginTop: 4 }}>
              <select value={apPage[it.id ?? -1] == null || apPage[it.id ?? -1] === "" ? "" : String(apPage[it.id ?? -1])} onChange={(e) => setApPage((m) => ({ ...m, [it.id!]: e.target.value ? Number(e.target.value) : "" }))} style={{ ...inp, flex: 1, fontSize: 9 }}><option value="">— appears on page —</option>{pages.map((p) => <option key={p.id} value={String(p.id)}>PAGE {p.page_number}</option>)}</select>
              <Add on={() => it.id && addAppearance(it.id)} />
            </div>
          )}
        </div>
      ))}
      {pages.length === 0 && <div style={{ fontSize: 9, color: "var(--txt3)", fontStyle: "italic" }}>Add or sync pages first, then tag continuity objects to them.</div>}
    </>
  );
}

// ----------------------------------------------------------------- Scene (graph-feeding scene fields)
function SceneGraphAuthoring({ pid }: { pid: number }) {
  const { api } = useStudio();
  const [scenes, setScenes] = useState<SceneDTO[]>([]);
  const [sel, setSel] = useState<number | null>(null);
  const [wkw, setWkw] = useState("");
  const [notes, setNotes] = useState<ContinuityMemoryDTO[]>([]);
  const [target, setTarget] = useState("");
  const [kind, setKind] = useState("state");
  const [msg, setMsg] = useState("");
  useEffect(() => { api.listScenes(pid).then((s) => { setScenes(s); if (sel == null && s[0]?.id != null) setSel(s[0].id!); }).catch(() => {}); }, [pid]);
  useEffect(() => {
    if (sel == null) return;
    const sc = scenes.find((s) => s.id === sel);
    setWkw(sc?.who_knows_what ?? "");
    api.listContinuity(pid, sel).then(setNotes).catch(() => setNotes([]));
  }, [sel, scenes]);
  const saveWkw = async () => { if (sel == null) return; setMsg("saving…"); try { await api.updateScene(pid, sel, { who_knows_what: wkw }); setMsg("saved who-knows"); } catch (e) { setMsg(`failed — ${e instanceof Error ? e.message : String(e)}`); } };
  const addNote = async () => { if (sel == null || !target.trim()) return; await api.addContinuity(pid, sel, { target, kind, value: "" }); setTarget(""); api.listContinuity(pid, sel).then(setNotes).catch(() => {}); };
  return (
    <>
      <div style={lbl}>SCENE (feeds the “knowledge” + “continuity” graph edges)</div>
      <div style={row}>
        <select value={sel == null ? "" : String(sel)} onChange={(e) => setSel(e.target.value ? Number(e.target.value) : null)} style={{ ...inp, flex: 1 }}>
          {scenes.map((s) => <option key={s.id} value={String(s.id)}>{s.title || `Scene ${s.id}`}</option>)}
        </select>
      </div>
      <div style={{ ...lbl, marginTop: 10 }}>WHO KNOWS WHAT</div>
      <div style={row}>
        <input value={wkw} onChange={(e) => setWkw(e.target.value)} placeholder="what a character knows here that others don’t" style={{ ...inp, flex: 1 }} /><Add on={saveWkw} />
      </div>
      {msg && <div style={{ fontSize: 9, color: "var(--txt2)", marginBottom: 6 }}>{msg}</div>}
      <div style={{ ...lbl, marginTop: 8 }}>CONTINUITY NOTES (track an element across scenes)</div>
      <div style={row}>
        <input value={target} onChange={(e) => setTarget(e.target.value)} placeholder="element, e.g. “the salt ledger”" style={{ ...inp, flex: 1 }} />
        <select value={kind} onChange={(e) => setKind(e.target.value)} style={{ ...inp, width: 92 }}>{["state", "object", "wound", "secret"].map((k) => <option key={k} value={k}>{k}</option>)}</select>
        <Add on={addNote} />
      </div>
      {notes.map((n) => <div key={n.id} style={{ ...card, padding: "5px 10px", fontSize: 10, color: "var(--txt2)" }}><span style={{ color: "var(--cyan)" }}>{n.kind}</span> · {n.target}</div>)}
    </>
  );
}

// ----------------------------------------------------------------- Stage
function StageAuthoring({ pid }: { pid: number }) {
  const { api } = useStudio();
  const [sceneId, setSceneId] = useState(1);
  const [cues, setCues] = useState<StageCueDTO[]>([]);
  const [entrances, setEntrances] = useState<StageEntranceExitDTO[]>([]);
  const [biz, setBiz] = useState<StageBusinessDTO[]>([]);
  const [chars, setChars] = useState<CharacterDTO[]>([]);
  const [props, setProps] = useState<PsykeEntryDTO[]>([]);
  const [cueType, setCueType] = useState("light");
  const [cueText, setCueText] = useState("");
  const [entType, setEntType] = useState("entrance");
  const [entChar, setEntChar] = useState<number | "">("");
  const [entCue, setEntCue] = useState("");
  const [bizProp, setBizProp] = useState<number | "">("");
  const [bizChar, setBizChar] = useState<number | "">("");
  const [bizAction, setBizAction] = useState("");
  const [stageSyncMsg, setStageSyncMsg] = useState("");

  const load = () => {
    api.listStageCues(pid, sceneId).then(setCues).catch(() => {});
    api.listStageEntrances(pid, sceneId).then(setEntrances).catch(() => {});
    api.listStageBusiness(pid, sceneId).then(setBiz).catch(() => {});
  };
  useEffect(() => { load(); }, [pid, sceneId]);
  // characters + PSYKE 'object' props drive the entrance/business pickers.
  useEffect(() => {
    api.listCharacters(pid).then(setChars).catch(() => {});
    api.listPsyke(pid).then((es) => setProps(es.filter((e) => e.type === "object"))).catch(() => {});
  }, [pid]);

  const charName = (id?: number | null) => chars.find((c) => c.id === id)?.name ?? (id != null ? `#${id}` : "—");
  const propName = (id?: number | null) => props.find((p) => p.id === id)?.name ?? (id != null ? `#${id}` : "—");
  const addCue = async () => { if (!cueText.trim()) return; await api.createStageCue(pid, sceneId, { cue_type: cueType, cue_text: cueText }); setCueText(""); load(); };
  const addEntrance = async () => { await api.createStageEntrance(pid, sceneId, { type: entType, character_id: entChar === "" ? null : entChar, cue_text: entCue }); setEntCue(""); setEntChar(""); load(); };
  const addBiz = async () => { if (bizProp === "") return; await api.createStageBusiness(pid, sceneId, { prop_psyke_entry_id: bizProp, character_id: bizChar === "" ? null : bizChar, stage_action: bizAction }); setBizAction(""); setBizProp(""); setBizChar(""); load(); };
  // Parse stage directions across all scenes into cue/entrance/offstage rows.
  const syncStage = async () => {
    setStageSyncMsg("syncing…");
    try { const r = await api.syncStageFromScenes(pid); setStageSyncMsg(`synced ${r.cues} cues · ${r.entrances} entrances · ${r.offstage} offstage`); load(); }
    catch (e) { setStageSyncMsg(`sync failed — ${e instanceof Error ? e.message : String(e)}`); }
  };

  return (
    <>
      <div style={{ ...row, justifyContent: "space-between" }}>
        <span style={{ fontSize: 8.5, color: "var(--txt3)" }}>SCENE <input type="number" value={sceneId} onChange={(e) => setSceneId(Number(e.target.value) || 1)} style={{ ...inp, width: 60 }} /></span>
        <span onClick={syncStage} style={{ fontSize: 9, color: "var(--accent)", border: "1px solid var(--line-cy)", background: "rgba(176,124,255,.08)", padding: "4px 10px", cursor: "pointer", letterSpacing: ".06em" }}>⟳ SYNC FROM SCENES</span>
      </div>
      {stageSyncMsg && <div style={{ fontSize: 9, color: "var(--txt2)", marginBottom: 8 }}>{stageSyncMsg}</div>}

      <div style={lbl}>ADD CUE</div>
      <div style={row}>
        <select value={cueType} onChange={(e) => setCueType(e.target.value)} style={{ ...inp, width: 90 }}>{["light", "sound", "music", "prop", "movement", "other"].map((t) => <option key={t} value={t}>{t}</option>)}</select>
        <input value={cueText} onChange={(e) => setCueText(e.target.value)} placeholder="cue text, e.g. “lights snap up”" style={{ ...inp, flex: 1 }} /><Add on={addCue} />
      </div>
      {cues.map((c) => <div key={c.id} style={{ ...card, padding: "6px 10px", display: "flex", gap: 9, fontSize: 10 }}><span style={{ color: "var(--amber)", letterSpacing: ".1em", width: 70 }}>{(c.cue_type || "").toUpperCase()}</span><span style={{ color: "var(--txt2)" }}>{c.cue_text}</span></div>)}

      <div style={{ ...lbl, marginTop: 12 }}>ADD ENTRANCE / EXIT</div>
      <div style={row}>
        <select value={entType} onChange={(e) => setEntType(e.target.value)} style={{ ...inp, width: 84 }}>{["entrance", "exit"].map((t) => <option key={t} value={t}>{t}</option>)}</select>
        <select value={entChar === "" ? "" : String(entChar)} onChange={(e) => setEntChar(e.target.value ? Number(e.target.value) : "")} style={{ ...inp, flex: 1 }}><option value="">— character —</option>{chars.map((c) => <option key={c.id} value={String(c.id)}>{c.name}</option>)}</select>
        <input value={entCue} onChange={(e) => setEntCue(e.target.value)} placeholder="cue text" style={{ ...inp, flex: 1 }} /><Add on={addEntrance} />
      </div>
      {entrances.map((en) => <div key={en.id} style={{ ...card, padding: "6px 10px", display: "flex", gap: 9, fontSize: 10 }}><span style={{ color: "var(--cyan)", letterSpacing: ".1em", width: 70 }}>{(en.type || "").toUpperCase()}</span><span style={{ color: "#fff" }}>{charName(en.character_id)}</span><span style={{ color: "var(--txt2)" }}>{en.cue_text}</span></div>)}

      <div style={{ ...lbl, marginTop: 12 }}>ADD STAGE BUSINESS (prop)</div>
      <div style={row}>
        <select value={bizProp === "" ? "" : String(bizProp)} onChange={(e) => setBizProp(e.target.value ? Number(e.target.value) : "")} style={{ ...inp, flex: 1 }}><option value="">— prop (PSYKE object) —</option>{props.map((p) => <option key={p.id} value={String(p.id)}>{p.name}</option>)}</select>
        <select value={bizChar === "" ? "" : String(bizChar)} onChange={(e) => setBizChar(e.target.value ? Number(e.target.value) : "")} style={{ ...inp, width: 120 }}><option value="">— character —</option>{chars.map((c) => <option key={c.id} value={String(c.id)}>{c.name}</option>)}</select>
        <input value={bizAction} onChange={(e) => setBizAction(e.target.value)} placeholder="stage action, e.g. “pockets the watch”" style={{ ...inp, flex: 1 }} /><Add on={addBiz} />
      </div>
      {props.length === 0 && <div style={{ fontSize: 9, color: "var(--txt3)", fontStyle: "italic", marginBottom: 7 }}>Add a PSYKE “object” entry to use as a prop.</div>}
      {biz.map((b) => <div key={b.id} style={{ ...card, padding: "6px 10px", display: "flex", gap: 9, fontSize: 10 }}><span style={{ color: "var(--green)", width: 90 }}>{propName(b.prop_psyke_entry_id)}</span><span style={{ color: "#fff", width: 70 }}>{charName(b.character_id)}</span><span style={{ color: "var(--txt2)" }}>{b.stage_action}</span></div>)}
    </>
  );
}

// ----------------------------------------------------------------- Series
function SeriesAuthoring({ pid }: { pid: number }) {
  const { api } = useStudio();
  const [seasons, setSeasons] = useState<SeasonDTO[]>([]);
  const [episodes, setEpisodes] = useState<EpisodeDTO[]>([]);
  const [arcs, setArcs] = useState<SeriesArcDTO[]>([]);
  const [plotlines, setPlotlines] = useState<Record<number, EpisodePlotlineDTO[]>>({});
  const [chars, setChars] = useState<PsykeEntryDTO[]>([]);
  const [seasonTitle, setSeasonTitle] = useState("");
  const [epDraft, setEpDraft] = useState<Record<number, string>>({});
  const [plDraft, setPlDraft] = useState<Record<number, string>>({});
  const [arcTitle, setArcTitle] = useState("");
  const [arcSetup, setArcSetup] = useState<number | "">("");
  const [arcPayoff, setArcPayoff] = useState<number | "">("");
  const [arcStatus, setArcStatus] = useState("active");
  const [memChar, setMemChar] = useState<number | "">("");
  const [memEp, setMemEp] = useState<number | "">("");
  const [memStatus, setMemStatus] = useState("");
  const [memFlags, setMemFlags] = useState("");
  const loadAll = () => {
    api.listSeasons(pid).then(setSeasons).catch(() => {});
    api.listEpisodes(pid).then(setEpisodes).catch(() => {});
    api.listSeriesArcs(pid).then(setArcs).catch(() => {});
    api.listPsyke(pid).then((es) => setChars(es.filter((e) => e.type === "character"))).catch(() => {});
  };
  useEffect(() => { loadAll(); }, [pid]);
  useEffect(() => { episodes.forEach((e) => e.id != null && api.listEpisodePlotlines(pid, e.id).then((pl) => setPlotlines((m) => ({ ...m, [e.id!]: pl }))).catch(() => {})); }, [episodes]);
  const epLabel = (id?: number | null) => { const e = episodes.find((x) => x.id === id); return e ? `EP${e.episode_number} ${e.title ?? ""}`.trim() : (id != null ? `#${id}` : "—"); };
  const addSeason = async () => { if (!seasonTitle.trim()) return; await api.createSeason(pid, { title: seasonTitle }); setSeasonTitle(""); loadAll(); };
  const addEpisode = async (seasonId: number) => { const t = (epDraft[seasonId] || "").trim(); if (!t) return; await api.createEpisode(pid, seasonId, { title: t }); setEpDraft((m) => ({ ...m, [seasonId]: "" })); loadAll(); };
  const addPlotline = async (episodeId: number) => { const t = (plDraft[episodeId] || "").trim(); if (!t) return; await api.createEpisodePlotline(pid, episodeId, { type: "A", title: t }); setPlDraft((m) => ({ ...m, [episodeId]: "" })); api.listEpisodePlotlines(pid, episodeId).then((pl) => setPlotlines((m) => ({ ...m, [episodeId]: pl }))).catch(() => {}); };
  // Merge a per-episode status (echo edges) + an optional continuity flag (contradict)
  // onto the chosen PSYKE character's series memory.
  const setMemory = async () => {
    if (memChar === "") return;
    const cur = await api.getSeriesMemory(pid, memChar).catch(() => ({ current_status_by_episode: {} as Record<string, string>, continuity_flags: "" }));
    const csbe = { ...(cur.current_status_by_episode || {}) };
    if (memEp !== "" && memStatus.trim()) csbe[String(memEp)] = memStatus.trim();
    await api.setSeriesMemory(pid, memChar, { continuity_flags: memFlags || cur.continuity_flags || "", current_status_by_episode: csbe });
    setMemStatus(""); setMemEp("");
  };
  // Bind the arc to its setup/payoff episodes + status — these are exactly what the
  // series graph enricher reads to emit sets_up / pays_off / resolves / escalates edges.
  const addArc = async () => {
    if (!arcTitle.trim()) return;
    await api.createSeriesArc(pid, {
      title: arcTitle, scope: "series", status: arcStatus,
      setup_episode_id: arcSetup === "" ? null : arcSetup,
      payoff_episode_id: arcPayoff === "" ? null : arcPayoff,
    });
    setArcTitle(""); setArcSetup(""); setArcPayoff(""); loadAll();
  };
  return (
    <>
      <div style={lbl}>ADD SEASON</div>
      <div style={row}><input value={seasonTitle} onChange={(e) => setSeasonTitle(e.target.value)} placeholder="season title" style={{ ...inp, flex: 1 }} /><Add on={addSeason} /></div>
      {seasons.map((s) => (
        <div key={s.id} style={card}>
          <div style={{ fontFamily: "'Chakra Petch'", fontSize: 11, color: "#fff" }}>SEASON {s.season_number} <span style={{ color: "var(--txt2)", fontWeight: 400 }}>· {s.title}</span></div>
          <div style={{ marginTop: 6, paddingLeft: 10, borderLeft: "1px solid var(--line2)" }}>
            {episodes.filter((e) => e.season_id === s.id).map((e) => (
              <div key={e.id} style={{ marginBottom: 5 }}>
                <div style={{ fontSize: 10, color: "var(--txt2)" }}>▸ EP{e.episode_number} {e.title}</div>
                <div style={{ paddingLeft: 12 }}>
                  {(plotlines[e.id ?? -1] || []).map((pl) => <div key={pl.id} style={{ fontSize: 9, color: "var(--cyan)" }}>· {pl.type}-story — {pl.title}</div>)}
                  <div style={{ display: "flex", gap: 5, marginTop: 2 }}>
                    <input value={plDraft[e.id ?? -1] || ""} onChange={(ev) => setPlDraft((m) => ({ ...m, [e.id!]: ev.target.value }))} placeholder="plotline (A-story)" style={{ ...inp, flex: 1, fontSize: 9 }} />
                    <Add on={() => e.id && addPlotline(e.id)} />
                  </div>
                </div>
              </div>
            ))}
            <div style={{ display: "flex", gap: 6, marginTop: 5 }}><input value={epDraft[s.id ?? -1] || ""} onChange={(ev) => setEpDraft((m) => ({ ...m, [s.id!]: ev.target.value }))} placeholder="episode title" style={{ ...inp, flex: 1, fontSize: 9.5 }} /><Add on={() => s.id && addEpisode(s.id)} /></div>
          </div>
        </div>
      ))}
      <div style={{ ...lbl, marginTop: 12 }}>ADD ARC (setup → payoff)</div>
      <div style={row}><input value={arcTitle} onChange={(e) => setArcTitle(e.target.value)} placeholder="arc title, e.g. “The Kessler Mystery”" style={{ ...inp, flex: 1 }} /></div>
      <div style={row}>
        <select value={arcSetup === "" ? "" : String(arcSetup)} onChange={(e) => setArcSetup(e.target.value ? Number(e.target.value) : "")} style={{ ...inp, flex: 1 }}><option value="">— setup episode —</option>{episodes.map((ep) => <option key={ep.id} value={String(ep.id)}>{epLabel(ep.id)}</option>)}</select>
        <select value={arcPayoff === "" ? "" : String(arcPayoff)} onChange={(e) => setArcPayoff(e.target.value ? Number(e.target.value) : "")} style={{ ...inp, flex: 1 }}><option value="">— payoff episode —</option>{episodes.map((ep) => <option key={ep.id} value={String(ep.id)}>{epLabel(ep.id)}</option>)}</select>
        <select value={arcStatus} onChange={(e) => setArcStatus(e.target.value)} style={{ ...inp, width: 96 }}>{["active", "resolved", "delayed"].map((s) => <option key={s} value={s}>{s}</option>)}</select>
        <Add on={addArc} />
      </div>
      {episodes.length === 0 && <div style={{ fontSize: 9, color: "var(--txt3)", fontStyle: "italic", marginBottom: 7 }}>Add episodes first to bind an arc’s setup → payoff (unbound arcs emit no arc edges).</div>}
      {arcs.map((a) => <div key={a.id} style={{ ...card, padding: "6px 10px", fontSize: 10, color: "var(--txt2)" }}><span style={{ color: "var(--green)", letterSpacing: ".08em" }}>◆ {a.title}</span> <span style={{ color: "var(--txt3)" }}>· {a.status}</span>{(a.setup_episode_id != null || a.payoff_episode_id != null) && <span style={{ color: "var(--cyan)" }}> · {epLabel(a.setup_episode_id)} → {epLabel(a.payoff_episode_id)}</span>}</div>)}

      <div style={{ ...lbl, marginTop: 12 }}>SERIES MEMORY (echo / contradict)</div>
      <div style={row}>
        <select value={memChar === "" ? "" : String(memChar)} onChange={(e) => setMemChar(e.target.value ? Number(e.target.value) : "")} style={{ ...inp, flex: 1 }}><option value="">— PSYKE character —</option>{chars.map((c) => <option key={c.id} value={String(c.id)}>{c.name}</option>)}</select>
        <select value={memEp === "" ? "" : String(memEp)} onChange={(e) => setMemEp(e.target.value ? Number(e.target.value) : "")} style={{ ...inp, flex: 1 }}><option value="">— episode —</option>{episodes.map((ep) => <option key={ep.id} value={String(ep.id)}>{epLabel(ep.id)}</option>)}</select>
        <input value={memStatus} onChange={(e) => setMemStatus(e.target.value)} placeholder="status in episode" style={{ ...inp, flex: 1 }} />
      </div>
      <div style={row}>
        <input value={memFlags} onChange={(e) => setMemFlags(e.target.value)} placeholder="continuity flag (optional → contradict edge)" style={{ ...inp, flex: 1 }} /><Add on={setMemory} />
      </div>
      {chars.length === 0 && <div style={{ fontSize: 9, color: "var(--txt3)", fontStyle: "italic" }}>Add a PSYKE “character” entry to track per-episode status.</div>}
    </>
  );
}

const TABS: [string, "gn" | "stage" | "series" | "scene"][] = [["GRAPHIC NOVEL", "gn"], ["STAGE", "stage"], ["SERIES", "series"], ["SCENE", "scene"]];

export function FormatStructure(props: PanelProps) {
  const { projectId } = useStudio();
  const [tab, setTab] = useState<"gn" | "stage" | "series" | "scene">("gn");
  const pid = projectId ?? 0;
  return (
    <PanelShell {...props} style={{ ["--accent"]: "#b07cff" } as CSSProperties}>
      <div data-screen-label="Format Structure" style={panelBox}>
        <Corners />
        <div style={{ height: 42, flex: "none", display: "flex", alignItems: "center", gap: 11, padding: "0 16px", borderBottom: "1px solid var(--line)" }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".1em", color: "#fff" }}>STRUCTURE</span>
          <div style={{ display: "flex", border: "1px solid var(--line2)", fontSize: 8, letterSpacing: ".08em" }}>
            {TABS.map(([label, key], i) => (
              <span key={key} onClick={() => setTab(key)} style={{ padding: "4px 9px", cursor: "pointer", borderLeft: i === 0 ? undefined : "1px solid var(--line2)", color: tab === key ? "#04060a" : "var(--txt3)", background: tab === key ? "var(--accent)" : undefined, fontWeight: tab === key ? 600 : 400 }}>{label}</span>
            ))}
          </div>
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 8, color: "var(--txt3)", letterSpacing: ".08em" }}>authors the structure the graph reads</span>
        </div>
        <div style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: 14 }}>
          {projectId == null ? (
            <div style={{ color: "var(--txt3)", fontSize: 11 }}>Select a project to author its structure.</div>
          ) : tab === "gn" ? (
            <GnAuthoring pid={pid} />
          ) : tab === "stage" ? (
            <StageAuthoring pid={pid} />
          ) : tab === "series" ? (
            <SeriesAuthoring pid={pid} />
          ) : (
            <SceneGraphAuthoring pid={pid} />
          )}
        </div>
      </div>
    </PanelShell>
  );
}
