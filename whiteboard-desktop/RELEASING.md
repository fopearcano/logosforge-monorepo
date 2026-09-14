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
Monterey or newer**, with Python 3.11+, Node.js 22.12+, npm, Xcode Command Line
Tools, and the runner online. Keep all three labels exactly as shown above;
changing their case or spelling prevents the job from being assigned.

The Monterey workflow temporarily keeps JavaScript actions on GitHub's Node 20
action runtime because Node 24 requires macOS 13.5+. GitHub removes that escape
hatch on **2026-09-23**, after which this runner must be upgraded to macOS 13.5+
before it can build another release. Already-built Electron 43 packages are not
affected by that CI deadline.

Every workflow freezes the Python Whiteboard wrapper and shared core with
PyInstaller, smoke-tests that native backend, packages it beside the Electron
app, uploads a workflow artifact, and optionally attaches it to the matching
GitHub prerelease. PyInstaller output is platform-specific and must never be
copied from one runner to another.

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
online; that is not a reason to retag the commit.

## 4. Manual workflow runs

A manual **Actions → Run workflow** invocation supports two modes:

- Leave `publish_release` off to build and upload a workflow artifact without
  modifying a GitHub Release.
- Turn `publish_release` on only when attaching or repairing an artifact for an
  existing tag. Enter the complete, exact `release_tag`, such as
  `whiteboard-vX.Y.Z`. The workflow checks out and validates that tag.

Use the same immutable tag when retrying a failed platform. Do not publish an
artifact built from a different branch or version under an existing release.

## 5. Verify the published release

Confirm the GitHub prerelease contains all expected, version-matched files:

- `LogosForge Whiteboard-X.Y.Z-x64.exe`
- `LogosForge Whiteboard-X.Y.Z-x64-portable.exe`
- `LogosForge Whiteboard-X.Y.Z-x64.dmg`
- `LogosForge Whiteboard-X.Y.Z-x86_64.AppImage`

On a clean or isolated test account for each platform:

1. Install or launch the artifact. For Linux, run
   `chmod +x "LogosForge Whiteboard-X.Y.Z-x86_64.AppImage"` first.
2. Confirm the status reaches `Connected` and shows API v1.0.0 with core
   0.9.0-alpha.
3. Create and edit a document, quit, reopen, and verify persistence.
4. Exercise a loopback/local AI provider, PDF or text export, and `.lfbundle`
   export. Import the `.lfbundle` in LogosForge Pro; Whiteboard does not restore
   bundles itself.
5. Confirm Windows installer and portable builds use isolated expected data,
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
auditable.
