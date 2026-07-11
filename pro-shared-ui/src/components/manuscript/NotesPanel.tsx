import { useCallback, useState, type CSSProperties } from "react";
import type { NoteDTO } from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useStudio } from "../../adapters/StudioProvider";
import { useNotes } from "../../hooks";

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

type Tag = { text: string; color: string; border: string };

function NoteCard({ note, onClick }: { note: NoteDTO; onClick: () => void }) {
  const pinned = note.pinned;
  const tags: Tag[] = [
    ...note.tags.map((t) => ({ text: t, color: "var(--txt2)", border: "var(--line2)" })),
    ...note.scene_links.map((id) => ({ text: `scene:${id}`, color: "var(--txt2)", border: "var(--line2)" })),
    ...note.psyke_links.map((id) => ({ text: `◆ #${id}`, color: "var(--cyan)", border: "var(--line-cy)" })),
  ];
  return (
    <button
      type="button"
      onClick={onClick}
      style={{ textAlign: "left", cursor: "pointer", font: "inherit", border: pinned ? "1px solid var(--accent)" : "1px solid var(--line2)", borderTop: pinned ? "2px solid var(--accent)" : undefined, background: pinned ? "rgba(76,194,255,.05)" : "var(--tint)", padding: 11, boxShadow: pinned ? "0 0 14px rgba(76,194,255,.1)" : undefined }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 7 }}>
        <span style={{ fontFamily: "'Chakra Petch'", fontSize: 12, color: "var(--strong)", letterSpacing: ".03em" }}>{note.title || "Untitled note"}</span>
        <span style={{ fontSize: 8, color: pinned ? "var(--accent)" : "var(--txt3)" }}>{pinned ? "⊙ PINNED" : "⊙"}</span>
      </div>
      <div style={{ fontSize: 10, color: "var(--txt2)", lineHeight: 1.5, marginBottom: 10, whiteSpace: "pre-wrap", maxHeight: 88, overflow: "hidden" }}>{note.content || "(empty)"}</div>
      <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
        {tags.map((t, i) => (
          <span key={i} style={{ fontSize: 8, color: t.color, border: `1px solid ${t.border}`, padding: "1px 6px" }}>{t.text}</span>
        ))}
      </div>
    </button>
  );
}

const btn = (accent = false): CSSProperties => ({
  background: accent ? "var(--accent)" : "transparent",
  color: accent ? "var(--on-accent)" : "var(--txt2)",
  border: accent ? "none" : "1px solid var(--line2)",
  padding: "6px 12px",
  fontSize: 10,
  letterSpacing: ".1em",
  cursor: "pointer",
  fontWeight: accent ? 600 : 400,
});

