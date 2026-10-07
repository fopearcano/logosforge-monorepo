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
requireMarkers("adapters/httpApiClient.ts", ["ApiRequestTimeoutError", "const timeoutOptions = { ...options }", "clientAbort.abort", "activeAbort?.abort", "getInflight.clear()", "cloneTransportValue", "streams.clear()", "dispose: () =>", "broker_instance_id", "connectedEvent(p, r.cursor)"]);
requireMarkers("hooks/useResource.ts", ['e.event === "connected" || refetchOn.includes']);
requireMarkers("components/shell/Chrome.tsx", ['["connected", "scene_changed"']);
requireMarkers("components/aipanels/Logos.tsx", ['["connected", "scenes_changed"']);
requireMarkers("adapters/clientLifetime.ts", ["queueMicrotask", "leases.get(value) !== 0", "dispose(value)"]);
requireMarkers("hooks/resources.ts", [
  "const TIMELINE_REFRESH_EVENTS: EventName[] = [",
  "export function useTimeline(): Resource<TimelineSnapshotDTO>",
  '"timeline_changed",',
  '"project_data_changed",',
  '"characters_changed",',
  '"psyke_changed",',
  "TIMELINE_REFRESH_EVENTS,",
  "export function useManuscriptSnapshot()",
  "api.getManuscriptSnapshot(projectId as number)",
  "export function useStoryStructure()",
  "api.getStoryStructure(projectId as number)",
  '["scene_changed", "scenes_changed", "project_data_changed"]',
]);
const sceneNavigator = requireMarkers("components/shell/StudioSceneNavigator.tsx", [
  "useStoryStructure()",
  "filterStudioStoryStructure",
  "activationRef.current !== token",
  "placementRef.current !== token",
  "projectIdRef.current !== ownerProjectId",
  "flushPendingProjectSaves()",
  "trackProjectWrite(",
  "api.placeScene(",
  "api.getStoryStructure(ownerProjectId)",
  "api.executeStoryStructureCommand(",
  "commandRef.current !== token",
  "pendingCommandFocusRef.current",
  'placementFailure.code === "structure_conflict"',
  'scrollIntoView?.({ block: "nearest" })',
  "initializedProjectRef.current = null",
]);
if (sceneNavigator.includes("useScenes()")) failures.push("StudioSceneNavigator must not reconstruct groups from useScenes");
if (sceneNavigator.includes("api.updateScene(")) failures.push("StudioSceneNavigator must not mutate structure labels through generic Scene PATCH");
const structurePanel = requireMarkers("components/manuscript/StructurePanel.tsx", [
  "useStoryStructure()",
  'data-structure-source="core"',
  "structure?.chapter_level",
]);
if (structurePanel.includes("groupByActChapter")) failures.push("StructurePanel must not reconstruct core story groups locally");
requireMarkers("workspace/useWorkspaceLayout.ts", [
  "loadGenerationRef",
  "registerProjectFlusher(flushLayout)",
  "dirtyRef.current = true",
  "trackProjectWrite(write, { saveKey:",
  "flushPromiseRef.current",
  "ownerIsCurrent()",
  "Keep dirty=true",
  "saved !== null && saved !== undefined",
  "clearTimer();",
]);
requireMarkers("components/formatpanels/VoiceHud.tsx", ["retrySaveKey: saveKey", "appendToScene(ownerProjectId, pending.sceneId, pending.text, true)"]);
requireMarkers("components/shell/DockWorkspace.tsx", [
  "new ResizeObserver(updateMetrics)",
  "observer.disconnect()",
  "focusAfterWorkspaceAction(",
  'event.target.getAttribute("role") !== "tab"',
]);
const manuscript = requireMarkers("components/manuscript/ManuscriptEditor.tsx", [
  "new IntersectionObserver", "observer.disconnect()", "data-prose-static", "data-scene-prose", "touchWarmSceneIds", "contentVisibility",
  "beginCrossScenePointerSelection", "finishCrossScenePointerSelection", "proseDomPointFromViewport",
  "commentDraft && !commentComposerOpen && !commentBusy",
  "contentVisibility: commentOverlayActive ? \"visible\" : \"auto\"",
  "jump(next.location.sceneId, false)",
  'setSelection({ sceneId: id, text: "", section: "Manuscript" })',
  "useManuscriptSnapshot()",
  "loadedSnapshot?.project_id === projectId",
  "loading && snapshot === undefined",
  "error && snapshot === undefined",
  "isFocusStable: () => {",
  "scenePlacementPlan(stepped.draft)",
  "expectedNeighborId",
  "isImmediateScenePlacementNeighbor(",
  "api.placeScene(projectId, id, plan.body)",
  "planAppendSceneCommand(",
  "api.executeStoryStructureCommand(",
  "STRUCTURE EDITS LIVE IN THE NAVIGATOR",
]);
if (manuscript.includes("useScenes()") || manuscript.includes("api.listScenes")) failures.push("ManuscriptEditor bypasses the canonical manuscript snapshot");
if (manuscript.includes("api.createScene(") || manuscript.includes("api.deleteScene(")) failures.push("ManuscriptEditor bypasses transactional structure commands for create/delete");
if ((manuscript.match(/<ProseEditor/g) ?? []).length !== 1) failures.push("ManuscriptEditor must keep one conditional ProseEditor render site");
if (manuscript.includes("contentById")) failures.push("ManuscriptEditor duplicates the whole manuscript in parent content state");
requireMarkers("components/manuscript/ManuscriptEditor.tsx", ["sceneObserverRef.current !== observer", "status === \"dirty\"", "status === \"saving\"", "status === \"error\""]);
const storyGrid = requireMarkers("components/manuscript/StoryGrid.tsx", [
  "useManuscriptSnapshot()",
  "useStoryStructure()",
  "planAppendSceneCommand(",
  "api.executeStoryStructureCommand(",
]);
if (storyGrid.includes("useScenes()") || storyGrid.includes("api.createScene(")) failures.push("StoryGrid bypasses canonical transactional structure authoring");
requireMarkers("components/manuscript/NotesPanel.tsx", [
  "useNoteTarget()",
  "notes.find((note) => note.id === targetId)",
  'data-note-editor-id={note.id}',
  "window.requestAnimationFrame",
  "clearTargetRef.current()",
  "<NoteEditor key={editing.id}",
]);
requireMarkers("components/manuscript/CommentsPanel.tsx", [
  "window.setInterval",
  "window.clearInterval(timer)",
  "mutationSequence.current += 1",
  "useCommentTarget()",
  "commentsData.find((comment) => comment.id === targetId",
  "comment.id === revealedTargetId",
  "scheduleThreadFocus(targetId, (focused) => {",
  "document.activeElement === button",
  "window.cancelAnimationFrame(focusFrameRef.current)",
  "loading && commentsData === undefined",
  "error && commentsData === undefined",
]);
requireMarkers("components/manuscript/commentPreferences.ts", ["removeEventListener(COMMENT_VISIBILITY_EVENT", "removeEventListener(\"storage\""]);
requireMarkers("adapters/StudioProvider.tsx", [
  "export interface StudioNavigationOptions",
  "noteId?: number",
  "commentId?: number",
  "noteTargetId?: number | null",
  "commentTargetId?: number | null",
  "export function useNoteTarget()",
  "export function useCommentTarget()",
]);
const studioOmnibox = requireMarkers("components/shell/StudioOmnibox.tsx", [
  "createLatestRequestGate()",
  "projectSearchAbortRef.current?.abort()",
  'requests.invalidate("project-search")',
  'requests.begin("project-search")',
  'api.searchProject(projectId, searchQuery, ["scene", "note", "psyke", "comment"], controller.signal)',
  "requests.open()",
  "requests.close()",
  'requests.invalidate("plan")',
  "if (planRef.current)",
  "canClose: !activating && !executing",
  'requests.invalidate("suggestions")',
  'requests.invalidate("execute")',
  'requests.begin("execute")',
  "openRef.current",
  "planAbortRef.current?.abort()",
  "suggestionAbortRef.current?.abort()",
  "new AbortController()",
  "window.clearTimeout(timer)",
  "controller.signal",
  "requests.isCurrent(token)",
  "identityRef.current.projectId !== ownerIdentity.projectId",
  "identityRef.current.sceneId !== ownerIdentity.sceneId",
  "activatingRef.current",
  "executingRef.current",
  "flushPendingProjectSaves({ commitActiveField: true })",
  "executeOmniboxPlan({",
  "PendingProjectSaveError",
  "StaleOmniboxPlanError",
]);
const cancelPlanSource = studioOmnibox.slice(
  studioOmnibox.indexOf("const cancelPlan"),
  studioOmnibox.indexOf("const closeNow"),
);
if (cancelPlanSource.includes("executingRef.current = false")) {
  failures.push("StudioOmnibox cancelPlan releases the execution lock before the core request settles");
}
if ((studioOmnibox.match(/!requests\.isCurrent\(token\)/g) ?? []).length < 4) {
  failures.push("StudioOmnibox does not gate all late planning/execution publications");
}
if ((studioOmnibox.match(/new AbortController\(\)/g) ?? []).length < 3) {
  failures.push("StudioOmnibox must independently cancel project search, suggestions, and command-plan requests");
}
if (!/return \(\) => \{[\s\S]*?window\.clearTimeout\(timer\);[\s\S]*?projectSearchAbortRef\.current\?\.abort\(\)/.test(studioOmnibox)) {
  failures.push("StudioOmnibox project-search debounce does not clear its timer and abort its request on cleanup");
}
if (!/return \(\) => \{[\s\S]*?window\.clearTimeout\(timer\);[\s\S]*?suggestionAbortRef\.current\?\.abort\(\)/.test(studioOmnibox)) {
  failures.push("StudioOmnibox suggestion debounce does not clear its timer and abort its request on cleanup");
}
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
