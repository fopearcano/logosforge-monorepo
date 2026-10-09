import { MessagePort } from "node:worker_threads";
import { act, create, type ReactTestInstance, type ReactTestRenderer } from "react-test-renderer";
import type { DecisionCardDTO, DecisionRadarDTO, EventMessage } from "@logosforge/ui-contracts";
import type { ApiClient } from "../src/adapters/api";
import type { PlatformAdapter } from "../src/adapters/platform";
import { StudioProvider, type StudioNavigationOptions } from "../src/adapters/StudioProvider";
import { DecisionRadar, mergeDecisionRadarCards } from "../src/components/projectos/DecisionRadar";
import { useDashboard, useKnowledgeGraph, useWorkflowRecommendations } from "../src/hooks/resources";

let assertions = 0;
function check(value: unknown, message: string): asserts value {
  assertions += 1;
  if (!value) throw new Error(message);
}

function text(node: ReactTestInstance): string {
  return node.children.map((child) => typeof child === "string" ? child : text(child)).join("");
}

const baseCard = (overrides: Partial<DecisionCardDTO>): DecisionCardDTO => ({
  id: "base",
  category: "structure",
  severity: "suggestion",
  confidence: "confirmed",
  title: "Base decision",
  explanation: "",
  suggested_action: "Open the source panel.",
  related_section: "Structure",
  related_target_type: "",
  related_target_id: null,
  related_target_key: "",
  created_from: "deterministic",
  graph_focus_key: "",
  graph_view_mode: null,
  graph_include_inferred: true,
  graph_depth: 1,
  evidence: [],
  evidence_total: 0,
  ...overrides,
});

const graphCard = baseCard({
  id: "kg_isolated_theme:psyke:6",
  category: "psyke",
  severity: "warning",
  confidence: "likely",
  title: "Theme 'Static' is isolated.",
  explanation: "No scene connection exists.",
  suggested_action: "Tie the theme to a scene.",
  related_section: "PSYKE",
  created_from: "knowledge_graph",
  graph_focus_key: "theme:psyke:6",
  graph_view_mode: "project_map",
  graph_include_inferred: true,
  graph_depth: 2,
  evidence: [{
    kind: "edge",
    label: "Static → Opening · expresses",
    detail: "The inferred link remains unconfirmed.",
    graph_focus_key: "scene:scene:2",
    source_key: "theme:psyke:6",
    target_key: "scene:scene:2",
    edge_type: "expresses",
    confidence: "likely",
    source_system: "manuscript",
    provenance: "scene text match",
    related_section: "",
    related_target_type: "",
    related_target_id: null,
    related_target_key: "",
  }],
  evidence_total: 3,
});

const continuityCard = baseCard({
  id: "continuity_0123456789abcdef",
  category: "continuity",
  severity: "blocking",
  confidence: "confirmed",
  title: "A setup link points to a missing scene.",
  explanation: "The linked payoff no longer exists.",
  suggested_action: "Review the broken setup/payoff link.",
  related_section: "Continuity",
  related_target_type: "continuity_issue",
  related_target_key: "0123456789abcdef",
  created_from: "semantic_continuity",
  evidence: [{
    kind: "continuity_issue",
    label: "A setup link points to a missing scene.",
    detail: "continuity gap · plot",
    graph_focus_key: "",
    source_key: "",
    target_key: "",
    edge_type: "",
    confidence: "confirmed",
    source_system: "semantic_continuity",
    provenance: "continuity:continuity_gap",
    related_section: "Continuity",
    related_target_type: "continuity_issue",
    related_target_id: null,
    related_target_key: "0123456789abcdef",
  }, {
    kind: "scene",
    label: "Opening",
    detail: "Scene #12 is explicitly related to this issue.",
    graph_focus_key: "",
    source_key: "",
    target_key: "",
    edge_type: "",
    confidence: "confirmed",
    source_system: "manuscript",
    provenance: "scene:12",
    related_section: "Manuscript",
    related_target_type: "scene",
    related_target_id: 12,
    related_target_key: "",
  }],
  evidence_total: 2,
});

