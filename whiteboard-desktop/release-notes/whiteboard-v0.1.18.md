# LogosForge Whiteboard 0.1.18 — Alpha

> [!WARNING]
> This is alpha software. Keep independent backups of important work and export
> a `.lfbundle` regularly. The desktop packages are currently unsigned.

## Highlights

- Made the Logos assistant movable by mouse and keyboard. It still opens beside
  the current writing context, then remembers a manually chosen position while
  keeping its header reachable inside the viewport.
- Moved the Logos transparency control into its header, immediately before the
  title, so it no longer consumes a separate content row.
- Added matching compact transparency controls to LittleBoy, PSYKE, and
  Comments. Each panel remembers its own setting independently.
- Kept panel controls usable while faded: transparency is capped at 70%, slider
  interaction does not initiate a drag, and the selected opacity survives the
  panel opening animation.
- Added regression coverage for contextual and persisted panel positioning,
  transparency normalization and storage, header control order, keyboard
  movement, and accessibility metadata.

## Compatibility

- This release does not change the Whiteboard document, Drafter, comment, PSYKE,
  bundle, backend API, or MCP data formats.
- Existing documents and settings remain compatible. New panel positions and
  transparency values are stored locally per installation.

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

[Full changelog](https://github.com/fopearcano/logosforge-monorepo/compare/whiteboard-v0.1.17...whiteboard-v0.1.18)