function NoteEditor({ note, onClose, onChanged }: { note: NoteDTO; onClose: () => void; onChanged: () => void }) {
  const { api, projectId } = useStudio();
  const [title, setTitle] = useState(note.title);
  const [content, setContent] = useState(note.content);
  const [pinned, setPinned] = useState(note.pinned);
  const [tags, setTags] = useState<string[]>(note.tags);
  const [tagDraft, setTagDraft] = useState("");
  const [sceneLinks, setSceneLinks] = useState<number[]>(note.scene_links);
  const [psykeLinks, setPsykeLinks] = useState<number[]>(note.psyke_links);
  const [sceneDraft, setSceneDraft] = useState("");
  const [psykeDraft, setPsykeDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const commitTag = () => {
    const t = tagDraft.trim();
    if (t && !tags.includes(t)) setTags((prev) => [...prev, t]);
    setTagDraft("");
  };
  const removeTag = (t: string) => setTags((prev) => prev.filter((x) => x !== t));

  const linkScene = async () => {
    if (projectId == null) return;
    const id = Number(sceneDraft);
    if (!Number.isFinite(id) || id <= 0 || sceneLinks.includes(id)) return;
    setBusy(true);
    setErr(null);
    try {
      await api.linkNoteScene(projectId, note.id, id);
      setSceneLinks((prev) => [...prev, id]);
      setSceneDraft("");
      onChanged();
    } catch {
      setErr("Couldn't link scene");
    } finally {
      setBusy(false);
    }
  };
  const unlinkScene = async (id: number) => {
    if (projectId == null) return;
    setBusy(true);
    setErr(null);
    try {
      await api.unlinkNoteScene(projectId, note.id, id);
      setSceneLinks((prev) => prev.filter((x) => x !== id));
      onChanged();
    } catch {
      setErr("Couldn't unlink scene");
    } finally {
      setBusy(false);
    }
  };
  const linkPsyke = async () => {
    if (projectId == null) return;
    const id = Number(psykeDraft);
    if (!Number.isFinite(id) || id <= 0 || psykeLinks.includes(id)) return;
    setBusy(true);
    setErr(null);
    try {
      await api.linkNotePsyke(projectId, note.id, id);
      setPsykeLinks((prev) => [...prev, id]);
      setPsykeDraft("");
      onChanged();
    } catch {
      setErr("Couldn't link PSYKE entry");
    } finally {
      setBusy(false);
    }
  };
  const unlinkPsyke = async (id: number) => {
    if (projectId == null) return;
    setBusy(true);
    setErr(null);
    try {
      await api.unlinkNotePsyke(projectId, note.id, id);
      setPsykeLinks((prev) => prev.filter((x) => x !== id));
      onChanged();
    } catch {
      setErr("Couldn't unlink PSYKE entry");
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    if (projectId == null) return;
    setBusy(true);
    setErr(null);
    try {
      await api.updateNote(projectId, note.id, { title, content, pinned, tags });
      onChanged();
      onClose();
    } catch {
      setErr("Couldn't save note");
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    if (projectId == null) return;
    setBusy(true);
    try {
      await api.deleteNote(projectId, note.id);
      onChanged();
      onClose();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ position: "absolute", inset: 0, zIndex: 5, background: "linear-gradient(180deg,var(--raised),var(--base))", display: "flex", flexDirection: "column", padding: 18, gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ fontFamily: "'Chakra Petch'", fontSize: 12, letterSpacing: ".16em", color: "var(--accent)" }}>EDIT NOTE</span>
        <label style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 9, color: "var(--txt2)", letterSpacing: ".1em", cursor: "pointer" }}>
          <input type="checkbox" checked={pinned} onChange={(e) => setPinned(e.target.checked)} /> PIN
        </label>
        <div style={{ flex: 1 }} />
        <button type="button" onClick={remove} disabled={busy} style={{ ...btn(), color: "var(--crimson)", borderColor: "var(--crimson)" }}>DELETE</button>
        <button type="button" onClick={onClose} disabled={busy} style={btn()}>CANCEL</button>
        <button type="button" onClick={save} disabled={busy} style={btn(true)}>{busy ? "SAVING…" : "SAVE"}</button>
      </div>
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Note title"
        aria-label="Note title"
        style={{ background: "var(--tint)", border: "1px solid var(--line2)", color: "var(--strong)", fontFamily: "'Chakra Petch'", fontSize: 15, padding: "9px 11px", outline: "none" }}
      />
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
        <span style={{ fontSize: 8, color: "var(--txt3)", letterSpacing: ".1em", marginRight: 2 }}>TAGS</span>
        {tags.map((t) => (
          <span key={t} style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 8, color: "var(--txt2)", border: "1px solid var(--line2)", padding: "1px 3px 1px 6px" }}>
            {t}
            <button type="button" onClick={() => removeTag(t)} aria-label={`Remove tag ${t}`} style={{ font: "inherit", fontSize: 8, background: "transparent", border: "none", color: "var(--crimson)", cursor: "pointer", padding: 0, lineHeight: 1 }}>✕</button>
          </span>
        ))}
        <input
          value={tagDraft}
          onChange={(e) => setTagDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === ",") {
              e.preventDefault();
              commitTag();
            }
          }}
          onBlur={commitTag}
          placeholder="add tag…"
          aria-label="Add tag"
          style={{ background: "var(--tint)", border: "1px solid var(--line2)", color: "var(--txt)", fontFamily: "'JetBrains Mono',monospace", fontSize: 9, padding: "2px 6px", outline: "none", width: 78 }}
        />
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
        <span style={{ fontSize: 8, color: "var(--txt3)", letterSpacing: ".1em", marginRight: 2 }}>SCENES</span>
        {sceneLinks.map((id) => (
          <span key={id} style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 8, color: "var(--txt2)", border: "1px solid var(--line2)", padding: "1px 3px 1px 6px" }}>
            scene:{id}
            <button type="button" onClick={() => unlinkScene(id)} disabled={busy} aria-label={`Unlink scene ${id}`} style={{ font: "inherit", fontSize: 8, background: "transparent", border: "none", color: "var(--crimson)", cursor: "pointer", padding: 0, lineHeight: 1 }}>✕</button>
          </span>
        ))}
        <input
          type="number"
          value={sceneDraft}
          onChange={(e) => setSceneDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void linkScene(); } }}
          placeholder="id"
          aria-label="Scene id to link"
          style={{ background: "var(--tint)", border: "1px solid var(--line2)", color: "var(--txt)", fontFamily: "'JetBrains Mono',monospace", fontSize: 9, padding: "2px 6px", outline: "none", width: 48 }}
        />
        <button type="button" onClick={() => void linkScene()} disabled={busy} style={{ font: "inherit", fontSize: 8, letterSpacing: ".1em", background: "transparent", border: "1px solid var(--line2)", color: "var(--accent)", cursor: "pointer", padding: "2px 6px" }}>ADD</button>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
        <span style={{ fontSize: 8, color: "var(--txt3)", letterSpacing: ".1em", marginRight: 2 }}>PSYKE</span>
        {psykeLinks.map((id) => (
          <span key={id} style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 8, color: "var(--cyan)", border: "1px solid var(--line-cy)", padding: "1px 3px 1px 6px" }}>
            ◆ #{id}
            <button type="button" onClick={() => unlinkPsyke(id)} disabled={busy} aria-label={`Unlink PSYKE entry ${id}`} style={{ font: "inherit", fontSize: 8, background: "transparent", border: "none", color: "var(--crimson)", cursor: "pointer", padding: 0, lineHeight: 1 }}>✕</button>
          </span>
        ))}
        <input
          type="number"
          value={psykeDraft}
          onChange={(e) => setPsykeDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void linkPsyke(); } }}
          placeholder="id"
          aria-label="PSYKE entry id to link"
          style={{ background: "var(--tint)", border: "1px solid var(--line2)", color: "var(--txt)", fontFamily: "'JetBrains Mono',monospace", fontSize: 9, padding: "2px 6px", outline: "none", width: 48 }}
        />
        <button type="button" onClick={() => void linkPsyke()} disabled={busy} style={{ font: "inherit", fontSize: 8, letterSpacing: ".1em", background: "transparent", border: "1px solid var(--line-cy)", color: "var(--cyan)", cursor: "pointer", padding: "2px 6px" }}>ADD</button>
      </div>
      {err && <span style={{ fontSize: 9, color: "var(--crimson)", letterSpacing: ".04em" }}>{err}</span>}
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder="Write your note…"
        aria-label="Note content"
        style={{ flex: 1, resize: "none", background: "var(--tint)", border: "1px solid var(--line2)", color: "var(--txt)", fontFamily: "'JetBrains Mono',monospace", fontSize: 13, lineHeight: 1.6, padding: "11px 12px", outline: "none" }}
      />
    </div>
  );
}