const progressionCard = baseCard({
  id: "progression_unanchored_11",
  category: "progression",
  severity: "suggestion",
  confidence: "confirmed",
  title: "Mara's arc has an unanchored beat.",
  explanation: "One beat is not connected to the manuscript axis.",
  suggested_action: "Review the progression track.",
  related_section: "Progressions",
  related_target_type: "progression_track",
  related_target_id: 11,
  created_from: "knowledge_graph",
  graph_focus_key: "progression_track:progressions:11",
  graph_view_mode: "project_map",
  graph_include_inferred: true,
  graph_depth: 1,
  evidence: [{
    kind: "progression_beat",
    label: "She answers the signal.",
    detail: "Unanchored beat #21 in Mara's arc.",
    graph_focus_key: "progression_beat:progressions:21",
    source_key: "",
    target_key: "",
    edge_type: "",
    confidence: "confirmed",
    source_system: "progressions",
    provenance: "canonical progression beat",
    related_section: "Progressions",
    related_target_type: "progression_beat",
    related_target_id: 21,
    related_target_key: "",
  }],
  evidence_total: 1,
});

const response: DecisionRadarDTO = {
  project_id: 7,
  generated_light: false,
  summary_line: "Radar",
  radar: [
    baseCard({ id: "graph_isolated", severity: "opportunity", title: "Legacy isolation" }),
    baseCard({ id: "base-warning", severity: "warning", title: "Base warning" }),
    progressionCard,
  ],
  knowledge_graph_available: true,
  knowledge_graph_cards: [graphCard],
  continuity_available: true,
  continuity_cards: [continuityCard],
};

const merged = mergeDecisionRadarCards(response);
check(merged.map((card) => card.id).join(",") === "continuity_0123456789abcdef,base-warning,kg_isolated_theme:psyke:6,progression_unanchored_11", "canonical Graph, Continuity, and Progressions intelligence must share one severity-ranked Radar");
const capped = mergeDecisionRadarCards({
  ...response,
  radar: Array.from({ length: 10 }, (_, index) => baseCard({ id: `base-${index}`, severity: "info" })),
  knowledge_graph_cards: [graphCard],
});
check(capped.length === 10 && capped[0]?.id === continuityCard.id && capped[1]?.id === graphCard.id, "the merged Radar must preserve one global ten-card cap after severity ranking");

const navigation: Array<{ panel: string; options?: StudioNavigationOptions }> = [];
let decisionReads = 0;
let radarListener: ((event: EventMessage) => void) | undefined;
const api = {
  getDecisionRadar: async () => {
    decisionReads += 1;
    return response;
  },
  subscribe: (_projectId: number, listener: (event: EventMessage) => void) => {
    radarListener = listener;
    return () => { radarListener = undefined; };
  },
} as unknown as ApiClient;
const platform = { isDesktop: false } as PlatformAdapter;
let renderer!: ReactTestRenderer;
await act(async () => {
  renderer = create(
    <StudioProvider
      services={{ api, platform }}
      projectId={7}
      nav={{ navigate: (panel, options) => navigation.push({ panel, options }) }}
    >
      <DecisionRadar />
    </StudioProvider>,
  );
  for (let index = 0; index < 6; index += 1) await Promise.resolve();
});

check(text(renderer.root).includes("KNOWLEDGE GRAPH") && text(renderer.root).includes("GRAPH ONLINE"), "graph-origin cards and availability must be explicit");
check(text(renderer.root).includes("SEMANTIC CONTINUITY") && text(renderer.root).includes("CONTINUITY ONLINE"), "continuity-origin cards and availability must be explicit");
check(text(renderer.root).includes("PROGRESSIONS"), "canonical Progressions cards must expose an explicit origin badge alongside Graph provenance");
check(text(renderer.root).includes("TRACEABLE EVIDENCE · 1 OF 3"), "bounded evidence must disclose both returned and authoritative counts");
check(text(renderer.root).includes("PROVENANCE scene text match") && text(renderer.root).includes("SOURCE manuscript"), "evidence rows must expose source and provenance as text");

const openGraph = renderer.root.findAllByType("button").find((button) => text(button) === "OPEN GRAPH EVIDENCE");
check(openGraph, "graph cards must expose a distinct graph deep-link control");
act(() => openGraph.props.onClick());
check(
  navigation.at(-1)?.panel === "Graph"
    && navigation.at(-1)?.options?.graphFocusKey === "theme:psyke:6"
    && navigation.at(-1)?.options?.graphViewMode === "project_map"
    && navigation.at(-1)?.options?.graphIncludeInferred === true
    && navigation.at(-1)?.options?.graphDepth === 2,
  "the card deep link must preserve its exact public key, projection, evidence scope, and depth",
);

const focusEvidence = renderer.root.findByProps({ "aria-label": "Open evidence for Static → Opening · expresses" });
act(() => focusEvidence.props.onClick());
check(navigation.at(-1)?.options?.graphFocusKey === "scene:scene:2", "each evidence row must deep-link its own canonical focus key");

