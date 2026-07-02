/**
 * Bridge between the title-bar toggle buttons (in the App shell) and the
 * LittleBoy AI agents — Billy (hovering chat) + Logos (inline) — which live in
 * LittleBoyProvider, mounted deep with the editor in WhiteboardPage.
 *
 * The provider registers its toggle fns and publishes its open state; the
 * title-bar reads the state via useSyncExternalStore and requests toggles. A
 * tiny module-level store keeps the two far-apart parts in sync without lifting
 * the editor up to App.
 */

export interface LittleBoyOpenState {
  billyOpen: boolean;
  logosOpen: boolean;
}

let openState: LittleBoyOpenState = { billyOpen: false, logosOpen: false };
const subs = new Set<() => void>();
let toggles: { billy: () => void; logos: () => void } | null = null;

export function getLittleBoyOpenState(): LittleBoyOpenState {
  return openState;
}

export function subscribeLittleBoyOpenState(cb: () => void): () => void {
  subs.add(cb);
  return () => {
    subs.delete(cb);
  };
}

/** Called by LittleBoyProvider whenever Billy/Logos opens or closes. */
export function publishLittleBoyOpenState(next: LittleBoyOpenState): void {
  if (next.billyOpen === openState.billyOpen && next.logosOpen === openState.logosOpen) return;
  openState = next;
  subs.forEach((cb) => cb());
}

/** Called by LittleBoyProvider on mount; returns an unregister fn. */
export function registerLittleBoyToggles(t: { billy: () => void; logos: () => void }): () => void {
  toggles = t;
  return () => {
    if (toggles === t) {
      toggles = null;
      publishLittleBoyOpenState({ billyOpen: false, logosOpen: false });
    }
  };
}

export function toggleBilly(): void {
  toggles?.billy();
}
export function toggleLogos(): void {
  toggles?.logos();
}
