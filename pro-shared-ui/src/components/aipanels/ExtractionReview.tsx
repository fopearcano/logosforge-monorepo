import { useEffect, useMemo, useState, type CSSProperties } from "react";
import type { ExtractionApplyRequestDTO, RelationProposalDTO, NearDupHintDTO } from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useExtraction } from "../../hooks";
import { useStudio } from "../../adapters/StudioProvider";

const panelBox: CSSProperties = {
  position: "relative",
  width: "100%",
  height: "100%",
  background: "linear-gradient(180deg,var(--panel2),var(--base))",
  border: "1px solid var(--line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)",
  overflow: "hidden",
  display: "flex",
  flexDirection: "column",
};

const REL_COLOR: Record<string, string> = {
  supports_setup: "var(--green)",
  payoff: "var(--green)",
  subtext_opposition: "var(--pink)",
  visual_motif: "var(--cyan)",
};

function Check({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <span
      onClick={onClick}
      style={{ width: 13, height: 13, flex: "none", cursor: "pointer", border: `1px solid ${on ? "var(--accent)" : "var(--line2)"}`, background: on ? "var(--accent)" : "transparent", display: "grid", placeItems: "center", fontSize: 9, lineHeight: 1, color: "var(--on-accent)", marginTop: 1 }}
    >
      {on ? "✓" : ""}
    </span>
  );
}

