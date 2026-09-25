# Releasing LogosForge Whiteboard

This is the evergreen release procedure for the Whiteboard desktop app. Release
tags have the exact form **`whiteboard-vX.Y.Z`**. The `X.Y.Z` portion must match
the desktop package version, and every published release must use a new version
and a new tag.

## Release outputs

| Platform    | Workflow                         | Runner                      | Artifacts                          |
| ----------- | -------------------------------- | --------------------------- | ---------------------------------- |
| Windows x64 | `release-whiteboard-windows.yml` | `windows-latest`            | NSIS installer and portable `.exe` |
| macOS Intel | `release-whiteboard-macos.yml`   | `[self-hosted, macOS, X64]` | unsigned `.dmg`                    |
| Linux x64   | `release-whiteboard-linux.yml`   | `ubuntu-latest`             | `.AppImage`                        |

The self-hosted Mac must be an Intel (`x86_64`) machine running **macOS 12
Monterey or newer**, with Python 3.11+, Xcode Command Line Tools, Git, curl, and
the runner online. Keep all three labels exactly as shown above; changing their
case or spelling prevents the job from being assigned. The workflow uses an
installed native Node.js 22.12+ when available and otherwise downloads the
checksum-pinned Intel Node.js build declared in the workflow.

GitHub retired its Node 20 action runtime and the temporary opt-out on
**2026-09-23**; Node 24 cannot run on macOS 13.4 or earlier. The Monterey build
job therefore contains only shell steps. Publishing runs attach the verified
DMG through GitHub's Releases REST API; non-publishing runs leave a checksummed
build drop in the runner workspace for local testing. GitHub classifies this old
self-hosted OS as unsupported, so this is a best-effort bridge for the existing
Intel test machine rather than a permanent CI platform.

Changes to the Monterey workflow or its packaging and validation inputs on
`main` automatically run the same non-publishing build and leave a local build
drop. Tag pushes still publish regardless of changed paths. This gives the
legacy runner a release-path dry run before a new immutable tag is created.

Every workflow freezes the Python Whiteboard wrapper/shared core and the
read-only MCP companion with PyInstaller, smoke-tests the native backend and an
authenticated MCP read over stdio, packages both beside the Electron app, and
launches the resulting package through `smoke-packaged-mcp.py`. Windows and
Linux upload workflow artifacts; Monterey either keeps a local checksummed
build-only drop or attaches the DMG directly to the matching GitHub prerelease.
PyInstaller output is platform-specific and must never be copied from one
runner to another.

The three platform workflows attach their assets independently. Repository
release immutability must therefore remain disabled until all platform assets
are present. If release immutability is enabled later, replace this with one
draft-first aggregation/finalization workflow before creating another tag.

## Version sources

Whiteboard's release version is recorded in both:

- `whiteboard-desktop/desktop/package.json`
- `whiteboard-desktop/desktop/package-lock.json` (the root package entries)

Use npm to update them together. The shared core version is independent and is
currently **0.9.0-alpha**; do not bump it as a side effect of a Whiteboard shell
release.

Each publishing release also requires committed notes at:

```text
whiteboard-desktop/release-notes/whiteboard-vX.Y.Z.md
```

The workflows reject a publishing tag that does not match the package version,
a checkout that does not resolve to the requested tag, or missing release notes.

## 1. Prepare a release branch

Start from an up-to-date `main` and a clean worktree. Replace `X.Y.Z` below with
the intended numeric version; do not type the angle brackets or reuse a released
number.

```bash
git switch main
git pull --ff-only origin main
git switch -c codex/whiteboard-vX.Y.Z
cd whiteboard-desktop/desktop
npm version X.Y.Z --no-git-tag-version
cd ../..
```

Create `whiteboard-desktop/release-notes/whiteboard-vX.Y.Z.md`. Describe user
changes, compatibility, known issues, and the unsigned-build warning. Review the
two version files together and confirm they contain exactly the same version.

Do not include generated `build/`, `dist/`, `release/`, `.venv`, `node_modules`,
local databases, `.env` files, API keys, model files, private working documents,
or transferred archives in the release commit.

## 2. Validate the candidate

Run the Whiteboard backend and desktop gates on the release commit:

```bash
python -m pytest whiteboard-desktop/backend/tests -q
python -m compileall -q whiteboard-desktop/backend/app
python -m pip check
cd whiteboard-desktop/desktop
npm ci
npm test
npm run build
npm audit --audit-level=moderate
cd ../..
git diff --check
git diff --stat
git status --short
```

Run Python commands from the environment in which
`./logosforge[export]`, the backend requirements, and pytest are installed. On
the self-hosted Intel Mac, also run:

```bash
bash whiteboard-desktop/scripts/validate-macos.sh
```

