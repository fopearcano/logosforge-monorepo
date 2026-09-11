import { StrictMode, useEffect, useState } from "react";
import { useMountedRef } from "../src/hooks/useMountedRef";

function MountedProbe({ generation }: { generation: number }) {
  const mounted = useMountedRef();
  const [observed, setObserved] = useState<"pending" | "true" | "false">("pending");

  useEffect(() => {
    const timer = window.setTimeout(() => setObserved(mounted.current ? "true" : "false"), 30);
    return () => window.clearTimeout(timer);
  }, [generation, mounted]);

  return <output id="lifecycle-mounted-state">mounted after StrictMode probe: {observed}</output>;
}

/** Manual browser harness for StrictMode mount ownership (`?lifecycle-harness`). */
export function LifecycleHarness() {
  const [shown, setShown] = useState(true);
  const [generation, setGeneration] = useState(1);
  const toggle = () => {
    if (shown) setShown(false);
    else { setGeneration((value) => value + 1); setShown(true); }
  };

  return (
    <main style={{ minHeight: "100vh", padding: 40, color: "#e4e8ef", background: "#080b10", fontFamily: "sans-serif" }}>
      <h1>Lifecycle ownership harness</h1>
      <p>The mounted ref must be true after Strict Mode's setup → cleanup → setup probe.</p>
      <button type="button" onClick={toggle}>{shown ? "Unmount probe" : "Remount probe"}</button>
      <div style={{ marginTop: 20 }}>
        <StrictMode>{shown && <MountedProbe key={generation} generation={generation} />}</StrictMode>
      </div>
    </main>
  );
}
