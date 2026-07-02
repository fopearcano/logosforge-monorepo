import { useCallback, useEffect, useState, type CSSProperties, type ReactNode } from "react";
import type { PsykeEntryDTO } from "@logosforge/ui-contracts";
import { useSelection } from "../../adapters/selection";
import { useStudio } from "../../adapters/StudioProvider";
import { PanelShell, type PanelProps } from "../shell/PanelShell";
import { usePsykeEntries, usePsykeRelations, usePsykeProgressions } from "../../hooks";

const panelBox: CSSProperties = {
  position: "relative",
  width: "100%",
  height: "100%",
  background: "linear-gradient(180deg,#080a0f,#05070b)",
  border: "1px solid var(--line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)",
  overflow: "hidden",
  display: "flex",
};

// ── PSYKE type → icon / accent / label. `details` schema varies by type. ──
type Meta = { type: string; icon: string; color: string; label: string };
const OTHER: Meta = { type: "other", icon: "▣", color: "var(--txt3)", label: "Other" };
const TYPES: Meta[] = [
  { type: "character", icon: "◆", color: "var(--c-char)", label: "Character" },
  { type: "place", icon: "▲", color: "var(--c-place)", label: "Place" },
  { type: "object", icon: "◇", color: "var(--c-obj)", label: "Object" },
  { type: "lore", icon: "⬢", color: "var(--c-lore)", label: "Lore" },
  { type: "theme", icon: "✦", color: "var(--c-theme)", label: "Theme" },
  OTHER,
];
const META: Record<string, Meta> = {};
for (const t of TYPES) META[t.type] = t;
const meta = (type: string): Meta => META[type] ?? OTHER;

/** Read a string field out of the loose `details` record (empty when absent). */
const str = (d: Record<string, unknown>, k: string): string => (typeof d[k] === "string" ? (d[k] as string) : "");

/** The WANT/NEED/LIE/WOUND triptych — only rendered for fields the entry actually has. */
const PSYCH = [
  { key: "want", label: "WANT · external", color: "var(--cyan)" },
  { key: "need", label: "NEED · internal", color: "var(--green)" },
  { key: "lie", label: "LIE · misbelief", color: "var(--blocking)" },
  { key: "wound", label: "WOUND · ghost", color: "var(--amber)" },
];

const subLabel = (t: string, pt = 4) => <div style={{ fontSize: 7.5, letterSpacing: ".26em", color: "var(--txt3)", padding: `${pt}px 5px 7px` }}>{t}</div>;

function TypeRow({ icon, iconColor, label, count, active = false, onClick }: { icon: string; iconColor: string; label: string; count: number; active?: boolean; onClick?: () => void }) {
  return (
    <div className={active ? undefined : "lf-row"} onClick={onClick} style={{ display: "flex", alignItems: "center", gap: 9, height: 25, padding: "0 8px", background: active ? "rgba(76,194,255,.08)" : undefined, color: active ? "#fff" : "var(--txt2)", fontSize: 10, cursor: "pointer" }}>
      <span style={{ color: iconColor }}>{icon}</span><span style={{ flex: 1 }}>{label}</span><span style={{ color: active ? "var(--txt2)" : "var(--txt3)" }}>{count}</span>
    </div>
  );
}

function EntryRow({ icon, iconColor, barColor, border = "var(--line2)", name, sub, active = false, right, onClick }: { icon: string; iconColor: string; barColor: string; border?: string; name: string; sub: ReactNode; active?: boolean; right?: ReactNode; onClick?: () => void }) {
  return (
    <div className={active ? undefined : "lf-row2"} onClick={onClick} style={{ position: "relative", display: "flex", alignItems: "center", gap: 10, padding: "10px 12px", cursor: "pointer", background: active ? "linear-gradient(90deg,rgba(76,194,255,.12),transparent)" : undefined, borderBottom: "1px solid var(--line2)" }}>
      {active && <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 2, background: barColor, boxShadow: `0 0 8px ${barColor}` }} />}
      <span style={{ width: 22, height: 22, display: "grid", placeItems: "center", border: `1px solid ${border}`, color: iconColor, fontSize: 11 }}>{icon}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12, color: active ? "#fff" : "var(--txt)", fontFamily: "'Chakra Petch'", letterSpacing: active ? ".04em" : undefined, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{name}</div>
        <div style={{ fontSize: 8, color: "var(--txt3)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{sub}</div>
      </div>
      {right}
    </div>
  );
}

