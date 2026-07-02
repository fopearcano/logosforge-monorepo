# LogosForge

A narrative-writing workstation — a monorepo with a shared Python **core** and two product tiers (a minimal free **Whiteboard** and a complete **Pro / Studio**).

## Layout

- **`logosforge/`** — the LogosForge **core**: the Python narrative engine + headless API (FastAPI / uvicorn / SQLModel, with export extras). Both products consume this; it is never reimplemented downstream.
- **Whiteboard** (minimal, free tier)
  - `whiteboard-desktop/` — Electron shell (`desktop/`) + a thin FastAPI wrapper backend (`backend/`) that runs the core **in-process**.
  - `whiteboard-shared-ui/`, `whiteboard-web/` — shared design layer + web target (WIP).
- **Pro / Studio** (complete tier)
  - `pro-desktop/` — Electron shell that spawns the frozen core and composes the Pro panels.
  - `pro-shared-ui/`, `logosforge-ui-contracts/`, `pro-web/` — shared UI, wire contracts, web target.
- **`models/`** — local voice / ML models. **Git-ignored** (multi-GB; not in the repo).

## Releases (CI/CD)

Workflows live in `.github/workflows/`. Each freezes the Python backend/core with **PyInstaller**, bundles it into the Electron app via **electron-builder**, and publishes a GitHub Release on a matching tag.

| Workflow | Product / platform | Trigger |
|---|---|---|
| `release-whiteboard-windows.yml` | Whiteboard — Windows (NSIS installer + portable) | tag `whiteboard-v*` |
| `release-whiteboard-macos.yml` | Whiteboard — macOS Intel (DMG) | tag `whiteboard-v*` |
| `release-windows.yml` | Pro — Windows | tag `v*` |

Cutting a release: `git tag whiteboard-v0.1.0 && git push origin whiteboard-v0.1.0` (or run the workflow manually via *Actions → Run workflow* for artifacts without a Release).

## Local development

- **Core:** `pip install -e ./logosforge[export]`
- **Whiteboard desktop:** `cd whiteboard-desktop/desktop && npm install && npm run dev` (spawns the wrapper backend from `whiteboard-desktop/backend/.venv`; run `pip install -r whiteboard-desktop/backend/requirements.txt` in that venv first).
- **Pro desktop:** `cd pro-desktop && npm install && npm run dev`

## Status

**Alpha.** Desktop builds are currently **unsigned** — Windows SmartScreen and macOS Gatekeeper will warn (on macOS, clear quarantine with `xattr -cr "/Applications/LogosForge Whiteboard.app"`). macOS arm64/universal and Linux targets are later milestones.
