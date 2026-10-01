const fs = require('node:fs');
const path = require('node:path');

const app = fs.readFileSync(path.join(process.cwd(), 'renderer', 'src', 'App.tsx'), 'utf8');
const palette = fs.readFileSync(path.join(process.cwd(), 'renderer', 'src', 'CommandPalette.tsx'), 'utf8');
const main = fs.readFileSync(path.join(process.cwd(), 'electron', 'main.ts'), 'utf8');
const preload = fs.readFileSync(path.join(process.cwd(), 'electron', 'preload.ts'), 'utf8');
const failures = [];
for (const marker of [
  'bootstrapRetryTimerRef',
  'window.clearTimeout(bootstrapRetryTimerRef.current)',
  'appMountedRef.current',
  'bootstrapRunRef.current === run',
  'const ps = await api.listProjects()',
  'liveEventSeen',
  'return () => { active = false; unsubscribe(); }',
  'Preparing your project…',
  'createDeferredDisposer<ApiClient>',
  'apiDisposer.acquire(api)',
  'const operationQueue = useRef<Promise<void>>',
  'const targetProjectId = projectIdRef.current',
  'workspaceHydratedProjectRef.current !== targetProjectId',
  'const queuedOperations = operationQueue.current',
  'queuedOperations.then(() => flushPendingProjectSaves',
  'closingRef.current = true',
  'if (closingRef.current) return false',
  'setClosePending(true)',
  'setClosePending(false)',
  'onCloseCancelled',
  'sendCloseResult(attemptId, true)',
]) {
  if (!app.includes(marker)) failures.push(`App bootstrap ownership missing ${marker}`);
}
for (const marker of [
  '...workspaceLayout.docks.left.panelIds',
  '...workspaceLayout.floatingPanels.map((panel) => panel.panelId)',
  'onFloat={floatWorkspacePanel}',
  'onMoveFloating={moveWorkspaceFloatingPanel}',
  'onMinimizeFloating={changeFloatingPanelMinimized}',
  'bringFloatingPanelToFront(layout, panelId)',
]) {
  if (!app.includes(marker)) failures.push(`App Phase 2 workspace integration missing ${marker}`);
}
for (const marker of [
  'STUDIO_AI_COMPANIONS_PANEL_ID,',
  'STUDIO_PANELS,',
  'STUDIO_WORKSPACE_PANEL_IDS,',
  'findStudioPanel,',
  'studioPanelGroupsForMode,',
  'const PANELS = STUDIO_PANELS',
  'const ALL_PANEL_IDS = STUDIO_WORKSPACE_PANEL_IDS',
  'const resolvePanel = findStudioPanel',
  '() => studioPanelGroupsForMode(mode)',
]) {
  if (!app.includes(marker)) failures.push(`App shared panel catalog integration missing ${marker}`);
}
for (const forbidden of [
  'interface Panel {',
  'interface PanelGroup {',
  'const PANEL_GROUPS: PanelGroup[]',
  "{ id: 'projects', label: 'Projects'",
  "{ id: 'manuscript', label: 'Manuscript'",
]) {
  if (app.includes(forbidden)) failures.push(`App duplicates shared panel catalog data: ${forbidden}`);
}
for (const marker of [
  'createCommandRegistry(commands)',
  'registry={commandRegistry}',
  'commandRegistry.execute(cmd)',
  'showConsole',
  'runtimeStatus={workspaceStatus}',
  'psykeTargetEntryId: pendingPsykeEntry',
  'clearPsykeTarget: (entryId) => setPendingPsykeEntry',
]) {
  if (!app.includes(marker)) failures.push(`App command/status/PSYKE Console integration missing ${marker}`);
}
for (const marker of [
  'type StudioNavigationOptions,',
  'const [pendingNote, setPendingNote] = useState<number | null>(null)',
  'const [pendingComment, setPendingComment] = useState<number | null>(null)',
  'setPendingNote(opts?.noteId ?? null)',
  'setPendingComment(opts?.commentId ?? null)',
  'setPendingNote(null)',
  'setPendingComment(null)',
  'noteTargetId: pendingNote',
  'clearNoteTarget: (noteId) => setPendingNote',
  'commentTargetId: pendingComment',
  'clearCommentTarget: (commentId) => setPendingComment',
]) {
  if (!app.includes(marker)) failures.push(`App note/comment navigation integration missing ${marker}`);
}
for (const forbidden of ["cmd.startsWith('nav:')", "cmd.startsWith('ai:')", "cmd.startsWith('theme:')"]) {
  if (app.includes(forbidden)) failures.push(`App still uses the native-menu command switch: ${forbidden}`);
}
if (!palette.includes('<StudioOmnibox')) {
  failures.push('Desktop CommandPalette does not delegate to the shared StudioOmnibox');
}
for (const marker of [
  'type StudioNavigationOptions,',
  'options?: StudioNavigationOptions',
  'onNavigate={onNavigate}',
]) {
  if (!palette.includes(marker)) failures.push(`Desktop CommandPalette navigation contract missing ${marker}`);
}
for (const marker of [
  'parseRecentProjectIds',
  'rememberRecentProject',
  'lf.omnibox.recent-projects.v1',
  'recentProjectIds={recentProjectIds}',
  'panels={omniboxPanels}',
  'projects={projects}',
  'onNavigate={selectPanel}',
  'onSelectProject={selectProject}',
]) {
  if (!app.includes(marker)) failures.push(`App StudioOmnibox host integration missing ${marker}`);
}
if (!/id:\s*`nav:\$\{panel\.id\}`/.test(app)) {
  failures.push('Panel commands do not use stable panel-id command ids');
}
if (!/aliases:\s*\[\s*`nav:\$\{panel\.label\}`,\s*`go-\$\{panel\.label\}`\s*\]/s.test(app)) {
  failures.push('Panel commands do not retain the legacy display-label aliases');
}
if (!/id:\s*`nav:\$\{panel\.id\}`[\s\S]{0,600}?showInOmnibox:\s*false/.test(app)) {
  failures.push('Panel commands are not hidden from duplicate omnibox command results');
}
if (!/!e\.repeat[\s\S]{0,180}?e\.key\.toLowerCase\(\) === ['"]k['"][\s\S]{0,180}?setPaletteOpen\(true\)/.test(app)) {
  failures.push('Ctrl/Cmd+K is not an idempotent, repeat-safe omnibox opener');
}
if (/cmd === ['"]palette['"][\s\S]{0,160}?setPaletteOpen\(\([^)]*=>\s*!/.test(app)) {
  failures.push('Native palette command still toggles instead of idempotently opening the omnibox');
}
if (app.includes('const unsupportedIsOpen') || app.includes('const unsupported = [')) {
  failures.push('App still rehomes supported left/floating placements into the center dock');
}
if (app.includes('window.setTimeout(() => setBootstrapAttempt')) {
  failures.push('App still creates an unowned bootstrap retry timer');
}
for (const marker of [
  'let nextCloseAttemptId = 1',
  "win.webContents.send('app:save-before-close', attemptId)",
  'pendingCloseResult?.attemptId !== attemptId',
  "win.webContents.send('app:close-cancelled')",
]) {
  if (!main.includes(marker)) failures.push(`Main close protocol missing ${marker}`);
}
for (const marker of [
  "subscribe<number>('app:save-before-close', cb)",
  "subscribe<void>('app:close-cancelled', () => cb())",
  "ipcRenderer.send('app:close-result', attemptId, saved)",
]) {
  if (!preload.includes(marker)) failures.push(`Preload close protocol missing ${marker}`);
}

console.log('Desktop lifecycle checks');
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} desktop lifecycle violation(s)`);
console.log('DESKTOP LIFECYCLE TESTS: PASS');
