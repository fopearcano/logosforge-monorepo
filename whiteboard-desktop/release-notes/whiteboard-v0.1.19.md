# LogosForge Whiteboard 0.1.19 — Alpha

> [!WARNING]
> This is alpha software. Keep independent backups of important work and export
> a `.lfbundle` regularly. The desktop packages are currently unsigned.

## Highlights

- Added advanced Find & Replace to the **Edit** menu and `Ctrl/Cmd+F`. It works
  on the active Manuscript or Drafter page, supports case-sensitive and Unicode
  whole-word matching, wraps through results, and provides Replace and Replace
  all actions.
- Made bulk replacement safer: Replace all is committed as one auto-saved edit,
  so a single Undo restores every replacement. Large documents also use bounded
  visual highlights without losing the exact result count.
- Expanded Editor Settings with a broader grouped typeface library covering
  serif, sans-serif, monospaced, typewriter, and handwritten styles.
- Added installed system font support. Whiteboard can request the local font
  inventory, refresh it after an OS font installation, or apply an exact family
  name directly; unresolved fonts fall back to the writing mode's default.
- Updated the in-app **Quick Start** help with complete Find & Replace and
  installed-font guidance, including search scope, navigation, permissions,
  fallback behavior, and the relevant keyboard shortcuts.
- Refreshed audited packaging dependencies and pinned the patched `shell-quote`
  release used by the desktop toolchain.

## Compatibility

- This release does not change the Whiteboard document, Drafter, comment, PSYKE,
  bundle, backend API, or MCP data formats.
- Existing documents remain compatible. Typeface choices are local presentation
  settings; Whiteboard never embeds or redistributes installed font files in a
  project export.

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

- Enumerating installed fonts requires local-font access from the operating
  system. If access is unavailable or denied, enter the exact family name or use
  one of the built-in cross-platform presets.
- Preset appearance can vary when a platform does not have the first-listed font;
  Whiteboard uses the next available fallback in that preset's stack.
- This remains a local-first, single-user alpha without cloud sync or real-time
  collaboration.
- MCP writes require an explicit review/apply flow and a server-side opt-in;
  document creation/deletion and unrestricted filesystem access are not exposed.
- Whiteboard exports `.lfbundle` archives but does not import them. Restore a
  Whiteboard workspace from its local data backup, or import a project bundle
  into LogosForge Pro.
- Advanced production capabilities remain in LogosForge Pro.

[Full changelog](https://github.com/fopearcano/logosforge-monorepo/compare/whiteboard-v0.1.18...whiteboard-v0.1.19)
