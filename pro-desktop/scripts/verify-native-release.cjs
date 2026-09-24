const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

function requireFormat(condition, message) {
  if (!condition) throw new Error(message);
}

/** Reject a stale PyInstaller executable from another OS or CPU architecture. */
function validateNativeBinary(binary, expectedPlatform, expectedArch) {
  requireFormat(expectedArch === 'x64', `Unsupported release architecture: ${expectedArch}`);

  if (expectedPlatform === 'darwin') {
    requireFormat(binary.length >= 8, 'Core executable is too short to be a Mach-O binary.');
    let cpuType;
    if (binary.readUInt32LE(0) === 0xfeedfacf) cpuType = binary.readUInt32LE(4);
    else if (binary.readUInt32BE(0) === 0xfeedfacf) cpuType = binary.readUInt32BE(4);
    else throw new Error('Core executable is not a 64-bit Mach-O binary.');
    requireFormat(cpuType === 0x01000007, 'Core Mach-O binary is not x86_64.');
    return 'Mach-O x86_64';
  }

  if (expectedPlatform === 'linux') {
    requireFormat(
      binary.length >= 20 &&
        binary[0] === 0x7f && binary[1] === 0x45 && binary[2] === 0x4c && binary[3] === 0x46,
      'Core executable is not an ELF binary.',
    );
    requireFormat(binary[4] === 2, 'Core ELF binary is not 64-bit.');
    requireFormat(binary[5] === 1, 'Core ELF binary is not little-endian x86_64.');
    requireFormat(binary.readUInt16LE(18) === 0x3e, 'Core ELF binary is not x86_64.');
    return 'ELF x86_64';
  }

  if (expectedPlatform === 'win32') {
    requireFormat(binary.length >= 64 && binary.toString('ascii', 0, 2) === 'MZ', 'Core executable is not a PE binary.');
    const peOffset = binary.readUInt32LE(0x3c);
    requireFormat(peOffset + 6 <= binary.length, 'Core PE header is truncated.');
    requireFormat(binary.toString('ascii', peOffset, peOffset + 4) === 'PE\0\0', 'Core executable has no PE signature.');
    requireFormat(binary.readUInt16LE(peOffset + 4) === 0x8664, 'Core PE binary is not x86_64.');
    return 'PE x86_64';
  }

  throw new Error(`Unsupported release platform: ${expectedPlatform}`);
}

function readDarwinHostFacts(run = execFileSync) {
  let translated = '0';
  try {
    translated = run('/usr/sbin/sysctl', ['-in', 'sysctl.proc_translated'], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    }).trim();
  } catch {
    // Intel Macs may not expose this Apple Silicon/Rosetta-specific sysctl.
  }

  let productVersion;
  try {
    productVersion = run('/usr/bin/sw_vers', ['-productVersion'], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    }).trim();
  } catch {
    throw new Error('Unable to determine the native macOS version with sw_vers.');
  }
  return { translated, productVersion };
}

function validateDarwinHostFacts({ translated, productVersion }) {
  requireFormat(String(translated).trim() !== '1', 'Rosetta-translated builds are not native Intel x64 releases.');
  const versionMatch = /^(\d+)(?:\.|$)/.exec(String(productVersion).trim());
  requireFormat(versionMatch !== null, `Unrecognized macOS version: ${productVersion}`);
  requireFormat(Number(versionMatch[1]) >= 13, `macOS 13+ is required; current host is ${productVersion}.`);
}

function verifyNativeRelease({
  expectedPlatform,
  expectedArch,
  actualPlatform = process.platform,
  actualArch = process.arch,
  projectDir = path.resolve(__dirname, '..'),
  darwinHostFacts,
}) {
  if (!expectedPlatform || !expectedArch) {
    throw new Error('Usage: node scripts/verify-native-release.cjs <platform> <arch>');
  }
  if (actualPlatform !== expectedPlatform || actualArch !== expectedArch) {
    throw new Error(
      `This release must be built natively on ${expectedPlatform}/${expectedArch}; ` +
      `current host is ${actualPlatform}/${actualArch}.`,
    );
  }
  if (expectedPlatform === 'darwin') {
    validateDarwinHostFacts(darwinHostFacts ?? readDarwinHostFacts());
  }

  const executable = expectedPlatform === 'win32' ? 'logosforge-core.exe' : 'logosforge-core';
  const companion = expectedPlatform === 'win32' ? 'logosforge-mcp.exe' : 'logosforge-mcp';
  const bundleDir = path.join(projectDir, 'core', 'dist', 'logosforge-core');
  const executablePath = path.join(bundleDir, executable);
  const companionPath = path.join(projectDir, 'core', 'dist', companion);

  if (!fs.statSync(bundleDir, { throwIfNoEntry: false })?.isDirectory()) {
    throw new Error(`Native PyInstaller core bundle is missing: ${bundleDir}`);
  }
  const executableStat = fs.statSync(executablePath, { throwIfNoEntry: false });
  if (!executableStat?.isFile()) {
    throw new Error(`Native PyInstaller core executable is missing: ${executablePath}`);
  }
  if (expectedPlatform !== 'win32' && (executableStat.mode & 0o111) === 0) {
    throw new Error(`Native PyInstaller core is not executable: ${executablePath}`);
  }

  const format = validateNativeBinary(fs.readFileSync(executablePath), expectedPlatform, expectedArch);
  const companionStat = fs.statSync(companionPath, { throwIfNoEntry: false });
  if (!companionStat?.isFile()) {
    throw new Error(`Native MCP companion is missing: ${companionPath}`);
  }
  if (expectedPlatform !== 'win32' && (companionStat.mode & 0o111) === 0) {
    throw new Error(`Native MCP companion is not executable: ${companionPath}`);
  }
  const companionFormat = validateNativeBinary(
    fs.readFileSync(companionPath), expectedPlatform, expectedArch,
  );
  return { executablePath, format, companionPath, companionFormat };
}

if (require.main === module) {
  try {
    const requestedPlatform = process.argv[2];
    const expectedPlatform = requestedPlatform === 'current' ? process.platform : requestedPlatform;
    const { executablePath, format, companionPath, companionFormat } = verifyNativeRelease({
      expectedPlatform,
      expectedArch: process.argv[3],
    });
    console.log(
      `Native release inputs verified: ${process.platform}/${process.arch} · ` +
      `${format} · ${executablePath} · ${companionFormat} · ${companionPath}`,
    );
  } catch (error) {
    console.error(`Native release preflight failed: ${error instanceof Error ? error.message : String(error)}`);
    process.exitCode = 1;
  }
}

module.exports = {
  readDarwinHostFacts,
  validateDarwinHostFacts,
  validateNativeBinary,
  verifyNativeRelease,
};