That script verifies macOS and tool versions, runs the backend and desktop
quality gates, freezes the native backend, builds the DMG, launches the packaged
`.app` with isolated data and a dynamically selected port, and checks the
packaged backend's identity and core version.

Before tagging, confirm each target-platform packaging job also built the
native `logosforge-whiteboard-mcp` companion, passed
`smoke-frozen-mcp.py`, placed the companion under the packaged application's
`resources/mcp` directory, and verified the expected executable architecture.

Commit only the intended source, version, lockfile, and release-note changes.
Open a pull request and wait for the normal Core/Pro and Whiteboard CI checks to
pass. Merge the release commit before creating the public tag.

## 3. Create the immutable tag

After the release change is merged, update local `main`, make sure the worktree
is clean, and verify the exact commit. In this example, `X.Y.Z` is still a
placeholder that must be replaced:

```bash
git switch main
git pull --ff-only origin main
git status --short
VERSION=X.Y.Z
TAG="whiteboard-v${VERSION}"
test "$(node -p 'require("./whiteboard-desktop/desktop/package.json").version')" = "$VERSION"
test -f "whiteboard-desktop/release-notes/${TAG}.md"
git fetch origin --tags
git tag -a "$TAG" -m "LogosForge Whiteboard $VERSION"
git push origin "refs/tags/$TAG"
```

Do not use `git push --tags`, and never force, move, delete, or reuse a published
release tag. If a tagged build is wrong, fix forward with a new package version,
release-note file, and tag.

Pushing the tag starts the Windows, macOS, and Linux release workflows. The
macOS job can remain queued until the labelled Intel self-hosted runner is
online; that is not a reason to retag the commit. Pro and future Electron lines
requiring newer macOS must use their GitHub workflow and wait for a compatible
macOS 13.5+ runner rather than compiling on the Monterey host.

## 4. Manual workflow runs

A manual **Actions → Run workflow** invocation supports two modes:

- Leave `publish_release` off to build without modifying a GitHub Release.
  Windows and Linux upload a workflow artifact. The Monterey runner instead
  preserves the DMG and `SHA256SUMS.txt` under
  `macos-build-drop/run-<run-id>-attempt-<attempt>` in its Actions workspace and
  writes the exact path to the workflow summary.
- Turn `publish_release` on only when attaching or repairing an artifact for an
  existing tag. Enter the complete, exact `release_tag`, such as
  `whiteboard-vX.Y.Z`. The workflow checks out and validates that tag. The
  current bundled-MCP repair path starts with `whiteboard-v0.1.14`; older tags
  do not contain its required packaging inputs and are rejected rather than
  silently mixing current build code into a historical source release.

Use the same immutable tag when retrying a failed platform. Do not publish an
artifact built from a different branch or version under an existing release.

## 5. Verify the published release

Confirm the GitHub prerelease contains all expected, version-matched files:

- `LogosForge.Whiteboard-X.Y.Z-x64.exe`
- `LogosForge.Whiteboard-X.Y.Z-x64-portable.exe`
- `LogosForge.Whiteboard-X.Y.Z-x64.dmg`
- `LogosForge.Whiteboard-X.Y.Z-x86_64.AppImage`

On a clean or isolated test account for each platform:

1. Install or launch the artifact. For Linux, run
   `chmod +x "LogosForge.Whiteboard-X.Y.Z-x86_64.AppImage"` first.
2. Confirm the status reaches `Connected` and shows API v1.0.0 with core
   0.9.0-alpha.
3. Confirm the stable per-user MCP companion and private descriptor exist while
   the GUI is running. From a local MCP client, discover exactly the nine
   `logosforge_whiteboard_` read-only tools and complete an authenticated
   document read. After quitting Whiteboard, confirm a new MCP connection is
   rejected rather than using stale runtime state.
4. Create and edit a document, quit, reopen, and verify persistence.
5. Exercise a loopback/local AI provider, PDF or text export, and `.lfbundle`
   export. Import the `.lfbundle` in LogosForge Pro; Whiteboard does not restore
   bundles itself.
6. Confirm Windows installer and portable builds use isolated expected data,
   and verify the macOS DMG and Linux AppImage on supported systems.

The builds are unsigned. Document the expected Windows SmartScreen prompt and
macOS Gatekeeper/quarantine step in the release notes; do not describe them as
signed or notarized.

## Recovery

If one platform fails before publishing, repair the workflow or runner and
manually rerun that platform against the existing exact tag. If a bad artifact
was published, mark the release clearly, remove only the bad release asset when
appropriate, and publish the corrected product under a new version/tag. Keep
the original Git tag immutable so source and distributed binaries remain
auditable. Tags older than `whiteboard-v0.1.14` must not be repaired with the
current bundled-MCP workflows; preserve their existing assets and issue a new
version if a correction is required.
