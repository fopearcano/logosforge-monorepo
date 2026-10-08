const fs = require('node:fs');
const path = require('node:path');

const readSource = (...segments) => fs
  .readFileSync(path.join(process.cwd(), ...segments), 'utf8')
  .replace(/\r\n?/g, '\n');

const app = readSource('renderer', 'src', 'App.tsx');
const palette = readSource('renderer', 'src', 'CommandPalette.tsx');
const main = readSource('electron', 'main.ts');
const menu = readSource('electron', 'menu.ts');
const preload = readSource('electron', 'preload.ts');
const styles = readSource('renderer', 'src', 'styles.css');
const mainRenderer = readSource('renderer', 'src', 'main.tsx');
const skinPreference = readSource('renderer', 'src', 'skinPreference.ts');
const panelShortcuts = readSource('..', 'pro-shared-ui', 'src', 'workspace', 'panelShortcuts.ts');
const failures = [];
for (const marker of [
  'bootstrapRetryTimerRef',
  'window.clearTimeout(bootstrapRetryTimerRef.current)',
  'appMountedRef.current',
  'bootstrapRunRef.current === run',
  'let nextProjects = await api.listProjects()',
  'selectStartupProjectId(',
  'loadLastActiveProjectId()',
  'const coreGenerationTrackerRef = useRef(new CoreGenerationTracker())',
  "coreStatusRef.current.state === 'connected'",
  'coreGenerationTrackerRef.current.isCurrent(ownerCoreGeneration)',
  'coreGenerationTrackerRef.current.isCurrent(run.coreGeneration)',
  "if (!isCurrent()) throw new Error('The core changed while opening the startup project.')",
  'return api.openProject(targetProjectId);',
  'const bootstrapBusyOwnerRef = useRef<BootstrapRun | null>(null)',
  'const releaseBootstrapRun = useCallback((run: BootstrapRun | null)',
  'const invalidatedRun = bootstrapRunRef.current',
  'releaseBootstrapRun(invalidatedRun)',
  '!coreGenerationTrackerRef.current.isCurrent(apiCoreGeneration)',
  'bootstrapBusyOwnerRef.current = run',
  'bootstrapBusyOwnerRef.current === run',
  'void persistLastActiveProjectId(opened.id)',
  'void persistLastActiveProjectId(target ?? null)',
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
  "setPendingScene(panelId === 'manuscript' ? opts?.sceneId ?? null : null)",
  "setPendingPsykeEntry(panelId === 'psyke' ? opts?.psykeEntryId ?? null : null)",
  "setPendingNote(panelId === 'notes' ? opts?.noteId ?? null : null)",
  "setPendingComment(panelId === 'comments' ? opts?.commentId ?? null : null)",
  "setPendingKnowledgeGraph(panelId === 'graph' && opts?.graphFocusKey ? {",
  "setPendingContinuityIssue(panelId === 'continuity' ? opts?.continuityIssueKey ?? null : null)",
  'setPendingContinuityRepair(panelId === AI_PANEL_ID ? opts?.continuityRepair ?? null : null)',
  'setPendingNote(null)',
  'setPendingComment(null)',
  'noteTargetId: pendingNote',
  'clearNoteTarget: (noteId) => setPendingNote',
  'commentTargetId: pendingComment',
  'clearCommentTarget: (commentId) => setPendingComment',
]) {
  if (!app.includes(marker)) failures.push(`App note/comment navigation integration missing ${marker}`);
}
for (const marker of [
  'const [projectReady, setProjectReady] = useState(false)',
  'const projectReadyRef = useRef(false)',
  'projectReadyRef.current = false',
  'setProjectReady(false)',
  "const baseUrl = status.state === 'connected' && status.baseUrl ? status.baseUrl : null",
  'if (projectReady)',
  'projectReadyRef.current = true',
  'setProjectReady(true)',
  'if (!projectReadyRef.current) return',
  'if (!projectReady)',
  "enabled: () => projectReadyRef.current && !busy",
  "if (projectReadyRef.current) setPaletteOpen(true)",
  "coreStatusRef.current.state !== 'connected'",
]) {
  if (!app.includes(marker)) failures.push(`App project/bootstrap readiness gate missing ${marker}`);
}
const refreshProjectsBlock = app.match(/const refreshProjects = useCallback[\s\S]*?const changeProjectMode = useCallback/)?.[0] ?? '';
for (const marker of [
  'const refreshSequence = refreshProjectsSequenceRef.current + 1',
  'refreshProjectsSequenceRef.current = refreshSequence',
  'refreshProjectsSequenceRef.current === refreshSequence',
  'if (!isCurrentRefresh()) return []',
]) {
  if (!refreshProjectsBlock.includes(marker)) {
    failures.push(`App project refresh ordering guard missing ${marker}`);
  }
}
if (!/ps = await ownerApi\.listProjects\(\);[\s\S]*?if \(!isCurrentRefresh\(\)\) return \[\];[\s\S]*?setProjects\(ps\)/.test(refreshProjectsBlock)) {
  failures.push('App publishes project refresh results before checking latest-request ownership');
}
const changeProjectModeBlock = app.match(/const changeProjectMode = useCallback[\s\S]*?\n\s*useEffect\(\(\) => \{/)?.[0] ?? '';
for (const marker of [
  'const ownerCoreGeneration = apiCoreGeneration',
  'coreGenerationTrackerRef.current.isCurrent(ownerCoreGeneration)',
  "coreStatusRef.current.state === 'connected'",
  'ownerApi.updateProject(activeId, { narrative_engine: nextMode })',
  'if (!isCurrentCore()) return false',
  'if (isCurrentCore()) setModeBusy(false)',
]) {
  if (!changeProjectModeBlock.includes(marker)) {
    failures.push(`App writing-mode core ownership guard missing ${marker}`);
  }
}
if (!/await flushPendingProjectSaves\(\{ commitActiveField: true \}\);\s*if \(!isCurrentCore\(\) \|\| projectIdRef\.current !== activeId\) return false;[\s\S]*?const committed = await trackProjectWrite\([\s\S]*?\);\s*if \(!isCurrentCore\(\) \|\| projectIdRef\.current !== activeId\) return false;/.test(changeProjectModeBlock)) {
  failures.push('App writing-mode mutation is not guarded before and after the old-client request');
}
if (!/catch \(error\) \{\s*if \(!isCurrentCore\(\)\) return false;/.test(changeProjectModeBlock)) {
  failures.push('App writing-mode failure path can publish an error from a stale core');
}
if (!app.includes('StudioSceneNavigator,')) {
  failures.push('App does not import the shared live scene navigator');
}
if (!/<StudioSceneNavigator[\s\S]{0,500}?onOpenScene=\{\(sceneId\)\s*=>\s*selectPanel\(['"]manuscript['"],\s*\{\s*sceneId\s*\}\)\}/.test(app)) {
  failures.push('Scene navigator does not use the save-barrier-aware manuscript navigation path');
}
if (!/<StudioSceneNavigator[\s\S]{0,500}?onSearch=\{\(\)\s*=>\s*setPaletteOpen\(true\)\}/.test(app)) {
  failures.push('Scene navigator search does not open the existing Studio Omnibox');
}
for (const forbidden of ["cmd.startsWith('nav:')", "cmd.startsWith('ai:')", "cmd.startsWith('theme:')"]) {
  if (app.includes(forbidden)) failures.push(`App still uses the native-menu command switch: ${forbidden}`);
}
for (const marker of [
  'readSkinPreference',
  'writeSkinPreference(skin)',
  'applySkinPreference(skin)',
  'id: `skin:${skinOption.id}`',
  '`theme:${LEGACY_THEME_FOR_SKIN[skinOption.id]}`',
  '`appearance.${LEGACY_THEME_FOR_SKIN[skinOption.id]}`',
  '<WorkspaceShell',
  'skin={skin}',
]) {
  if (!app.includes(marker)) failures.push(`App skin integration missing ${marker}`);
}
for (const marker of [
  "SKIN_STORAGE_KEY = 'lf.skin.v1'",
  "LEGACY_THEME_STORAGE_KEY = 'lf.theme'",
  'resolveSkin(',
  'root.dataset.skin = skin',
  "return 'forge'",
]) {
  if (!skinPreference.includes(marker)) failures.push(`Skin preference helper missing ${marker}`);
}
if (!mainRenderer.includes('applySkinPreference(readSkinPreference())')) {
  failures.push('Renderer does not apply the persisted skin before React mounts');
}
for (const marker of [
  "label: 'Skins'",
  "send('skin:forge')",
  "send('skin:paper')",
  "send('skin:lamplit')",
]) {
  if (!menu.includes(marker)) failures.push(`Native Skins menu missing ${marker}`);
}
for (const marker of [
  ':root[data-skin="forge"]',
  ':root[data-skin="paper"]',
  ':root[data-skin="lamplit"]',
  'font-family: var(--ui-font)',
]) {
  if (!styles.includes(marker)) failures.push(`Desktop skin CSS missing ${marker}`);
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
for (const marker of [
  'panelIdForKeyboardShortcut,',
  'const panelId = panelIdForKeyboardShortcut(e)',
  'visiblePanels.some((panel) => panel.id === panelId)',
  'void selectPanelAndFocus(panelId)',
]) {
  if (!app.includes(marker)) failures.push(`App generic panel-shortcut routing missing ${marker}`);
}
const panelShortcutHandler = app.match(/const handleWorkspaceKeyDown = useCallback[\s\S]*?window\.addEventListener\('keydown', handleWorkspaceKeyDown\);/)?.[0] ?? '';
if (!panelShortcutHandler.includes('panelIdForKeyboardShortcut(e)')
    || !panelShortcutHandler.includes('workspaceHydrated')
    || !panelShortcutHandler.includes('selectPanelAndFocus(panelId)')
    || !panelShortcutHandler.includes('getPanelHostDocuments()')) {
  failures.push('Global panel shortcuts do not use the canonical matcher and hydrated save-aware navigation path');
}
if (!app.includes("window.removeEventListener('keydown', handleWorkspaceKeyDown)")
    || !app.includes('onExternalWindowKeyDown={handleWorkspaceKeyDown}')) {
  failures.push('Global panel shortcuts are not shared with native panel documents');
}
const selectPanelBlock = app.match(/const selectPanel = useCallback[\s\S]*?const panelFocusTarget = useCallback/)?.[0] ?? '';
const selectPanelAndFocusBlock = app.match(/const selectPanelAndFocus = useCallback[\s\S]*?\/\/ Cross-panel navigation/)?.[0] ?? '';
const workspaceMutationBlock = app.match(/const runWorkspaceMutation = useCallback[\s\S]*?const selectPanel = useCallback/)?.[0] ?? '';
if (!selectPanelAndFocusBlock.includes('const task = selectPanel(panelId)')
    || !selectPanelAndFocusBlock.includes('focusAfterWorkspaceAction(task')) {
  failures.push('Panel shortcut/menu navigation does not restore focus through selectPanelAndFocus');
}
if (!selectPanelBlock.includes('runWorkspaceMutation((layout) =>')
    || !workspaceMutationBlock.includes('await flushPendingProjectSaves({ commitActiveField: true })')) {
  failures.push('Panel shortcut/menu navigation bypasses the pending-save workspace barrier');
}
const panelCommandBlock = app.match(/\.\.\.PANELS\.map\(\(panel\) => \(\{[\s\S]*?\}\)\),\s*\{\s*id: `nav:\$\{AI_PANEL_ID\}`/)?.[0] ?? '';
if (!panelCommandBlock.includes('shortcut: panel.shortcut')
    || !panelCommandBlock.includes('? selectPanelAndFocus(panel.id)')
    || !panelCommandBlock.includes('!panel.modes || panel.modes.includes(mode)')
    || !panelCommandBlock.includes(': Promise.resolve(false)')) {
  failures.push('Catalog panel commands do not carry their canonical shortcut into the focus-aware command path');
}
const omniboxPanelsBlock = app.match(/const omniboxPanels = useMemo\([\s\S]*?\/\/ Normalize only mode-ineligible panels/)?.[0] ?? '';
if (!omniboxPanelsBlock.includes('...visiblePanels.map((panel) => ({')
    || omniboxPanelsBlock.includes('...PANELS.map((panel) => ({')) {
  failures.push('Omnibox panels are not restricted to the active writing mode');
}
const aiPanelCommandBlock = app.match(/id: `nav:\$\{AI_PANEL_ID\}`[\s\S]*?\n\s*\},\s*\.\.\.AI_TOOL_KEYS/)?.[0] ?? '';
if (!aiPanelCommandBlock.includes('shortcut: studioPanelShortcut(AI_PANEL_ID)')
    || !aiPanelCommandBlock.includes('run: () => selectPanelAndFocus(AI_PANEL_ID)')) {
  failures.push('AI Companions navigation command is missing its canonical direct shortcut/focus path');
}

const panelMovementBlock = app.match(/const moveDockPanel = useCallback[\s\S]*?const closeDockPanel = useCallback/)?.[0] ?? '';
for (const forbidden of [
  "panelId === 'manuscript'",
  'panelId === AI_PANEL_ID',
]) {
  if (panelMovementBlock.includes(forbidden)) {
    failures.push(`Panel move/float/resize/minimize path still blocks a detachable surface: ${forbidden}`);
  }
}
const openedPanelsBlock = app.match(/const openedPanels = useMemo[\s\S]*?\/\/ One runtime registry/)?.[0] ?? '';
for (const forbidden of [
  'movable: false',
  "movable: panel.id !== 'manuscript'",
]) {
  if (openedPanelsBlock.includes(forbidden)) failures.push(`Opened panel metadata still prevents detachment: ${forbidden}`);
}
const workspaceNormalizationBlock = app.match(/\/\/ Normalize only mode-ineligible panels[\s\S]*?\}, \[mode, runWorkspaceMutation, workspaceHydrated, workspaceLayout\]\);/)?.[0] ?? '';
for (const forbidden of ['aiNeedsHome', 'nextAiPlacement', 'placePanel(next, AI_PANEL_ID']) {
  if (workspaceNormalizationBlock.includes(forbidden)) failures.push(`Workspace normalization still rehomes AI Companions: ${forbidden}`);
}

const shortcutDefinitions = [...panelShortcuts.matchAll(
  /\{ id: "([^"]+)", label: "[^"]+", group: "[^"]+", shortcut: "([^"]+)" \}/g,
)].map((match) => ({
  panelId: match[1],
  accelerator: match[2].replace(/^Primary/, 'CmdOrCtrl').replace('Comma', ','),
}));
const nativeNavEntries = [...menu.matchAll(
  /accelerator: '([^']+)', click: \(\) => send\('nav:([^']+)'\)/g,
)].map((match) => ({ accelerator: match[1], panelId: match[2] }));
if (shortcutDefinitions.length !== 37) {
  failures.push(`Canonical panel shortcut catalog has ${shortcutDefinitions.length} entries instead of 37`);
}
if (nativeNavEntries.length !== 37) {
  failures.push(`Native menu has ${nativeNavEntries.length} accelerated panel entries instead of 37`);
}
if (new Set(nativeNavEntries.map((entry) => entry.accelerator)).size !== 37) {
  failures.push('Native panel accelerators are not unique');
}
if (new Set(nativeNavEntries.map((entry) => entry.panelId)).size !== 37) {
  failures.push('Native menu does not target 37 unique panel ids');
}
const nativeByPanelId = new Map(nativeNavEntries.map((entry) => [entry.panelId, entry.accelerator]));
for (const expected of shortcutDefinitions) {
  if (nativeByPanelId.get(expected.panelId) !== expected.accelerator) {
    failures.push(`Native menu shortcut drift for ${expected.panelId}: expected ${expected.accelerator}`);
  }
}
if (nativeByPanelId.get('ai-companions') !== 'CmdOrCtrl+J'
    || /accelerator: 'CmdOrCtrl\+J'[^\n]+send\('ai-dock'\)/.test(menu)) {
  failures.push('Cmd/Ctrl+J does not directly open/focus AI Companions');
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
  "ipcMain.handle('live-context:publish'",
  "ipcMain.handle('live-context:clear'",
  "ipcMain.handle('session:load'",
  "ipcMain.handle('session:save-last-project'",
  'requireMainRenderer(event);\n    return core.publishLiveContext(payload);',
  'requireMainRenderer(event);\n    return core.clearLiveContextFromRenderer();',
  'requireMainRenderer(event);\n    return loadDesktopSessionState();',
  'return saveLastActiveProjectId(p.projectId);',
  'await core.suspendLiveContext();',
  'await core.stop();',
  'await drainDesktopSessionSaves();',
  'drainDesktopSessionSaves().then(() => core.stop())',
  'core.resumeLiveContext();',
  'if (!allowClose) void core.suspendLiveContext();',
]) {
  if (!main.includes(marker)) failures.push(`Main close protocol missing ${marker}`);
}
const suspendIndex = main.indexOf('await core.suspendLiveContext();');
const postSuspendQuitIndex = main.indexOf('if (isQuitting) {', suspendIndex);
const ordinaryWindowCloseIndex = main.indexOf('win.close();', suspendIndex);
if (
  suspendIndex < 0 ||
  postSuspendQuitIndex <= suspendIndex ||
  ordinaryWindowCloseIndex <= postSuspendQuitIndex
) {
  failures.push('Main close protocol does not preserve Cmd+Q during live-context suspension');
}
for (const marker of [
  "subscribe<number>('app:save-before-close', cb)",
  "subscribe<void>('app:close-cancelled', () => cb())",
  "ipcRenderer.send('app:close-result', attemptId, saved)",
  "ipcRenderer.invoke('live-context:publish', context)",
  "ipcRenderer.invoke('live-context:clear')",
  "ipcRenderer.invoke('session:load')",
  "ipcRenderer.invoke('session:save-last-project', { projectId })",
]) {
  if (!preload.includes(marker)) failures.push(`Preload close protocol missing ${marker}`);
}
for (const forbidden of ['source_id', 'sourceId', 'revision:']) {
  if (preload.includes(forbidden)) {
    failures.push(`Preload exposes main-owned live-context authority: ${forbidden}`);
  }
}

console.log('Desktop lifecycle checks');
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} desktop lifecycle violation(s)`);
console.log('DESKTOP LIFECYCLE TESTS: PASS');
