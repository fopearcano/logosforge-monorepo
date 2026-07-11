import { useEffect, useState, type CSSProperties } from "react";
import type { AssistantSettingsDTO } from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useStudio } from "../../adapters/StudioProvider";

/**
 * AI Settings — point Billy / Logos / Counterpart / Dexter-Billy at the model
 * provider of your choice (LM Studio on localhost or a LAN box, Ollama, an
 * OpenAI-compatible endpoint, or Anthropic). Reads/writes the core's
 * ``/assistant/settings`` (provider, model, base_url, api_key [write-only],
 * timeout) so a writer never has to configure the model outside the app.
 */

const panelBox: CSSProperties = {
  position: "relative", width: "100%", height: "100%",
  background: "linear-gradient(180deg,var(--panel),var(--base))", border: "1px solid var(--line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)", overflow: "hidden", display: "flex", flexDirection: "column",
};
const headCss: CSSProperties = { flex: "none", height: 40, display: "flex", alignItems: "center", gap: 10, padding: "0 16px", borderBottom: "1px solid var(--line)" };
const titleCss: CSSProperties = { fontFamily: "'Chakra Petch',sans-serif", fontWeight: 600, fontSize: 12.5, letterSpacing: ".14em", color: "var(--strong)" };
const label: CSSProperties = { fontSize: 8.5, letterSpacing: ".16em", color: "var(--txt3)", textTransform: "uppercase", marginBottom: 5 };
const input: CSSProperties = {
  width: "100%", boxSizing: "border-box", background: "var(--tint)", border: "1px solid var(--line2)",
  color: "var(--txt)", font: "inherit", fontSize: 12, padding: "8px 10px", outline: "none",
};
const field = { marginBottom: 15 } as CSSProperties;

const PROVIDERS = ["LM Studio", "Ollama", "OpenAI", "Anthropic", "OpenRouter", "Custom"];
const PRESETS: Record<string, string> = {
  "LM Studio": "http://localhost:1234/v1",
  "Ollama": "http://localhost:11434/v1",
  "OpenAI": "https://api.openai.com/v1",
  "Anthropic": "https://api.anthropic.com",
  // OpenRouter is OpenAI-compatible — the core routes it through the OpenAI path
  // (chat/completions + Bearer key). Models are namespaced, e.g. anthropic/claude-opus-4-8.
  "OpenRouter": "https://openrouter.ai/api/v1",
};

export function AiSettingsPanel(props: PanelProps) {
  const { api, projectId } = useStudio();
  const [s, setS] = useState<AssistantSettingsDTO | null>(null);
  const [apiKey, setApiKey] = useState("");            // write-only; blank = unchanged
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (projectId == null) return;
    let alive = true;
    api.getAssistantSettings(projectId)
      .then((v) => { if (alive) setS(v); })
      .catch((e) => { if (alive) setErr(String(e)); });
    return () => { alive = false; };
  }, [api, projectId]);

  const set = (patch: Partial<AssistantSettingsDTO>) => setS((cur) => (cur ? { ...cur, ...patch } : cur));

  const save = async () => {
    if (projectId == null || !s) return;
    setBusy(true); setErr(null); setNote(null);
    try {
      const body: AssistantSettingsDTO = {
        provider: s.provider, model: s.model, base_url: s.base_url, timeout: s.timeout,
        ...(apiKey ? { api_key: apiKey } : {}),
      };
      const saved = await api.patchAssistantSettings(projectId, body);
      setS(saved); setApiKey("");
      setNote("Saved. Billy, Logos, Counterpart and voice-Billy now use this model.");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <PanelShell {...props}>
      <div data-screen-label="AI Settings" style={panelBox}>
        <Corners />
        <div style={headCss}>
          <span style={{ width: 6, height: 6, background: "var(--accent)", boxShadow: "0 0 6px var(--accent)" }} />
          <span style={titleCss}>AI SETTINGS</span>
          <span style={{ fontSize: 8, color: "var(--txt3)", letterSpacing: ".1em", marginLeft: "auto" }}>drives Billy · Logos · Counterpart · Dexter</span>
        </div>

        <div style={{ flex: 1, overflowY: "auto", padding: "18px 18px 8px" }}>
          {projectId == null ? <div style={{ color: "var(--txt3)", fontSize: 11 }}>Open a project.</div>
            : !s ? <div style={{ color: "var(--txt3)", fontSize: 11 }}>Loading…</div>
            : (
              <div style={{ maxWidth: 460 }}>
                <div style={field}>
                  <div style={label}>Provider</div>
                  <select value={PROVIDERS.includes(s.provider) ? s.provider : "Custom"}
                    onChange={(e) => { const v = e.target.value; set({ provider: v, base_url: PRESETS[v] ?? s.base_url }); }}
                    style={input}>
                    {PROVIDERS.map((p) => <option key={p} value={p}>{p}</option>)}
                  </select>
                </div>

                <div style={field}>
                  <div style={label}>Base URL</div>
                  <input style={input} value={s.base_url} placeholder="http://192.168.1.141:1234/v1"
                    onChange={(e) => set({ base_url: e.target.value })} />
                  <div style={{ fontSize: 8.5, color: "var(--txt3)", marginTop: 4 }}>
                    A LAN LM Studio looks like <code>http://192.168.1.141:1234/v1</code>. Local is <code>http://localhost:1234/v1</code>.
                  </div>
                </div>

                <div style={field}>
                  <div style={label}>Model</div>
                  <input style={input} value={s.model}
                    placeholder={s.provider === "OpenRouter" ? "anthropic/claude-opus-4-8" : "llama-3.2-3b-instruct"}
                    onChange={(e) => set({ model: e.target.value })} />
                  {s.provider === "OpenRouter" && (
                    <div style={{ fontSize: 8.5, color: "var(--txt3)", marginTop: 4 }}>
                      OpenRouter models are namespaced — e.g. <code>anthropic/claude-opus-4-8</code>, <code>openai/gpt-4o</code>, <code>openrouter/auto</code>. Paste your <code>sk-or-…</code> key below.
                    </div>
                  )}
                </div>

                <div style={field}>
                  <div style={label}>API key <span style={{ textTransform: "none", letterSpacing: 0 }}>(only for hosted providers — leave blank to keep the current key)</span></div>
                  <input style={input} type="password" value={apiKey} placeholder="•••• (unchanged)"
                    autoComplete="off" onChange={(e) => setApiKey(e.target.value)} />
                </div>

                <div style={field}>
                  <div style={label}>Timeout (seconds, 0 = default)</div>
                  <input style={input} type="number" min={0} value={s.timeout}
                    onChange={(e) => set({ timeout: Number(e.target.value) || 0 })} />
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 4 }}>
                  <button type="button" onClick={() => void save()} disabled={busy}
                    style={{ fontSize: 10, letterSpacing: ".1em", fontWeight: 600, color: "var(--on-accent)", background: "var(--accent)", border: "1px solid var(--accent)", padding: "8px 18px", cursor: busy ? "default" : "pointer" }}>
                    {busy ? "SAVING…" : "SAVE"}
                  </button>
                  {note && <span style={{ fontSize: 9.5, color: "var(--green)" }}>✓ {note}</span>}
                  {err && <span style={{ fontSize: 9.5, color: "var(--crimson)" }}>⚠ {err}</span>}
                </div>
              </div>
            )}
        </div>
      </div>
    </PanelShell>
  );
}
