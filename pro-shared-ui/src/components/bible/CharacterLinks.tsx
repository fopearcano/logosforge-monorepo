/**
 * Character Links (PSYKE Story Bible group) — view + manage the stable
 * Character⇄PSYKE binding. Lists the manuscript cast, shows each character's
 * linked bible entry, lets the writer set/clear the link via a picker, and
 * runs the name-based auto-linker. Wraps useCharacters + usePsykeEntries and the
 * updateCharacter / backfillCharacterLinks ApiClient methods (the FK the core
 * stores in Character.psyke_entry_id).
 */
import { useState, type CSSProperties } from "react";
import type { CharacterDTO } from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useCharacters, usePsykeEntries } from "../../hooks";
import { useStudio } from "../../adapters/StudioProvider";

const panelBox: CSSProperties = {
  position: "relative", width: "100%", height: "100%",
  background: "linear-gradient(180deg,var(--panel),var(--base))",
  border: "1px solid var(--line)", boxShadow: "0 16px 60px rgba(0,0,0,.6)",
  overflow: "hidden", display: "flex", flexDirection: "column",
};

const message = (text: string) => (
  <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: "34px 0", textAlign: "center", fontSize: 11, color: "var(--txt3)", letterSpacing: ".04em" }}>{text}</div>
);

