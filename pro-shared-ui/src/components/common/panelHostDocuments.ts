const registeredDocuments = new Map<Document, number>();

export function getAmbientPanelDocument(): Document | null {
  return typeof document === "undefined" ? null : document;
}

export function getAmbientPanelWindow(): Window | null {
  return typeof window === "undefined" ? null : window;
}

/** Register a host document for non-React integrations and the save barrier. */
export function registerPanelHostDocument(ownerDocument: Document): () => void {
  registeredDocuments.set(ownerDocument, (registeredDocuments.get(ownerDocument) ?? 0) + 1);
  return () => {
    const remaining = (registeredDocuments.get(ownerDocument) ?? 1) - 1;
    if (remaining > 0) registeredDocuments.set(ownerDocument, remaining);
    else registeredDocuments.delete(ownerDocument);
  };
}

/** All currently mounted panel documents, including the ambient application document. */
export function getPanelHostDocuments(): readonly Document[] {
  const documents = new Set<Document>(registeredDocuments.keys());
  const fallback = getAmbientPanelDocument();
  if (fallback) documents.add(fallback);
  return [...documents];
}

/** Cross-realm-safe HTMLElement test. */
export function isPanelHostHTMLElement(value: unknown, ownerDocument: Document): value is HTMLElement {
  const ElementConstructor = ownerDocument.defaultView?.HTMLElement;
  if (ElementConstructor) return value instanceof ElementConstructor;
  return typeof HTMLElement !== "undefined" && value instanceof HTMLElement;
}

/** Cross-realm-safe Node test. */
export function isPanelHostNode(value: unknown, ownerDocument: Document): value is Node {
  const NodeConstructor = ownerDocument.defaultView?.Node;
  if (NodeConstructor) return value instanceof NodeConstructor;
  return typeof Node !== "undefined" && value instanceof Node;
}
