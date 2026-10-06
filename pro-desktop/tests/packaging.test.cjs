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
const linuxJobStart = releaseWorkflow.indexOf('\n  build_linux:');
const linuxJobEnd = releaseWorkflow.indexOf('\n  build_macos:', linuxJobStart);
const linuxJob = releaseWorkflow.slice(linuxJobStart, linuxJobEnd);
const linuxAcceptanceStepStart = linuxJob.indexOf(
  '\n      - name: Exercise packaged Linux Pro pointer workspace and restart persistence',
);
const linuxAcceptanceStepEnd = linuxJob.indexOf('\n      - name:', linuxAcceptanceStepStart + 1);
const linuxAcceptanceStep = linuxJob.slice(linuxAcceptanceStepStart, linuxAcceptanceStepEnd);
const linuxDiagnosticsStepStart = linuxJob.indexOf(
  '\n      - name: Upload Linux packaged-workspace failure diagnostics',
);
const linuxDiagnosticsStepEnd = linuxJob.indexOf('\n      - name:', linuxDiagnosticsStepStart + 1);
const linuxDiagnosticsStep = linuxJob.slice(linuxDiagnosticsStepStart, linuxDiagnosticsStepEnd);
const macJobStart = releaseWorkflow.indexOf('\n  build_macos:');
const macJobEnd = releaseWorkflow.indexOf('\n  ingest_macos:', macJobStart);
const macJob = releaseWorkflow.slice(macJobStart, macJobEnd);
const macIngestJobStart = macJobEnd;
const macIngestJobEnd = releaseWorkflow.indexOf('\n  publish:', macIngestJobStart);
const macIngestJob = releaseWorkflow.slice(macIngestJobStart, macIngestJobEnd);
const publishJobStart = macIngestJobEnd;
const publishJob = releaseWorkflow.slice(publishJobStart);

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
check('packaged workspace acceptance supports native Windows, macOS, and Linux layouts',
  packagedWorkspaceScript.includes("process.platform === 'win32' || process.platform === 'darwin' || process.platform === 'linux'") &&
  packagedWorkspaceScript.includes('const DEFAULT_LINUX_EXE = path.join(') &&
  packagedWorkspaceScript.includes("'linux-unpacked',") &&
  packagedWorkspaceScript.includes("'logosforge-pro',") &&
  packagedWorkspaceScript.includes("if (!requested && process.platform === 'linux') requested = DEFAULT_LINUX_EXE;") &&
  packagedWorkspaceScript.includes("process.platform === 'win32' || process.platform === 'linux'") &&
  packagedWorkspaceScript.includes("return path.join(path.dirname(exePath), 'resources');") &&
  packagedWorkspaceScript.includes("path.resolve(path.dirname(exePath), '..', 'Resources')") &&
  packagedWorkspaceScript.includes("process.platform === 'win32' ? 'logosforge-core.exe' : 'logosforge-core'") &&
  packagedWorkspaceScript.includes("process.platform === 'win32' ? 'logosforge-mcp.exe' : 'logosforge-mcp'"));
