type DependencyList = readonly unknown[] | undefined;
type Cleanup = void | (() => void);

interface StateSlot<T = unknown> {
  kind: "state";
  value: T;
  set: (next: T | ((current: T) => T)) => void;
}

interface RefSlot<T = unknown> {
  kind: "ref";
  value: { current: T };
}

interface MemoSlot<T = unknown> {
  kind: "memo";
  value: T;
  deps: DependencyList;
}

interface EffectSlot {
  kind: "effect";
  deps: DependencyList;
  cleanup: Cleanup;
}

type HookSlot = StateSlot | RefSlot | MemoSlot | EffectSlot;

const slots: HookSlot[] = [];
let cursor = 0;
let pendingEffects: Array<{ index: number; effect: () => Cleanup }> = [];

function depsEqual(left: DependencyList, right: DependencyList): boolean {
  if (left === undefined || right === undefined || left.length !== right.length) return false;
  return left.every((value, index) => Object.is(value, right[index]));
}

export function beginHookRender(): void {
  cursor = 0;
}

export function flushHookEffects(): void {
  const effects = pendingEffects;
  pendingEffects = [];
  for (const pending of effects) {
    const slot = slots[pending.index];
    if (!slot || slot.kind !== "effect") throw new Error("Invalid fake effect slot");
    if (typeof slot.cleanup === "function") slot.cleanup();
    slot.cleanup = pending.effect();
  }
}

/** Simulate a concurrent render React abandons before committing its effects. */
export function discardHookEffects(): void {
  pendingEffects = [];
}

export function resetHookRuntime(): void {
  pendingEffects = [];
  for (const slot of slots) {
    if (slot.kind === "effect" && typeof slot.cleanup === "function") slot.cleanup();
  }
  slots.length = 0;
  cursor = 0;
}

export function useState<T>(initial: T | (() => T)): [T, StateSlot<T>["set"]] {
  const index = cursor;
  cursor += 1;
  let slot = slots[index] as StateSlot<T> | undefined;
  if (!slot) {
    const value = typeof initial === "function" ? (initial as () => T)() : initial;
    slot = {
      kind: "state",
      value,
      set: (next) => {
        const current = slots[index] as StateSlot<T>;
        current.value = typeof next === "function"
          ? (next as (value: T) => T)(current.value)
          : next;
      },
    };
    slots[index] = slot;
  }
  if (slot.kind !== "state") throw new Error("Fake hook order changed at useState");
  return [slot.value, slot.set];
}

export function useRef<T>(initial?: T): { current: T } {
  const index = cursor;
  cursor += 1;
  let slot = slots[index] as RefSlot<T> | undefined;
  if (!slot) {
    slot = { kind: "ref", value: { current: initial as T } };
    slots[index] = slot;
  }
  if (slot.kind !== "ref") throw new Error("Fake hook order changed at useRef");
  return slot.value;
}

export function useMemo<T>(factory: () => T, deps: DependencyList): T {
  const index = cursor;
  cursor += 1;
  let slot = slots[index] as MemoSlot<T> | undefined;
  if (!slot || slot.kind !== "memo" || !depsEqual(slot.deps, deps)) {
    slot = { kind: "memo", value: factory(), deps };
    slots[index] = slot;
  }
  return slot.value;
}

export function useCallback<T extends (...args: never[]) => unknown>(callback: T, deps: DependencyList): T {
  return useMemo(() => callback, deps);
}

export function useEffect(effect: () => Cleanup, deps?: DependencyList): void {
  const index = cursor;
  cursor += 1;
  const slot = slots[index] as EffectSlot | undefined;
  if (!slot) {
    slots[index] = { kind: "effect", deps, cleanup: undefined };
    pendingEffects.push({ index, effect });
    return;
  }
  if (slot.kind !== "effect") throw new Error("Fake hook order changed at useEffect");
  if (depsEqual(slot.deps, deps)) return;
  slot.deps = deps;
  pendingEffects.push({ index, effect });
}

export const useLayoutEffect = useEffect;
