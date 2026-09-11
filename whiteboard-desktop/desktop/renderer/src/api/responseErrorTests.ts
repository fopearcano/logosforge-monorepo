import { responseError } from './responseError';
import { setBackendAuthToken, withBackendAuth } from './backendAuth';
import { setCurrentDocId } from '../state/currentDocument';
import { getWhiteboardForDocument } from '../features/whiteboard/whiteboardApi';
import { onRecoveryNoticeCheckRequested } from './recoverySignal';

let passed = 0;
const failures: string[] = [];

function check(label: string, condition: boolean): void {
  if (condition) passed += 1;
  else failures.push(label);
}

const structured = await responseError(
  new Response(JSON.stringify({ error: { code: 'local_state_corrupt', message: 'Backup required' } }), {
    status: 409,
    headers: { 'Content-Type': 'application/json' },
  }),
  'Fallback',
);
check('structured error message', structured.message === 'Backup required (HTTP 409)');

const detail = await responseError(
  new Response(JSON.stringify({ detail: 'Export aborted safely' }), {
    status: 502,
    headers: { 'Content-Type': 'application/json' },
  }),
  'Fallback',
);
check('FastAPI detail message', detail.message === 'Export aborted safely (HTTP 502)');

const plain = await responseError(new Response('Disk is full', { status: 500 }), 'Fallback');
check('plain-text message', plain.message === 'Disk is full (HTTP 500)');

const empty = await responseError(new Response('', { status: 503 }), 'Stable fallback');
check('empty response fallback', empty.message === 'Stable fallback (HTTP 503)');

setBackendAuthToken('session-secret');
const authorized = new Headers(withBackendAuth({ headers: { 'Content-Type': 'application/json' } }).headers);
check('backend token attached', authorized.get('Authorization') === 'Bearer session-secret');
check('existing headers preserved', authorized.get('Content-Type') === 'application/json');
setBackendAuthToken('');
const browserDev = new Headers(withBackendAuth().headers);
check('blank dev token adds no authorization', !browserDev.has('Authorization'));

// A target document is loaded explicitly while the old one remains active.
// This is the safety boundary used by document switching.
const originalFetch = globalThis.fetch;
let requestedUrl = '';
globalThis.fetch = (async (input: RequestInfo | URL) => {
  requestedUrl = String(input);
  return new Response(
    JSON.stringify({ id: 'new doc', title: 'New', mode: 'novel', blocks: [], updated_at: '' }),
    { status: 200, headers: { 'Content-Type': 'application/json' } },
  );
}) as typeof fetch;
try {
  let recoverySignals = 0;
  const unsubscribeRecovery = onRecoveryNoticeCheckRequested(() => {
    recoverySignals += 1;
  });
  setCurrentDocId('old-doc');
  await getWhiteboardForDocument('http://127.0.0.1:8777', 'new doc');
  check('explicit document load uses the target id', requestedUrl.endsWith('/api/whiteboard?doc=new%20doc'));
  check('explicit document load ignores active id', !requestedUrl.includes('old-doc'));
  check('ordinary API activity requests a recovery check', recoverySignals === 1);
  await (await import('./backendAuth')).backendFetch('http://127.0.0.1:8777/api/recovery/notices');
  check('recovery endpoint does not recursively signal', recoverySignals === 1);
  unsubscribeRecovery();
} finally {
  globalThis.fetch = originalFetch;
  setCurrentDocId('');
}

console.log(`API error tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} API error test(s) failed`);
console.log('API ERROR TESTS: PASS');
