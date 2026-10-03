#!/usr/bin/env node

import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import process from 'node:process';

const SEVERITY = Object.freeze({
  info: 0,
  low: 1,
  moderate: 2,
  high: 3,
  critical: 4,
});

// These advisories currently have no patched release. They are restricted to
// development-only tools that are excluded from every packaged application:
//
// - braces is reached only through nodemon's file watcher. LogosForge supplies
//   the watched path itself; untrusted users cannot submit glob expressions.
// - http-cache-semantics is reached only through electron-builder's artifact
//   downloader, which runs on an isolated build host with a private cache.
//
// The production-only audit below must remain clean, and any other advisory —
// including a severity change for either exception — still fails the gate.
const TEMPORARY_DEV_ADVISORIES = new Map([
  [
    'https://github.com/advisories/GHSA-vfj7-8cjw-p6xm',
    { dependency: 'braces', severity: 'high' },
  ],
  [
    'https://github.com/advisories/GHSA-ch52-4w7c-c8xp',
    { dependency: 'http-cache-semantics', severity: 'high' },
  ],
]);

function packageName() {
  try {
    const manifest = JSON.parse(readFileSync('package.json', 'utf8'));
    return typeof manifest.name === 'string' ? manifest.name : process.cwd();
  } catch {
    return process.cwd();
  }
}

function audit(extraArguments) {
  const npmArguments = ['audit', '--json', ...extraArguments];
  const executable = process.platform === 'win32'
    ? (process.env.ComSpec || 'cmd.exe')
    : 'npm';
  const arguments_ = process.platform === 'win32'
    ? ['/d', '/s', '/c', `npm ${npmArguments.join(' ')}`]
    : npmArguments;
  const completed = spawnSync(
    executable,
    arguments_,
    {
      cwd: process.cwd(),
      encoding: 'utf8',
      maxBuffer: 32 * 1024 * 1024,
      shell: false,
    },
  );
  if (completed.error) throw completed.error;

  let report;
  try {
    report = JSON.parse(completed.stdout || '{}');
  } catch (error) {
    throw new Error(
      `npm audit did not return JSON (exit ${completed.status}).\n`
      + `${completed.stderr || completed.stdout || error}`,
    );
  }
  if (report.error) {
    throw new Error(`npm audit failed: ${JSON.stringify(report.error)}`);
  }
  if (completed.status !== 0 && completed.status !== 1) {
    throw new Error(
      `npm audit exited ${completed.status}.\n${completed.stderr || completed.stdout}`,
    );
  }
  return report;
}

function atLeastModerate(severity) {
  return (SEVERITY[severity] ?? Number.POSITIVE_INFINITY) >= SEVERITY.moderate;
}

function advisoryRoots(vulnerabilities, dependency, trail = new Set()) {
  if (trail.has(dependency)) return [{ unresolved: `cycle:${dependency}` }];
  const vulnerability = vulnerabilities[dependency];
  if (!vulnerability) return [{ unresolved: dependency }];

  const nextTrail = new Set(trail);
  nextTrail.add(dependency);
  const roots = [];
  for (const via of vulnerability.via ?? []) {
    if (typeof via === 'string') {
      roots.push(...advisoryRoots(vulnerabilities, via, nextTrail));
    } else if (via && typeof via === 'object') {
      roots.push({ advisory: via });
    }
  }
  return roots.length > 0 ? roots : [{ unresolved: dependency }];
}

function assertProductionAuditIsClean(report, label) {
  const vulnerable = Object.entries(report.vulnerabilities ?? {})
    .filter(([, value]) => atLeastModerate(value?.severity))
    .map(([name, value]) => `${name} (${value.severity})`);
  if (vulnerable.length > 0) {
    throw new Error(
      `${label} has moderate-or-higher production vulnerabilities:\n`
      + vulnerable.map((value) => `  - ${value}`).join('\n'),
    );
  }
}

function assertFullAuditMatchesPolicy(report, label) {
  const vulnerabilities = report.vulnerabilities ?? {};
  const unexpected = [];
  const acknowledged = new Map();

  for (const [dependency, vulnerability] of Object.entries(vulnerabilities)) {
    if (!atLeastModerate(vulnerability?.severity)) continue;
    const roots = advisoryRoots(vulnerabilities, dependency);
    const resolvedRoots = roots.filter((root) => root.advisory);
    if (resolvedRoots.length === 0) {
      const unresolved = roots.map((root) => root.unresolved).filter(Boolean);
      unexpected.push(
        `${dependency}: unresolved advisory chain (${unresolved.join(', ') || 'empty'})`,
      );
      continue;
    }
    for (const root of resolvedRoots) {
      const advisory = root.advisory;
      const expected = TEMPORARY_DEV_ADVISORIES.get(advisory.url);
      if (
        !expected
        || advisory.name !== expected.dependency
        || advisory.severity !== expected.severity
      ) {
        unexpected.push(
          `${dependency}: ${advisory.url ?? advisory.source ?? advisory.name}`
          + ` (${advisory.severity ?? vulnerability.severity})`,
        );
        continue;
      }
      acknowledged.set(advisory.url, expected);
    }
  }

  if (unexpected.length > 0) {
    throw new Error(
      `${label} has unapproved moderate-or-higher dependency findings:\n`
      + [...new Set(unexpected)].map((value) => `  - ${value}`).join('\n'),
    );
  }

  console.log(`${label}: production dependency audit passed.`);
  if (acknowledged.size === 0) {
    console.log(`${label}: full dependency audit passed with no temporary exceptions.`);
    return;
  }
  console.warn(`${label}: acknowledged development-tool advisories with no patched release:`);
  for (const [url, expected] of acknowledged) {
    console.warn(`  - ${expected.dependency} (${expected.severity}): ${url}`);
  }
}

function main() {
  const label = packageName();
  const production = audit(['--omit=dev']);
  assertProductionAuditIsClean(production, label);
  const full = audit([]);
  assertFullAuditMatchesPolicy(full, label);
}

try {
  main();
} catch (error) {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
}