check('packaged workspace acceptance explicitly requires Chromium sandboxing',
  packagedWorkspaceScript.includes('chromiumSandbox: true') &&
  packagedWorkspaceScript.includes("app.commandLine.hasSwitch('no-sandbox')") &&
  /assert\.equal\(\s*runtime\.hasNoSandboxSwitch,\s*false,/.test(packagedWorkspaceScript) &&
  packagedWorkspaceScript.includes('`${session.label} launched Chromium with --no-sandbox`'));
check('packaged workspace acceptance uses native shortcuts and graceful macOS app quit',
  packagedWorkspaceScript.includes("process.platform === 'darwin' ? 'Meta+A' : 'Control+A'") &&
  packagedWorkspaceScript.includes("if (process.platform === 'darwin') app.quit()") &&
  packagedWorkspaceScript.includes("fallback SIGTERM for owned process group"));
check('packaged workspace acceptance tears down the Linux/macOS process group safely',
  packagedWorkspaceScript.includes("process.platform === 'darwin' || process.platform === 'linux'") &&
  packagedWorkspaceScript.includes('process.kill(-session.pid, signal)') &&
  packagedWorkspaceScript.includes('process.kill(-session.pid, 0)') &&
  packagedWorkspaceScript.includes("if (error?.code !== 'ESRCH') throw error") &&
  packagedWorkspaceScript.includes('while (processGroupExists())') &&
  packagedWorkspaceScript.includes("signalProcessGroup('SIGTERM')") &&
  packagedWorkspaceScript.includes('if (await waitForProcessGroupExit(10_000)) return') &&
  packagedWorkspaceScript.includes("signalProcessGroup('SIGKILL')") &&
  packagedWorkspaceScript.includes('if (!await waitForProcessGroupExit(5_000))') &&
  packagedWorkspaceScript.includes('survived SIGKILL') &&
  !packagedWorkspaceScript.includes("session.child.kill('SIGTERM')") &&
  !packagedWorkspaceScript.includes("session.child.kill('SIGKILL')"));
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
check('Linux release candidates pass the same unpacked packaged pointer journey under one Xvfb',
  linuxJobStart > 0 && linuxJobEnd > linuxJobStart &&
  linuxAcceptanceStepStart > 0 && linuxAcceptanceStepEnd > linuxAcceptanceStepStart &&
  linuxAcceptanceStep.includes('release/linux-unpacked/logosforge-pro') &&
  linuxAcceptanceStep.includes('LOGOSFORGE_PRO_WORKSPACE_ACCEPTANCE_ROOT') &&
  linuxAcceptanceStep.includes('test ! -e "$LOGOSFORGE_PRO_WORKSPACE_ACCEPTANCE_ROOT"') &&
  linuxAcceptanceStep.includes('--server-args="-screen 0 1600x1000x24"') &&
  (linuxAcceptanceStep.match(/xvfb-run/g) || []).length === 1 &&
  linuxAcceptanceStep.includes('npm --prefix pro-desktop run test:packaged-workspace'));
check('Linux packaged-workspace diagnostics upload only on failure',
  linuxDiagnosticsStepStart > 0 && linuxDiagnosticsStepEnd > linuxDiagnosticsStepStart &&
  linuxDiagnosticsStep.includes('if: failure()') &&
  linuxDiagnosticsStep.includes('logosforge-pro-linux-workspace-diagnostics-') &&
  linuxDiagnosticsStep.includes('logosforge-pro-linux-workspace-acceptance-') &&
  linuxDiagnosticsStep.includes('include-hidden-files: true'));
check('macOS release candidates pass the same packaged pointer journey',
  macJob.includes('Exercise packaged macOS Pro pointer workspace and restart persistence') &&
  macJob.includes('LOGOSFORGE_PRO_WORKSPACE_ACCEPTANCE_EXE="$app_exe"') &&
  macJob.includes('LOGOSFORGE_PRO_WORKSPACE_ACCEPTANCE_ROOT="$ACCEPTANCE_ROOT"') &&
  macJob.includes('npm --prefix pro-desktop run test:packaged-workspace'));
check('Monterey retains packaged-workspace failure diagnostics without JavaScript actions',
  macJob.includes('Preserve macOS packaged-workspace failure diagnostics on the host') &&
  macJob.includes('if: failure()') &&
  macJob.includes('acceptance-diagnostics') &&
  macJob.includes('cp -R -- "$ACCEPTANCE_ROOT"/. "$drop"/'));
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
  macJob.includes('Preserve build-only or failed-handoff Monterey candidate on the Mac host') &&
  macJob.includes("needs.metadata.outputs.publish != 'true' || steps.handoff.outcome != 'success'") &&
  macJob.includes('macos-build-drop/run-${GITHUB_RUN_ID}-attempt-${GITHUB_RUN_ATTEMPT}'));
check('Monterey release job cannot execute JavaScript actions and has only package handoff write access',
  !macJob.includes('\n        uses:') &&
  macJob.includes('permissions:\n      contents: read\n      packages: write') &&
  !macJob.includes('contents: write') &&
  !macJob.includes('actions/upload-artifact@'));
check('Monterey release job creates bounded evidence and pushes exactly four typed layers with pinned ORAS',
  macJob.includes('ORAS_VERSION: "1.3.4"') &&
  macJob.includes('ORAS_ARCHIVE_SHA256: "5e964f3d5a36eb9499a9d3e252a86b09e7adf3e6f6447eec56fd249c6702af7e"') &&
  macJob.includes('steps.controls.outputs.evidence }}" create') &&
  macJob.includes('--artifact-type application/vnd.logosforge.pro.macos-handoff.v1') &&
  macJob.includes('"LogosForge Pro-${VERSION}-x64.dmg:application/x-apple-diskimage"') &&
  macJob.includes('"macos-handoff.json:application/json"') &&
  macJob.includes('"pip-freeze.txt:text/plain"') &&
  macJob.includes('"SHA256SUMS-and-build.txt:text/plain"') &&
  macJob.includes('handoff_run_attempt: ${{ steps.evidence.outputs.run_attempt }}') &&
  macJob.includes('echo "run_attempt=$GITHUB_RUN_ATTEMPT" >> "$GITHUB_OUTPUT"') &&
  macJob.includes('echo "digest=$digest" >> "$GITHUB_OUTPUT"'));
