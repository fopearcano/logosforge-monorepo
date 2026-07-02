import { useCallback, useEffect, useState, type CSSProperties, type ReactNode } from "react";
import type { OutlineNodeDTO } from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useStudio } from "../../adapters/StudioProvider";
import { useOutline } from "../../hooks";
import { useSelection } from "../../adapters/selection";

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

function SceneRow({ code, title, description, leftColor }: { code: string; title: string; description?: string; leftColor: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, borderLeft: `3px solid ${leftColor}`, background: "rgba(11,14,21,.5)", padding: "6px 9px" }}>
      <span style={{ fontSize: 8, color: "var(--txt3)", fontFamily: "'Chakra Petch'" }}>{code}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <span style={{ fontSize: 10, color: "var(--txt)" }}>{title}</span>
        {description && <div style={{ fontSize: 8.5, color: "var(--txt3)", lineHeight: 1.4, marginTop: 2 }}>{description}</div>}
      </div>
    </div>
  );
}

const cap = (children: ReactNode) => <div style={{ fontSize: 8, letterSpacing: ".16em", color: "var(--txt3)", marginBottom: 7 }}>{children}</div>;

const message = (text: string) => (
  <div style={{ padding: "34px 0", textAlign: "center", fontSize: 11, color: "var(--txt3)", letterSpacing: ".04em" }}>{text}</div>
);

/** Render a chapter's child nodes (scenes) as the SceneRow list; leaves become a single row. */
function renderScenes(node: OutlineNodeDTO, chapterCode: string): ReactNode {
  const scenes = node.children;
  if (scenes.length === 0) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 11 }}>
        <SceneRow code={chapterCode} title={node.title} description={node.description} leftColor="var(--cyan)" />
      </div>
    );
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 11 }}>
      {scenes.map((scene, sceneIndex) => (
        <SceneRow key={scene.id} code={`${chapterCode}.${sceneIndex + 1}`} title={scene.title} description={scene.description} leftColor="var(--cyan)" />
      ))}
    </div>
  );
}

interface OutlineHandlers {
  onPick: (n: OutlineNodeDTO) => void;
  editingId: number | null;
  setEditingId: (id: number | null) => void;
  rename: (node: OutlineNodeDTO, title: string) => void;
  remove: (node: OutlineNodeDTO) => void;
  addChapter: (act: OutlineNodeDTO) => void;
  busy: boolean;
}

/** A node title that becomes an inline input on ✎ / double-click. */
function EditableTitle({ node, editing, onStart, onSave, style }: { node: OutlineNodeDTO; editing: boolean; onStart: () => void; onSave: (t: string) => void; style: CSSProperties }) {
  const [val, setVal] = useState(node.title);
  useEffect(() => { setVal(node.title); }, [node.title, editing]);
  if (editing) {
    return (
      <input
        autoFocus
        value={val}
        onChange={(e) => setVal(e.target.value)}
        onBlur={() => onSave(val.trim() || node.title)}
        onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); if (e.key === "Escape") { setVal(node.title); e.currentTarget.blur(); } }}
        aria-label="Rename node"
        style={{ ...style, background: "rgba(11,14,21,.7)", border: "1px solid var(--line-cy)", outline: "none", padding: "2px 6px" }}
      />
    );
  }
  return <span onDoubleClick={onStart} title="Double-click to rename" style={{ ...style, cursor: "text" }}>{node.title}</span>;
}

const nodeIconBtn: CSSProperties = { background: "transparent", border: "none", color: "var(--txt3)", cursor: "pointer", fontSize: 11, padding: "0 3px", lineHeight: 1 };

/** Render a top-level node as an expanded Act block; its children are chapter groups, grandchildren scene rows. */
function renderAct(act: OutlineNodeDTO, actIndex: number, h: OutlineHandlers): ReactNode {
  const chapters = act.children;
  return (
    <div key={act.id} style={{ border: "1px solid var(--line-cy)", marginBottom: 11 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 9, padding: "9px 11px", background: "rgba(76,194,255,.07)", borderBottom: "1px solid var(--line2)" }}>
        <span onClick={() => h.onPick(act)} title="Select for Logos" style={{ color: "var(--accent)", fontSize: 9, cursor: "pointer" }}>▾</span>
        <EditableTitle node={act} editing={h.editingId === act.id} onStart={() => h.setEditingId(act.id)} onSave={(t) => h.rename(act, t)} style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".08em", color: "#fff" }} />
        <span style={{ fontSize: 9, color: "var(--accent)", fontFamily: "'Chakra Petch'" }}>[{actIndex + 1}]</span>
        <span style={{ fontSize: 8.5, color: "var(--txt3)", marginLeft: "auto" }}>{chapters.length} ch</span>
        <button type="button" aria-label="Rename act" onClick={() => h.setEditingId(act.id)} style={nodeIconBtn}>✎</button>
        <button type="button" aria-label="Add chapter" title="Add chapter" disabled={h.busy} onClick={() => h.addChapter(act)} style={{ ...nodeIconBtn, color: "var(--accent)" }}>＋</button>
        <button type="button" aria-label="Delete act" onClick={() => h.remove(act)} style={nodeIconBtn}>✕</button>
      </div>
      <div style={{ padding: "9px 11px" }}>
        {chapters.length === 0
          ? (act.description ? <div style={{ fontSize: 9, color: "var(--txt3)", lineHeight: 1.4 }}>{act.description}</div> : cap("NO CHAPTERS — ＋ to add one"))
          : chapters.map((chapter, chapterIndex) => (
              <div key={chapter.id}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 5 }}>
                  <span style={{ fontSize: 8, letterSpacing: ".16em", color: "var(--txt3)" }}>CH {actIndex + 1}.{chapterIndex + 1}</span>
                  <EditableTitle node={chapter} editing={h.editingId === chapter.id} onStart={() => h.setEditingId(chapter.id)} onSave={(t) => h.rename(chapter, t)} style={{ fontSize: 10, letterSpacing: ".1em", color: "var(--txt2)", textTransform: "uppercase" }} />
                  <button type="button" aria-label="Rename chapter" onClick={() => h.setEditingId(chapter.id)} style={{ ...nodeIconBtn, fontSize: 9 }}>✎</button>
                  <button type="button" aria-label="Delete chapter" onClick={() => h.remove(chapter)} style={{ ...nodeIconBtn, fontSize: 9 }}>✕</button>
                </div>
                {renderScenes(chapter, `${actIndex + 1}.${chapterIndex + 1}`)}
              </div>
            ))}
      </div>
    </div>
  );
}

