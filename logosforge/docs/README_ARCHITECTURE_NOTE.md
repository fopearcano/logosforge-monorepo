<!-- Paste this section into this repo's README.md -->

## Architecture

This repository is part of the **LogosForge** ecosystem, governed by the
architecture/control repo
[`fopearcano/logosforge-architecture`](https://github.com/fopearcano/logosforge-architecture).

- **Product/layer:** LogosForge Core
- **Status:** **real alpha** — one of only two LogosForge repos with real
  application code (the other is `logosforge-desktop`).
- **Role:** the canonical Python core **and the existing Python app** —
  project logic, data models, PSYKE logic, assistant logic, import/export
  logic, and API/backend logic. Single source of truth for the core.
- **Owns:** all behavior and data. If it decides what LogosForge *does*, it
  lives here.
- **Must not own:** React/visual UI, Electron packaging, web cloud
  deployment. Frontend changes belong elsewhere.
- **Consumed by:** in the target architecture, every LogosForge app through
  the API layer (typed by `logosforge-ui-contracts` once that future package
  exists). Today, no shared-package integrations exist.
- **Depends on:** nothing in the ecosystem — the core has no frontend
  dependency, ever.

Before changing anything here, read this repo's `CLAUDE.md` and the
architecture repo's `docs/REPO_MAP.md` and `docs/CHANGE_PROTOCOL.md`.
