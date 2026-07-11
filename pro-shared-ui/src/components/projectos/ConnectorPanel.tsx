import { useEffect, useMemo, useState, type CSSProperties } from "react";
import type { ConnectorActionDTO, ConnectorResultDTO } from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useStudio } from "../../adapters/StudioProvider";

/**
 * Connector — the core's safe action layer (`/connector/actions` + `/execute`),
 * the same catalog Billy and Logos drive internally. Lists every action, groups
 * reads vs writes, and lets a writer run one directly with a params form. Writes
 * mutate the project, so they're clearly marked and run only on an explicit click.
 */

const panelBox: CSSProperties = {
  position: "relative", width: "100%", height: "100%",
  background: "linear-gradient(180deg,var(--panel),var(--base))", border: "1px solid var(--line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)", overflow: "hidden", display: "flex",
};
const titleCss: CSSProperties = { fontFamily: "'Chakra Petch',sans-serif", fontWeight: 600, fontSize: 12.5, letterSpacing: ".14em", color: "var(--strong)" };
const label: CSSProperties = { fontSize: 8, letterSpacing: ".16em", color: "var(--txt3)", textTransform: "uppercase", marginBottom: 4 };
const input: CSSProperties = { width: "100%", boxSizing: "border-box", background: "var(--tint)", border: "1px solid var(--line2)", color: "var(--txt)", font: "inherit", fontSize: 12, padding: "7px 9px", outline: "none" };

/** A write action mutates project data; a read just returns info. */
const isWrite = (a: ConnectorActionDTO) =>
  /^(create|add|update|set|delete|remove|link|unlink|apply|commit|pin|assign|move|reorder|rename)/i.test(a.name)
  || /write|mutat/i.test(a.category);

