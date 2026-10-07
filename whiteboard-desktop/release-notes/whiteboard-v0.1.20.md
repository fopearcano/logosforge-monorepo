# LogosForge Whiteboard 0.1.20 — Alpha

> [!WARNING]
> This is alpha software. Keep independent backups of important work and export
> a `.lfbundle` regularly. The desktop packages are currently unsigned.

## Highlights

- Added fail-closed runtime validation for Whiteboard backend responses. Invalid
  document, Drafter, outline, comment, PSYKE, settings, recovery, AI, and export
  payloads are rejected before they can reach application state.
- Bound mutation acknowledgements and project exports to the requested document,
  comment thread, or PSYKE element so a structurally valid response for another
  entity cannot be applied accidentally.
- Added a standalone packaged-app lifecycle gate for every release platform. It
  creates and edits a document, verifies durable autosave across a full restart,
  exports and validates a `.lfbundle`, discovers all 28 read-only MCP tools, and
  confirms the private MCP connection fails closed after shutdown.
- Hardened packaged acceptance with production-equivalent Chromium sandbox
  checks, nonce-verified orphan-backend cleanup, bounded diagnostics, and removal
  of the private MCP bearer descriptor before failure artifacts are retained.
- Clarified the product boundary: `.lfbundle` is an export-only, one-way path
  from Whiteboard to LogosForge Pro. Drafter remains a Whiteboard-only authoring
  surface; Whiteboard does not import project bundles.

## Compatibility

- This release does not change the Whiteboard document, Drafter, comment, PSYKE,
  bundle, backend API, or MCP data formats.
- Existing Whiteboard workspaces remain compatible. Restore a Whiteboard
  workspace from its local data folder; use `.lfbundle` for archival or one-way
  migration into LogosForge Pro.

## Platforms

- Windows x64: installer and portable executable.
- macOS Intel x64: DMG for macOS 12 Monterey or newer. Whiteboard remains on
  Electron 43, the final Electron line supporting Monterey. Apple Silicon and
  universal packages remain deferred.
- Linux x64: AppImage built on Ubuntu.

Windows SmartScreen and macOS Gatekeeper may warn because the builds are not yet
code-signed or notarized. On macOS, right-click the app and choose **Open**, or
clear quarantine with `xattr -cr "/Applications/LogosForge Whiteboard.app"`.

## Known limitations

- This remains a local-first, single-user alpha without cloud sync or real-time
  collaboration.
- MCP writes require an explicit review/apply flow and a server-side opt-in;
  document creation/deletion and unrestricted filesystem access are not exposed.
- Whiteboard exports `.lfbundle` archives but does not import them. Restore a
  Whiteboard workspace from its local data backup, or import a project bundle
  into LogosForge Pro.
- Advanced production capabilities remain in LogosForge Pro.

[Full changelog](https://github.com/fopearcano/logosforge-monorepo/compare/whiteboard-v0.1.19...whiteboard-v0.1.20)
