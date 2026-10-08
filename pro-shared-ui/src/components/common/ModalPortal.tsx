import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import { useWritingMode } from "../../adapters/StudioProvider";
import { resolveMode, shellSkinVars } from "../shell/shellVars";
import { useSkin } from "../shell/SkinContext";
import { usePanelHostDocument } from "./PanelHost";

/** Render modal content beside the application root so that root can be inert. */
export function ModalPortal({ children }: { children: ReactNode }) {
  const mode = resolveMode(useWritingMode());
  const skin = useSkin();
  const ownerDocument = usePanelHostDocument();
  if (!ownerDocument?.body) return <>{children}</>;
  return createPortal(
    <div className="lf-shell lf-modal-portal" data-skin={skin} style={{ display: "contents", ...shellSkinVars(mode, skin) }}>
      {children}
    </div>,
    ownerDocument.body,
  );
}
