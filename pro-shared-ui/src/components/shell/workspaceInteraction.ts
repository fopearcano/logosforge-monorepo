/** Result contract shared by dock actions that may wait for a save barrier. */
export type WorkspaceActionResult = void | boolean | Promise<void | boolean>;

export type WorkspaceFocusTarget = () => { focus: () => void } | null | undefined;
export type WorkspaceFocusScheduler = (work: () => void) => void;

function animationFrame(work: () => void): void {
  requestAnimationFrame(work);
}

/**
 * Move focus only after an asynchronous workspace action has actually applied.
 * A rejected/declined action can restore the control that remains selected.
 */
export function focusAfterWorkspaceAction(
  result: WorkspaceActionResult,
  appliedTarget: WorkspaceFocusTarget,
  declinedTarget?: WorkspaceFocusTarget,
  schedule: WorkspaceFocusScheduler = animationFrame,
): void {
  const focus = (target: WorkspaceFocusTarget | undefined) => {
    if (target) schedule(() => target()?.focus());
  };
  void Promise.resolve(result).then(
    (applied) => focus(applied === false ? declinedTarget : appliedTarget),
    () => focus(declinedTarget),
  );
}

/**
 * Encode every code point at a fixed width so distinct valid panel registry IDs
 * can never collapse onto the same tab/tabpanel DOM ID.
 */
export function workspacePanelDomToken(panelId: string): string {
  return Array.from(panelId, (character) => (
    character.codePointAt(0)!.toString(16).padStart(6, "0")
  )).join("");
}
