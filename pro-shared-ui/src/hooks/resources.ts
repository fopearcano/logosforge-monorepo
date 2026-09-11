import { useState, useCallback, useEffect, useRef } from "react";
import type { NoteDTO, CharacterDTO, SceneDTO, PsykeEntryDTO, PsykeRelationDTO, PsykeProgressionDTO, OutlineNodeDTO, ProjectDTO, TimelineEventDTO, PlotBlockDTO, ExportRequestDTO, ExportResponseDTO, NarrativeDashboardDTO, ContinuityReportDTO, PacingInsightDTO, BalanceDataDTO, StoryHealthDTO, StructuralAnalysisDTO, WorkflowRunDTO, DecisionRadarDTO, GraphGravityDTO, AdaptDTO, ReviewReportDTO, FormatReviewDTO, QuantumResultDTO, AssistantResponseDTO, ExtractionResultDTO, ExtractionApplyRequestDTO, ExtractionApplyReportDTO } from "@logosforge/ui-contracts";
import type { ExtractionJobDTO } from "@logosforge/ui-contracts";
import { useStudio } from "../adapters/StudioProvider";
import { useResource, type Resource } from "./useResource";
import { createLatestRequestGate } from "./latestRequest";
import { ExtractionPollingCancelled, pollExtractionJob } from "./extractionPolling";
import { forgetExtraction, recallExtraction, rememberExtraction } from "./extractionSession";

/** One-shot export action: POSTs an ExportRequest, exposing run/result/running/error (not a Resource — fires on demand). */
export function useExport(): { run: (req: ExportRequestDTO) => Promise<void>; running: boolean; result: ExportResponseDTO | null; error: string | null } {
  const { api, projectId } = useStudio();
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<ExportResponseDTO | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(async (request: ExportRequestDTO) => {
    if (projectId == null) { setError("No project selected"); return; }
    setRunning(true); setError(null);
    try { setResult(await api.export(projectId, request)); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); setResult(null); }
    finally { setRunning(false); }
  }, [api, projectId]);
  return { run, running, result, error };
}

/** Project settings bag (getSettings) + a patch writer (patchSettings → refetch). Exercises the write path. */
export function useSettings(): {
  data: Record<string, unknown> | undefined;
  loading: boolean;
  error: string | null;
  patch: (changes: Record<string, unknown>) => Promise<void>;
  saving: boolean;
} {
  const { api, projectId } = useStudio();
  const res = useResource(projectId ?? null, () => api.getSettings(projectId as number).then((s) => s.settings), ["project_data_changed"]);
  const [overrides, setOverrides] = useState<Record<string, unknown>>({});
  const [pendingWrites, setPendingWrites] = useState(0);
  const [writeError, setWriteError] = useState<string | null>(null);
  const projectIdRef = useRef(projectId);
  projectIdRef.current = projectId;
  const versions = useRef(new Map<string, number>());
  const confirmed = useRef(new Map<string, number>());
  const sequence = useRef(0);
  // drop optimistic overrides when the project changes (don't leak across projects)
  useEffect(() => {
    setOverrides({});
    setPendingWrites(0);
    setWriteError(null);
    versions.current.clear();
    confirmed.current.clear();
  }, [projectId]);
  // A successful PATCH publishes/refetches the authoritative settings object.
  // Remove only optimistic values whose latest request has been confirmed; a
  // newer in-flight value for the same key must remain visible.
  useEffect(() => {
    if (!res.data || confirmed.current.size === 0) return;
    setOverrides((current) => {
      let changed = false;
      const next = { ...current };
      for (const [key, token] of confirmed.current) {
        if (versions.current.get(key) !== token) {
          confirmed.current.delete(key);
          continue;
        }
        delete next[key];
        confirmed.current.delete(key);
        changed = true;
      }
      return changed ? next : current;
    });
  }, [res.data]);
  // optimistic overlay so a write reflects immediately; refetch reconciles to the core's truth
  const data = res.data ? { ...res.data, ...overrides } : Object.keys(overrides).length ? overrides : undefined;
  const patch = useCallback(
    async (changes: Record<string, unknown>) => {
      if (projectId == null) return;
      const ownerProjectId = projectId;
      const token = ++sequence.current;
      for (const key of Object.keys(changes)) versions.current.set(key, token);
      setOverrides((o) => ({ ...o, ...changes }));
      setPendingWrites((count) => count + 1);
      setWriteError(null);
      try {
        await api.patchSettings(ownerProjectId, { settings: changes });
        if (projectIdRef.current !== ownerProjectId) return;
        for (const key of Object.keys(changes)) confirmed.current.set(key, token);
        res.refetch();
      } catch (error) {
        if (projectIdRef.current !== ownerProjectId) return;
        setOverrides((current) => {
          const next = { ...current };
          let changed = false;
          for (const key of Object.keys(changes)) {
            if (versions.current.get(key) !== token) continue;
            delete next[key];
            versions.current.delete(key);
            confirmed.current.delete(key);
            changed = true;
          }
          return changed ? next : current;
        });
        setWriteError(error instanceof Error ? error.message : String(error));
        res.refetch();
      } finally {
        if (projectIdRef.current === ownerProjectId) {
          setPendingWrites((count) => Math.max(0, count - 1));
        }
      }
    },
    [api, projectId, res],
  );
  return { data, loading: res.loading, error: writeError ?? res.error, patch, saving: pendingWrites > 0 };
}

