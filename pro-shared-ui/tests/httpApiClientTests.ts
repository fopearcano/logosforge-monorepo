import { ApiRequestError, createHttpApiClient } from '../src/adapters/httpApiClient';
import { flushPendingProjectSaves } from '../src/adapters/projectSaveCoordinator';

const originalFetch = globalThis.fetch;
const requests: Array<{ input: string; init: RequestInit }> = [];
const project = (id: number, title: string) => ({
  id,
  title,
  description: "",
  narrative_engine: "novel",
  default_writing_format: "prose",
  format_mode: "novel",
});
globalThis.fetch = async (input: RequestInfo | URL, init: RequestInit = {}) => {
  requests.push({ input: String(input), init });
  return new Response(JSON.stringify({ status: 'ok' }), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
};

try {
  const secured = createHttpApiClient('http://127.0.0.1:8765', 'session-secret');
  await secured.health();
  let headers = new Headers(requests.at(-1)?.init.headers);
  if (headers.get('authorization') !== 'Bearer session-secret') {
    throw new Error('Bearer token was not attached to the core request');
  }
  if (headers.get('content-type') !== 'application/json') {
    throw new Error('JSON content type was not preserved');
  }

  const browser = createHttpApiClient('');
  await browser.health();
  headers = new Headers(requests.at(-1)?.init.headers);
  if (headers.has('authorization')) {
    throw new Error('Unauthenticated browser client unexpectedly sent Authorization');
  }

  globalThis.fetch = async () => new Response(
    JSON.stringify({ error: { code: 'assistant_error', message: 'Provider unavailable' } }),
    { status: 502, headers: { 'content-type': 'application/json' } },
  );
  let structured = '';
  let structuredError: unknown = null;
  try { await browser.health(); } catch (error) {
    structuredError = error;
    structured = error instanceof Error ? error.message : '';
  }
  if (structured !== 'GET /api/health → 502 · Provider unavailable') {
    throw new Error(`Structured API error was not decoded: ${structured}`);
  }
  if (!(structuredError instanceof ApiRequestError)
      || structuredError.status !== 502 || structuredError.code !== 'assistant_error') {
    throw new Error('Structured API error metadata was not retained');
  }

  globalThis.fetch = async () => new Response(
    JSON.stringify({ detail: [{ loc: ['body', 'blocks', 0], msg: 'Input should be an object' }] }),
    { status: 422, headers: { 'content-type': 'application/json' } },
  );
  let validation = '';
  try { await browser.health(); } catch (error) { validation = error instanceof Error ? error.message : ''; }
  if (!validation.endsWith('body.blocks.0: Input should be an object')) {
    throw new Error(`Validation API error was not decoded: ${validation}`);
  }

  globalThis.fetch = async () => new Response('Disk is full', { status: 500 });
  let plain = '';
  try { await browser.health(); } catch (error) { plain = error instanceof Error ? error.message : ''; }
  if (!plain.endsWith('500 · Disk is full')) throw new Error(`Plain API error was not retained: ${plain}`);

  let releaseWrite!: (response: Response) => void;
  globalThis.fetch = () => new Promise<Response>((resolve) => { releaseWrite = resolve; });
  const pendingWrite = browser.updateProject(7, { title: 'Tracked' });
  let writeBarrierDone = false;
  const writeBarrier = flushPendingProjectSaves().then(() => { writeBarrierDone = true; });
  for (let i = 0; i < 6; i++) await Promise.resolve();
  if (writeBarrierDone) throw new Error('Save barrier did not wait for a mutating HTTP request');
  if (!releaseWrite) throw new Error('Queued mutating request did not start');
  releaseWrite(new Response(JSON.stringify(project(7, "Tracked")), {
    status: 200, headers: { 'content-type': 'application/json' },
  }));
  await Promise.all([pendingWrite, writeBarrier]);
  if (!writeBarrierDone) throw new Error('Save barrier did not resume after the mutating request');

  let releaseRead!: (response: Response) => void;
  globalThis.fetch = () => new Promise<Response>((resolve) => { releaseRead = resolve; });
  const pendingRead = browser.health();
  await flushPendingProjectSaves();
  releaseRead(new Response(JSON.stringify({ status: 'ok' }), {
    status: 200, headers: { 'content-type': 'application/json' },
  }));
  await pendingRead;

  const patchResolvers: Array<(response: Response) => void> = [];
  const patchBodies: string[] = [];
  let startedPatches = 0;
  globalThis.fetch = (_input: RequestInfo | URL, init: RequestInit = {}) => {
    startedPatches += 1;
    patchBodies.push(String(init.body ?? ''));
    return new Promise<Response>((resolve) => { patchResolvers.push(resolve); });
  };
  const firstPatch = browser.updateProject(11, { title: 'First' });
  const queuedBody = { title: 'Second' };
  const secondPatch = browser.updateProject(11, queuedBody);
  queuedBody.title = 'Mutated after enqueue';
  for (let i = 0; i < 6; i++) await Promise.resolve();
  if (startedPatches !== 1) throw new Error(`Same-resource PATCHes were not serialized: ${startedPatches} started`);
  patchResolvers[0]!(new Response(JSON.stringify(project(11, "First")), {
    status: 200, headers: { 'content-type': 'application/json' },
  }));
  await firstPatch;
  for (let i = 0; i < 6; i++) await Promise.resolve();
  if (startedPatches !== 2) throw new Error('Second PATCH did not start after the first settled');
  if (JSON.parse(patchBodies[1]!).title !== 'Second') throw new Error('Queued PATCH body was not captured at invocation time');
  patchResolvers[1]!(new Response(JSON.stringify(project(11, "Second")), {
    status: 200, headers: { 'content-type': 'application/json' },
  }));
  await secondPatch;

  let failureCalls = 0;
  globalThis.fetch = async () => {
    failureCalls += 1;
    return failureCalls === 1
      ? new Response('first failed', { status: 500 })
      : new Response(JSON.stringify(project(12, "Recovered")), {
          status: 200, headers: { 'content-type': 'application/json' },
        });
  };
  const failedPatch = browser.updateProject(12, { title: 'Fails' }).catch(() => undefined);
  const recoveredPatch = browser.updateProject(12, { title: 'Recovered' });
  await Promise.all([failedPatch, recoveredPatch]);
  if (failureCalls !== 2) throw new Error('PATCH queue stopped after a rejected request');

  console.log('HTTP API client tests: 14 passed, 0 failed');
} finally {
  globalThis.fetch = originalFetch;
}
