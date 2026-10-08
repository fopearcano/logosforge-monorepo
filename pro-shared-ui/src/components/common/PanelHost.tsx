import {
  createContext,
  useContext,
  useEffect,
  type ReactNode,
} from "react";
import {
  getAmbientPanelDocument,
  getAmbientPanelWindow,
  registerPanelHostDocument,
} from "./panelHostDocuments";

export {
  getPanelHostDocuments,
  isPanelHostHTMLElement,
  isPanelHostNode,
  registerPanelHostDocument,
} from "./panelHostDocuments";

/**
 * DOM realm used by a panel. React context follows a subtree through a portal,
 * while ambient `document`/`window` continue to point at the opener realm.
 */
const PanelHostDocumentContext = createContext<Document | null | undefined>(undefined);

export function PanelHostProvider({
  ownerDocument,
  children,
}: {
  ownerDocument: Document | null;
  children: ReactNode;
}) {
  useEffect(() => ownerDocument ? registerPanelHostDocument(ownerDocument) : undefined, [ownerDocument]);
  return (
    <PanelHostDocumentContext.Provider value={ownerDocument}>
      {children}
    </PanelHostDocumentContext.Provider>
  );
}

/** The document that physically contains the current panel subtree. */
export function usePanelHostDocument(): Document | null {
  const ownerDocument = useContext(PanelHostDocumentContext);
  return ownerDocument === undefined ? getAmbientPanelDocument() : ownerDocument;
}

/** The Window paired with the document that physically contains this panel. */
export function usePanelHostWindow(): Window | null {
  const ownerDocument = useContext(PanelHostDocumentContext);
  if (ownerDocument === null) return null;
  if (ownerDocument !== undefined) return ownerDocument.defaultView;
  return getAmbientPanelDocument()?.defaultView ?? getAmbientPanelWindow();
}
