# LogosForge Whiteboard 0.1.13 — Alpha

> [!WARNING]
> This is alpha software. Keep independent backups of important work and export
> a `.lfbundle` regularly. The desktop packages are currently unsigned.

## Highlights

- Hardened project isolation, document lifecycle handling, atomic persistence,
  recovery, and backup behavior across the Whiteboard backend and desktop app.
- Added stable manuscript block identifiers and more resilient Outline and
  comment anchors, including reliable Outline-to-manuscript navigation.
- Improved dialog focus management, keyboard behavior, form labeling, runtime
  fault reporting, and render recovery.
- Improved AI grounding with manuscript, Outline, and PSYKE context, along with
  OpenRouter support and narrative voice settings.
- Expanded `.lfbundle` import/export metadata. LogosForge Pro can import a
  Whiteboard bundle's manuscript, PSYKE, Outline, settings, and section links;
  inline comment migration remains deferred.

## Platforms

- Windows x64: installer and portable executable.
- macOS Intel x64: DMG. Apple Silicon and universal packages are deferred.
- Linux x64: AppImage.

Windows SmartScreen and macOS Gatekeeper may warn because the builds are not yet
code-signed or notarized. On macOS, right-click the app and choose **Open**, or
clear quarantine with `xattr -cr "/Applications/LogosForge Whiteboard.app"`.

## Known limitations

- This remains a local-first, single-user alpha without cloud sync or real-time
  collaboration.
- Advanced production capabilities remain in LogosForge Pro rather than
  Whiteboard.
- A complete packaged-app writer-journey acceptance pass remains part of release
  validation in addition to the automated tests and frozen-backend smoke tests.

[Full changelog](https://github.com/fopearcano/logosforge-monorepo/compare/whiteboard-v0.1.12...whiteboard-v0.1.13)
