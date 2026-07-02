/**
 * AI & Quantum (design Ticket 05) — implemented from the Claude Design handoff
 * page (canvas mode, 4 frames). The four AI presences: the Quantum Outliner
 * (branching wavefunction showpiece), Billy (assistant + project chat), Logos
 * (contextual actions), and Counterpart (two-stance reflection, never edits).
 * Each is a standalone <PanelShell> panel with the design's data-screen-label and
 * a fixed per-frame --accent (violet for Quantum/Counterpart, cyan for Billy/Logos).
 */
export * from "./QuantumOutliner";
export * from "./AssistantDock";
export * from "./CounterpartPanel";
export * from "./Logos";
export * from "./ExtractionReview";
export * from "./FormatStructure";