export function OutlinePanel(props: PanelProps) {
  const { api, projectId } = useStudio();
  const { data: acts, loading, error, refetch } = useOutline();
  const [busy, setBusy] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const count = acts?.length ?? 0;
  // publish the clicked act/chapter to the cross-panel bus → Logos "Outline" actions
  const { setSelection } = useSelection();
  const pick = (n: OutlineNodeDTO) => setSelection({ section: "Outline", nodeId: n.id, sceneId: null, text: n.title });

  const addAct = useCallback(async () => {
    if (projectId == null || busy) return;
    setBusy(true);
    try {
      await api.createOutlineNode(projectId, { title: `Act ${count + 1}` });
      refetch();
    } catch {
      /* no-op */
    } finally {
      setBusy(false);
    }
  }, [api, projectId, busy, count, refetch]);

  const rename = useCallback(async (node: OutlineNodeDTO, title: string) => {
    setEditingId(null);
    if (projectId == null || title === node.title) return;
    try { await api.updateOutlineNode(projectId, node.id, { title }); refetch(); } catch { /* no-op */ }
  }, [api, projectId, refetch]);

  const remove = useCallback(async (node: OutlineNodeDTO) => {
    if (projectId == null) return;
    try { await api.deleteOutlineNode(projectId, node.id); refetch(); } catch { /* no-op */ }
  }, [api, projectId, refetch]);

  const addChapter = useCallback(async (act: OutlineNodeDTO) => {
    if (projectId == null || busy) return;
    setBusy(true);
    try {
      await api.createOutlineNode(projectId, { title: `Chapter ${act.children.length + 1}`, parent_id: act.id });
      refetch();
    } catch { /* no-op */ } finally { setBusy(false); }
  }, [api, projectId, busy, refetch]);

  const handlers: OutlineHandlers = { onPick: pick, editingId, setEditingId, rename, remove, addChapter, busy };

  return (
    <PanelShell {...props}>
      <div data-screen-label="Outline Panel" style={panelBox}>
        <Corners />
        <div style={{ height: 42, flex: "none", display: "flex", alignItems: "center", gap: 10, padding: "0 14px", borderBottom: "1px solid var(--line)" }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".12em", color: "#fff" }}>OUTLINE</span>
          <span style={{ fontSize: 8, color: "var(--txt3)", letterSpacing: ".14em" }}>ACTS · CHAPTERS · SCENES</span>
          <div style={{ flex: 1 }} />
          <button type="button" onClick={addAct} disabled={busy || projectId == null} style={{ fontSize: 9, color: "#04060a", background: "var(--accent)", padding: "5px 11px", letterSpacing: ".08em", fontWeight: 600, border: "none", cursor: busy ? "default" : "pointer", opacity: busy || projectId == null ? 0.5 : 1 }}>＋ ACT</button>
        </div>
        <div style={{ flex: 1, overflowY: "auto", padding: 12 }}>
          {loading
            ? message("Loading outline…")
            : error
              ? message(`Couldn't load outline — ${error}`)
              : count === 0
                ? message("No outline yet — add one with ＋ ACT")
                : acts!.map((act, i) => renderAct(act, i, handlers))}
          {count > 0 && (
            <button type="button" onClick={addAct} disabled={busy || projectId == null} style={{ fontSize: 9, color: "var(--txt2)", background: "transparent", border: "1px dashed var(--line2)", padding: "6px 12px", letterSpacing: ".08em", cursor: busy ? "default" : "pointer", opacity: busy ? 0.5 : 1 }}>＋ ADD ACT</button>
          )}
        </div>
      </div>
    </PanelShell>
  );
}
