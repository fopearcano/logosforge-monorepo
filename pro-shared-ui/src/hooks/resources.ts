import { useState, useCallback, useEffect } from "react";
import type { NoteDTO, CharacterDTO, SceneDTO, PsykeEntryDTO, PsykeRelationDTO, PsykeProgressionDTO, OutlineNodeDTO, ProjectDTO, TimelineEventDTO, PlotBlockDTO, ExportRequestDTO, ExportResponseDTO, NarrativeDashboardDTO, ContinuityReportDTO, PacingInsightDTO, BalanceDataDTO, StoryHealthDTO, StructuralAnalysisDTO, WorkflowRunDTO, DecisionRadarDTO, GraphGravityDTO, QuantumResultDTO, AssistantResponseDTO, ExtractionResultDTO, ExtractionApplyRequestDTO, ExtractionApplyReportDTO } from "@logosforge/ui-contracts";
import { useStudio } from "../adapters/StudioProvider";
import { useResource, type Resource } from "./useResource";

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
  const [saving, setSaving] = useState(false);
  // drop optimistic overrides when the project changes (don't leak across projects)
  useEffect(() => { setOverrides({}); }, [projectId]);
  // optimistic overlay so a write reflects immediately; refetch reconciles to the core's truth
  const data = res.data ? { ...res.data, ...overrides } : Object.keys(overrides).length ? overrides : undefined;
  const patch = useCallback(
    async (changes: Record<string, unknown>) => {
      if (projectId == null) return;
      setOverrides((o) => ({ ...o, ...changes }));
      setSaving(true);
      try {
        await api.patchSettings(projectId, { settings: changes });
        res.refetch();
      } finally {
        setSaving(false);
      }
    },
    [api, projectId, res],
  );
  return { data, loading: res.loading, error: res.error, patch, saving };
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

/** Quantum outliner — generate a wavefunction of branches from a premise (POST action). */
export function useQuantum(): { generate: (premise: string, n?: number) => Promise<void>; running: boolean; result: QuantumResultDTO | null; error: string | null } {
  const { api, projectId } = useStudio();
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<QuantumResultDTO | null>(null);
  const [error, setError] = useState<string | null>(null);
  const generate = useCallback(
    async (premise: string, n = 4) => {
      if (projectId == null || !premise.trim()) return;
      setRunning(true);
      setError(null);
      try {
        setResult(await api.generateQuantumOutline(projectId, { premise, n }));
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        setResult(null);
      } finally {
        setRunning(false);
      }
    },
    [api, projectId],
  );
  return { generate, running, result, error };
}

/** Counterpart — a reflective second reader for a scene in a chosen dialogic mode (POST action; LLM-gated). */
export function useCounterpart(): { reflect: (mode: string, sceneContext: string) => Promise<void>; running: boolean; result: AssistantResponseDTO | null; error: string | null } {
  const { api, projectId } = useStudio();
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<AssistantResponseDTO | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reflect = useCallback(
    async (mode: string, sceneContext: string) => {
      if (projectId == null || !sceneContext.trim()) return;
      setRunning(true);
      setError(null);
      try {
        setResult(await api.runCounterpart(projectId, { mode, scene_context: sceneContext }));
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        setResult(null);
      } finally {
        setRunning(false);
      }
    },
    [api, projectId],
  );
  return { reflect, running, result, error };
}

/** Manuscript extractor — propose structured data (read-only), review, then apply (POST actions). */
export function useExtraction(): {
  propose: (useLlm?: boolean, model?: string) => Promise<void>;
  apply: (body: ExtractionApplyRequestDTO) => Promise<void>;
  revert: () => Promise<void>;
  proposals: ExtractionResultDTO | null;
  report: ExtractionApplyReportDTO | null;
  running: boolean;
  applying: boolean;
  reverting: boolean;
  error: string | null;
  progress: { done: number; total: number } | null;
} {
  const { api, projectId } = useStudio();
  const [proposals, setProposals] = useState<ExtractionResultDTO | null>(null);
  const [report, setReport] = useState<ExtractionApplyReportDTO | null>(null);
  const [running, setRunning] = useState(false);
  const [applying, setApplying] = useState(false);
  const [reverting, setReverting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  // start an async extraction job, then poll its progress until done/error
  const propose = useCallback(
    async (useLlm = true, model?: string) => {
      if (projectId == null) return;
      setRunning(true);
      setError(null);
      setReport(null);
      setProposals(null);
      setProgress(null);
      try {
        const job = await api.startExtract(projectId, useLlm, model);
        setProgress({ done: job.done, total: job.total });
        let cur = job;
        for (let i = 0; cur.status === "running" && i < 800; i++) {
          await new Promise((r) => setTimeout(r, 900));
          cur = await api.getExtractJob(projectId, job.job_id);
          setProgress({ done: cur.done, total: cur.total });
        }
        if (cur.status === "error") setError(cur.error || "Extraction failed");
        else setProposals(cur.result ?? null);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        setProposals(null);
      } finally {
        setRunning(false);
      }
    },
    [api, projectId],
  );
  const apply = useCallback(
    async (body: ExtractionApplyRequestDTO) => {
      if (projectId == null) return;
      setApplying(true);
      setError(null);
      try {
        setReport(await api.applyExtraction(projectId, body));
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setApplying(false);
      }
    },
    [api, projectId],
  );
  // undo the last apply via its provenance receipt
  const revert = useCallback(async () => {
    if (projectId == null || !report?.receipt) return;
    setReverting(true);
    setError(null);
    try {
      await api.revertExtraction(projectId, report.receipt);
      setReport(null);
      setProposals(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setReverting(false);
    }
  }, [api, projectId, report]);
  return { propose, apply, revert, proposals, report, running, applying, reverting, error, progress };
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