const linkBadge = (t: string) => <span style={{ fontSize: 8, color: "var(--txt2)", border: "1px solid var(--line2)", padding: "1px 5px" }}>{t}</span>;
const globalBadge = <span style={{ fontSize: 7, color: "var(--c-place)", border: "1px solid rgba(245,177,51,.3)", padding: "1px 4px" }}>GLOBAL</span>;

function Triptych({ label, color, text }: { label: string; color: string; text: string }) {
  return (
    <div style={{ border: "1px solid var(--line2)", borderLeft: `2px solid ${color}`, padding: "11px 12px", background: "rgba(11,14,21,.4)" }}>
      <div style={{ fontSize: 8, letterSpacing: ".18em", color, marginBottom: 5 }}>{label}</div>
      <div style={{ fontSize: 12, color: "var(--txt)", lineHeight: 1.4 }}>{text}</div>
    </div>
  );
}

const tab = (label: ReactNode, active = false) => (
  <span style={{ position: "relative", padding: active ? "7px 14px 9px" : "7px 14px", color: active ? "#fff" : "var(--txt3)" }}>
    {label}{active && <span style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 2, background: "var(--accent)", boxShadow: "0 0 8px var(--accent)" }} />}
  </span>
);

const sectLabel = (t: string, mb = 9): ReactNode => <div style={{ fontSize: 8, letterSpacing: ".26em", color: "var(--txt3)", marginBottom: mb }}>{t}</div>;
const muted = (t: string) => <div style={{ fontSize: 11, color: "var(--txt3)", fontStyle: "italic" }}>{t}</div>;
const centered = (t: string) => <div style={{ flex: 1, display: "grid", placeItems: "center", fontSize: 11, color: "var(--txt3)", letterSpacing: ".04em" }}>{t}</div>;

const ebtn = (accent = false): CSSProperties => ({
  background: accent ? "var(--accent)" : "transparent",
  color: accent ? "#04060a" : "var(--txt2)",
  border: accent ? "none" : "1px solid var(--line2)",
  padding: "6px 12px",
  fontSize: 10,
  letterSpacing: ".1em",
  cursor: "pointer",
  fontWeight: accent ? 600 : 400,
});
const efield: CSSProperties = { background: "rgba(11,14,21,.6)", border: "1px solid var(--line2)", color: "#fff", fontSize: 13, padding: "8px 10px", outline: "none", fontFamily: "inherit" };

/** Create/edit a PSYKE bible entry (name / type / aliases / notes). */
function PsykeEditor({ entry, onClose, onChanged }: { entry: PsykeEntryDTO; onClose: () => void; onChanged: () => void }) {
  const { api, projectId } = useStudio();
  const [name, setName] = useState(entry.name);
  const [type, setType] = useState(entry.type);
  const [aliases, setAliases] = useState(entry.aliases.join(", "));
  const [notes, setNotes] = useState(entry.notes);
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (projectId == null) return;
    setBusy(true);
    try {
      await api.updatePsyke(projectId, entry.id, { name, type, aliases: aliases.split(",").map((s) => s.trim()).filter(Boolean), notes });
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
      await api.deletePsyke(projectId, entry.id);
      onChanged();
      onClose();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ position: "absolute", inset: 0, zIndex: 6, background: "linear-gradient(180deg,#0a0d13,#05070b)", display: "flex", flexDirection: "column", padding: 20, gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ fontFamily: "'Chakra Petch'", fontSize: 12, letterSpacing: ".16em", color: "var(--accent)" }}>EDIT ENTRY</span>
        <div style={{ flex: 1 }} />
        <button type="button" onClick={remove} disabled={busy} style={{ ...ebtn(), color: "var(--crimson)", borderColor: "var(--crimson)" }}>DELETE</button>
        <button type="button" onClick={onClose} disabled={busy} style={ebtn()}>CANCEL</button>
        <button type="button" onClick={save} disabled={busy} style={ebtn(true)}>{busy ? "SAVING…" : "SAVE"}</button>
      </div>
      <div style={{ display: "flex", gap: 12 }}>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" aria-label="Entry name" style={{ ...efield, flex: 2, fontFamily: "'Chakra Petch'", fontSize: 16 }} />
        <select value={type} onChange={(e) => setType(e.target.value)} aria-label="Entry type" style={{ ...efield, flex: 1 }}>
          {TYPES.map((t) => (
            <option key={t.type} value={t.type}>{t.label}</option>
          ))}
        </select>
      </div>
      <input value={aliases} onChange={(e) => setAliases(e.target.value)} placeholder="Aliases (comma-separated)" aria-label="Aliases" style={efield} />
      <textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Notes — who they are, what they want…" aria-label="Notes" style={{ ...efield, flex: 1, resize: "none", fontFamily: "'Courier Prime',monospace", lineHeight: 1.6 }} />
    </div>
  );
}

