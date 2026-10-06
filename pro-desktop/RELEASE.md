# Building LogosForge Pro (desktop)

LogosForge Pro ships as a **self-contained desktop app**: the Electron shell +
the built renderer + a PyInstaller-frozen copy of the Python `logosforge` core.
**No Python install is required on the user's machine** — the app spawns the
bundled core (`resources/core/logosforge-core.exe` on Windows,
`resources/core/logosforge-core` on macOS/Linux) on startup and talks to it over
loopback HTTP. Port `8765` is preferred; if it is occupied, the shell selects a
free local port and publishes the resolved endpoint to the renderer and MCP
runtime descriptor.

The core and Electron package must be built on the same native OS and CPU
architecture. PyInstaller does not cross-compile. Every `dist` release command
verifies the native x64 frozen sidecar before invoking electron-builder; the
platform-specific commands also pin their target OS. The macOS preflight rejects
Rosetta-translated Node and hosts older than macOS 12.

## What the build produces

The platform release scripts write to `pro-desktop/release/`:

- Windows: `LogosForge Pro-<version>-x64.exe` — NSIS installer (Start-menu + desktop
  shortcuts, user can choose the install dir).
- Windows: `LogosForge Pro-<version>-x64-portable.exe` — single portable exe (no install).
- macOS Intel: `LogosForge Pro-<version>-x64.dmg` — unsigned DMG for macOS 12+.
- Linux: `LogosForge Pro-<version>-x86_64.AppImage` — x64 AppImage
  (electron-builder renders its `${arch}` macro as `x86_64` for AppImage).
  Its internal executable is the shell-safe `logosforge-pro`, and its
  synchronized desktop identity is `logosforge-pro.desktop`.

Each embeds the platform's Electron executable · `resources/app.asar` (main +
renderer) · `resources/core/` (the native frozen core + its `_internal/` deps)
· `resources/mcp/` (the native one-file Codex/MCP companion).

## CI (recommended): GitHub Actions

Release jobs build the whole thing on their target OS. Each job must run the
PyInstaller bundle, **smoke-test** that the frozen core answers `/api/health`,
then initialize its stdio MCP mode and complete an authenticated API read before
invoking the matching npm release script. Build macOS on an available native
Intel x64 runner and Linux on a native x64 runner; do not reuse a sidecar from
another job or OS.

After packaging, the Windows, Intel macOS and Linux jobs run
`npm run test:packaged-workspace` against the real unpacked native application.
The Playwright Electron journey uses an isolated profile, performs pointer
Canvas and dock mutations, closes through the production save barrier, and
relaunches to verify the persisted board and project layout. The Linux job runs
the unpacked `release/linux-unpacked/logosforge-pro` executable in one
1600x1000 Xvfb display, explicitly enables Playwright's Chromium sandbox, and
asserts that the packaged command line does not contain `--no-sandbox`. This
complements the distributable inspection and MCP smoke; it does not replace
final human installer, Gatekeeper, or system-permission testing. Windows and
Linux failures upload the isolated acceptance directory for diagnosis.

macOS runs support the self-hosted Intel Monterey runner without JavaScript
actions: the job performs an isolated native Git checkout, bootstraps a
checksum-pinned Node 22 when needed, and builds and verifies the complete DMG.
It then pushes the DMG and source-bound evidence to a private GHCR OCI handoff
using a checksum-pinned native ORAS binary. A hosted Ubuntu ingestion job pulls
that handoff by immutable digest, independently verifies its exact files,
checksums, source, version and workflow-run identity, and only then creates the
normal Actions artifact consumed by the hosted publisher. The Monterey job has
package-write permission but never release-write permission; the final hosted
job remains the only GitHub Release mutator. The packaged app's declared
consumer floor is macOS 12.0.

