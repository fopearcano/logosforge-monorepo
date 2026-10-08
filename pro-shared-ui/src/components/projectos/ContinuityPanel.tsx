import { useCallback, useEffect, useId, useRef, useState, type CSSProperties, type RefCallback } from "react";
import type { ContinuityCommandDTO, ContinuityIssueDTO, ContinuityReportDTO } from "@logosforge/ui-contracts";
import type { ApiClient } from "../../adapters/api";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useContinuity } from "../../hooks";
import {
  useContinuityTarget,
  useNavigate,
  useStudio,
} from "../../adapters/StudioProvider";
import { STUDIO_AI_COMPANIONS_PANEL_ID } from "../../workspace/panelCatalog";
import { flushPendingProjectSaves } from "../../adapters/projectSaveCoordinator";
import { ApiRequestError, ApiRequestTimeoutError } from "../../adapters/httpApiClient";
import { ModalPortal } from "../common/ModalPortal";
import { useModalDialog } from "../common/useModalDialog";
import {
  buildContinuityRepairBrief,
  createContinuityIdempotencyKey,
  describeContinuityAction,
  planContinuityCommand,
  type ContinuityReviewAction,
} from "./continuityTransactions";

const panelBox: CSSProperties = {
  position: "relative",
  width: "100%",
  height: "100%",
  background: "linear-gradient(180deg,var(--panel),var(--base))",
  border: "1px solid var(--line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)",
  overflow: "hidden",
  display: "flex",
};

/** Severity → row palette (blocking→red, warning→amber, suggestion→cyan, info→muted). */
const SEV: Record<string, { color: string; border: string; bg: string }> = {
  blocking: { color: "var(--blocking)", border: "rgba(255,82,96,.35)", bg: "rgba(255,82,96,.04)" },
  warning: { color: "var(--warning)", border: "var(--line2)", bg: "var(--tint)" },
  suggestion: { color: "var(--cyan)", border: "var(--line2)", bg: "var(--tint)" },
  info: { color: "var(--txt3)", border: "var(--line2)", bg: "var(--tint)" },
};
const sevOf = (s: string) => SEV[s] ?? SEV.info!;

/** Confidence → short badge label. */
const CONF: Record<string, string> = { confirmed: "CONFIRMED", likely: "LIKELY", possible: "POSSIBLE", unknown: "UNKNOWN" };
const confOf = (c: string) => CONF[c] ?? c.toUpperCase();

/** Dimension swatch colors for the breakdown legend / radial. */
const DIM_COLORS = ["var(--blocking)", "var(--warning)", "var(--cyan)", "var(--green)", "var(--accent)", "var(--txt2)"];

type RecoveryMode = "none" | "resend" | "receipt";

interface ContinuityReviewProposal {
  ownerApi: ApiClient;
  ownerProjectId: number;
  issue: ContinuityIssueDTO;
  action: ContinuityReviewAction;
  idempotencyKey: string;
  command: ContinuityCommandDTO | null;
  recoveryMode: RecoveryMode;
}

const modalBackdrop: CSSProperties = {
  position: "fixed", inset: 0, zIndex: 1000, display: "grid", placeItems: "center",
  background: "rgba(2,3,6,.7)", backdropFilter: "blur(2px)", padding: 24,
};
const modalBox: CSSProperties = {
  width: "min(620px,94vw)", maxHeight: "84vh", display: "flex", flexDirection: "column",
  background: "linear-gradient(180deg,var(--raised),var(--panel2))",
  border: "1px solid var(--line-cy)", boxShadow: "0 30px 90px rgba(0,0,0,.8)",
  color: "var(--txt)", fontFamily: "'JetBrains Mono',monospace",
};

