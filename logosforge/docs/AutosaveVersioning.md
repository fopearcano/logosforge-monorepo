# Autosave & Versioning (Alpha)

## Autosave (`logosforge/autosave.py`)

- **Debounced**: a single-shot timer coalesces rapid edits; no save runs on every
  keystroke.
- **Atomic**: writes the project `.json` via temp + `fsync` + `os.replace`.
- **External-change aware**: if the file changed on disk, autosave **blocks the
  overwrite**, emits `external_change_detected`, and can write a conflict copy.
- **Non-blocking & focus-safe**: autosave never touches the editor widget — it
  does not disable it, reload it, or steal focus.
- **Visible status**: emits `status_changed` ("Saving…", "Saved", "Save failed");
  failures are logged, never swallowed.
- Assistant- and Logos-applied changes mark autosave dirty just like manual
  edits, so AI-driven changes are persisted too.

Note: the live SQLite DB already holds every committed change immediately; the
`.json` autosave is the portable/shareable copy.

### Editor refresh safety

The Manuscript editor saves per-scene on a short debounce. When a full refresh is
triggered (e.g. an Assistant/Logos apply, or a structural change), the view:
1. **flushes** any pending per-scene saves first (so the rebuild reads the user's
   latest text — no keystroke loss), then
2. rebuilds and **restores focus + cursor** to the scene being edited.

## Versioning (`logosforge/version_manager.py`)

- **Per-project snapshots** under `<config>/versions/<project_id>/` as timestamped
  JSON (microsecond-precision filenames — no collisions).
- **Automatic** snapshots on a timer while the project is dirty, plus **manual**
  snapshots on demand (with an optional label).
- **Metadata** per snapshot: timestamp, reason (`autosave`/`manual`/
  `pre-restore safety snapshot`), label, size.
- **Retention**: oldest snapshots beyond `MAX_VERSIONS` (50) are pruned.
- **Per-project isolation**: `set_project()` re-points the manager; listing a
  project shows only that project's snapshots — no leakage across a switch.
- **Restore** (see docs/BackupRestore.md) is explicit, takes a pre-restore safety
  snapshot, and imports as a new project.

## Settings

- `version_*` interval/retention are module constants; autosave debounce is a
  module constant. No per-keystroke I/O.

## Tests

`tests/test_autosave.py`, `tests/test_manuscript_editor_stability.py`,
`tests/test_versioning_backup.py`.