export function PsykeBible(props: PanelProps) {
  const { api, projectId } = useStudio();
  const { data: entriesData, loading, error, refetch } = usePsykeEntries();
  const { data: relData } = usePsykeRelations();
  const { data: progData } = usePsykeProgressions();
  const entries = entriesData ?? [];
  const relations = relData ?? [];
  const progressions = progData ?? [];

  const [selId, setSelId] = useState<number | null>(null);
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<PsykeEntryDTO | null>(null);
  const [busy, setBusy] = useState(false);
  const q = query.trim().toLowerCase();

  const createNew = useCallback(async () => {
    if (projectId == null || busy) return;
    setBusy(true);
    try {
      const created = await api.createPsyke(projectId, { name: "New entry", type: "character" });
      refetch();
      setSelId(created.id);
      setEditing(created);
    } catch {
      /* no-op */
    } finally {
      setBusy(false);
    }
  }, [api, projectId, busy, refetch]);

  const byId = new Map<number, PsykeEntryDTO>(entries.map((e) => [e.id, e]));
  const relCountOf = (id: number) => relations.filter((r) => r.source_id === id || r.target_id === id).length;

  const filtered = entries.filter(
    (e) => (!typeFilter || e.type === typeFilter) && (!q || e.name.toLowerCase().includes(q) || e.aliases.some((a) => a.toLowerCase().includes(q))),
  );
  const selected = filtered.find((e) => e.id === selId) ?? filtered[0];

  // Publish the focused bible entry to the cross-panel selection bus so Logos's PSYKE
  // actions operate on it. Only on an EXPLICIT selection (selId set) — not the default
  // first-entry — so merely opening this panel doesn't clobber the writer's active
  // (e.g. manuscript) selection.
  const { setSelection } = useSelection();
  useEffect(() => {
    if (selId != null && selected) setSelection({ section: "PSYKE", nodeId: selected.id, sceneId: null, text: selected.name });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selId]);

  const selRelations = selected ? relations.filter((r) => r.source_id === selected.id || r.target_id === selected.id) : [];
  const selProg = selected
    ? progressions.filter((p) => p.entry_id === selected.id).slice().sort((a, b) => a.sort_order - b.sort_order)
    : [];
  const psychCards = selected ? PSYCH.map((p) => ({ ...p, text: str(selected.details, p.key) })).filter((p) => p.text) : [];
  const selMeta = selected ? meta(selected.type) : OTHER;

  return (
    <PanelShell {...props}>
      <div data-screen-label="PSYKE Bible" style={panelBox}>
        <div style={{ position: "absolute", top: -1, left: -1, width: 14, height: 14, borderTop: "1px solid var(--crimson)", borderLeft: "1px solid var(--crimson)", zIndex: 3 }} />
        <div style={{ position: "absolute", top: 3, left: 3, width: 5, height: 5, background: "var(--crimson)", zIndex: 3 }} />

        {/* filter sidebar */}
        <div style={{ width: 212, flex: "none", borderRight: "1px solid var(--line)", background: "#06080c", display: "flex", flexDirection: "column" }}>
          <div style={{ height: 38, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 12px", borderBottom: "1px solid var(--line2)" }}>
            <span style={{ fontSize: 8.5, letterSpacing: ".24em", color: "var(--txt3)" }}>FILTER</span>
            <span style={{ fontFamily: "'Chakra Petch'", fontSize: 12, color: "var(--accent)" }}>{entries.length}</span>
          </div>
          <div style={{ flex: 1, overflowY: "auto", padding: "10px 9px" }}>
            {subLabel("TYPE")}
            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              {TYPES.map((t) => (
                <TypeRow key={t.type} icon={t.icon} iconColor={t.color} label={t.label} count={entries.filter((e) => e.type === t.type).length} active={typeFilter === t.type} onClick={() => setTypeFilter(typeFilter === t.type ? null : t.type)} />
              ))}
            </div>
            {subLabel("ROLE", 14)}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 5, padding: "0 4px" }}>
              {["Protagonist", "Deuteragonist", "Antagonist", "Supporting"].map((r) => (
                <span key={r} style={{ fontSize: 8, color: "var(--txt2)", border: "1px solid var(--line2)", padding: "2px 7px" }}>{r}</span>
              ))}
            </div>
            {subLabel("FLAGS", 14)}
            <div style={{ display: "flex", flexDirection: "column", gap: 6, padding: "0 5px", fontSize: 9, color: "var(--txt2)" }}>
              <label style={{ display: "flex", alignItems: "center", gap: 7 }}><span style={{ width: 11, height: 11, border: "1px solid var(--line2)" }} />is_global</label>
              <label style={{ display: "flex", alignItems: "center", gap: 7 }}><span style={{ width: 11, height: 11, border: "1px solid var(--line2)" }} />has memory layer</label>
              <label style={{ display: "flex", alignItems: "center", gap: 7 }}><span style={{ width: 11, height: 11, border: "1px solid var(--line2)" }} />CI-aligned</label>
            </div>
          </div>
        </div>

        {/* entry list */}
        <div style={{ width: 330, flex: "none", borderRight: "1px solid var(--line)", display: "flex", flexDirection: "column" }}>
          <div style={{ height: 38, display: "flex", alignItems: "center", gap: 8, padding: "0 11px", borderBottom: "1px solid var(--line2)" }}>
            <span style={{ color: "var(--accent)" }}>⌕</span>
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search name · aliases…" style={{ flex: 1, minWidth: 0, background: "transparent", border: "none", outline: "none", fontSize: 10, color: "var(--txt)", fontFamily: "inherit" }} />
            <button type="button" onClick={createNew} disabled={busy || projectId == null} style={{ fontSize: 8, color: "#04060a", background: "var(--accent)", padding: "4px 9px", fontWeight: 600, border: "none", cursor: busy ? "default" : "pointer", opacity: busy || projectId == null ? 0.5 : 1 }}>＋ NEW</button>
          </div>
          <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column" }}>
            {loading
              ? centered("Loading PSYKE entries…")
              : error
                ? centered(`Couldn't load PSYKE — ${error}`)
                : entries.length === 0
                  ? centered("No PSYKE entries yet — ＋ NEW")
                  : filtered.length === 0
                    ? centered("No entries match the filter")
                    : filtered.map((e) => {
                        const m = meta(e.type);
                        const rc = relCountOf(e.id);
                        const role = str(e.details, "role");
                        const sub = e.aliases.length ? `a.k.a. ${e.aliases.join(" · ")}` : role || m.label;
                        return (
                          <EntryRow
                            key={e.id}
                            icon={m.icon}
                            iconColor={m.color}
                            barColor={m.color}
                            border={selected?.id === e.id ? m.color : "var(--line2)"}
                            name={e.name}
                            sub={sub}
                            active={selected?.id === e.id}
                            onClick={() => setSelId(e.id)}
                            right={<>{e.is_global && globalBadge}{rc > 0 && linkBadge(`↔${rc}`)}</>}
                          />
                        );
                      })}
          </div>
          <div style={{ height: 24, flex: "none", display: "flex", alignItems: "center", padding: "0 11px", borderTop: "1px solid var(--line2)", fontSize: 8, letterSpacing: ".1em", color: "var(--txt3)" }}>
            SHOWING {filtered.length} / {entries.length}{typeFilter ? ` · ${meta(typeFilter).label.toUpperCase()}` : ""}
          </div>
        </div>

        {/* dossier */}
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
          {!selected ? (
            centered(loading ? "Loading…" : "Select an entry")
          ) : (
            <>
              <div style={{ padding: "18px 22px 14px", borderBottom: "1px solid var(--line)", background: "linear-gradient(180deg,rgba(76,194,255,.06),transparent)", position: "relative" }}>
                <button type="button" onClick={() => setEditing(selected)} style={{ position: "absolute", top: 14, right: 18, zIndex: 2, ...ebtn() }}>✎ EDIT</button>
                <div style={{ display: "flex", alignItems: "flex-start", gap: 16 }}>
                  <div style={{ width: 54, height: 54, flex: "none", display: "grid", placeItems: "center", border: `1px solid ${selMeta.color}`, color: selMeta.color, fontSize: 24, boxShadow: "0 0 18px rgba(76,194,255,.25) inset" }}>{selMeta.icon}</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                      <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 700, fontSize: 26, letterSpacing: ".04em", color: "#fff", textShadow: "0 0 16px rgba(76,194,255,.3)" }}>{selected.name}</span>
                      <span style={{ fontSize: 8, letterSpacing: ".16em", color: selMeta.color, border: `1px solid ${selMeta.color}`, padding: "2px 7px" }}>{selMeta.label.toUpperCase()}</span>
                      {selected.is_global && <span style={{ fontSize: 8, letterSpacing: ".16em", color: "var(--c-place)", border: "1px solid rgba(245,177,51,.3)", padding: "2px 7px" }}>GLOBAL</span>}
                    </div>
                    {selected.aliases.length > 0 && <div style={{ fontSize: 9, color: "var(--txt3)", marginTop: 4 }}>a.k.a. {selected.aliases.join(" · ")}</div>}
                    <div style={{ display: "flex", gap: 18, marginTop: 7, fontSize: 10, color: "var(--txt2)", flexWrap: "wrap" }}>
                      <span>ROLE <span style={{ color: "var(--txt)" }}>{str(selected.details, "role") || "—"}</span></span>
                      <span>RELATIONS <span style={{ color: "var(--accent)" }}>{selRelations.length}</span></span>
                      <span>STATES <span style={{ color: "var(--accent)" }}>{selProg.length}</span></span>
                    </div>
                  </div>
                </div>
                <div style={{ display: "flex", gap: 0, marginTop: 16, fontSize: 9.5, letterSpacing: ".12em" }}>
                  {tab("OVERVIEW", true)}{tab("DETAILS")}{tab("MEMORY")}
                  {tab(<>RELATIONS <span style={{ color: "var(--txt2)" }}>{selRelations.length}</span></>)}
                  {tab(<>PROGRESSIONS <span style={{ color: "var(--txt2)" }}>{selProg.length}</span></>)}
                  {tab("APPEARANCES")}
                </div>
              </div>

              <div style={{ flex: 1, overflowY: "auto", padding: "18px 22px" }}>
                {sectLabel("PSYCHOLOGY · WANT / NEED / LIE", 10)}
                {psychCards.length === 0 ? (
                  <div style={{ marginBottom: 20 }}>{muted("No psychology fields recorded for this entry — add them in the entry editor.")}</div>
                ) : (
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 11, marginBottom: 20 }}>
                    {psychCards.map((p) => <Triptych key={p.key} label={p.label} color={p.color} text={p.text} />)}
                  </div>
                )}

                {sectLabel("NOTES")}
                <div style={{ fontFamily: "'Courier Prime'", fontSize: 13, color: "var(--txt2)", lineHeight: 1.6, marginBottom: 20 }}>
                  {selected.notes ? selected.notes : muted("No notes yet.")}
                </div>

                <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
                  <div style={{ flex: 1, minWidth: 220 }}>
                    {sectLabel("KEY RELATIONS")}
                    {selRelations.length === 0 ? (
                      muted("No relations.")
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        {selRelations.map((r) => {
                          const outgoing = r.source_id === selected.id;
                          const otherName = outgoing ? r.target : r.source;
                          const otherType = byId.get(outgoing ? r.target_id : r.source_id)?.type ?? "other";
                          const m = meta(otherType);
                          return (
                            <div key={r.id} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 10, color: "var(--txt2)" }}>
                              <span style={{ color: m.color }}>{m.icon} {otherName}</span>
                              <span style={{ color: "var(--txt3)" }}>— {outgoing ? "" : "← "}{r.relation_type}{outgoing ? " →" : ""}</span>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                  <div style={{ flex: 1, minWidth: 220 }}>
                    {sectLabel("PROGRESSION · scene-pinned states")}
                    {selProg.length === 0 ? (
                      muted("No progression states yet.")
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
                        {selProg.map((p) => (
                          <div key={p.id} style={{ borderLeft: "2px solid var(--accent)", padding: "2px 0 2px 10px" }}>
                            <div style={{ fontSize: 11, color: "var(--txt)", lineHeight: 1.4 }}>{p.text}</div>
                            {p.scene_title && <div style={{ fontSize: 8, color: "var(--txt3)", marginTop: 2 }}>↳ {p.scene_title}</div>}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </>
          )}
        </div>

        {editing && <PsykeEditor entry={editing} onClose={() => setEditing(null)} onChanged={refetch} />}
      </div>
    </PanelShell>
  );
}
