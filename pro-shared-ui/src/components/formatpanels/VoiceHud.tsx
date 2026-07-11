import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import type {
  VoiceStatusDTO, VoiceHistoryEntryDTO, VoiceIntentDTO, VoiceBillyOperationDTO,
  VoiceCommitTargetDTO, VoiceIntentPreviewDTO, VoiceBillyProposalDTO, VoiceCtx,
} from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useStudio } from "../../adapters/StudioProvider";
import { useSelection } from "../../adapters/selection";
import { useScenes } from "../../hooks";
import { startMic, type MicRecorder } from "./mic";

/**
 * Dexter's Room — the FULL headless voice facade (VoiceRoomService) over HTTP,
 * not a transcribe-only panel. Records mic → 16 kHz PCM → the core's local
 * faster-whisper, which records each segment in the session history. From a
 * segment the writer can: run an **Intent** (cleanup), **ask / edit with
 * Billy** by voice, and **commit** to a target (the active scene, a Note, or a
 * PSYKE entry) — with **undo** for server-side commits. Editor/cursor commits
 * come back as `inserted_text`, which we append to the active scene. Audio
 * never leaves the machine; degrades gracefully when no model is set up.
 */

const panelBox: CSSProperties = {
  position: "relative", width: "100%", height: "100%",
  background: "radial-gradient(70% 80% at 50% 0%,var(--raised),var(--base))", border: "1px solid var(--line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)", overflow: "hidden", display: "flex", flexDirection: "column",
};
const ACCENT = { ["--accent"]: "#4cc2ff" } as CSSProperties;
const WAVE = ["0.9s", "0.7s", "1.1s", "0.6s", "0.85s", "0.95s", "1.2s", "0.75s", "1.05s", "0.8s", "1.15s", "0.65s"];
const HEIGHTS = [60, 85, 40, 95, 55, 75, 35, 88, 50, 70, 45, 80];

const btn: CSSProperties = { fontSize: 8.5, letterSpacing: ".05em", border: "1px solid var(--line2)", background: "transparent", color: "var(--txt2)", padding: "3px 8px", cursor: "pointer", font: "inherit" };
const sel: CSSProperties = { ...btn, color: "var(--txt2)", background: "var(--tint)" };

type Seg = VoiceHistoryEntryDTO & { committedLabel?: string };
type Work =
  | { kind: "intent"; segId: string; preview: VoiceIntentPreviewDTO }
  | { kind: "billy"; segId: string; proposal: VoiceBillyProposalDTO };

