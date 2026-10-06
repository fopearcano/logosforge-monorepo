interface EditMenuBridge {
  onMenuEdit?(cb: (action: string) => void): () => void;
}

function bridge(): EditMenuBridge | undefined {
  if (typeof window === 'undefined') return undefined;
  return (window as unknown as { logosforge?: EditMenuBridge }).logosforge;
}

/** Subscribe to packaged-app Edit actions; a browser preview safely no-ops. */
export function onMenuEdit(cb: (action: string) => void): () => void {
  return bridge()?.onMenuEdit?.(cb) ?? (() => {});
}
