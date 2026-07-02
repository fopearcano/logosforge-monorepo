import { useCallback, useState, type CSSProperties } from "react";
import type { NoteDTO } from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useStudio } from "../../adapters/StudioProvider";
import { useNotes } from "../../hooks";

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
      style={{ textAlign: "left", cursor: "pointer", font: "inherit", border: pinned ? "1px solid var(--accent)" : "1px solid var(--line2)", borderTop: pinned ? "2px solid var(--accent)" : undefined, background: pinned ? "rgba(76,194,255,.05)" : "rgba(11,14,21,.4)", padding: 11, boxShadow: pinned ? "0 0 14px rgba(76,194,255,.1)" : undefined }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 7 }}>
        <span style={{ fontFamily: "'Chakra Petch'", fontSize: 12, color: "#fff", letterSpacing: ".03em" }}>{note.title || "Untitled note"}</span>
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
  color: accent ? "#04060a" : "var(--txt2)",
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
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (projectId == null) return;
    setBusy(true);
    try {
      await api.updateNote(projectId, note.id, { title, content, pinned });
      onChanged();
      onClose();
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
    <div style={{ position: "absolute", inset: 0, zIndex: 5, background: "linear-gradient(180deg,#0a0d13,#05070b)", display: "flex", flexDirection: "column", padding: 18, gap: 12 }}>
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
        style={{ background: "rgba(11,14,21,.6)", border: "1px solid var(--line2)", color: "#fff", fontFamily: "'Chakra Petch'", fontSize: 15, padding: "9px 11px", outline: "none" }}
      />
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder="Write your note…"
        aria-label="Note content"
        style={{ flex: 1, resize: "none", background: "rgba(11,14,21,.6)", border: "1px solid var(--line2)", color: "#c6ccd6", fontFamily: "'JetBrains Mono',monospace", fontSize: 13, lineHeight: 1.6, padding: "11px 12px", outline: "none" }}
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
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".12em", color: "#fff" }}>NOTES</span>
          <span style={{ fontSize: 8, color: "var(--txt3)" }}>{count} · {pinned} PINNED</span>
          <div style={{ flex: 1 }} />
          <button type="button" onClick={createNote} disabled={busy || projectId == null} style={{ fontSize: 9, color: "#04060a", background: "var(--accent)", padding: "5px 11px", fontWeight: 600, letterSpacing: ".08em", border: "none", cursor: busy ? "default" : "pointer", opacity: busy || projectId == null ? 0.5 : 1 }}>＋ NEW NOTE</button>
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
