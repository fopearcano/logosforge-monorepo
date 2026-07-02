# Data Safety (Alpha)

How Logosforge protects user work in the 0.9.0-alpha build. See also
docs/AutosaveVersioning.md and docs/BackupRestore.md.

## Layers of protection

1. **Authoritative SQLite store.** All project data lives in a single SQLite
   database (`logosforge.db`) and **every mutation commits immediately**
   (`session.commit()` per write). User work is durable in the DB at all times,
   independent of any file save — a crash does not lose committed work.
2. **Atomic project file writes.** Saving/exporting the portable `.json` uses
   `cloud_storage.atomic_write_text` (write to a sibling tempfile → `fsync` →
   `os.replace`), so a project file is never left half-written, even mid-sync on
   a cloud-backed folder.
3. **External-change detection.** An `mtime+size` fingerprint detects when a
   project file changed on disk underneath the app; autosave **blocks the
   overwrite**, emits a signal, and can write a conflict copy beside the file.
4. **Per-project file locks.** Opening a project acquires a lock; a project
   already open elsewhere opens **read-only** rather than racing writes.
5. **Versioned snapshots.** Timestamped JSON snapshots (auto + manual) per
   project, with a **pre-restore safety snapshot** before any restore.

## Guarantees

- **No silent critical failure.** Save/export/snapshot failures surface a status
  ("Save failed") or a dialog; load/restore failures return a clear error and are
  logged.
- **Non-destructive restore/import.** Restoring a snapshot or importing a backup
  creates a **new project**; the current project is never overwritten.
- **Project isolation.** Reads/writes are per-`project_id`; version snapshots are
  stored per project (`<config>/versions/<project_id>/`); switching projects
  clears stale UI/engine state and never leaks another project's data.
- **Typing is never lost on refresh.** Before the Manuscript editor rebuilds (on
  any refresh), pending per-scene edits are flushed to the DB and focus/cursor
  are restored — no keystroke loss, no grey-out.
- **No secret/path leakage.** Exports/snapshots contain story data only — **no
  provider API keys** (those live in app settings, not project data) and no
  absolute filesystem paths.

## Database safety

- `check_same_thread=False` (safe for Qt + the optional API threads);
  in-memory test DBs use a `StaticPool`.
- Migrations are **additive/idempotent** (`SQLModel.metadata.create_all`): old
  databases open unchanged and simply gain any new empty tables. No `DROP`/
  `TRUNCATE`, no silent column truncation.

## Known limitations (alpha)

- All projects share one `logosforge.db`; per-project backups/snapshots provide
  isolated recovery copies.
- Restore produces a **new** project (a recovery copy) rather than reverting the
  current project in place — intentional, to never clobber live data.
- No cloud sync or collaboration (cloud folders are treated as ordinary local
  paths only).
