/**
 * Manuscript & Structure (design Ticket 02) — implemented from the Claude Design
 * handoff page. Five standalone panels (each carries the design's data-screen-
 * label, uses var(--accent), wraps in <PanelShell>): the rich Manuscript Editor
 * + editing-intelligence HUD, the Story Grid corkboard, the Outline accordion,
 * the scene-derived Structure spine, and the Notes grid.
 */
export * from "./ManuscriptEditor";
export * from "./StoryGrid";
export * from "./OutlinePanel";
export * from "./StructurePanel";
export * from "./NotesPanel";
