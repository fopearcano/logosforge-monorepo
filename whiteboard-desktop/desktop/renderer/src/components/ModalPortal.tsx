import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';

/** Render modal content beside #root so the application tree can safely be inert. */
export function ModalPortal({ children }: { children: ReactNode }) {
  if (typeof document === 'undefined') return <>{children}</>;
  return createPortal(
    <div data-wb-modal-portal style={{ display: 'contents' }}>
      {children}
    </div>,
    document.body,
  );
}
