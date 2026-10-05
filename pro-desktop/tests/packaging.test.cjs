const fs = require('node:fs');
const path = require('node:path');

const {
  bundledCoreExecutableName,
  bundledMcpExecutableName,
  resolveBundledCorePath,
  resolveBundledMcpPath,
} = require('../dist-electron/platform-paths.js');
const {
  readDarwinHostFacts,
  validateDarwinHostFacts,
  validateNativeBinary,
} = require('../scripts/verify-native-release.cjs');
const pkg = JSON.parse(fs.readFileSync(path.join(process.cwd(), 'package.json'), 'utf8'));
const releaseWorkflow = fs.readFileSync(
  path.join(process.cwd(), '..', '.github', 'workflows', 'release-windows.yml'),
  'utf8',
);
const packagedWindowsWorkflow = fs.readFileSync(
  path.join(process.cwd(), '..', '.github', 'workflows', 'ci-packaged-windows.yml'),
  'utf8',
);
const packagedWorkspaceScriptPath = path.join(
  process.cwd(),
  'scripts',
  'packaged-workspace-acceptance.mjs',
);
const packagedWorkspaceScript = fs.readFileSync(packagedWorkspaceScriptPath, 'utf8');
const macJobStart = releaseWorkflow.indexOf('\n  build_macos:');
const macJobEnd = releaseWorkflow.indexOf('\n  publish:', macJobStart);
const macJob = releaseWorkflow.slice(macJobStart, macJobEnd);

let passed = 0;
function check(label, condition) {
  if (!condition) throw new Error(`Packaging test failed: ${label}`);
  passed += 1;
}
function rejects(label, fn) {
  let rejected = false;
  try { fn(); } catch { rejected = true; }
  check(label, rejected);
}

function target(config, name) {
  return config.target.find((entry) => entry.target === name);
}

const extraCore = pkg.build.extraResources.find(
  (entry) => entry.from === 'core/dist/logosforge-core',
);
check('native PyInstaller onedir is copied to resources/core', extraCore?.to === 'core');

check('Windows still builds NSIS x64', target(pkg.build.win, 'nsis')?.arch?.includes('x64'));
check('Windows still builds portable x64', target(pkg.build.win, 'portable')?.arch?.includes('x64'));
check('macOS builds only an Intel x64 DMG',
  pkg.build.mac.target.length === 1 &&
  JSON.stringify(target(pkg.build.mac, 'dmg')?.arch) === JSON.stringify(['x64']));
check('macOS signing is explicitly disabled until credentials are supplied', pkg.build.mac.identity === null);
check('macOS minimum matches Electron 43 Monterey support', pkg.build.mac.minimumSystemVersion === '12.0.0');
check('macOS uses the checked-in high-resolution PNG icon', pkg.build.mac.icon === 'build/icon.png');
const appIcon = fs.readFileSync(path.join(process.cwd(), pkg.build.mac.icon));
check('shared macOS/Linux icon is a 1120px square PNG',
  appIcon.toString('hex', 0, 8) === '89504e470d0a1a0a' &&
  appIcon.readUInt32BE(16) === 1120 && appIcon.readUInt32BE(20) === 1120);
check('macOS declares why Dexter needs microphone access',
  pkg.build.mac.extendInfo.NSMicrophoneUsageDescription.includes('Dexter'));
check('Linux builds only an x64 AppImage',
  pkg.build.linux.target.length === 1 &&
  JSON.stringify(target(pkg.build.linux, 'AppImage')?.arch) === JSON.stringify(['x64']));
check('Linux uses the same checked-in PNG icon', pkg.build.linux.icon === pkg.build.mac.icon);
check('Linux executable name is shell- and AppImage-safe',
  pkg.build.linux.executableName === 'logosforge-pro' &&
  /^[0-9A-Za-z._-]+$/.test(pkg.build.linux.executableName));
