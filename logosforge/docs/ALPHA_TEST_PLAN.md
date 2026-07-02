# Alpha Test Plan — Manual Smoke Checklist

For private-alpha verification of **0.9.0-alpha**. Run on a throwaway project
first. Automated coverage: `python -m pytest tests/` (5,900+ tests).

## 1. Smoke — core navigation

- [ ] App launches (`python run.py`) without error.
- [ ] New Project (each Writing Mode: Novel, Screenplay, Graphic Novel, Stage,
      Series) — opens on Dashboard.
- [ ] Every left-panel section opens without error (Projects, Dashboard, Notes,
      Manuscript, Outline, Scenes, Plot, Timeline, Graph, PSYKE, …).
- [ ] Graphic-Novel project shows a **Pages** section; switching to a Novel
      project removes it.
- [ ] Sidebar collapse/expand works; active section stays highlighted.

## 2. Manuscript / writing

- [ ] Type continuously — editor never greys out, never loses focus.
- [ ] Trigger an Assistant/Logos action while typing — latest keystrokes are kept.
- [ ] Change font + size (Text/Bg) — applies without losing focus.
- [ ] Focus mode toggles the chrome; exiting restores it.

## 3. Data safety

- [ ] Create scenes/PSYKE/notes → close → reopen: content preserved.
- [ ] Version History: create a manual snapshot; restore it → loads as a **new**
      project; original untouched; a pre-restore safety snapshot exists.
- [ ] Switch projects: previous project's data/suggestions do not appear.
- [ ] Open the same project twice: second instance is **read-only**.

## 4. Provider / AI

- [ ] Set a provider (LM Studio/Ollama/OpenAI/Anthropic/OpenRouter) — persists
      after restart.
- [ ] Switch to **Anthropic** — no blank/tiny window; key field appears; model
      list populates.
- [ ] Enter a **custom model** name — accepted.
- [ ] Set an API **timeout**; force a timeout (tiny value) — readable error, no
      crash, no key in the message.
- [ ] Write in a non-English language — the Assistant replies in that language.

## 5. Export

- [ ] Export **Markdown / TXT / Fountain / FDX / HTML / JSON / CSV** — each writes
      a file and shows the path.
- [ ] Screenplay → **Fountain**: scene headings / character cues / dialogue look
      right.
- [ ] PDF/DOCX without the optional lib → **readable** "install …" message (no
      traceback).
- [ ] Open an exported JSON — **no `api_key`**, no absolute paths.
- [ ] Full Project export → re-import → new project with the same content.

## 6. 13-inch screen (≈1280×800)

- [ ] No section is cut off at the right edge.
- [ ] Assistant panel auto-hides to a strip when the window is narrow (no hidden
      panel, no tiny window).
- [ ] Dialogs (Settings, Version History, Outline confirm, Export) fit on-screen.
- [ ] PSYKE console is a slim bottom bar.

## 7. Regression checklist (before tagging alpha)

- [ ] Full suite green: `QT_QPA_PLATFORM=offscreen python -m pytest -q`.
- [ ] Safety-gate defaults unchanged: `logos_enabled=False`,
      `connector_enabled=False`, `connector_allow_writes=False`, API desktop mode.
- [ ] No API key in any export or log.
- [ ] Autosave/Versioning/lifecycle untouched unless a confirmed regression fix.

See [KNOWN_LIMITATIONS_ALPHA.md](KNOWN_LIMITATIONS_ALPHA.md) for expected gaps.
