import type {
  ContinuityCommandDTO,
  ContinuityIssueDTO,
  ContinuityReportDTO,
} from "@logosforge/ui-contracts";

export type ContinuityReviewAction = ContinuityCommandDTO["kind"];

export interface ContinuityReviewIntent {
  kind: ContinuityReviewAction;
  issueId: string;
}

export type ContinuityCommandPlan =
  | { command: ContinuityCommandDTO; issue: ContinuityIssueDTO; error?: never }
  | { command?: never; issue?: never; error: string };

/** Bind one still-open issue to the freshest persisted review revision. */
export function planContinuityCommand(
  report: ContinuityReportDTO,
  intent: ContinuityReviewIntent,
): ContinuityCommandPlan {
  const issue = report.issues.find((candidate) => candidate.id === intent.issueId);
  if (!issue) return { error: "That Continuity issue is no longer present." };
  if (issue.status !== "open") {
    return { error: `That Continuity issue is already ${issue.status}.` };
  }
  return {
    issue,
    command: {
      kind: intent.kind,
      expected_revision: report.review_revision,
      issue_id: issue.id,
      expected_issue_fingerprint: issue.review_fingerprint,
    },
  };
}

export function describeContinuityAction(action: ContinuityReviewAction): string {
  if (action === "defer_issue") return "defer this issue";
  if (action === "dismiss_issue") return "dismiss this issue";
  return "mark this issue resolved";
}

let fallbackSequence = 0;

/** One capability key per confirmed proposal; every retry reuses it exactly. */
export function createContinuityIdempotencyKey(): string {
  const randomUuid = globalThis.crypto?.randomUUID?.();
  if (randomUuid) return `continuity-ui-${randomUuid}`;
  fallbackSequence += 1;
  return `continuity-ui-${Date.now().toString(36)}-${fallbackSequence.toString(36)}-${Math.random().toString(36).slice(2, 14)}`;
}

/** A bounded, explicit brief for Billy; sending remains a separate user action. */
export function buildContinuityRepairBrief(issue: ContinuityIssueDTO): string {
  const scenes = issue.related_scene_ids.length > 0
    ? `Related scene${issue.related_scene_ids.length === 1 ? "" : "s"}: ${issue.related_scene_ids.map((id) => `SC.${id}`).join(", ")}.`
    : "No scene is linked directly; help me identify the safest repair target first.";
  return [
    "Help me repair this Semantic Continuity issue. Do not alter the manuscript automatically; propose replacement prose or precise edits for review through Controlled Apply.",
    `Issue: ${issue.title}`,
    issue.explanation ? `Evidence: ${issue.explanation}` : "",
    issue.suggested_action ? `Suggested direction: ${issue.suggested_action}` : "",
    scenes,
  ].filter(Boolean).join("\n\n").slice(0, 4000);
}
