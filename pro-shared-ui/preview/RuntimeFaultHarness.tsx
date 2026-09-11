import { RuntimeFaultBanner } from "../src/components/common/RuntimeFaultBanner";
import { markRuntimeFaultHandled } from "../src/components/common/runtimeFaults";
import { useRuntimeFaultReporter } from "../src/components/common/useRuntimeFaultReporter";

function dispatchRejection(reason: unknown): void {
  const event = new Event("unhandledrejection") as PromiseRejectionEvent;
  Object.defineProperty(event, "reason", { configurable: true, value: reason });
  window.dispatchEvent(event);
}

/** Manual browser harness for global runtime reporting (`?runtime-fault-harness`). */
export function RuntimeFaultHarness() {
  const { fault, dismiss } = useRuntimeFaultReporter();

  return (
    <main style={{ minHeight: "100vh", padding: 40, color: "#e4e8ef", background: "#080b10", fontFamily: "sans-serif" }}>
      <h1>Runtime fault reporter harness</h1>
      <p>Only genuine, uncontained failures should produce the global banner.</p>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        <button type="button" onClick={() => window.dispatchEvent(new ErrorEvent("error", { error: new Error("Synthetic window failure"), message: "Synthetic window failure" }))}>Dispatch window error</button>
        <button type="button" onClick={() => dispatchRejection(new Error("Synthetic promise failure"))}>Dispatch promise rejection</button>
        <button type="button" onClick={() => { const error = new Error("Synthetic cancellation"); error.name = "AbortError"; dispatchRejection(error); }}>Dispatch cancellation</button>
        <button type="button" onClick={() => { const error = new Error("Synthetic contained failure"); markRuntimeFaultHandled(error); window.dispatchEvent(new ErrorEvent("error", { error, message: error.message })); }}>Dispatch handled error</button>
      </div>
      <output id="runtime-fault-state" style={{ display: "block", marginTop: 20 }}>{fault ? `${fault.source}: ${fault.message}` : "No runtime fault"}</output>
      <RuntimeFaultBanner fault={fault} onDismiss={dismiss} />
    </main>
  );
}
