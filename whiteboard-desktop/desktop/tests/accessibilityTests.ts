import fs from 'node:fs';
import path from 'node:path';
import ts from 'typescript';

import { restoreFocusAfterNotificationDismiss } from '../renderer/src/features/whiteboard/notificationFocus';

const rendererRoot = path.join(process.cwd(), 'renderer', 'src');
const files: string[] = [];
const walk = (directory: string): void => {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) walk(target);
    else if (target.endsWith('.tsx')) files.push(target);
  }
};
walk(rendererRoot);

const failures: string[] = [];

// Deterministic regression for the browser state React leaves behind when a
// focused toast dismiss button is removed. This intentionally uses a tiny DOM
// facade so the headless accessibility suite does not need jsdom.
{
  const body = { isConnected: true };
  const documentElement = { isConnected: true };
  let focusCalls = 0;
  const queries: string[] = [];
  const fallback = {
    isConnected: true,
    focus: ({ preventScroll }: FocusOptions = {}) => {
      if (preventScroll) focusCalls += 1;
    },
  };
  const fakeDocument = (activeElement: object | null, hasAnotherToast = true) => ({
    activeElement,
    body,
    documentElement,
    querySelector: (selector: string) => {
      queries.push(selector);
      if (selector === '.wb-toast-dismiss' && !hasAnotherToast) return null;
      return fallback;
    },
  } as unknown as Document);

  restoreFocusAfterNotificationDismiss(fakeDocument({ isConnected: false }));
  if (focusCalls !== 1) failures.push('Toast dismissal does not recover from a disconnected focused button');
  if (queries[0] !== '.wb-toast-dismiss') failures.push('Toast focus recovery does not prefer another notification');

  restoreFocusAfterNotificationDismiss(fakeDocument(body, false));
  if (focusCalls !== 2) failures.push('Toast dismissal does not recover when focus falls back to body');
  if (!queries.at(-1)?.includes('.wb-editor')) failures.push('Toast focus recovery has no workspace fallback');

  restoreFocusAfterNotificationDismiss(fakeDocument({ isConnected: true }));
  if (focusCalls !== 2) failures.push('Toast dismissal steals focus that moved to a connected control');
}
const modalFiles = new Set<string>();
let buttons = 0;
let fields = 0;
const location = (file: string, source: ts.SourceFile, node: ts.Node): string =>
  `${path.relative(process.cwd(), file)}:${source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1}`;