check('Monterey cleanup roots are exported before failure-prone staging and downloads',
  macJob.indexOf('echo "root=$controls_root" >> "$GITHUB_OUTPUT"') <
    macJob.indexOf('cp -p -- "$evidence" "$controls_root/macos-handoff-evidence.py"') &&
  macJob.indexOf('echo "root=$handoff_root" >> "$GITHUB_OUTPUT"') <
    macJob.indexOf('steps.controls.outputs.evidence }}" create') &&
  macJob.indexOf('echo "root=$oras_root" >> "$GITHUB_OUTPUT"') <
    macJob.indexOf("curl --fail --location --proto '=https'"));
check('hosted macOS ingest is a bounded read-only-package bridge',
  macIngestJobStart > macJobStart && macIngestJobEnd > macIngestJobStart &&
  macIngestJob.includes('runs-on: ubuntu-22.04') &&
  macIngestJob.includes('permissions:\n      contents: read\n      packages: read') &&
  !macIngestJob.includes('contents: write') &&
  macIngestJob.includes('ORAS_ARCHIVE_SHA256: "f27adb935022d94df8dc77719c322dda592c78a0d57a6f7dcdd8d900b248c454"') &&
  macIngestJob.includes('HANDOFF_RUN_ATTEMPT: ${{ needs.build_macos.outputs.handoff_run_attempt }}') &&
  macIngestJob.includes('"io.logosforge.run-attempt": os.environ["HANDOFF_RUN_ATTEMPT"]') &&
  macIngestJob.includes('--run-attempt "$HANDOFF_RUN_ATTEMPT"') &&
  !macIngestJob.includes('--run-attempt "$GITHUB_RUN_ATTEMPT"') &&
  macIngestJob.indexOf('echo "root=$oras_root" >> "$GITHUB_OUTPUT"') <
    macIngestJob.indexOf("curl --fail --location --proto '=https'") &&
  macIngestJob.includes('reference="${package}@${HANDOFF_DIGEST}"') &&
  macIngestJob.includes('Fetched OCI manifest must be between 1 byte and 1 MiB') &&
  macIngestJob.includes('Fetched OCI manifest does not match the build job digest'));
check('hosted macOS ingest validates exact OCI layers, evidence, and downloaded bytes',
  macIngestJob.includes('OCI handoff must contain exactly four layers') &&
  macIngestJob.includes('"application/x-apple-diskimage"') &&
  macIngestJob.includes('"macos-handoff.json": ("application/json", 1024 * 1024)') &&
  macIngestJob.includes('macos-handoff-evidence.py verify') &&
  macIngestJob.includes('Pulled OCI layer digest mismatch') &&
  macIngestJob.includes('8 * 1024 * 1024 * 1024') &&
  macIngestJob.includes('layer["size"] > maximum_size') &&
  (macIngestJob.match(/uses: actions\/upload-artifact@/g) || []).length === 2 &&
  (macIngestJob.match(/overwrite: true/g) || []).length === 2 &&
  macIngestJob.includes('name: logosforge-pro-macos-intel-x64-provenance'));
check('release publisher is the sole release writer and re-verifies the admitted macOS bytes',
  publishJobStart > macIngestJobStart &&
  (releaseWorkflow.match(/contents: write/g) || []).length === 1 &&
  (releaseWorkflow.match(/uses: softprops\/action-gh-release@/g) || []).length === 1 &&
  publishJob.includes('needs: [metadata, quality, build_windows, build_linux, build_macos, ingest_macos]') &&
  publishJob.includes('permissions:\n      contents: write') &&
  publishJob.includes('name: logosforge-pro-macos-intel-x64-provenance') &&
  publishJob.includes('macos-handoff-evidence.py verify') &&
  publishJob.includes('EXPECTED_DMG_SHA256: ${{ needs.ingest_macos.outputs.dmg_sha256 }}') &&
  publishJob.includes('HANDOFF_RUN_ATTEMPT: ${{ needs.build_macos.outputs.handoff_run_attempt }}') &&
  publishJob.includes('--run-attempt "$HANDOFF_RUN_ATTEMPT"') &&
  !publishJob.includes('--run-attempt "$GITHUB_RUN_ATTEMPT"') &&
  publishJob.includes('Downloaded DMG does not match the hosted ingest digest') &&
  publishJob.includes('uses: softprops/action-gh-release@'));
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
