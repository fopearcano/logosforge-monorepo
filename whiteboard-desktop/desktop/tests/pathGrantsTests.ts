import * as path from 'node:path';
import { createServer } from 'node:net';

import { PathGrantRegistry } from '../electron/path-grants';
import { selectAvailablePort } from '../electron/port-selection';
import { isExpectedBackendHealth } from '../electron/service-identity';

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: boolean) => {
  if (condition) passed += 1;
  else failures.push(label);
};

const grants = new PathGrantRegistry();
const allowed = path.resolve('writer', '..', 'project.fountain');
const denied = path.resolve('different.fountain');

check('unknown path denied', grants.allows(allowed) === false);
grants.grant(allowed);
check('granted path allowed', grants.allows(allowed) === true);
check('equivalent normalized path allowed', grants.allows(path.join('.', 'project.fountain')) === true);
check('different path remains denied', grants.allows(denied) === false);
check('blank path denied', grants.allows('') === false);
check('real backend identity accepted', isExpectedBackendHealth({
  status: 'ok',
  service: 'logosforge-whiteboard-backend',
  api_version: '1.0.0',
  instance_nonce: 'nonce-1',
}, 'nonce-1'));
check('generic healthy service rejected', !isExpectedBackendHealth({ status: 'ok' }, 'nonce-1'));
check('wrong local service rejected', !isExpectedBackendHealth({
  status: 'ok',
  service: 'different-service',
  api_version: '1.0.0',
  instance_nonce: 'nonce-1',
}, 'nonce-1'));
check('stale backend nonce rejected', !isExpectedBackendHealth({
  status: 'ok',
  service: 'logosforge-whiteboard-backend',
  api_version: '1.0.0',
  instance_nonce: 'old-nonce',
}, 'nonce-1'));

const occupied = createServer();
await new Promise<void>((resolve, reject) => {
  occupied.once('error', reject);
  occupied.listen({ host: '127.0.0.1', port: 0, exclusive: true }, resolve);
});
const address = occupied.address();
if (!address || typeof address === 'string') throw new Error('test port unavailable');
const occupiedPort = address.port;
const fallbackPort = await selectAvailablePort('127.0.0.1', occupiedPort, true);
check('occupied default port gets a different fallback', fallbackPort !== occupiedPort);
let strictRejected = false;
try {
  await selectAvailablePort('127.0.0.1', occupiedPort, false);
} catch {
  strictRejected = true;
}
check('occupied explicit port is rejected', strictRejected);
await new Promise<void>((resolve, reject) => {
  occupied.close((error) => (error ? reject(error) : resolve()));
});
check(
  'available preferred port is retained',
  (await selectAvailablePort('127.0.0.1', occupiedPort, false)) === occupiedPort,
);

console.log(`Path grant tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} path grant test(s) failed`);
console.log('PATH GRANT TESTS: PASS');
