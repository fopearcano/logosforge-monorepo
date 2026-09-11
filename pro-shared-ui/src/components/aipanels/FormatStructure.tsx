import { useEffect, useRef, useState, type CSSProperties } from "react";
import type { GnPageDTO, GnPanelDTO, GnContinuityItemDTO, GnContinuityAppearanceDTO, StageCueDTO, StageEntranceExitDTO, StageBusinessDTO, SeasonDTO, EpisodeDTO, SeriesArcDTO, EpisodePlotlineDTO, ContinuityMemoryDTO, SceneDTO, CharacterDTO, PsykeEntryDTO } from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useStudio } from "../../adapters/StudioProvider";
import { flushPendingProjectSaves, markProjectSavePending, registerProjectFlusher, trackProjectWrite } from "../../adapters/projectSaveCoordinator";
import { createLatestRequestGate } from "../../hooks/latestRequest";
import { ApiRequestError } from "../../adapters/httpApiClient";
import { ConfirmDeleteButton } from "../common/ConfirmDeleteButton";
import { useMountedRef } from "../../hooks/useMountedRef";

const panelBox: CSSProperties = {
  position: "relative", width: "100%", height: "100%",
  background: "linear-gradient(180deg,var(--panel2),var(--base))", border: "1px solid var(--line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)", overflow: "hidden", display: "flex", flexDirection: "column",
};
const inp: CSSProperties = { background: "var(--tint)", border: "1px solid var(--line2)", color: "var(--txt)", fontSize: 10.5, padding: "4px 8px", outline: "none", fontFamily: "inherit", minWidth: 0 };
const lbl: CSSProperties = { fontSize: 8, letterSpacing: ".14em", color: "var(--txt3)", marginBottom: 6 };
const textButton: CSSProperties = { font: "inherit", color: "inherit", background: "transparent", border: "none", padding: 0 };

function Add({ on, busy }: { on: () => void; busy?: boolean }) {
  return <button type="button" onClick={on} disabled={busy} style={{ font: "inherit", border: "none", fontSize: 9, color: "var(--on-accent)", background: busy ? "var(--line2)" : "var(--accent)", padding: "4px 11px", fontWeight: 600, letterSpacing: ".06em", cursor: busy ? "default" : "pointer", flex: "none" }}>{busy ? "…" : "+ ADD"}</button>;
}
// Small destructive ✕ next to a listed row — mirrors the Add chip idiom.
function Del({ on, busy, label = "item" }: { on: () => void; busy?: boolean; label?: string }) {
  return <ConfirmDeleteButton label={label} onConfirm={on} disabled={busy} containerStyle={{ marginLeft: "auto" }} triggerStyle={{ fontSize: 8.5, color: "var(--crimson)", borderColor: "var(--crimson)", borderRadius: 2, padding: "2px 5px", opacity: 0.85 }} />;
}
const card: CSSProperties = { border: "1px solid var(--line2)", background: "var(--tint)", padding: "8px 10px", marginBottom: 7 };
const row: CSSProperties = { display: "flex", gap: 7, alignItems: "center", marginBottom: 9 };