/** Scene-derived timeline events for the active project. */
export function useTimeline(): Resource<TimelineEventDTO[]> {
  const { api, projectId } = useStudio();
  return useResource(projectId ?? null, () => api.getTimeline(projectId as number), ["timeline_changed", "scenes_changed", "scene_changed"]);
}

/** Plot-lane blocks (plotline → scenes) for the active project. */
export function usePlot(): Resource<PlotBlockDTO[]> {
  const { api, projectId } = useStudio();
  return useResource(projectId ?? null, () => api.getPlot(projectId as number), ["plot_changed", "scenes_changed", "scene_changed"]);
}

/** Derived narrative dashboard (tension curve, character/theme presence, structure) — read-only. */
export function useDashboard(): Resource<NarrativeDashboardDTO> {
  const { api, projectId } = useStudio();
  return useResource(projectId ?? null, () => api.getDashboard(projectId as number), ["dashboard_changed", "scenes_changed", "scene_changed", "psyke_changed"]);
}

/** Continuity issues (contradictions, drift, gaps) by dimension + counts. */
export function useContinuity(): Resource<ContinuityReportDTO> {
  const { api, projectId } = useStudio();
  return useResource(projectId ?? null, () => api.getContinuity(projectId as number), ["scenes_changed", "scene_changed", "psyke_changed"]);
}

/** Pacing insights (monotony, disappearance, stagnation, …) — up to 5. */
export function usePacing(): Resource<PacingInsightDTO[]> {
  const { api, projectId } = useStudio();
  return useResource(projectId ?? null, () => api.getPacing(projectId as number), ["scenes_changed", "scene_changed"]);
}

/** Character/arc scene-distribution balance with imbalance flags. */
export function useBalance(): Resource<BalanceDataDTO> {
  const { api, projectId } = useStudio();
  return useResource(projectId ?? null, () => api.getBalance(projectId as number), ["scenes_changed", "scene_changed", "psyke_changed"]);
}

/** Four high-level story-health signals (structure, characters, arcs, density). */
export function useStoryHealth(): Resource<StoryHealthDTO> {
  const { api, projectId } = useStudio();
  return useResource(projectId ?? null, () => api.getStoryHealth(projectId as number), ["scenes_changed", "scene_changed", "psyke_changed"]);
}

/** Structural-weakness analysis (act balance, climax prep, beats, …). */
export function useStructureAnalysis(): Resource<StructuralAnalysisDTO> {
  const { api, projectId } = useStudio();
  return useResource(projectId ?? null, () => api.getStructureAnalysis(projectId as number), ["scenes_changed", "scene_changed", "psyke_changed"]);
}

/** Guided-workflow runs (steps + progress) for the active project. */
export function useWorkflows(): Resource<WorkflowRunDTO[]> {
  const { api, projectId } = useStudio();
  return useResource(projectId ?? null, () => api.getWorkflows(projectId as number), ["project_data_changed"]);
}

/** Decision radar — ranked decision cards (blocking→info) for the active project. */
export function useDecisionRadar(): Resource<DecisionRadarDTO> {
  const { api, projectId } = useStudio();
  return useResource(projectId ?? null, () => api.getDecisionRadar(projectId as number), ["scenes_changed", "scene_changed", "psyke_changed", "dashboard_changed"]);
}

