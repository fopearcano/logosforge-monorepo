const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const root = path.join(process.cwd(), 'renderer', 'src');
const files = [];
const walk = (directory) => {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) walk(target);
    else if (target.endsWith('.tsx')) files.push(target);
  }
};
walk(root);

const failures = [];
let buttons = 0;
for (const file of files) {
  const source = ts.createSourceFile(
    file, fs.readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX,
  );
  const visit = (node) => {
    if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
      const tag = node.tagName.getText(source);
      const attributes = new Set(
        node.attributes.properties.filter(ts.isJsxAttribute).map((attribute) => attribute.name.getText(source)),
      );
      const at = `${path.relative(process.cwd(), file)}:${source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1}`;
      const keyboardButton = attributes.has('role') && attributes.has('tabIndex') && attributes.has('onKeyDown');
      const modalBackdrop = tag === 'div' && attributes.has('data-lf-modal-layer');
      if (['div', 'span', 'label'].includes(tag) && attributes.has('onClick') && !keyboardButton && !modalBackdrop) {
        failures.push(`${at} non-semantic click control`);
      }
      if (tag === 'button') {
        buttons += 1;
        if (!attributes.has('type')) failures.push(`${at} button has no explicit type`);
      }
      if (attributes.has('onPointerDown') && !attributes.has('onKeyDown')) {
        failures.push(`${at} pointer-only control has no keyboard handler`);
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
}

const dock = fs.readFileSync(path.join(root, 'AiDock.tsx'), 'utf8');
for (const marker of ['role="separator"', 'aria-valuemin', 'aria-valuemax', 'aria-valuenow', 'onPointerCancel', 'onLostPointerCapture']) {
  if (!dock.includes(marker)) failures.push(`AiDock resizer missing ${marker}`);
}

const palette = fs.readFileSync(path.join(root, 'CommandPalette.tsx'), 'utf8');
for (const marker of ['<ModalPortal>', 'useModalDialog(', 'role="dialog"', 'aria-modal="true"', 'event.target === event.currentTarget']) {
  if (!palette.includes(marker)) failures.push(`Command palette dialog missing ${marker}`);
}

const app = fs.readFileSync(path.join(root, 'App.tsx'), 'utf8');
for (const marker of ['<PanelErrorBoundary name="Studio workspace"', 'name={`${current.label} panel`}']) {
  if (!app.includes(marker)) failures.push(`App render containment missing ${marker}`);
}
if (!dock.includes('<PanelErrorBoundary name={`${t.label} AI`}')) {
  failures.push('AI tools do not have per-tool render containment');
}
for (const marker of ['useRuntimeFaultReporter()', '<RuntimeFaultBanner', 'dismissRuntimeFault']) {
  if (!app.includes(marker)) failures.push(`Global runtime error reporting missing ${marker}`);
}

console.log(`Desktop accessibility checks: ${files.length} files · ${buttons} buttons`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} desktop accessibility violation(s)`);
console.log('DESKTOP ACCESSIBILITY TESTS: PASS');
