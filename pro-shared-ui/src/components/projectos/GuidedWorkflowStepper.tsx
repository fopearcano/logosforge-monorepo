import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import type {
  WorkflowCommandDTO,
  WorkflowEventDTO,
  WorkflowRunDTO,
  WorkflowStepDTO,
  WorkflowStepKind,
  WorkflowTemplateDTO,
} from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import {
  useWorkflowEvents,
  useWorkflowRecommendations,
  useWorkflowRun,
  useWorkflowTemplates,
  useWorkflows,
} from "../../hooks";
import { useNavigate, useStudio } from "../../adapters/StudioProvider";
import { STUDIO_AI_COMPANIONS_PANEL_ID } from "../../workspace/panelCatalog";
import { ApiRequestError, ApiRequestTimeoutError } from "../../adapters/httpApiClient";
import {
  boundedWorkflowEvents,
  createWorkflowIdempotencyKey,
  planWorkflowCommand,
  planWorkflowStart,
  validateRecoveredWorkflowRun,
  workflowNoChangeMessage,
  workflowSectionPanelId,
  type WorkflowRunIntent,
} from "./guidedWorkflowTransactions";

const EVENT_LIMIT = 40;

type WorkflowRecoveryMode = "none" | "resend" | "receipt";

interface WorkflowCommandProposal {
  command: WorkflowCommandDTO;
  idempotencyKey: string;
  recoveryMode: WorkflowRecoveryMode;
}

const panelBox: CSSProperties = {
  position: "relative",
  width: "100%",
  height: "100%",
  minHeight: 420,
  background: "linear-gradient(180deg,var(--panel),var(--base))",
  border: "1px solid var(--line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)",
  overflow: "hidden",
  display: "flex",
};

const textButton: CSSProperties = {
  font: "inherit",
  fontSize: 8,
  letterSpacing: ".06em",
  color: "var(--txt2)",
  background: "transparent",
  border: "1px solid var(--line2)",
  padding: "4px 8px",
};

const message = (copy: string) => (
  <div style={{ padding: "24px 12px", textAlign: "center", fontSize: 9, lineHeight: 1.55, color: "var(--txt3)" }}>{copy}</div>
);

const statusColor = (status: string): string => {
  if (status === "completed") return "var(--green)";
  if (status === "cancelled" || status === "blocked") return "var(--blocking)";
  if (status === "paused") return "var(--warning)";
  return "var(--cyan)";
};

const kindLabel = (kind: WorkflowStepKind): string => {
  if (kind === "check") return "CHECK · DETERMINISTIC";
  if (kind === "creative") return "CREATIVE · YOUR JUDGEMENT";
  return "MANUAL · ACKNOWLEDGE";
};

function StepDot({ step, current }: { step: WorkflowStepDTO; current: boolean }) {
  const done = step.status === "completed" || step.status === "skipped";
  const color = done
    ? "var(--green)"
    : step.status === "blocked"
      ? "var(--blocking)"
      : current
        ? "var(--accent)"
        : "var(--txt3)";
  const glyph = step.status === "completed"
    ? "✓"
    : step.status === "skipped"
      ? "↷"
      : step.status === "blocked"
        ? "!"
        : step.kind === "check"
          ? "◇"
          : step.kind === "creative"
            ? "✎"
            : "○";
  return (
    <span style={{
      position: "relative", zIndex: 1, width: 20, height: 20, flex: "none",
      borderRadius: "50%", display: "grid", placeItems: "center", fontSize: 9,
      color: done || current ? "var(--on-accent)" : color,
      background: done ? "var(--green)" : current ? "var(--accent)" : "var(--raised)",
      border: `1px solid ${color}`,
      boxShadow: current ? "0 0 12px var(--accent)" : undefined,
    }}>{glyph}</span>
  );
}

