import { app, Menu, shell, type BrowserWindow, type MenuItemConstructorOptions } from 'electron';

/**
 * The application menu. Native roles (undo/copy/zoom/…) are handled by Electron;
 * app-specific items post a `menu:command` string to the renderer, which maps it
 * to the same handlers the sidebar / command palette use (see App.tsx).
 *
 * Command grammar (kept trivial so the renderer dispatcher is a small switch):
 *   "new-project" | "palette" | "focus" | "ai-dock" | "reset-workspace"
 *   "nav:<Panel id>"      → open/focus that workspace panel (e.g. "nav:manuscript")
 *   "ai:<Tool key>"       → open that AI companion (e.g. "ai:Billy")
 *   "skin:forge|paper|lamplit"
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
            { label: 'Settings', click: () => send('nav:settings') },
            { type: 'separator' }, { role: 'hide' }, { role: 'hideOthers' }, { role: 'unhide' },
            { type: 'separator' }, { role: 'quit' },
          ],
        }] as MenuItemConstructorOptions[])
      : []),
    {
      label: 'File',
      submenu: [
        { label: 'New Project', accelerator: 'CmdOrCtrl+N', click: () => send('new-project') },
        { label: 'Open Projects…', click: () => send('nav:projects') },
        { type: 'separator' },
        { label: 'Export…', click: () => send('nav:export') },
        { type: 'separator' },
        ...(!isMac
          ? ([{ label: 'Settings', click: () => send('nav:settings') },
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
        { label: 'Open / Focus AI Companions', click: () => send('ai-dock') },
        { label: 'Reset Workspace Layout', click: () => send('reset-workspace') },
        { type: 'separator' },
        {
          label: 'Skins',
          submenu: [
            { label: 'Forge', click: () => send('skin:forge') },
            { label: 'Paper', click: () => send('skin:paper') },
            { label: 'Lamplit', click: () => send('skin:lamplit') },
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
        {
          label: 'Writing & Project',
          submenu: [
            { label: 'Projects', accelerator: 'CmdOrCtrl+O', click: () => send('nav:projects') },
            { label: 'Dashboard', accelerator: 'CmdOrCtrl+2', click: () => send('nav:dashboard') },
            { label: 'Manuscript', accelerator: 'CmdOrCtrl+1', click: () => send('nav:manuscript') },
            { label: 'Notes', accelerator: 'CmdOrCtrl+Alt+Shift+N', click: () => send('nav:notes') },
            { label: 'Comments', accelerator: 'CmdOrCtrl+Shift+C', click: () => send('nav:comments') },
            { label: "Dexter's Room", accelerator: 'CmdOrCtrl+Alt+Shift+V', click: () => send('nav:dexters-room') },
          ],
        },
        {
          label: 'Plan',
          submenu: [
            { label: 'Outline', accelerator: 'CmdOrCtrl+3', click: () => send('nav:outline') },
            { label: 'Story Grid', accelerator: 'CmdOrCtrl+Alt+Shift+G', click: () => send('nav:story-grid') },
            { label: 'Timeline', accelerator: 'CmdOrCtrl+4', click: () => send('nav:timeline') },
            { label: 'Canvas Plot', accelerator: 'CmdOrCtrl+Alt+Shift+X', click: () => send('nav:canvas-plot') },
            { label: 'Series', accelerator: 'CmdOrCtrl+Alt+Shift+S', click: () => send('nav:series') },
          ],
        },
        {
          label: 'Structure',
          submenu: [
            { label: 'Structure', accelerator: 'CmdOrCtrl+Alt+Shift+U', click: () => send('nav:structure') },
            { label: 'Acts', accelerator: 'CmdOrCtrl+Alt+Shift+A', click: () => send('nav:acts') },
            { label: 'Beats', accelerator: 'CmdOrCtrl+Alt+Shift+B', click: () => send('nav:beats') },
            { label: 'Chapters', accelerator: 'CmdOrCtrl+Alt+Shift+H', click: () => send('nav:chapters') },
            { label: 'Structure Analysis', accelerator: 'CmdOrCtrl+Alt+Shift+R', click: () => send('nav:structure-analysis') },
            { label: 'Format Studio', accelerator: 'CmdOrCtrl+Alt+Shift+F', click: () => send('nav:format-studio') },
          ],
        },
        {
          label: 'Analytics',
          submenu: [
            { label: 'Health', accelerator: 'CmdOrCtrl+Alt+Shift+L', click: () => send('nav:health') },
            { label: 'Pacing', accelerator: 'CmdOrCtrl+Alt+Shift+I', click: () => send('nav:pacing') },
            { label: 'Balance', accelerator: 'CmdOrCtrl+Alt+Shift+E', click: () => send('nav:balance') },
            { label: 'Tags', accelerator: 'CmdOrCtrl+Alt+Shift+T', click: () => send('nav:tags') },
            { label: 'Continuity', accelerator: 'CmdOrCtrl+Alt+Shift+Q', click: () => send('nav:continuity') },
            { label: 'Decision Radar', accelerator: 'CmdOrCtrl+Alt+Shift+W', click: () => send('nav:decision-radar') },
            { label: 'Guided Workflows', accelerator: 'CmdOrCtrl+Alt+Shift+5', click: () => send('nav:guided-workflows') },
            { label: 'Adapt', accelerator: 'CmdOrCtrl+Alt+Shift+6', click: () => send('nav:adapt') },
            { label: 'Review', accelerator: 'CmdOrCtrl+Alt+Shift+7', click: () => send('nav:review') },
          ],
        },
        {
          label: 'Bible',
          submenu: [
            { label: 'PSYKE', accelerator: 'CmdOrCtrl+Alt+Shift+Y', click: () => send('nav:psyke') },
            { label: 'Progressions', accelerator: 'CmdOrCtrl+Alt+Shift+P', click: () => send('nav:progressions') },
            { label: 'Characters', accelerator: 'CmdOrCtrl+Alt+Shift+K', click: () => send('nav:characters') },
            { label: 'Theme Scenes', accelerator: 'CmdOrCtrl+Alt+Shift+8', click: () => send('nav:theme-scenes') },
            { label: 'Graph', accelerator: 'CmdOrCtrl+Alt+Shift+9', click: () => send('nav:graph') },
          ],
        },
        {
          label: 'Tools & Settings',
          submenu: [
            { label: 'Plugins', accelerator: 'CmdOrCtrl+Alt+Shift+0', click: () => send('nav:plugins') },
            { label: 'Connector', accelerator: 'CmdOrCtrl+Alt+Shift+C', click: () => send('nav:connector') },
            { label: 'Export', accelerator: 'CmdOrCtrl+E', click: () => send('nav:export') },
            { label: 'AI Settings', accelerator: 'CmdOrCtrl+Alt+Shift+Z', click: () => send('nav:ai-settings') },
            { label: 'Settings', accelerator: 'CmdOrCtrl+,', click: () => send('nav:settings') },
            { label: 'Help', accelerator: 'CmdOrCtrl+Alt+Shift+D', click: () => send('nav:help') },
          ],
        },
        { type: 'separator' },
        { label: 'AI Companions', accelerator: 'CmdOrCtrl+J', click: () => send('nav:ai-companions') },
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
        { label: 'Help & Syntax Guide', click: () => send('nav:help') },
        { type: 'separator' },
        { label: 'LogosForge on GitHub', click: () => void shell.openExternal('https://github.com/fopearcano/logosforge') },
      ],
    },
  ];

  return Menu.buildFromTemplate(template);
}
