# Logosforge — Private Alpha (0.9.0-alpha)

A local-first **narrative operating system** that unifies writing, structure and
AI in one desktop app. This is an early **private alpha** — feature-frozen and
focused on stability. Expect rough edges, and **back up your work**.

## What you can do

- Write in a distraction-free **Manuscript** editor across five **Writing Modes**
  (Novel, Screenplay, Graphic Novel, Stage Script, Series).
- Plan with **Outline / Plot / Timeline / Graph** and a **PSYKE** story bible
  (characters, places, objects, lore, themes, relations).
- Get AI help from the **Assistant** (chat, critique, inline edits, Counterpart,
  Quantum outliner) and the inline **Logos** layer — always **propose-then-
  confirm**, never silent edits.
- **Export** to Markdown, TXT, Fountain, FDX, HTML, JSON, CSV (and PDF/DOCX with
  optional libraries).

## Install & run

Python **3.10+**:

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python3 run.py
```

Optional, only for those formats: `pip install reportlab` (PDF),
`pip install python-docx` (DOCX). See `docs/USER_GUIDE_ALPHA.md`.

## ⚠️ Backup warning

This is alpha software. Your work lives in a local database with autosave and
version snapshots, but **please back up**: use **File → Export → Full Project
(JSON)** regularly and keep copies. Restore loads a snapshot as a *new* project
(it never overwrites your current one). See `docs/BackupRestore.md`.

## AI setup (optional)

The editor works without AI. For AI features, open **Assistant → Settings** and
pick a provider:

- **Local:** LM Studio (`http://localhost:1234/v1`) or Ollama
  (`http://localhost:11434/v1`) — no key.
- **Cloud:** OpenAI / Anthropic / OpenRouter — paste your API key.

Set the model (custom names allowed) and a **timeout** (local models are slow —
the default is 300s). Keys are never written to your project files or exports.
Step-by-step: `docs/AI_SETUP.md`. Stuck? `docs/TROUBLESHOOTING.md`.

## Known limitations

- **PDF/DOCX** need optional libraries; **FDX/HTML** and the **API LAN/remote**
  modes are experimental.
- **Knowledge Graph, Semantic Continuity, Decision Radar, Guided Workflows** ship
  as services surfaced through Logos/Assistant — **no dedicated UI panel yet**.
- Plot/Timeline are derived from scene fields; grammar is basic.
- Single-user, **local-only** (no cloud sync or collaboration).

Full list: `docs/KNOWN_LIMITATIONS_ALPHA.md`.

## Recommended first test workflow

1. **New Project** → choose a **Writing Mode** (try Novel).
2. Write a couple of **scenes** in the Manuscript.
3. Add a **PSYKE** character; search it in the bottom console.
4. Generate an **Outline** via the Assistant (review and confirm it).
5. Configure a **provider** and ask the Assistant a question; toggle **Logos** ON
   for inline suggestions, then OFF.
6. **Export** the manuscript (Markdown or Fountain) and a **Full Project** backup.
7. **Close and reopen** the app; **reload** the project and confirm everything is
   intact.

## Alpha Release Candidate — multi-mode gate (2026-06-08)

This RC completes and stabilizes the five **Writing Modes** on the single
**universal Manuscript** (the editor adapts by `writing_mode`; canonical structure
stays Project → Act → Chapter → Scene):

- **Screenplay** (blocks + Fountain foundation), **Graphic Novel** (Page/Panel
  script), **Stage Script** (stage blocks), and **Series** (teleplay blocks;
  Act↦Season/Arc and Chapter↦Episode are display labels only) each add a planning
  pipeline, deterministic intelligence checks, Counterpart/Reflection, a controlled
  rewrite (preview → diff → confirmed apply), cross-unit continuity, and a Review
  Dashboard. **Novel** prose is unchanged (primary unit = Chapter).
- Every mutating AI action is **propose-then-confirm** (preview + Controlled
  Apply); deterministic checks never call a provider; actions are **mode-gated**.
- **Series Navigator** (left **Plan** group, Series-only): a read-only tree over
  Season/Arc → Episode → Scene with A/B/C buckets from the Episode Beat Plan; it
  navigates to Outline/Manuscript and never mutates data.
- **Export dependencies:** `requirements.txt` now lists `reportlab` (PDF) and
  `python-docx` (DOCX); a normal install supports every export format, with the
  same graceful fallback if a library is missing.