/** Per-node story-gravity weights (narrative/thematic/structural) for the knowledge graph. */
export function useGraphGravity(): Resource<GraphGravityDTO> {
  const { api, projectId } = useStudio();
  return useResource(projectId ?? null, () => api.getGraphGravity(projectId as number), ["scenes_changed", "scene_changed", "psyke_changed"]);
}

/** Adaptive-AI mode (stage × health) + actionable suggestions for the active project. */
export function useAdapt(): Resource<AdaptDTO> {
  const { api, projectId } = useStudio();
  return useResource(projectId ?? null, () => api.getAdapt(projectId as number), ["scenes_changed", "scene_changed", "psyke_changed", "project_data_changed"]);
}

/** Screenplay review dashboard — per-scene readiness + summary metrics. */
export function useReview(): Resource<ReviewReportDTO> {
  const { api, projectId } = useStudio();
  return useResource(projectId ?? null, () => api.getReview(projectId as number), ["scenes_changed", "scene_changed", "project_data_changed"]);
}

/** Format-specific review checks (graphic novel / stage / series). */
export function useFormatReview(): Resource<FormatReviewDTO> {
  const { api, projectId } = useStudio();
  return useResource(projectId ?? null, () => api.getFormatReview(projectId as number), ["scenes_changed", "scene_changed", "project_data_changed"]);
}

/** Quantum outliner — generate a wavefunction of branches from a premise (POST action).
 *  `structureMode` (auto/classical/quantum/hybrid) picks the compose strategy. */
export function useQuantum(): { generate: (premise: string, n?: number, structureMode?: string) => Promise<void>; running: boolean; result: QuantumResultDTO | null; error: string | null } {
  const { api, projectId } = useStudio();
  const requests = useRef(createLatestRequestGate()).current;
  useEffect(() => { requests.open(); return () => requests.close(); }, [requests]);
  const runningRef = useRef(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<QuantumResultDTO | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    requests.invalidate("generate");
    runningRef.current = false;
    setRunning(false);
    setResult(null);
    setError(null);
  }, [api, projectId, requests]);
  const generate = useCallback(
    async (premise: string, n = 4, structureMode?: string) => {
      if (projectId == null || !premise.trim() || runningRef.current) return;
      const token = requests.begin("generate");
      runningRef.current = true;
      setRunning(true);
      setError(null);
      try {
        // The Quantum Outliner is the generative panel — request the LLM-backed
        // LAMBDA branches (degrades to deterministic stub branches with no provider).
        const value = await api.generateQuantumOutline(projectId, {
          premise, n, generative: true,
          ...(structureMode ? { structure_mode: structureMode } : {}),
        });
        if (requests.isCurrent(token)) setResult(value);
      } catch (e) {
        if (requests.isCurrent(token)) {
          setError(e instanceof Error ? e.message : String(e));
          setResult(null);
        }
      } finally {
        if (requests.isCurrent(token)) {
          runningRef.current = false;
          setRunning(false);
        }
      }
    },
    [api, projectId, requests],
  );
  return { generate, running, result, error };
}

/** Counterpart — a reflective second reader for a scene in a chosen dialogic mode (POST action; LLM-gated). */
export function useCounterpart(): { reflect: (mode: string, sceneContext: string) => Promise<void>; running: boolean; result: AssistantResponseDTO | null; error: string | null } {
  const { api, projectId } = useStudio();
  const requests = useRef(createLatestRequestGate()).current;
  useEffect(() => { requests.open(); return () => requests.close(); }, [requests]);
  const runningRef = useRef(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<AssistantResponseDTO | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    requests.invalidate("reflect");
    runningRef.current = false;
    setRunning(false); setResult(null); setError(null);
  }, [api, projectId, requests]);
  const reflect = useCallback(
    async (mode: string, sceneContext: string) => {
      if (projectId == null || !sceneContext.trim() || runningRef.current) return;
      const token = requests.begin("reflect");
      runningRef.current = true;
      setRunning(true);
      setError(null);
      try {
        const value = await api.runCounterpart(projectId, { mode, scene_context: sceneContext });
        if (requests.isCurrent(token)) setResult(value);
      } catch (e) {
        if (requests.isCurrent(token)) {
          setError(e instanceof Error ? e.message : String(e));
          setResult(null);
        }
      } finally {
        if (requests.isCurrent(token)) {
          runningRef.current = false;
          setRunning(false);
        }
      }
    },
    [api, projectId, requests],
  );
  return { reflect, running, result, error };
}

