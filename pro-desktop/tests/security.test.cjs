const {
  isExpectedCoreHealth,
  normalizeExternalUrl,
  requireProjectId,
} = require('../dist-electron/security.js');

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

console.log(`Electron security tests: ${passed} passed, 0 failed`);
