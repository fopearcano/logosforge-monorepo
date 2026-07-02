#!/usr/bin/env node
/**
 * Live API smoke: checks every Whiteboard endpoint against a *running* backend.
 *
 * Start the backend first (../../scripts/run-backend.sh|ps1, or uvicorn), then:
 *   npm run smoke
 *
 * Honors LOGOSFORGE_PORT (default 8777). Exits non-zero on any failure.
 *
 * Non-destructive: it snapshots the whiteboard + outline before mutating them and
 * restores them (and deletes the PSYKE element it creates) in a finally block, so
 * a run leaves ZERO trace in the live session — even if an assertion throws.
 */

const PORT = process.env.LOGOSFORGE_PORT || '8777';
const BASE = `http://127.0.0.1:${PORT}`;

let failures = 0;
function record(label, ok, detail = '') {
  console.log(`  [${ok ? 'ok' : 'FAIL'}] ${label}${detail ? ' — ' + detail : ''}`);
  if (!ok) failures += 1;
}

async function json(method, path, body) {
  const res = await fetch(BASE + path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function main() {
  console.log(`LogosForge Whiteboard — API smoke against ${BASE}`);

  try {
    await fetch(BASE + '/health');
  } catch {
    console.error(`\nBackend not reachable at ${BASE}.`);
    console.error('Start it first: scripts/run-backend.sh (or .ps1), or:');
    console.error(`  cd backend && . .venv/bin/activate && uvicorn app.main:app --port ${PORT}`);
    process.exit(1);
  }

  // Hoisted so the finally cleanup can run even if the try aborts early.
  let wbSnapshot = null;
  let olSnapshot = null;
  let createdId = null;

  try {
    const health = await json('GET', '/health');
    record('GET  /health', health.status === 'ok' && !!health.api_version && !!health.core_version);
    const ver = await json('GET', '/api/version');
    record('GET  /api/version', !!ver.api_version && !!ver.core_version);
    // Snapshot the live session BEFORE we mutate it, so cleanup can restore it.
    wbSnapshot = (await json('GET', '/api/whiteboard')).blocks;
    record('GET  /api/whiteboard', Array.isArray(wbSnapshot));

    const put = await json('PUT', '/api/whiteboard', {
      blocks: [{ id: 'b0', type: 'heading', text: 'Smoke', level: 1 }],
    });
    record('PUT  /api/whiteboard', put.blocks.length === 1);

    const modes = await json('GET', '/api/writing-modes');
    record('GET  /api/writing-modes', modes.modes.length >= 1, `${modes.modes.length} modes`);

    olSnapshot = (await json('GET', '/api/outline/items')).items;
    record('GET  /api/outline/items', Array.isArray(olSnapshot));
    const outlinePut = await json('PUT', '/api/outline/items', {
      items: [{ id: 'n0', parentId: null, type: 'act', title: 'Smoke', order: 0 }],
    });
    record('PUT  /api/outline/items', outlinePut.items.length === 1);

    const psyke = await json('GET', '/api/psyke/search?q=test');
    record('GET  /api/psyke/search', Array.isArray(psyke.results));

    const created = await json('POST', '/api/psyke/elements', { type: 'character', name: 'SmokeHero' });
    createdId = created.element?.id ?? null;
    record('POST /api/psyke/elements', created.ok === true && !!created.element?.id);

    const billy = await json('POST', '/api/littleboy/billy/chat', {
      message: 'Help me improve this.',
      writing_mode: 'novel',
    });
    record('POST /api/littleboy/billy/chat', billy.ok === true && !!billy.message?.content && !!billy.conversation_id);

    const lbLogos = await json('POST', '/api/littleboy/logos/inline', {
      action: 'rewrite',
      selected_text: 'the sea is big',
    });
    // The endpoint is functional; suggested_replacement is provider-dependent —
    // null in the offline/stub path by design (the UI must not apply a placeholder).
    record('POST /api/littleboy/logos/inline (rewrite)', lbLogos.ok === true && !!lbLogos.result);

    // Deterministic Logos action — no AI provider needed. connect_to_psyke must
    // find the entry created above, proving the wrapper consumes core /logos/run.
    const lbConnect = await json('POST', '/api/littleboy/logos/inline', {
      action: 'connect_to_psyke',
      selected_text: 'SmokeHero stands at the edge',
    });
    record(
      'POST /api/littleboy/logos/inline (connect_to_psyke)',
      lbConnect.ok === true && /SmokeHero/.test(lbConnect.result || ''),
    );
  } catch (err) {
    record('request', false, String(err && err.message ? err.message : err));
  } finally {
    // Cleanup — leave ZERO trace even if an earlier (flaky AI) assertion threw.
    // Each step is independently guarded so one failure can't skip the others, and
    // the hoisted vars let this run even when the try aborts before they are set.
    if (createdId != null) {
      try {
        const del = await json('DELETE', `/api/psyke/elements/${createdId}`);
        record('DELETE /api/psyke/elements/:id', del.ok === true && String(del.deleted) === String(createdId));
      } catch (e) {
        record('DELETE /api/psyke/elements/:id', false, String(e?.message ?? e));
      }
    }
    let restored = true;
    if (Array.isArray(wbSnapshot)) {
      try {
        await json('PUT', '/api/whiteboard', { blocks: wbSnapshot });
      } catch (e) {
        restored = false;
        record('cleanup — restore whiteboard', false, String(e?.message ?? e));
      }
    }
    if (Array.isArray(olSnapshot)) {
      try {
        await json('PUT', '/api/outline/items', { items: olSnapshot });
      } catch (e) {
        restored = false;
        record('cleanup — restore outline', false, String(e?.message ?? e));
      }
    }
    if (restored && (Array.isArray(wbSnapshot) || Array.isArray(olSnapshot))) {
      record('cleanup — session restored to pre-smoke state', true);
    }
  }

  console.log(failures === 0 ? '\nSMOKE: PASS' : `\nSMOKE: FAIL (${failures} failed)`);
  process.exit(failures === 0 ? 0 : 1);
}

main();