function ContinuityReviewDialog({
  proposal,
  busy,
  error,
  status,
  onConfirm,
  onClose,
}: {
  proposal: ContinuityReviewProposal;
  busy: boolean;
  error: string;
  status: string;
  onConfirm: () => void;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const titleId = useId();
  const descriptionId = useId();
  useModalDialog({ open: true, dialogRef, onClose, canClose: !busy });
  const action = describeContinuityAction(proposal.action);
  const confirmLabel = proposal.recoveryMode === "receipt"
    ? "CHECK RECEIPT"
    : proposal.recoveryMode === "resend"
      ? "RETRY EXACT COMMAND"
      : "CONFIRM DECISION";
  return (
    <ModalPortal>
      <div data-lf-modal-layer style={modalBackdrop} onClick={(event) => { if (!busy && event.target === event.currentTarget) onClose(); }}>
        <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={descriptionId} aria-busy={busy} tabIndex={-1} style={modalBox}>
          <div style={{ padding: "13px 16px", borderBottom: "1px solid var(--line)", display: "flex", alignItems: "center", gap: 10 }}>
            <span id={titleId} style={{ fontFamily: "'Chakra Petch',sans-serif", fontWeight: 600, fontSize: 14, letterSpacing: ".08em", color: "var(--strong)" }}>REVIEW CONTINUITY</span>
            <span style={{ fontSize: 8, color: "var(--cyan)", border: "1px solid var(--line-cy)", padding: "2px 7px", letterSpacing: ".1em" }}>{proposal.action.replace("_issue", "").toUpperCase()}</span>
            <div style={{ flex: 1 }} />
            <button type="button" disabled={busy} onClick={onClose} aria-label="Close" style={{ border: 0, background: "transparent", color: "var(--txt3)", fontSize: 14, cursor: busy ? "default" : "pointer" }}>✕</button>
          </div>
          <div id={descriptionId} style={{ padding: "14px 16px", overflowY: "auto", lineHeight: 1.55 }}>
            <div style={{ color: "var(--strong)", fontSize: 12, marginBottom: 8 }}>{proposal.issue.title}</div>
            {proposal.issue.explanation ? <div style={{ color: "var(--txt2)", fontSize: 10, marginBottom: 9 }}>{proposal.issue.explanation}</div> : null}
            {proposal.issue.suggested_action ? <div style={{ borderLeft: "2px solid var(--cyan)", padding: "5px 9px", background: "var(--tint)", color: "var(--txt2)", fontSize: 9.5 }}>Suggested repair · {proposal.issue.suggested_action}</div> : null}
            <div style={{ marginTop: 12, color: "var(--txt3)", fontSize: 8.5 }}>
              This records a review decision to {action}. It does not edit manuscript text or run AI. A fresh report and revision are checked before the command is committed.
            </div>
            {status ? <div role="status" style={{ marginTop: 10, color: "var(--cyan)", fontSize: 9 }}>{status}</div> : null}
            {error ? <div role="alert" style={{ marginTop: 10, color: "var(--blocking)", fontSize: 9, lineHeight: 1.45 }}>⚠ {error}</div> : null}
          </div>
          <div style={{ padding: "11px 16px", borderTop: "1px solid var(--line)", display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 8, color: "var(--txt3)" }}>durable receipt · exact-key recovery</span>
            <div style={{ flex: 1 }} />
            <button type="button" disabled={busy} onClick={onClose} style={{ border: "1px solid var(--line2)", background: "transparent", color: "var(--txt2)", padding: "7px 12px", font: "inherit", fontSize: 9, cursor: busy ? "default" : "pointer" }}>CANCEL</button>
            <button type="button" disabled={busy} onClick={onConfirm} style={{ border: 0, background: "var(--accent)", color: "var(--on-accent)", padding: "8px 14px", font: "inherit", fontSize: 9, fontWeight: 700, cursor: busy ? "default" : "pointer", opacity: busy ? .55 : 1 }}>{busy ? "WORKING…" : confirmLabel}</button>
          </div>
        </div>
      </div>
    </ModalPortal>
  );
}

function GroupHead({ label, counts, mt = 0 }: { label: string; counts: { n: string; color: string }[]; mt?: number }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 9, margin: `${mt}px 0 8px` }}>
      <span style={{ fontSize: 9, letterSpacing: ".14em", color: "var(--txt2)" }}>{label}</span>
      {counts.map((c, i) => <span key={i} style={{ fontSize: 7.5, color: c.color }}>{c.n}</span>)}
      <span style={{ flex: 1, height: 1, background: "var(--line2)" }} />
    </div>
  );
}

