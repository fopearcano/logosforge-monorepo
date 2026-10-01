#!/usr/bin/env node

/**
 * Test-only command driver for the compiled Electron CoreManager.
 *
 * The companion Python smoke owns assertions and the MCP client. This process
 * owns the real CoreManager so publication still crosses the exact production
 * transport, including its private live-context capability and ordered queue.
 * Core logs may share stdout, therefore protocol records carry a unique prefix.
 */

const fs = require('node:fs');
const path = require('node:path');
const readline = require('node:readline');

const RECORD_PREFIX = '@@LOGOSFORGE_LIVE_CONTEXT_DRIVER@@';

function emit(record) {
  process.stdout.write(`${RECORD_PREFIX}${JSON.stringify(record)}\n`);
}

function parseArgs(argv) {
  const values = new Map();
  for (let index = 0; index < argv.length; index += 2) {
    const name = argv[index];
    const value = argv[index + 1];
    if (!name?.startsWith('--') || value == null) {
      throw new Error(`Invalid driver argument near ${name ?? '<end>'}.`);
    }
    values.set(name.slice(2), value);
  }
  const required = (name) => {
    const value = values.get(name);
    if (!value) throw new Error(`Missing required --${name} argument.`);
    const resolved = path.resolve(value);
    if (!path.isAbsolute(resolved)) throw new Error(`--${name} must be absolute.`);
    return resolved;
  };
  return {
    manager: required('manager'),
    core: required('core'),
    db: required('db'),
    descriptor: required('descriptor'),
  };
}

function waitForExit(child, timeoutMs = 10_000) {
  if (!child || child.exitCode != null || child.signalCode != null) return Promise.resolve();
  return Promise.race([
    new Promise((resolve) => child.once('exit', resolve)),
    new Promise((resolve) => setTimeout(resolve, timeoutMs)),
  ]);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  for (const [label, filePath] of [['manager', args.manager], ['core', args.core]]) {
    if (!fs.statSync(filePath).isFile()) throw new Error(`${label} is not a file: ${filePath}`);
  }
  if (!process.env.LOGOSFORGE_PORT?.trim()) {
    throw new Error('LOGOSFORGE_PORT must be set before CoreManager is imported.');
  }

  // CoreManager captures LOGOSFORGE_PORT at module evaluation time. Keep this
  // require below the environment validation so the smoke cannot silently use
  // the default port.
  const { CoreManager } = require(args.manager);
  const manager = new CoreManager({
    production: true,
    bundledCorePath: args.core,
    dbPath: args.db,
    mcpRuntimePath: args.descriptor,
  });
  let stopped = false;

  const stopManager = async () => {
    if (stopped) return;
    stopped = true;
    const child = manager.child;
    await manager.stop();
    await waitForExit(child);
  };

  const shutdownOnSignal = () => {
    void stopManager().finally(() => process.exit(1));
  };
  process.once('SIGINT', shutdownOnSignal);
  process.once('SIGTERM', shutdownOnSignal);

  try {
    await manager.start();
    const status = manager.getStatus();
    if (status.state !== 'connected' || status.managed !== true) {
      throw new Error(`CoreManager did not start a managed core: ${status.state} ${status.detail ?? ''}`);
    }
    if (typeof status.authToken !== 'string' || status.authToken.length < 32) {
      throw new Error('CoreManager did not expose its test-local API bearer token.');
    }
    if (Object.hasOwn(status, 'liveContextToken')) {
      throw new Error('CoreStatus exposed the private live-context capability.');
    }
    emit({
      event: 'ready',
      baseUrl: status.baseUrl,
      authToken: status.authToken,
      managed: status.managed,
      statusKeys: Object.keys(status).sort(),
    });

    const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
    let serial = Promise.resolve();
    const handle = async (line) => {
      let request;
      try {
        request = JSON.parse(line);
      } catch {
        throw new Error('Driver received malformed JSON.');
      }
      if (!Number.isSafeInteger(request.id) || request.id < 1) {
        throw new Error('Driver command requires a positive integer id.');
      }
      try {
        switch (request.command) {
          case 'publish':
            await manager.publishLiveContext(request.context);
            break;
          case 'suspend':
            await manager.suspendLiveContext();
            break;
          case 'resume':
            manager.resumeLiveContext();
            break;
          case 'stop':
            await stopManager();
            break;
          default:
            throw new Error(`Unsupported driver command: ${String(request.command)}`);
        }
        emit({ id: request.id, ok: true });
        if (request.command === 'stop') input.close();
      } catch (error) {
        emit({
          id: request.id,
          ok: false,
          error: error instanceof Error ? error.message : String(error),
        });
      }
    };
    input.on('line', (line) => {
      serial = serial.then(() => handle(line));
    });
    await new Promise((resolve) => input.once('close', resolve));
    await serial;
  } finally {
    await stopManager();
  }
}

main().catch((error) => {
  emit({
    event: 'fatal',
    error: error instanceof Error ? (error.stack || error.message) : String(error),
  });
  process.exitCode = 1;
});
