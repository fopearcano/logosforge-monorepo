import { useRef, useState } from "react";
import { ModalPortal } from "../src/components/common/ModalPortal";
import { useModalDialog } from "../src/components/common/useModalDialog";

/** Manual browser harness for the modal keyboard contract (`?modal-harness`). */
export function ModalDialogHarness() {
  const [open, setOpen] = useState(false);
  const [childOpen, setChildOpen] = useState(false);
  const [backgroundActivations, setBackgroundActivations] = useState(0);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const childDialogRef = useRef<HTMLDivElement | null>(null);

  useModalDialog({ open, dialogRef, onClose: () => setOpen(false) });
  useModalDialog({ open: childOpen, dialogRef: childDialogRef, onClose: () => setChildOpen(false) });

  return (
    <main style={{ minHeight: "100vh", padding: 40, color: "#e4e8ef", background: "#080b10", fontFamily: "sans-serif" }}>
      <h1>Modal keyboard harness</h1>
      <p>Open the dialog, cycle with Tab/Shift+Tab, then press Escape.</p>
      <button id="modal-harness-origin" type="button" onClick={() => setOpen(true)}>Open test dialog</button>
      <button id="modal-harness-background" type="button" onClick={() => setBackgroundActivations((value) => value + 1)} style={{ marginLeft: 12 }}>
        Background action ({backgroundActivations})
      </button>

      {open && (
        <ModalPortal>
          <div data-lf-modal-layer style={{ position: "fixed", inset: 0, display: "grid", placeItems: "center", background: "rgba(0,0,0,.72)" }}>
            <div ref={dialogRef} id="modal-harness-dialog" role="dialog" aria-modal="true" aria-labelledby="modal-harness-title" tabIndex={-1} style={{ width: 360, padding: 24, border: "1px solid #4cc2ff", background: "#11151e", color: "#e4e8ef" }}>
              <h2 id="modal-harness-title">Focus trap test</h2>
              <button id="modal-harness-first" type="button">First action</button>
              <button id="modal-harness-child-open" type="button" onClick={() => setChildOpen(true)} style={{ marginLeft: 12 }}>Open child dialog</button>
              <button id="modal-harness-last" type="button" onClick={() => setOpen(false)} style={{ marginLeft: 12 }}>Close dialog</button>
            </div>
          </div>
        </ModalPortal>
      )}

      {childOpen && (
        <ModalPortal>
          <div data-lf-modal-layer style={{ position: "fixed", inset: 0, zIndex: 2, display: "grid", placeItems: "center", background: "rgba(0,0,0,.78)" }}>
            <div ref={childDialogRef} id="modal-harness-child" role="dialog" aria-modal="true" aria-labelledby="modal-harness-child-title" tabIndex={-1} style={{ width: 360, padding: 24, border: "1px solid #b07cff", background: "#171120", color: "#e4e8ef" }}>
              <h2 id="modal-harness-child-title">Nested focus trap test</h2>
              <button id="modal-harness-child-unmount-parent" type="button" onClick={() => setOpen(false)}>Unmount parent first</button>
              <button id="modal-harness-child-close" type="button" onClick={() => setChildOpen(false)} style={{ marginLeft: 12 }}>Close child</button>
            </div>
          </div>
        </ModalPortal>
      )}
    </main>
  );
}
