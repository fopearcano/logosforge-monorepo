/**
 * Workspace area (design Ticket 01) — now implemented for real from the Claude
 * Design handoff. The shell + chrome + Navigator + dock regions live in ./shell;
 * this file re-exports them so `WorkspaceShell`, `Navigator`, `CommandPalette`,
 * `ModeStrip`, and `PsykeConsole` keep their public names.
 */
export * from "./shell";