function RunCard({ run, selected, onSelect }: {
  run: WorkflowRunDTO;
  selected: boolean;
  onSelect: () => void;
}) {
  const progress = run.total_steps > 0 ? Math.round((run.completed_steps / run.total_steps) * 100) : 0;
  return (
    <button
      type="button"
      data-workflow-run-id={run.id}
      aria-pressed={selected}
      onClick={onSelect}
      style={{
        width: "100%", textAlign: "left", font: "inherit", cursor: "pointer",
        border: `1px solid ${selected ? "var(--line-cy)" : "var(--line2)"}`,
        background: selected ? "rgba(76,194,255,.07)" : "var(--tint)", padding: "9px 10px",
      }}
    >
      <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 5 }}>
        <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 10, color: selected ? "var(--strong)" : "var(--txt2)" }}>{run.title}</span>
        <span style={{ fontSize: 7, color: statusColor(run.status), letterSpacing: ".08em" }}>{run.status.toUpperCase()}</span>
      </div>
      <div style={{ height: 4, background: "var(--tint2)" }}>
        <div style={{ width: `${progress}%`, height: "100%", background: selected ? "var(--accent)" : "var(--txt3)" }} />
      </div>
      <div style={{ fontSize: 7.5, color: "var(--txt3)", marginTop: 4 }}>{run.completed_steps}/{run.total_steps} · {progress}%</div>
    </button>
  );
}

function TemplateCard({ template, recommended, busy, alreadyRunning, onStart }: {
  template: WorkflowTemplateDTO;
  recommended: boolean;
  busy: boolean;
  alreadyRunning: boolean;
  onStart: () => void;
}) {
  return (
    <div data-workflow-template-id={template.id} style={{ border: `1px solid ${recommended ? "var(--line-cy)" : "var(--line2)"}`, padding: "7px 8px", background: recommended ? "rgba(76,194,255,.04)" : "transparent" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{ flex: 1, minWidth: 0, fontSize: 9, color: "var(--txt2)" }}>{template.title}</span>
        <span style={{ fontSize: 7, color: "var(--txt3)" }}>{template.steps.length} STEPS</span>
      </div>
      <div style={{ marginTop: 3, fontSize: 7.5, lineHeight: 1.4, color: "var(--txt3)" }}>{template.description}</div>
      <button type="button" disabled={busy || alreadyRunning} onClick={onStart} aria-label={`Start workflow ${template.title}`} style={{ ...textButton, marginTop: 6, color: alreadyRunning ? "var(--txt3)" : "var(--cyan)", borderColor: alreadyRunning ? "var(--line2)" : "var(--line-cy)", cursor: busy || alreadyRunning ? "default" : "pointer", opacity: busy ? .5 : 1 }}>{alreadyRunning ? "RUNNING" : "START"}</button>
    </div>
  );
}

function EventLog({ events, loading, error }: {
  events: readonly WorkflowEventDTO[];
  loading: boolean;
  error: string | null;
}) {
  if (loading && events.length === 0) return message("Loading quest log…");
  if (error && events.length === 0) return message(`Quest log unavailable — ${error}`);
  if (events.length === 0) return message("No workflow events yet");
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 8.5, color: "var(--txt2)" }}>
      {boundedWorkflowEvents(events, EVENT_LIMIT).map((event) => {
        const time = new Date(event.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        return (
          <div key={event.id} data-workflow-event-id={event.id} style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
            <span style={{ color: "var(--txt3)" }}>{time}</span>
            <span style={{ color: event.event_type.includes("completed") ? "var(--green)" : "var(--cyan)" }}>●</span>
            <span style={{ flex: 1 }}>{event.message || event.event_type.replaceAll("_", " ")}</span>
          </div>
        );
      })}
    </div>
  );
}