function IssueCard({ issue, focused, register, onScene, onReview, onRepair, locked }: {
  issue: ContinuityIssueDTO;
  focused: boolean;
  register: RefCallback<HTMLDivElement>;
  onScene: (sceneId: number) => void;
  onReview: (action: ContinuityReviewAction, issue: ContinuityIssueDTO, trigger: HTMLButtonElement) => void;
  onRepair: (issue: ContinuityIssueDTO, sceneId: number | null) => void;
  locked: boolean;
}) {
  const sev = sevOf(issue.severity);
  const blocking = issue.severity === "blocking";
  return (
    <div
      ref={register}
      tabIndex={-1}
      data-continuity-issue-id={issue.id}
      style={{
        border: `1px solid ${focused ? "var(--cyan)" : sev.border}`,
        background: focused ? "var(--tint2)" : sev.bg,
        boxShadow: focused ? "0 0 0 1px var(--line-cy), 0 0 18px rgba(80,210,220,.12)" : undefined,
        padding: "9px 11px",
        marginBottom: 7,
        outline: "none",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
        {blocking
          ? <span style={{ width: 9, height: 9, background: sev.color, display: "inline-grid", placeItems: "center", color: "var(--strong)", fontSize: 6 }}>!</span>
          : <span style={{ width: 8, height: 8, transform: "rotate(45deg)", background: sev.color }} />}
        <span style={{ fontSize: 8, letterSpacing: ".12em", color: sev.color }}>{issue.severity.toUpperCase()} · {issue.issue_type}</span>
        <span style={{ fontSize: 7.5, color: "var(--txt3)" }}>conf {confOf(issue.confidence)}</span>
      </div>
      <div style={{ fontSize: 10.5, color: blocking ? "var(--strong)" : "var(--txt)", lineHeight: 1.4, marginBottom: issue.explanation ? 4 : 6 }}>{issue.title}</div>
      {issue.explanation
        ? <div style={{ fontSize: 9, color: "var(--txt2)", lineHeight: 1.45, marginBottom: 6 }}>{issue.explanation}</div>
        : null}
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
        {issue.related_scene_ids.map((id) => (
          <button
            key={id}
            type="button"
            onClick={() => onScene(id)}
            aria-label={`Open scene ${id} for continuity issue`}
            style={{ font: "inherit", fontSize: 7.5, color: "var(--cyan)", background: "transparent", border: "1px solid var(--line2)", padding: "1px 5px", cursor: "pointer" }}
          >SC.{id}</button>
        ))}
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 7.5, letterSpacing: ".1em", color: "var(--txt3)" }}>{issue.status.toUpperCase()}</span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 5, flexWrap: "wrap", marginTop: 7, paddingTop: 7, borderTop: "1px solid var(--line2)" }}>
        {issue.status === "open" ? ([
          ["defer_issue", "DEFER"],
          ["dismiss_issue", "DISMISS"],
          ["resolve_issue", "RESOLVE"],
        ] as const).map(([action, label]) => (
          <button
            key={action}
            type="button"
            disabled={locked}
            onClick={(event) => onReview(action, issue, event.currentTarget)}
            style={{ font: "inherit", fontSize: 7.5, color: action === "resolve_issue" ? "var(--green)" : "var(--txt2)", background: "transparent", border: "1px solid var(--line2)", padding: "2px 6px", cursor: locked ? "default" : "pointer", opacity: locked ? .5 : 1 }}
          >{label}</button>
        )) : null}
        <div style={{ flex: 1 }} />
        {issue.related_scene_ids.length === 0 ? (
          <button type="button" disabled={locked} onClick={() => onRepair(issue, null)} style={{ font: "inherit", fontSize: 7.5, color: "var(--cyan)", background: "transparent", border: "1px solid var(--line-cy)", padding: "2px 6px", cursor: locked ? "default" : "pointer", opacity: locked ? .5 : 1 }}>ASK BILLY TO PLAN REPAIR</button>
        ) : issue.related_scene_ids.map((sceneId) => (
          <button key={sceneId} type="button" disabled={locked} onClick={() => onRepair(issue, sceneId)} style={{ font: "inherit", fontSize: 7.5, color: "var(--cyan)", background: "transparent", border: "1px solid var(--line-cy)", padding: "2px 6px", cursor: locked ? "default" : "pointer", opacity: locked ? .5 : 1 }}>REPAIR SC.{sceneId}</button>
        ))}
      </div>
    </div>
  );
}

const message = (text: string) => (
  <div style={{ padding: "34px 0", textAlign: "center", fontSize: 11, color: "var(--txt3)", letterSpacing: ".04em" }}>{text}</div>
);

/** Group issues by dimension, preserving first-seen order. */
function byDimension(issues: ContinuityIssueDTO[]): { dimension: string; items: ContinuityIssueDTO[] }[] {
  const order: string[] = [];
  const map = new Map<string, ContinuityIssueDTO[]>();
  for (const it of issues) {
    let bucket = map.get(it.dimension);
    if (!bucket) {
      bucket = [];
      map.set(it.dimension, bucket);
      order.push(it.dimension);
    }
    bucket.push(it);
  }
  return order.map((dimension) => ({ dimension, items: map.get(dimension) ?? [] }));
}

/** Per-group severity tally → the chip row next to the group head. */
function groupCounts(items: ContinuityIssueDTO[]): { n: string; color: string }[] {
  const tally: Record<string, number> = {};
  for (const it of items) tally[it.severity] = (tally[it.severity] ?? 0) + 1;
  const out: { n: string; color: string }[] = [];
  for (const sev of ["blocking", "warning", "suggestion", "info"]) {
    const c = tally[sev] ?? 0;
    if (c > 0) out.push({ n: `${c} ${sev}${c > 1 ? "s" : ""}`, color: sevOf(sev).color });
  }
  return out;
}

