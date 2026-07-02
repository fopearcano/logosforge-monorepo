# Alpha Release Candidate — Checklist

Companion to [ALPHA_RC_STATUS.md](ALPHA_RC_STATUS.md),
[ALPHA_TEST_COMMANDS.md](ALPHA_TEST_COMMANDS.md), and the broader
[ALPHA_RELEASE_CHECKLIST.md](ALPHA_RELEASE_CHECKLIST.md) (private-alpha closure).
This file is the **multi-mode RC** checklist used before tagging.

## Pre-release (hard gate)

- [x] Branch is `claude/setup-logosforge-app-5cVxF`; working tree clean.
- [x] Version is `0.9.0-alpha` (`logosforge/__init__.py`).
- [x] Alpha Release Gate audit = **A** ([ALPHA_RELEASE_GATE_AUDIT.md](ALPHA_RELEASE_GATE_AUDIT.md)).
- [x] Per-mode integrity audits = **A** (Screenplay / Graphic Novel / Stage Script / Series).
- [x] No production code changed during packaging.
- [ ] Manual smoke test completed (below).
- [ ] Maintainer sign-off to tag (tagging is a separate, explicit step).

## Automated tests

- [x] Focused gate — `pytest tests/test_alpha_release_gate.py` → **35 passed**.
- [x] Broad certification sweep → **1527 passed, 0 failures** (see
      [ALPHA_TEST_COMMANDS.md](ALPHA_TEST_COMMANDS.md)) — re-verified at the
      FINAL integration gate (2026-06-10) together with the post-sweep voice
      (392) and GN/Series/export (392) batches: **2311 passed, 0 failed**
      (see [ALPHA_RC_STATUS.md](ALPHA_RC_STATUS.md)).
- [x] Per-mode phase suites green (Screenplay 1–10, Graphic Novel 1–8, Stage
      Script 1–8, Series 1–8).
- [x] Cross-cutting green (structure invariant, project + PSYKE isolation,
      manuscript/outline separation, timeline, notes, logos).

## Manual smoke test

1. [ ] Launch the app (`python3 run.py`).
2. [ ] Create a new project.
3. [ ] Create **Act → Chapter → Scene** in the Outline.
4. [ ] On a **brand-new (empty)** project, open **Project Settings** and confirm the
       writing-mode selector is **enabled** and changes apply (mode is chosen at
       creation while empty). Create **five** projects, one per mode — **Novel,
       Screenplay, Graphic Novel, Stage Script, Series** — to exercise all editors.
5. [ ] Verify the **Manuscript** editor behavior matches each project's mode (prose
       vs. screenplay blocks vs. page/panel vs. stage blocks vs. teleplay blocks) in
       the **same** Manuscript section.
   - [ ] **Mode lock:** after a project has content (body/notes/PSYKE/etc.), open
         Project Settings and confirm the writing-mode selector is **disabled** with
         a lock message; the mode cannot be changed (no conversion in Alpha).
6. [ ] Verify **Outline** still shows the canonical Act → Chapter → Scene structure.
7. [ ] Verify **Timeline** opens and lanes are independent (not Acts/Seasons).
8. [ ] Verify **Notes** and **PSYKE** are project-bound.
9. [ ] Verify the **Logos** quick-actions dropdown is readable (not a tiny button row).
10. [ ] Verify changing the **theme** updates Assistant/Logos live.
11. [ ] Edit body text → confirm the project shows a **dirty** marker.
12. [ ] Close the app → confirm a **save prompt** appears for the modified project.
13. [ ] Reopen → confirm data **persists**.
14. [ ] **Export** one project/body (Markdown/Text/Fountain).
15. [ ] Confirm the export contains **no API keys / provider secrets**.
16. [ ] Switch projects → confirm **no data leakage** between projects.

## Project isolation

- [ ] Project A data (blocks, plans, Timeline, Notes, PSYKE, dashboards, export)
      not visible in Project B.
- [ ] Switching B → A returns A's data intact.
- [ ] A brand-new Project C has no A/B debris.

## Export / privacy

Exports and reports must **not** include: API keys, provider settings, Assistant
configuration secrets, unrelated/previous-project data, sentinel strings, system
prompts, debug markers, ComfyUI / image-generation settings, or production-
scheduling data. (Automated coverage in `tests/test_alpha_release_gate.py` and the
per-mode export tests.)

- [ ] Spot-check one exported file for the above.

## Dirty-state / save

- [ ] Creating/editing Manuscript/Outline/Timeline/Notes marks the project dirty.
- [ ] Preview-only operations (health/reflection/continuity/dashboard, rewrite
      preview, plan preview) do **not** mutate or mark dirty before apply.
- [ ] Cancel leaves data and dirty state unchanged.
- [ ] Project switch / close prompts to save when dirty.

## Theme / UI

- [ ] Sidebar routes to the correct sections; Manuscript mounts the correct mode
      editor; Outline/Timeline/Notes/PSYKE/Assistant mount correctly.
- [ ] Theme change propagates live to Assistant and the Logos toolbar.
- [ ] Usable at small window width; no obsolete "Classical" header / extra
      Navigator panel; Manuscript summary/navigation rail intact.
- [ ] **General Preferences fits small screens:** settings content scrolls
      vertically inside the dialog; the **Close row is sticky outside the
      scroll area** (bottom controls always reachable); dialog height is
      clamped to ~85% of the available screen; opening it never minimizes the
      app (parented to the main window).

