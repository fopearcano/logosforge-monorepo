# LogosForge Whiteboard 0.1.21 — Alpha

> [!WARNING]
> This is alpha software. Keep independent backups of important work and export
> a `.lfbundle` regularly. The desktop packages are currently unsigned.

## Highlights

- Adds a dedicated **Progressions** workspace for mapping story, character,
  relationship, theme, world, and custom arcs as ordered beats without leaving
  the current Whiteboard project.
- Supports traceable manuscript-block anchors, PSYKE subjects, track filtering,
  reordering, completion state, and guarded create/edit operations.
- Uses optimistic revisions, idempotent mutation identifiers, durable command
  receipts, and explicit retry/recovery behavior so stale or repeated writes do
  not silently duplicate progression changes.
- Makes Littleboy aware of canonical Progression tracks and their most relevant
  beats while retaining bounded project context.
- Extends `.lfbundle` export with complete canonical Progression tracks and
  ordered beats. The one-way Pro importer remaps PSYKE subjects and restores an
  anchor only when it has one unambiguous destination match.
- Expands packaged acceptance to cover Progressions creation, editing, recovery,
  export, relaunch persistence, and the existing private MCP lifecycle boundary.

## Compatibility

- Existing Whiteboard workspaces remain compatible. Projects without
  Progressions open normally and can add tracks at any time.
- Bundle version 1.0 is retained. Progression fields are additive so older
  readers can ignore them, while current LogosForge Pro imports them safely.
- Whiteboard remains the drafting origin of the one-way `.lfbundle` workflow;
  it does not import Pro projects or bundles.

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
- Whiteboard Progression beats anchor to durable manuscript blocks rather than
  Pro scene identifiers.
- Whiteboard exports `.lfbundle` archives but does not import them. Restore a
  Whiteboard workspace from its local data backup, or import a project bundle
  into LogosForge Pro.
- Native packages are unsigned; code signing, notarization, and Apple Silicon
  packaging remain future work.

[Full changelog](https://github.com/fopearcano/logosforge-monorepo/compare/whiteboard-v0.1.20...whiteboard-v0.1.21)
