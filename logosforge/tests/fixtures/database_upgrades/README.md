# Database upgrade fixtures

These SQLite fixtures are sanitized derivatives of real application databases
included in the September 2026 workstation transfer. They preserve the released
table, column, index, and foreign-key topology plus representative row
cardinality, but contain no original project titles, manuscript prose, settings,
paths, credentials, or other user-controlled text.

- `whiteboard-released-unversioned.sqlite3` derives from the Whiteboard
  `whiteboard.db.pre-v1.bak` snapshot. The source SHA-256 was
  `ABE4A953550A1A35E63265F04CE499D6A4A8ED425A325475953EA44DAE170E0D`.
  The sanitized fixture SHA-256 is
  `3C7860ACEB884552B116A209923337F0684AFD77F231E4181B2FF1BFA0FC3491`.
  The database came from the v0.1.12-era released application, though the exact
  executable build is not encoded in SQLite.
- `pro-previous-unversioned.sqlite3` derives from the previous Pro 0.1.0
  `logosforge.db` snapshot. The manifest-recorded source SHA-256 was
  `FC0E0CD9538B47C684D424EBC99B43059E2009BD705871789EA900728815922A`.
  The sanitized fixture SHA-256 is
  `514EB6EF3A1E230AFB464F3005C5245AD8234021E0F86687FAE479644EA4B984`.
  The exact source commit is not encoded in SQLite.

Sanitization replaced every populated user-controlled text field with
deterministic fixture content, enabled SQLite secure deletion, switched to the
standalone delete journal, and ran `VACUUM` so superseded source text is not left
in free pages. Tests pin each committed fixture's SHA-256 and always copy it to a
temporary directory before opening it through `Database`.