const message = (text: string) => (
  <div style={{ gridColumn: "1 / -1", padding: "34px 0", textAlign: "center", fontSize: 11, color: "var(--txt3)", letterSpacing: ".04em" }}>{text}</div>
);

export function NotesPanel(props: PanelProps) {
  const { api, projectId } = useStudio();
  const { data: notes, loading, error, refetch } = useNotes();
  const [editing, setEditing] = useState<NoteDTO | null>(null);
  const [busy, setBusy] = useState(false);
  const count = notes?.length ?? 0;
  const pinned = notes?.filter((n) => n.pinned).length ?? 0;

  const createNote = useCallback(async () => {
    if (projectId == null || busy) return;
    setBusy(true);
    try {
      const created = await api.createNote(projectId, { title: "Untitled note", content: "" });
      refetch();
      setEditing(created);
    } catch {
      /* no-op */
    } finally {
      setBusy(false);
    }
  }, [api, projectId, busy, refetch]);

  return (
    <PanelShell {...props}>
      <div data-screen-label="Notes Panel" style={panelBox}>
        <Corners />
        <div style={{ height: 40, flex: "none", display: "flex", alignItems: "center", gap: 12, padding: "0 16px", borderBottom: "1px solid var(--line)" }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".12em", color: "var(--strong)" }}>NOTES</span>
          <span style={{ fontSize: 8, color: "var(--txt3)" }}>{count} · {pinned} PINNED</span>
          <div style={{ flex: 1 }} />
          <button type="button" onClick={createNote} disabled={busy || projectId == null} style={{ fontSize: 9, color: "var(--on-accent)", background: "var(--accent)", padding: "5px 11px", fontWeight: 600, letterSpacing: ".08em", border: "none", cursor: busy ? "default" : "pointer", opacity: busy || projectId == null ? 0.5 : 1 }}>＋ NEW NOTE</button>
        </div>
        <div style={{ position: "relative", flex: 1, minHeight: 0 }}>
          <div style={{ position: "absolute", inset: 0, overflowY: "auto", padding: 13, display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 11, alignContent: "start" }}>
            {loading
              ? message("Loading notes…")
              : error
                ? message(`Couldn't load notes — ${error}`)
                : count === 0
                  ? message("No notes yet — create one with ＋ NEW NOTE")
                  : notes!.map((n) => <NoteCard key={n.id} note={n} onClick={() => setEditing(n)} />)}
          </div>
          {editing && <NoteEditor note={editing} onClose={() => setEditing(null)} onChanged={refetch} />}
        </div>
      </div>
    </PanelShell>
  );
}