export function ExtractionReview(props: PanelProps) {
  const { api, projectId } = useStudio();
  const { propose, apply, revert, proposals, report, running, applying, reverting, error, progress } = useExtraction();
  const [useLlm, setUseLlm] = useState(true);
  const [model, setModel] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [rejected, setRejected] = useState<Set<string>>(new Set());

  // Best-effort: populate the override picker with the active provider's loaded
  // models. Stays free-text — an empty list (provider unreachable) just means no
  // suggestions, not a broken input.
  useEffect(() => {
    let cancelled = false;
    if (projectId == null) return;
    api.listExtractionModels(projectId)
      .then((r) => { if (!cancelled) setModels(r.models ?? []); })
      .catch(() => { /* no suggestions */ });
    return () => { cancelled = true; };
  }, [api, projectId]);

  const isOn = (key: string) => !rejected.has(key);
  const toggle = (key: string) =>
    setRejected((r) => {
      const n = new Set(r);
      n.has(key) ? n.delete(key) : n.add(key);
      return n;
    });

  const request = useMemo<ExtractionApplyRequestDTO>(() => {
    if (!proposals) return { scenes: [], setup_payoffs: [] };
    return {
      scenes: proposals.scenes.map((s) => ({
        scene_id: s.scene_id,
        title: s.title,
        characters: isOn(`chars:${s.scene_id}`) ? s.characters : [],
        who_knows_what: isOn(`wkw:${s.scene_id}`) ? s.who_knows_what ?? "" : "",
        relations: (s.relations ?? []).filter((_, i) => isOn(`rel:${s.scene_id}:${i}`)),
      })),
      setup_payoffs: (proposals.setup_payoffs ?? []).filter((_, i) => isOn(`sp:${i}`)),
    };
  }, [proposals, rejected]);

  const accepted = useMemo(() => {
    let n = 0;
    for (const s of request.scenes) {
      if (s.characters.length) n += 1;
      if ((s.who_knows_what ?? "").trim()) n += 1;
      n += s.relations.length;
    }
    return n + request.setup_payoffs.length;
  }, [request]);

  // Advisory near-duplicate badge: the core flags an entity that would create a NEW
  // bible entry yet closely resembles an existing one (a likely LLM typo). It's a
  // HINT only — the writer fixes the name upstream or rejects the row; nothing is
  // auto-merged here.
  const dupBadge = (label: string, h?: NearDupHintDTO | null) =>
    h ? (
      <span key={label} title={`Possible duplicate of an existing bible entry (similarity ${h.score}). Advisory only — fix the name or reject this row; nothing is auto-merged.`} style={{ color: "var(--amber)", cursor: "help" }}>
        ⚠ “{label}” ≈ “{h.existing_name}”?
      </span>
    ) : null;

  const relRow = (sceneKey: string, rel: RelationProposalDTO, i: number) => {
    const key = `rel:${sceneKey}:${i}`;
    const dupes = [dupBadge(rel.source, rel.source_hint), dupBadge(rel.target, rel.target_hint)].filter(Boolean);
    return (
      <div key={key} style={{ display: "flex", alignItems: "flex-start", gap: 8, fontSize: 10, color: isOn(key) ? "var(--txt2)" : "var(--txt3)", opacity: isOn(key) ? 1 : 0.5 }}>
        <Check on={isOn(key)} onClick={() => toggle(key)} />
        <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
          <span><span style={{ color: "var(--strong)" }}>{rel.source}</span> <span style={{ color: REL_COLOR[rel.rel_type] ?? "var(--txt3)" }}>{rel.rel_type}</span> <span style={{ color: "var(--strong)" }}>{rel.target}</span>{rel.why ? <span style={{ color: "var(--txt3)" }}> · {rel.why}</span> : null}</span>
          {dupes.length > 0 && <span style={{ fontSize: 8.5, display: "flex", gap: 8, flexWrap: "wrap" }}>{dupes}</span>}
        </div>
      </div>
    );
  };

  return (
    <PanelShell {...props} style={{ ["--accent"]: "#b07cff" } as CSSProperties}>
      <div data-screen-label="Extraction Review" style={panelBox}>
        <Corners />

        {/* header */}
        <div style={{ height: 42, flex: "none", display: "flex", alignItems: "center", gap: 11, padding: "0 16px", borderBottom: "1px solid var(--line)" }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".1em", color: "var(--strong)" }}>EXTRACT STRUCTURE</span>
          <div style={{ display: "flex", border: "1px solid var(--line2)", fontSize: 8, letterSpacing: ".08em" }}>
            <span onClick={() => setUseLlm(false)} style={{ padding: "4px 8px", cursor: "pointer", color: useLlm ? "var(--txt3)" : "var(--on-accent)", background: useLlm ? undefined : "var(--accent)", fontWeight: useLlm ? 400 : 600 }}>TIER 1 ONLY</span>
            <span onClick={() => setUseLlm(true)} style={{ padding: "4px 8px", cursor: "pointer", borderLeft: "1px solid var(--line2)", color: useLlm ? "var(--on-accent)" : "var(--txt3)", background: useLlm ? "var(--accent)" : undefined, fontWeight: useLlm ? 600 : 400 }}>+ AI INFERENCE</span>
          </div>
          {useLlm && (
            <>
              <input
                value={model}
                onChange={(e) => setModel(e.target.value)}
                list="extract-model-list"
                placeholder={models.length ? "model override (blank = default)" : "model override (free-text)"}
                spellCheck={false}
                title="Optional: run AI inference with a specific (e.g. stronger) model — kept on the active provider's endpoint. Pick a loaded model or type any name."
                style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 9, color: "var(--txt2)", background: "var(--raised)", border: "1px solid var(--line2)", padding: "4px 7px", width: 230, outline: "none" }}
              />
              <datalist id="extract-model-list">
                {models.map((m) => <option key={m} value={m} />)}
              </datalist>
            </>
          )}
          <div style={{ flex: 1 }} />
          <span
            onClick={running ? undefined : () => { setRejected(new Set()); propose(useLlm, model.trim() || undefined); }}
            style={{ fontSize: 9.5, color: "var(--on-accent)", background: running ? "var(--line2)" : "var(--accent)", padding: "6px 13px", fontWeight: 600, letterSpacing: ".08em", cursor: running ? "default" : "pointer", boxShadow: running ? undefined : "0 0 14px rgba(176,124,255,.35)" }}
          >
            {running ? "EXTRACTING…" : "⟳ EXTRACT FROM MANUSCRIPT"}
          </span>
        </div>

        {/* body */}
        <div style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: 14 }}>
          {running ? (
            <div style={{ padding: "10px 2px" }}>
              <div style={{ color: "var(--accent)", fontSize: 12, marginBottom: 10 }}>
                Reading the manuscript… {progress ? `scene ${progress.done} / ${progress.total}` : "starting job…"}
              </div>
              <div style={{ height: 6, background: "var(--tint2)", overflow: "hidden" }}>
                <div style={{ width: progress && progress.total ? `${Math.round((progress.done / progress.total) * 100)}%` : "6%", height: "100%", background: "var(--accent)", transition: "width .3s" }} />
              </div>
              <div style={{ fontSize: 8.5, color: "var(--txt3)", marginTop: 7 }}>Runs as a background job — Tier-1 cues are instant; AI inference runs per scene. You can keep working.</div>
            </div>
          ) : error ? (
            <div style={{ color: "var(--blocking)", fontSize: 11.5, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>Extraction failed.{"\n"}<span style={{ color: "var(--txt3)", fontSize: 10 }}>{error}</span></div>
          ) : !proposals ? (
            <div style={{ color: "var(--txt3)", fontSize: 11.5, lineHeight: 1.6, maxWidth: 560 }}>
              Turn your authored scenes into structured story-data — scene↔character links, who-knows-what, and typed PSYKE relations (setup/payoff, subtext, motifs). <span style={{ color: "var(--accent)" }}>Extract</span> proposes; nothing is written until you review and apply.
            </div>
          ) : (
            <>
              <div style={{ fontSize: 8, letterSpacing: ".16em", color: "var(--txt3)", marginBottom: 10 }}>
                {proposals.scenes.length} SCENES · {proposals.used_llm ? "TIER 1 + AI" : "TIER 1 ONLY"} · review then apply
              </div>
              {proposals.scenes.map((s) => {
                const charKey = `chars:${s.scene_id}`;
                const wkwKey = `wkw:${s.scene_id}`;
                const hasAny = s.characters.length || (s.who_knows_what ?? "").trim() || (s.relations ?? []).length;
                if (!hasAny) return null;
                return (
                  <div key={s.scene_id} style={{ border: "1px solid var(--line2)", background: "var(--tint)", padding: "9px 11px", marginBottom: 8 }}>
                    <div style={{ fontFamily: "'Chakra Petch'", fontSize: 11, color: "var(--strong)", letterSpacing: ".04em", marginBottom: 7 }}>{s.title || `Scene ${s.scene_id}`}</div>
                    {s.characters.length > 0 && (
                      <div style={{ display: "flex", alignItems: "flex-start", gap: 8, marginBottom: 6 }}>
                        <Check on={isOn(charKey)} onClick={() => toggle(charKey)} />
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 5, opacity: isOn(charKey) ? 1 : 0.5 }}>
                          <span style={{ fontSize: 8, color: "var(--txt3)", letterSpacing: ".1em", alignSelf: "center" }}>CAST</span>
                          {s.characters.map((c) => (
                            <span key={c} style={{ fontSize: 8.5, color: "var(--cyan)", border: "1px solid var(--line2)", padding: "1px 6px" }}>{c}</span>
                          ))}
                        </div>
                      </div>
                    )}
                    {(s.who_knows_what ?? "").trim() && (
                      <div style={{ display: "flex", alignItems: "flex-start", gap: 8, marginBottom: 6, opacity: isOn(wkwKey) ? 1 : 0.5 }}>
                        <Check on={isOn(wkwKey)} onClick={() => toggle(wkwKey)} />
                        <span style={{ fontSize: 10, color: "var(--txt2)", lineHeight: 1.45 }}><span style={{ fontSize: 8, color: "var(--amber)", letterSpacing: ".1em" }}>KNOWS </span>{s.who_knows_what}</span>
                      </div>
                    )}
                    {(s.relations ?? []).length > 0 && (
                      <div style={{ display: "flex", flexDirection: "column", gap: 5, marginTop: 2 }}>
                        {(s.relations ?? []).map((r, i) => relRow(String(s.scene_id), r, i))}
                      </div>
                    )}
                  </div>
                );
              })}
              {(proposals.setup_payoffs ?? []).length > 0 && (
                <div style={{ border: "1px solid rgba(98,217,154,.3)", background: "rgba(11,18,12,.4)", padding: "9px 11px", marginBottom: 8 }}>
                  <div style={{ fontSize: 8, letterSpacing: ".16em", color: "var(--green)", marginBottom: 7 }}>CROSS-SCENE SETUP / PAYOFF</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                    {(proposals.setup_payoffs ?? []).map((r, i) => relRow("sp", r, i))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* apply footer */}
        <div style={{ flex: "none", minHeight: 34, display: "flex", alignItems: "center", gap: 12, padding: "0 16px", borderTop: "1px solid var(--line2)", background: "var(--tint2)" }}>
          {report ? (
            <span style={{ fontSize: 9.5, color: "var(--green)", letterSpacing: ".04em" }}>
              ✓ APPLIED · {report.characters_created} chars · {report.links_added} links · {report.who_knows_what_set} knows · {report.relations_added} relations {report.psyke_created ? `· ${report.psyke_created} PSYKE` : ""}
            </span>
          ) : (
            <span style={{ fontSize: 8.5, color: "var(--txt3)", letterSpacing: ".06em" }}>
              {proposals ? `${accepted} item${accepted === 1 ? "" : "s"} accepted — uncheck anything you don't want` : "nothing written until you apply"}
            </span>
          )}
          <div style={{ flex: 1 }} />
          {report?.receipt ? (
            <span
              onClick={reverting ? undefined : () => revert()}
              title="Undo this apply — removes exactly what was written"
              style={{ fontSize: 9.5, color: reverting ? "var(--txt3)" : "var(--amber)", border: "1px solid rgba(245,177,51,.4)", padding: "5px 12px", letterSpacing: ".08em", cursor: reverting ? "default" : "pointer" }}
            >
              {reverting ? "REVERTING…" : "↶ REVERT THIS APPLY"}
            </span>
          ) : proposals ? (
            <span
              onClick={applying || accepted === 0 ? undefined : () => apply(request)}
              style={{ fontSize: 9.5, color: "var(--on-accent)", background: applying || accepted === 0 ? "var(--line2)" : "var(--green)", padding: "6px 13px", fontWeight: 600, letterSpacing: ".08em", cursor: applying || accepted === 0 ? "default" : "pointer" }}
            >
              {applying ? "APPLYING…" : `APPLY ${accepted} ACCEPTED ▸`}
            </span>
          ) : null}
        </div>
      </div>
    </PanelShell>
  );
}
