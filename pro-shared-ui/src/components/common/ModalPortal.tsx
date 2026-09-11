import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import { useWritingMode } from "../../adapters/StudioProvider";
import { panelScopeVars, resolveMode } from "../shell/shellVars";

/** Render modal content beside the application root so that root can be inert. */
export function ModalPortal({ children }: { children: ReactNode }) {
  const mode = resolveMode(useWritingMode());
  if (typeof document === "undefined") return <>{children}</>;
  return createPortal(
    <div className="lf-shell lf-modal-portal" style={{ display: "contents", ...panelScopeVars(mode) }}>
      {children}
    </div>,
    document.body,
  );
}
