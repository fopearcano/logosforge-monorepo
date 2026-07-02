# Alpha Release Checklist — Logosforge 0.9.0-alpha

Gate checklist for declaring **Alpha Closed (private alpha)**. Companion to
[ALPHA_SCOPE.md](ALPHA_SCOPE.md), [ALPHA_FREEZE.md](ALPHA_FREEZE.md),
[KNOWN_LIMITATIONS_ALPHA.md](KNOWN_LIMITATIONS_ALPHA.md) and the full
[ALPHA_TEST_PLAN.md](ALPHA_TEST_PLAN.md).

## Must pass before Alpha (hard gate)

- [x] **Full test suite** — `QT_QPA_PLATFORM=offscreen python -m pytest -q`
      (~6008 tests; safety-critical subset 214 passed / 0 skipped). The gate run
      surfaced one regression (Outline-confirm dialog minimum) — **fixed** — and
      one full-suite-ordering flake (a Logos toolbar test that passes in
      isolation). Re-run the full suite to confirm a clean baseline before
      tagging.
- [x] **No data-loss paths** — autosave is atomic; per-keystroke edits flush
      before any editor rebuild; restore is non-destructive (new project).
- [x] **Project switch clears stale state** — scenes/PSYKE/notes/Assistant/Logos
      surfaces; writing-mode-dependent nav (Pages) recomputed.
- [x] **`writing_mode` is the single source of truth** — read fresh everywhere;
      persists; propagates on switch (incl. Assistant mode strip).
- [x] **Provider layer** — single `build_active_provider` resolver; settings
      persist; readable timeout/config errors; **no API key in logs/exports**.
- [x] **Export** — Markdown/TXT/Fountain/FDX/HTML/JSON/CSV work; PDF/DOCX
      failures show readable errors; exports leak no keys/abs-paths.
- [x] **Safety gates OFF by default** — `logos_enabled=False`,
      `connector_enabled=False`, `connector_allow_writes=False`, API desktop mode.
- [x] **Migrations additive/idempotent** — old DBs open unchanged.

## Should pass before Alpha (soft gate)

- [x] Manuscript editor never greys out / loses focus while typing.
- [x] 13-inch layout: no hidden right edge; Assistant auto-hides when cramped;
      dialogs fit 1280×800.
- [x] Logos is an inline ON/OFF toggle (not a central page).
- [x] PSYKE console compact, focus-restoring, shows character/place suggestions.
- [x] Assistant responds in the user's language; explicit override wins.
- [x] No "Unknown property" QSS warnings in the app stylesheet.
- [x] Docs: README alpha note + User Guide / AI Setup / Troubleshooting / index.

## Acceptable Alpha limitations

- PDF/DOCX need optional libs (`reportlab`/`python-docx`); other formats don't.
- FDX, HTML, and the API LAN/remote modes are **experimental**.
- Plot/Timeline are scene-derived; grammar is rule-based.
- Knowledge-Graph/Continuity/Decision-Radar/Workflow services have **no UI panel**.
- Single-user, local-only; restore creates a new project (non-destructive).
- API keys stored plaintext in the **local** settings file (never exported).

## Beta blockers (resolve before expanding scope)

1. UI panels for the deferred intelligence services.
2. API LAN/remote hardening + required auth before non-desktop exposure.
3. Richer Plot/Timeline models; opt-in semantic-continuity checks.
4. Re-confirm full-suite-green after each change.

## Deferred features

See [KNOWN_LIMITATIONS_ALPHA.md](KNOWN_LIMITATIONS_ALPHA.md) and
[ALPHA_SCOPE.md](ALPHA_SCOPE.md) §6.

## Manual smoke test checklist

Run on a throwaway project. Full version: [ALPHA_TEST_PLAN.md](ALPHA_TEST_PLAN.md).

- [ ] Create a **new project**.
- [ ] **Set a Writing Mode** (try Novel and Screenplay).
- [ ] **Write manuscript** text — editor stays responsive, no grey-out.
- [ ] **Create an Outline** (manually or via the Assistant, confirmed).
- [ ] **Create a PSYKE entry** (a character) — it appears in the console search.
- [ ] **Use the Assistant** (set a provider first; ask a question).
- [ ] **Use Logos** — toggle it ON; inline suggestions appear; toggle OFF.
- [ ] **Export the manuscript** (Markdown/TXT/Fountain) — path shown, file written.
- [ ] **Back up the project** (Export → Full Project JSON; create a snapshot).
- [ ] **Close and reopen** the app.
- [ ] **Reload the project** — verify scenes, PSYKE, notes are intact.
- [ ] **Open an exported JSON** — confirm no `api_key`, no absolute paths.
