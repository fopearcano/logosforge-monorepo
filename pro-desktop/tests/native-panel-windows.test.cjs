const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const {
  NATIVE_PANEL_IDS,
  nativePanelWindowFrameName,
  panelIdFromNativePanelFrameName,
  nativePanelWindowRequestFromFrameName,
  recoverNativePanelWindowBounds,
} = require('../dist-electron/native-panel-windows.js');

let passed = 0;
function check(label, condition) {
  assert.ok(condition, `Native panel window test failed: ${label}`);
  passed += 1;
}

check('the fixed host allowlist has all 37 unique workspace panels',
  NATIVE_PANEL_IDS.length === 37 && new Set(NATIVE_PANEL_IDS).size === 37);
const panelCatalogSource = fs.readFileSync(
  path.join(__dirname, '..', '..', 'pro-shared-ui', 'src', 'workspace', 'panelCatalog.tsx'),
  'utf8',
);
const sharedPanelIds = [
  ...panelCatalogSource.matchAll(/panel\(\{ id: "([a-z0-9-]+)"/g),
].map((match) => match[1]);
sharedPanelIds.push('ai-companions');
assert.deepEqual(
  [...NATIVE_PANEL_IDS].sort(),
  sharedPanelIds.sort(),
  'Electron native panel allowlist drifted from STUDIO_WORKSPACE_PANEL_IDS',
);
passed += 1;

const acquisitionToken = 'acquisition_token_0001';
for (const panelId of NATIVE_PANEL_IDS) {
  const frameName = nativePanelWindowFrameName(panelId, acquisitionToken);
  check(`allowlisted frame round-trips: ${panelId}`,
    panelIdFromNativePanelFrameName(frameName) === panelId);
  assert.deepEqual(
    nativePanelWindowRequestFromFrameName(frameName),
    { panelId, token: acquisitionToken },
    `Native panel acquisition identity did not round-trip: ${panelId}`,
  );
  passed += 1;
}

for (const frameName of [
  'notes',
  'logosforge-panel:',
  'logosforge-panel:notes',
  'logosforge-panel:notes:short',
  'logosforge-panel:unknown',
  'logosforge-panel:unknown:acquisition_token_0001',
  'logosforge-panel:notes:acquisition:token:0001',
  'LOGOSFORGE-PANEL:notes:acquisition_token_0001',
  '_blank',
]) {
  check(`untrusted frame is rejected: ${frameName}`,
    nativePanelWindowRequestFromFrameName(frameName) === null
      && panelIdFromNativePanelFrameName(frameName) === null);
}
assert.throws(
  () => nativePanelWindowFrameName('unknown', acquisitionToken),
  /Unknown native panel id/,
);
assert.throws(
  () => nativePanelWindowFrameName('notes', 'short'),
  /Invalid native panel window token/,
);
passed += 1;

const mainSource = fs.readFileSync(path.join(__dirname, '..', 'electron', 'main.ts'), 'utf8');
const appSource = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'App.tsx'), 'utf8');
const closeHandler = mainSource.match(
  /ipcMain\.handle\(NATIVE_PANEL_WINDOW_CHANNELS\.close[\s\S]*?ipcMain\.handle\(NATIVE_PANEL_WINDOW_CHANNELS\.bounds/,
)?.[0] ?? '';
check('stale release tokens cannot close a replacement panel window',
  closeHandler.includes('entry.token !== token')
    && closeHandler.includes('entry.window.destroy()'));
check('release revokes an exact pending creation without touching a newer reservation',
  closeHandler.includes('pending?.token !== token')
    && closeHandler.includes('pendingNativePanelWindows.delete(panelId)')
    && closeHandler.includes('clearTimeout(pending.timer)'));
const didCreateHandler = mainSource.match(
  /win\.webContents\.on\('did-create-window'[\s\S]*?\n  \}\);\n\}/,
)?.[0] ?? '';
check('late child registration requires its exact live reservation',
  didCreateHandler.includes('pending?.token === token')
    && didCreateHandler.includes('!reservationIsLive || !hostIsLive')
    && didCreateHandler.includes('panelWindow.destroy()'));
check('late child registration rechecks every shutdown state',
  didCreateHandler.includes('mainWindow === win')
    && didCreateHandler.includes('!win.isDestroyed()')
    && didCreateHandler.includes('!closeInProgress')
    && didCreateHandler.includes('!isQuitting')
    && didCreateHandler.includes('!allowClose'));
const openHandler = mainSource.match(
  /win\.webContents\.setWindowOpenHandler[\s\S]*?win\.webContents\.on\('did-create-window'/,
)?.[0] ?? '';
check('a newer acquisition supersedes an undelivered old reservation',
  openHandler.includes('pending?.token === token')
    && openHandler.includes('clearTimeout(pending.timer)')
    && openHandler.includes('pendingNativePanelWindows.set(panelId, { token, timer })'));
check('renderer acquisitions and releases carry one generation token end to end',
  appSource.includes('const token = globalThis.crypto.randomUUID()')
    && appSource.includes('bridge.nativePanelWindowFrameName(panelId, token)')
    && appSource.includes('bridge.closeNativePanelWindow(panelId, current.token)')
    && appSource.includes('event.panelId) !== event.token'));
const restoredHandler = appSource.match(
  /if \(event\.type === 'restored'\)[\s\S]*?\n        return;/,
)?.[0] ?? '';
check('a rejected native restore is rolled back to minimized state',
  restoredHandler.includes('.then((changed) =>')
    && restoredHandler.includes('if (!changed) void bridge.minimizeNativePanelWindow(event.panelId, event.token)'));

const primary = { x: 0, y: 0, width: 1920, height: 1040 };
const left = { x: -1280, y: 0, width: 1280, height: 984 };

assert.deepEqual(
  recoverNativePanelWindowBounds(
    { x: 120, y: 80, width: 640, height: 480 },
    [primary, left],
    primary,
  ),
  { x: 120, y: 80, width: 640, height: 480 },
);
passed += 1;

assert.deepEqual(
  recoverNativePanelWindowBounds(
    { x: -1100, y: 100, width: 600, height: 500 },
    [primary, left],
    left,
  ),
  { x: -1100, y: 100, width: 600, height: 500 },
);
passed += 1;

assert.deepEqual(
  recoverNativePanelWindowBounds(
    { x: 1820, y: 100, width: 600, height: 500 },
    [primary, left],
    primary,
  ),
  { x: 1820, y: 100, width: 600, height: 500 },
);
passed += 1;

assert.deepEqual(
  recoverNativePanelWindowBounds(
    { x: 120, y: -450, width: 640, height: 480 },
    [primary],
    primary,
  ),
  { x: 120, y: 0, width: 640, height: 480 },
  'A visible bottom strip must not count when the title bar is stranded on a removed upper display',
);
passed += 1;

assert.deepEqual(
  recoverNativePanelWindowBounds(
    { x: 5000, y: 3000, width: 700, height: 500 },
    [primary, left],
    primary,
  ),
  { x: 1220, y: 540, width: 700, height: 500 },
);
passed += 1;

assert.deepEqual(
  recoverNativePanelWindowBounds(
    { x: 40, y: 30, width: 3000, height: 2000 },
    [primary],
    primary,
  ),
  primary,
);
passed += 1;

const unchangedWithoutDisplays = { x: 5000, y: 3000, width: 700, height: 500 };
assert.deepEqual(
  recoverNativePanelWindowBounds(unchangedWithoutDisplays, []),
  unchangedWithoutDisplays,
);
passed += 1;

console.log(`Native panel window tests: ${passed} passed, 0 failed`);
