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
| `release-windows.yml` | Pro — Windows x64, macOS Intel x64, Linux x64 | tag `v*` or manually selected native builds |

Whiteboard release tags use the form **`whiteboard-vX.Y.Z`** and must match the
version in `whiteboard-desktop/desktop/package.json`. Do not reuse or move a
published tag. For the version bump, release notes, validation, tag, manual
workflow, and recovery procedures, follow
**[whiteboard-desktop/RELEASING.md](whiteboard-desktop/RELEASING.md)**. The macOS
jobs need a self-hosted Intel Mac runner labelled `self-hosted`, `macOS`, and
`X64`, with Python 3.11+ installed. Whiteboard 0.1.14 supports macOS 12 through
Electron 43 and a shell-only Monterey build job documented in its release guide;
Pro requires macOS 13.5+ and Actions Runner 2.327.1+.

## Local development

- **Prerequisite:** Node.js 22.12+ (Whiteboard Electron 43, Pro Electron 44,
  Vite 8) and Python 3.11+.
- **Core:** `pip install -e ./logosforge[export,mcp]`
- **Whiteboard desktop:** `cd whiteboard-desktop/desktop && npm install && npm run dev` (spawns the wrapper backend from `whiteboard-desktop/backend/.venv`; run `pip install -r whiteboard-desktop/backend/requirements.txt` in that venv first).
- **Pro desktop:** install `logosforge-ui-contracts`, `pro-shared-ui`, then
  `pro-desktop` dependencies; run `npm run dev` from `pro-desktop` (see its
  README for the exact clean-checkout commands). Native Pro packages expose a
  local, descriptor-authenticated MCP companion at a stable per-user path for
  Codex orchestration, including portable EXE and AppImage builds.

## Status

**Alpha.** Desktop builds are currently **unsigned** — Windows SmartScreen and
macOS Gatekeeper will warn. Whiteboard and Pro have native Windows x64, macOS
Intel, and Linux x64 release paths; Whiteboard supports macOS 12+, while Pro
requires macOS 13+. Linux ships as a self-contained AppImage. macOS
arm64/universal, signed/notarized builds, and Linux `.deb` packages remain later
milestones. Native artifacts require target-system manual acceptance before
publishing.
