# LogosForge Whiteboard 0.1.22 — Alpha

> [!WARNING]
> This is alpha software. Keep an independent backup of important work and
> export a `.lfbundle` regularly. The desktop packages are currently unsigned.

## Highlights

- Adds opt-in **Cloud Folder Sync** for moving complete Whiteboard projects
  between devices through a locally synchronized Google Drive, Dropbox,
  OneDrive, iCloud Drive, Syncthing, or similar provider folder.
- Synchronizes the manuscript, Drafter pages, comments, PSYKE knowledge,
  Progressions, project settings, and other canonical project data while
  retaining Whiteboard's local-first model and requiring no LogosForge account.
- Uses immutable snapshots, durable receipts, guarded restores, automatic
  retry, and explicit conflict recovery. Divergent device histories are never
  silently overwritten: Whiteboard offers **Keep Both**, **Use Cloud**, or
  **Replace Cloud** actions with preserved recovery state.
- Improves manuscript formatting and alignment across Novel, Screenplay,
  Graphic Novel, and Stage modes, expands curated font choices, and exposes
  installed system fonts in the editor.
- Simplifies the View menu by removing the duplicate fullscreen command and
  legacy theme toggle, and removes the unused current-line highlight setting.
- Extends automated and packaged acceptance coverage for cloud recovery,
  rendering contracts, system fonts, persistence, private MCP lifecycle, and
  relaunch behavior.

## Cloud Folder Sync

Install and sign in to the cloud provider's normal desktop application on each
device, then select a folder managed by that application in Whiteboard's
Settings. Whiteboard writes portable `.lfsync` snapshots into that folder and
keeps the editable workspace local. Provider credentials and OAuth tokens are
never stored by Whiteboard.

Wait for the provider to finish uploading or downloading before switching
devices. Cloud Folder Sync is designed for one writer moving between devices;
it is not real-time collaborative editing.

## Compatibility

- Existing Whiteboard workspaces remain compatible and cloud sync is disabled
  until the writer explicitly chooses a sync folder.
- Devices participating in the same synced workspace should run Whiteboard
  0.1.22 or newer and use the same provider-managed folder.
- Whiteboard remains the drafting origin of the one-way `.lfbundle` workflow;
  it does not import Pro projects or bundles.

## Platforms

- Windows x64: installer and portable executable.
- macOS Intel x64: DMG for macOS 12 Monterey or newer. Apple Silicon and
  universal packages remain deferred.
- Linux x64: AppImage built on Ubuntu.

Windows SmartScreen and macOS Gatekeeper may warn because the builds are not yet
code-signed or notarized. On macOS, right-click the app and choose **Open**, or
clear quarantine with `xattr -cr "/Applications/LogosForge Whiteboard.app"`.

## Known limitations

- Cloud Folder Sync depends on a supported provider's desktop sync client (or
  another local-folder synchronization tool); Whiteboard does not connect
  directly to cloud accounts.
- Simultaneous editing on multiple devices can create a recoverable conflict
  and is not a live collaboration workflow.
- Native packages are unsigned; code signing, notarization, and Apple Silicon
  packaging remain future work.

[Full changelog](https://github.com/fopearcano/logosforge-monorepo/compare/whiteboard-v0.1.21...whiteboard-v0.1.22)