check('Linux desktop identity is explicit and synchronized',
  pkg.desktopName === 'logosforge-pro.desktop' &&
  pkg.build.linux.syncDesktopName === true &&
  pkg.desktopName.replace(/\.desktop$/, '') === pkg.build.linux.executableName);
check('AppImage desktop launches do not disable the Chromium sandbox',
  Array.isArray(pkg.build.appImage.executableArgs) &&
  pkg.build.appImage.executableArgs.length === 0);
check('packaged workspace acceptance is an explicit Pro script',
  pkg.scripts['test:packaged-workspace'] === 'node scripts/packaged-workspace-acceptance.mjs' &&
  fs.statSync(packagedWorkspaceScriptPath).isFile());
check('packaged workspace acceptance pins the browserless Electron driver',
  pkg.devDependencies['playwright-core'] === '1.63.0');
check('packaged workspace acceptance drives real pointer interactions and relaunch persistence',
  packagedWorkspaceScript.includes('notesTab.dragTo(workspace') &&
  packagedWorkspaceScript.includes('page.mouse.down()') &&
  packagedWorkspaceScript.includes('Resize left workspace dock') &&
  packagedWorkspaceScript.includes('pointer-authored project layout survived graceful packaged relaunch'));
check('packaged workspace acceptance covers Canvas Plot pointer authoring and persistence',
  packagedWorkspaceScript.includes("selectPanel(page, 'Canvas Plot', 'canvas-plot'") &&
  packagedWorkspaceScript.includes("name: 'Add Canvas Plot block', exact: true") &&
  packagedWorkspaceScript.includes('[data-canvas-node-move-handle]') &&
  packagedWorkspaceScript.includes('[data-canvas-frame-move-handle]') &&
  packagedWorkspaceScript.includes('[data-canvas-frame-resize-handle]') &&
  packagedWorkspaceScript.includes('selected Canvas Plot frame inspector') &&
  packagedWorkspaceScript.includes('move selected Canvas Plot frame away from inspector') &&
  packagedWorkspaceScript.includes('[data-canvas-node-connect-handle]') &&
  packagedWorkspaceScript.includes("getAttribute('data-viewport-ready')") &&
  packagedWorkspaceScript.includes("name: 'Block title', exact: true") &&
  packagedWorkspaceScript.includes("name: 'Block summary', exact: true") &&
  packagedWorkspaceScript.includes('pressSequentially(nodeTitle)') &&
  packagedWorkspaceScript.includes('pressSequentially(nodeSummary)') &&
  packagedWorkspaceScript.includes('pointer-moved Canvas Plot block and flushed its inspector draft') &&
  packagedWorkspaceScript.includes('pointer-flushed Canvas Plot inspector text after relaunch') &&
  packagedWorkspaceScript.includes('expected.nodeTitle') &&
  packagedWorkspaceScript.includes('expected.nodeSummary') &&
  packagedWorkspaceScript.includes("pointerClickCenter(page, sourceHandle, 'start Canvas Plot connection')") &&
  packagedWorkspaceScript.includes("pointerClickCenter(page, targetHandle, 'finish Canvas Plot connection')") &&
  packagedWorkspaceScript.includes('page.mouse.wheel(0, 360)') &&
  packagedWorkspaceScript.includes('prepareCanvasPointerWorkspace(page, board') &&
  packagedWorkspaceScript.includes('restoreCanvasPointerWorkspace(') &&
  packagedWorkspaceScript.includes('Collapse ${region} dock') &&
  packagedWorkspaceScript.includes('Expand ${region} dock') &&
  packagedWorkspaceScript.includes('pointer-safe board size') &&
  packagedWorkspaceScript.includes('pointer-authored Canvas Plot content and viewport survived graceful packaged relaunch'));
check('packaged Windows CI runs and preserves diagnostics for the Pro pointer journey',
  packagedWindowsWorkflow.includes('npm run test:packaged-workspace') &&
  packagedWindowsWorkflow.includes('LOGOSFORGE_PRO_WORKSPACE_ACCEPTANCE_ROOT') &&
  packagedWindowsWorkflow.includes('logosforge-pro-workspace-acceptance-${{ github.run_id }}-${{ github.run_attempt }}'));
