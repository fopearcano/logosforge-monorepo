# LogosForge Whiteboard 0.1.14 — Alpha

> [!WARNING]
> This is alpha software. Keep independent backups of important work and export
> a `.lfbundle` regularly. The desktop packages are currently unsigned.

## Highlights

- Added the packaged, authenticated, read-only Whiteboard MCP companion for
  local ChatGPT and Codex orchestration. It exposes nine discovery and reading
  tools while keeping manuscript changes inside the Whiteboard application.
- Added conflict-safe manuscript and Outline persistence with resource
  revisions, exact acknowledgements, durable pending-write receipts, and clear
  recovery prompts when another session changes or deletes a document.
- Added a crash-safe recovery journal and in-app restoration for manuscript,
  Outline, and pending-document recovery files. Restores validate their target
  document again before applying and never reuse imported write authority.
- Hardened local imports with bounded reads, same-file identity checks, and
  canonical recovery exports that remain compatible with tolerated legacy
  project data.
- Expanded frozen and packaged MCP smoke tests, restart-persistence coverage,
  and the genuine packaged Whiteboard-to-Pro writer journey.

## Platforms

- Windows x64: installer and portable executable.
- macOS Intel x64: DMG for macOS 12 Monterey or newer. This release stays on
  Electron 43, the final Electron line supporting Monterey. Apple Silicon and
  universal packages remain deferred.
- Linux x64: AppImage.

Windows SmartScreen and macOS Gatekeeper may warn because the builds are not yet
code-signed or notarized. On macOS, right-click the app and choose **Open**, or
clear quarantine with `xattr -cr "/Applications/LogosForge Whiteboard.app"`.

## Known limitations

- This remains a local-first, single-user alpha without cloud sync or real-time
  collaboration.
- The Whiteboard MCP gateway is deliberately read-only. Editing and conflict
  resolution remain visible user actions in the desktop application.
- Advanced production capabilities remain in LogosForge Pro rather than
  Whiteboard.

[Full changelog](https://github.com/fopearcano/logosforge-monorepo/compare/whiteboard-v0.1.13...whiteboard-v0.1.14)
