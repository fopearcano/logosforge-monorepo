# LogosForge Whiteboard 0.1.16 — Alpha

> [!WARNING]
> This is alpha software. Keep independent backups of important work and export
> a `.lfbundle` regularly. The desktop packages are currently unsigned.

## Highlights

- Added anchored Comments to every Drafter page. Threads, highlights, navigation,
  and the Comments panel now follow the active writing page while remaining
  isolated from the canonical Manuscript and from other Drafter tabs.
- Hardened Drafter comment persistence around autosave, tab and project changes,
  editing conflicts, and page deletion so an interrupted write cannot remove or
  misplace another page's comment thread.
- Kept Billy and Logos aware of the active Drafter page and its comments while
  explicitly identifying that material as provisional and noncanonical. The
  canonical manuscript, Outline, narrative profile, and PSYKE remain available
  as separate project context.
- Extended the authenticated local MCP comment contract with writing-surface and
  Drafter-page identity. Invalid or missing page references are rejected, while
  comments created by older Whiteboard versions remain manuscript comments.
- Preserved Drafter comment scope in `.lfbundle` backups and labeled the owning
  Drafter page in comment reports. LogosForge Pro now safely reports and skips
  Drafter-only comment threads instead of attaching them to unrelated canonical
  manuscript scenes.
- Expanded desktop, backend, MCP, export, UI-contract, and Pro-import regression
  coverage for per-page comment isolation and compatibility.

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
- LogosForge Pro imports Drafter pages as tagged Notes, but does not yet migrate
  their page-scoped comment threads. The original threads remain preserved in
  the source `.lfbundle`.
- Whiteboard exports `.lfbundle` archives but does not import them. Restore a
  Whiteboard workspace from its local data backup, or import a project bundle
  into LogosForge Pro.
- Advanced production capabilities remain in LogosForge Pro.

[Full changelog](https://github.com/fopearcano/logosforge-monorepo/compare/whiteboard-v0.1.15...whiteboard-v0.1.16)
