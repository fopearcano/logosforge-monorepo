import fs from "node:fs";
import path from "node:path";

const read = (relative: string) => fs.readFileSync(path.join(process.cwd(), "src", relative), "utf8");
const failures: string[] = [];
const requireMarkers = (file: string, markers: string[]) => {
  const source = read(file);
  for (const marker of markers) if (!source.includes(marker)) failures.push(`${file} is missing ${marker}`);
  return source;
};

const quantum = requireMarkers("components/aipanels/QuantumOutliner.tsx", ["new ResizeObserver", "ro.disconnect()"]);
if ((quantum.match(/new ResizeObserver/g) ?? []).length !== (quantum.match(/ro\.disconnect\(\)/g) ?? []).length) {
  failures.push("QuantumOutliner ResizeObserver creation/cleanup count differs");
}
requireMarkers("components/formatpanels/VoiceHud.tsx", ["setInterval(", "clearInterval(", "recorder.current?.cancel()"]);
requireMarkers("components/formatpanels/mic.ts", ["if (closed) return", "track.stop()", "ctx.close().catch", "catch (error)", "cleanup();"]);
requireMarkers("components/common/RuntimeFaultBanner.tsx", ["focusTimerRef", "window.clearTimeout(focusTimerRef.current)"]);
requireMarkers("components/common/useModalDialog.ts", ["window.clearTimeout(focusTimer)", "removeEventListener(\"keydown\"", "removeEventListener(\"focusin\""]);
requireMarkers("components/common/useRuntimeFaultReporter.ts", ["for (const timer of pending) window.clearTimeout(timer)", "removeEventListener(\"unhandledrejection\""]);
requireMarkers("adapters/httpApiClient.ts", ["if (timer) clearTimeout(timer)", "es.close()"]);
requireMarkers("adapters/httpApiClient.ts", ["ApiRequestTimeoutError", "const timeoutOptions = { ...options }", "clientAbort.abort", "activeAbort?.abort", "getInflight.clear()", "cloneTransportValue", "streams.clear()", "dispose: () =>"]);
requireMarkers("adapters/clientLifetime.ts", ["queueMicrotask", "leases.get(value) !== 0", "dispose(value)"]);
const manuscript = requireMarkers("components/manuscript/ManuscriptEditor.tsx", ["new IntersectionObserver", "observer.disconnect()", "data-prose-static", "data-scene-prose", "touchWarmSceneIds", "contentVisibility"]);
if ((manuscript.match(/<ProseEditor/g) ?? []).length !== 1) failures.push("ManuscriptEditor must keep one conditional ProseEditor render site");
if (manuscript.includes("contentById")) failures.push("ManuscriptEditor duplicates the whole manuscript in parent content state");
requireMarkers("components/manuscript/ManuscriptEditor.tsx", ["sceneObserverRef.current !== observer", "status === \"dirty\"", "status === \"saving\"", "status === \"error\""]);
const mountedRef = requireMarkers("hooks/useMountedRef.ts", ["mounted.current = true", "mounted.current = false"]);
if (mountedRef.indexOf("mounted.current = true") > mountedRef.indexOf("mounted.current = false")) {
  failures.push("useMountedRef does not re-open before its cleanup");
}

const componentRoot = path.join(process.cwd(), "src", "components");
const scanComponents = (directory: string): void => {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) scanComponents(target);
    else if (target.endsWith(".tsx")) {
      const source = fs.readFileSync(target, "utf8");
      if (/useEffect\(\(\) => \(\) => \{\s*mounted\.current = false/.test(source)) {
        failures.push(`${path.relative(process.cwd(), target)} uses a StrictMode-unsafe mounted ref`);
      }
    }
  }
};
scanComponents(componentRoot);

console.log("Lifecycle resource checks");
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} lifecycle resource violation(s)`);
console.log("LIFECYCLE RESOURCE TESTS: PASS");
