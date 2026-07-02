/**
 * Project OS (design Ticket 06 / §4.9) — implemented from the Claude Design
 * handoff page (canvas mode, 5 frames). The deterministic
 * Understand→Decide→Act→Verify→Apply core: the universal Diff/Impact Confirm
 * modal, mission-control dashboard, Decision Radar, Guided Workflow Stepper, and
 * Continuity Panel. Each is a standalone <PanelShell> panel with the design's
 * data-screen-label + var(--accent).
 */
export * from "./DiffConfirmModal";
export * from "./NarrativeDashboard";
export * from "./DecisionRadar";
export * from "./GuidedWorkflowStepper";
export * from "./ContinuityPanel";
