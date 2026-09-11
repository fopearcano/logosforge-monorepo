import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import type {
  VoiceStatusDTO, VoiceHistoryEntryDTO, VoiceIntentDTO, VoiceBillyOperationDTO,
  VoiceCommitTargetDTO, VoiceIntentPreviewDTO, VoiceBillyProposalDTO, VoiceCtx,
} from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useStudio } from "../../adapters/StudioProvider";
import { useSelection } from "../../adapters/selection";
import { useScenes } from "../../hooks";
import { flushPendingProjectSaves, markProjectSavePending, registerProjectFlusher, trackProjectWrite } from "../../adapters/projectSaveCoordinator";
import { startMic, type MicRecorder } from "./mic";
import { createLatestRequestGate, type RequestToken } from "../../hooks/latestRequest";

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
type PendingInsert = {
  projectId: number;
  sceneId: number;
  segId: string;
  label: string;
  text: string;
  message: string;
};

export function VoiceHud(props: PanelProps) {
  const { api, projectId } = useStudio();
  const projectIdRef = useRef(projectId);
  projectIdRef.current = projectId;
  const requests = useRef(createLatestRequestGate()).current;
  useEffect(() => { requests.open(); return () => requests.close(); }, [requests]);
  const { selection } = useSelection();
  const scenes = useScenes();

  const [status, setStatus] = useState<VoiceStatusDTO | null>(null);
  const [micStarting, setMicStarting] = useState(false);
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [segments, setSegments] = useState<Seg[]>([]);
  const [intents, setIntents] = useState<VoiceIntentDTO[]>([]);
  const [billyOps, setBillyOps] = useState<VoiceBillyOperationDTO[]>([]);
  const [targets, setTargets] = useState<VoiceCommitTargetDTO[]>([]);
  const [work, setWork] = useState<Work | null>(null);
  const [pendingInsert, setPendingInsert] = useState<PendingInsert | null>(null);
  const [workBusy, setWorkBusy] = useState(false);
  const [canUndo, setCanUndo] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const recorder = useRef<MicRecorder | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const recordingRef = useRef(recording);
  recordingRef.current = recording;
  const busyRef = useRef(busy);
  busyRef.current = busy;
  const workRef = useRef(work);
  workRef.current = work;
  const pendingInsertRef = useRef(pendingInsert);
  pendingInsertRef.current = pendingInsert;
  const workBusyRef = useRef(workBusy);
  workBusyRef.current = workBusy;
  const micStartRef = useRef<Promise<MicRecorder> | null>(null);
  const transcribeRef = useRef<Promise<void> | null>(null);
  const actionRef = useRef<Promise<void> | null>(null);
  const [loadErrors, setLoadErrors] = useState<Record<string, string>>({});
  const setLoadError = useCallback((key: string, error: unknown | null) => setLoadErrors((current) => {
    const next = { ...current };
    if (error == null) delete next[key];
    else next[key] = error instanceof Error ? error.message : String(error);
    return next;
  }), []);

  const activeScene = scenes.data?.find((s) => s.id === selection.sceneId);
  const available = status?.available === true;

  const ctx = useCallback((): VoiceCtx => ({ has_active_editor: !!activeScene }), [activeScene]);
  const isOwned = useCallback((ownerProjectId: number, token: RequestToken) =>
    projectIdRef.current === ownerProjectId && requests.isCurrent(token), [requests]);

  const stopTimer = useCallback(() => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
  }, []);

  useEffect(() => {
    const token = requests.begin("status");
    setStatus(null);
    void api.voiceStatus().then((value) => { if (requests.isCurrent(token)) setStatus(value); })
      .catch((error) => { if (requests.isCurrent(token)) setStatus({ available: false, message: String(error), model_configured: false, device: "" }); });
    return () => requests.invalidate("status");
  }, [api, requests]);

  const voiceFlusher = useCallback(async () => {
    if (micStartRef.current) throw new Error("The microphone is starting. Wait, then stop or cancel recording before leaving Dexter's Room.");
    if (recordingRef.current) throw new Error("Stop the active recording before leaving Dexter's Room.");
    if (transcribeRef.current) await transcribeRef.current;
    if (actionRef.current) await actionRef.current;
    if (workRef.current) throw new Error("Apply or dismiss the pending Voice preview before leaving Dexter's Room.");
    if (pendingInsertRef.current) throw new Error("Retry or discard the pending Voice scene insertion before leaving Dexter's Room.");
    return true;
  }, []);

  useEffect(() => registerProjectFlusher(voiceFlusher), [voiceFlusher]);

  useEffect(() => () => {
    requests.invalidate("mic"); requests.invalidate("transcribe"); requests.invalidate("actions"); requests.invalidate("history"); requests.invalidate("work");
    recorder.current?.cancel();
    stopTimer();
  }, [requests, stopTimer]);

  useEffect(() => {
    requests.invalidate("actions"); requests.invalidate("history"); requests.invalidate("work"); requests.invalidate("mic"); requests.invalidate("transcribe");
    recorder.current?.cancel(); recorder.current = null;
    stopTimer();
    recordingRef.current = false; busyRef.current = false; workBusyRef.current = false; workRef.current = null; pendingInsertRef.current = null;
    micStartRef.current = null; transcribeRef.current = null; actionRef.current = null;
    setMicStarting(false); setRecording(false); setBusy(false); setElapsed(0); setSegments([]);
    setIntents([]); setBillyOps([]); setTargets([]); setCanUndo(false);
    setWork(null); setPendingInsert(null); setWorkBusy(false); setErr(null); setNote(null); setLoadErrors({});
  }, [api, projectId, requests, stopTimer]);

  // Load available actions as one context snapshot; history is independent so
  // a transient capability failure never hides already-recorded transcripts.
  const refreshActions = useCallback(async () => {
    if (projectId == null || !available) {
      setIntents([]); setBillyOps([]); setTargets([]); setCanUndo(false);
      return;
    }
    const token = requests.begin("actions");
    const body = { ctx: ctx() };
    try {
      const [i, b, t, u] = await Promise.all([
        api.voiceIntents(projectId, body),
        api.voiceBillyOps(projectId, body),
        api.voiceCommitTargets(projectId, body),
        api.voiceCanUndo(projectId),
      ]);
      if (!requests.isCurrent(token)) return;
      setIntents(i.intents || []);
      setBillyOps(b.operations || []);
      setTargets(t.targets || []);
      setCanUndo(!!u.can_undo);
      setLoadError("actions", null);
    } catch (error) {
      if (requests.isCurrent(token)) setLoadError("actions", error);
    }
  }, [api, projectId, available, ctx, requests, setLoadError]);

  const refreshHistory = useCallback(async () => {
    if (projectId == null || !available) { setSegments([]); return; }
    const token = requests.begin("history");
    try {
      const value = await api.voiceHistory(projectId);
      if (!requests.isCurrent(token)) return;
      setSegments((value.entries || []).map((entry) => ({ ...entry })));
      setLoadError("history", null);
    } catch (error) {
      if (requests.isCurrent(token)) setLoadError("history", error);
    }
  }, [api, projectId, available, requests, setLoadError]);

  useEffect(() => {
    void refreshActions();
    return () => requests.invalidate("actions");
  }, [refreshActions, requests]);
  useEffect(() => {
    void refreshHistory();
    return () => requests.invalidate("history");
  }, [refreshHistory, requests]);

  const beginRecord = useCallback(async () => {
    const ownerProjectId = projectIdRef.current;
    if (ownerProjectId == null || !available || micStartRef.current || recorder.current
      || recordingRef.current || busyRef.current || transcribeRef.current || actionRef.current) return;
    if (workRef.current || pendingInsertRef.current) {
      setErr("Resolve the pending Voice preview or scene insertion before recording again.");
      return;
    }
    const token = requests.begin("mic");
    setErr(null); setNote(null); setMicStarting(true);
    markProjectSavePending();
    const starting = startMic();
    micStartRef.current = starting;
    try {
      const rec = await starting;
      if (!isOwned(ownerProjectId, token)) {
        rec.cancel();
        return;
      }
      recorder.current = rec;
      recordingRef.current = true;
      setRecording(true); setElapsed(0);
      stopTimer();
      timer.current = setInterval(() => setElapsed((e) => e + 1), 1000);
    } catch (error) {
      if (isOwned(ownerProjectId, token)) {
        setErr(error instanceof Error ? `Mic blocked — ${error.message}` : String(error));
      }
    } finally {
      if (micStartRef.current === starting) micStartRef.current = null;
      if (isOwned(ownerProjectId, token)) setMicStarting(false);
      markProjectSavePending();
    }
  }, [available, isOwned, requests, stopTimer]);

  const stopRecord = useCallback((): Promise<void> | undefined => {
    const ownerProjectId = projectIdRef.current;
    if (transcribeRef.current || busyRef.current) return transcribeRef.current ?? undefined;
    const rec = recorder.current;
    recorder.current = null;
    recordingRef.current = false;
    setRecording(false);
    stopTimer();
    if (!rec || ownerProjectId == null) return undefined;

    const token = requests.begin("transcribe");
    busyRef.current = true;
    setBusy(true); setErr(null); setNote(null);
    markProjectSavePending();
    let operation!: Promise<void>;
    operation = (async () => {
      try {
        const audio = await rec.stop();
        if (!isOwned(ownerProjectId, token)) return;
        if (!audio) {
          setErr("No audio captured — is the mic muted?");
          return;
        }
        const result = await api.voiceTranscribeSegment(ownerProjectId, {
          audio_base64: audio.base64,
          sample_rate: audio.sampleRate,
        });
        if (!isOwned(ownerProjectId, token)) return;
        if ("error" in result && result.error) setErr(result.error);
        else if ("empty" in result) setErr("No speech detected.");
        else if ("id" in result) {
          const entry = result as Seg;
          setSegments((current) => current.some((segment) => segment.id === entry.id)
            ? current.map((segment) => segment.id === entry.id ? { ...segment, ...entry } : segment)
            : [...current, entry]);
          await Promise.all([refreshHistory(), refreshActions()]);
        }
      } catch (error) {
        if (isOwned(ownerProjectId, token)) setErr(error instanceof Error ? error.message : String(error));
      } finally {
        if (transcribeRef.current === operation) transcribeRef.current = null;
        if (isOwned(ownerProjectId, token)) {
          busyRef.current = false;
          setBusy(false);
        }
        markProjectSavePending();
      }
    })();
    transcribeRef.current = operation;
    return operation;
  }, [api, isOwned, refreshActions, refreshHistory, requests, stopTimer]);

  const patchSeg = useCallback((id: string, patch: Partial<Seg>) =>
    setSegments((current) => current.map((segment) =>
      segment.id === id ? { ...segment, ...patch } : segment)), []);

  const appendToScene = useCallback(async (ownerProjectId: number, sceneId: number, text: string) => {
    await flushPendingProjectSaves({ excludeFlusher: voiceFlusher });
    if (projectIdRef.current !== ownerProjectId) throw new Error("The active project changed before Voice could update the scene.");
    const current = (await api.listScenes(ownerProjectId)).find((scene) => scene.id === sceneId);
    if (!current) throw new Error("The target scene no longer exists.");
    if (projectIdRef.current !== ownerProjectId) throw new Error("The active project changed before Voice could update the scene.");
    const content = (current.content ? current.content + "\n\n" : "") + text;
    await trackProjectWrite(api.updateScene(ownerProjectId, current.id, {
      content,
      ...(current.revision ? { expected_revision: current.revision } : {}),
    }));
    scenes.refetch();
  }, [api, scenes, voiceFlusher]);

  const runVoiceAction = useCallback((
    action: (ownerProjectId: number, token: RequestToken) => Promise<void>,
    allowPendingWork = false,
    allowPendingInsert = false,
  ): Promise<void> | null => {
    const ownerProjectId = projectIdRef.current;
    if (ownerProjectId == null || micStartRef.current || recordingRef.current || busyRef.current
      || transcribeRef.current || actionRef.current || workBusyRef.current) return null;
    if (workRef.current && !allowPendingWork) {
      setErr("Apply or dismiss the pending Voice preview before starting another action.");
      return null;
    }
    if (pendingInsertRef.current && !allowPendingInsert) {
      setErr("Retry or discard the pending Voice scene insertion before starting another action.");
      return null;
    }
    const token = requests.begin("work");
    workBusyRef.current = true;
    setWorkBusy(true); setErr(null); setNote(null);
    markProjectSavePending();
    let operation!: Promise<void>;
    operation = (async () => {
      try {
        await action(ownerProjectId, token);
      } catch (error) {
        if (isOwned(ownerProjectId, token)) setErr(error instanceof Error ? error.message : String(error));
      } finally {
        if (actionRef.current === operation) actionRef.current = null;
        if (isOwned(ownerProjectId, token)) {
          workBusyRef.current = false;
          setWorkBusy(false);
        }
        markProjectSavePending();
      }
    })();
    actionRef.current = operation;
    return operation;
  }, [isOwned, requests]);

  const preservePendingInsert = useCallback((value: PendingInsert, error: unknown) => {
    pendingInsertRef.current = value;
    setPendingInsert(value);
    setErr(`Voice completed, but the scene insertion is still pending. ${error instanceof Error ? error.message : String(error)}`);
    markProjectSavePending();
  }, []);

  const retryPendingInsert = useCallback(() => {
    const pending = pendingInsertRef.current;
    if (!pending) return;
    void runVoiceAction(async (ownerProjectId, token) => {
      if (pendingInsertRef.current !== pending || ownerProjectId !== pending.projectId) return;
      await appendToScene(ownerProjectId, pending.sceneId, pending.text);
      if (!isOwned(ownerProjectId, token) || pendingInsertRef.current !== pending) return;
      patchSeg(pending.segId, { committedLabel: pending.label });
      pendingInsertRef.current = null;
      setPendingInsert(null);
      setErr(null);
      setNote(pending.message);
      markProjectSavePending();
      await Promise.all([refreshHistory(), refreshActions()]);
    }, false, true);
  }, [appendToScene, isOwned, patchSeg, refreshActions, refreshHistory, runVoiceAction]);

  const discardPendingInsert = useCallback(() => {
    if (workBusyRef.current) return;
    pendingInsertRef.current = null;
    setPendingInsert(null);
    setErr(null);
    setNote("Pending scene insertion discarded; the transcript remains in Voice history.");
    markProjectSavePending();
  }, []);

  const dismissWork = useCallback(() => {
    const pending = workRef.current;
    if (!pending || workBusyRef.current) return;
    void runVoiceAction(async (ownerProjectId, token) => {
      if (workRef.current !== pending) return;
      const result = pending.kind === "intent"
        ? await api.voiceIntentCancel(ownerProjectId, { preview_id: pending.preview.id })
        : await api.voiceBillyCancel(ownerProjectId, { proposal_id: pending.proposal.id });
      if (!isOwned(ownerProjectId, token)) return;
      workRef.current = null;
      setWork(null);
      setNote(result.message || "Voice preview dismissed.");
      markProjectSavePending();
      await refreshHistory();
    }, true);
  }, [api, isOwned, refreshHistory, runVoiceAction]);

  // --- Intent (cleanup) ----------------------------------------------------
  const runIntent = useCallback((seg: Seg, intent: VoiceIntentDTO) => {
    const context = ctx();
    void runVoiceAction(async (ownerProjectId, token) => {
      const preview = await api.voiceIntentPreview(ownerProjectId, {
        intent_id: intent.id,
        source_text: seg.text,
        source_segment_ids: [seg.id],
        ctx: context,
      });
      if (!isOwned(ownerProjectId, token)) return;
      const next: Work = { kind: "intent", segId: seg.id, preview };
      workRef.current = next;
      setWork(next);
    });
  }, [api, ctx, isOwned, runVoiceAction]);

  const applyIntent = useCallback(() => {
    const pending = workRef.current;
    if (pending?.kind !== "intent") return;
    const context = ctx();
    void runVoiceAction(async (ownerProjectId, token) => {
      if (workRef.current !== pending) return;
      const result = await api.voiceIntentApply(ownerProjectId, {
        preview_id: pending.preview.id,
        ctx: context,
      });
      if (!isOwned(ownerProjectId, token)) return;
      if (result.applied) {
        if (result.cleaned_text) patchSeg(pending.segId, { text: result.cleaned_text });
        setNote(result.message || "Cleanup applied.");
      } else setErr(result.message || "Intent could not be applied.");
      workRef.current = null;
      setWork(null);
      markProjectSavePending();
      await Promise.all([refreshHistory(), refreshActions()]);
    }, true);
  }, [api, ctx, isOwned, patchSeg, refreshActions, refreshHistory, runVoiceAction]);

  // --- Billy (ask / edit by voice) -----------------------------------------
  const runBilly = useCallback((seg: Seg, op: VoiceBillyOperationDTO) => {
    const context = ctx();
    void runVoiceAction(async (ownerProjectId, token) => {
      const proposal = await api.voiceBillyGenerate(ownerProjectId, {
        operation: op.id,
        transcript_text: seg.text,
        source_segment_ids: [seg.id],
        ctx: context,
      });
      if (!isOwned(ownerProjectId, token)) return;
      const next: Work = { kind: "billy", segId: seg.id, proposal };
      workRef.current = next;
      setWork(next);
      patchSeg(seg.id, { sent_to_billy: true });
    });
  }, [api, ctx, isOwned, patchSeg, runVoiceAction]);

  const applyBilly = useCallback(() => {
    const pending = workRef.current;
    if (pending?.kind !== "billy") return;
    const context = ctx();
    const targetSceneId = activeScene?.id ?? null;
    void runVoiceAction(async (ownerProjectId, token) => {
      if (workRef.current !== pending) return;
      const result = await api.voiceBillyApply(ownerProjectId, {
        proposal_id: pending.proposal.id,
        ctx: context,
      });
      if (!isOwned(ownerProjectId, token)) return;
      if (result.applied) {
        if (result.inserted_text) {
          if (targetSceneId == null) throw new Error("The scene target is no longer available.");
          try {
            await appendToScene(ownerProjectId, targetSceneId, result.inserted_text);
          } catch (error) {
            if (isOwned(ownerProjectId, token)) {
              preservePendingInsert({
                projectId: ownerProjectId, sceneId: targetSceneId,
                segId: pending.segId, label: "→ scene (Billy)", text: result.inserted_text,
                message: result.message || "Billy's edit inserted in the scene.",
              }, error);
              workRef.current = null;
              setWork(null);
              markProjectSavePending();
              await Promise.all([refreshHistory(), refreshActions()]);
            }
            return;
          }
          if (!isOwned(ownerProjectId, token)) return;
          patchSeg(pending.segId, { committedLabel: "→ scene (Billy)" });
        }
        setNote(result.message || "Billy's edit applied.");
      } else setErr(result.message || "Could not apply Billy's proposal.");
      workRef.current = null;
      setWork(null);
      markProjectSavePending();
      await Promise.all([refreshHistory(), refreshActions()]);
    }, true);
  }, [activeScene?.id, api, appendToScene, ctx, isOwned, patchSeg, preservePendingInsert, refreshActions, refreshHistory, runVoiceAction]);

  // --- Commit --------------------------------------------------------------
  const commit = useCallback((seg: Seg, target: VoiceCommitTargetDTO) => {
    const context = ctx();
    const targetSceneId = activeScene?.id ?? null;
    void runVoiceAction(async (ownerProjectId, token) => {
      const result = await api.voiceCommit(ownerProjectId, {
        text: seg.text,
        target_id: target.id,
        source_segment_ids: [seg.id],
        ctx: context,
      });
      if (!isOwned(ownerProjectId, token)) return;
      if (!result.applied) {
        setErr(result.message || "Commit failed.");
        return;
      }
      if (result.inserted_text) {
        if (targetSceneId == null) throw new Error("The scene target is no longer available.");
        try {
          await appendToScene(ownerProjectId, targetSceneId, result.inserted_text);
        } catch (error) {
          if (isOwned(ownerProjectId, token)) {
            preservePendingInsert({
              projectId: ownerProjectId, sceneId: targetSceneId,
              segId: seg.id, label: `→ ${target.label}`, text: result.inserted_text,
              message: result.message || `Committed ${target.label}.`,
            }, error);
            await Promise.all([refreshHistory(), refreshActions()]);
          }
          return;
        }
        if (!isOwned(ownerProjectId, token)) return;
      }
      patchSeg(seg.id, { committedLabel: `→ ${target.label}` });
      setNote(result.message || `Committed ${target.label}.`);
      await Promise.all([refreshHistory(), refreshActions()]);
    });
  }, [activeScene?.id, api, appendToScene, ctx, isOwned, patchSeg, preservePendingInsert, refreshActions, refreshHistory, runVoiceAction]);

  const undo = useCallback(() => {
    void runVoiceAction(async (ownerProjectId, token) => {
      const result = await api.voiceUndo(ownerProjectId);
      if (!isOwned(ownerProjectId, token)) return;
      setNote(result.message || (result.undone ? "Last commit undone." : "Nothing to undo."));
      scenes.refetch();
      await Promise.all([refreshHistory(), refreshActions()]);
    });
  }, [api, isOwned, refreshActions, refreshHistory, runVoiceAction, scenes]);

  const cleanupIntents = intents.filter((i) => i.enabled && (i.type === "cleanup" || /clean/i.test(i.id)));
  const askOps = billyOps.filter((o) => o.enabled);
  const commitTargets = targets.filter((t) => t.enabled);
  const actionLocked = micStarting || recording || busy || workBusy || work !== null || pendingInsert !== null;
  const commitLabelFor = (segment: Seg) => segment.committedLabel
    || (segment.committed_target
      ? `→ ${targets.find((target) => target.id === segment.committed_target)?.label ?? segment.committed_target}`
      : "");

  return (
    <PanelShell {...props} style={ACCENT}>
      <div data-screen-label="Dexters Room Voice" style={panelBox}>
        <Corners />

        {/* header */}
        <div style={{ height: 40, flex: "none", display: "flex", alignItems: "center", gap: 11, padding: "0 16px", borderBottom: "1px solid var(--line)" }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".1em", color: "var(--strong)" }}>DEXTER&apos;S ROOM</span>
          <span style={{ fontSize: 8, color: "var(--txt3)", border: "1px solid var(--line2)", padding: "2px 7px", letterSpacing: ".1em" }}>LOCAL · audio never leaves device</span>
          <div style={{ flex: 1 }} />
          {canUndo && <button type="button" disabled={actionLocked} onClick={() => void undo()} style={{ ...btn, fontSize: 8, color: "var(--amber)", borderColor: "var(--amber)" }}>↺ UNDO LAST</button>}
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
              <button type="button" onClick={() => (recording ? void stopRecord() : void beginRecord())} disabled={busy || micStarting || workBusy || work !== null || !status}
                title={recording ? "Stop + transcribe" : "Start recording"}
                style={{ position: "relative", width: 56, height: 56, flex: "none", borderRadius: "50%", border: `2px solid ${recording ? "var(--blocking,#ff5260)" : "var(--cyan)"}`, background: "transparent", color: recording ? "var(--blocking,#ff5260)" : "var(--cyan)", fontSize: 10, letterSpacing: ".1em", cursor: busy || micStarting ? "default" : "pointer", boxShadow: recording ? "0 0 22px rgba(255,82,96,.35) inset" : "0 0 18px rgba(76,194,255,.25) inset" }}>
                {busy || micStarting ? "···" : recording ? "■" : "REC"}
              </button>
              <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 2, height: 54, opacity: recording ? 1 : 0.25 }}>
                {WAVE.map((dur, i) => (
                  <div key={i} style={{ flex: 1, height: `${HEIGHTS[i]}%`, background: "linear-gradient(180deg,var(--cyan),rgba(76,194,255,.2))", animation: recording ? `lf-bars ${dur} ease-in-out infinite` : "none" }} />
                ))}
              </div>
              <div style={{ flex: "none", textAlign: "right" }}>
                <div style={{ fontFamily: "'Chakra Petch'", fontSize: 13, color: recording ? "var(--cyan)" : "var(--txt2)" }}>{busy ? "TRANSCRIBING" : micStarting ? "STARTING MIC" : recording ? "LISTENING" : "IDLE"}</div>
                <div style={{ fontSize: 8, color: "var(--txt3)" }}>{recording ? `${elapsed}s` : work ? "resolve the preview to continue" : "press REC to dictate"}</div>
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
              {pendingInsert && (
                <div role="alert" style={{ marginBottom: 9, padding: "8px 10px", border: "1px solid var(--crimson)", background: "rgba(255,82,96,.08)", color: "var(--txt2)", fontSize: 9 }}>
                  <div style={{ color: "var(--crimson)", marginBottom: 4 }}>SCENE INSERTION PENDING · the Voice action will not be run twice</div>
                  <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.45, maxHeight: 72, overflowY: "auto" }}>{pendingInsert.text}</div>
                  <div style={{ display: "flex", gap: 7, marginTop: 7 }}>
                    <button type="button" disabled={workBusy} style={{ ...btn, color: "var(--cyan)" }} onClick={retryPendingInsert}>RETRY INSERT</button>
                    <button type="button" disabled={workBusy} style={{ ...btn, color: "var(--crimson)" }} onClick={discardPendingInsert}>DISCARD INSERT</button>
                  </div>
                </div>
              )}
              {Object.entries(loadErrors).map(([key, message]) => (
                <div key={key} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8, padding: "7px 9px", border: "1px solid var(--line2)", color: "var(--crimson)", fontSize: 9 }}>
                  <span style={{ flex: 1 }}>Could not load Voice {key}: {message}</span>
                  <button type="button" style={btn} onClick={() => void (key === "history" ? refreshHistory() : refreshActions())}>RETRY</button>
                </div>
              ))}
              <div style={{ fontSize: 7.5, letterSpacing: ".18em", color: "var(--txt3)", marginBottom: 9 }}>TRANSCRIPT · session history</div>
              {segments.length === 0
                ? <div style={{ fontSize: 10, color: "var(--txt3)", fontStyle: "italic" }}>Nothing yet — press REC, speak, then stop. Each segment records to the session and can be cleaned, sent to Billy, or committed.</div>
                : <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {segments.map((seg) => (
                      <div key={seg.id} style={{ border: "1px solid var(--line2)", borderLeft: `2px solid ${commitLabelFor(seg) ? "var(--green)" : "var(--cyan)"}`, background: "var(--tint)", padding: "9px 11px" }}>
                        <div style={{ fontSize: 11, color: "var(--txt)", lineHeight: 1.5 }}>{seg.text}</div>

                        {/* action bar */}
                        <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                          {commitLabelFor(seg) && <span style={{ fontSize: 8, color: "var(--green)", marginRight: 4 }}>✓ {commitLabelFor(seg)}</span>}

                          {cleanupIntents.map((i) => (
                            <button key={i.id} type="button" disabled={actionLocked} onClick={() => void runIntent(seg, i)} style={{ ...btn, color: "var(--txt2)" }} title={i.label}>✦ {i.label.toUpperCase()}</button>
                          ))}

                          {askOps.length > 0 && (
                            <select disabled={actionLocked} defaultValue="" aria-label={`Billy action for transcript ${seg.preview || seg.text}`} onChange={(e) => { const op = askOps.find((o) => o.id === e.target.value); if (op) void runBilly(seg, op); e.currentTarget.value = ""; }} style={sel} title="Ask or edit with Billy by voice">
                              <option value="" disabled>◇ BILLY…</option>
                              {askOps.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
                            </select>
                          )}

                          {commitTargets.length > 0 && (
                            <select disabled={actionLocked} defaultValue="" aria-label={`Commit target for transcript ${seg.preview || seg.text}`} onChange={(e) => { const t = commitTargets.find((x) => x.id === e.target.value); if (t) void commit(seg, t); e.currentTarget.value = ""; }} style={{ ...sel, color: "var(--cyan)", borderColor: "var(--line-cy,#2b6f8f)", marginLeft: "auto" }} title="Commit this segment">
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
                              <button type="button" disabled={workBusy} onClick={dismissWork} style={{ ...btn }}>DISMISS</button>
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
