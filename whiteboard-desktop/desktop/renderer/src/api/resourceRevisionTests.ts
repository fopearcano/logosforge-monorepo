import {
  advanceResourceRevision,
  beginResourceRevisionRead,
  clearDocumentResourceRevisions,
  commitResourceRevisionRead,
  installResourceRevision,
  requireResourceRevision,
  resetResourceRevisionsForTests,
  resourceEtag,
  StaleResourceReadError,
  validateResourceRevisionResponse,
} from './resourceRevision';
import {
  getWhiteboardForDocument,
  updateWhiteboardForDocument,
} from '../features/whiteboard/whiteboardApi';
import { getOutlineItemsForDocument } from '../features/outline/outlineApi';
import { persistPendingDocument } from './pendingDocumentPersistence';

let passed = 0;
const failures: string[] = [];

function test(name: string, run: () => void): void {
  try {
    run();
    passed += 1;
  } catch (error) {
    failures.push(`${name}: ${error instanceof Error ? error.message : String(error)}`);
  }
}

async function asyncTest(name: string, run: () => Promise<void>): Promise<void> {
  try {
    await run();
    passed += 1;
  } catch (error) {
    failures.push(`${name}: ${error instanceof Error ? error.message : String(error)}`);
  }
}

function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((accept) => {
    resolve = accept;
  });
  return { promise, resolve };
}

const incarnation = '0123456789abcdef0123456789abcdef';
const r1 = '11111111111111111111111111111111';
const r2 = '22222222222222222222222222222222';
const r3 = '33333333333333333333333333333333';

test('strong ETags include resource, incarnation, and opaque revision', () => {
  const actual = resourceEtag('whiteboard', incarnation, r1);
  const expected = `"lfwb:whiteboard:${incarnation}:${r1}"`;
  if (actual !== expected) throw new Error(actual);
});

test('a response ETag must describe the exact body revision', () => {
  let rejected = false;
  try {
    validateResourceRevisionResponse(
      'whiteboard',
      incarnation,
      r1,
      resourceEtag('whiteboard', incarnation, r2),
    );
  } catch {
    rejected = true;
  }
  if (!rejected) throw new Error('Mismatched body and ETag were accepted');
});

test('a successful conditional write advances exactly one known base', () => {
  resetResourceRevisionsForTests();
  installResourceRevision('whiteboard', '7', incarnation, r1);
  advanceResourceRevision('whiteboard', '7', incarnation, r1, r2);
  if (requireResourceRevision('whiteboard', '7', incarnation) !== r2) {
    throw new Error('Acknowledged revision was not installed');
  }
});

test('a late GET cannot downgrade a revision advanced by PUT', () => {
  resetResourceRevisionsForTests();
  installResourceRevision('whiteboard', '7', incarnation, r1);
  const read = beginResourceRevisionRead('whiteboard', '7', incarnation);
  advanceResourceRevision('whiteboard', '7', incarnation, r1, r2);
  const retained = commitResourceRevisionRead('whiteboard', '7', incarnation, r3, read);
  if (
    retained.accepted
    || retained.revision !== r2
    || requireResourceRevision('whiteboard', '7', incarnation) !== r2
  ) {
    throw new Error('Late GET replaced the acknowledged PUT revision');
  }
});

test('independent manuscript and outline validators do not conflict', () => {
  resetResourceRevisionsForTests();
  installResourceRevision('whiteboard', '7', incarnation, r1);
  installResourceRevision('outline', '7', incarnation, r2);
  if (
    requireResourceRevision('whiteboard', '7', incarnation) !== r1
    || requireResourceRevision('outline', '7', incarnation) !== r2
  ) throw new Error('Resource revisions were conflated');
});

test('deleting one incarnation clears both resource validators', () => {
  resetResourceRevisionsForTests();
  installResourceRevision('whiteboard', '7', incarnation, r1);
  installResourceRevision('outline', '7', incarnation, r2);
  clearDocumentResourceRevisions('7', incarnation);
  let missing = 0;
  for (const kind of ['whiteboard', 'outline'] as const) {
    try {
      requireResourceRevision(kind, '7', incarnation);
    } catch {
      missing += 1;
    }
  }
  if (missing !== 2) throw new Error('Deleted validators remained available');
});

function whiteboardResponse(revision: string, title: string): Response {
  return new Response(JSON.stringify({
    id: '7',
    incarnation,
    revision,
    title,
    mode: 'novel',
    blocks: [],
    settings: {},
    updated_at: '',
  }), {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
      ETag: resourceEtag('whiteboard', incarnation, revision),
    },
  });
}

function outlineResponse(revision: string, title: string): Response {
  return new Response(JSON.stringify({
    revision,
    items: [{ id: title.toLowerCase(), title }],
  }), {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
      ETag: resourceEtag('outline', incarnation, revision),
    },
  });
}