- **Graphic Novel — canonical `Act → Page → Scene → Panel` structure in the
  Outline + Manuscript (standalone Pages disabled):** the separate left-panel
  **Pages** route was fullscreen-hostile, so it is **disabled for Alpha** (hidden;
  inert route). The **Outline is the canonical structure** — one page-first tree,
  `Act → Page → Scene → Panel`: an **Act owns its act-wide Pages and its Scenes**;
  a **Panel belongs to one Scene** and sits on **one Page**; a **Scene can span
  several Pages** (shown as `Scene … (continued)`); **one Page can hold Panels
  from several Scenes** (pin the scene's *start page* in the selected-item
  editor; *Auto* chains it after the previous scene). **Chapters are hidden** in
  Graphic Novel mode (kept as storage labels for other modes). The selected-item
  editor edits the Panel's five fields (**Visual / Caption / Dialogue / SFX /
  Notes**), the scene title (rename), page title/notes and the scene start
  page, with add Act/Scene/Page/Panel, move and confirmed delete. The **Manuscript derives from the Outline**
  — the **comics script editor** (Superscript-style): the scene flows as a
  script document — PAGE headings showing the **act-wide** page numbers, then
  one large free-typing script block per panel with labeled sections (labels
  optional, unlabeled text is the Visual). Blocks parse back into the
  structured model on commit; line breaks are preserved; numbers stay
  auto-numbered; Outline Panel double-click deep-links to the script block;
  empty project → *"Create an Act to begin your Graphic Novel."* + **+ Act**.
  Not a tree, not a form. Storage is unchanged and the migration is purely
  additive (one nullable `Scene.gn_page_start` offset; `NULL` keeps the exact
  legacy sequential layout — non-destructive for existing projects). Export
  follows the same `Act → Page → Scene → Panel` order with explicit
  Panel → Scene / Panel → Page assignments (each panel's text exactly once; no
  image data, no settings/keys). Pages/Panels are script structure, not image
  generation; **Panels are the future anchor for visual production
  integrations**. Both surfaces are embedded child widgets (no separate route,
  no top-level window), addressing the earlier macOS fullscreen minimize. See
  `docs/KNOWN_LIMITATIONS_ALPHA.md`.
- **Graphic Novel UI alignment (pre-release fix):** both GN screens now use
  the SAME UX paradigm as the other modes — the **Manuscript** is one
  full-document block editor (ACT/SCENE headers, act-wide PAGE blocks,
  free-typing panel script blocks, mode label + live word count; the old
  single-scene "Comics Script" renderer and its scene dropdown are gone)
  and the **Outline** is the block/card planner (Act → Page → Scene → Panel
  cards with selection highlight, inline page/scene editing and start-page
  pinning; the old thin tree + empty detail pane is gone). Same canonical
  data, same mirroring, same deep-links.
- **Local voice-to-script (MVP, off by default):** an opt-in, **local-first**
  dictation foundation (`enable_voice_mode`; backend mode defaults to Disabled) —
  buffered microphone capture, simple pause detection, transcript preview, and
  **manual plain-text commit** at the editor cursor. Two backends: **Local PC**
  (`faster-whisper` + `sounddevice`, optional installs; local model path required,
  **no automatic downloads**) and **Local LAN Server** (capture stays local;
  finalized segments go only to a Whisper server you configured on the **trusted
  local network** — private/loopback addresses enforced, public URLs / ngrok /
  tunnels **blocked**, redirects refused; an opt-in companion server script ships
  at `scripts/local_whisper_server.py`). **No cloud speech API, no OpenAI
  Realtime; audio never leaves the device/trusted LAN.** No voice commands, no
  automatic dialogue/action classification (deferred hooks exist). **View →
  Dexter's Room** (Ctrl/Cmd+Shift+V) toggles the floating, modeless,
  resizable **Dexter's Room** voice workspace (parented to the main window; one instance; Hide/close/Esc
  hide it with the transcript preview preserved; hiding while recording stops
  the session safely; commit stays manual, auto-commit off by default). See
  `docs/VOICE_MVP.md` + `docs/LOCAL_LAN_WHISPER.md`.
- **General Preferences usable on small screens:** the Preferences dialog now
  scrolls its content vertically (sticky Close row outside the scroll area, so
  the bottom controls are always reachable) and clamps its height to ~85% of
  the available screen.