// ----------------------------------------------------------------- Graphic novel
function GnAuthoring({ pid }: { pid: number }) {
  const { api } = useStudio();
  const requests = useRef(createLatestRequestGate()).current;
  useEffect(() => { requests.open(); return () => requests.close(); }, [requests]);
  const [pages, setPages] = useState<GnPageDTO[]>([]);
  const [panels, setPanels] = useState<Record<number, GnPanelDTO[]>>({});
  const [summary, setSummary] = useState("");
  const [draft, setDraft] = useState<Record<number, string>>({});
  const [loadErrors, setLoadErrors] = useState<Record<string, string>>({});
  const setLoadError = (key: string, error: unknown | null) => setLoadErrors((current) => {
    const next = { ...current };
    if (error == null) delete next[key];
    else next[key] = error instanceof Error ? error.message : String(error);
    return next;
  });
  const loadPages = async () => {
    const token = requests.begin("pages");
    try {
      const rows = await api.listGnPages(pid);
      if (requests.isCurrent(token)) { setPages(rows); setLoadError("pages", null); }
    } catch (error) {
      if (requests.isCurrent(token)) setLoadError("pages", error);
    }
  };
  const loadPanels = async (pageId: number) => {
    const key = `panels:${pageId}`;
    const token = requests.begin(key);
    try {
      const rows = await api.listGnPanels(pid, pageId);
      if (requests.isCurrent(token)) {
        setPanels((current) => ({ ...current, [pageId]: rows }));
        setLoadError(key, null);
      }
    } catch (error) {
      if (requests.isCurrent(token)) setLoadError(key, error);
    }
  };
  useEffect(() => { void loadPages(); return () => requests.invalidate("pages"); }, [api, pid, requests]);
  useEffect(() => {
    const ids = pages.flatMap((page) => page.id == null ? [] : [page.id]);
    for (const id of ids) void loadPanels(id);
    return () => { for (const id of ids) requests.invalidate(`panels:${id}`); };
  }, [api, pid, pages, requests]);
  const [syncMsg, setSyncMsg] = useState("");
  const [items, setItems] = useState<GnContinuityItemDTO[]>([]);
  const [appears, setAppears] = useState<Record<number, GnContinuityAppearanceDTO[]>>({});
  const [itemName, setItemName] = useState("");
  const [itemType, setItemType] = useState("prop");
  const [apPage, setApPage] = useState<Record<number, number | "">>({});
  const loadItems = async () => {
    const token = requests.begin("items");
    try {
      const rows = await api.listGnContinuityItems(pid);
      if (requests.isCurrent(token)) { setItems(rows); setLoadError("items", null); }
    } catch (error) {
      if (requests.isCurrent(token)) setLoadError("items", error);
    }
  };
  const loadAppearances = async (itemId: number) => {
    const key = `appearances:${itemId}`;
    const token = requests.begin(key);
    try {
      const rows = await api.listGnContinuityAppearances(pid, itemId);
      if (requests.isCurrent(token)) {
        setAppears((current) => ({ ...current, [itemId]: rows }));
        setLoadError(key, null);
      }
    } catch (error) {
      if (requests.isCurrent(token)) setLoadError(key, error);
    }
  };
  useEffect(() => { void loadItems(); return () => requests.invalidate("items"); }, [api, pid, requests]);
  useEffect(() => {
    const ids = items.flatMap((item) => item.id == null ? [] : [item.id]);
    for (const id of ids) void loadAppearances(id);
    return () => { for (const id of ids) requests.invalidate(`appearances:${id}`); };
  }, [api, pid, items, requests]);
  const pageNum = (id?: number | null) => { const p = pages.find((x) => x.id === id); return p ? `p${p.page_number}` : `#${id}`; };
  const addItem = async () => { const submitted = itemName; if (!submitted.trim()) return; setDelErr(""); try { await api.createGnContinuityItem(pid, { name: submitted, item_type: itemType }); setItemName((current) => current === submitted ? "" : current); await loadItems(); } catch (e) { setDelErr(`add failed — ${e instanceof Error ? e.message : String(e)}`); } };
  const addAppearance = async (itemId: number) => { const pg = apPage[itemId]; if (pg === "" || pg == null) return; setDelErr(""); try { await api.createGnContinuityAppearance(pid, itemId, { page_id: pg }); setApPage((current) => current[itemId] === pg ? { ...current, [itemId]: "" } : current); await loadAppearances(itemId); } catch (e) { setDelErr(`add failed — ${e instanceof Error ? e.message : String(e)}`); } };
  const addPage = async () => { const submitted = summary; if (!submitted.trim()) return; setDelErr(""); try { await api.createGnPage(pid, { summary: submitted }); setSummary((current) => current === submitted ? "" : current); await loadPages(); } catch (e) { setDelErr(`add failed — ${e instanceof Error ? e.message : String(e)}`); } };
  const [busyDel, setBusyDel] = useState<string | null>(null);
  const [delErr, setDelErr] = useState("");
  const delPage = async (id: number) => { setBusyDel(`pg${id}`); setDelErr(""); try { await api.deleteGnPage(pid, id); await loadPages(); } catch (e) { setDelErr(`delete failed — ${e instanceof Error ? e.message : String(e)}`); } finally { setBusyDel(null); } };
  const delPanel = async (pageId: number, id: number) => { setBusyDel(`pn${id}`); setDelErr(""); try { await api.deleteGnPanel(pid, id); await loadPanels(pageId); } catch (e) { setDelErr(`delete failed — ${e instanceof Error ? e.message : String(e)}`); } finally { setBusyDel(null); } };
  const delItem = async (id: number) => { setBusyDel(`it${id}`); setDelErr(""); try { await api.deleteGnContinuityItem(pid, id); await loadItems(); } catch (e) { setDelErr(`delete failed — ${e instanceof Error ? e.message : String(e)}`); } finally { setBusyDel(null); } };
  const delAppearance = async (itemId: number, id: number) => { setBusyDel(`ap${id}`); setDelErr(""); try { await api.deleteGnContinuityAppearance(pid, id); await loadAppearances(itemId); } catch (e) { setDelErr(`delete failed — ${e instanceof Error ? e.message : String(e)}`); } finally { setBusyDel(null); } };
  // Bridge authored GN-script scene text into structured page/panel rows the graph reads.
  const syncFromScenes = async () => {
    setSyncMsg("syncing…");
    try {
      const r = await api.syncGnFromScenes(pid);
      setSyncMsg(r.skipped ? "already synced (pages exist)" : `synced ${r.pages} pages · ${r.panels} panels`);
      await loadPages();
    } catch (e) {
      setSyncMsg(`sync failed — ${e instanceof Error ? e.message : String(e)}`);
    }
  };
  const addPanel = async (pageId: number) => { const submitted = draft[pageId] || ""; const d = submitted.trim(); if (!d) return; const [description, motifs] = d.split("|"); setDelErr(""); try { await api.createGnPanel(pid, pageId, { description: (description ?? "").trim(), visual_motifs: (motifs || "").split(",").map((s) => s.trim()).filter(Boolean) }); setDraft((current) => current[pageId] === submitted ? { ...current, [pageId]: "" } : current); await loadPanels(pageId); } catch (e) { setDelErr(`add failed — ${e instanceof Error ? e.message : String(e)}`); } };
  const loadError = [...new Set(Object.values(loadErrors))].join("; ");
  return (
    <>
      <div style={{ ...row, justifyContent: "space-between" }}>
        <span style={{ fontSize: 8.5, color: "var(--txt3)", letterSpacing: ".06em" }}>parse PAGE/PANEL scene text → structured rows the graph reads</span>
        <button type="button" onClick={() => { void syncFromScenes(); }} style={{ font: "inherit", fontSize: 9, color: "var(--accent)", border: "1px solid var(--line-cy)", background: "rgba(176,124,255,.08)", padding: "4px 10px", cursor: "pointer", letterSpacing: ".06em" }}>⟳ SYNC FROM SCENES</button>
      </div>
      {syncMsg && <div style={{ fontSize: 9, color: "var(--txt2)", marginBottom: 8 }}>{syncMsg}</div>}
      <div style={lbl}>ADD PAGE</div>
      <div style={row}><input value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="page summary, e.g. “The vault at night”" aria-label="New graphic-novel page summary" style={{ ...inp, flex: 1 }} /><Add on={addPage} /></div>
      {loadError && <div style={{ fontSize: 9, color: "var(--amber)", marginBottom: 6 }}>load failed — {loadError}</div>}
      {delErr && <div style={{ fontSize: 9, color: "var(--crimson)", marginBottom: 6 }}>{delErr}</div>}
      {pages.map((p) => (
        <div key={p.id} style={card}>
          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <div style={{ fontFamily: "'Chakra Petch'", fontSize: 11, color: "var(--strong)" }}>PAGE {p.page_number} <span style={{ color: "var(--txt2)", fontWeight: 400 }}>· {p.summary}</span></div>
            {p.id != null && <Del label={`page ${p.page_number}`} on={() => delPage(p.id!)} busy={busyDel === `pg${p.id}`} />}
          </div>
          <div style={{ marginTop: 6, paddingLeft: 10, borderLeft: "1px solid var(--line2)" }}>
            {(panels[p.id ?? -1] || []).map((pn) => (
              <div key={pn.id} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10, color: "var(--txt2)", marginBottom: 3 }}><span>▸ {pn.description}{(pn.visual_motifs || []).length ? <span style={{ color: "var(--cyan)" }}> · {(pn.visual_motifs || []).join(", ")}</span> : null}</span>{p.id != null && pn.id != null && <Del label={`panel ${pn.panel_number}`} on={() => delPanel(p.id!, pn.id!)} busy={busyDel === `pn${pn.id}`} />}</div>
            ))}
            <div style={{ display: "flex", gap: 6, marginTop: 5 }}>
              <input value={draft[p.id ?? -1] || ""} onChange={(e) => setDraft((m) => ({ ...m, [p.id!]: e.target.value }))} placeholder="panel description | motif, motif" aria-label={`New panel for page ${p.page_number}`} style={{ ...inp, flex: 1, fontSize: 9.5 }} />
              <Add on={() => p.id && addPanel(p.id)} />
            </div>
          </div>
        </div>
      ))}

      <div style={{ ...lbl, marginTop: 12 }}>CONTINUITY OBJECTS (object → page edges)</div>
      <div style={row}>
        <input value={itemName} onChange={(e) => setItemName(e.target.value)} placeholder="object name, e.g. “the watch”" aria-label="New continuity object name" style={{ ...inp, flex: 1 }} />
        <select value={itemType} onChange={(e) => setItemType(e.target.value)} aria-label="Continuity object type" style={{ ...inp, width: 88 }}>{["prop", "setting", "character", "other"].map((t) => <option key={t} value={t}>{t}</option>)}</select>
        <Add on={addItem} />
      </div>
      {items.map((it) => (
        <div key={it.id} style={{ ...card, padding: "7px 10px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10.5, color: "var(--strong)" }}>
            <span>◆ {it.name} <span style={{ color: "var(--txt3)", fontWeight: 400 }}>· {it.item_type}</span></span>
            {(appears[it.id ?? -1] || []).length ? <span style={{ color: "var(--cyan)", fontSize: 9, display: "inline-flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>{(appears[it.id ?? -1] || []).map((ap) => <span key={ap.id} style={{ display: "inline-flex", alignItems: "center", gap: 3 }}>{pageNum(ap.page_id)}{ap.id != null && <ConfirmDeleteButton label={`${it.name} appearance on ${pageNum(ap.page_id)}`} onConfirm={() => { if (it.id != null) void delAppearance(it.id, ap.id!); }} disabled={busyDel === `ap${ap.id}`} triggerStyle={{ border: "none", color: "var(--crimson)", fontSize: 9, padding: 0, opacity: 0.85 }} />}</span>)}</span> : null}
            {it.id != null && <Del label={it.name || `continuity item ${it.id}`} on={() => delItem(it.id!)} busy={busyDel === `it${it.id}`} />}
          </div>
          {pages.length > 0 && (
            <div style={{ display: "flex", gap: 5, marginTop: 4 }}>
              <select value={apPage[it.id ?? -1] == null || apPage[it.id ?? -1] === "" ? "" : String(apPage[it.id ?? -1])} onChange={(e) => setApPage((m) => ({ ...m, [it.id!]: e.target.value ? Number(e.target.value) : "" }))} aria-label={`Page appearance for ${it.name}`} style={{ ...inp, flex: 1, fontSize: 9 }}><option value="">— appears on page —</option>{pages.map((p) => <option key={p.id} value={String(p.id)}>PAGE {p.page_number}</option>)}</select>
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
  const requests = useRef(createLatestRequestGate()).current;
  useEffect(() => { requests.open(); return () => requests.close(); }, [requests]);
  const [scenes, setScenes] = useState<SceneDTO[]>([]);
  const [sel, setSel] = useState<number | null>(null);
  const selectedSceneRef = useRef<number | null>(sel);
  selectedSceneRef.current = sel;
  const [wkw, setWkw] = useState("");
  const [notes, setNotes] = useState<ContinuityMemoryDTO[]>([]);
  const [target, setTarget] = useState("");
  const [kind, setKind] = useState("state");
  const [msg, setMsg] = useState("");
  const [loadErrors, setLoadErrors] = useState<Record<string, string>>({});
  const setLoadError = (key: string, error: unknown | null) => setLoadErrors((current) => {
    const next = { ...current };
    if (error == null) delete next[key];
    else next[key] = error instanceof Error ? error.message : String(error);
    return next;
  });
  useEffect(() => {
    const token = requests.begin("scenes");
    void api.listScenes(pid).then((rows) => {
      if (!requests.isCurrent(token)) return;
      setScenes(rows);
      setLoadError("scenes", null);
      if (selectedSceneRef.current == null && rows[0]?.id != null) setSel(rows[0].id!);
    }).catch((error) => {
      if (requests.isCurrent(token)) setLoadError("scenes", error);
    });
    return () => requests.invalidate("scenes");
  }, [api, pid, requests]);
  const addNote = async () => { const sceneId = sel; const submitted = target; const submittedKind = kind; if (sceneId == null || !submitted.trim()) return; setDelErr(""); try { await api.addContinuity(pid, sceneId, { target: submitted, kind: submittedKind, value: "" }); setTarget((current) => current === submitted ? "" : current); await reloadNotes(sceneId); } catch (error) { setDelErr(`add failed — ${error instanceof Error ? error.message : String(error)}`); } };
  const [busyDel, setBusyDel] = useState<string | null>(null);
  const [delErr, setDelErr] = useState("");
  const [savingEdit, setSavingEdit] = useState(false);
  const [wkwConflict, setWkwConflict] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [eTarget, setETarget] = useState("");
  const [eValue, setEValue] = useState("");
  const [eKind, setEKind] = useState("state");
  const mounted = useMountedRef();
  const wkwDraftRef = useRef<{ sceneId: number; original: string; text: string; revision: string } | null>(null);
  const wkwInFlightRef = useRef<Promise<boolean> | null>(null);
  const forceWkwOverwriteRef = useRef(false);
  const continuityDraftRef = useRef<{
    sceneId: number;
    id: number;
    original: { target: string; value: string; kind: string };
    value: { target: string; value: string; kind: string };
  } | null>(null);
  const continuityInFlightRef = useRef<Promise<boolean> | null>(null);
  const reloadNotes = async (sceneId = sel) => {
    if (sceneId == null) return;
    const key = `continuity:${sceneId}`;
    const token = requests.begin(key);
    try {
      const rows = await api.listContinuity(pid, sceneId);
      if (requests.isCurrent(token) && sceneId === selectedSceneRef.current) {
        setNotes(rows);
        setLoadError("continuity", null);
      }
    } catch (error) {
      if (requests.isCurrent(token) && sceneId === selectedSceneRef.current) {
        setLoadError("continuity", error);
      }
    }
  };
  const persistWkwRef = useRef<() => Promise<boolean>>(async () => true);
  persistWkwRef.current = async () => {
    if (wkwInFlightRef.current) return wkwInFlightRef.current;
    const draft = wkwDraftRef.current;
    if (!draft || draft.text === draft.original) return true;
    const operation = (async () => {
      if (mounted.current) { setSavingEdit(true); setMsg("saving…"); }
      try {
        const force = forceWkwOverwriteRef.current;
        forceWkwOverwriteRef.current = false;
        const updated = await trackProjectWrite(api.updateScene(pid, draft.sceneId, {
          who_knows_what: draft.text,
          ...(!force && draft.revision ? { expected_revision: draft.revision } : {}),
        }));
        if (wkwDraftRef.current?.sceneId === draft.sceneId) {
          wkwDraftRef.current = { ...wkwDraftRef.current, original: draft.text, revision: updated.revision ?? "" };
        }
        if (mounted.current) {
          setScenes((current) => current.map((scene) => scene.id === updated.id ? updated : scene));
          setWkwConflict(false);
          setMsg("saved who-knows");
        }
        return true;
      } catch (error) {
        if (mounted.current) {
          setWkwConflict(error instanceof ApiRequestError && error.code === "scene_conflict");
          setMsg(`failed — ${error instanceof Error ? error.message : String(error)}`);
        }
        return false;
      } finally {
        if (mounted.current) setSavingEdit(false);
      }
    })();
    wkwInFlightRef.current = operation;
    const saved = await operation;
    if (wkwInFlightRef.current === operation) wkwInFlightRef.current = null;
    if (saved && wkwDraftRef.current && wkwDraftRef.current.text !== wkwDraftRef.current.original) {
      return persistWkwRef.current();
    }
    return saved;
  };
  const persistContinuityRef = useRef<() => Promise<boolean>>(async () => true);
  persistContinuityRef.current = async () => {
    if (continuityInFlightRef.current) return continuityInFlightRef.current;
    const draft = continuityDraftRef.current;
    if (!draft) return true;
    const next = { ...draft.value, target: draft.value.target.trim() };
    if (!next.target) {
      if (mounted.current) setDelErr("continuity target cannot be empty — enter one or cancel");
      return false;
    }
    if (next.target === draft.original.target && next.value === draft.original.value && next.kind === draft.original.kind) {
      continuityDraftRef.current = null;
      if (mounted.current) setEditId(null);
      return true;
    }
    const operation = (async () => {
      if (mounted.current) { setSavingEdit(true); setDelErr(""); }
      try {
        await api.updateContinuity(pid, draft.sceneId, draft.id, next);
        const current = continuityDraftRef.current;
        if (current === draft) {
          continuityDraftRef.current = null;
          if (mounted.current) setEditId(null);
        } else if (current?.id === draft.id) {
          continuityDraftRef.current = { ...current, original: next };
        }
        if (mounted.current) reloadNotes(draft.sceneId);
        return true;
      } catch (error) {
        if (mounted.current) setDelErr(`update failed — ${error instanceof Error ? error.message : String(error)}`);
        return false;
      } finally {
        if (mounted.current) setSavingEdit(false);
      }
    })();
    continuityInFlightRef.current = operation;
    const saved = await operation;
    if (continuityInFlightRef.current === operation) continuityInFlightRef.current = null;
    if (saved && continuityDraftRef.current) return persistContinuityRef.current();
    return saved;
  };
  useEffect(() => registerProjectFlusher(async () => {
    if (!await persistContinuityRef.current()) return false;
    return persistWkwRef.current();
  }), []);
  useEffect(() => {
    if (sel == null) return;
    const scene = scenes.find((item) => item.id === sel);
    const text = scene?.who_knows_what ?? "";
    const current = wkwDraftRef.current;
    if (!current || current.sceneId !== sel || current.text === current.original) {
      wkwDraftRef.current = { sceneId: sel, original: text, text, revision: scene?.revision ?? "" };
      setWkwConflict(false);
      setWkw(text);
    }
    void reloadNotes(sel);
    return () => requests.invalidate(`continuity:${sel}`);
  }, [api, pid, sel, scenes, requests]);
  const saveWkw = async () => { await persistWkwRef.current(); };
  const reloadWkw = async () => {
    const draft = wkwDraftRef.current;
    if (!draft || savingEdit) return;
    setSavingEdit(true);
    try {
      const rows = await api.listScenes(pid);
      if (wkwDraftRef.current !== draft) throw new Error("The local field changed while reloading. Review it and choose again.");
      const latest = rows.find((scene) => scene.id === draft.sceneId);
      if (!latest) throw new Error("The scene no longer exists.");
      const text = latest.who_knows_what ?? "";
      setScenes(rows);
      wkwDraftRef.current = { sceneId: latest.id, original: text, text, revision: latest.revision ?? "" };
      setWkw(text); setWkwConflict(false); setMsg("reloaded newer who-knows");
    } catch (error) {
      setMsg(`reload failed — ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setSavingEdit(false);
    }
  };
  const overwriteWkw = async () => {
    if (savingEdit) return;
    forceWkwOverwriteRef.current = true;
    const saved = await persistWkwRef.current();
    if (!saved) forceWkwOverwriteRef.current = false;
  };
  const changeScene = async (next: number | null) => {
    if (next === sel) return;
    if (!await persistContinuityRef.current()) return;
    if (!await persistWkwRef.current()) return;
    continuityDraftRef.current = null;
    setEditId(null);
    selectedSceneRef.current = next;
    setNotes([]);
    setWkw("");
    setSel(next);
  };
  const changeWkw = (text: string) => {
    setWkw(text);
    if (sel != null) {
      const current = wkwDraftRef.current;
      wkwDraftRef.current = current?.sceneId === sel
        ? { ...current, text }
        : { sceneId: sel, original: "", text, revision: scenes.find((scene) => scene.id === sel)?.revision ?? "" };
      markProjectSavePending();
    }
  };
  const delNote = async (id: number) => { if (sel == null) return; setBusyDel(`n${id}`); setDelErr(""); try { await api.deleteContinuity(pid, sel, id); await reloadNotes(); } catch (e) { setDelErr(`delete failed — ${e instanceof Error ? e.message : String(e)}`); } finally { setBusyDel(null); } };
  const beginEdit = async (note: ContinuityMemoryDTO) => {
    if (note.id == null || sel == null) return;
    if (continuityDraftRef.current?.id !== note.id && !await persistContinuityRef.current()) return;
    const value = { target: note.target ?? "", value: note.value ?? "", kind: note.kind ?? "state" };
    continuityDraftRef.current = { sceneId: sel, id: note.id, original: value, value };
    setEditId(note.id); setETarget(value.target); setEValue(value.value); setEKind(value.kind);
  };
  const changeContinuity = (patch: Partial<{ target: string; value: string; kind: string }>) => {
    const draft = continuityDraftRef.current;
    if (!draft) return;
    continuityDraftRef.current = { ...draft, value: { ...draft.value, ...patch } };
    markProjectSavePending();
  };
  const cancelContinuityEdit = () => { continuityDraftRef.current = null; setEditId(null); setDelErr(""); };
  const saveNote = async (id: number) => {
    if (continuityDraftRef.current?.id !== id) return;
    await persistContinuityRef.current();
  };
  return (
    <>
      <div style={lbl}>SCENE (feeds the “knowledge” + “continuity” graph edges)</div>
      <div style={row}>
        <select value={sel == null ? "" : String(sel)} disabled={savingEdit} onChange={(e) => { void changeScene(e.target.value ? Number(e.target.value) : null); }} aria-label="Scene for graph fields" style={{ ...inp, flex: 1 }}>
          {scenes.map((s) => <option key={s.id} value={String(s.id)}>{s.title || `Scene ${s.id}`}</option>)}
        </select>
      </div>
      {Object.keys(loadErrors).length > 0 && <div role="alert" style={{ fontSize: 9, color: "var(--amber)", marginBottom: 6 }}>load failed — {[...new Set(Object.values(loadErrors))].join("; ")}</div>}
      <div style={{ ...lbl, marginTop: 10 }}>WHO KNOWS WHAT</div>
      <div style={row}>
        <input value={wkw} disabled={savingEdit} onChange={(e) => changeWkw(e.target.value)} placeholder="what a character knows here that others don’t" aria-label="Who knows what in this scene" style={{ ...inp, flex: 1 }} /><Add on={() => void saveWkw()} busy={savingEdit} />
      </div>
      {msg && <div style={{ fontSize: 9, color: "var(--txt2)", marginBottom: 6 }}>{msg}</div>}
      {wkwConflict && <div role="alert" style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 7, color: "var(--crimson)", fontSize: 9 }}><span style={{ flex: 1 }}>Newer scene data exists; your local field is preserved.</span><button type="button" disabled={savingEdit} onClick={() => { void reloadWkw(); }} style={{ ...textButton, cursor: savingEdit ? "default" : "pointer", color: "var(--txt2)" }}>DISCARD · RELOAD</button><button type="button" disabled={savingEdit} onClick={() => { void overwriteWkw(); }} style={{ ...textButton, cursor: savingEdit ? "default" : "pointer", color: "var(--crimson)" }}>OVERWRITE</button></div>}
      <div style={{ ...lbl, marginTop: 8 }}>CONTINUITY NOTES (track an element across scenes)</div>
      <div style={row}>
        <input value={target} onChange={(e) => setTarget(e.target.value)} placeholder="element, e.g. “the salt ledger”" aria-label="New continuity-note target" style={{ ...inp, flex: 1 }} />
        <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="New continuity-note kind" style={{ ...inp, width: 92 }}>{["state", "object", "wound", "secret"].map((k) => <option key={k} value={k}>{k}</option>)}</select>
        <Add on={addNote} />
      </div>
      {delErr && <div style={{ fontSize: 9, color: "var(--crimson)", marginBottom: 6 }}>{delErr}</div>}
      {notes.map((n) => (
        <div key={n.id} style={{ ...card, padding: "5px 10px", display: "flex", alignItems: "center", gap: 6, fontSize: 10, color: "var(--txt2)" }}>
          {editId === n.id ? (
            <>
              <select value={eKind} disabled={savingEdit} onChange={(e) => { setEKind(e.target.value); changeContinuity({ kind: e.target.value }); }} aria-label="Continuity-note kind" style={{ ...inp, width: 82, fontSize: 9 }}>{["state", "object", "wound", "secret"].map((k) => <option key={k} value={k}>{k}</option>)}</select>
              <input value={eTarget} disabled={savingEdit} onChange={(e) => { setETarget(e.target.value); changeContinuity({ target: e.target.value }); }} placeholder="element" aria-label="Continuity-note target" style={{ ...inp, flex: 1, fontSize: 9 }} />
              <input value={eValue} disabled={savingEdit} onChange={(e) => { setEValue(e.target.value); changeContinuity({ value: e.target.value }); }} placeholder="value" aria-label="Continuity-note value" style={{ ...inp, flex: 1, fontSize: 9 }} />
              <button type="button" disabled={savingEdit || n.id == null} onClick={() => { if (n.id != null) void saveNote(n.id); }} style={{ ...textButton, fontSize: 9, color: "var(--accent)", cursor: savingEdit ? "default" : "pointer", letterSpacing: ".06em" }}>SAVE</button>
              <button type="button" disabled={savingEdit} onClick={cancelContinuityEdit} aria-label="Cancel continuity edit" style={{ ...textButton, fontSize: 9, color: "var(--txt3)", cursor: savingEdit ? "default" : "pointer" }}>✕</button>
            </>
          ) : (
            <>
              <button type="button" onClick={() => { void beginEdit(n); }} title="Edit continuity note" style={{ ...textButton, flex: 1, textAlign: "left", cursor: "text" }}><span style={{ color: "var(--cyan)" }}>{n.kind}</span> · {n.target}{n.value ? <span style={{ color: "var(--txt3)" }}> — {n.value}</span> : null}</button>
              {n.id != null && <Del label={`continuity note ${n.target}`} on={() => delNote(n.id!)} busy={busyDel === `n${n.id}`} />}
            </>
          )}
        </div>
      ))}
    </>
  );
}

// ----------------------------------------------------------------- Stage
function StageAuthoring({ pid }: { pid: number }) {
  const { api } = useStudio();
  const requests = useRef(createLatestRequestGate()).current;
  useEffect(() => { requests.open(); return () => requests.close(); }, [requests]);
  const [sceneId, setSceneId] = useState(1);
  const sceneIdRef = useRef(sceneId);
  sceneIdRef.current = sceneId;
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
  const [loadErrors, setLoadErrors] = useState<Record<string, string>>({});
  const setLoadError = (key: string, error: unknown | null) => setLoadErrors((current) => {
    const next = { ...current };
    if (error == null) delete next[key];
    else next[key] = error instanceof Error ? error.message : String(error);
    return next;
  });

  const load = async (targetSceneId = sceneIdRef.current) => {
    const key = `stage:${targetSceneId}`;
    const token = requests.begin(key);
    try {
      const [nextCues, nextEntrances, nextBusiness] = await Promise.all([
        api.listStageCues(pid, targetSceneId),
        api.listStageEntrances(pid, targetSceneId),
        api.listStageBusiness(pid, targetSceneId),
      ]);
      if (requests.isCurrent(token) && sceneIdRef.current === targetSceneId) {
        setCues(nextCues); setEntrances(nextEntrances); setBiz(nextBusiness); setLoadError("scene", null);
      }
    } catch (error) {
      if (requests.isCurrent(token) && sceneIdRef.current === targetSceneId) {
        setLoadError("scene", error);
      }
    }
  };
  useEffect(() => {
    setCues([]); setEntrances([]); setBiz([]);
    setLoadError("scene", null);
    void load(sceneId);
    return () => requests.invalidate(`stage:${sceneId}`);
  }, [api, pid, sceneId, requests]);
  // characters + PSYKE 'object' props drive the entrance/business pickers.
  useEffect(() => {
    const token = requests.begin("stage-metadata");
    void Promise.all([api.listCharacters(pid), api.listPsyke(pid)]).then(([nextChars, entries]) => {
      if (!requests.isCurrent(token)) return;
      setChars(nextChars);
      setProps(entries.filter((entry) => entry.type === "object"));
      setLoadError("metadata", null);
    }).catch((error) => {
      if (requests.isCurrent(token)) setLoadError("metadata", error);
    });
    return () => requests.invalidate("stage-metadata");
  }, [api, pid, requests]);

  const charName = (id?: number | null) => chars.find((c) => c.id === id)?.name ?? (id != null ? `#${id}` : "—");
  const propName = (id?: number | null) => props.find((p) => p.id === id)?.name ?? (id != null ? `#${id}` : "—");
  const addCue = async () => { const submitted = cueText; const submittedType = cueType; if (!submitted.trim()) return; const target = sceneId; setDelErr(""); try { await api.createStageCue(pid, target, { cue_type: submittedType, cue_text: submitted }); setCueText((current) => current === submitted ? "" : current); await load(target); } catch (e) { setDelErr(`add failed — ${e instanceof Error ? e.message : String(e)}`); } };
  const addEntrance = async () => { const target = sceneId; const submittedType = entType; const submittedChar = entChar; const submittedCue = entCue; setDelErr(""); try { await api.createStageEntrance(pid, target, { type: submittedType, character_id: submittedChar === "" ? null : submittedChar, cue_text: submittedCue }); setEntCue((current) => current === submittedCue ? "" : current); setEntChar((current) => current === submittedChar ? "" : current); await load(target); } catch (e) { setDelErr(`add failed — ${e instanceof Error ? e.message : String(e)}`); } };
  const addBiz = async () => { if (bizProp === "") return; const target = sceneId; const submittedProp = bizProp; const submittedChar = bizChar; const submittedAction = bizAction; setDelErr(""); try { await api.createStageBusiness(pid, target, { prop_psyke_entry_id: submittedProp, character_id: submittedChar === "" ? null : submittedChar, stage_action: submittedAction }); setBizAction((current) => current === submittedAction ? "" : current); setBizProp((current) => current === submittedProp ? "" : current); setBizChar((current) => current === submittedChar ? "" : current); await load(target); } catch (e) { setDelErr(`add failed — ${e instanceof Error ? e.message : String(e)}`); } };
  const [busyDel, setBusyDel] = useState<string | null>(null);
  const [delErr, setDelErr] = useState("");
  const delCue = async (id: number) => { const target = sceneId; setBusyDel(`cue${id}`); setDelErr(""); try { await api.deleteStageCue(pid, id); await load(target); } catch (e) { setDelErr(`delete failed — ${e instanceof Error ? e.message : String(e)}`); } finally { setBusyDel(null); } };
  const delEntrance = async (id: number) => { const target = sceneId; setBusyDel(`ent${id}`); setDelErr(""); try { await api.deleteStageEntrance(pid, id); await load(target); } catch (e) { setDelErr(`delete failed — ${e instanceof Error ? e.message : String(e)}`); } finally { setBusyDel(null); } };
  const delBiz = async (id: number) => { const target = sceneId; setBusyDel(`biz${id}`); setDelErr(""); try { await api.deleteStageBusiness(pid, id); await load(target); } catch (e) { setDelErr(`delete failed — ${e instanceof Error ? e.message : String(e)}`); } finally { setBusyDel(null); } };
  // Parse stage directions across all scenes into cue/entrance/offstage rows.
  const syncStage = async () => {
    setStageSyncMsg("syncing…");
    try { const r = await api.syncStageFromScenes(pid); setStageSyncMsg(`synced ${r.cues} cues · ${r.entrances} entrances · ${r.offstage} offstage`); await load(); }
    catch (e) { setStageSyncMsg(`sync failed — ${e instanceof Error ? e.message : String(e)}`); }
  };

  return (
    <>
      <div style={{ ...row, justifyContent: "space-between" }}>
        <label style={{ fontSize: 8.5, color: "var(--txt3)" }}>SCENE <input type="number" value={sceneId} onChange={(e) => { const next = Number(e.target.value) || 1; sceneIdRef.current = next; setSceneId(next); }} aria-label="Stage scene id" style={{ ...inp, width: 60 }} /></label>
        <button type="button" onClick={() => { void syncStage(); }} style={{ font: "inherit", fontSize: 9, color: "var(--accent)", border: "1px solid var(--line-cy)", background: "rgba(176,124,255,.08)", padding: "4px 10px", cursor: "pointer", letterSpacing: ".06em" }}>⟳ SYNC FROM SCENES</button>
      </div>
      {stageSyncMsg && <div style={{ fontSize: 9, color: "var(--txt2)", marginBottom: 8 }}>{stageSyncMsg}</div>}
      {Object.keys(loadErrors).length > 0 && <div role="alert" style={{ fontSize: 9, color: "var(--amber)", marginBottom: 8 }}>load failed — {[...new Set(Object.values(loadErrors))].join("; ")}</div>}

      <div style={lbl}>ADD CUE</div>
      <div style={row}>
        <select value={cueType} onChange={(e) => setCueType(e.target.value)} aria-label="Stage cue type" style={{ ...inp, width: 90 }}>{["light", "sound", "music", "prop", "movement", "other"].map((t) => <option key={t} value={t}>{t}</option>)}</select>
        <input value={cueText} onChange={(e) => setCueText(e.target.value)} placeholder="cue text, e.g. “lights snap up”" aria-label="Stage cue text" style={{ ...inp, flex: 1 }} /><Add on={addCue} />
      </div>
      {delErr && <div style={{ fontSize: 9, color: "var(--crimson)", marginBottom: 6 }}>{delErr}</div>}
      {cues.map((c) => <div key={c.id} style={{ ...card, padding: "6px 10px", display: "flex", gap: 9, alignItems: "center", fontSize: 10 }}><span style={{ color: "var(--amber)", letterSpacing: ".1em", width: 70 }}>{(c.cue_type || "").toUpperCase()}</span><span style={{ color: "var(--txt2)" }}>{c.cue_text}</span>{c.id != null && <Del label={`stage cue ${c.id}`} on={() => delCue(c.id!)} busy={busyDel === `cue${c.id}`} />}</div>)}

      <div style={{ ...lbl, marginTop: 12 }}>ADD ENTRANCE / EXIT</div>
      <div style={row}>
        <select value={entType} onChange={(e) => setEntType(e.target.value)} aria-label="Entrance or exit" style={{ ...inp, width: 84 }}>{["entrance", "exit"].map((t) => <option key={t} value={t}>{t}</option>)}</select>
        <select value={entChar === "" ? "" : String(entChar)} onChange={(e) => setEntChar(e.target.value ? Number(e.target.value) : "")} aria-label="Entrance or exit character" style={{ ...inp, flex: 1 }}><option value="">— character —</option>{chars.map((c) => <option key={c.id} value={String(c.id)}>{c.name}</option>)}</select>
        <input value={entCue} onChange={(e) => setEntCue(e.target.value)} placeholder="cue text" aria-label="Entrance or exit cue text" style={{ ...inp, flex: 1 }} /><Add on={addEntrance} />
      </div>
      {entrances.map((en) => <div key={en.id} style={{ ...card, padding: "6px 10px", display: "flex", gap: 9, alignItems: "center", fontSize: 10 }}><span style={{ color: "var(--cyan)", letterSpacing: ".1em", width: 70 }}>{(en.type || "").toUpperCase()}</span><span style={{ color: "var(--strong)" }}>{charName(en.character_id)}</span><span style={{ color: "var(--txt2)" }}>{en.cue_text}</span>{en.id != null && <Del label={`${en.type || "stage"} ${en.id}`} on={() => delEntrance(en.id!)} busy={busyDel === `ent${en.id}`} />}</div>)}

      <div style={{ ...lbl, marginTop: 12 }}>ADD STAGE BUSINESS (prop)</div>
      <div style={row}>
        <select value={bizProp === "" ? "" : String(bizProp)} onChange={(e) => setBizProp(e.target.value ? Number(e.target.value) : "")} aria-label="Stage-business prop" style={{ ...inp, flex: 1 }}><option value="">— prop (PSYKE object) —</option>{props.map((p) => <option key={p.id} value={String(p.id)}>{p.name}</option>)}</select>
        <select value={bizChar === "" ? "" : String(bizChar)} onChange={(e) => setBizChar(e.target.value ? Number(e.target.value) : "")} aria-label="Stage-business character" style={{ ...inp, width: 120 }}><option value="">— character —</option>{chars.map((c) => <option key={c.id} value={String(c.id)}>{c.name}</option>)}</select>
        <input value={bizAction} onChange={(e) => setBizAction(e.target.value)} placeholder="stage action, e.g. “pockets the watch”" aria-label="Stage-business action" style={{ ...inp, flex: 1 }} /><Add on={addBiz} />
      </div>
      {props.length === 0 && <div style={{ fontSize: 9, color: "var(--txt3)", fontStyle: "italic", marginBottom: 7 }}>Add a PSYKE “object” entry to use as a prop.</div>}
      {biz.map((b) => <div key={b.id} style={{ ...card, padding: "6px 10px", display: "flex", gap: 9, alignItems: "center", fontSize: 10 }}><span style={{ color: "var(--green)", width: 90 }}>{propName(b.prop_psyke_entry_id)}</span><span style={{ color: "var(--strong)", width: 70 }}>{charName(b.character_id)}</span><span style={{ color: "var(--txt2)" }}>{b.stage_action}</span>{b.id != null && <Del label={`stage business ${b.id}`} on={() => delBiz(b.id!)} busy={busyDel === `biz${b.id}`} />}</div>)}
    </>
  );
}

// ----------------------------------------------------------------- Series
function SeriesAuthoring({ pid }: { pid: number }) {
  const { api } = useStudio();
  const requests = useRef(createLatestRequestGate()).current;
  useEffect(() => { requests.open(); return () => requests.close(); }, [requests]);
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
  const [loadErrors, setLoadErrors] = useState<Record<string, string>>({});
  const setLoadError = (key: string, error: unknown | null) => setLoadErrors((current) => {
    const next = { ...current };
    if (error == null) delete next[key];
    else next[key] = error instanceof Error ? error.message : String(error);
    return next;
  });
  const loadAll = async () => {
    const token = requests.begin("series");
    try {
      const [nextSeasons, nextEpisodes, nextArcs, entries] = await Promise.all([
        api.listSeasons(pid), api.listEpisodes(pid), api.listSeriesArcs(pid), api.listPsyke(pid),
      ]);
      if (!requests.isCurrent(token)) return;
      setSeasons(nextSeasons); setEpisodes(nextEpisodes); setArcs(nextArcs);
      setChars(entries.filter((entry) => entry.type === "character"));
      setLoadError("series", null);
    } catch (error) {
      if (requests.isCurrent(token)) setLoadError("series", error);
    }
  };
  const loadPlotlines = async (episodeId: number) => {
    const key = `plotlines:${episodeId}`;
    const token = requests.begin(key);
    try {
      const rows = await api.listEpisodePlotlines(pid, episodeId);
      if (requests.isCurrent(token)) {
        setPlotlines((current) => ({ ...current, [episodeId]: rows }));
        setLoadError(key, null);
      }
    } catch (error) {
      if (requests.isCurrent(token)) setLoadError(key, error);
    }
  };
  useEffect(() => { void loadAll(); return () => requests.invalidate("series"); }, [api, pid, requests]);
  useEffect(() => {
    const ids = episodes.flatMap((episode) => episode.id == null ? [] : [episode.id]);
    for (const id of ids) void loadPlotlines(id);
    return () => { for (const id of ids) requests.invalidate(`plotlines:${id}`); };
  }, [api, pid, episodes, requests]);
  const epLabel = (id?: number | null) => { const e = episodes.find((x) => x.id === id); return e ? `EP${e.episode_number} ${e.title ?? ""}`.trim() : (id != null ? `#${id}` : "—"); };
  const addSeason = async () => { const submitted = seasonTitle; if (!submitted.trim()) return; setDelErr(""); try { await api.createSeason(pid, { title: submitted }); setSeasonTitle((current) => current === submitted ? "" : current); await loadAll(); } catch (e) { setDelErr(`add failed — ${e instanceof Error ? e.message : String(e)}`); } };
  const addEpisode = async (seasonId: number) => { const submitted = epDraft[seasonId] || ""; const title = submitted.trim(); if (!title) return; setDelErr(""); try { await api.createEpisode(pid, seasonId, { title }); setEpDraft((current) => current[seasonId] === submitted ? { ...current, [seasonId]: "" } : current); await loadAll(); } catch (e) { setDelErr(`add failed — ${e instanceof Error ? e.message : String(e)}`); } };
  const [busyDel, setBusyDel] = useState<string | null>(null);
  const [delErr, setDelErr] = useState("");
  const [editKey, setEditKey] = useState<string | null>(null);
  const [editVal, setEditVal] = useState("");
  const [renameBusy, setRenameBusy] = useState(false);
  const mounted = useMountedRef();
  const loadAllRef = useRef(loadAll);
  loadAllRef.current = loadAll;
  const renameDraftRef = useRef<{
    key: string;
    kind: "season" | "episode";
    id: number;
    original: string;
    text: string;
  } | null>(null);
  const renameInFlightRef = useRef<Promise<boolean> | null>(null);
  const persistRenameRef = useRef<() => Promise<boolean>>(async () => true);
  persistRenameRef.current = async () => {
    if (renameInFlightRef.current) return renameInFlightRef.current;
    const draft = renameDraftRef.current;
    if (!draft) return true;
    const title = draft.text.trim();
    if (!title) {
      if (mounted.current) setDelErr("title cannot be empty — enter one or press Esc to cancel");
      return false;
    }
    if (title === draft.original) {
      renameDraftRef.current = null;
      if (mounted.current) setEditKey(null);
      return true;
    }
    const operation = (async () => {
      if (mounted.current) { setRenameBusy(true); setDelErr(""); }
      try {
        if (draft.kind === "season") await api.updateSeason(pid, draft.id, { title });
        else await api.updateEpisode(pid, draft.id, { title });
        const current = renameDraftRef.current;
        if (current === draft) {
          renameDraftRef.current = null;
          if (mounted.current) setEditKey(null);
        } else if (current?.key === draft.key) {
          renameDraftRef.current = { ...current, original: title };
        }
        if (mounted.current) loadAllRef.current();
        return true;
      } catch (error) {
        if (mounted.current) setDelErr(`rename failed — ${error instanceof Error ? error.message : String(error)}`);
        return false;
      } finally {
        if (mounted.current) setRenameBusy(false);
      }
    })();
    renameInFlightRef.current = operation;
    const saved = await operation;
    if (renameInFlightRef.current === operation) renameInFlightRef.current = null;
    if (saved && renameDraftRef.current) return persistRenameRef.current();
    return saved;
  };
  useEffect(() => registerProjectFlusher(() => persistRenameRef.current()), []);
  const startRename = async (kind: "season" | "episode", id: number, title: string) => {
    const key = `${kind === "season" ? "s" : "e"}${id}`;
    if (renameDraftRef.current?.key !== key && !await persistRenameRef.current()) return;
    renameDraftRef.current = { key, kind, id, original: title, text: title };
    setEditKey(key);
    setEditVal(title);
  };
  const changeRename = (text: string) => {
    setEditVal(text);
    if (renameDraftRef.current) renameDraftRef.current = { ...renameDraftRef.current, text };
    markProjectSavePending();
  };
  const cancelRename = () => { renameDraftRef.current = null; setEditKey(null); setDelErr(""); };
  const delSeason = async (id: number) => { if (!await persistRenameRef.current()) return; setBusyDel(`s${id}`); setDelErr(""); try { await api.deleteSeason(pid, id); await loadAll(); } catch (e) { setDelErr(`delete failed — ${e instanceof Error ? e.message : String(e)}`); } finally { setBusyDel(null); } };
  const delEpisode = async (id: number) => { if (!await persistRenameRef.current()) return; setBusyDel(`e${id}`); setDelErr(""); try { await api.deleteEpisode(pid, id); await loadAll(); } catch (e) { setDelErr(`delete failed — ${e instanceof Error ? e.message : String(e)}`); } finally { setBusyDel(null); } };
  const delArc = async (id: number) => { setBusyDel(`arc${id}`); setDelErr(""); try { await api.deleteSeriesArc(pid, id); await loadAll(); } catch (e) { setDelErr(`delete failed — ${e instanceof Error ? e.message : String(e)}`); } finally { setBusyDel(null); } };
  const delPlotline = async (episodeId: number, id: number) => { setBusyDel(`pl${id}`); setDelErr(""); try { await api.deleteEpisodePlotline(pid, id); await loadPlotlines(episodeId); } catch (e) { setDelErr(`delete failed — ${e instanceof Error ? e.message : String(e)}`); } finally { setBusyDel(null); } };
  const saveSeasonTitle = async (id: number) => { if (renameDraftRef.current?.kind === "season" && renameDraftRef.current.id === id) await persistRenameRef.current(); };
  const saveEpisodeTitle = async (id: number) => { if (renameDraftRef.current?.kind === "episode" && renameDraftRef.current.id === id) await persistRenameRef.current(); };
  const addPlotline = async (episodeId: number) => { const submitted = plDraft[episodeId] || ""; const title = submitted.trim(); if (!title) return; setDelErr(""); try { await api.createEpisodePlotline(pid, episodeId, { type: "A", title }); setPlDraft((current) => current[episodeId] === submitted ? { ...current, [episodeId]: "" } : current); await loadPlotlines(episodeId); } catch (e) { setDelErr(`add failed — ${e instanceof Error ? e.message : String(e)}`); } };
  // Merge a per-episode status (echo edges) + an optional continuity flag (contradict)
  // onto the chosen PSYKE character's series memory.
  const setMemory = async () => {
    if (memChar === "") return;
    const submittedChar = memChar;
    const submittedEpisode = memEp;
    const submittedStatus = memStatus;
    const submittedFlags = memFlags;
    setDelErr("");
    try {
      const cur = await api.getSeriesMemory(pid, submittedChar);
      const csbe = { ...(cur.current_status_by_episode || {}) };
      if (submittedEpisode !== "" && submittedStatus.trim()) csbe[String(submittedEpisode)] = submittedStatus.trim();
      await api.setSeriesMemory(pid, submittedChar, { continuity_flags: submittedFlags || cur.continuity_flags || "", current_status_by_episode: csbe });
      setMemStatus((current) => current === submittedStatus ? "" : current);
      setMemEp((current) => current === submittedEpisode ? "" : current);
    } catch (e) {
      setDelErr(`memory update failed — ${e instanceof Error ? e.message : String(e)}`);
    }
  };
  // Bind the arc to its setup/payoff episodes + status — these are exactly what the
  // series graph enricher reads to emit sets_up / pays_off / resolves / escalates edges.
  const addArc = async () => {
    const submittedTitle = arcTitle;
    const submittedSetup = arcSetup;
    const submittedPayoff = arcPayoff;
    const submittedStatus = arcStatus;
    if (!submittedTitle.trim()) return;
    setDelErr("");
    try {
      await api.createSeriesArc(pid, {
        title: submittedTitle, scope: "series", status: submittedStatus,
        setup_episode_id: submittedSetup === "" ? null : submittedSetup,
        payoff_episode_id: submittedPayoff === "" ? null : submittedPayoff,
      });
      setArcTitle((current) => current === submittedTitle ? "" : current);
      setArcSetup((current) => current === submittedSetup ? "" : current);
      setArcPayoff((current) => current === submittedPayoff ? "" : current);
      await loadAll();
    } catch (e) {
      setDelErr(`add failed — ${e instanceof Error ? e.message : String(e)}`);
    }
  };
  return (
    <>
      <div style={lbl}>ADD SEASON</div>
      <div style={row}><input value={seasonTitle} onChange={(e) => setSeasonTitle(e.target.value)} placeholder="season title" aria-label="New season title" style={{ ...inp, flex: 1 }} /><Add on={addSeason} /></div>
      {Object.keys(loadErrors).length > 0 && <div role="alert" style={{ fontSize: 9, color: "var(--amber)", marginBottom: 6 }}>load failed — {[...new Set(Object.values(loadErrors))].join("; ")}</div>}
      {delErr && <div style={{ fontSize: 9, color: "var(--crimson)", marginBottom: 6 }}>{delErr}</div>}
      {seasons.map((s) => (
        <div key={s.id} style={card}>
          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <span style={{ fontFamily: "'Chakra Petch'", fontSize: 11, color: "var(--strong)" }}>SEASON {s.season_number} </span>
            {editKey === `s${s.id}` ? (
              <input autoFocus value={editVal} disabled={renameBusy} onChange={(ev) => changeRename(ev.target.value)} onBlur={() => { if (s.id != null) void saveSeasonTitle(s.id); }} onKeyDown={(ev) => { if (ev.key === "Enter" && s.id != null) void saveSeasonTitle(s.id); if (ev.key === "Escape") cancelRename(); }} aria-label={`Rename season ${s.season_number}`} style={{ ...inp, flex: 1, fontSize: 9.5 }} />
            ) : (
              <button type="button" onClick={() => { if (s.id != null) void startRename("season", s.id, s.title ?? ""); }} title="Rename season" style={{ ...textButton, color: "var(--txt2)", fontWeight: 400, fontSize: 11, cursor: "text" }}>· {s.title}</button>
            )}
            {s.id != null && <Del label={s.title || `season ${s.season_number}`} on={() => delSeason(s.id!)} busy={renameBusy || busyDel === `s${s.id}`} />}
          </div>
          <div style={{ marginTop: 6, paddingLeft: 10, borderLeft: "1px solid var(--line2)" }}>
            {episodes.filter((e) => e.season_id === s.id).map((e) => (
              <div key={e.id} style={{ marginBottom: 5 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10, color: "var(--txt2)" }}>
                  <span>▸ EP{e.episode_number}</span>
                  {editKey === `e${e.id}` ? (
                    <input autoFocus value={editVal} disabled={renameBusy} onChange={(ev) => changeRename(ev.target.value)} onBlur={() => { if (e.id != null) void saveEpisodeTitle(e.id); }} onKeyDown={(ev) => { if (ev.key === "Enter" && e.id != null) void saveEpisodeTitle(e.id); if (ev.key === "Escape") cancelRename(); }} aria-label={`Rename episode ${e.episode_number}`} style={{ ...inp, flex: 1, fontSize: 9 }} />
                  ) : (
                    <button type="button" onClick={() => { if (e.id != null) void startRename("episode", e.id, e.title ?? ""); }} title="Rename episode" style={{ ...textButton, cursor: "text" }}>{e.title}</button>
                  )}
                  {e.id != null && <Del label={e.title || `episode ${e.episode_number}`} on={() => delEpisode(e.id!)} busy={renameBusy || busyDel === `e${e.id}`} />}
                </div>
                <div style={{ paddingLeft: 12 }}>
                  {(plotlines[e.id ?? -1] || []).map((pl) => <div key={pl.id} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 9, color: "var(--cyan)" }}><span>· {pl.type}-story — {pl.title}</span>{e.id != null && pl.id != null && <Del label={pl.title || `plotline ${pl.id}`} on={() => delPlotline(e.id!, pl.id!)} busy={busyDel === `pl${pl.id}`} />}</div>)}
                  <div style={{ display: "flex", gap: 5, marginTop: 2 }}>
                    <input value={plDraft[e.id ?? -1] || ""} onChange={(ev) => setPlDraft((m) => ({ ...m, [e.id!]: ev.target.value }))} placeholder="plotline (A-story)" aria-label={`New plotline for episode ${e.episode_number}`} style={{ ...inp, flex: 1, fontSize: 9 }} />
                    <Add on={() => e.id && addPlotline(e.id)} />
                  </div>
                </div>
              </div>
            ))}
            <div style={{ display: "flex", gap: 6, marginTop: 5 }}><input value={epDraft[s.id ?? -1] || ""} onChange={(ev) => setEpDraft((m) => ({ ...m, [s.id!]: ev.target.value }))} placeholder="episode title" aria-label={`New episode for season ${s.season_number}`} style={{ ...inp, flex: 1, fontSize: 9.5 }} /><Add on={() => s.id && addEpisode(s.id)} /></div>
          </div>
        </div>
      ))}
      <div style={{ ...lbl, marginTop: 12 }}>ADD ARC (setup → payoff)</div>
      <div style={row}><input value={arcTitle} onChange={(e) => setArcTitle(e.target.value)} placeholder="arc title, e.g. “The Kessler Mystery”" aria-label="New series arc title" style={{ ...inp, flex: 1 }} /></div>
      <div style={row}>
        <select value={arcSetup === "" ? "" : String(arcSetup)} onChange={(e) => setArcSetup(e.target.value ? Number(e.target.value) : "")} aria-label="Series arc setup episode" style={{ ...inp, flex: 1 }}><option value="">— setup episode —</option>{episodes.map((ep) => <option key={ep.id} value={String(ep.id)}>{epLabel(ep.id)}</option>)}</select>
        <select value={arcPayoff === "" ? "" : String(arcPayoff)} onChange={(e) => setArcPayoff(e.target.value ? Number(e.target.value) : "")} aria-label="Series arc payoff episode" style={{ ...inp, flex: 1 }}><option value="">— payoff episode —</option>{episodes.map((ep) => <option key={ep.id} value={String(ep.id)}>{epLabel(ep.id)}</option>)}</select>
        <select value={arcStatus} onChange={(e) => setArcStatus(e.target.value)} aria-label="Series arc status" style={{ ...inp, width: 96 }}>{["active", "resolved", "delayed"].map((s) => <option key={s} value={s}>{s}</option>)}</select>
        <Add on={addArc} />
      </div>
      {episodes.length === 0 && <div style={{ fontSize: 9, color: "var(--txt3)", fontStyle: "italic", marginBottom: 7 }}>Add episodes first to bind an arc’s setup → payoff (unbound arcs emit no arc edges).</div>}
      {arcs.map((a) => <div key={a.id} style={{ ...card, padding: "6px 10px", display: "flex", alignItems: "center", gap: 6, fontSize: 10, color: "var(--txt2)" }}><span><span style={{ color: "var(--green)", letterSpacing: ".08em" }}>◆ {a.title}</span> <span style={{ color: "var(--txt3)" }}>· {a.status}</span>{(a.setup_episode_id != null || a.payoff_episode_id != null) && <span style={{ color: "var(--cyan)" }}> · {epLabel(a.setup_episode_id)} → {epLabel(a.payoff_episode_id)}</span>}</span>{a.id != null && <Del label={a.title || `arc ${a.id}`} on={() => delArc(a.id!)} busy={busyDel === `arc${a.id}`} />}</div>)}

      <div style={{ ...lbl, marginTop: 12 }}>SERIES MEMORY (echo / contradict)</div>
      <div style={row}>
        <select value={memChar === "" ? "" : String(memChar)} onChange={(e) => setMemChar(e.target.value ? Number(e.target.value) : "")} aria-label="Series-memory PSYKE character" style={{ ...inp, flex: 1 }}><option value="">— PSYKE character —</option>{chars.map((c) => <option key={c.id} value={String(c.id)}>{c.name}</option>)}</select>
        <select value={memEp === "" ? "" : String(memEp)} onChange={(e) => setMemEp(e.target.value ? Number(e.target.value) : "")} aria-label="Series-memory episode" style={{ ...inp, flex: 1 }}><option value="">— episode —</option>{episodes.map((ep) => <option key={ep.id} value={String(ep.id)}>{epLabel(ep.id)}</option>)}</select>
        <input value={memStatus} onChange={(e) => setMemStatus(e.target.value)} placeholder="status in episode" aria-label="Character status in episode" style={{ ...inp, flex: 1 }} />
      </div>
      <div style={row}>
        <input value={memFlags} onChange={(e) => setMemFlags(e.target.value)} placeholder="continuity flag (optional → contradict edge)" aria-label="Series-memory continuity flag" style={{ ...inp, flex: 1 }} /><Add on={setMemory} />
      </div>
      {chars.length === 0 && <div style={{ fontSize: 9, color: "var(--txt3)", fontStyle: "italic" }}>Add a PSYKE “character” entry to track per-episode status.</div>}
    </>
  );
}

const TABS: [string, "gn" | "stage" | "series" | "scene"][] = [["GRAPHIC NOVEL", "gn"], ["STAGE", "stage"], ["SERIES", "series"], ["SCENE", "scene"]];

export function FormatStructure(props: PanelProps) {
  const { projectId } = useStudio();
  const [tab, setTab] = useState<"gn" | "stage" | "series" | "scene">("gn");
  const [tabError, setTabError] = useState("");
  const tabRequestRef = useRef(0);
  const pid = projectId ?? 0;
  const selectTab = async (next: typeof tab) => {
    if (next === tab) return;
    const request = ++tabRequestRef.current;
    try {
      await flushPendingProjectSaves({ commitActiveField: true });
      if (request !== tabRequestRef.current) return;
      setTab(next);
      setTabError("");
    } catch (error) {
      if (request !== tabRequestRef.current) return;
      setTabError(error instanceof Error ? error.message : String(error));
    }
  };
  return (
    <PanelShell {...props} style={{ ["--accent"]: "#b07cff" } as CSSProperties}>
      <div data-screen-label="Format Structure" style={panelBox}>
        <Corners />
        <div style={{ height: 42, flex: "none", display: "flex", alignItems: "center", gap: 11, padding: "0 16px", borderBottom: "1px solid var(--line)" }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".1em", color: "var(--strong)" }}>STRUCTURE</span>
          <div style={{ display: "flex", border: "1px solid var(--line2)", fontSize: 8, letterSpacing: ".08em" }}>
            {TABS.map(([label, key], i) => (
              <button key={key} type="button" aria-pressed={tab === key} onClick={() => { void selectTab(key); }} style={{ font: "inherit", border: "none", padding: "4px 9px", cursor: "pointer", borderLeft: i === 0 ? undefined : "1px solid var(--line2)", color: tab === key ? "var(--on-accent)" : "var(--txt3)", background: tab === key ? "var(--accent)" : "transparent", fontWeight: tab === key ? 600 : 400 }}>{label}</button>
            ))}
          </div>
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 8, color: "var(--txt3)", letterSpacing: ".08em" }}>authors the structure the graph reads</span>
        </div>
        {tabError && <div role="alert" style={{ flex: "none", padding: "7px 14px", borderBottom: "1px solid var(--crimson)", color: "var(--crimson)", fontSize: 9.5 }}>⚠ Tab switch stopped — {tabError}</div>}
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