for (const file of files) {
  const source = ts.createSourceFile(
    file,
    fs.readFileSync(file, 'utf8'),
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );
  const visit = (node: ts.Node): void => {
    if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
      const tag = node.tagName.getText(source);
      const attributes = new Set(
        node.attributes.properties
          .filter(ts.isJsxAttribute)
          .map((attribute) => attribute.name.getText(source)),
      );
      const at = location(file, source, node);
      const keyboardButton = attributes.has('role') && attributes.has('tabIndex') && attributes.has('onKeyDown');
      const modalBackdrop = tag === 'div' && attributes.has('data-wb-modal-layer');

      if (['div', 'span', 'label'].includes(tag) && attributes.has('onClick') && !keyboardButton && !modalBackdrop) {
        failures.push(`${at} non-semantic <${tag}> has onClick`);
      }
      if (tag === 'button') {
        buttons += 1;
        if (!attributes.has('type')) failures.push(`${at} button has no explicit type`);
        if (ts.isJsxOpeningElement(node) && ts.isJsxElement(node.parent)) {
          const children = node.parent.children;
          const hasOnlyStaticText = children.every(ts.isJsxText);
          const staticText = children
            .filter(ts.isJsxText)
            .map((child) => child.getText(source))
            .join('')
            .trim();
          const isGlyphOnly = hasOnlyStaticText
            && staticText.length > 0
            && !/[A-Za-z0-9]/.test(staticText);
          if (
            isGlyphOnly
            && !attributes.has('aria-label')
            && !attributes.has('aria-labelledby')
          ) {
            failures.push(`${at} glyph-only button has no accessible name`);
          }
        }
      }
      if (['input', 'textarea', 'select'].includes(tag)) {
        fields += 1;
        let parent: ts.Node | undefined = node.parent;
        let wrappedByLabel = false;
        while (parent) {
          if (ts.isJsxElement(parent) && parent.openingElement.tagName.getText(source) === 'label') {
            wrappedByLabel = true;
            break;
          }
          parent = parent.parent;
        }
        if (
          !wrappedByLabel &&
          !attributes.has('aria-label') &&
          !attributes.has('aria-labelledby') &&
          !attributes.has('id')
        ) {
          failures.push(`${at} <${tag}> has no accessible name`);
        }
      }
      if (attributes.has('onPointerDown') && !attributes.has('onKeyDown')) {
        failures.push(`${at} pointer-only control has no keyboard handler`);
      }
      if (attributes.has('aria-modal')) {
        modalFiles.add(file);
        if (!attributes.has('role')) failures.push(`${at} aria-modal surface has no dialog role`);
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
}

const sourceText = (relative: string): string =>
  fs.readFileSync(path.join(rendererRoot, relative), 'utf8');
const requireMarkers = (label: string, text: string, markers: string[]): void => {
  for (const marker of markers) {
    if (!text.includes(marker)) failures.push(`${label} is missing ${marker}`);
  }
};

const requireNativeMenuModalGuard = (label: string, relative: string, subscription: string): void => {
  const text = sourceText(relative);
  const guardedCallback = new RegExp(
    `${subscription}\\(\\(action\\) => \\{\\s*if \\(isModalDialogOpen\\(\\)(?: \\|\\| isDocumentInteractionLocked\\(\\))?\\) return;`,
  );
  if (!guardedCallback.test(text)) failures.push(`${label} does not yield while a modal is open`);
};

for (const file of modalFiles) {
  const text = fs.readFileSync(file, 'utf8');
  const label = path.relative(process.cwd(), file);
  requireMarkers(label, text, [
    '<ModalPortal>',
    'useModalDialog({',
    'data-wb-modal-layer',
    'role="dialog"',
    'aria-modal="true"',
    'tabIndex={-1}',
    'event.target === event.currentTarget',
  ]);
  if (text.includes('className="cf-overlay"') && text.includes('onMouseDown')) {
    failures.push(`${label} still dismisses its modal on pointer-down`);
  }
}

requireMarkers('ModalDialog', sourceText('components/useModalDialog.ts'), [
  "event.key !== 'Tab'",
  "event.key === 'Escape'",
  'destination?.focus',
  'returnFocusFallbackRef',
  'canRestoreFocus',
  'child.inert = true',
  'restoreBackgroundElement',
  'modalStack',
  "addEventListener('focusin'",
  "removeEventListener('focusin'",
  "document.body.style.overflow = 'hidden'",
  'isModalDialogOpen',
]);
requireMarkers('ModalPortal', sourceText('components/ModalPortal.tsx'), [
  'createPortal(',
  'data-wb-modal-portal',
  'document.body',
]);
requireMarkers('LittleBoy modal precedence', sourceText('features/littleboy/LittleBoyProvider.tsx'), [
  'isModalDialogOpen()',
]);
requireNativeMenuModalGuard('Native View menu', 'App.tsx', 'onMenuView');
requireNativeMenuModalGuard('Native File menu', 'features/files/useFileActions.ts', 'onMenuFile');
requireNativeMenuModalGuard('Native Import/Export menu', 'features/files/useImportExport.ts', 'onMenuFile');
requireMarkers('Native PDF menu', sourceText('features/whiteboard/WhiteboardPage.tsx'), [
  '!isModalDialogOpen()',
  '!isDocumentInteractionLocked()',
  "a === 'export:pdf'",
]);
requireMarkers('Comment navigation modal precedence', sourceText('features/comments/CommentsLayer.tsx'), [
  'if (isModalDialogOpen()) return;',
]);
requireMarkers('Comment error dismissal', sourceText('features/whiteboard/WhiteboardPage.tsx'), [
  'commentsApi.dismissError',
  'aria-label="Dismiss comment error"',
  'dismissNotification',
  'restoreFocusAfterNotificationDismiss',
]);
if (sourceText('features/files/useImportExport.ts').includes('setTimeout(() => setFeedback(null)')) {
  failures.push('Import/export feedback still disappears before explicit dismissal');
}
requireMarkers('Clean comment-free print surface', sourceText('styles/app.css'), [
  '.comments-window, .comment-popover, .comment-add-fab',
  '.comment-mark, .comment-mark-active, .comment-mark-resolved',
  'border-bottom: 0 !important',
]);
requireMarkers('Destructive modal focus fallback', sourceText('components/ConfirmDialog.tsx'), [
  'returnFocusFallbackRef',
]);
requireMarkers('Outline delete focus fallback', sourceText('features/outline/OutlinePanel.tsx'), [
  'returnFocusFallbackRef={addButtonRef}',
]);
requireMarkers('PSYKE delete focus fallback', sourceText('features/psyke/PsykeWindow.tsx'), [
  'returnFocusFallbackRef={addButtonRef}',
]);
requireMarkers('Reusable confirm dialog ids', sourceText('components/ConfirmDialog.tsx'), [
  'const titleId = useId()',
  'const messageId = useId()',
  'aria-labelledby={titleId}',
  'aria-describedby={messageId}',
]);
requireMarkers('Reusable prompt dialog ids', sourceText('components/PromptDialog.tsx'), [
  'const titleId = useId()',
  'const messageId = useId()',
  'aria-labelledby={titleId}',
  'aria-describedby={message ? messageId : undefined}',
]);
requireMarkers('Settings recovery path', sourceText('App.tsx'), [
  'setSettingsOpen((open) => !open)',
]);
requireMarkers('Popover accessible trigger and focus contract', sourceText('components/Popover.tsx'), [
  'aria-label={title}',
  'options?.restoreFocus !== false',
  'triggerRef.current?.focus',
]);
for (const [label, relative] of [
  ['File-menu modal openers', 'features/whiteboard/WhiteboardPage.tsx'],
  ['Outline-template modal opener', 'features/outline/OutlinePanel.tsx'],
] as const) {
  requireMarkers(label, sourceText(relative), ['restoreFocus: true']);
}
requireMarkers('Outline-delete modal opener', sourceText('features/outline/OutlineRow.tsx'), [
  'restoreFocus: hasChildren',
]);

requireMarkers('RenderErrorBoundary', sourceText('components/RenderErrorBoundary.tsx'), [
  'getDerivedStateFromError',
  'componentDidCatch',
  'componentDidUpdate',
  'markRuntimeFaultHandled',
  'role="alert"',
  'data-ui-error-boundary',
  'data-ui-error-content',
  'focusAfterRecovery',
  'this.contentRef.current?.focus',
  'this.setState({ error: null })',
]);
requireMarkers('Runtime fault normalization', sourceText('components/runtimeFaults.ts'), [
  'isExpectedCancellation',
  'markRuntimeFaultHandled',
  'shouldReportRuntimeFault',
  'WeakSet<object>',
]);
requireMarkers('Runtime fault listener', sourceText('components/useRuntimeFaultReporter.ts'), [
  "addEventListener('error'",
  "addEventListener('unhandledrejection'",
  "removeEventListener('error'",
  "removeEventListener('unhandledrejection'",
  'wasRuntimeFaultHandled',
  'isExpectedCancellation',
  'window.clearTimeout(timer)',
]);
requireMarkers('Runtime fault banner', sourceText('components/RuntimeFaultBanner.tsx'), [
  'role="alert"',
  'data-runtime-fault',
  'aria-label="Dismiss runtime error"',
  'returnFocus.focus',
]);

requireMarkers('Renderer root fault host', sourceText('main.tsx'), [
  'function RendererFaultHost()',
  'useRuntimeFaultReporter()',
  '<RenderErrorBoundary name="Whiteboard application"',
  '<RuntimeFaultBanner',
]);
requireMarkers('Application fault containment', sourceText('App.tsx'), [
  '<RenderErrorBoundary',
  'name="PSYKE panel"',
  'useCurrentDocId()',
  'isModalDialogOpen()',
]);
const outlinePanelText = sourceText('features/outline/OutlinePanel.tsx');
requireMarkers('Outline fault containment', outlinePanelText, [
  '<RenderErrorBoundary',
  'name="Outline panel"',
  '<OutlinePanelContent',
]);
if (outlinePanelText.indexOf('const store = useOutline') > outlinePanelText.indexOf('<RenderErrorBoundary')) {
  failures.push('Outline save owner is mounted below its render boundary');
}
requireMarkers('Writing fault containment', sourceText('features/whiteboard/WhiteboardPage.tsx'), [
  'name="Writing workspace"',
  'name="LittleBoy tools"',
  'name="Settings dialog"',
  'name="Comments"',
  'isModalDialogOpen()',
]);
requireMarkers('Whiteboard app-lifetime save coordinator', sourceText('features/whiteboard/pendingWhiteboardRecovery.ts'), [
  'flushWhiteboardPatches',
  'registerDocFlusher',
  'registerDocDiscarder',
  'registerUnloadFlush',
  'WhiteboardPatchTransport',
]);
requireMarkers('Outline app-lifetime save coordinator', sourceText('features/outline/pendingOutlineRecovery.ts'), [
  'flushOutlineSnapshots',
  'registerDocFlusher',
  'registerDocDiscarder',
  'registerUnloadFlush',
  'OutlineSnapshotTransport',
]);
requireMarkers('Explicit document save routes', sourceText('features/whiteboard/whiteboardApi.ts'), [
  'updateWhiteboardForDocument',
  'encodeURIComponent(documentId)',
]);
requireMarkers('Explicit outline routes', sourceText('features/outline/outlineApi.ts'), [
  'getOutlineItemsForDocument',
  'saveOutlineItemsForDocument',
]);
requireMarkers('StrictMode document bootstrap', sourceText('features/whiteboard/documentBootstrap.ts'), [
  'inFlightLoads',
  'loadInitialDocumentOnce',
  'complete initial LIST -> optional CREATE -> GET transaction',
]);
requireMarkers('Electron persistence adapter', sourceText('api/pendingDocumentPersistence.ts'), [
  'persistPendingDocumentOnUnload',
  'waitForPendingDocumentPersistence',
  'captureDocumentIncarnation(documentId)',
  "kind === 'whiteboard'",
  'main process rejected',
]);
requireMarkers('Captured document generation identity', sourceText('state/currentDocument.ts'), [
  'currentDocIncarnation',
  'captureDocumentIdentity(',
  'setCurrentDocumentIdentity(',
]);
for (const [label, relative] of [
  ['Comment generation headers', 'features/comments/commentsApi.ts'],
  ['PSYKE generation headers', 'features/psyke/psykeApi.ts'],
  ['Outline generation headers', 'features/outline/outlineApi.ts'],
  ['Whiteboard generation headers', 'features/whiteboard/whiteboardApi.ts'],
  ['LittleBoy generation headers', 'features/littleboy/littleboyApi.ts'],
] as const) {
  requireMarkers(label, sourceText(relative), ['withDocumentIncarnation']);
}
requireMarkers(
  'LittleBoy close and ABA response gate',
  sourceText('features/littleboy/littleboyRequestLifecycle.ts'),
  ['runPendingDocWrite(', 'isCurrentLittleBoyIdentity(', 'StaleLittleBoyResponseError'],
);
for (const relative of [
  'features/whiteboard/useWhiteboardDocument.ts',
  'features/outline/useOutline.ts',
]) {
  if (sourceText(relative).includes('keepalive: true')) {
    failures.push(`${relative} bypasses the main-process save serializer during unload`);
  }
}
const electronMain = fs.readFileSync(path.join(process.cwd(), 'electron', 'main.ts'), 'utf8');
requireMarkers('All-close autosave handshake', electronMain, [
  'requestRendererAutosaveFlush',
  "app:flush-autosave-before-close",
  "app:autosave-flush-result",
  'documentPersistence.drain()',
  'Intercept every close',
]);
requireMarkers('Renderer-loss and shutdown persistence fallback', electronMain, [
  "'app:set-close-handshake-ready'",
  "'app:set-external-save-handshake-ready'",
  'RendererCloseCapabilities',
  'rendererCloseCapabilities.canFlushAutosave',
  'rendererCloseCapabilities.canSaveExternalFile',
  "'did-start-loading'",
  "'render-process-gone'",
  'prepareCloseWithoutRenderer',
  'waitForMainDocumentPersistence()',
  'drainPersistenceUntilSettled',
  'retrying without stopping the backend',
]);
requireMarkers('Windows non-interactive session-end persistence', electronMain, [
  "'query-session-end'",
  'event.preventDefault()',
  'queueSystemSessionEnd(createdWindow)',
  'closePreparations.waitUntilIdle()',
  'ordinaryCloseCanContinue(systemSessionEndInFlight)',
  'prepareSystemSessionEndPersistence(',
  'classifySystemSessionRendererOutcome(',
  'systemSessionEndInFlight',
]);
const systemSessionEndStart = electronMain.indexOf('async function handleSystemSessionEnd');
const systemSessionEndEnd = electronMain.indexOf('function createWindow', systemSessionEndStart);
const systemSessionEndSource = electronMain.slice(systemSessionEndStart, systemSessionEndEnd);
for (const interactiveSave of ['requestRendererSave(', 'confirmSaveChanges(']) {
  if (systemSessionEndSource.includes(interactiveSave)) {
    failures.push(`Windows session end opens an interactive save path: ${interactiveSave}`);
  }
}
const rendererRootSource = sourceText('main.tsx');
requireMarkers('Renderer module-lifetime close-handler readiness publication', rendererRootSource, [
  'fileOnFlushAutosaveBeforeClose',
  'fileOnCloseCancelled',
  'fileSetCloseHandshakeReady(true)',
]);
const rendererReadyIndex = rendererRootSource.indexOf('fileSetCloseHandshakeReady(true)');
for (const listener of ['fileOnFlushAutosaveBeforeClose', 'fileOnCloseCancelled']) {
  if (rendererRootSource.indexOf(listener) > rendererReadyIndex) {
    failures.push(`Renderer publishes close readiness before registering ${listener}`);
  }
}
const fileActionsSource = sourceText('features/files/useFileActions.ts');
if (fileActionsSource.includes('setCloseHandshakeReady(')) {
  failures.push('Hook mount/unmount controls module-lifetime close-handshake readiness');
}
requireMarkers('Hook-scoped external-file Save readiness publication', fileActionsSource, [
  'fileApi.onSaveBeforeClose',
  'fileApi.setExternalSaveHandshakeReady(true)',
  'fileApi.setExternalSaveHandshakeReady(false)',
]);
requireMarkers('Exclusive close preparation ownership', electronMain, [
  "closePreparations.begin('ordinary')",
  "closePreparations.end('ordinary')",
  "closePreparations.begin('system-session-end')",
  "closePreparations.end('system-session-end')",
]);
requireMarkers('Renderer close operation barrier', sourceText('main.tsx'), [
  'beginDocumentCloseBarrier(requestId)',
  'waitForTrackedDocumentOperations()',
  'flushPendingDocSaves()',
  'waitForPendingDocumentPersistence()',
  'fileOnCloseCancelled',
  'lockDocumentInteraction()',
]);
requireMarkers('Imported outline save serialization', sourceText('features/files/useImportExport.ts'), [
  'queueOutlineSnapshot(',
  'flushOutlineSnapshots(documentId)',
  'persistPendingDocument(',
  'acquireTrackedDocumentOperation()',
  'createPsykeElementForDocument',
]);
requireMarkers('Renderer delete persistence fence', sourceText('features/whiteboard/useWhiteboardDocument.ts'), [
  'deleteDocumentWithNativePersistenceFence(',
  'blockWhiteboardWrites(id)',
  'blockOutlineWrites(id)',
  'blockDocumentMutations(id)',
]);
requireMarkers('Main-owned delete transaction', electronMain, [
  'documentDeleteOperations',
  'runDocumentDeleteTransaction({',
  "'document:delete-with-fence'",
  'waitForMainDocumentPersistence()',
  'DOCUMENT_DELETE_REQUEST_TIMEOUT_MS',
]);
requireMarkers('Document incarnation transport', electronMain, [
  "'X-LogosForge-Document-Incarnation': incarnation",
]);
requireMarkers('Comments remount read barrier', sourceText('features/comments/useComments.ts'), [
  'await waitForPendingDocWrites()',
  'getCommentsForDocument(baseUrl, requestDocId)',
  'invalidateLoad();',
  'runSerializedPendingDocWrite(',
  'isLatestCommentMutation',
]);
requireMarkers('Save-coupled orphan cleanup', sourceText('features/whiteboard/WhiteboardPage.tsx'), [
  'flushWhiteboardPatchThrough(persistence.receipt)',
  'eligibleOrphanCleanupIds(',
  'persistence.blocks !== liveBlocks',
]);
requireMarkers('PSYKE retry read barrier', sourceText('features/psyke/usePsykeSearch.ts'), [
  'await waitForPendingDocWrites()',
  'searchPsykeForDocument(',
  'requestDocId !== getCurrentDocId()',
]);
requireMarkers('Stable backend export snapshot', sourceText('features/files/useImportExport.ts'), [
  'await flushPendingDocSaves()',
  "url.searchParams.set('doc', documentId)",
  'getWhiteboardForDocument(',
  'exportPayloadFromProjectBundle(projectContent)',
  'lockDocumentInteraction()',
]);
requireMarkers('Exact imported outline handoff', sourceText('features/outline/outlineApi.ts'), [
  'CustomEvent<OutlineRefreshSnapshot>',
  'detail: { documentId, items }',
]);
const importExportSource = sourceText('features/files/useImportExport.ts');
const replaceImportSource = importExportSource.slice(
  importExportSource.indexOf("if (mode === 'replace')"),
  importExportSource.indexOf('} else {', importExportSource.indexOf("if (mode === 'replace')")),
);
if (replaceImportSource.indexOf('o.loadBlocks(') > replaceImportSource.indexOf('await o.setMode(')) {
  failures.push('Replace import can overwrite typing performed during its first backend await');
}
const appendImportSource = importExportSource.slice(
  importExportSource.indexOf('} else {', importExportSource.indexOf("if (mode === 'replace')")),
  importExportSource.indexOf('// loadBlocks already marks dirty'),
);
if (appendImportSource.indexOf('o.loadBlocks(') > appendImportSource.indexOf('await o.setMode(')) {
  failures.push('Append import can lose its manuscript during an async mode save');
}
const exportFlowSource = importExportSource.slice(importExportSource.indexOf('const doExport'));
for (const liveGetter of ['o.getBlocks()', 'o.getMode()', 'o.getSettings()', 'o.getComments()']) {
  if (exportFlowSource.includes(liveGetter)) {
    failures.push(`Export uses incoherent live renderer state: ${liveGetter}`);
  }
}
if (electronMain.includes("role: 'reload'")) {
  failures.push('Electron exposes a raw reload that bypasses the persistence handshake');
}
requireMarkers('Guarded Electron reload', fs.readFileSync(path.join(process.cwd(), 'electron', 'menu.ts'), 'utf8'), [
  "accelerator: 'CmdOrCtrl+R'",
  'reloadWindow()',
]);

const appCss = sourceText('styles/app.css');
if (!appCss.includes(':focus-visible')) failures.push('app.css has no visible keyboard focus rule');
if (!appCss.includes('prefers-reduced-motion: reduce')) failures.push('app.css does not honor reduced motion');
for (const marker of ['.wb-app-boundary', '.wb-outline-boundary', '.wb-document-boundary']) {
  if (!appCss.includes(marker)) failures.push(`app.css is missing boundary layout rule ${marker}`);
}
for (const marker of [
  '.wb-toast-stack',
  '[data-runtime-fault]',
  '[data-wb-modal-portal]',
  '[data-ui-error-boundary]',
]) {
  if (!appCss.includes(marker)) failures.push(`app.css is missing notification/print rule ${marker}`);
}

console.log(
  `Accessibility/resilience checks: ${files.length} TSX files · ${buttons} buttons · ${fields} fields · ${modalFiles.size} modals`,
);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} accessibility/resilience violation(s)`);
console.log('ACCESSIBILITY / RESILIENCE TESTS: PASS');
