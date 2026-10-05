import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react';

import {
  clampFloatingPanelPosition,
  defaultFloatingPanelPosition,
  type FloatingPanelPosition,
} from './floatingPanelPosition';

interface Options {
  storageKey: string;
  width: number;
  defaultSide: 'left' | 'right';
  defaultTop?: number;
}

function viewport() {
  return {
    width: typeof window === 'undefined' ? 1280 : window.innerWidth,
    height: typeof window === 'undefined' ? 800 : window.innerHeight,
  };
}

function loadPosition(options: Options): FloatingPanelPosition {
  const fallback = defaultFloatingPanelPosition(
    options.width,
    viewport(),
    options.defaultSide,
    options.defaultTop,
  );
  try {
    const raw = localStorage.getItem(options.storageKey);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<FloatingPanelPosition>;
    if (typeof parsed.x !== 'number' || typeof parsed.y !== 'number') return fallback;
    return clampFloatingPanelPosition({ x: parsed.x, y: parsed.y }, options.width, viewport());
  } catch {
    return fallback;
  }
}

function savePosition(storageKey: string, position: FloatingPanelPosition) {
  try {
    localStorage.setItem(storageKey, JSON.stringify(position));
  } catch {
    /* ignore unavailable storage */
  }
}

/** Pointer + keyboard movement for compact non-modal tool windows. */
export function useFloatingPanel(options: Options) {
  const [position, setPosition] = useState<FloatingPanelPosition>(() => loadPosition(options));
  const [dragging, setDragging] = useState(false);
  const positionRef = useRef(position);
  const dragRef = useRef<{ pointerId: number; dx: number; dy: number } | null>(null);
  positionRef.current = position;

  const commit = useCallback(
    (next: FloatingPanelPosition) => {
      const clamped = clampFloatingPanelPosition(next, options.width, viewport());
      positionRef.current = clamped;
      setPosition(clamped);
      return clamped;
    },
    [options.width],
  );

  const onPointerDown = useCallback(
    (event: ReactPointerEvent<HTMLElement>) => {
      if (event.button !== 0) return;
      dragRef.current = {
        pointerId: event.pointerId,
        dx: event.clientX - positionRef.current.x,
        dy: event.clientY - positionRef.current.y,
      };
      setDragging(true);
      event.currentTarget.setPointerCapture?.(event.pointerId);
      event.preventDefault();
    },
    [],
  );

  const onKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLElement>) => {
      const delta = event.shiftKey ? 32 : 12;
      const movement: Record<string, FloatingPanelPosition> = {
        ArrowLeft: { x: -delta, y: 0 },
        ArrowRight: { x: delta, y: 0 },
        ArrowUp: { x: 0, y: -delta },
        ArrowDown: { x: 0, y: delta },
      };
      const move = movement[event.key];
      if (!move) return;
      event.preventDefault();
      const next = commit({ x: positionRef.current.x + move.x, y: positionRef.current.y + move.y });
      savePosition(options.storageKey, next);
    },
    [commit, options.storageKey],
  );

  useEffect(() => {
    const onMove = (event: PointerEvent) => {
      const drag = dragRef.current;
      if (!drag || event.pointerId !== drag.pointerId) return;
      commit({ x: event.clientX - drag.dx, y: event.clientY - drag.dy });
    };
    const onUp = (event: PointerEvent) => {
      const drag = dragRef.current;
      if (!drag || event.pointerId !== drag.pointerId) return;
      dragRef.current = null;
      setDragging(false);
      savePosition(options.storageKey, positionRef.current);
    };
    const onResize = () => {
      const next = commit(positionRef.current);
      savePosition(options.storageKey, next);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointercancel', onUp);
    window.addEventListener('resize', onResize);
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onUp);
      window.removeEventListener('resize', onResize);
    };
  }, [commit, options.storageKey]);

  return { position, dragging, onPointerDown, onKeyDown };
}
