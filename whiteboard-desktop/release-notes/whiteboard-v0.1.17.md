# LogosForge Whiteboard 0.1.17 — Alpha

> [!WARNING]
> This is alpha software. Keep independent backups of important work and export
> a `.lfbundle` regularly. The desktop packages are currently unsigned.

## Highlights

- Fixed Editor View manuscript colour so a selected ink is applied consistently
  to the writing surface, preview, and title pages, persists across restarts,
  and can be reset to the active theme default.
- Fixed Editor View typeface overrides and expanded the selector to twelve
  writing voices: mode default, three serif families, two sans families, two
  monospaced choices, screenplay Courier Prime, vintage typewriter, and three
  handwriting styles. Offline-safe bundled or platform fallbacks are used.
- Corrected the colour-code switch across Novel, Screenplay, Graphic Novel, and
  Stage Play modes. Turning it off now restores one manuscript ink; turning it
  on restores semantic syntax colours. Custom themes choose their syntax
  palette from the manuscript page luminance rather than the surrounding UI.
- Changed Comments and PSYKE from manuscript-covering docks into movable,
  floating tool windows. Their positions persist, remain clamped to the visible
  viewport, and can also be adjusted with the keyboard. PSYKE create/edit forms
  remain scrollable in short windows.
- Added a persistent transparency slider to the Logos inline assistant so its
  panel can be faded while keeping manuscript context visible.
- Added regression coverage for editor-style persistence, syntax palette
  selection, floating-panel positioning, accessibility, and Logos transparency.

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
- Handwriting and vintage typewriter choices use installed platform fonts when
  a matching face is not bundled, so their exact appearance can vary by OS.
- MCP writes require an explicit review/apply flow and a server-side opt-in;
  document creation/deletion and unrestricted filesystem access are not exposed.
- LogosForge Pro imports Drafter pages as tagged Notes, but does not yet migrate
  their page-scoped comment threads. The original threads remain preserved in
  the source `.lfbundle`.
- Whiteboard exports `.lfbundle` archives but does not import them. Restore a
  Whiteboard workspace from its local data backup, or import a project bundle
  into LogosForge Pro.
- Advanced production capabilities remain in LogosForge Pro.

[Full changelog](https://github.com/fopearcano/logosforge-monorepo/compare/whiteboard-v0.1.16...whiteboard-v0.1.17)