const openContinuity = renderer.root.findAllByType("button").find((button) => text(button) === "OPEN CONTINUITY ISSUE");
check(openContinuity, "continuity cards must expose an exact issue deep link");
act(() => openContinuity.props.onClick());
check(
  navigation.at(-1)?.panel === "Continuity"
    && navigation.at(-1)?.options?.continuityIssueKey === "0123456789abcdef",
  "continuity card navigation must preserve the canonical issue key",
);

const openSceneEvidence = renderer.root.findByProps({ "aria-label": "Open evidence for Opening" });
act(() => openSceneEvidence.props.onClick());
check(
  navigation.at(-1)?.panel === "Manuscript" && navigation.at(-1)?.options?.sceneId === 12,
  "continuity scene evidence must deep-link the exact manuscript scene",
);

const openProgression = renderer.root.findAllByType("button").find((button) => text(button) === "OPEN PROGRESSION");
check(openProgression, "Progressions cards must expose a distinct track deep link");
act(() => openProgression.props.onClick());
check(
  navigation.at(-1)?.panel === "Progressions"
    && navigation.at(-1)?.options?.progressionTrackId === 11,
  "Progressions card navigation must preserve the exact canonical track id",
);

const focusProgressionGraphEvidence = renderer.root.findByProps({ "aria-label": "Open evidence for She answers the signal." });
act(() => focusProgressionGraphEvidence.props.onClick());
check(
  navigation.at(-1)?.panel === "Graph"
    && navigation.at(-1)?.options?.graphFocusKey === "progression_beat:progressions:21",
  "Progressions evidence must preserve its exact Graph focus",
);

const openProgressionEvidence = renderer.root.findByProps({ "aria-label": "Open Progressions evidence for She answers the signal." });
act(() => openProgressionEvidence.props.onClick());
check(
  navigation.at(-1)?.panel === "Progressions"
    && navigation.at(-1)?.options?.progressionBeatId === 21,
  "Progressions evidence must deep-link the exact canonical beat id",
);

act(() => radarListener?.({ id: 1, event: "progressions_changed", project_id: 7, data: {}, ts: Date.now() }));
await act(async () => {
  await new Promise((resolve) => setTimeout(resolve, 140));
  await Promise.resolve();
});
check(decisionReads === 2, "progressions_changed must refresh Decision Radar cards");

act(() => renderer.unmount());

function ProgressionIntelligenceProbe() {
  useDashboard();
  useKnowledgeGraph();
  useWorkflowRecommendations();
  return <output>mounted</output>;
}

let dashboardReads = 0;
let graphReads = 0;
let recommendationReads = 0;
const intelligenceListeners = new Set<(event: EventMessage) => void>();
const intelligenceApi = {
  getDashboard: async () => { dashboardReads += 1; return {}; },
  getKnowledgeGraph: async () => { graphReads += 1; return {}; },
  getWorkflowRecommendations: async () => { recommendationReads += 1; return []; },
  subscribe: (_projectId: number, listener: (event: EventMessage) => void) => {
    intelligenceListeners.add(listener);
    return () => { intelligenceListeners.delete(listener); };
  },
} as unknown as ApiClient;
await act(async () => {
  renderer = create(
    <StudioProvider services={{ api: intelligenceApi, platform }} projectId={7}>
      <ProgressionIntelligenceProbe />
    </StudioProvider>,
  );
  await Promise.resolve();
});
check(
  dashboardReads === 1 && graphReads === 1 && recommendationReads === 1,
  "all Progressions-dependent intelligence resources must load once",
);
act(() => intelligenceListeners.forEach((listener) => listener({
  id: 2,
  event: "progressions_changed",
  project_id: 7,
  data: { track_id: 11 },
  ts: Date.now(),
})));
await act(async () => {
  await new Promise((resolve) => setTimeout(resolve, 140));
  await Promise.resolve();
});
check(
  dashboardReads === 2 && graphReads === 2 && recommendationReads === 2,
  "progressions_changed must refresh Dashboard, Graph, and graph-backed workflow recommendations",
);
act(() => renderer.unmount());
check(intelligenceListeners.size === 0, "Progressions-dependent intelligence subscriptions must be released on unmount");

console.log(`${assertions} Decision Radar assertions passed.`);

for (const handle of process._getActiveHandles()) {
  if (handle instanceof MessagePort) handle.unref();
}