Build-only candidates also become downloadable workflow artifacts after hosted
ingestion and remain under `macos-build-drop/` on the runner as a local fallback.
If the native UI journey fails on Monterey, its screenshots, acceptance log and
isolated state are retained beside that run under `macos-build-drop/` for
diagnosis. GitHub no longer supports Node-based actions on macOS 13.4 or older,
so the Monterey job intentionally contains no `uses:` steps. Keep the
self-hosted runner current enough to accept GitHub jobs even though every build
and transfer step on it is shell/native.

- `npm run dist:win` → Windows NSIS + portable.
- `npm run dist:mac` → Intel x64 DMG (native macOS only).
- `npm run dist:linux` → x64 AppImage (native Linux only).

Keep native artifacts as CI downloads until they have been manually tested on
their target systems. A Monterey build-only candidate is available as a verified
Actions download after hosted ingestion and is also retained in the runner's
`macos-build-drop/` directory. Create/push a release tag only after that
validation.

```bash
git tag v0.1.0 && git push origin v0.1.0
```

The workflow assumes a **single monorepo checkout** containing `logosforge/`,
`logosforge-ui-contracts/`, `pro-shared-ui/`, and `pro-desktop/` as sibling
dirs (the current on-disk layout). Hosted jobs use `actions/checkout`; the
Monterey job makes an equivalent isolated native Git checkout without a
JavaScript action. The handoff registry package is derived from the repository
owner/name and addressed by the digest emitted by that exact build; mutable tags
are never accepted by ingestion or publication.

## Local build

Prereqs: Node 22.12+ and Python 3.11+. On Windows, **Windows Developer Mode
enabled** or an elevated/admin shell may be required, otherwise electron-builder fails
extracting its `winCodeSign` cache with *"Cannot create symbolic link: A
required privilege is not held"*. (That cache holds macOS signing tools a
Windows build never uses; the GitHub runner has the privilege, so CI is
unaffected.)

From the repository root, install the JavaScript siblings in dependency order
before any clean local package build. Installing only `pro-desktop` is not
enough in a fresh checkout because its renderer resolves the sibling sources.

```bash
(cd logosforge-ui-contracts && npm ci)
(cd pro-shared-ui && npm ci && npm run build)
(cd pro-desktop && npm ci)
```

### Windows x64

```bash
# 1. Freeze the core (from the repo root)
python -m venv core-venv
./core-venv/Scripts/python -m pip install "./logosforge[export,voice,mcp]" "pyinstaller==6.22.2"
cd pro-desktop/core
../../core-venv/Scripts/python -m PyInstaller logosforge-core.spec --noconfirm --clean
../../core-venv/Scripts/python -m PyInstaller logosforge-mcp.spec --noconfirm --clean

# 2. Build + package the app
cd ..              # -> pro-desktop
npm run dist:win   # NSIS + portable  ->  release/
#   or:  npm run pack   (unpacked dir only, fast, no installer)
```

### macOS Intel x64

Run these commands on an Intel Mac running macOS 12 or newer. Electron 43 is
the final Electron line that supports Monterey. The current DMG is intentionally unsigned and not
notarized. Dexter's Room triggers the standard macOS microphone permission
prompt when voice capture is used.

```bash
python3 -m venv core-venv
./core-venv/bin/python -m pip install "./logosforge[export,voice,mcp]" "pyinstaller==6.22.2"
cd pro-desktop/core
../../core-venv/bin/python -m PyInstaller logosforge-core.spec --noconfirm --clean
../../core-venv/bin/python -m PyInstaller logosforge-mcp.spec --noconfirm --clean
cd ..
npm run dist:mac   # DMG -> release/
```

### Linux x64

Run these commands on the oldest glibc-based x64 distribution the release is
intended to support; PyInstaller bundles remain sensitive to the builder's
glibc baseline. The packaged UI gate also requires Xvfb and `xauth`, plus a
host that permits sandbox-capable unprivileged user namespaces. Do not work
around a disabled Chromium sandbox by passing `--no-sandbox`.

