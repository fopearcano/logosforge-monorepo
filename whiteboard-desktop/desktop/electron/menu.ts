/**
 * Native application menu (main process). Built explicitly so the macOS menu bar
 * reliably shows the full App + File menus; set via `Menu.setApplicationMenu`
 * after the app is ready.
 *
 *  - File ops post `menu:file` to the renderer (one shared action pathway) and
 *    log `[menu] … clicked` to the terminal.
 *  - Close Window uses the `close` role (Cmd/Ctrl+W) → routes through the window
 *    close guard, which runs the unsaved-changes prompt.
 *  - View toggles use `registerAccelerator: false` (handled by the renderer's
 *    keydown). Cmd/Ctrl+K is intentionally absent — it stays Logos.
 */

import { app, BrowserWindow, Menu, type MenuItemConstructorOptions } from 'electron';

interface MenuDeps {
  getWindow: () => BrowserWindow | null;
}

export function setAppMenu({ getWindow }: MenuDeps): void {
  const isMac = process.platform === 'darwin';
  const fileAction = (action: string) => {
    console.log(`[menu] ${action} clicked`);
    getWindow()?.webContents.send('menu:file', action);
  };
  const viewAction = (action: string) => getWindow()?.webContents.send('menu:view', action);

  const appMenu: MenuItemConstructorOptions = {
    label: app.name,
    submenu: [
      { role: 'about' },
      { type: 'separator' },
      { role: 'services' },
      { type: 'separator' },
      { role: 'hide' },
      { role: 'hideOthers' },
      { role: 'unhide' },
      { type: 'separator' },
      { role: 'quit' },
    ],
  };

  const importSubmenu: MenuItemConstructorOptions = {
    label: 'Import',
    submenu: [
      { label: 'Import Text…', click: () => fileAction('import:txt') },
      { label: 'Import Markdown…', click: () => fileAction('import:md') },
      { label: 'Import Fountain…', click: () => fileAction('import:fountain') },
      { label: 'Import LogosForge…', click: () => fileAction('import:logosforge') },
      { label: 'Import Final Draft…', click: () => fileAction('import:fdx') },
    ],
  };

  const exportSubmenu: MenuItemConstructorOptions = {
    label: 'Export',
    submenu: [
      { label: 'Export Project (.lfbundle)…', click: () => fileAction('export:project-bundle') },
      { type: 'separator' },
      { label: 'Export as Text…', click: () => fileAction('export:txt') },
      { label: 'Export as Markdown…', click: () => fileAction('export:md') },
      { label: 'Export as Fountain…', click: () => fileAction('export:fountain') },
      { label: 'Export as LogosForge…', click: () => fileAction('export:logosforge') },
      { label: 'Export as JSON…', click: () => fileAction('export:json') },
      { label: 'Export as HTML…', click: () => fileAction('export:html') },
      { type: 'separator' },
      { label: 'Export as PDF…', click: () => fileAction('export:pdf') },
      { label: 'Export Comments…', click: () => fileAction('export:comments') },
    ],
  };

  const fileMenu: MenuItemConstructorOptions = {
    label: 'File',
    submenu: [
      { label: 'New', accelerator: 'CmdOrCtrl+N', click: () => fileAction('new') },
      { label: 'Open…', accelerator: 'CmdOrCtrl+O', click: () => fileAction('open') },
      { type: 'separator' },
      { label: 'Save', accelerator: 'CmdOrCtrl+S', click: () => fileAction('save') },
      { label: 'Save As…', accelerator: 'CmdOrCtrl+Shift+S', click: () => fileAction('save-as') },
      { type: 'separator' },
      importSubmenu,
      exportSubmenu,
      { type: 'separator' },
      { role: 'close', label: 'Close Window' }, // Cmd/Ctrl+W → window close guard
      ...((isMac ? [] : [{ type: 'separator' }, { role: 'quit' }]) as MenuItemConstructorOptions[]),
    ],
  };

  const editMenu: MenuItemConstructorOptions = {
    label: 'Edit',
    submenu: [
      { role: 'undo' },
      { role: 'redo' },
      { type: 'separator' },
      { role: 'cut' },
      { role: 'copy' },
      { role: 'paste' },
      { role: 'selectAll' },
    ],
  };

  const viewMenu: MenuItemConstructorOptions = {
    label: 'View',
    submenu: [
      {
        label: 'Toggle Top Panel',
        accelerator: 'CmdOrCtrl+Shift+T',
        registerAccelerator: false,
        click: () => viewAction('toggleTopPanel'),
      },
      {
        label: 'Toggle Outline',
        accelerator: 'CmdOrCtrl+Shift+O',
        registerAccelerator: false,
        click: () => viewAction('toggleOutline'),
      },
      {
        label: 'Toggle PSYKE',
        accelerator: 'CmdOrCtrl+Shift+P',
        registerAccelerator: false,
        click: () => viewAction('togglePsyke'),
      },
      {
        label: 'Toggle Story Map',
        accelerator: 'CmdOrCtrl+Shift+M',
        registerAccelerator: false,
        click: () => viewAction('toggleStoryMap'),
      },
      {
        label: 'Focus Mode',
        accelerator: 'CmdOrCtrl+Shift+D',
        registerAccelerator: false,
        click: () => viewAction('focusMode'),
      },
      {
        label: 'Toggle Comments',
        accelerator: 'CmdOrCtrl+Shift+C',
        registerAccelerator: false,
        click: () => viewAction('toggleComments'),
      },
      { type: 'separator' },
      { label: 'Toggle Theme', click: () => viewAction('toggleTheme') },
      { type: 'separator' },
      { role: 'reload' },
      { role: 'toggleDevTools' },
      { role: 'togglefullscreen' },
    ],
  };

  const windowMenu: MenuItemConstructorOptions = { label: 'Window', role: 'windowMenu' };

  const template: MenuItemConstructorOptions[] = [
    ...(isMac ? [appMenu] : []),
    fileMenu,
    editMenu,
    viewMenu,
    ...(isMac ? [windowMenu] : []),
  ];

  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
  console.log('[menu] application menu set');
}
