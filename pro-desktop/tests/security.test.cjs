const {
  isExpectedCoreHealth,
  normalizeExternalUrl,
  requireProjectId,
  resolveCoreHost,
} = require('../dist-electron/security.js');
const { CoreManager } = require('../dist-electron/core-manager.js');

let passed = 0;
function check(label, condition) {
  if (!condition) throw new Error(`Security test failed: ${label}`);
  passed += 1;
}
function rejects(label, fn) {
  let rejected = false;
  try { fn(); } catch { rejected = true; }
  check(label, rejected);
}

check('https URL allowed', normalizeExternalUrl('https://example.com/docs') === 'https://example.com/docs');
check('http URL allowed', normalizeExternalUrl('http://127.0.0.1:8765/docs') === 'http://127.0.0.1:8765/docs');
rejects('file URL rejected', () => normalizeExternalUrl('file:///tmp/secret'));
rejects('custom scheme rejected', () => normalizeExternalUrl('calculator:open'));
rejects('invalid URL rejected', () => normalizeExternalUrl('not a url'));
check('positive project id allowed', requireProjectId(42) === 42);
for (const value of [0, -1, 1.5, Number.NaN, Number.MAX_SAFE_INTEGER + 1]) {
  rejects(`invalid project id rejected: ${value}`, () => requireProjectId(value));
}
check('real core identity accepted', isExpectedCoreHealth({
  status: 'ok', service: 'logosforge-api', api_version: '1.0.0', instance_nonce: 'nonce-1',
}, 'nonce-1'));
check('generic 200 payload rejected', !isExpectedCoreHealth({ status: 'ok' }, 'nonce-1'));
check('wrong service rejected', !isExpectedCoreHealth({
  status: 'ok', service: 'other-api', api_version: '1.0.0', instance_nonce: 'nonce-1',
}, 'nonce-1'));
check('stale core nonce rejected', !isExpectedCoreHealth({
  status: 'ok', service: 'logosforge-api', api_version: '1.0.0', instance_nonce: 'old-nonce',
}, 'nonce-1'));

check('production host defaults to loopback', resolveCoreHost(undefined, true) === '127.0.0.1');
check('production ignores a LAN host override', resolveCoreHost('0.0.0.0', true) === '127.0.0.1');
check('source development retains a LAN host override', resolveCoreHost('0.0.0.0', false) === '0.0.0.0');

const previousHost = process.env.LOGOSFORGE_HOST;
process.env.LOGOSFORGE_HOST = '192.168.1.25';
const originalWarn = console.warn;
console.warn = () => {};
try {
  check(
    'production CoreManager advertises only loopback',
    new URL(new CoreManager({ production: true }).baseUrl).hostname === '127.0.0.1',
  );
  check(
    'development CoreManager keeps explicit LAN binding',
    new URL(new CoreManager({ production: false }).baseUrl).hostname === '192.168.1.25',
  );
} finally {
  console.warn = originalWarn;
  if (previousHost === undefined) delete process.env.LOGOSFORGE_HOST;
  else process.env.LOGOSFORGE_HOST = previousHost;
}

console.log(`Electron security tests: ${passed} passed, 0 failed`);
