/**
 * Theme Scenes (PSYKE Story Bible group) — tag which scenes a theme appears in.
 * The writer-facing end of the structured Scene⇄theme link: pick a theme, then
 * check the scenes it's present in. These links are what let a theme read present
 * in the Narrative Dashboard (source "scene_link") instead of relying on prose
 * name-matching. Wraps usePsykeEntries + useScenes and the getThemeScenes /
 * setThemeScenes ApiClient methods (backed by the core's SceneThemeLink table).
 */
import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useScenes, usePsykeEntries } from "../../hooks";
import { useStudio } from "../../adapters/StudioProvider";

const panelBox: CSSProperties = {
  position: "relative", width: "100%", height: "100%",
  background: "linear-gradient(180deg,#080a0f,#05070b)",
  border: "1px solid var(--line)", boxShadow: "0 16px 60px rgba(0,0,0,.6)",
  overflow: "hidden", display: "flex", flexDirection: "column",
};

const message = (text: string) => (
  <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: "34px 0", textAlign: "center", fontSize: 11, color: "var(--txt3)", letterSpacing: ".04em" }}>{text}</div>
);

export function ThemeScenes(props: PanelProps) {
  const { api, projectId } = useStudio();
  const { data: psyke, loading, error } = usePsykeEntries();
  const { data: scenes } = useScenes();
  const [selected, setSelected] = useState<number | null>(null);
  const [tagged, setTagged] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const themes = useMemo(
    () => (psyke ?? []).filter((e) => e.type === "theme").sort((a, b) => a.name.localeCompare(b.name)),
    [psyke],
  );
  // Fall back to the first theme if the manually-selected one no longer exists
  // (e.g. it was deleted elsewhere) — never hold a stale id that would 404.
  const activeId = (selected != null && themes.some((t) => t.id === selected)) ? selected : (themes[0]?.id ?? null);
  const sceneList = useMemo(
    () => [...(scenes ?? [])].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0)),
    [scenes],
  );

  // Load the active theme's tagged scenes whenever it (or the project) changes.
  useEffect(() => {
    let cancelled = false;
    if (projectId == null || activeId == null) { setTagged(new Set()); return; }
    api.getThemeScenes(projectId, activeId)
      .then((r) => { if (!cancelled) setTagged(new Set(r.scene_ids)); })
      .catch((e) => { if (!cancelled) setActionError(`Couldn't load theme scenes — ${e instanceof Error ? e.message : String(e)}`); });
    return () => { cancelled = true; };
  }, [api, projectId, activeId]);

  async function toggle(sceneId: number) {
    if (projectId == null || activeId == null || busy) return;
    const next = new Set(tagged);
    next.has(sceneId) ? next.delete(sceneId) : next.add(sceneId);
    setTagged(next);  // optimistic
    setBusy(true);
    setActionError(null);
    try {
      const r = await api.setThemeScenes(projectId, activeId, [...next]);
      setTagged(new Set(r.scene_ids));  // reconcile with the server's filtered set
    } catch (e) {
      setActionError(`Couldn't save — ${e instanceof Error ? e.message : String(e)}`);
      const r = await api.getThemeScenes(projectId, activeId).catch(() => null);
      if (r) setTagged(new Set(r.scene_ids));  // revert to the stored truth
    } finally {
      setBusy(false);
    }
  }

  return (
    <PanelShell {...props}>
      <div data-screen-label="Theme Scenes" style={panelBox}>
        <Corners />
        {/* header */}
        <div style={{ height: 40, flex: "none", display: "flex", alignItems: "center", gap: 13, padding: "0 16px", borderBottom: "1px solid var(--line)" }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".12em", color: "#fff" }}>THEME SCENES</span>
          {themes.length > 0 && (
            <select
              value={activeId != null ? String(activeId) : ""}
              onChange={(e) => setSelected(e.target.value ? Number(e.target.value) : null)}
              disabled={busy || projectId == null}
              style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 11, color: "var(--txt)", background: "#11151e", border: "1px solid var(--line2)", padding: "4px 7px", minWidth: 160 }}
            >
              {themes.map((t) => <option key={t.id} value={String(t.id)}>{t.name}</option>)}
            </select>
          )}
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 9, color: "var(--txt3)", letterSpacing: ".1em" }}>
            <span style={{ color: "var(--accent)" }}>{tagged.size}</span> / {sceneList.length} SCENES TAGGED
          </span>
        </div>

        {/* body */}
        {loading
          ? message("Loading themes…")
          : error
          ? message(`Couldn't load themes — ${error}`)
          : themes.length === 0
          ? message("No themes in the bible yet — add a 'theme' PSYKE entry")
          : sceneList.length === 0
          ? message("No scenes yet")
          : (
            <div style={{ flex: 1, overflowY: "auto", padding: "10px 14px", display: "flex", flexDirection: "column", gap: 5 }}>
              {actionError && (
                <div style={{ fontSize: 10, color: "var(--blocking)", border: "1px solid rgba(255,82,96,.35)", background: "rgba(255,82,96,.06)", padding: "6px 9px" }}>{actionError}</div>
              )}
              {sceneList.map((s, i) => {
                const on = tagged.has(s.id);
                return (
                  <div
                    key={s.id}
                    onClick={() => toggle(s.id)}
                    style={{ display: "flex", alignItems: "center", gap: 11, padding: "7px 11px", cursor: busy ? "default" : "pointer", border: `1px solid ${on ? "var(--line-cy)" : "var(--line2)"}`, background: on ? "rgba(76,194,255,.07)" : "rgba(11,14,21,.4)", opacity: busy ? 0.6 : 1 }}
                  >
                    <span style={{ width: 11, height: 11, flex: "none", border: on ? "1px solid var(--line-cy)" : "1px solid var(--line2)", background: on ? "var(--accent)" : undefined }} />
                    <span style={{ fontSize: 8.5, color: "var(--txt3)", width: 24, flex: "none" }}>{s.sort_order ?? i + 1}</span>
                    <span style={{ fontFamily: "'Chakra Petch'", fontSize: 11.5, color: on ? "#fff" : "var(--txt2)", letterSpacing: ".02em", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{s.title || `Scene ${s.id}`}</span>
                  </div>
                );
              })}
            </div>
          )}
      </div>
    </PanelShell>
  );
}
