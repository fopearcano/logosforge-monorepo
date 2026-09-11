/** Event-only bridge: API activity asks the mounted UI to consume recovery notices. */

const listeners = new Set<() => void>();

export function requestRecoveryNoticeCheck(): void {
  listeners.forEach((listener) => listener());
}

export function onRecoveryNoticeCheckRequested(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