export function ContinuityPanel(props: PanelProps) {
  const { api, projectId } = useStudio();
  const {
    data,
    loading,
    error,
    refetch,
    lastSettledRequest,
    lastSuccessfulRequest,
  } = useContinuity();
  const { issueKey: targetIssueKey, clear: clearContinuityTarget } = useContinuityTarget();
  const navigate = useNavigate();
  const issueRefs = useRef(new Map<string, HTMLDivElement>());
  const consumedTargetRef = useRef("");
  const targetRequestRef = useRef<{ token: string; requestId: number } | null>(null);
  const focusingTargetRef = useRef("");
  const exhaustedFocusTargetRef = useRef("");
  const focusFrameRef = useRef<number | null>(null);
  const clearTargetRef = useRef(clearContinuityTarget);
  const renderedTargetToken = targetIssueKey ? `${projectId ?? ""}:${targetIssueKey}` : "";
  const renderedTargetTokenRef = useRef(renderedTargetToken);
  const [focusedIssueKey, setFocusedIssueKey] = useState<string | null>(null);
  const [targetNotice, setTargetNotice] = useState("");
  const [review, setReview] = useState<ContinuityReviewProposal | null>(null);
  const reviewRef = useRef<ContinuityReviewProposal | null>(null);
  const reviewTriggerRef = useRef<HTMLButtonElement | null>(null);
  const requestRef = useRef<object | null>(null);
  const mountedRef = useRef(true);
  const projectIdRef = useRef(projectId);
  const apiRef = useRef(api);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewError, setReviewError] = useState("");
  const [reviewStatus, setReviewStatus] = useState("");
  const [actionNotice, setActionNotice] = useState("");
  projectIdRef.current = projectId;
  apiRef.current = api;
  clearTargetRef.current = clearContinuityTarget;
  renderedTargetTokenRef.current = renderedTargetToken;
  const report: ContinuityReportDTO | undefined = data;
  const issues = report?.issues ?? [];
  const total = issues.length;
  const blockingCount = report?.blocking_count ?? 0;
  const warningCount = report?.warning_count ?? 0;
  const unavailable = report?.unavailable ?? [];

  const groups = byDimension(issues);

  const replaceReview = useCallback((next: ContinuityReviewProposal | null) => {
    reviewRef.current = next;
    setReview(next);
  }, []);

  const cancelIssueFocus = useCallback(() => {
    if (focusFrameRef.current != null && typeof window !== "undefined") {
      window.cancelAnimationFrame(focusFrameRef.current);
    }
    focusFrameRef.current = null;
    focusingTargetRef.current = "";
  }, []);

  const scheduleIssueFocus = useCallback((token: string, issueId: string, afterFocus: (focused: boolean) => void) => {
    cancelIssueFocus();
    if (typeof window === "undefined") {
      afterFocus(false);
      return;
    }
    focusingTargetRef.current = token;
    let remainingAttempts = 120;
    const attempt = () => {
      if (focusingTargetRef.current !== token || renderedTargetTokenRef.current !== token) return;
      if (remainingAttempts <= 0) {
        focusingTargetRef.current = "";
        afterFocus(false);
        return;
      }
      remainingAttempts -= 1;
      focusFrameRef.current = window.requestAnimationFrame(() => {
        focusFrameRef.current = null;
        if (focusingTargetRef.current !== token || renderedTargetTokenRef.current !== token) return;
        const node = issueRefs.current.get(issueId);
        if (!node) {
          attempt();
          return;
        }
        node.scrollIntoView?.({ block: "center", behavior: "smooth" });
        node.focus?.({ preventScroll: true });
        // Workspace commits and modal teardown can reclaim focus in the same
        // frame. Consume the one-shot target only when the issue card remains
        // active for a complete animation frame.
        focusFrameRef.current = window.requestAnimationFrame(() => {
          focusFrameRef.current = null;
          if (focusingTargetRef.current !== token || renderedTargetTokenRef.current !== token) return;
          if (node.ownerDocument.activeElement === node) {
            focusingTargetRef.current = "";
            afterFocus(true);
          } else {
            attempt();
          }
        });
      });
    };
    attempt();
  }, [cancelIssueFocus]);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => () => cancelIssueFocus(), [cancelIssueFocus]);

  useEffect(() => {
    cancelIssueFocus();
    consumedTargetRef.current = "";
    exhaustedFocusTargetRef.current = "";
    targetRequestRef.current = null;
    setFocusedIssueKey(null);
    setTargetNotice("");
    replaceReview(null);
    requestRef.current = null;
    reviewTriggerRef.current = null;
    setReviewBusy(false);
    setReviewError("");
    setReviewStatus("");
    setActionNotice("");
  }, [api, cancelIssueFocus, projectId, replaceReview]);

  useEffect(() => {
    if (!targetIssueKey) {
      cancelIssueFocus();
      consumedTargetRef.current = "";
      exhaustedFocusTargetRef.current = "";
      targetRequestRef.current = null;
      return;
    }
    const token = `${projectId ?? ""}:${targetIssueKey}`;
    if (consumedTargetRef.current === token) return;
    if (targetRequestRef.current?.token !== token) {
      cancelIssueFocus();
      exhaustedFocusTargetRef.current = "";
      targetRequestRef.current = { token, requestId: refetch() };
      setTargetNotice("");
      return;
    }
    const { requestId } = targetRequestRef.current;
    if (lastSuccessfulRequest < requestId) {
      if (loading || lastSettledRequest < requestId) return;
      consumedTargetRef.current = token;
      setFocusedIssueKey(null);
      setTargetNotice(
        `Continuity could not refresh this issue safely${error ? ` — ${error}` : ""}. Open it again to retry.`,
      );
      clearTargetRef.current();
      return;
    }
    if (!report) return;
    const issue = issues.find((candidate) => candidate.id === targetIssueKey);
    if (!issue) {
      consumedTargetRef.current = token;
      setFocusedIssueKey(null);
      setTargetNotice(
        "This continuity issue is no longer present in the current report. It may have been resolved or changed.",
      );
      clearTargetRef.current();
      return;
    }
    if (focusingTargetRef.current === token || exhaustedFocusTargetRef.current === token) return;
    setTargetNotice("");
    setFocusedIssueKey(issue.id);
    scheduleIssueFocus(token, issue.id, (focused) => {
      if (!focused) {
        exhaustedFocusTargetRef.current = token;
        setTargetNotice(
          "Continuity opened this issue, but its card could not retain focus. Open it again to retry.",
        );
        return;
      }
      exhaustedFocusTargetRef.current = "";
      consumedTargetRef.current = token;
      clearTargetRef.current();
    });
  }, [
    cancelIssueFocus,
    error,
    issues,
    lastSettledRequest,
    lastSuccessfulRequest,
    loading,
    projectId,
    refetch,
    report,
    scheduleIssueFocus,
    targetIssueKey,
  ]);

  const beginReview = useCallback(async (
    action: ContinuityReviewAction,
    issue: ContinuityIssueDTO,
    trigger: HTMLButtonElement,
  ) => {
    if (projectId == null || reviewRef.current || requestRef.current) return;
    const ownerApi = api;
    const ownerProjectId = projectId;
    const token = {};
    requestRef.current = token;
    reviewTriggerRef.current = trigger;
    setReviewBusy(true);
    setReviewError("");
    setReviewStatus("");
    setActionNotice("Refreshing Continuity before opening the decision…");
    try {
      await flushPendingProjectSaves({ commitActiveField: true });
      if (
        !mountedRef.current
        || requestRef.current !== token
        || projectIdRef.current !== ownerProjectId
        || apiRef.current !== ownerApi
      ) return;
      ownerApi.invalidatePendingReads?.();
      const latest = await ownerApi.getContinuity(ownerProjectId);
      if (
        !mountedRef.current
        || requestRef.current !== token
        || projectIdRef.current !== ownerProjectId
        || apiRef.current !== ownerApi
      ) return;
      const planned = planContinuityCommand(latest, {
        kind: action,
        issueId: issue.id,
      });
      if (!planned.command) {
        setActionNotice(planned.error);
        refetch();
        reviewTriggerRef.current = null;
        return;
      }
      replaceReview({
        ownerApi,
        ownerProjectId,
        issue: planned.issue,
        action,
        idempotencyKey: createContinuityIdempotencyKey(),
        command: planned.command,
        recoveryMode: "none",
      });
      setActionNotice("");
    } catch (failure) {
      if (
        mountedRef.current
        && requestRef.current === token
        && projectIdRef.current === ownerProjectId
      ) {
        setActionNotice(`Couldn’t prepare the Continuity decision — ${failure instanceof Error ? failure.message : String(failure)}.`);
      }
    } finally {
      if (requestRef.current === token) {
        requestRef.current = null;
        if (mountedRef.current && projectIdRef.current === ownerProjectId) {
          setReviewBusy(false);
        }
      }
    }
  }, [api, projectId, refetch, replaceReview]);

  const closeReview = useCallback(() => {
    if (reviewBusy || requestRef.current) return;
    replaceReview(null);
    setReviewError("");
    setReviewStatus("");
    const trigger = reviewTriggerRef.current;
    reviewTriggerRef.current = null;
    trigger?.focus?.();
  }, [replaceReview, reviewBusy]);

  const runReview = useCallback(async () => {
    const initial = reviewRef.current;
    if (!initial?.command || requestRef.current) return;
    const ownerApi = initial.ownerApi;
    const ownerProjectId = initial.ownerProjectId;
    const token = {};
    requestRef.current = token;
    setReviewBusy(true);
    setReviewError("");
    const ownsRequest = () => mountedRef.current
      && requestRef.current === token
      && projectIdRef.current === ownerProjectId
      && apiRef.current === ownerApi;
    const ownsProposal = () => ownsRequest()
      && reviewRef.current?.idempotencyKey === initial.idempotencyKey;

    const finishFromReport = (_next: ContinuityReportDTO, message: string) => {
      if (!ownsRequest()) return;
      ownerApi.invalidatePendingReads?.();
      replaceReview(null);
      reviewTriggerRef.current = null;
      setReviewError("");
      setReviewStatus("");
      setActionNotice(message);
      refetch();
    };

    const recoverReceipt = async (): Promise<boolean> => {
      setReviewStatus("Checking the durable command receipt…");
      const receipt = await ownerApi.getContinuityCommandReceipt(
        ownerProjectId,
        initial.idempotencyKey,
        initial.command!,
      );
      if (!ownsProposal()) return true;
      ownerApi.invalidatePendingReads?.();
      const latest = await ownerApi.getContinuity(ownerProjectId);
      if (!ownsProposal()) return true;
      finishFromReport(
        latest,
        receipt.original_changed
          ? "Recovered the committed Continuity decision from its durable receipt."
          : "The durable receipt confirms the Continuity decision.",
      );
      return true;
    };

    try {
      if (initial.recoveryMode === "receipt") {
        try {
          await recoverReceipt();
        } catch (receiptFailure) {
          if (!ownsProposal()) return;
          setReviewStatus("");
          setReviewError(`The committed outcome is still unavailable — ${receiptFailure instanceof Error ? receiptFailure.message : String(receiptFailure)}. Check the same receipt again; do not create a new decision.`);
        }
        return;
      }

      const usedExactResend = initial.recoveryMode === "resend";
      if (usedExactResend) {
        replaceReview({ ...initial, recoveryMode: "receipt" });
      }
      setReviewStatus(
        usedExactResend
          ? "Retrying the exact command and Idempotency-Key once…"
          : `Saving the decision to ${describeContinuityAction(initial.action)}…`,
      );
      try {
        const result = await ownerApi.executeContinuityCommand(
          ownerProjectId,
          initial.command,
          initial.idempotencyKey,
        );
        if (!ownsProposal()) return;
        finishFromReport(
          result.continuity,
          result.replayed
            ? "Recovered the previously committed Continuity decision."
            : "Continuity review decision saved.",
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
            return;
          } catch (receiptFailure) {
            if (!ownsProposal()) return;
            const cleanMiss = receiptFailure instanceof ApiRequestError
              && receiptFailure.code === "continuity_receipt_not_found";
            const recoveryMode: RecoveryMode = cleanMiss && !usedExactResend
              ? "resend"
              : "receipt";
            replaceReview({ ...initial, recoveryMode });
            setReviewStatus("");
            setReviewError(
              recoveryMode === "resend"
                ? "No committed receipt is available. One retry may reuse this exact reviewed command and Idempotency-Key."
                : `The write outcome is not verified — ${receiptFailure instanceof Error ? receiptFailure.message : String(receiptFailure)}. Only receipt checks remain; do not create a new decision.`,
            );
            return;
          }
        }
        throw failure;
      }
    } catch (failure) {
      if (!ownsRequest()) return;
      const keyConflict = failure instanceof ApiRequestError
        && failure.code === "idempotency_key_conflict";
      const conflict = failure instanceof ApiRequestError
        && !keyConflict
        && (failure.code === "continuity_conflict" || failure.status === 409);
      const missing = failure instanceof ApiRequestError && failure.status === 404;
      const definiteClientFailure = failure instanceof ApiRequestError
        && failure.status >= 400
        && failure.status < 500
        && failure.status !== 408
        && failure.status !== 429;
      if (conflict || missing || keyConflict || definiteClientFailure) {
        replaceReview(null);
        reviewTriggerRef.current = null;
      }
      setReviewStatus("");
      const message = conflict
          ? "Continuity review state changed before this decision could be saved. The report was refreshed; review the issue again."
          : missing
            ? "That Continuity issue is no longer available. The report was refreshed."
            : keyConflict
              ? "This proposal key was already used for another decision. Review the issue again to create a new proposal."
              : definiteClientFailure
                ? `Core rejected the Continuity decision — ${failure.message}.`
                : `Couldn’t save the Continuity decision — ${failure instanceof Error ? failure.message : String(failure)}.`;
      setReviewError(message);
      if (conflict || missing || keyConflict || definiteClientFailure) {
        setActionNotice(message);
      }
      refetch();
    } finally {
      if (requestRef.current === token) {
        requestRef.current = null;
        if (mountedRef.current && projectIdRef.current === ownerProjectId) {
          setReviewBusy(false);
        }
      }
    }
  }, [refetch, replaceReview]);

  const handoffRepair = useCallback(async (
    issue: ContinuityIssueDTO,
    sceneId: number | null,
  ) => {
    if (projectId == null || reviewBusy || reviewRef.current) return;
    const ownerProjectId = projectId;
    const navigated = await Promise.resolve(navigate(STUDIO_AI_COMPANIONS_PANEL_ID, {
      aiTool: "Billy",
      ...(sceneId == null ? {} : { sceneId }),
      continuityRepair: {
        handoffId: createContinuityIdempotencyKey(),
        ownerProjectId: projectId,
        issueId: issue.id,
        sceneId,
        draft: buildContinuityRepairBrief(issue),
      },
    }));
    if (!mountedRef.current || projectIdRef.current !== ownerProjectId) return;
    if (navigated === false) {
      setActionNotice(
        "Billy did not receive the repair handoff because workspace navigation was stopped. Your manuscript and Billy draft are unchanged.",
      );
      return;
    }
    setActionNotice(
      sceneId == null
        ? "Sent Billy a repair-planning handoff. Nothing was sent or changed; any existing Billy draft is preserved for confirmation."
        : `Sent Billy a repair handoff for SC.${sceneId}. Any existing draft is preserved, and prose still requires Controlled Apply confirmation.`,
    );
  }, [navigate, projectId, reviewBusy]);

  // Issue-breakdown legend: count per dimension (derived from the grouping).
  const breakdown = groups.map((g, i) => ({
    dimension: g.dimension,
    count: g.items.length,
    color: DIM_COLORS[i % DIM_COLORS.length]!,
  }));
  // Radial wedges proportional to each dimension's share of total issues.
  let acc = 0;
  const stops = breakdown
    .map((b) => {
      const start = total > 0 ? (acc / total) * 100 : 0;
      acc += b.count;
      const end = total > 0 ? (acc / total) * 100 : 0;
      return `${b.color} ${start}% ${end}%`;
    })
    .join(",");
  const conic = stops ? `conic-gradient(${stops})` : "var(--line2)";

  // Most-affected scenes: frequency of each scene across all related_scene_ids.
  const sceneFreq = new Map<number, number>();
  for (const it of issues) for (const id of it.related_scene_ids) sceneFreq.set(id, (sceneFreq.get(id) ?? 0) + 1);
  const topScenes = [...sceneFreq.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10);
  const maxFreq = topScenes.reduce((m, [, c]) => Math.max(m, c), 0);

  return (
    <PanelShell {...props}>
      <div data-screen-label="Continuity Panel" style={panelBox}>
        <Corners />
        {/* issues by dimension */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", borderRight: "1px solid var(--line)", minWidth: 0 }}>
          <div style={{ height: 42, flex: "none", display: "flex", alignItems: "center", gap: 11, padding: "0 16px", borderBottom: "1px solid var(--line)" }}>
            <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".1em", color: "var(--strong)" }}>CONTINUITY</span>
            <span style={{ fontSize: 8, color: "var(--txt3)" }}>
              SCOPE · PROJECT · {total} finding{total === 1 ? "" : "s"}
              {blockingCount > 0 ? <> · <span style={{ color: "var(--blocking)" }}>{blockingCount} blocking</span></> : null}
              {warningCount > 0 ? <> · <span style={{ color: "var(--warning)" }}>{warningCount} warning</span></> : null}
            </span>
            <div style={{ flex: 1 }} /><span style={{ fontSize: 8, color: "var(--txt3)" }}>DIMENSION ▾ · SEVERITY ▾ · STATUS ▾</span>
          </div>
          <div style={{ flex: 1, overflowY: "auto", padding: "13px 16px" }}>
            {actionNotice ? (
              <div role="status" style={{ border: "1px solid var(--line-cy)", color: "var(--cyan)", background: "var(--tint)", padding: "8px 10px", marginBottom: 10, fontSize: 8.5, lineHeight: 1.4 }}>
                {actionNotice}
                <button type="button" onClick={() => setActionNotice("")} style={{ marginLeft: 8, border: "1px solid var(--line2)", background: "transparent", color: "var(--txt2)", font: "inherit", fontSize: 7.5, padding: "2px 5px", cursor: "pointer" }}>DISMISS</button>
              </div>
            ) : null}
            {targetNotice ? (
              <div role="status" style={{ border: "1px solid var(--warning)", color: "var(--warning)", background: "var(--tint)", padding: "8px 10px", marginBottom: 10, fontSize: 8.5, lineHeight: 1.4 }}>
                {targetNotice}
                <button type="button" onClick={() => setTargetNotice("")} style={{ marginLeft: 8, border: "1px solid var(--line2)", background: "transparent", color: "var(--txt2)", font: "inherit", fontSize: 7.5, padding: "2px 5px", cursor: "pointer" }}>SHOW CURRENT ISSUES</button>
              </div>
            ) : null}
            {loading
              ? message("Loading continuity report…")
              : error
                ? message(`Couldn't load continuity — ${error}`)
                : total === 0
                  ? message("No continuity issues found")
                  : groups.map((g, gi) => (
                    <div key={g.dimension}>
                      <GroupHead label={`▾ ${g.dimension.toUpperCase()}`} counts={groupCounts(g.items)} mt={gi === 0 ? 0 : 14} />
                      {g.items.map((issue) => (
                        <IssueCard
                          key={issue.id}
                          issue={issue}
                          focused={focusedIssueKey === issue.id}
                          register={(node) => {
                            if (node) issueRefs.current.set(issue.id, node);
                            else issueRefs.current.delete(issue.id);
                          }}
                          onScene={(sceneId) => navigate("Manuscript", { sceneId })}
                          onReview={(action, candidate, trigger) => { void beginReview(action, candidate, trigger); }}
                          onRepair={handoffRepair}
                          locked={reviewBusy || review != null}
                        />
                      ))}
                    </div>
                  ))}
            {unavailable.length > 0
              ? <div style={{ fontSize: 7.5, color: "var(--txt3)", marginTop: 12, letterSpacing: ".06em" }}>↳ deferred for {report?.writing_mode ?? "this mode"}: {unavailable.join(" · ")}</div>
              : null}
          </div>
        </div>

        {/* right: heat + radial breakdown */}
        <div style={{ width: 440, flex: "none", background: "var(--panel2)", display: "flex", flexDirection: "column", overflowY: "auto" }}>
          <div style={{ padding: "13px 14px", borderBottom: "1px solid var(--line2)" }}>
            <div style={{ fontSize: 8, letterSpacing: ".18em", color: "var(--txt3)", marginBottom: 9 }}>MOST-AFFECTED SCENES</div>
            {topScenes.length === 0
              ? <div style={{ fontSize: 8.5, color: "var(--txt3)" }}>No scene-linked issues.</div>
              : (
                <>
                  <div style={{ display: "flex", gap: 3, height: 30, alignItems: "flex-end" }}>
                    {topScenes.map(([id, count]) => {
                      const ratio = maxFreq > 0 ? count / maxFreq : 0;
                      const color = ratio >= 0.8 ? "var(--blocking)" : ratio >= 0.45 ? "var(--amber)" : "var(--green)";
                      return <div key={id} style={{ flex: 1, background: color, height: `${Math.max(12, Math.round(ratio * 100))}%` }} />;
                    })}
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 7, color: "var(--txt3)", marginTop: 3 }}>
                    <span>SC.{topScenes[0]![0]}</span>
                    <span>SC.{topScenes[topScenes.length - 1]![0]}</span>
                  </div>
                </>
              )}
          </div>
          <div style={{ padding: "13px 14px", borderBottom: "1px solid var(--line2)" }}>
            <div style={{ fontSize: 8, letterSpacing: ".18em", color: "var(--txt3)", marginBottom: 10 }}>ISSUES BY DIMENSION</div>
            {breakdown.length === 0
              ? <div style={{ fontSize: 8.5, color: "var(--txt3)" }}>No issues to chart.</div>
              : (
                <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                  <div style={{ position: "relative", width: 74, height: 74, borderRadius: "50%", background: conic }}>
                    <div style={{ position: "absolute", inset: 13, borderRadius: "50%", background: "var(--panel2)", display: "grid", placeItems: "center", fontFamily: "'Chakra Petch'", fontSize: 16, color: "var(--strong)" }}>{total}</div>
                  </div>
                  <div style={{ fontSize: 8.5, color: "var(--txt2)", lineHeight: 1.7 }}>
                    {breakdown.map((b) => (
                      <div key={b.dimension}><span style={{ color: b.color }}>●</span> {b.dimension} {b.count}</div>
                    ))}
                  </div>
                </div>
              )}
          </div>
        </div>
      </div>
      {review ? (
        <ContinuityReviewDialog
          proposal={review}
          busy={reviewBusy}
          error={reviewError}
          status={reviewStatus}
          onConfirm={() => { void runReview(); }}
          onClose={closeReview}
        />
      ) : null}
    </PanelShell>
  );
}
