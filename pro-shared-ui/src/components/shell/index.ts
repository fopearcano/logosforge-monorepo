/**
 * The Studio workspace shell (design Ticket 01) — implemented from the Claude
 * Design handoff `Workspace Shell.dc.html`. <WorkspaceShell> is the dockable
 * cinematic chrome; the chrome bars + Navigator are reusable; the three dock
 * regions are faithful, slot-swappable defaults until the dedicated panel
 * handoffs (T02 manuscript, T03 spatial, T06 project-OS) are implemented.
 */
export * from "./WorkspaceShell";
export * from "./PanelShell";
export * from "./Navigator";
export * from "./Chrome";
export * from "./regions";
export * from "./shellVars";
