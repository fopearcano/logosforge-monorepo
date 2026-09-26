/**
 * Manuscript & Structure (design Ticket 02) — implemented from the Claude Design
 * handoff page. Five standalone panels (each carries the design's data-screen-
 * label, uses var(--accent), wraps in <PanelShell>): the rich Manuscript Editor
 * + editing-intelligence HUD, the Story Grid corkboard, the Outline accordion,
 * the scene-derived Structure spine, the Notes grid, and imported Comments.
 */
export * from "./ManuscriptEditor";
export * from "./StoryGrid";
export * from "./OutlinePanel";
export * from "./StructurePanel";
export * from "./NotesPanel";
export * from "./CommentsPanel";
export * from "./commentAnchors";
export * from "./commentAssistant";
export * from "./commentPreferences";
export * from "./TitleCommentInput";
export * from "./titleCommentHighlights";
export * from "./Breakdowns";