check('Windows release candidates pass the same packaged pointer journey',
  releaseWorkflow.includes('Exercise packaged Pro pointer workspace and restart persistence') &&
  releaseWorkflow.includes('npm run test:packaged-workspace') &&
  releaseWorkflow.includes('logosforge-pro-windows-workspace-diagnostics'));
check('generic release script verifies the current native x64 sidecar',
  pkg.scripts.dist.includes('verify-native-release.cjs current x64'));
check('Windows release script verifies a native x64 sidecar',
  pkg.scripts['dist:win'].includes('verify-native-release.cjs win32 x64'));
check('macOS release script enforces a native Intel host',
  pkg.scripts['dist:mac'].includes('verify-native-release.cjs darwin x64'));
check('Linux release script enforces a native x64 host',
  pkg.scripts['dist:linux'].includes('verify-native-release.cjs linux x64'));
check('macOS release job exists as a bounded workflow section',
  macJobStart > 0 && macJobEnd > macJobStart);
check('Monterey release job uses an isolated native Git checkout',
  macJob.includes('working-directory: pro-macos-source') &&
  macJob.includes('Checkout verified source without JavaScript actions') &&
  !macJob.includes('uses: actions/checkout@'));
check('Monterey release job bootstraps a checksum-pinned native Node 22',
  macJob.includes('NODE_VERSION: "22.23.3"') &&
  macJob.includes('NODE_ARCHIVE_SHA256:') &&
  !macJob.includes('uses: actions/setup-node@'));
check('Monterey build-only job preserves its verified DMG on the host',
  macJob.includes("if: needs.metadata.outputs.publish != 'true'") &&
  macJob.includes('macos-build-drop/run-${GITHUB_RUN_ID}-attempt-${GITHUB_RUN_ATTEMPT}'));
check('Node 24 artifact actions run only on supported publishing hosts',
  (macJob.match(/if: needs\.metadata\.outputs\.publish == 'true'/g) || []).length === 2 &&
  (macJob.match(/uses: actions\/upload-artifact@/g) || []).length === 2 &&
  macJob.includes('working-directory: pro-macos-source/pro-desktop') &&
  macJob.includes('path: ${{ github.workspace }}/pro-macos-source/pro-desktop/release/*.dmg') &&
  macJob.includes('requires macOS 13.5+') &&
  macJob.includes('require Actions Runner >=2.327.1'));
check('Monterey job pins and verifies the macOS 12 deployment floor',
  macJob.includes('MACOSX_DEPLOYMENT_TARGET: "12.0"') &&
  macJob.includes('test "$minimum_version" = "12.0.0"') &&
  macJob.includes('Expected packaged Electron 43.x'));
check('Monterey job uses the direct tested Mach-O parser instead of otool',
  (macJob.match(/whiteboard-desktop\/scripts\/check-macos-deployment-targets\.py/g) || []).length === 3 &&
  macJob.includes('--self-test') &&
  macJob.includes('--maximum 12.0.0') &&
  !macJob.includes('otool'));

check('Windows bundled core uses .exe', bundledCoreExecutableName('win32') === 'logosforge-core.exe');
check('macOS bundled core has no extension', bundledCoreExecutableName('darwin') === 'logosforge-core');
check('Linux bundled core has no extension', bundledCoreExecutableName('linux') === 'logosforge-core');
check('Windows MCP companion uses .exe', bundledMcpExecutableName('win32') === 'logosforge-mcp.exe');
check('macOS MCP companion has no extension', bundledMcpExecutableName('darwin') === 'logosforge-mcp');
check('Linux MCP companion has no extension', bundledMcpExecutableName('linux') === 'logosforge-mcp');
check('Windows bundled core resolves under resources/core',
  resolveBundledCorePath(path.join('C:', 'app', 'resources'), 'win32') ===
    path.join('C:', 'app', 'resources', 'core', 'logosforge-core.exe'));