/** Manuscript extractor — propose structured data (read-only), review, then apply (POST actions). */
export function useExtraction(): {
  propose: (useLlm?: boolean, model?: string) => Promise<void>;
  cancel: () => Promise<void>;
  resume: () => Promise<void>;
  apply: (body: ExtractionApplyRequestDTO) => Promise<void>;
  revert: () => Promise<void>;
  proposals: ExtractionResultDTO | null;
  report: ExtractionApplyReportDTO | null;
  running: boolean;
  applying: boolean;
  reverting: boolean;
  error: string | null;
  progress: { done: number; total: number } | null;
  jobStatus: string | null;
} {
  const { api, projectId } = useStudio();
  const projectIdRef = useRef(projectId);
  projectIdRef.current = projectId;
  const requests = useRef(createLatestRequestGate()).current;
  useEffect(() => { requests.open(); return () => requests.close(); }, [requests]);
  const pollAbortRef = useRef<AbortController | null>(null);
  const activeJobRef = useRef<{ projectId: number; jobId: string } | null>(null);
  const runningRef = useRef(false);
  const applyingRef = useRef(false);
  const revertingRef = useRef(false);
  const cancellingRef = useRef(false);
  const [proposals, setProposals] = useState<ExtractionResultDTO | null>(null);
  const [report, setReport] = useState<ExtractionApplyReportDTO | null>(null);
  const [running, setRunning] = useState(false);
  const [applying, setApplying] = useState(false);
  const [reverting, setReverting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [jobStatus, setJobStatus] = useState<string | null>(null);

  const followJob = useCallback(async (
    ownerProjectId: number,
    initial: ExtractionJobDTO,
    token: ReturnType<typeof requests.begin>,
  ) => {
    pollAbortRef.current?.abort();
    const controller = new AbortController();
    pollAbortRef.current = controller;
    activeJobRef.current = { projectId: ownerProjectId, jobId: initial.job_id };
    runningRef.current = initial.status === "running" || initial.status === "cancelling";
    if (requests.isCurrent(token)) {
      setRunning(runningRef.current);
      setJobStatus(initial.status);
    }
    try {
      const outcome = await pollExtractionJob({
        initial,
        load: () => api.getExtractJob(ownerProjectId, initial.job_id),
        signal: controller.signal,
        onProgress: (job) => {
          if (!requests.isCurrent(token) || projectIdRef.current !== ownerProjectId) return;
          setProgress({ done: job.done, total: job.total });
          setJobStatus(job.status);
        },
      });
      if (!requests.isCurrent(token) || projectIdRef.current !== ownerProjectId) return;
      setJobStatus(outcome.kind);
      if (outcome.kind === "done") {
        activeJobRef.current = null;
        if (outcome.job.result) {
          setProposals(outcome.job.result);
          setError(null);
        } else {
          setProposals(null);
          setError("Extraction completed without a proposal payload.");
        }
      } else if (outcome.kind === "cancelled") {
        forgetExtraction(ownerProjectId);
        activeJobRef.current = null;
        setProposals(null);
        setProgress(null);
        setError(null);
      } else if (outcome.kind === "timeout") {
        setError("Polling timed out. The core job may still be running; Resume or Cancel it.");
      } else {
        activeJobRef.current = null;
        setProposals(null);
        setError(outcome.job.error || "Extraction failed");
      }
    } catch (pollError) {
      if (pollError instanceof ExtractionPollingCancelled) return;
      if (requests.isCurrent(token) && projectIdRef.current === ownerProjectId) {
        setError(pollError instanceof Error ? pollError.message : String(pollError));
        setJobStatus("poll_error");
      }
    } finally {
      if (pollAbortRef.current === controller) pollAbortRef.current = null;
      if (requests.isCurrent(token) && projectIdRef.current === ownerProjectId) {
        runningRef.current = false;
        cancellingRef.current = false;
        setRunning(false);
      }
    }
  }, [api, requests]);

  const resume = useCallback(async () => {
    if (projectId == null || runningRef.current) return;
    const remembered = recallExtraction(projectId);
    if (!remembered?.jobId) return;
    const ownerProjectId = projectId;
    const token = requests.begin("extract");
    runningRef.current = true;
    setRunning(true); setError(null); setJobStatus("resuming");
    try {
      const job = await api.getExtractJob(ownerProjectId, remembered.jobId);
      if (requests.isCurrent(token) && projectIdRef.current === ownerProjectId) {
        await followJob(ownerProjectId, job, token);
      }
    } catch (resumeError) {
      if (requests.isCurrent(token) && projectIdRef.current === ownerProjectId) {
        forgetExtraction(ownerProjectId);
        activeJobRef.current = null;
        runningRef.current = false;
        setRunning(false); setJobStatus("resume_error");
        setError(resumeError instanceof Error ? resumeError.message : String(resumeError));
      }
    }
  }, [api, projectId, followJob, requests]);

  useEffect(() => {
    pollAbortRef.current?.abort();
    requests.invalidate("extract"); requests.invalidate("apply"); requests.invalidate("revert");
    runningRef.current = false; applyingRef.current = false; revertingRef.current = false; cancellingRef.current = false;
    activeJobRef.current = null;
    setRunning(false); setApplying(false); setReverting(false);
    setProposals(null); setReport(null); setError(null); setProgress(null); setJobStatus(null);
    if (projectId != null) {
      const remembered = recallExtraction(projectId);
      if (remembered?.report) {
        setReport(remembered.report);
        setJobStatus("applied");
      } else if (remembered?.jobId) {
        void resume();
      }
    }
    return () => {
      pollAbortRef.current?.abort();
      requests.invalidate("extract"); requests.invalidate("apply"); requests.invalidate("revert");
    };
  }, [api, projectId, requests, resume]);

  const propose = useCallback(async (useLlm = true, model?: string) => {
    if (projectId == null || runningRef.current || applyingRef.current || revertingRef.current || activeJobRef.current != null) return;
    const ownerProjectId = projectId;
    const token = requests.begin("extract");
    pollAbortRef.current?.abort();
    runningRef.current = true;
    forgetExtraction(ownerProjectId);
    activeJobRef.current = null;
    setRunning(true); setError(null); setReport(null); setProposals(null); setProgress(null); setJobStatus("starting");
    try {
      const job = await api.startExtract(ownerProjectId, useLlm, model);
      rememberExtraction(ownerProjectId, { jobId: job.job_id });
      activeJobRef.current = { projectId: ownerProjectId, jobId: job.job_id };
      if (requests.isCurrent(token) && projectIdRef.current === ownerProjectId) {
        await followJob(ownerProjectId, job, token);
      }
    } catch (startError) {
      if (requests.isCurrent(token) && projectIdRef.current === ownerProjectId) {
        runningRef.current = false;
        setRunning(false); setJobStatus("start_error");
        setError(startError instanceof Error ? startError.message : String(startError));
      }
    }
  }, [api, projectId, followJob, requests]);

  const cancel = useCallback(async () => {
    if (projectId == null || cancellingRef.current) return;
    let active = activeJobRef.current?.projectId === projectId ? activeJobRef.current : null;
    if (!active) {
      const remembered = recallExtraction(projectId);
      if (remembered?.jobId) active = { projectId, jobId: remembered.jobId };
    }
    if (!active) return;
    const token = requests.begin("extract");
    pollAbortRef.current?.abort();
    cancellingRef.current = true;
    runningRef.current = true;
    setRunning(true); setError(null); setJobStatus("cancelling");
    try {
      const job = await api.cancelExtractJob(active.projectId, active.jobId);
      rememberExtraction(active.projectId, { jobId: active.jobId });
      if (requests.isCurrent(token) && projectIdRef.current === active.projectId) {
        await followJob(active.projectId, job, token);
      }
    } catch (cancelError) {
      if (requests.isCurrent(token) && projectIdRef.current === active.projectId) {
        cancellingRef.current = false;
        runningRef.current = false;
        setRunning(false); setJobStatus("cancel_error");
        setError(`Cancellation failed — ${cancelError instanceof Error ? cancelError.message : String(cancelError)}`);
      }
    }
  }, [api, projectId, followJob, requests]);

  const apply = useCallback(
    async (body: ExtractionApplyRequestDTO) => {
      if (projectId == null || applyingRef.current || runningRef.current || revertingRef.current) return;
      const ownerProjectId = projectId;
      const token = requests.begin("apply");
      applyingRef.current = true;
      setApplying(true);
      setError(null);
      try {
        const value = await api.applyExtraction(ownerProjectId, body);
        if (requests.isCurrent(token) && projectIdRef.current === ownerProjectId) {
          setReport(value);
          setJobStatus("applied");
          rememberExtraction(ownerProjectId, { report: value });
          activeJobRef.current = null;
        }
      } catch (applyError) {
        if (requests.isCurrent(token) && projectIdRef.current === ownerProjectId) {
          setError(applyError instanceof Error ? applyError.message : String(applyError));
        }
      } finally {
        if (requests.isCurrent(token) && projectIdRef.current === ownerProjectId) {
          applyingRef.current = false;
          setApplying(false);
        }
      }
    },
    [api, projectId, requests],
  );
  // undo the last apply via its provenance receipt
  const revert = useCallback(async () => {
    if (projectId == null || !report?.receipt || revertingRef.current || applyingRef.current || runningRef.current) return;
    const ownerProjectId = projectId;
    const receipt = report.receipt;
    const token = requests.begin("revert");
    revertingRef.current = true;
    setReverting(true);
    setError(null);
    try {
      await api.revertExtraction(ownerProjectId, receipt);
      if (requests.isCurrent(token) && projectIdRef.current === ownerProjectId) {
        setReport(null); setProposals(null); setJobStatus("reverted");
        forgetExtraction(ownerProjectId);
      }
    } catch (revertError) {
      if (requests.isCurrent(token) && projectIdRef.current === ownerProjectId) {
        setError(revertError instanceof Error ? revertError.message : String(revertError));
      }
    } finally {
      if (requests.isCurrent(token) && projectIdRef.current === ownerProjectId) {
        revertingRef.current = false;
        setReverting(false);
      }
    }
  }, [api, projectId, report, requests]);
  return { propose, cancel, resume, apply, revert, proposals, report, running, applying, reverting, error, progress, jobStatus };
}

/** All projects (cross-project — used by the Launchpad). */
export function useProjects(): Resource<ProjectDTO[]> {
  const { api } = useStudio();
  return useResource("projects", () => api.listProjects(), []);
}

/** Typed PSYKE relations for the active project. */
export function usePsykeRelations(): Resource<PsykeRelationDTO[]> {
  const { api, projectId } = useStudio();
  return useResource(projectId ?? null, () => api.listRelations(projectId as number), ["psyke_changed"]);
}

/** PSYKE progressions (scene-pinned states) for the active project. */
export function usePsykeProgressions(): Resource<PsykeProgressionDTO[]> {
  const { api, projectId } = useStudio();
  return useResource(projectId ?? null, () => api.listProgressions(projectId as number), ["psyke_changed"]);
}

/**
 * Per-domain data hooks: thin wrappers over `useResource` that bind the active
 * project's `ApiClient` call to the change-events that should refresh it. Panels
 * call these instead of touching the ApiClient directly.
 */

export function useNotes(): Resource<NoteDTO[]> {
  const { api, projectId } = useStudio();
  return useResource(projectId ?? null, () => api.listNotes(projectId as number), ["notes_changed"]);
}

/** The manuscript cast (with the stable Character->PSYKE bible link). Refetches on
 *  character/psyke/scene changes so the link stays in sync with both sides. */
export function useCharacters(): Resource<CharacterDTO[]> {
  const { api, projectId } = useStudio();
  return useResource(
    projectId ?? null,
    () => api.listCharacters(projectId as number),
    ["characters_changed", "psyke_changed", "scenes_changed"],
  );
}

export function useScenes(): Resource<SceneDTO[]> {
  const { api, projectId } = useStudio();
  return useResource(projectId ?? null, () => api.listScenes(projectId as number), ["scenes_changed", "scene_changed"]);
}

export function usePsykeEntries(): Resource<PsykeEntryDTO[]> {
  const { api, projectId } = useStudio();
  return useResource(projectId ?? null, () => api.listPsyke(projectId as number), ["psyke_changed"]);
}

export function useOutline(): Resource<OutlineNodeDTO[]> {
  const { api, projectId } = useStudio();
  return useResource(projectId ?? null, () => api.getOutline(projectId as number), ["outline_changed"]);
}
