import { createMockApiClient } from "./mockApi";
import { ApiRequestError } from "../src/adapters/httpApiClient";

let passed = 0;

function check(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
  passed += 1;
}

const api = createMockApiClient();
check(typeof api.getAdapt === "function", "preview mock must implement getAdapt");
check(typeof api.patchAiBehavior === "function", "preview mock must implement patchAiBehavior");
check(typeof api.voiceHistory === "function", "preview mock must implement Voice history");
check(typeof api.voiceIntentCancel === "function", "preview mock must implement Voice preview cancellation");
check(typeof api.voiceBillyCancel === "function", "preview mock must implement Billy preview cancellation");

const initial = await api.getAdapt(1);
check(initial.mode === "Structure", "preview should start in automatic Structure mode");

await api.patchAiBehavior(1, { adaptive_override: "Refinement" });
const overridden = await api.getAdapt(1);
check(overridden.mode === "Refinement", "adaptive override must round-trip in preview");
check(overridden.override === "Refinement", "preview must expose the active override");

const voice = await api.voiceHistory(1);
check(voice.entries.length > 0, "preview Voice history should contain a reviewable segment");
const otherVoice = await api.voiceHistory(2);
check(otherVoice.entries.length === 0, "preview Voice history must stay project-scoped");

const scene = (await api.listScenes(1))[0]!;
const updatedScene = await api.updateScene(1, scene.id, {
  content: `${scene.content}\nrevision-safe`,
  expected_revision: scene.revision,
});
check(updatedScene.revision !== scene.revision, "scene mutation should advance its revision");
let staleConflict: unknown = null;
try {
  await api.updateScene(1, scene.id, { content: "stale", expected_revision: scene.revision });
} catch (error) {
  staleConflict = error;
}
check(staleConflict instanceof ApiRequestError && staleConflict.code === "scene_conflict",
  "preview mock should reject a stale scene revision like the core");

console.log(`Preview API tests: ${passed} passed, 0 failed`);
