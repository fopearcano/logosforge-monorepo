# Logosforge — Alpha Freeze Policy

Version: **0.9.0-alpha** (`logosforge.__version__`).
Status: **FROZEN for Alpha.** Logosforge is in alpha closure: the goal is
stability, data safety, UI hardening, documentation, and release readiness —
**not** new features.

Read together with **docs/ALPHA_SCOPE.md** (what Alpha includes / defers).

This policy governs every change made between now and the Alpha release tag.

---

## Allowed changes (during Alpha closure)

Small, safe, well-scoped changes that increase stability without expanding scope:

- **Bug fixes** for confirmed defects in existing systems.
- **Data-safety fixes** — autosave, versioning, project lifecycle, locks,
  migrations (additive/idempotent only), external-change handling.
- **UI hardening** — alignment/layout/theme fixes, 13-inch responsiveness,
  collapse/expand correctness, stale-state clearing, focus/modal behavior.
- **Provider / settings fixes** — configuration, persistence, and safe defaults
  (without changing the shared backend architecture).
- **Project lifecycle fixes** — switch/open/lock/recent correctness and stale
  cache clearing.
- **Tests** — add/repair tests for any of the above (required where practical).
- **Documentation** — scope, freeze, subsystem docs, release notes.
- **Export / import reliability** — roundtrip integrity and lossless I/O.

Each allowed change should be the **smallest safe fix** and ship with tests
where practical.

## Forbidden changes (before Alpha close)

Do **not**, under any circumstances during Alpha closure:

- Implement **Phase 10R** or any successor phase.
- Implement the **Director / Showrunner Control Room**.
- Add **new major systems** or major creative features.
- Add **new AI agents** or any **autonomous mutation** behavior.
- Add **cloud collaboration**, multi-user, or real-time sync.
- Begin a **React / Electron rewrite**, or expose the API in `lan` / `remote`
  mode as a default.
- Add **new schema-heavy features** — new tables/columns are allowed **only**
  when strictly required for a data-safety fix, and must be additive/idempotent.
- Rewrite **Assistant, Logos, PSYKE, Quantum, Graph, Continuity, API, or Writing
  Modes** — unless strictly required to fix a *confirmed* regression, with tests.
- Rewrite **architecture** unless a critical bug proves it necessary.

## High-risk zones — touch only for confirmed regressions, with tests

These carry the highest blast radius (data loss or backend destabilization).
Stop and report before changing them; never change them speculatively:

- `logosforge/autosave.py`, `logosforge/version_manager.py`
- Project switch / lock / lifecycle (`project_lifecycle.py`, `recent_projects.py`,
  `cloud_storage.py`)
- DB models & migrations (`logosforge/models/`, `logosforge/db/database.py`)
- Shared provider backend (`logosforge/providers.py::build_active_provider`,
  `logosforge/assistant.py`)
- Assistant context policy (`assistant_context_policy.py`) — keep gated/capped.

## Safety gates that must stay OFF/locked by default

- `connector_enabled = False`, `connector_allow_writes = False`
- API `mode = "desktop"` (localhost-only)
- Go McKee plugin disabled by default

Changes must not flip these defaults.

## Change checklist (every Alpha-closure PR)

1. Is it in **Allowed changes**? If not, stop.
2. Is it the **smallest safe fix**?
3. Does it touch a **high-risk zone**? If so — confirmed regression only, with
   tests, and **stop and report if project data could be affected**.
4. Are the **safety-gate defaults** unchanged?
5. Are **tests** added/updated where practical?
6. Does the **full test suite** still pass?

## Exit criteria (to lift the freeze → Beta)

- Recorded **full-suite green** baseline.
- Data-safety round-trip tests passing (create→edit→autosave→version→switch→
  reopen; export/import).
- Safety-gate tests passing (Connector writes, API origin policy, Go McKee).
- Alpha scope (docs/ALPHA_SCOPE.md) reviewed and tagged.

Until those are met, the freeze stands.
