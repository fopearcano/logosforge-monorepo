import { useState, type CSSProperties } from "react";
import { WRITING_MODES, type ProjectDTO } from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useStudio, useSelectProject, useRefreshProjects } from "../../adapters/StudioProvider";
import { parseProjectBundle, importProjectBundle } from "../../adapters/projectBundle";
import { useProjects } from "../../hooks";

/**
 * Projects — full lifecycle management (list · open · create · rename · delete)
 * over the core project endpoints. The active project is owned by the host app;
 * this panel switches it via the injected selectProject and keeps the host's
 * rail list in sync via refreshProjects.
 */

const panelBox: CSSProperties = {
  position: "relative", width: "100%", height: "100%",
  background: "linear-gradient(180deg,var(--panel),var(--base))", border: "1px solid var(--line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)", overflow: "hidden", display: "flex", flexDirection: "column",
};
const btn: CSSProperties = { fontSize: 9, letterSpacing: ".06em", border: "1px solid var(--line2)", background: "transparent", color: "var(--txt2)", padding: "4px 9px", cursor: "pointer", font: "inherit" };
const inp: CSSProperties = { background: "var(--tint)", border: "1px solid var(--line2)", outline: "none", color: "var(--txt)", fontFamily: "inherit", fontSize: 12, padding: "6px 9px" };