```bash
python3 -m venv core-venv
./core-venv/bin/python -m pip install "./logosforge[export,voice,mcp]" "pyinstaller==6.22.2"
cd pro-desktop/core
../../core-venv/bin/python -m PyInstaller logosforge-core.spec --noconfirm --clean
../../core-venv/bin/python -m PyInstaller logosforge-mcp.spec --noconfirm --clean
cd ..
npm run dist:linux # AppImage -> release/
xvfb-run --auto-servernum --server-args="-screen 0 1600x1000x24" \
  npm run test:packaged-workspace
```

## How the pieces fit

- **`core/core_entry.py` + `core/logosforge-core.spec`** — the PyInstaller
  entry (forwards `--host/--port/--mode` to `logosforge.api.server.main`, or
  runs the bundled stdio gateway with `--mcp`) and
  the onedir spec. It excludes GUI and torch, includes the headless API plus
  `reportlab`/`python-docx`/MCP SDK, and collects the faster-whisper runtime
  installed by the `voice` extra. Model weights remain user-supplied and are not bundled.
- **`core/mcp_entry.py` + `core/logosforge-mcp.spec`** — a small native
  console companion containing only the stdio MCP gateway. Every packaged app
  carries it under `resources/mcp/`; on first launch Electron atomically copies
  it to the stable per-user `LogosForge Pro/mcp/` directory. This is what Codex
  launches, including when Pro itself is a self-extracting portable/AppImage.
- **`electron/core-manager.ts`** — packaged builds spawn
  `resources/core/logosforge-core(.exe)` (`windowsHide` on Windows); dev builds spawn
  `python -m logosforge.api` from the sibling `logosforge/venv`. Once the core
  identity is verified, it atomically publishes a private runtime descriptor
  used by the local MCP launcher and removes it on shutdown.
- **`electron/mcp-runtime.ts`** — installs/updates that companion and atomically
  maintains the private connection descriptor used to discover the current
  loopback port, token, process ids, and nonce.
- **`electron/platform-paths.ts`** — maps each packaged OS to the sidecar name
  copied into `resources/core/`.
- **`scripts/verify-native-release.cjs`** — rejects macOS/Linux packaging on a
  wrong-OS or non-x64 host, rejects missing/non-executable sidecars, and checks
  the native executable header (Mach-O x86_64, ELF x86_64, or PE x86_64). On
  macOS it also checks `sysctl.proc_translated` and `sw_vers` so Rosetta or a
  pre-macOS-12 runner cannot produce the release.
- **Linux application identity** — `linux.executableName` avoids characters
  inherited from the scoped npm package name, while top-level `desktopName`
  plus `linux.syncDesktopName` keeps the AppImage launcher, WM class, and
  `.desktop` entry associated consistently. The AppImage desktop command does
  not force Electron's `--no-sandbox`; its launcher only falls back to that flag
  on hosts where unprivileged user namespaces are unavailable.
- **`electron/static-server.ts`** — packaged builds serve the renderer from
  `http://127.0.0.1:<port>` (NOT `file://`) so its origin is allowed by the
  core's desktop-mode CORS regex. Without this, every renderer→core fetch fails.

## Known follow-ups

- **Code signing/notarization.** Windows and macOS builds are **unsigned**. Users
  will encounter SmartScreen/Gatekeeper warnings. Windows signing needs an
  EV/OV certificate; macOS signing needs Developer ID credentials plus
  notarization. Remove `mac.identity: null` when that signing flow is added.
- **Application icon.** Windows uses `build/icon.ico`; macOS and Linux use the
  checked-in 1120×1120 `build/icon.png` (electron-builder converts it for the
  macOS bundle on the native runner).
- **Native validation.** DMG mounting/app launch and AppImage launch should be
  tested on their target systems before publishing; a Windows host cannot
  validate either runtime.
- **AI features.** The bundled core runs fully offline for deterministic
  features; Billy/Logos/extraction need an LLM provider (e.g. local LM Studio)
  configured by the user, and degrade gracefully without one.
- **Voice models.** Release builds include the native faster-whisper engine,
  but users must supply/download model files separately (normally under
  `~/.logosforge/models/` or via `LOGOSFORGE_VOICE_MODEL`).
