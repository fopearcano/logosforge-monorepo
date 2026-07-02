/**
 * AI surfaces (design Ticket 05 + §4.9). Billy (assistant + project chat),
 * Logos (contextual actions), and Counterpart (reflection) come from the AI &
 * Quantum handoff (./aipanels). The Project-OS panels (Decision Radar, Guided
 * Workflow Stepper, the universal Diff/Impact Confirm modal, Continuity) come
 * from the Project OS handoff (./projectos).
 *
 * `ChatPanel` is an alias of `AssistantDock` — the Billy frame is the assistant
 * *and* the full project chat; there is no separate chat surface in the design.
 */
export { DecisionRadar, GuidedWorkflowStepper, DiffConfirmModal, ContinuityPanel } from "./projectos";
export { AssistantDock, AssistantDock as ChatPanel, CounterpartPanel, Logos, ExtractionReview, FormatStructure } from "./aipanels";
