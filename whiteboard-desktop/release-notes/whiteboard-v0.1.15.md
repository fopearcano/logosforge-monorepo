# LogosForge Whiteboard 0.1.15 — Alpha

> [!WARNING]
> This is alpha software. Keep independent backups of important work and export
> a `.lfbundle` regularly. The desktop packages are currently unsigned.

## Highlights

- Added **Drafter**, a project-scoped tabbed writing space for isolated scenes,
  alternatives, and exploratory prose. Drafter pages auto-save independently,
  support Text, Markdown, and Fountain imports, and stay separate from the
  canonical manuscript.
- Added conflict-safe Drafter revisions, crash recovery, backup generations,
  and resource-specific recovery imports. Project switches and shutdown now
  drain pending Drafter writes together with manuscript and project data.
- Kept Billy and Logos aware of the complete project while drafting: the active
  page and selection are supplied as explicitly provisional context alongside
  the canonical manuscript digest, Outline, narrative profile, and PSYKE.
- Extended `.lfbundle` exports with exact structured Drafter pages. LogosForge
  Pro imports them as tagged Notes and preserves their original blocks in project
  settings, while publication-oriented exports remain manuscript-only.
- Expanded the authenticated local Whiteboard MCP contract to version 1.5.0
  with 28 bounded tools. It now supports Drafter reads/search and reviewed,
  revision-safe proposals for manuscript, Drafter, Outline, PSYKE, and limited
  comment collaboration. The apply gate remains disabled by default.
- Expanded frozen and packaged MCP smoke coverage, independent Drafter/comment
  revision checks, recovery tests, and Whiteboard-to-Pro migration reporting.

## Platforms

- Windows x64: installer and portable executable.
- macOS Intel x64: DMG for macOS 12 Monterey or newer. Whiteboard remains on
  Electron 43, the final Electron line supporting Monterey. Apple Silicon and
  universal packages remain deferred.
- Linux x64: AppImage.

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

[Full changelog](https://github.com/fopearcano/logosforge-monorepo/compare/whiteboard-v0.1.14...whiteboard-v0.1.15)
