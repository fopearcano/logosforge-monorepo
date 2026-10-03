import fs from "node:fs";
import path from "node:path";
import ts from "typescript";

const root = path.join(process.cwd(), "src", "components");
const files: string[] = [];
const walk = (directory: string): void => {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) walk(target);
    else if (target.endsWith(".tsx")) files.push(target);
  }
};
walk(root);

const violations: string[] = [];
let buttons = 0;
let fields = 0;
const location = (file: string, source: ts.SourceFile, node: ts.Node) =>
  `${path.relative(process.cwd(), file)}:${source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1}`;

for (const file of files) {
  const source = ts.createSourceFile(
    file, fs.readFileSync(file, "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX,
  );
  const visit = (node: ts.Node): void => {
    if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
      const tag = node.tagName.getText(source);
      const attributes = new Set(
        node.attributes.properties.filter(ts.isJsxAttribute).map((attribute) => attribute.name.getText(source)),
      );
      const keyboardButton = attributes.has("role") && attributes.has("tabIndex") && attributes.has("onKeyDown");
      const modalBackdrop = tag === "div" && attributes.has("data-lf-modal-layer");
      if (["div", "span", "label"].includes(tag) && attributes.has("onClick") && !keyboardButton && !modalBackdrop) {
        violations.push(`${location(file, source, node)} non-semantic <${tag}> has onClick`);
      }
      if (tag === "button") {
        buttons += 1;
        if (!attributes.has("type")) violations.push(`${location(file, source, node)} button has no explicit type`);
      }
      if (["input", "textarea", "select"].includes(tag)) {
        fields += 1;
        let parent: ts.Node | undefined = node.parent;
        let wrappedByLabel = false;
        while (parent) {
          if (ts.isJsxElement(parent) && parent.openingElement.tagName.getText(source) === "label") {
            wrappedByLabel = true;
            break;
          }
          parent = parent.parent;
        }
        if (!wrappedByLabel && !attributes.has("aria-label")
          && !attributes.has("aria-labelledby") && !attributes.has("id")) {
          violations.push(`${location(file, source, node)} <${tag}> has no accessible name`);
        }
      }
      if (attributes.has("onPointerDown") && !attributes.has("onKeyDown")) {
        violations.push(`${location(file, source, node)} pointer-only control has no keyboard handler`);
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
}

const shellStyles = fs.readFileSync(path.join(root, "shell", "ShellStyles.tsx"), "utf8");
if (!shellStyles.includes(":focus-visible")) violations.push("ShellStyles has no visible keyboard focus rule");
if (!shellStyles.includes("prefers-reduced-motion:reduce")) violations.push("ShellStyles does not honor reduced motion");

const modalUtility = fs.readFileSync(path.join(root, "common", "useModalDialog.ts"), "utf8");
for (const marker of [
  "event.key !== \"Tab\"",
  "event.key === \"Escape\"",
  "destination?.focus",
  "child.inert = true",
  "restoreBackgroundElement",
  "modalStack",
]) {
  if (!modalUtility.includes(marker)) violations.push(`ModalDialog is missing ${marker}`);
}

const modalPortal = fs.readFileSync(path.join(root, "common", "ModalPortal.tsx"), "utf8");
for (const marker of ["lf-shell lf-modal-portal", "panelScopeVars(mode)", "createPortal("]) {
  if (!modalPortal.includes(marker)) violations.push(`ModalPortal is missing ${marker}`);
}

const errorBoundary = fs.readFileSync(path.join(root, "common", "PanelErrorBoundary.tsx"), "utf8");
for (const marker of [
  "getDerivedStateFromError",
  "componentDidCatch",
  "componentDidUpdate",
  "role=\"alert\"",
  "data-ui-error-boundary",
  "data-ui-error-content",
  "focusAfterRecovery",
  "this.contentRef.current?.focus",
  "this.setState({ error: null })",
]) {
  if (!errorBoundary.includes(marker)) violations.push(`PanelErrorBoundary is missing ${marker}`);
}

const runtimeFaults = fs.readFileSync(path.join(root, "common", "runtimeFaults.ts"), "utf8");
for (const marker of ["isExpectedCancellation", "markRuntimeFaultHandled", "shouldReportRuntimeFault", "WeakSet<object>"]) {
  if (!runtimeFaults.includes(marker)) violations.push(`Runtime fault reporting is missing ${marker}`);
}

const runtimeReporter = fs.readFileSync(path.join(root, "common", "useRuntimeFaultReporter.ts"), "utf8");
for (const marker of ["addEventListener(\"error\"", "addEventListener(\"unhandledrejection\"", "wasRuntimeFaultHandled", "isExpectedCancellation"]) {
  if (!runtimeReporter.includes(marker)) violations.push(`Runtime fault listener is missing ${marker}`);
}

const runtimeBanner = fs.readFileSync(path.join(root, "common", "RuntimeFaultBanner.tsx"), "utf8");
for (const marker of ["role=\"alert\"", "data-runtime-fault", "Dismiss runtime error", "returnFocus.focus"]) {
  if (!runtimeBanner.includes(marker)) violations.push(`Runtime fault banner is missing ${marker}`);
}

const applyModal = fs.readFileSync(path.join(root, "aipanels", "applyToScene.tsx"), "utf8");
for (const marker of ["<ModalPortal>", "useModalDialog(", "role=\"dialog\"", "aria-modal=\"true\"", "event.target === event.currentTarget"]) {
  if (!applyModal.includes(marker)) violations.push(`Controlled Apply dialog is missing ${marker}`);
}

const commentsPanel = fs.readFileSync(path.join(root, "manuscript", "CommentsPanel.tsx"), "utf8");
for (const marker of [
  "data-screen-label=\"Comments Panel\"",
  "aria-label=\"Comment threads\"",
  "aria-label=\"Replies\"",
  "aria-label=\"Show all comments\"",
  "aria-label=\"Show open comments\"",
  "aria-label=\"Export comments as Markdown\"",
  "aria-label=\"Reply to comment\"",
  "aria-label=\"Delete comment thread\"",
  "aria-label=\"Confirm thread deletion\"",
  "aria-live=\"polite\"",
  "\"Resolve comment\"",
  "\"Reopen comment\"",
  "Anchor unavailable",
  "navigate(\"Manuscript\", { sceneId })",
  "button?.scrollIntoView({ block: \"nearest\" })",
  "button?.focus({ preventScroll: true })",
  "scheduleThreadFocus(targetId, (focused) => {",
  "document.activeElement === button",
]) {
  if (!commentsPanel.includes(marker)) violations.push(`CommentsPanel is missing ${marker}`);
}

const notesPanel = fs.readFileSync(path.join(root, "manuscript", "NotesPanel.tsx"), "utf8");
for (const marker of [
  'data-note-editor-id={note.id}',
  '`[data-note-editor-id="${noteId}"]`',
  "input.focus({ preventScroll: true })",
  "document.activeElement === input",
  "scheduleNoteFocus(targetId, (focused) => {",
]) {
  if (!notesPanel.includes(marker)) violations.push(`NotesPanel target focus is missing ${marker}`);
}

const psykeConsole = fs.readFileSync(path.join(root, "shell", "PsykeConsole.tsx"), "utf8");
for (const marker of [
  'data-screen-label="PSYKE Console"',
  'role="combobox"',
  'aria-autocomplete="list"',
  'aria-expanded={expanded}',
  'aria-controls={listId}',
  'aria-activedescendant={activeId}',
  'role="listbox"',
  'role="option"',
  'aria-selected={index === selectedIndex}',
  'tabIndex={-1}',
  'onBlur={() => setExpanded(false)}',
  'aria-live="polite"',
  'event.key === "ArrowDown"',
  'event.key === "ArrowUp"',
  'event.key === "Enter"',
  'event.key === "Escape"',
  'window.setTimeout(() =>',
  '}, 100)',
  'requests.isCurrent(token)',
  'navigate("PSYKE", { psykeEntryId: suggestion.entry_id })',
  'skipNextQuerySearch.current = true',
  'skipNextQuerySearch.current = false',
  'if (nextQuery !== query) skipNextQuerySearch.current = true',
  'searchTimerRef.current = null',
  'window.clearTimeout(searchTimerRef.current)',
  'searchAbortRef.current?.abort()',
  'controller.signal',
  'suggestion.category === "entity"',
  '!suggestion.text.startsWith("/")',
  'Requested ${suggestion.text} in the PSYKE Bible.',
  'Complete the command, then press Enter to preview its exact effect.',
  'role="group"',
  'aria-labelledby={planTitleId}',
  'aria-describedby={planDescriptionId}',
  'aria-busy={executing}',
  'role="alert"',
  'CONFIRM & RUN',
  'CANCEL · ESC',
  'runButtonRef.current?.focus()',
  'flushPendingProjectSaves({ commitActiveField: true })',
  'confirmed: true',
  'executingRef.current',
]) {
  if (!psykeConsole.includes(marker)) violations.push(`PSYKE Console is missing ${marker}`);
}

const studioOmnibox = fs.readFileSync(path.join(root, "shell", "StudioOmnibox.tsx"), "utf8");
for (const marker of [
  "<ModalPortal>",
  "useModalDialog({",
  'data-screen-label="Studio Omnibox"',
  'role="dialog"',
  'aria-modal="true"',
  'aria-describedby={descriptionId}',
  'aria-busy={activating || planning || executing}',
  'role="combobox"',
  'aria-autocomplete="list"',
  'aria-expanded={plan == null && flatItems.length > 0}',
  'aria-controls={plan == null ? listId : undefined}',
  'aria-activedescendant={plan == null ? activeOptionId : undefined}',
  'role="listbox"',
  'aria-label="Omnibox results"',
  'role="group"',
  'aria-labelledby={groupId}',
  'role="option"',
  'aria-selected={selected}',
  'aria-disabled={item.disabled}',
  'tabIndex={-1}',
  'aria-labelledby={planTitleId}',
  'aria-describedby={planDescriptionId}',
  'aria-busy={executing}',
  'role="alert"',
  'role="status"',
  'aria-live="polite"',
  'event.key === "ArrowDown"',
  'event.key === "ArrowUp"',
  'event.key === "Home"',
  'event.key === "End"',
  'event.key === "Enter"',
  'event.key === "Escape"',
  "omniboxOptionDomId(idPrefix, item.key)",
  'scrollIntoView({ block: "nearest" })',
  "Search commands, panels, scenes, notes, PSYKE entries, comments, and recent projects.",
]) {
  if (!studioOmnibox.includes(marker)) violations.push(`Studio Omnibox is missing ${marker}`);
}

const chrome = fs.readFileSync(path.join(root, "shell", "Chrome.tsx"), "utf8");
for (const forbidden of ["SYNCED", "AUTOSAVE", "CORE · CONNECTED"]) {
  if (chrome.includes(forbidden)) violations.push(`Workspace chrome still hard-codes ${forbidden}`);
}
for (const marker of ['<details', '<summary', 'aria-label={`Workspace status:', 'aria-atomic="true"', 'runtimeStatus.copy']) {
  if (!chrome.includes(marker)) violations.push(`Workspace status HUD is missing ${marker}`);
}
for (const marker of ['disabled={!available}', 'Command palette is available in the desktop host', 'The browser preview does not host desktop commands']) {
  if (!chrome.includes(marker)) violations.push(`Host-scoped command palette control is missing ${marker}`);
}

const sceneNavigator = fs.readFileSync(path.join(root, "shell", "StudioSceneNavigator.tsx"), "utf8");
for (const marker of [
  'aria-label="Project structure"',
  'data-structure-level="act"',
  'data-structure-level="chapter"',
  'data-structure-level="scene"',
  'data-scene-group-toggle="act"',
  'data-scene-group-toggle="chapter"',
  'aria-expanded={actExpanded}',
  'aria-expanded={chapterExpanded}',
  'aria-controls={actControls}',
  'aria-controls={chapterControls}',
  'aria-label="Filter project scenes"',
  'event.key === "Escape"',
  'aria-label="Clear scene filter"',
  'aria-current={active ? "location" : undefined}',
  'data-scene-move-id={scene.id}',
  'aria-pressed={keyboardOwner}',
  'aria-disabled={moveUnavailable || undefined}',
  'event.key === "ArrowDown"',
  'event.key === "ArrowUp"',
  'event.key === "Enter"',
  'role="status" aria-live="polite"',
  'data-structure-action="create_act"',
  'data-structure-action="create_chapter"',
  'data-structure-action="create_scene"',
  'data-structure-action="rename_act"',
  'data-structure-action="rename_chapter"',
  'data-structure-action="detach_act"',
  'data-structure-action="detach_chapter"',
  'data-structure-action="delete_scene"',
  'data-structure-action="repair_orphans"',
  'data-structure-action-editor={structureAction.kind}',
  'aria-busy={commandBusy != null || undefined}',
  'This cannot be undone.',
  'Manuscript text and every scene field will be preserved',
]) {
  if (!sceneNavigator.includes(marker)) violations.push(`StudioSceneNavigator is missing ${marker}`);
}
if (sceneNavigator.includes("aria-grabbed")) {
  violations.push("StudioSceneNavigator must not expose the deprecated aria-grabbed state");
}

console.log(`Accessibility markup checks: ${files.length} files · ${buttons} buttons · ${fields} fields`);
for (const violation of violations) console.error(`  FAIL: ${violation}`);
if (violations.length) throw new Error(`${violations.length} accessibility markup violation(s)`);
console.log("ACCESSIBILITY MARKUP TESTS: PASS");
