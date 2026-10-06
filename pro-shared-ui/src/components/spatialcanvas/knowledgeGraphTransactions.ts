import type {
  KnowledgeGraphCommandDTO,
  KnowledgeGraphEdgeDTO,
  KnowledgeGraphEdgeIdentityDTO,
  KnowledgeGraphReadDTO,
} from "@logosforge/ui-contracts";

export type KnowledgeGraphEdgeAction = KnowledgeGraphCommandDTO["kind"];

export interface KnowledgeGraphEdgeIntent extends KnowledgeGraphEdgeIdentityDTO {
  kind: KnowledgeGraphEdgeAction;
}

export type KnowledgeGraphCommandPlan =
  | { command: KnowledgeGraphCommandDTO; edge: KnowledgeGraphEdgeDTO; error?: never }
  | { command?: never; edge?: never; error: string };

export function knowledgeGraphEdgeIdentity(
  edge: KnowledgeGraphEdgeIdentityDTO,
): string {
  return [edge.source, edge.target, edge.edge_type].join("\u0000");
}

export function sameKnowledgeGraphEdge(
  left: KnowledgeGraphEdgeIdentityDTO,
  right: KnowledgeGraphEdgeIdentityDTO,
): boolean {
  return knowledgeGraphEdgeIdentity(left) === knowledgeGraphEdgeIdentity(right);
}

/**
 * Bind a reviewed semantic intent to one freshly read graph review revision.
 * Core repeats every check transactionally; this planner prevents a stale or
 * already-resolved edge from being submitted from an old inspector render.
 */
export function planKnowledgeGraphCommand(
  graph: KnowledgeGraphReadDTO,
  intent: KnowledgeGraphEdgeIntent,
): KnowledgeGraphCommandPlan {
  const collection = intent.kind === "unhide_edge" ? graph.hidden_edges : graph.edges;
  const edge = collection.find((candidate) => sameKnowledgeGraphEdge(candidate, intent));
  if (!edge) {
    return {
      error: intent.kind === "unhide_edge"
        ? "That hidden edge is no longer available to restore."
        : "That visible edge is no longer available for review.",
    };
  }

  if (intent.kind === "confirm_edge" && edge.is_user_confirmed) {
    return { error: "That edge is already user-confirmed." };
  }
  if (intent.kind === "confirm_edge" && !edge.is_inferred) {
    return { error: "Only inferred edges can be user-confirmed." };
  }
  if (intent.kind === "hide_edge" && (!edge.is_inferred || edge.is_user_confirmed)) {
    return { error: "Only visible, unconfirmed inferred edges can be hidden." };
  }
  if (intent.kind === "unhide_edge" && !edge.is_hidden) {
    return { error: "That edge is no longer hidden." };
  }
  if (intent.kind !== "unhide_edge" && edge.is_hidden) {
    return { error: "That edge is hidden; restore it before reviewing it again." };
  }

  return {
    edge,
    command: {
      kind: intent.kind,
      expected_revision: graph.revision,
      source: edge.source,
      target: edge.target,
      edge_type: edge.edge_type,
    },
  };
}

export function describeKnowledgeGraphAction(action: KnowledgeGraphEdgeAction): string {
  if (action === "confirm_edge") return "confirm this inferred edge";
  if (action === "hide_edge") return "hide this edge";
  return "restore this hidden edge";
}

let fallbackSequence = 0;

/** One capability key per reviewed proposal; retries must reuse this exact key. */
export function createKnowledgeGraphIdempotencyKey(): string {
  const randomUuid = globalThis.crypto?.randomUUID?.();
  if (randomUuid) return `kg-ui-${randomUuid}`;
  fallbackSequence += 1;
  return `kg-ui-${Date.now().toString(36)}-${fallbackSequence.toString(36)}-${Math.random().toString(36).slice(2, 14)}`;
}
