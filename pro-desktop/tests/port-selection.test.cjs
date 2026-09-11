const { createServer } = require('node:net');
const { selectAvailablePort } = require('../dist-electron/port-selection.js');

let passed = 0;
function check(label, condition) {
  if (!condition) throw new Error(`Port-selection test failed: ${label}`);
  passed += 1;
}

async function main() {
  const occupied = createServer();
  await new Promise((resolve, reject) => {
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

  await new Promise((resolve, reject) => {
    occupied.close((error) => (error ? reject(error) : resolve()));
  });
  check(
    'available preferred port is retained',
    (await selectAvailablePort('127.0.0.1', occupiedPort, false)) === occupiedPort,
  );

  console.log(`Port-selection tests: ${passed} passed, 0 failed`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