await asyncTest('manuscript GET retries rather than returning a body superseded by PUT', async () => {
  resetResourceRevisionsForTests();
  installResourceRevision('whiteboard', '7', incarnation, r1);
  const delayedGet = deferred<Response>();
  const originalFetch = globalThis.fetch;
  let getCalls = 0;
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === 'PUT') return whiteboardResponse(r2, 'Saved');
    getCalls += 1;
    if (getCalls === 1) return delayedGet.promise;
    return whiteboardResponse(r2, 'Fresh');
  }) as typeof fetch;
  try {
    const load = getWhiteboardForDocument('http://127.0.0.1:8777', '7', undefined, incarnation);
    await updateWhiteboardForDocument(
      'http://127.0.0.1:8777',
      '7',
      { title: 'Saved' },
      undefined,
      incarnation,
    );
    delayedGet.resolve(whiteboardResponse(r1, 'Stale'));
    const loaded = await load;
    if (loaded.title !== 'Fresh' || getCalls !== 2) {
      throw new Error(`Returned ${loaded.title} after ${getCalls} GET request(s)`);
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
});

await asyncTest('conditional API write rejects a mismatched response validator', async () => {
  resetResourceRevisionsForTests();
  installResourceRevision('whiteboard', '7', incarnation, r1);
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => {
    const response = whiteboardResponse(r2, 'Saved');
    response.headers.set('ETag', resourceEtag('whiteboard', incarnation, r3));
    return response;
  }) as typeof fetch;
  try {
    let rejected = false;
    try {
      await updateWhiteboardForDocument(
        'http://127.0.0.1:8777', '7', { title: 'Saved' }, undefined, incarnation,
      );
    } catch {
      rejected = true;
    }
    if (!rejected || requireResourceRevision('whiteboard', '7', incarnation) !== r1) {
      throw new Error('Invalid write acknowledgement advanced the revision');
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
});

await asyncTest('browser persistence rejects a mismatched response validator', async () => {
  resetResourceRevisionsForTests();
  installResourceRevision('outline', '7', incarnation, r1);
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => {
    const response = outlineResponse(r2, 'Saved');
    response.headers.set('ETag', resourceEtag('outline', incarnation, r3));
    return response;
  }) as typeof fetch;
  try {
    let rejected = false;
    try {
      await persistPendingDocument(
        'http://127.0.0.1:8777', 'outline', '7', 1, { items: [] }, incarnation,
      );
    } catch {
      rejected = true;
    }
    if (!rejected || requireResourceRevision('outline', '7', incarnation) !== r1) {
      throw new Error('Invalid direct persistence acknowledgement advanced the revision');
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
});

await asyncTest('outline GET retries rather than returning a body superseded by a newer GET', async () => {
  resetResourceRevisionsForTests();
  installResourceRevision('outline', '7', incarnation, r1);
  const olderResponse = deferred<Response>();
  const newerResponse = deferred<Response>();
  const originalFetch = globalThis.fetch;
  let getCalls = 0;
  globalThis.fetch = (async () => {
    getCalls += 1;
    if (getCalls === 1) return olderResponse.promise;
    if (getCalls === 2) return newerResponse.promise;
    return outlineResponse(r2, 'Fresh');
  }) as typeof fetch;
  try {
    const olderLoad = getOutlineItemsForDocument(
      'http://127.0.0.1:8777', '7', undefined, incarnation,
    );
    const newerLoad = getOutlineItemsForDocument(
      'http://127.0.0.1:8777', '7', undefined, incarnation,
    );
    newerResponse.resolve(outlineResponse(r2, 'Fresh'));
    const newerItems = await newerLoad;
    olderResponse.resolve(outlineResponse(r1, 'Stale'));
    const olderItems = await olderLoad;
    if (
      newerItems[0]?.title !== 'Fresh'
      || olderItems[0]?.title !== 'Fresh'
      || getCalls !== 3
    ) {
      throw new Error('A superseded outline body escaped the read retry');
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
});

await asyncTest('a second superseded GET fails explicitly after the bounded retry', async () => {
  resetResourceRevisionsForTests();
  installResourceRevision('outline', '7', incarnation, r1);
  const originalFetch = globalThis.fetch;
  let getCalls = 0;
  globalThis.fetch = (async () => {
    getCalls += 1;
    if (getCalls === 1) {
      installResourceRevision('outline', '7', incarnation, r2);
      return outlineResponse(r1, 'Stale one');
    }
    installResourceRevision('outline', '7', incarnation, r3);
    return outlineResponse(r2, 'Stale two');
  }) as typeof fetch;
  try {
    let rejection: unknown;
    try {
      await getOutlineItemsForDocument(
        'http://127.0.0.1:8777', '7', undefined, incarnation,
      );
    } catch (error) {
      rejection = error;
    }
    if (!(rejection instanceof StaleResourceReadError) || getCalls !== 2) {
      throw new Error('Repeated read race did not stop after one retry');
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
});

console.log(`Resource revision tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} resource revision test(s) failed`);
console.log('RESOURCE REVISION TESTS: PASS');
