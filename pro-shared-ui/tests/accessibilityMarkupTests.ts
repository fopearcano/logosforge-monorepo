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

console.log(`Accessibility markup checks: ${files.length} files · ${buttons} buttons · ${fields} fields`);
for (const violation of violations) console.error(`  FAIL: ${violation}`);
if (violations.length) throw new Error(`${violations.length} accessibility markup violation(s)`);
console.log("ACCESSIBILITY MARKUP TESTS: PASS");