check('macOS bundled core resolves under resources/core',
  resolveBundledCorePath('/Applications/LogosForge Pro.app/Contents/Resources', 'darwin') ===
    path.join('/Applications/LogosForge Pro.app/Contents/Resources', 'core', 'logosforge-core'));
check('Linux bundled core resolves under resources/core',
  resolveBundledCorePath('/tmp/.mount/Resources', 'linux') ===
    path.join('/tmp/.mount/Resources', 'core', 'logosforge-core'));
check('Windows MCP companion resolves under resources/mcp',
  resolveBundledMcpPath(path.join('C:', 'app', 'resources'), 'win32') ===
    path.join('C:', 'app', 'resources', 'mcp', 'logosforge-mcp.exe'));
check('macOS MCP companion resolves under resources/mcp',
  resolveBundledMcpPath('/Applications/LogosForge Pro.app/Contents/Resources', 'darwin') ===
    path.join('/Applications/LogosForge Pro.app/Contents/Resources', 'mcp', 'logosforge-mcp'));
check('Linux MCP companion resolves under resources/mcp',
  resolveBundledMcpPath('/tmp/.mount/Resources', 'linux') ===
    path.join('/tmp/.mount/Resources', 'mcp', 'logosforge-mcp'));

const machO = Buffer.alloc(32);
machO.writeUInt32LE(0xfeedfacf, 0);
machO.writeUInt32LE(0x01000007, 4);
const elf = Buffer.alloc(64);
Buffer.from([0x7f, 0x45, 0x4c, 0x46, 2, 1]).copy(elf);
elf.writeUInt16LE(0x3e, 18);
const pe = Buffer.alloc(256);
pe.write('MZ', 0, 'ascii');
pe.writeUInt32LE(0x80, 0x3c);
pe.write('PE\0\0', 0x80, 'ascii');
pe.writeUInt16LE(0x8664, 0x84);

check('native preflight accepts Mach-O x86_64', validateNativeBinary(machO, 'darwin', 'x64') === 'Mach-O x86_64');
check('native preflight accepts ELF x86_64', validateNativeBinary(elf, 'linux', 'x64') === 'ELF x86_64');
check('native preflight accepts PE x86_64', validateNativeBinary(pe, 'win32', 'x64') === 'PE x86_64');
rejects('native preflight rejects a Linux sidecar for macOS', () => validateNativeBinary(elf, 'darwin', 'x64'));
rejects('native preflight rejects a macOS sidecar for Linux', () => validateNativeBinary(machO, 'linux', 'x64'));
check('macOS host preflight accepts native macOS 12+',
  validateDarwinHostFacts({ translated: '0', productVersion: '12.7.6' }) === undefined);
rejects('macOS host preflight rejects Rosetta', () =>
  validateDarwinHostFacts({ translated: '1', productVersion: '15.6' }));
rejects('macOS host preflight rejects macOS 11', () =>
  validateDarwinHostFacts({ translated: '0', productVersion: '11.7.10' }));
rejects('macOS host preflight rejects malformed OS versions', () =>
  validateDarwinHostFacts({ translated: '0', productVersion: 'unknown' }));
const darwinFactCalls = [];
const darwinFacts = readDarwinHostFacts((file, args) => {
  darwinFactCalls.push(`${file} ${args.join(' ')}`);
  return file.endsWith('sysctl') ? '0\n' : '15.6.1\n';
});
check('macOS host facts query Rosetta translation state',
  darwinFactCalls[0] === '/usr/sbin/sysctl -in sysctl.proc_translated' && darwinFacts.translated === '0');
check('macOS host facts query the product version',
  darwinFactCalls[1] === '/usr/bin/sw_vers -productVersion' && darwinFacts.productVersion === '15.6.1');

console.log(`Electron packaging tests: ${passed} passed, 0 failed`);

require('./mcp-runtime.test.cjs');
