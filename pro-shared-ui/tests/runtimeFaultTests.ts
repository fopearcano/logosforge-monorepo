import {
  createRuntimeFault,
  isExpectedCancellation,
  markRuntimeFaultHandled,
  shouldReportRuntimeFault,
  wasRuntimeFaultHandled,
} from "../src/components/common/runtimeFaults";

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: boolean): void => {
  if (condition) passed += 1;
  else failures.push(label);
};

const ordinary = new Error("network exploded");
const fault = createRuntimeFault("promise", ordinary, 1000);
check("Error reason keeps its name", fault.name === "Error");
check("Error reason keeps its concise message", fault.message === "network exploded");
check("fault records its source and timestamp", fault.source === "promise" && fault.occurredAt === 1000);
check("fault details retain diagnostics", fault.details.includes("network exploded"));

const textFault = createRuntimeFault("event", "  broken\n click  ", 1100);
check("primitive reasons are normalized", textFault.message === "broken click");
check("fault identity is stable across sources", textFault.key === createRuntimeFault("promise", "broken click", 1200).key);

const cyclic: { self?: unknown } = {};
cyclic.self = cyclic;
check("cyclic reasons never break reporting", createRuntimeFault("event", cyclic).message.length > 0);

const abort = new Error("cancelled by navigation");
abort.name = "AbortError";
check("AbortError is an expected cancellation", isExpectedCancellation(abort));
check("ABORT_ERR code is an expected cancellation", isExpectedCancellation({ code: "ABORT_ERR" }));
check("an ordinary error mentioning abort is still reported", !isExpectedCancellation(new Error("request aborted unexpectedly")));

check("first occurrence is reportable", shouldReportRuntimeFault(null, fault));
check("same occurrence is deduplicated inside the window", !shouldReportRuntimeFault({ key: fault.key, occurredAt: 1000 }, { ...fault, occurredAt: 5999 }));
check("same occurrence returns after the window", shouldReportRuntimeFault({ key: fault.key, occurredAt: 1000 }, { ...fault, occurredAt: 6000 }));
check("different errors are never collapsed", shouldReportRuntimeFault({ key: fault.key, occurredAt: 1000 }, textFault));

check("uncaught objects start unmarked", !wasRuntimeFaultHandled(ordinary));
markRuntimeFaultHandled(ordinary);
check("boundary-caught objects are marked", wasRuntimeFaultHandled(ordinary));
check("primitive handled checks stay safe", !wasRuntimeFaultHandled("primitive"));

console.log(`Runtime fault tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} runtime-fault test(s) failed`);
console.log("RUNTIME FAULT TESTS: PASS");
