import { app, Menu, shell, type BrowserWindow, type MenuItemConstructorOptions } from 'electron';

/**
 * The application menu. Native roles (undo/copy/zoom/…) are handled by Electron;
 * app-specific items post a `menu:command` string to the renderer, which maps it
 * to the same handlers the sidebar / command palette use (see App.tsx).
 *
 * Command grammar (kept trivial so the renderer dispatcher is a small switch):
 *   "new-project" | "palette" | "focus" | "ai-dock"
 *   "nav:<Panel label>"   → select that left-nav panel (e.g. "nav:Manuscript")
 *   "ai:<Tool key>"       → open that AI companion (e.g. "ai:Billy")
 *   "theme:dark|light|warm"
 */
export function buildAppMenu(getWin: () => BrowserWindow | null): Menu {
  const send = (cmd: string) => getWin()?.webContents.send('menu:command', cmd);
  const isMac = process.platform === 'darwin';
  const devOnly: MenuItemConstructorOptions[] = app.isPackaged
    ? []
    : [{ type: 'separator' }, { role: 'reload' }, { role: 'forceReload' }, { role: 'toggleDevTools' }];

  const template: MenuItemConstructorOptions[] = [
    // macOS app menu (no-op on Windows, where we ship — kept for correctness).
    ...(isMac
      ? ([{
          label: app.name,
          submenu: [
            { role: 'about' }, { type: 'separator' },
            { label: 'Settings', accelerator: 'Cmd+,', click: () => send('nav:Settings') },
            { type: 'separator' }, { role: 'hide' }, { role: 'hideOthers' }, { role: 'unhide' },
            { type: 'separator' }, { role: 'quit' },
          ],
        }] as MenuItemConstructorOptions[])
      : []),
    {
      label: 'File',
      submenu: [
        { label: 'New Project', accelerator: 'CmdOrCtrl+N', click: () => send('new-project') },
        { label: 'Open Projects…', accelerator: 'CmdOrCtrl+O', click: () => send('nav:Projects') },
        { type: 'separator' },
        { label: 'Export…', accelerator: 'CmdOrCtrl+E', click: () => send('nav:Export') },
        { type: 'separator' },
        ...(!isMac
          ? ([{ label: 'Settings', accelerator: 'CmdOrCtrl+,', click: () => send('nav:Settings') },
             { type: 'separator' },
             { role: 'quit' }] as MenuItemConstructorOptions[])
          : ([{ role: 'close' }] as MenuItemConstructorOptions[])),
      ],
    },
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' }, { role: 'redo' }, { type: 'separator' },
        { role: 'cut' }, { role: 'copy' }, { role: 'paste' }, { role: 'selectAll' },
        { type: 'separator' },
        { label: 'Command Palette…', accelerator: 'CmdOrCtrl+K', click: () => send('palette') },
      ],
    },
    {
      label: 'View',
      submenu: [
        { label: 'Focus Mode', accelerator: 'CmdOrCtrl+Shift+F', click: () => send('focus') },
        { label: 'Toggle AI Dock', accelerator: 'CmdOrCtrl+J', click: () => send('ai-dock') },
        { type: 'separator' },
        {
          label: 'Appearance',
          submenu: [
            { label: 'Dark', click: () => send('theme:dark') },
            { label: 'Light', click: () => send('theme:light') },
            { label: 'Warm — Old Wood', click: () => send('theme:warm') },
          ],
        },
        { type: 'separator' },
        { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' },
        ...devOnly,
      ],
    },
    {
      label: 'Go',
      submenu: [
        { label: 'Manuscript', accelerator: 'CmdOrCtrl+1', click: () => send('nav:Manuscript') },
        { label: 'Dashboard', accelerator: 'CmdOrCtrl+2', click: () => send('nav:Dashboard') },
        { label: 'Outline', accelerator: 'CmdOrCtrl+3', click: () => send('nav:Outline') },
        { label: 'Timeline', accelerator: 'CmdOrCtrl+4', click: () => send('nav:Timeline') },
        { label: 'Story Grid', click: () => send('nav:Story Grid') },
        { label: 'Structure', click: () => send('nav:Structure') },
        { label: 'PSYKE Bible', click: () => send('nav:PSYKE') },
        { label: 'Knowledge Graph', click: () => send('nav:Graph') },
        { label: 'Notes', click: () => send('nav:Notes') },
        { type: 'separator' },
        { label: "Dexter's Room — Voice", click: () => send("nav:Dexter's Room") },
      ],
    },
    {
      label: 'AI',
      submenu: [
        { label: 'Billy — Project Assistant', click: () => send('ai:Billy') },
        { label: 'Logos — Line Editor', click: () => send('ai:Logos') },
        { label: 'Quantum — Outliner', click: () => send('ai:Quantum') },
        { label: 'Counterpart', click: () => send('ai:Counterpart') },
        { label: 'Extraction', click: () => send('ai:Extraction') },
      ],
    },
    {
      label: 'Window',
      submenu: [
        { role: 'minimize' }, { role: 'zoom' },
        ...(isMac
          ? ([{ type: 'separator' }, { role: 'front' }] as MenuItemConstructorOptions[])
          : ([{ role: 'close' }] as MenuItemConstructorOptions[])),
      ],
    },
    {
      role: 'help',
      submenu: [
        { label: 'Help & Syntax Guide', click: () => send('nav:Help') },
        { type: 'separator' },
        { label: 'LogosForge on GitHub', click: () => void shell.openExternal('https://github.com/fopearcano/logosforge') },
      ],
    },
  ];

  return Menu.buildFromTemplate(template);
}