export function GuidedWorkflowStepper(props: PanelProps) {
  const { api, projectId } = useStudio();
  const navigate = useNavigate();
  const runsResource = useWorkflows();
  const templatesResource = useWorkflowTemplates();
  const recommendationsResource = useWorkflowRecommendations();
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const runResource = useWorkflowRun(selectedRunId);
  const eventsResource = useWorkflowEvents(selectedRunId, EVENT_LIMIT);
  const [optimisticRun, setOptimisticRun] = useState<WorkflowRunDTO | null>(null);
  const [optimisticBarrier, setOptimisticBarrier] = useState<{ runId: number; requestId: number | null } | null>(null);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const mountedRef = useRef(true);
  const projectIdRef = useRef(projectId);
  const apiRef = useRef(api);
  const [recovery, setRecovery] = useState<WorkflowCommandProposal | null>(null);
  const recoveryRef = useRef<WorkflowCommandProposal | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [cancelArmed, setCancelArmed] = useState(false);
  projectIdRef.current = projectId;
  apiRef.current = api;

  const runs = runsResource.data ?? [];
  const templates = templatesResource.data ?? [];
  const recommendations = recommendationsResource.data ?? [];

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    setSelectedRunId(null);
    setOptimisticRun(null);
    setOptimisticBarrier(null);
    recoveryRef.current = null;
    setRecovery(null);
    setError("");
    setNotice("");
    setCancelArmed(false);
    busyRef.current = false;
    setBusy(false);
  }, [api, projectId]);

  useEffect(() => {
    if (runs.length === 0) {
      setSelectedRunId(null);
      return;
    }
    if (selectedRunId != null && runs.some((run) => run.id === selectedRunId)) return;
    const preferred = runs.find((run) => run.status === "active")
      ?? runs.find((run) => run.status === "paused" || run.status === "blocked")
      ?? runs[0]!;
    setSelectedRunId(preferred.id);
  }, [runs, selectedRunId]);

  useEffect(() => {
    if (!optimisticRun || !optimisticBarrier || runResource.data?.id !== optimisticBarrier.runId) return;
    if (optimisticBarrier.requestId == null || runResource.lastSettledRequest >= optimisticBarrier.requestId) {
      setOptimisticRun(null);
      setOptimisticBarrier(null);
    }
  }, [optimisticBarrier, optimisticRun, runResource.data, runResource.lastSettledRequest]);

  const selectedFromList = runs.find((candidate) => candidate.id === selectedRunId);
  const run = optimisticRun?.id === selectedRunId
    ? optimisticRun
    : runResource.data ?? selectedFromList;
  const currentStep = run?.steps.find((step) => step.step_id === run.current_step_id) ?? null;
  const recommendedIds = useMemo(
    () => new Set(recommendations.map((item) => item.template_id)),
    [recommendations],
  );

  const refetchAll = useCallback((): number => {
    runsResource.refetch();
    const runRequestId = runResource.refetch();
    eventsResource.refetch();
    recommendationsResource.refetch();
    return runRequestId;
  }, [eventsResource, recommendationsResource, runResource, runsResource]);

  const replaceRecovery = useCallback((next: WorkflowCommandProposal | null) => {
    recoveryRef.current = next;
    setRecovery(next);
  }, []);

  const executeProposal = useCallback(async (proposal: WorkflowCommandProposal) => {
    if (projectId == null || busyRef.current) return;
    const ownerProjectId = projectId;
    const ownerApi = api;
    const ownsProposal = () => mountedRef.current
      && projectIdRef.current === ownerProjectId
      && apiRef.current === ownerApi
      && recoveryRef.current?.idempotencyKey === proposal.idempotencyKey;
    busyRef.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    setCancelArmed(false);

    const publishRun = (nextRun: WorkflowRunDTO, messageText: string) => {
      if (!ownsProposal()) return;
      replaceRecovery(null);
      setOptimisticRun(nextRun);
      const identityChanged = selectedRunId !== nextRun.id;
      setSelectedRunId(nextRun.id);
      setNotice(messageText);
      const requestId = refetchAll();
      setOptimisticBarrier({ runId: nextRun.id, requestId: identityChanged ? null : requestId });
    };

    const recoverReceipt = async (): Promise<void> => {
      setNotice("Checking the durable workflow command receipt…");
      const receipt = await ownerApi.getWorkflowCommandReceipt(
        ownerProjectId,
        proposal.idempotencyKey,
        proposal.command,
      );
      if (!ownsProposal()) return;
      ownerApi.invalidatePendingReads?.();
      const recoveredRun = await ownerApi.getWorkflowRun(ownerProjectId, receipt.original_run_id);
      if (!ownsProposal()) return;
      const mismatch = validateRecoveredWorkflowRun(recoveredRun, proposal.command, receipt);
      if (mismatch) throw new Error(mismatch);
      publishRun(
        recoveredRun,
        receipt.original_changed
          ? "Recovered the committed workflow command from its durable receipt."
          : "The durable receipt confirms the workflow was already up to date.",
      );
    };

    const retainAfterReceiptFailure = (receiptFailure: unknown, usedExactResend: boolean) => {
      if (!ownsProposal()) return;
      const cleanMiss = receiptFailure instanceof ApiRequestError
        && receiptFailure.code === "workflow_receipt_not_found";
      const recoveryMode: WorkflowRecoveryMode = cleanMiss && !usedExactResend
        ? "resend"
        : "receipt";
      replaceRecovery({ ...proposal, recoveryMode });
      setNotice("");
      setError(
        recoveryMode === "resend"
          ? "No committed receipt is available. One retry may reuse this exact command and Idempotency-Key."
          : `The workflow write is not yet verified — ${receiptFailure instanceof Error ? receiptFailure.message : String(receiptFailure)}. Only checks of this same receipt remain; no new command key will be created.`,
      );
      refetchAll();
    };

    try {
      if (proposal.recoveryMode === "receipt") {
        try {
          await recoverReceipt();
        } catch (receiptFailure) {
          retainAfterReceiptFailure(receiptFailure, true);
        }
        return;
      }

      const usedExactResend = proposal.recoveryMode === "resend";
      if (usedExactResend) {
        // Consume the single resend before dispatch so any ambiguous completion
        // leaves this capability receipt-only, even across a re-render.
        replaceRecovery({ ...proposal, recoveryMode: "receipt" });
      }
      setNotice(usedExactResend
        ? "Retrying the exact workflow command and Idempotency-Key once…"
        : "Updating workflow state…");
      try {
        const result = await ownerApi.executeWorkflowCommand(
          ownerProjectId,
          proposal.command,
          proposal.idempotencyKey,
        );
        if (!ownsProposal()) return;
        publishRun(
          result.workflow,
          result.replayed
            ? "Recovered the already committed workflow command."
            : result.changed
              ? "Workflow state updated."
              : workflowNoChangeMessage(proposal.command),
        );
      } catch (failure) {
        if (!ownsProposal()) return;
        const ambiguousTransport = failure instanceof ApiRequestTimeoutError
          ? failure.outcomeUnknown
          : failure instanceof ApiRequestError
            ? failure.status >= 500 || failure.status === 408 || failure.status === 429
            : true;
        if (ambiguousTransport) {
          try {
            await recoverReceipt();
          } catch (receiptFailure) {
            retainAfterReceiptFailure(receiptFailure, usedExactResend);
          }
          return;
        }
        throw failure;
      }
    } catch (failure) {
      if (!ownsProposal()) return;
      replaceRecovery(null);
      const keyConflict = failure instanceof ApiRequestError
        && failure.code === "idempotency_key_conflict";
      if (failure instanceof ApiRequestError && failure.status === 409 && !keyConflict) {
        setOptimisticRun(null);
        setOptimisticBarrier(null);
        setError("This workflow changed in another surface. Refreshed the authoritative run; review it before trying again.");
        refetchAll();
        return;
      }
      setError(keyConflict
        ? "This command key was already used for another workflow command. Review the authoritative run before creating a new command."
        : failure instanceof Error ? failure.message : String(failure));
      refetchAll();
    } finally {
      if (mountedRef.current && projectIdRef.current === ownerProjectId && apiRef.current === ownerApi) {
        busyRef.current = false;
        setBusy(false);
      }
    }
  }, [api, projectId, refetchAll, replaceRecovery, selectedRunId]);

  const execute = useCallback((command: WorkflowCommandDTO) => {
    if (projectId == null || busyRef.current) return;
    if (recoveryRef.current) {
      setError("Resolve the pending workflow command with its existing Idempotency-Key before starting another command.");
      return;
    }
    const proposal: WorkflowCommandProposal = {
      command,
      idempotencyKey: createWorkflowIdempotencyKey(),
      recoveryMode: "none",
    };
    replaceRecovery(proposal);
    void executeProposal(proposal);
  }, [executeProposal, projectId, replaceRecovery]);

  const continueRecovery = useCallback(() => {
    const proposal = recoveryRef.current;
    if (!proposal || proposal.recoveryMode === "none" || busyRef.current) return;
    void executeProposal(proposal);
  }, [executeProposal]);

  const executeIntent = useCallback((intent: WorkflowRunIntent) => {
    if (!run || busyRef.current) return;
    const planned = planWorkflowCommand(run, intent);
    if (!planned.command) {
      setError(planned.error);
      return;
    }
    void execute(planned.command);
  }, [execute, run]);

  const startTemplate = useCallback((template: WorkflowTemplateDTO) => {
    if (busyRef.current) return;
    void execute(planWorkflowStart(template.id));
  }, [execute]);

  const openStepSection = useCallback(async (step: WorkflowStepDTO) => {
    const panelId = workflowSectionPanelId(step.section_name);
    if (!panelId) {
      setError(step.section_name
        ? `No safe Studio destination is registered for “${step.section_name}”.`
        : "This step does not name a Studio destination.");
      return;
    }
    const options = step.target_type === "scene" && step.target_id != null
      ? { sceneId: step.target_id }
      : undefined;
    const opened = await Promise.resolve(navigate(panelId, options));
    if (!mountedRef.current) return;
    setNotice(opened === false
      ? `The workspace stopped the ${step.section_name} handoff; nothing changed.`
      : `Opened ${step.section_name}. Workflow state is unchanged.`);
  }, [navigate]);

  const handoffLogos = useCallback(async (step: WorkflowStepDTO) => {
    if (!step.action_id) return;
    const opened = await Promise.resolve(navigate(STUDIO_AI_COMPANIONS_PANEL_ID, { aiTool: "Logos" }));
    if (!mountedRef.current) return;
    setNotice(opened === false
      ? "The workspace stopped the Logos handoff. No action ran and nothing changed."
      : `Opened Logos for suggested action “${step.action_id}”. Review and run it there; nothing ran automatically.`);
  }, [navigate]);

  const events = eventsResource.data ?? [];
  const terminal = run?.status === "completed" || run?.status === "cancelled";
  const commandLocked = busy || recovery != null;
  const canAct = Boolean(run && run.status === "active" && !commandLocked);

  return (
    <PanelShell {...props}>
      <div data-screen-label="Guided Workflow Stepper" style={panelBox}>
        <Corners />
        <aside style={{ width: 278, flex: "none", borderRight: "1px solid var(--line)", background: "var(--panel2)", display: "flex", flexDirection: "column", minWidth: 0 }}>
          <div style={{ height: 38, display: "flex", alignItems: "center", padding: "0 13px", borderBottom: "1px solid var(--line2)", fontSize: 8.5, letterSpacing: ".18em", color: "var(--txt3)" }}>WORKFLOW RUNS · {runs.length}</div>
          <div style={{ padding: 10, display: "flex", flexDirection: "column", gap: 7, maxHeight: "32%", overflowY: "auto" }}>
            {runsResource.loading && runs.length === 0
              ? message("Loading workflow runs…")
              : runsResource.error && runs.length === 0
                ? message(`Couldn't load workflows — ${runsResource.error}`)
                : runs.length === 0
                  ? message("No workflow runs yet")
                  : runs.map((candidate) => (
                    <RunCard key={candidate.id} run={candidate} selected={candidate.id === selectedRunId} onSelect={() => { setSelectedRunId(candidate.id); setOptimisticRun(null); setCancelArmed(false); if (!recoveryRef.current) setError(""); }} />
                  ))}
          </div>
          <div style={{ padding: "6px 13px", fontSize: 8.5, letterSpacing: ".18em", color: "var(--txt3)", borderTop: "1px solid var(--line2)", borderBottom: "1px solid var(--line2)" }}>MODE-FILTERED TEMPLATES · {templates.length}</div>
          <div style={{ flex: 1, minHeight: 80, overflowY: "auto", padding: "7px 10px", display: "flex", flexDirection: "column", gap: 5 }}>
            {templatesResource.loading && templates.length === 0
              ? message("Loading templates…")
              : templatesResource.error && templates.length === 0
                ? message(`Couldn't load templates — ${templatesResource.error}`)
                : templates.map((template) => (
                  <TemplateCard
                    key={template.id}
                    template={template}
                    recommended={recommendedIds.has(template.id)}
                    busy={commandLocked}
                    alreadyRunning={runs.some((candidate) => candidate.template_id === template.id && ["active", "paused", "blocked"].includes(candidate.status))}
                    onStart={() => startTemplate(template)}
                  />
                ))}
          </div>
          <div style={{ borderTop: "1px solid var(--line-cy)", background: "rgba(76,194,255,.05)", padding: "9px 11px", minHeight: 46 }}>
            <div style={{ fontSize: 7.5, letterSpacing: ".14em", color: "var(--cyan)", marginBottom: 4 }}>RECOMMENDED NEXT</div>
            {recommendationsResource.loading && recommendations.length === 0
              ? <div style={{ fontSize: 8, color: "var(--txt3)" }}>Scanning Decision Radar…</div>
              : recommendations[0]
                ? <div style={{ fontSize: 9, lineHeight: 1.4, color: "var(--txt)" }}><strong>{recommendations[0].title}</strong> · {recommendations[0].reason}</div>
                : <div style={{ fontSize: 8, color: "var(--txt3)" }}>No recommendation right now.</div>}
          </div>
        </aside>

        <main style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
          <div style={{ minHeight: 44, flex: "none", display: "flex", alignItems: "center", gap: 8, padding: "0 14px", borderBottom: "1px solid var(--line)", flexWrap: "wrap" }}>
            <span style={{ fontFamily: "'Chakra Petch',sans-serif", fontWeight: 600, fontSize: 13, letterSpacing: ".1em", color: "var(--strong)" }}>{run?.title?.toUpperCase() ?? "GUIDED WORKFLOWS"}</span>
            {run ? <span style={{ fontSize: 8, color: statusColor(run.status), border: "1px solid var(--line2)", padding: "2px 6px", letterSpacing: ".1em" }}>{run.status.toUpperCase()}</span> : null}
            {run ? <span style={{ fontSize: 8, color: "var(--txt3)" }}>{run.writing_mode} · {run.completed_steps}/{run.total_steps}</span> : null}
            <div style={{ flex: 1 }} />
            {run?.status === "active" ? <button type="button" disabled={commandLocked} onClick={() => executeIntent({ kind: "pause" })} style={{ ...textButton, cursor: commandLocked ? "default" : "pointer" }}>PAUSE</button> : null}
            {run && (run.status === "paused" || run.status === "blocked") ? <button type="button" disabled={commandLocked} onClick={() => executeIntent({ kind: "resume" })} style={{ ...textButton, color: "var(--green)", cursor: commandLocked ? "default" : "pointer" }}>RESUME</button> : null}
            {run && !terminal ? <button type="button" disabled={commandLocked} onClick={() => { if (cancelArmed) executeIntent({ kind: "cancel" }); else setCancelArmed(true); }} style={{ ...textButton, color: cancelArmed ? "var(--blocking)" : "var(--txt3)", cursor: commandLocked ? "default" : "pointer" }}>{cancelArmed ? "CONFIRM CANCEL" : "CANCEL"}</button> : null}
          </div>

          {(notice || error || runsResource.error || runResource.error) ? (
            <div role={error ? "alert" : "status"} style={{ flex: "none", padding: "7px 13px", borderBottom: "1px solid var(--line2)", color: error ? "var(--blocking)" : "var(--cyan)", background: "var(--tint)", fontSize: 8.5, lineHeight: 1.45, display: "flex", alignItems: "center", gap: 9 }}>
              <span style={{ flex: 1 }}>{error || notice || runsResource.error || runResource.error}</span>
              {recovery && recovery.recoveryMode !== "none" ? (
                <button
                  type="button"
                  disabled={busy}
                  onClick={continueRecovery}
                  aria-label={recovery.recoveryMode === "resend" ? "Retry exact workflow command once" : "Check workflow command receipt"}
                  style={{ ...textButton, flex: "none", color: "var(--cyan)", borderColor: "var(--line-cy)", cursor: busy ? "default" : "pointer" }}
                >
                  {recovery.recoveryMode === "resend" ? "RETRY EXACT COMMAND ONCE" : "CHECK SAME RECEIPT"}
                </button>
              ) : null}
            </div>
          ) : null}

          <div style={{ flex: 1, overflowY: "auto", padding: "15px 18px", position: "relative" }}>
            {!run
              ? message(projectId == null ? "Open a project to use Guided Workflows." : "Start a mode-compatible workflow from the template gallery.")
              : (
                <>
                  <div style={{ position: "absolute", left: 32, top: 24, bottom: 30, width: 1, background: "var(--line2)" }} />
                  {run.steps.map((step) => {
                    const current = step.step_id === run.current_step_id;
                    const done = step.status === "completed" || step.status === "skipped";
                    const canMutateStep = canAct && current && step.status === "active";
                    return (
                      <div key={step.step_id} data-workflow-step-id={step.step_id} data-current={current || undefined} style={{ display: "flex", gap: 13, alignItems: "flex-start", marginBottom: 14, opacity: !current && !done ? .72 : 1 }}>
                        <StepDot step={step} current={current} />
                        <div style={{ flex: 1, minWidth: 0, border: current ? "1px solid var(--line-cy)" : "1px solid transparent", background: current ? "rgba(76,194,255,.06)" : "transparent", padding: current ? "9px 11px" : "1px 0" }}>
                          <div style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
                            <span style={{ fontSize: current ? 11.5 : 10.5, color: current ? "var(--strong)" : "var(--txt2)" }}>{step.title}</span>
                            <span style={{ fontSize: 7.5, color: step.kind === "check" ? "var(--green)" : step.kind === "creative" ? "var(--violet)" : "var(--txt3)", letterSpacing: ".08em" }}>{kindLabel(step.kind)}</span>
                          </div>
                          {step.description ? <div style={{ marginTop: 4, fontSize: 8.5, lineHeight: 1.45, color: "var(--txt3)" }}>{step.description}</div> : null}
                          {step.notes ? <div style={{ marginTop: 4, fontSize: 8, color: "var(--txt2)" }}>NOTE · {step.notes}</div> : null}
                          {(current || step.status === "blocked") && !terminal ? (
                            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
                              {step.section_name ? <button type="button" disabled={busy} onClick={() => { void openStepSection(step); }} aria-label={`Open ${step.section_name} for ${step.title}`} style={{ ...textButton, color: "var(--cyan)", borderColor: "var(--line-cy)", cursor: busy ? "default" : "pointer" }}>OPEN {step.section_name.toUpperCase()} ▸</button> : null}
                              {step.action_id ? <button type="button" disabled={busy} onClick={() => { void handoffLogos(step); }} aria-label={`Open Logos suggestion ${step.action_id}`} style={{ ...textButton, color: "var(--violet)", cursor: busy ? "default" : "pointer" }}>OPEN LOGOS SUGGESTION</button> : null}
                              <button type="button" disabled={!canMutateStep} onClick={() => executeIntent({ kind: "complete_step", stepId: step.step_id })} style={{ ...textButton, color: "var(--green)", cursor: canMutateStep ? "pointer" : "default", opacity: canMutateStep ? 1 : .5 }}>MARK COMPLETE</button>
                              <button type="button" disabled={!canMutateStep} onClick={() => executeIntent({ kind: "skip_step", stepId: step.step_id })} style={{ ...textButton, cursor: canMutateStep ? "pointer" : "default", opacity: canMutateStep ? 1 : .5 }}>SKIP</button>
                            </div>
                          ) : null}
                        </div>
                      </div>
                    );
                  })}
                </>
              )}
          </div>

          {run && !terminal ? (
            <div style={{ flex: "none", minHeight: 38, borderTop: "1px solid var(--line2)", display: "flex", alignItems: "center", gap: 7, padding: "6px 14px", background: "var(--panel2)" }}>
              <button type="button" disabled={!canAct} onClick={() => executeIntent({ kind: "refresh" })} style={{ ...textButton, color: "var(--green)", cursor: canAct ? "pointer" : "default", opacity: canAct ? 1 : .5 }}>{busy ? "WORKING…" : "VERIFY CHECKS"}</button>
              <button type="button" disabled={!canAct || !currentStep} onClick={() => executeIntent({ kind: "advance" })} style={{ ...textButton, cursor: canAct && currentStep ? "pointer" : "default", opacity: canAct && currentStep ? 1 : .5 }}>ADVANCE</button>
              <div style={{ flex: 1 }} />
              <span style={{ fontSize: 7.5, color: "var(--txt3)", letterSpacing: ".08em" }}>WORKFLOW STATE ONLY · CONTENT CHANGES STILL REQUIRE THEIR OWN REVIEW/APPLY</span>
            </div>
          ) : null}

          <div style={{ flex: "none", height: 108, borderTop: "1px solid var(--line)", padding: "8px 14px", background: "var(--panel2)", overflowY: "auto" }}>
            <div style={{ fontSize: 7.5, letterSpacing: ".18em", color: "var(--txt3)", marginBottom: 7 }}>EVENT TIMELINE · LAST {EVENT_LIMIT}</div>
            <EventLog events={events} loading={eventsResource.loading} error={eventsResource.error} />
          </div>
        </main>
      </div>
    </PanelShell>
  );
}
