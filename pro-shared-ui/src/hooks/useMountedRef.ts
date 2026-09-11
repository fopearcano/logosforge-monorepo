import { useEffect, useRef, type MutableRefObject } from "react";

/**
 * True only while the current React mount is active. Re-opens during Strict
 * Mode's setup → cleanup → setup probe instead of remaining permanently false.
 */
export function useMountedRef(): MutableRefObject<boolean> {
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  return mounted;
}