export function VoiceHud(props: PanelProps) {
  const { api, projectId } = useStudio();
  const { selection } = useSelection();
  const scenes = useScenes();

  const [status, setStatus] = useState<VoiceStatusDTO | null>(null);
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [segments, setSegments] = useState<Seg[]>([]);
  const [intents, setIntents] = useState<VoiceIntentDTO[]>([]);
  const [billyOps, setBillyOps] = useState<VoiceBillyOperationDTO[]>([]);
  const [targets, setTargets] = useState<VoiceCommitTargetDTO[]>([]);
  const [work, setWork] = useState<Work | null>(null);
  const [workBusy, setWorkBusy] = useState(false);
  const [canUndo, setCanUndo] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const recorder = useRef<MicRecorder | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const activeScene = scenes.data?.find((s) => s.id === selection.sceneId);
  const available = status?.available === true;

  const ctx = useCallback((): VoiceCtx => ({ has_active_editor: !!activeScene }), [activeScene]);

  useEffect(() => {
    let alive = true;
    api.voiceStatus().then((s) => { if (alive) setStatus(s); })
      .catch((e) => { if (alive) setStatus({ available: false, message: String(e), model_configured: false, device: "" }); });
    return () => { alive = false; };
  }, [api]);

  useEffect(() => () => { recorder.current?.cancel(); if (timer.current) clearInterval(timer.current); }, []);

  // Load the available Intents / Billy ops / commit targets once voice is up.
  const refreshActions = useCallback(async () => {
    if (projectId == null || !available) return;
    const body = { ctx: ctx() };
    try {
      const [i, b, t, u] = await Promise.all([
        api.voiceIntents(projectId, body).catch(() => ({ intents: [] })),
        api.voiceBillyOps(projectId, body).catch(() => ({ operations: [] })),
        api.voiceCommitTargets(projectId, body).catch(() => ({ targets: [] })),
        api.voiceCanUndo(projectId).catch(() => ({ can_undo: false, reason: "" })),
      ]);
      setIntents(i.intents || []);
      setBillyOps(b.operations || []);
      setTargets(t.targets || []);
      setCanUndo(!!u.can_undo);
    } catch { /* non-fatal */ }
  }, [api, projectId, available, ctx]);

  useEffect(() => { void refreshActions(); }, [refreshActions]);

  const beginRecord = useCallback(async () => {
    setErr(null); setNote(null);
    try {
      recorder.current = await startMic();
      setRecording(true); setElapsed(0);
      timer.current = setInterval(() => setElapsed((e) => e + 1), 1000);
    } catch (e) {
      setErr(e instanceof Error ? `Mic blocked — ${e.message}` : String(e));
    }
  }, []);

  const stopRecord = useCallback(async () => {
    setRecording(false);
    if (timer.current) { clearInterval(timer.current); timer.current = null; }
    const rec = recorder.current;
    recorder.current = null;
    if (!rec || projectId == null) return;
    setBusy(true);
    try {
      const audio = await rec.stop();
      if (!audio) { setBusy(false); setErr("No audio captured — is the mic muted?"); return; }
      const r = await api.voiceTranscribeSegment(projectId, { audio_base64: audio.base64, sample_rate: audio.sampleRate });
      if ("error" in r && r.error) setErr(r.error);
      else if ("empty" in r) setErr("No speech detected.");
      else if ("id" in r) setSegments((s) => [...s, r as Seg]);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [api, projectId]);

  const patchSeg = (id: string, patch: Partial<Seg>) =>
    setSegments((s) => s.map((seg) => (seg.id === id ? { ...seg, ...patch } : seg)));

  const appendToScene = useCallback(async (text: string) => {
    if (projectId == null || !activeScene) return false;
    const content = (activeScene.content ? activeScene.content + "\n\n" : "") + text;
    await api.updateScene(projectId, activeScene.id, { content });
    scenes.refetch();
    return true;
  }, [api, projectId, activeScene, scenes]);

  // --- Intent (cleanup) ----------------------------------------------------
  const runIntent = useCallback(async (seg: Seg, intent: VoiceIntentDTO) => {
    if (projectId == null) return;
    setErr(null); setWorkBusy(true);
    try {
      const preview = await api.voiceIntentPreview(projectId, {
        intent_id: intent.id, source_text: seg.text, source_segment_ids: [seg.id], ctx: ctx(),
      });
      setWork({ kind: "intent", segId: seg.id, preview });
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    finally { setWorkBusy(false); }
  }, [api, projectId, ctx]);

  const applyIntent = useCallback(async () => {
    if (projectId == null || work?.kind !== "intent") return;
    setWorkBusy(true);
    try {
      const res = await api.voiceIntentApply(projectId, { preview_id: work.preview.id, ctx: ctx() });
      if (res.applied) {
        if (res.cleaned_text) patchSeg(work.segId, { text: res.cleaned_text });
        setNote(res.message || "Cleanup applied.");
      } else setErr(res.message || "Intent could not be applied.");
      setWork(null);
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    finally { setWorkBusy(false); }
  }, [api, projectId, work, ctx]);

  // --- Billy (ask / edit by voice) -----------------------------------------
  const runBilly = useCallback(async (seg: Seg, op: VoiceBillyOperationDTO) => {
    if (projectId == null) return;
    setErr(null); setWorkBusy(true);
    try {
      const proposal = await api.voiceBillyGenerate(projectId, {
        operation: op.id, transcript_text: seg.text, source_segment_ids: [seg.id], ctx: ctx(),
      });
      setWork({ kind: "billy", segId: seg.id, proposal });
      patchSeg(seg.id, { sent_to_billy: true });
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    finally { setWorkBusy(false); }
  }, [api, projectId, ctx]);

  const applyBilly = useCallback(async () => {
    if (projectId == null || work?.kind !== "billy") return;
    setWorkBusy(true);
    try {
      const res = await api.voiceBillyApply(projectId, { proposal_id: work.proposal.id, ctx: ctx() });
      if (res.applied) {
        if (res.inserted_text) { await appendToScene(res.inserted_text); patchSeg(work.segId, { committedLabel: "→ scene (Billy)" }); }
        setNote(res.message || "Billy's edit applied.");
        void refreshActions();
      } else setErr(res.message || "Could not apply Billy's proposal.");
      setWork(null);
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    finally { setWorkBusy(false); }
  }, [api, projectId, work, ctx, appendToScene, refreshActions]);

  // --- Commit --------------------------------------------------------------
  const commit = useCallback(async (seg: Seg, target: VoiceCommitTargetDTO) => {
    if (projectId == null) return;
    setErr(null);
    try {
      const res = await api.voiceCommit(projectId, { text: seg.text, target_id: target.id, ctx: ctx() });
      if (!res.applied) { setErr(res.message || "Commit failed."); return; }
      if (res.inserted_text) await appendToScene(res.inserted_text);
      patchSeg(seg.id, { committedLabel: `→ ${target.label}` });
      setNote(res.message || `Committed ${target.label}.`);
      void refreshActions();
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
  }, [api, projectId, ctx, appendToScene, refreshActions]);

  const undo = useCallback(async () => {
    if (projectId == null) return;
    try {
      const res = await api.voiceUndo(projectId);
      setNote(res.message || (res.undone ? "Last commit undone." : "Nothing to undo."));
      scenes.refetch();
      void refreshActions();
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
  }, [api, projectId, scenes, refreshActions]);

  const cleanupIntents = intents.filter((i) => i.enabled && (i.type === "cleanup" || /clean/i.test(i.id)));
  const askOps = billyOps.filter((o) => o.enabled);
  const commitTargets = targets.filter((t) => t.enabled);

  return (
    <PanelShell {...props} style={ACCENT}>
      <div data-screen-label="Dexters Room Voice" style={panelBox}>
        <Corners />

        {/* header */}
        <div style={{ height: 40, flex: "none", display: "flex", alignItems: "center", gap: 11, padding: "0 16px", borderBottom: "1px solid var(--line)" }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".1em", color: "var(--strong)" }}>DEXTER&apos;S ROOM</span>
          <span style={{ fontSize: 8, color: "var(--txt3)", border: "1px solid var(--line2)", padding: "2px 7px", letterSpacing: ".1em" }}>LOCAL · audio never leaves device</span>
          <div style={{ flex: 1 }} />
          {canUndo && <button type="button" onClick={() => void undo()} style={{ ...btn, fontSize: 8, color: "var(--amber)", borderColor: "var(--amber)" }}>↺ UNDO LAST</button>}
          {status && (
            <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 8, color: available ? "var(--green)" : "var(--amber)" }}>
              <span style={{ width: 5, height: 5, borderRadius: "50%", background: available ? "var(--green)" : "var(--amber)" }} />
              {available ? `READY · ${status.device === "cuda" ? "GPU" : "CPU"}` : "VOICE UNAVAILABLE"}
            </span>
          )}
        </div>

        {!available && status ? (
          <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12, padding: 30, textAlign: "center" }}>
            <div style={{ fontSize: 12, color: "var(--txt2)" }}>Local voice isn&apos;t set up on this core.</div>
            <div style={{ fontSize: 10, color: "var(--txt3)", maxWidth: 380, lineHeight: 1.6 }}>{status.message || "Set LOGOSFORGE_VOICE_MODEL to a faster-whisper model directory (a sibling _cuda_runtime enables GPU), then restart."}</div>
          </div>
        ) : (
          <>
            {/* record control + waveform */}
            <div style={{ height: 108, flex: "none", display: "flex", alignItems: "center", gap: 16, padding: "0 18px", borderBottom: "1px solid var(--line2)" }}>
              <button type="button" onClick={() => (recording ? void stopRecord() : void beginRecord())} disabled={busy || !status}
                title={recording ? "Stop + transcribe" : "Start recording"}
                style={{ position: "relative", width: 56, height: 56, flex: "none", borderRadius: "50%", border: `2px solid ${recording ? "var(--blocking,#ff5260)" : "var(--cyan)"}`, background: "transparent", color: recording ? "var(--blocking,#ff5260)" : "var(--cyan)", fontSize: 10, letterSpacing: ".1em", cursor: busy ? "default" : "pointer", boxShadow: recording ? "0 0 22px rgba(255,82,96,.35) inset" : "0 0 18px rgba(76,194,255,.25) inset" }}>
                {busy ? "···" : recording ? "■" : "REC"}
              </button>
              <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 2, height: 54, opacity: recording ? 1 : 0.25 }}>
                {WAVE.map((dur, i) => (
                  <div key={i} style={{ flex: 1, height: `${HEIGHTS[i]}%`, background: "linear-gradient(180deg,var(--cyan),rgba(76,194,255,.2))", animation: recording ? `lf-bars ${dur} ease-in-out infinite` : "none" }} />
                ))}
              </div>
              <div style={{ flex: "none", textAlign: "right" }}>
                <div style={{ fontFamily: "'Chakra Petch'", fontSize: 13, color: recording ? "var(--cyan)" : "var(--txt2)" }}>{busy ? "TRANSCRIBING" : recording ? "LISTENING" : "IDLE"}</div>
                <div style={{ fontSize: 8, color: "var(--txt3)" }}>{recording ? `${elapsed}s` : "press REC to dictate"}</div>
              </div>
            </div>

            {/* context line */}
            <div style={{ flex: "none", display: "flex", alignItems: "center", gap: 9, padding: "7px 16px", borderBottom: "1px solid var(--line2)", fontSize: 8, color: "var(--txt3)", letterSpacing: ".08em" }}>
              <span>TARGET EDITOR:</span>
              <span style={{ color: activeScene ? "var(--cyan)" : "var(--amber)" }}>{activeScene ? (activeScene.title || "active scene") : "none — focus a scene in the Manuscript"}</span>
              <span style={{ marginLeft: "auto", color: "var(--txt3)" }}>{commitTargets.length} commit target{commitTargets.length === 1 ? "" : "s"} · {askOps.length} Billy op{askOps.length === 1 ? "" : "s"}</span>
            </div>

            {/* transcript + per-segment facade actions */}
            <div style={{ flex: 1, overflowY: "auto", padding: "12px 16px" }}>
              <div style={{ fontSize: 7.5, letterSpacing: ".18em", color: "var(--txt3)", marginBottom: 9 }}>TRANSCRIPT · session history</div>
              {segments.length === 0
                ? <div style={{ fontSize: 10, color: "var(--txt3)", fontStyle: "italic" }}>Nothing yet — press REC, speak, then stop. Each segment records to the session and can be cleaned, sent to Billy, or committed.</div>
                : <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {segments.map((seg) => (
                      <div key={seg.id} style={{ border: "1px solid var(--line2)", borderLeft: `2px solid ${seg.committedLabel ? "var(--green)" : "var(--cyan)"}`, background: "var(--tint)", padding: "9px 11px" }}>
                        <div style={{ fontSize: 11, color: "var(--txt)", lineHeight: 1.5 }}>{seg.text}</div>

                        {/* action bar */}
                        <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                          {seg.committedLabel && <span style={{ fontSize: 8, color: "var(--green)", marginRight: 4 }}>✓ {seg.committedLabel}</span>}

                          {cleanupIntents.map((i) => (
                            <button key={i.id} type="button" disabled={workBusy} onClick={() => void runIntent(seg, i)} style={{ ...btn, color: "var(--txt2)" }} title={i.label}>✦ {i.label.toUpperCase()}</button>
                          ))}

                          {askOps.length > 0 && (
                            <select disabled={workBusy} defaultValue="" onChange={(e) => { const op = askOps.find((o) => o.id === e.target.value); if (op) void runBilly(seg, op); e.currentTarget.value = ""; }} style={sel} title="Ask or edit with Billy by voice">
                              <option value="" disabled>◇ BILLY…</option>
                              {askOps.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
                            </select>
                          )}

                          {commitTargets.length > 0 && (
                            <select defaultValue="" onChange={(e) => { const t = commitTargets.find((x) => x.id === e.target.value); if (t) void commit(seg, t); e.currentTarget.value = ""; }} style={{ ...sel, color: "var(--cyan)", borderColor: "var(--line-cy,#2b6f8f)", marginLeft: "auto" }} title="Commit this segment">
                              <option value="" disabled>✓ COMMIT TO…</option>
                              {commitTargets.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
                            </select>
                          )}
                        </div>

                        {/* inline preview / proposal for THIS segment */}
                        {work && work.segId === seg.id && (
                          <div style={{ marginTop: 9, border: "1px solid var(--line2)", borderLeft: "2px solid var(--accent)", background: "var(--tint)", padding: "8px 10px" }}>
                            {work.kind === "intent" ? (
                              <>
                                <div style={{ fontSize: 7.5, letterSpacing: ".16em", color: "var(--txt3)", marginBottom: 5 }}>INTENT PREVIEW · {work.preview.intent_type}{work.preview.risk_level ? ` · ${work.preview.risk_level} risk` : ""}</div>
                                <div style={{ fontSize: 10.5, color: "var(--txt)", lineHeight: 1.5, whiteSpace: "pre-wrap" }}>{work.preview.after_text || work.preview.target_summary}</div>
                                {work.preview.reason_if_blocked && <div style={{ fontSize: 8.5, color: "var(--amber)", marginTop: 4 }}>{work.preview.reason_if_blocked}</div>}
                              </>
                            ) : (
                              <>
                                <div style={{ fontSize: 7.5, letterSpacing: ".16em", color: "var(--txt3)", marginBottom: 5 }}>BILLY · {work.proposal.operation}</div>
                                <div style={{ fontSize: 10.5, color: "var(--txt)", lineHeight: 1.5, whiteSpace: "pre-wrap" }}>{work.proposal.response_text || work.proposal.after_text || work.proposal.target_summary}</div>
                                {work.proposal.reason_if_blocked && <div style={{ fontSize: 8.5, color: "var(--amber)", marginTop: 4 }}>{work.proposal.reason_if_blocked}</div>}
                              </>
                            )}
                            <div style={{ display: "flex", gap: 7, marginTop: 8 }}>
                              {((work.kind === "intent" && work.preview.can_apply) || (work.kind === "billy" && work.proposal.can_apply)) && (
                                <button type="button" disabled={workBusy} onClick={() => void (work.kind === "intent" ? applyIntent() : applyBilly())} style={{ ...btn, color: "var(--on-accent)", background: "var(--cyan)", borderColor: "var(--cyan)", fontWeight: 600 }}>{workBusy ? "···" : "APPLY"}</button>
                              )}
                              <button type="button" disabled={workBusy} onClick={() => setWork(null)} style={{ ...btn }}>DISMISS</button>
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>}
              {note && <div style={{ marginTop: 10, fontSize: 9.5, color: "var(--green)" }}>✓ {note}</div>}
              {err && <div style={{ marginTop: 8, fontSize: 10, color: "var(--crimson)" }}>⚠ {err}</div>}
            </div>
          </>
        )}
      </div>
    </PanelShell>
  );
}
