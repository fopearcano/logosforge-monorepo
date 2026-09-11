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
| `release-whiteboard-macos.yml` | Whiteboard — macOS Intel (DMG) | tag `whiteboard-v*` — runs on a **self-hosted Intel Mac** runner |
| `release-whiteboard-linux.yml` | Whiteboard — Linux x64 (AppImage) | tag `whiteboard-v*` — hosted `ubuntu-latest` |
| `release-windows.yml` | Pro — Windows | tag `v*` |

Whiteboard release tags use the form **`whiteboard-vX.Y.Z`** and must match the
version in `whiteboard-desktop/desktop/package.json`. Do not reuse or move a
published tag. For the version bump, release notes, validation, tag, manual
workflow, and recovery procedures, follow
**[whiteboard-desktop/RELEASING.md](whiteboard-desktop/RELEASING.md)**. The macOS
job needs a self-hosted Intel Mac runner labelled `self-hosted`, `macOS`, and
`X64`, running macOS 13 Ventura or newer with Python 3.11+ installed.

## Local development

- **Prerequisite:** Node.js 22.12+ (Electron 44 / Vite 8) and Python 3.11+.
- **Core:** `pip install -e ./logosforge[export]`
- **Whiteboard desktop:** `cd whiteboard-desktop/desktop && npm install && npm run dev` (spawns the wrapper backend from `whiteboard-desktop/backend/.venv`; run `pip install -r whiteboard-desktop/backend/requirements.txt` in that venv first).
- **Pro desktop:** `cd pro-desktop && npm install && npm run dev`

## Status

**Alpha.** Desktop builds are currently **unsigned** — Windows SmartScreen and macOS Gatekeeper will warn (on macOS, clear quarantine with `xattr -cr "/Applications/LogosForge Whiteboard.app"`). Whiteboard ships Windows, macOS 13+ Intel, and Linux x64 as a self-contained AppImage (`chmod +x "LogosForge Whiteboard-X.Y.Z-x86_64.AppImage"`, then run it). macOS arm64/universal, Linux `.deb`, and Pro's Mac/Linux are later milestones.
