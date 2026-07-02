# Troubleshooting (Alpha)

Quick fixes for common alpha issues. If anything looks like data loss, **export a
backup first** (File → Export → Full Project) before experimenting.

## AI / provider

**Provider timeout** ("… timed out after Ns")
- The model didn't respond in time. Increase **API timeout** in Assistant
  Settings (local models are slow — try 300s+), and make sure the model/server is
  actually loaded and running.

**Provider settings issue** (no response, wrong output, key errors)
- Re-check Provider / Model / Base URL / API key in Assistant Settings. Keys are
  masked; a wrong key shows an HTTP 401/403. Local servers must be running.
- "… requires an API key" → add the key (or set `OPENAI_API_KEY` /
  `ANTHROPIC_API_KEY` / `OPENROUTER_API_KEY`). See [AI_SETUP.md](AI_SETUP.md).

**API not responding** (the optional HTTP API)
- The desktop app does **not** need the API. If you started it
  (`python -m logosforge.api`), it binds to `127.0.0.1:8765` in desktop mode;
  LAN/remote are experimental (set an auth token if exposed). Check the port and
  firewall.

**Slow local model**
- Use a smaller/quantised model, raise the timeout, and prefer Logos/Assistant
  actions over long generations. Cloud providers are faster.

## Editor / project

**Editor greyed out / lost typing**
- This was fixed in alpha (a refresh now flushes pending keystrokes and restores
  focus). If you still see it, save (Ctrl+S) and reopen the section; report it.

**Stale project data after switching projects**
- Switching projects clears caches/engines/views. If a panel looks stale, switch
  sections once. (No data is lost; the live store is per-project.)

**Project opens read-only**
- The project is locked by another open instance / machine (a safety lock). Close
  the other instance, or copy the file. An external-change warning means the file
  changed on disk underneath the app — use the conflict copy it offers.

## Export

**Export failure**
- You'll get a readable "Export failed" dialog. For **PDF** install `reportlab`;
  for **DOCX** install `python-docx` (`pip install reportlab python-docx`).
  Markdown / TXT / Fountain / FDX / HTML / JSON need no extra libraries.
- Permission/disk errors: choose a writable path.

## Appearance / console

**Missing fonts** (e.g. a "Segoe UI" warning on macOS/Linux)
- Harmless. Logosforge uses a font fallback list (Segoe UI → Helvetica/Arial/Noto
  → sans-serif); the app picks the first available font. No action needed.

**Qt stylesheet warnings**
- The app's stylesheets are clean of unsupported properties in this alpha. If you
  see "Unknown property" lines from a plugin or custom theme, they're cosmetic
  (the style is ignored, layout is unaffected).

## Still stuck?

Note your OS, Python version, provider, and the exact message, and file it for
the private alpha. See [KNOWN_LIMITATIONS_ALPHA.md](KNOWN_LIMITATIONS_ALPHA.md)
for things that are *expected* not to work yet.