- **Multi-language writing (pre-finalization infrastructure):** every project
  has a **Writing Language** (full OpenAI Whisper list — 100 languages +
  Auto, friendly "Italian (it)" names, set in New Project / Project
  Settings; changing it never rewrites or translates your text). It
  coordinates: **AI** (assistant, Logos, rewrite tools and Billy voice
  proposals preserve the project language by default — never auto-translate,
  with RTL and CJK-aware instructions) and **Dexter's Room** (transcription
  language defaults to *Use project language*, with Auto detect and explicit
  overrides; per-segment language metadata). **Unicode-safe end-to-end**:
  Chinese/Japanese/Korean/Arabic/Hebrew/Hindi/… text saves, reloads,
  searches and exports (UTF-8 Markdown/TXT/JSON/Fountain; DOCX preserves
  Unicode; PDF glyph coverage depends on system/ReportLab fonts —
  documented); CJK word counts show **≈ characters**. **Dexter's Room is
  the dynamic voice writing room** — capture, transcript review/editing,
  formatting and preview-first AI drafting with explicit Apply; it is **not
  a grammar checker** and performs no automatic correction. **Grammar
  checking and deep text correction are deferred** to a later
  Review/Correction phase (the Review-menu entry is a disabled "deferred"
  placeholder; not an Alpha blocker). **The Alpha UI is English-only** —
  interface localization is deferred (the translation scaffolding stays
  dormant and non-user-facing); project writing language and Dexter
  language are separate from UI language and fully multilingual.
  Local-only: no cloud grammar or speech services anywhere.

**Final Alpha RC integration gate (2026-06-10): PASSED** — authoritative
sweep 1527 + voice stack 392 + GN/Series/export 392 = **2311 passed, 0
failed**; no blockers, no production changes; manual smoke test (V1–V49)
remains before tagging. See `docs/ALPHA_RC_STATUS.md`.

**FINAL ALPHA RC RE-CERTIFICATION (2026-06-11): PASSED — classification
A.** After the Graphic Novel `Act → Page → Scene → Panel` refactor, the
multi-language system (project Writing Language + Dexter language + full
Whisper list + Unicode/CJK/RTL writing) and the final scope cleanup
(Dexter = local voice writing room; grammar/text correction and UI
localization deferred; Alpha UI English-only), the complete Desktop Alpha
was re-certified with **zero changes**: broad sweep **1527** + full
voice/Dexter **569** + language/editor **359** + Graphic Novel **358** +
Series/lock/lifecycle/export **254** = **3067 passed, 0 failures**.
Manual smoke checks (microphone, macOS fullscreen, language/Unicode
UI, optional-export visuals) remain before tagging. See
`docs/ALPHA_RC_STATUS.md`.

**Verification:** the final global multi-mode integrity audit (Alpha Release Gate)
returned **A**. Focused gate `tests/test_alpha_release_gate.py` = **35 passed**;
the broad certification sweep = **1527 passed, 0 failures**
(see `docs/ALPHA_TEST_COMMANDS.md`).

**Still deferred / out of scope:** ComfyUI / image generation, Canvas Plot
(hidden), production scheduling, writers-room / showrunner automation, and a
Season/Episode-aware *global* Outline (the new hierarchy lives in the Series
Navigator — see below). Persistent serialized-story relation links are reported
but not yet persisted. See `docs/KNOWN_LIMITATIONS_ALPHA.md`,
`docs/ALPHA_RC_STATUS.md`, and `docs/ALPHA_RC_CHECKLIST.md`.

## Series — real Season → Episode → Act → Chapter → Scene hierarchy (Phase 1)

The Series Alpha shortcut (Act = Season, Chapter = Episode) is replaced by a real
hierarchy: **Season** and **Episode** are now **stored rows**, each Series scene
links to its Episode (`Scene.episode_id`, a nullable column — `NULL` everywhere
else, so nothing changes for Novel / Screenplay / Graphic Novel / Stage Script),
and the Act → Chapter → Scene outline is **episode-scoped**.

- **Series Navigator is now the structural editor** (Series-only, left **Plan**
  group): create / rename / delete / move Seasons, Episodes, internal
  Acts/Chapters and Scenes; move a scene between Episodes; per-episode A/B/C
  buckets; an "Unassigned Scenes" bucket so no body is hidden. Deleting a
  Season/Episode **unlinks** its scenes (it never deletes a body).
- **Legacy Series projects keep working** and offer a one-click, **confirmed,
  non-destructive Convert to Season/Episode** (old Act → Season title, old Chapter
  → Episode title; bodies, labels and order untouched).
- **Phase-1 boundary:** the *global* Outline / Manuscript / Timeline stay
  episode-agnostic (canonical flat Act → Chapter → Scene); the Navigator is the
  canonical Season/Episode surface. Export adds a Series Markdown outline
  (structure + bodies only — never settings or API keys).
- **Verification:** `tests/test_series_hierarchy.py` = **70 passed**; the legacy
  `tests/test_series_navigator.py` stays green (**26 passed**); broad cross-mode +
  gate sweep clean. See `docs/SERIES_ARCHITECTURE_CORRECTION_REPORT.md` §10.

> ⚠️ **This is Alpha software, not a final production release.** Back up your work.

Thanks for testing Logosforge. Please report what breaks.
