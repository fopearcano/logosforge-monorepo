# Backup & Restore (Alpha)

## Backup / export

Logosforge backs up a project as a single portable JSON document.

- **Full project export** — `data_export.build_full_export(db, project_id)` (with
  `to_json`) produces an **import-compatible** document containing:
  `project`, `scenes` (all fields, incl. screenplay), `characters`, `places`,
  `notes`, `psyke_entries`, `outline` (tree), derived `plot` and `timeline`
  views, quantum state, and project `settings`.
- **Scoped exports** — story-elements and PSYKE-only exports are also available.
- **Manuscript exports** — Fountain / DOCX / PDF / HTML / plain text (see
  docs/Export.md); FDX is experimental.

### What backups never contain

- **No provider API keys.** Keys live in app-level settings (`settings.json`),
  not in project data, and are not serialized into any export/snapshot.
- **No absolute filesystem paths.**

### Optional systems

Backups degrade cleanly: subsystems with no data (empty PSYKE, no outline, etc.)
simply serialize as empty — exporting an empty project never errors.

## Restore / import

- **Import a backup** — `import_data.validate_import_data(raw)` validates the JSON
  (returning a readable error string on failure), then `import_json(db, data)`
  creates a **new project** from it. Importing never overwrites an existing
  project.
- **Restore a snapshot** — from *Version History*: select a snapshot → confirm →
  the manager takes a **pre-restore safety snapshot**, then imports the snapshot
  as a **new project**. On failure it returns no project and the UI shows a
  "Restore Failed" message (the cause is logged).
- **UI refresh** — a successful restore routes through `MainWindow._switch_project`,
  which rebuilds the active view and clears all stale state, so the restored
  project is shown immediately with nothing left over from the previous one.

## Safety summary

| Operation | Destructive? | Errors visible? | Result |
|-----------|-------------|-----------------|--------|
| Backup / export | No | Yes (dialog) | Portable JSON, no secrets/paths |
| Import backup | No | Yes (validation error) | New project |
| Restore snapshot | No (pre-restore safety snapshot) | Yes ("Restore Failed") | New project |
| Delete snapshot | Yes (confirmed) | — | Snapshot file removed |

## Tests

`tests/test_versioning_backup.py`, `tests/test_data_export.py`,
`tests/test_import*`.