export function ConnectorPanel(props: PanelProps) {
  const { api, projectId } = useStudio();
  const [actions, setActions] = useState<ConnectorActionDTO[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [selName, setSelName] = useState<string | null>(null);
  const [args, setArgs] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ConnectorResultDTO | null>(null);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    if (projectId == null) return;
    let alive = true;
    api.listConnectorActions(projectId)
      .then((a) => { if (alive) setActions(a); })
      .catch((e) => { if (alive) setErr(String(e)); });
    return () => { alive = false; };
  }, [api, projectId]);

  const selected = useMemo(() => actions?.find((a) => a.name === selName) ?? null, [actions, selName]);

  const pick = (a: ConnectorActionDTO) => {
    setSelName(a.name);
    setResult(null); setErr(null); setConfirming(false);
    const seed: Record<string, string> = {};
    for (const p of a.params) seed[p.name] = p.default == null ? "" : String(p.default);
    setArgs(seed);
  };

  const run = async () => {
    if (projectId == null || !selected) return;
    setBusy(true); setErr(null); setResult(null); setConfirming(false);
    try {
      // Coerce param values to their declared types.
      const coerced: Record<string, unknown> = {};
      for (const p of selected.params) {
        const raw = args[p.name] ?? "";
        if (raw === "" && !p.required) continue;
        if (/int|float|number/i.test(p.param_type)) coerced[p.name] = Number(raw);
        else if (/bool/i.test(p.param_type)) coerced[p.name] = raw === "true" || raw === "1";
        else coerced[p.name] = raw;
      }
      setResult(await api.connectorExecute(projectId, { action: selected.name, args: coerced }));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const groups = useMemo(() => {
    const g: Record<string, ConnectorActionDTO[]> = {};
    for (const a of actions ?? []) (g[a.category || "general"] ??= []).push(a);
    return Object.entries(g).sort(([a], [b]) => a.localeCompare(b));
  }, [actions]);

  const write = selected ? isWrite(selected) : false;

  return (
    <PanelShell {...props}>
      <div data-screen-label="Connector" style={panelBox}>
        <Corners />
        {/* action catalog */}
        <div style={{ width: 300, flex: "none", borderRight: "1px solid var(--line)", background: "var(--panel2)", display: "flex", flexDirection: "column" }}>
          <div style={{ height: 40, display: "flex", alignItems: "center", gap: 10, padding: "0 14px", borderBottom: "1px solid var(--line2)" }}>
            <span style={{ width: 6, height: 6, background: "var(--accent)", boxShadow: "0 0 6px var(--accent)" }} />
            <span style={titleCss}>CONNECTOR</span>
            {actions && <span style={{ fontSize: 9, color: "var(--txt3)", marginLeft: "auto" }}>{actions.length}</span>}
          </div>
          <div style={{ flex: 1, overflowY: "auto", padding: "8px 8px 16px" }}>
            {projectId == null ? <div style={{ padding: 20, fontSize: 11, color: "var(--txt3)" }}>Open a project.</div>
              : err && !actions ? <div style={{ padding: 20, fontSize: 11, color: "var(--crimson)" }}>{err}</div>
              : !actions ? <div style={{ padding: 20, fontSize: 11, color: "var(--txt3)" }}>Loading…</div>
              : groups.map(([cat, list]) => (
                  <div key={cat} style={{ marginBottom: 10 }}>
                    <div style={{ fontSize: 7.5, letterSpacing: ".2em", color: "var(--txt3)", padding: "6px 6px 5px" }}>{cat.toUpperCase()}</div>
                    {list.map((a) => (
                      <div key={a.name} className={selName === a.name ? undefined : "lf-row"} onClick={() => pick(a)}
                        style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 8px", cursor: "pointer", background: selName === a.name ? "rgba(76,194,255,.1)" : undefined }}>
                        <span style={{ fontSize: 7, letterSpacing: ".1em", color: isWrite(a) ? "var(--amber)" : "var(--green)", border: `1px solid ${isWrite(a) ? "var(--amber)" : "var(--green)"}`, padding: "1px 4px", flex: "none" }}>{isWrite(a) ? "W" : "R"}</span>
                        <span style={{ flex: 1, minWidth: 0, fontSize: 10.5, color: selName === a.name ? "var(--strong)" : "var(--txt)", fontFamily: "'Courier Prime',monospace", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{a.name}</span>
                      </div>
                    ))}
                  </div>
                ))}
          </div>
        </div>

        {/* run pane */}
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
          {!selected ? (
            <div style={{ flex: 1, display: "grid", placeItems: "center", fontSize: 11, color: "var(--txt3)" }}>Select an action to run it.</div>
          ) : (
            <div style={{ flex: 1, overflowY: "auto", padding: "20px 22px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
                <span style={{ fontFamily: "'Chakra Petch'", fontSize: 16, color: "var(--strong)" }}>{selected.name}</span>
                <span style={{ fontSize: 8, letterSpacing: ".14em", color: write ? "var(--amber)" : "var(--green)", border: `1px solid ${write ? "var(--amber)" : "var(--green)"}`, padding: "2px 7px" }}>{write ? "WRITE · mutates project" : "READ"}</span>
              </div>
              {selected.description && <div style={{ fontSize: 11, color: "var(--txt2)", lineHeight: 1.5, marginBottom: 16 }}>{selected.description}</div>}

              {selected.params.length > 0 && (
                <div style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 480, marginBottom: 16 }}>
                  {selected.params.map((p) => (
                    <div key={p.name}>
                      <div style={label}>{p.name} <span style={{ textTransform: "none", letterSpacing: 0, color: "var(--txt3)" }}>· {p.param_type}{p.required ? " · required" : ""}</span></div>
                      <input style={input} value={args[p.name] ?? ""} placeholder={p.default == null ? "" : String(p.default)}
                        onChange={(e) => setArgs((s) => ({ ...s, [p.name]: e.target.value }))} />
                    </div>
                  ))}
                </div>
              )}

              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                {write && !confirming ? (
                  <button type="button" onClick={() => setConfirming(true)} disabled={busy}
                    style={{ fontSize: 10, letterSpacing: ".1em", fontWeight: 600, color: "var(--on-accent)", background: "var(--amber)", border: "1px solid var(--amber)", padding: "8px 18px", cursor: "pointer" }}>RUN…</button>
                ) : (
                  <button type="button" onClick={() => void run()} disabled={busy}
                    style={{ fontSize: 10, letterSpacing: ".1em", fontWeight: 600, color: "var(--on-accent)", background: write ? "var(--amber)" : "var(--accent)", border: "none", padding: "8px 18px", cursor: busy ? "default" : "pointer" }}>
                    {busy ? "RUNNING…" : write ? "CONFIRM RUN" : "RUN"}
                  </button>
                )}
                {confirming && !busy && <button type="button" onClick={() => setConfirming(false)} style={{ fontSize: 10, letterSpacing: ".1em", color: "var(--txt2)", background: "transparent", border: "1px solid var(--line2)", padding: "8px 14px", cursor: "pointer" }}>CANCEL</button>}
                {write && <span style={{ fontSize: 8.5, color: "var(--amber)" }}>this writes to the project</span>}
              </div>

              {err && <div style={{ marginTop: 14, fontSize: 10.5, color: "var(--crimson)" }}>⚠ {err}</div>}
              {result && (
                <div style={{ marginTop: 16, border: "1px solid var(--line2)", borderLeft: `2px solid ${result.ok ? "var(--green)" : "var(--crimson)"}`, background: "var(--tint)", padding: "10px 12px" }}>
                  <div style={{ fontSize: 8, letterSpacing: ".16em", color: result.ok ? "var(--green)" : "var(--crimson)", marginBottom: 6 }}>{result.ok ? "✓ OK" : "✕ FAILED"}{result.error ? ` · ${result.error}` : ""}</div>
                  <pre style={{ margin: 0, fontSize: 10.5, color: "var(--txt)", fontFamily: "'Courier Prime',monospace", whiteSpace: "pre-wrap", wordBreak: "break-word", maxHeight: 260, overflow: "auto" }}>{JSON.stringify(result.result, null, 2)}</pre>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </PanelShell>
  );
}
