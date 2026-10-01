/** Result contract shared by dock actions that may wait for a save barrier. */
export type WorkspaceActionResult = void | boolean | Promise<void | boolean>;

export interface WorkspaceFocusCandidate {
  focus: (options?: { preventScroll?: boolean }) => void;
  /** DOM candidates expose these fields; structural test doubles may omit them. */
  readonly ownerDocument?: { readonly activeElement: unknown };
  readonly isConnected?: boolean;
}

export type WorkspaceFocusTarget = () => WorkspaceFocusCandidate | null | undefined;
export type WorkspaceFocusScheduler = (work: () => void) => void;

const WORKSPACE_FOCUS_ATTEMPTS = 3;

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
    if (!target) return;
    const attempt = (remaining: number) => {
      schedule(() => {
        const candidate = target();
        if (!candidate || candidate.isConnected === false) {
          if (remaining > 1) attempt(remaining - 1);
          return;
        }
        try {
          candidate.focus({ preventScroll: true });
        } catch {
          if (remaining > 1) attempt(remaining - 1);
          return;
        }
        // React may resolve the workspace action before it commits a newly
        // conditional target (restore tray, collapsed strip, navigator). A DOM
        // focus call that did not stick gets another bounded, re-queried frame.
        const ownerDocument = candidate.ownerDocument;
        if (ownerDocument && ownerDocument.activeElement !== candidate && remaining > 1) {
          attempt(remaining - 1);
        }
      });
    };
    attempt(WORKSPACE_FOCUS_ATTEMPTS);
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