export function ProjectsPanel(props: PanelProps) {
  const { api, projectId, writingMode, platform } = useStudio();
  const projects = useProjects();
  const selectProject = useSelectProject();
  const refreshProjects = useRefreshProjects();

  const [newTitle, setNewTitle] = useState("");
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameText, setRenameText] = useState("");
  const [confirmDelId, setConfirmDelId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  // Raw-manuscript import (.txt/.md/.docx) — a small inline form so the writer
  // picks the writing mode + how to split it into scenes before choosing a file.
  const [showManuscript, setShowManuscript] = useState(false);
  const [mMode, setMMode] = useState<string>(String(writingMode ?? "novel"));
  const [mStrategy, setMStrategy] = useState<string>("smart");

  const list: ProjectDTO[] = [...(projects.data ?? [])].sort((a, b) => a.id - b.id);
  const sync = () => { projects.refetch(); refreshProjects(); };

  const create = async () => {
    if (busy) return;
    setBusy(true); setErr(null); setNote(null);
    try {
      const p = await api.createProject({ title: newTitle.trim() || "Untitled Project", default_writing_format: String(writingMode ?? "") });
      setNewTitle(""); sync(); selectProject(p.id);
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  };

  // Free → Pro: pick a Whiteboard document (~/.logosforge/whiteboards/{id}.json),
  // convert its blocks into scenes, and open the resulting new project.
  const importWhiteboard = async () => {
    if (busy) return;
    setBusy(true); setErr(null); setNote(null);
    try {
      const res = await platform.openFile({ filters: [{ name: "Whiteboard document", extensions: ["json"] }] });
      if (res.canceled || !res.content) { setBusy(false); return; }
      let doc: { title?: string; mode?: string; blocks?: unknown };
      try { doc = JSON.parse(res.content); } catch { setErr("That file isn't valid JSON."); setBusy(false); return; }
      if (!Array.isArray(doc.blocks)) { setErr("That JSON isn't a Whiteboard document (no blocks)."); setBusy(false); return; }
      const r = await api.importWhiteboard({ title: String(doc.title ?? ""), mode: String(doc.mode ?? "novel"), blocks: doc.blocks as never });
      sync(); selectProject(r.project_id);
      setNote(`Imported “${r.title}” — ${r.scenes_created} scene${r.scenes_created === 1 ? "" : "s"} (${r.mode}).`);
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  };

  // Whiteboard → Pro: import a whole single-project bundle (.lfbundle) — manuscript
  // (blocks → scenes via the same converter) AND the PSYKE story bible — into one
  // new project. Outline + comments ride along in the bundle for a later phase.
  const importBundle = async () => {
    if (busy) return;
    setBusy(true); setErr(null); setNote(null);
    try {
      const res = await platform.openFile({ filters: [{ name: "LogosForge project bundle", extensions: ["lfbundle", "json"] }] });
      if (res.canceled || !res.content) { setBusy(false); return; }
      let bundle;
      try { bundle = parseProjectBundle(res.content); }
      catch (e) { setErr(e instanceof Error ? e.message : String(e)); setBusy(false); return; }
      const r = await importProjectBundle(api, bundle);
      sync(); selectProject(r.projectId);
      const parts = [
        `${r.scenes} scene${r.scenes === 1 ? "" : "s"}`,
        `${r.entries} bible entr${r.entries === 1 ? "y" : "ies"}`,
        `${r.outlineNodes} outline node${r.outlineNodes === 1 ? "" : "s"}`,
      ];
      if (r.links > 0) parts.push(`${r.links} section link${r.links === 1 ? "" : "s"}`);   // Phase 3
      // Comments are carried by the bundle but Pro has no inline-comments target
      // yet — say so plainly rather than dropping them silently (Phase 2 decision).
      // Likewise report any outline→scene links that couldn't be resolved.
      const deferredBits: string[] = [];
      if (r.comments > 0) deferredBits.push(`${r.comments} comment${r.comments === 1 ? "" : "s"} not migrated (Pro has no inline comments yet)`);
      if (r.linksSkipped > 0) deferredBits.push(`${r.linksSkipped} section link${r.linksSkipped === 1 ? "" : "s"} couldn't be resolved`);
      const deferred = deferredBits.length ? ` ${deferredBits.join("; ")}.` : "";
      setNote(`Imported “${r.title}” — ${parts.join(", ")} (${r.mode}).${deferred}`);
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  };
  // Import an already-written, unformatted manuscript (.txt / .md / .docx): the
  // core segments the prose into scenes for the chosen mode + strategy. The file
  // is sent base64 (so a binary .docx survives) — desktop gives us contentBase64;
  // fall back to base64-encoding the utf-8 text (web / .txt).
  const importManuscript = async () => {
    if (busy) return;
    setErr(null); setNote(null);
    const res = await platform.openFile({ filters: [{ name: "Manuscript", extensions: ["txt", "md", "markdown", "docx"] }] });
    if (res.canceled) return;
    let b64 = res.contentBase64 ?? "";
    if (!b64 && res.content != null) {
      try { b64 = btoa(unescape(encodeURIComponent(res.content))); } catch { b64 = ""; }
    }
    if (!b64) { setErr("Couldn't read that file."); return; }
    const filename = (res.path ?? "").split(/[\\/]/).pop() || "manuscript.txt";
    setBusy(true);
    try {
      const r = await api.importManuscript({
        title: filename.replace(/\.[^.]+$/, ""),
        mode: mMode, strategy: mStrategy, filename, content_base64: b64,
      });
      sync(); selectProject(r.project_id); setShowManuscript(false);
      setNote(`Imported “${r.title}” — ${r.scenes_created} scene${r.scenes_created === 1 ? "" : "s"} (${r.mode}). Tip: run Extract to auto-build the story bible.`);
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  };

  const rename = async (id: number) => {
    const t = renameText.trim();
    if (!t || busy) { setRenamingId(null); return; }
    setBusy(true); setErr(null);
    try { await api.updateProject(id, { title: t }); setRenamingId(null); sync(); }
    catch (e) { setErr(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  };
  const remove = async (id: number) => {
    if (busy) return;
    setBusy(true); setErr(null);
    try {
      await api.deleteProject(id);
      setConfirmDelId(null);
      const remaining = list.filter((p) => p.id !== id);
      sync();
      if (projectId === id) selectProject(remaining[0]?.id ?? 0);
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  };

  return (
    <PanelShell {...props}>
      <div data-screen-label="Projects" style={panelBox}>
        <Corners />
        <div style={{ height: 40, flex: "none", display: "flex", alignItems: "center", gap: 10, padding: "0 16px", borderBottom: "1px solid var(--line)" }}>
          <span style={{ fontFamily: "'Chakra Petch',sans-serif", fontWeight: 600, fontSize: 12.5, letterSpacing: ".14em", color: "var(--strong)" }}>PROJECTS</span>
          <span style={{ fontSize: 9, color: "var(--txt3)", letterSpacing: ".1em" }}>{list.length}</span>
        </div>

        <div style={{ flex: 1, overflowY: "auto", padding: 14 }}>
          {/* create row */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16 }}>
            <input value={newTitle} onChange={(e) => setNewTitle(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void create(); }} placeholder="New project title…" aria-label="New project title" style={{ ...inp, flex: "1 1 160px" }} />
            <button type="button" onClick={() => void create()} disabled={busy} style={{ ...btn, color: "var(--on-accent)", background: "var(--accent)", border: "none", fontWeight: 700, opacity: busy ? 0.5 : 1 }}>＋ CREATE</button>
            <button type="button" onClick={() => void importBundle()} disabled={busy} title="Import a whole LogosForge project bundle (.lfbundle) exported from Whiteboard — manuscript + story bible" style={{ ...btn, color: "var(--txt2)", opacity: busy ? 0.5 : 1 }}>⇩ IMPORT PROJECT</button>
            <button type="button" onClick={() => void importWhiteboard()} disabled={busy} title="Graduate a single Whiteboard document (.json) into a Pro project (blocks → scenes)" style={{ ...btn, color: "var(--txt2)", opacity: busy ? 0.5 : 1 }}>⇩ IMPORT WHITEBOARD</button>
            <button type="button" onClick={() => { setShowManuscript((v) => !v); setErr(null); }} disabled={busy} title="Import an already-written, unformatted manuscript (.txt / .md / .docx) — split into scenes for a new project" style={{ ...btn, color: showManuscript ? "var(--accent)" : "var(--txt2)", borderColor: showManuscript ? "var(--line-cy,#2b6f8f)" : "var(--line2)", opacity: busy ? 0.5 : 1 }}>⇩ IMPORT MANUSCRIPT</button>
          </div>

          {/* raw-manuscript import: choose mode + how to split, then pick a file */}
          {showManuscript && (
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: 10, marginBottom: 16, padding: "11px 12px", border: "1px solid var(--line-cy)", background: "var(--tint)" }}>
              <div style={{ fontSize: 8.5, letterSpacing: ".1em", color: "var(--txt3)", width: "100%" }}>IMPORT MANUSCRIPT · .txt / .md / .docx → scenes</div>
              <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 8, letterSpacing: ".1em", color: "var(--txt3)" }}>
                WRITING MODE
                <select value={mMode} onChange={(e) => setMMode(e.target.value)} style={{ ...inp, fontSize: 11, padding: "5px 7px" }}>
                  {WRITING_MODES.map((m) => <option key={m} value={m}>{m}</option>)}
                </select>
              </label>
              <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 8, letterSpacing: ".1em", color: "var(--txt3)" }}>
                SPLIT INTO SCENES
                <select value={mStrategy} onChange={(e) => setMStrategy(e.target.value)} title="How to break the flowing manuscript into scenes" style={{ ...inp, fontSize: 11, padding: "5px 7px" }}>
                  <option value="smart">Smart — any chapter / scene-break marker</option>
                  <option value="chapter">By chapter heading</option>
                  <option value="scene_break">By scene break (*** / #)</option>
                  <option value="single">One scene (split later)</option>
                </select>
              </label>
              <button type="button" onClick={() => void importManuscript()} disabled={busy} style={{ ...btn, color: "var(--on-accent)", background: "var(--accent)", border: "none", fontWeight: 700, padding: "6px 11px", opacity: busy ? 0.5 : 1 }}>{busy ? "IMPORTING…" : "CHOOSE FILE…"}</button>
            </div>
          )}
          {note && <div style={{ fontSize: 9.5, color: "var(--green)", marginBottom: 12 }}>✓ {note}</div>}

          {projects.loading && !projects.data ? <div style={{ color: "var(--txt3)", fontSize: 11 }}>Loading…</div>
            : projects.error ? <div style={{ color: "var(--blocking)", fontSize: 11 }}>{projects.error}</div>
            : list.length === 0 ? <div style={{ color: "var(--txt3)", fontSize: 11 }}>No projects yet — create your first above.</div>
            : (
              <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
                {list.map((p) => {
                  const active = p.id === projectId;
                  return (
                    <div key={p.id} style={{ display: "flex", alignItems: "center", gap: 9, border: `1px solid ${active ? "var(--accent)" : "var(--line2)"}`, background: active ? "rgba(76,194,255,.06)" : "var(--tint)", padding: "9px 11px" }}>
                      {renamingId === p.id ? (
                        <>
                          <input autoFocus value={renameText} onChange={(e) => setRenameText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void rename(p.id); if (e.key === "Escape") setRenamingId(null); }} aria-label="Rename project" style={{ ...inp, flex: 1, fontSize: 12.5, color: "var(--strong)" }} />
                          <button type="button" onClick={() => void rename(p.id)} disabled={busy} style={{ ...btn, color: "var(--green)" }}>✓ SAVE</button>
                          <button type="button" onClick={() => setRenamingId(null)} style={btn}>✕</button>
                        </>
                      ) : confirmDelId === p.id ? (
                        <>
                          <span style={{ flex: 1, fontSize: 11, color: "var(--txt2)" }}>Delete “{p.title || `Project ${p.id}`}” and all its data?</span>
                          <button type="button" onClick={() => void remove(p.id)} disabled={busy} style={{ ...btn, color: "var(--blocking)", borderColor: "var(--blocking)" }}>✓ DELETE</button>
                          <button type="button" onClick={() => setConfirmDelId(null)} style={btn}>✕</button>
                        </>
                      ) : (
                        <>
                          <button type="button" onClick={() => selectProject(p.id)} title="Open this project" style={{ flex: 1, textAlign: "left", background: "transparent", border: "none", font: "inherit", cursor: "pointer", padding: 0 }}>
                            <span style={{ fontSize: 12.5, color: active ? "var(--strong)" : "var(--txt)" }}>{p.title || `Project ${p.id}`}</span>
                            <span style={{ fontSize: 8, color: "var(--txt3)", marginLeft: 9, letterSpacing: ".08em" }}>{p.default_writing_format || p.format_mode || "novel"}{active ? " · ACTIVE" : ""}</span>
                          </button>
                          {!active && <button type="button" onClick={() => selectProject(p.id)} style={{ ...btn, color: "var(--accent)", borderColor: "var(--line-cy,#2b6f8f)" }}>OPEN</button>}
                          <button type="button" onClick={() => { setRenamingId(p.id); setRenameText(p.title || ""); }} title="Rename" style={btn}>✎</button>
                          <button type="button" onClick={() => setConfirmDelId(p.id)} title="Delete" style={{ ...btn, color: "var(--txt3)" }}>🗑</button>
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          {err && <div style={{ marginTop: 12, fontSize: 10, color: "var(--crimson)" }}>⚠ {err}</div>}
        </div>
      </div>
    </PanelShell>
  );
}
