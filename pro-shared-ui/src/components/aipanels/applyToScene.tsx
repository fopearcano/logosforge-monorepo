import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import { useStudio } from "../../adapters/StudioProvider";
import { useSelection } from "../../adapters/selection";
import { useScenes } from "../../hooks";

/**
 * The single mutation gate for AI-proposed prose. The AI companions (Billy,
 * Logos) never write silently: they hand a proposed text to <ApplyDiffModal>,
 * which shows a real line diff against the active scene and only calls
 * api.updateScene on explicit confirm. `useApplyToScene` resolves the active
 * scene (from the cross-panel selection bus) and performs the write.
 */

export interface SceneTarget {
  id: number;
  title: string;
  content: string;
}

/** Resolve the active scene + a confirmed-apply writer over the core. */
export function useApplyToScene(): { target: SceneTarget | null; apply: (proposed: string) => Promise<void> } {
  const { api, projectId } = useStudio();
  const { selection } = useSelection();
  const scenes = useScenes();

  const target = useMemo<SceneTarget | null>(() => {
    const id = selection.sceneId;
    if (id == null) return null;
    const sc = scenes.data?.find((s) => s.id === id);
    if (sc) return { id: sc.id, title: sc.title || `Scene ${sc.id}`, content: sc.content ?? "" };
    return { id, title: `Scene ${id}`, content: "" };
  }, [selection.sceneId, scenes.data]);

  const apply = useCallback(
    async (proposed: string) => {
      if (projectId == null || target == null) throw new Error("No active scene — open a scene in the Manuscript first.");
      await api.updateScene(projectId, target.id, { content: proposed });
      // scene_changed fires on the core stream → every useScenes (incl. the editor)
      // refetches; refetch here too so this panel's copy is immediately current.
      scenes.refetch();
    },
    [api, projectId, target, scenes],
  );

  return { target, apply };
}

/* ---------------- line diff (LCS) ---------------- */

export interface DiffRow { type: "ctx" | "del" | "add"; text: string }

/** Minimal line-level LCS diff. Falls back to a whole-block replace for very large inputs. */
export function lineDiff(a: string, b: string): DiffRow[] {
  const A = a.split("\n");
  const B = b.split("\n");
  const m = A.length;
  const n = B.length;
  if (m > 1200 || n > 1200) {
    const rows: DiffRow[] = [];
    for (const l of A) rows.push({ type: "del", text: l });
    for (const l of B) rows.push({ type: "add", text: l });
    return rows;
  }
  // dp[i][j] = LCS length of A[i:] and B[j:]
  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array<number>(n + 1).fill(0));
  for (let i = m - 1; i >= 0; i--) {
    const row = dp[i]!;
    const below = dp[i + 1]!;
    for (let j = n - 1; j >= 0; j--) {
      row[j] = A[i] === B[j] ? below[j + 1]! + 1 : Math.max(below[j]!, row[j + 1]!);
    }
  }
  const rows: DiffRow[] = [];
  let i = 0;
  let j = 0;
  while (i < m && j < n) {
    const ai = A[i]!;
    const bj = B[j]!;
    if (ai === bj) { rows.push({ type: "ctx", text: ai }); i++; j++; }
    else if (dp[i + 1]![j]! >= dp[i]![j + 1]!) { rows.push({ type: "del", text: ai }); i++; }
    else { rows.push({ type: "add", text: bj }); j++; }
  }
  while (i < m) rows.push({ type: "del", text: A[i++]! });
  while (j < n) rows.push({ type: "add", text: B[j++]! });
  return rows;
}

/* ---------------- the confirm-gate modal ---------------- */

const backdrop: CSSProperties = {
  position: "fixed", inset: 0, zIndex: 1000, display: "grid", placeItems: "center",
  background: "rgba(2,3,6,.66)", backdropFilter: "blur(2px)", padding: 24,
};
const modal: CSSProperties = {
  width: "min(760px,94vw)", maxHeight: "84vh", display: "flex", flexDirection: "column",
  background: "linear-gradient(180deg,var(--raised),var(--panel2))", border: "1px solid var(--crimson)",
  boxShadow: "0 30px 90px rgba(0,0,0,.8),0 0 0 1px rgba(232,68,58,.1)",
  fontFamily: "'JetBrains Mono',monospace", color: "var(--txt)",
};
const rowBase: CSSProperties = { padding: "1px 10px", whiteSpace: "pre-wrap", wordBreak: "break-word", fontFamily: "'Courier Prime',monospace", fontSize: 12.5, lineHeight: 1.65 };