## Series Navigator + export deps

- [ ] `pip install -r requirements.txt` installs `reportlab` + `python-docx`; PDF
      and DOCX export work. (If a lib is absent, export shows a graceful "install …"
      message and other formats still work.)
- [ ] In a **Series** project, the left **Plan** group shows **Series Navigator**;
      it does **not** appear in Novel / Screenplay / Graphic Novel / Stage Script.
- [ ] Series Navigator shows Season/Arc → Episode → Scene with canonical numbers;
      clicking a Season/Episode opens Outline, clicking a Scene opens Manuscript;
      A/B/C buckets reflect the Episode Beat Plan (or show an empty-state message).
      Navigation does not modify or dirty the project.

## Languages (multi-language infrastructure)

- [ ] New Project + Project Settings show **Writing Language** (full Whisper
      list, friendly "Italian (it)" names); changing it never mutates scene
      text and never unlocks/changes the writing mode.
- [ ] Project language **does not leak** across projects (switch A→B→A keeps
      each project's language and AI context).
- [ ] AI replies **preserve the project language** by default (no automatic
      translation; explicit ask required to translate).
- [ ] **Dexter's Room** transcription language: *Use project language*
      (default) / *Auto detect* / explicit code; invalid saved values repair
      to Auto with the message; segments carry project/mode metadata.
- [ ] **Grammar checking is DEFERRED (not a blocker):** no active grammar
      pass anywhere; the Manuscript Review menu shows a disabled
      *"Grammar Check — deferred after Alpha"* placeholder; Project Settings
      states the deferral (no per-language support claims); Dexter's Room
      has no grammar coupling; no startup/grammar dependency.
- [ ] **Unicode**: Chinese/Japanese/Arabic/Hebrew/emoji text saves, reloads,
      searches (titles/summaries) and exports (Markdown/TXT/JSON/Fountain
      UTF-8); CJK word count shows **≈ characters**; PDF glyph limits
      documented.
- [ ] **Alpha UI is English-only (localization deferred):** no UI-language
      selector anywhere; the Preferences Language section keeps only the
      default WRITING language and states the deferral; no partial/mixed
      translations visible; writing/Dexter languages stay fully
      multilingual and independent of the UI language.

## Deferred features (must remain off/hidden)

- [ ] **Canvas Plot** hidden from navigation.
- [ ] **Standalone Pages section disabled (fullscreen-hostile):** the left-panel
      **Pages** item is hidden in every mode and its route is inert (never mounts
      the old standalone Pages widget). The Graphic Novel structure lives in the
      **Outline** — the canonical page-first `Act → Page → Scene → Panel` tree
      (an Act owns its act-wide Pages and Scenes; a Scene can span Pages with
      `(continued)` labels; one Page can hold Panels from several Scenes via the
      scene's pinned start page; **chapters hidden** in GN mode) — **and** the
      **Manuscript**, which **derives from it** (a **comics script editor**:
      PAGE headings with act-wide numbers + one free-typing script block per
      panel with labeled Visual/Caption/Dialogue/SFX/Notes sections — not a
      tree, not a form; empty project → *"Create an Act to begin your Graphic
      Novel."* + **+ Act**), both over the shared `Scene.content` body
      (mirrored; Outline Panel double-click deep-links to the script block).
      **Verify in macOS fullscreen** (smoke-test F-items) that opening the GN
      Outline/Manuscript shows the script editor and does **not** minimize.
- [ ] **Local voice-to-script (MVP)** — **off by default** (`enable_voice_mode`;
      backend mode defaults to **Disabled**). App starts normally with voice off.
      The voice surface — **Dexter's Room** (View → Dexter's Room) — is a **floating, modeless, resizable window**
      parented to the main window (one instance; menu / Ctrl+Shift+V toggles
      show↔hide; Hide/close/Esc hide it with the transcript preview preserved;
      hiding while recording stops the session safely; never auto-shown, never
      auto-recording, no parentless top-level window). **Commit targets are
      explicit and mode-aware** (cursor / Note / PSYKE-draft-with-chosen-type /
      Screenplay Action–Dialogue / Stage Direction–Dialogue / GN Panel fields
      for the selected Panel): no auto-classification, no character or panel
      guessing, no voice commands; unavailable targets show disabled with a
      reason; stale transcripts cannot commit into a different project.
      **Phase 9 hardening gate passed** (voice matrix 427 + regression 449,
      0 failures; privacy audit clean — see `docs/ALPHA_RC_STATUS.md`).
      Backends: **Local PC** (faster-whisper, local model path, no auto-download)
      and **Local LAN Server** (private/loopback URLs only — public URLs/ngrok/
      tunnels blocked, redirects refused). Missing/misconfigured backend shows a
      non-blocking setup message (no crash). **No cloud speech API; audio never
      leaves the device/trusted LAN.** Manual plain-text commit only. See
      `docs/VOICE_MVP.md` + `docs/LOCAL_LAN_WHISPER.md`.
- [ ] No **ComfyUI / image-generation** module, action, or settings.
- [ ] No **production scheduling / rehearsal / writers-room** management.
- [ ] No **showrunner automation** that mutates data.
- [ ] **Writer QA harness**: 0 BLOCKER findings (`tools/writer_qa/run_writer_qa.py --suite all`).