export function CharacterLinks(props: PanelProps) {
  const { api, projectId } = useStudio();
  const { data: characters, loading, error, refetch } = useCharacters();
  const { data: psyke } = usePsykeEntries();
  const [busy, setBusy] = useState<number | "auto" | "create" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [newName, setNewName] = useState("");

  // Only 'character' bible entries are valid link targets (matches the core's
  // server-side validation).
  const charEntries = (psyke ?? []).filter((e) => e.type === "character");
  const entryName = new Map(charEntries.map((e) => [e.id, e.name]));
  const cast = [...(characters ?? [])].sort((a, b) => a.name.localeCompare(b.name));
  const linked = cast.filter((c) => c.psyke_entry_id != null).length;

  async function setLink(character: CharacterDTO, entryId: number | null) {
    if (projectId == null) return;
    setBusy(character.id);
    setActionError(null);
    try {
      // null clears the link (explicit-null semantics in the core PATCH).
      await api.updateCharacter(projectId, character.id, { psyke_entry_id: entryId });
      refetch();
    } catch (e) {
      setActionError(`Couldn't update ${character.name} — ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(null);
    }
  }

  async function createCharacter() {
    if (projectId == null) return;
    const name = newName.trim();
    if (!name) return;
    setBusy("create");
    setActionError(null);
    try {
      await api.createCharacter(projectId, { name });
      setNewName("");
      refetch();
    } catch (e) {
      setActionError(`Couldn't add ${name} — ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(null);
    }
  }

  async function removeCharacter(character: CharacterDTO) {
    if (projectId == null) return;
    setBusy(character.id);
    setActionError(null);
    try {
      await api.deleteCharacter(projectId, character.id);
      refetch();
    } catch (e) {
      setActionError(`Couldn't delete ${character.name} — ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(null);
    }
  }

  async function autoLink() {
    if (projectId == null) return;
    setBusy("auto");
    setActionError(null);
    try {
      await api.backfillCharacterLinks(projectId);
      refetch();
    } catch (e) {
      setActionError(`Auto-link failed — ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(null);
    }
  }

  return (
    <PanelShell {...props}>
      <div data-screen-label="Character Links" style={panelBox}>
        <Corners />
        {/* header */}
        <div style={{ height: 40, flex: "none", display: "flex", alignItems: "center", gap: 13, padding: "0 16px", borderBottom: "1px solid var(--line)" }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".12em", color: "var(--strong)" }}>CHARACTER LINKS</span>
          <span style={{ fontSize: 9, color: "var(--txt3)", letterSpacing: ".1em" }}>
            <span style={{ color: "var(--accent)" }}>{linked}</span> / {cast.length} BOUND TO BIBLE
          </span>
          <div style={{ flex: 1 }} />
          <button
            onClick={autoLink}
            disabled={busy != null || projectId == null}
            style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 9, letterSpacing: ".12em", color: busy === "auto" ? "var(--txt3)" : "var(--accent)", background: "rgba(76,194,255,.08)", border: "1px solid var(--line-cy)", padding: "4px 10px", cursor: busy != null || projectId == null ? "default" : "pointer" }}
          >
            {busy === "auto" ? "⟲ LINKING…" : "⟲ AUTO-LINK BY NAME"}
          </button>
          <input
            value={newName}
            disabled={busy != null || projectId == null}
            placeholder="new character…"
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") void createCharacter(); }}
            style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 9, letterSpacing: ".04em", color: "var(--txt)", background: "var(--raised)", border: "1px solid var(--line2)", padding: "4px 7px", width: 120 }}
          />
          <button
            onClick={createCharacter}
            disabled={busy != null || projectId == null || !newName.trim()}
            style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 9, letterSpacing: ".12em", color: busy === "create" ? "var(--txt3)" : "var(--cyan)", background: "rgba(76,194,255,.08)", border: "1px solid var(--line-cy)", padding: "4px 10px", cursor: busy != null || projectId == null || !newName.trim() ? "default" : "pointer" }}
          >
            {busy === "create" ? "＋ ADDING…" : "＋ CHARACTER"}
          </button>
        </div>

        {/* body */}
        {loading
          ? message("Loading characters…")
          : error
          ? message(`Couldn't load characters — ${error}`)
          : cast.length === 0
          ? message("No characters yet — run the extractor to build the cast")
          : (
            <div style={{ flex: 1, overflowY: "auto", padding: "10px 14px", display: "flex", flexDirection: "column", gap: 7 }}>
              {actionError && (
                <div style={{ fontSize: 10, color: "var(--blocking)", border: "1px solid rgba(255,82,96,.35)", background: "rgba(255,82,96,.06)", padding: "6px 9px" }}>{actionError}</div>
              )}
              {cast.map((c) => {
                const isLinked = c.psyke_entry_id != null;
                return (
                  <div key={c.id} style={{ display: "flex", alignItems: "center", gap: 11, padding: "8px 11px", border: `1px solid ${isLinked ? "var(--line2)" : "rgba(245,177,51,.35)"}`, background: isLinked ? "var(--tint)" : "rgba(245,177,51,.05)", opacity: busy === c.id ? 0.5 : 1 }}>
                    <span style={{ width: 9, height: 9, flex: "none", borderRadius: "50%", background: c.color || "var(--accent)" }} />
                    <span style={{ fontFamily: "'Chakra Petch'", fontSize: 12, color: "var(--strong)", letterSpacing: ".02em", minWidth: 130 }}>{c.name}</span>
                    <span style={{ fontSize: 9, letterSpacing: ".06em", color: isLinked ? "var(--green)" : "var(--amber)" }}>
                      {isLinked ? `→ ${entryName.get(c.psyke_entry_id as number) ?? "(missing entry)"}` : "⚑ unlinked"}
                    </span>
                    <div style={{ flex: 1 }} />
                    <select
                      value={isLinked ? String(c.psyke_entry_id) : ""}
                      disabled={busy != null || projectId == null}
                      onChange={(e) => setLink(c, e.target.value ? Number(e.target.value) : null)}
                      style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 11, color: "var(--txt)", background: "var(--raised)", border: "1px solid var(--line2)", padding: "4px 7px", minWidth: 200 }}
                    >
                      <option value="">— not linked —</option>
                      {charEntries.map((e) => (
                        <option key={e.id} value={String(e.id)}>{e.name}</option>
                      ))}
                    </select>
                    <button
                      onClick={() => removeCharacter(c)}
                      disabled={busy != null || projectId == null}
                      title={`Delete ${c.name}`}
                      style={{ flex: "none", fontFamily: "'JetBrains Mono',monospace", fontSize: 9, color: "var(--crimson)", background: "rgba(255,82,96,.06)", border: "1px solid rgba(255,82,96,.35)", padding: "4px 7px", cursor: busy != null || projectId == null ? "default" : "pointer" }}
                    >
                      ✕
                    </button>
                  </div>
                );
              })}
            </div>
          )}
      </div>
    </PanelShell>
  );
}