export function ApplyDiffModal({
  title,
  badge,
  original,
  proposed,
  onConfirm,
  onClose,
}: {
  title: string;
  badge: string;
  original: string;
  proposed: string;
  /** Perform the write. Resolves → modal closes; rejects → error shown. */
  onConfirm: () => Promise<void>;
  onClose: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const rows = useMemo(() => lineDiff(original, proposed), [original, proposed]);
  const adds = rows.reduce((k, r) => k + (r.type === "add" ? 1 : 0), 0);
  const dels = rows.reduce((k, r) => k + (r.type === "del" ? 1 : 0), 0);
  const noChange = adds === 0 && dels === 0;

  const confirm = useCallback(async () => {
    if (busy || noChange) return;
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }, [busy, noChange, onConfirm, onClose]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) { e.preventDefault(); onClose(); }
      else if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); void confirm(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose, confirm]);

  return (
    <div style={backdrop} onMouseDown={() => { if (!busy) onClose(); }}>
      <div style={modal} onMouseDown={(e) => e.stopPropagation()}>
        {/* header */}
        <div style={{ flex: "none", padding: "13px 16px", borderBottom: "1px solid var(--line)", display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontFamily: "'Chakra Petch',sans-serif", fontWeight: 600, fontSize: 15, letterSpacing: ".08em", color: "var(--strong)" }}>CONTROLLED APPLY</span>
          <span style={{ fontSize: 9, color: "var(--cyan)", border: "1px solid var(--line-cy,#2b6f8f)", padding: "2px 8px", letterSpacing: ".1em" }}>{badge} · {title}</span>
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 9, color: "var(--green)" }}>+{adds}</span>
          <span style={{ fontSize: 9, color: "var(--blocking)" }}>−{dels}</span>
          <button type="button" onClick={() => { if (!busy) onClose(); }} aria-label="Close" style={{ background: "transparent", border: "none", color: "var(--txt3)", fontSize: 14, cursor: busy ? "default" : "pointer", padding: "0 2px" }}>✕</button>
        </div>

        {/* sub-caption */}
        <div style={{ flex: "none", padding: "6px 16px", borderBottom: "1px solid var(--line2)", fontSize: 8.5, letterSpacing: ".14em", color: "var(--txt3)" }}>
          DIFF · ORIGINAL → PROPOSED · confirm writes to the scene (non-destructive — the editor updates live)
        </div>

        {/* diff body */}
        <div style={{ flex: 1, overflowY: "auto", padding: "12px 6px", minHeight: 90 }}>
          {noChange ? (
            <div style={{ padding: "30px 0", textAlign: "center", fontSize: 11, color: "var(--txt3)" }}>No changes — the proposal matches the scene.</div>
          ) : (
            rows.map((r, i) =>
              r.type === "ctx" ? (
                <div key={i} style={{ ...rowBase, color: "var(--txt3)" }}>{`  ${r.text}`}</div>
              ) : r.type === "del" ? (
                <div key={i} style={{ ...rowBase, background: "rgba(255,82,96,.10)", borderLeft: "2px solid var(--blocking)", color: "var(--txt2)" }}>
                  <span style={{ color: "var(--blocking)" }}>− </span>
                  <span style={{ textDecoration: "line-through", textDecorationColor: "rgba(255,82,96,.5)" }}>{r.text}</span>
                </div>
              ) : (
                <div key={i} style={{ ...rowBase, background: "rgba(98,217,154,.10)", borderLeft: "2px solid var(--green)", color: "var(--txt)" }}>
                  <span style={{ color: "var(--green)" }}>+ </span>{r.text}
                </div>
              ),
            )
          )}
        </div>

        {/* footer */}
        <div style={{ flex: "none", borderTop: "1px solid var(--line)", display: "flex", alignItems: "center", gap: 11, padding: "12px 16px" }}>
          {error
            ? <span style={{ fontSize: 9, color: "var(--crimson)", lineHeight: 1.4 }}>⚠ {error}</span>
            : <span style={{ fontSize: 8.5, color: "var(--txt3)", letterSpacing: ".04em" }}>↳ nothing is auto-applied · this is the single mutation gate</span>}
          <div style={{ flex: 1 }} />
          <button type="button" onClick={() => { if (!busy) onClose(); }} disabled={busy}
            style={{ fontSize: 10, letterSpacing: ".1em", color: "var(--txt2)", border: "1px solid var(--line2)", background: "transparent", padding: "8px 16px", cursor: busy ? "default" : "pointer" }}>CANCEL</button>
          <button type="button" onClick={() => void confirm()} disabled={busy || noChange}
            style={{ fontSize: 11, letterSpacing: ".1em", color: "var(--on-accent)", background: "var(--green)", border: "none", padding: "9px 22px", fontWeight: 700, boxShadow: "0 0 18px rgba(98,217,154,.35)", cursor: busy || noChange ? "default" : "pointer", opacity: busy || noChange ? 0.5 : 1 }}>
            {busy ? "APPLYING…" : "✓ APPLY"}
          </button>
        </div>
      </div>
    </div>
  );
}
