import { useState } from "react";
import { PanelErrorBoundary } from "../src/components/common/PanelErrorBoundary";

function SyntheticPanel({ crash }: { crash: boolean }) {
  if (crash) throw new Error("Synthetic persistent panel failure");
  return <div id="error-harness-healthy" style={{ padding: 20, border: "1px solid #62d99a" }}>Panel rendered successfully.</div>;
}

/** Manual browser harness for local panel recovery (`?error-boundary-harness`). */
export function ErrorBoundaryHarness() {
  const [crash, setCrash] = useState(false);
  const [scope, setScope] = useState(0);

  return (
    <main style={{ minHeight: "100vh", padding: 40, color: "#e4e8ef", background: "#080b10", fontFamily: "sans-serif" }}>
      <h1>Error-boundary recovery harness</h1>
      <p>A synthetic child failure must replace only the panel and remain recoverable.</p>
      <button id="error-harness-trigger" type="button" onClick={() => setCrash(true)}>Trigger render failure</button>
      <button id="error-harness-scope" type="button" onClick={() => { setCrash(false); setScope((value) => value + 1); }} style={{ marginLeft: 12 }}>Change recovery scope</button>
      <div style={{ height: 360, marginTop: 20 }}>
        <PanelErrorBoundary name="Test panel" resetKey={scope} onReset={() => setCrash(false)}>
          <SyntheticPanel crash={crash} />
        </PanelErrorBoundary>
      </div>
    </main>
  );
}
