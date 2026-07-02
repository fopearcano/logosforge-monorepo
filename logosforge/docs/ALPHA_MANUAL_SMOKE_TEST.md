# Alpha RC — Manual Smoke Test

> **Status: PENDING MANUAL RETEST — template prepared.**
> This document is a retest *template*. The manual UI checklist has **not** been
> run yet; every manual item below is `PENDING MANUAL RETEST` / `NOT TESTED`.
> The automated focused suites (§ Automated pre-verification) **are** green, but
> automated tests are **not** a substitute for manual UI verification. Do not
> read this as "the smoke test passed."

- **Branch:** `claude/setup-logosforge-app-5cVxF`
- **Template prepared:** 2026-06-08
- **Manual retest date / tester:** _pending manual entry_
- **App version:** `0.9.0-alpha` (`logosforge/__init__.py`)

## Retest context

The Alpha RC was previously "ready", but manual testing surfaced four serious
blockers, all addressed by post-RC blocker fixes:

1. **Writing-mode switching after creation could misinterpret bodies** → mode is
   now **locked** once a project has meaningful content
   (`writing_modes.can_change_writing_mode` / `change_writing_mode`; commit
   `5ce9d86`).
2. **PDF export required a missing `reportlab`** → `requirements.txt` now lists
   `reportlab` + `python-docx`; PDF/DOCX still degrade gracefully when absent.
3. **Graphic Novel Manuscript and Pages/Panels needed one coherent body** → both
   now edit the same `Scene.content` via `graphic_novel_blocks` (commit `3ac8115`).
4. **Series needed the corrected hierarchy** → real
   **Season → Episode → Act → Chapter → Scene** with `Scene.episode_id` +
   `series_structure.py` + rebuilt Navigator (commit `f9dc1a2`).

This retest confirms those fixes in the running app and decides whether the Alpha
RC can proceed to **tag / release**.

## How to run

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python3 run.py
```

Optional export formats: `pip install reportlab python-docx` (PDF / DOCX). See
`RELEASE_NOTES_ALPHA.md` and `docs/AI_SETUP.md`.

## Automated pre-verification (completed)

Focused suites run before manual retest (supporting evidence only — **not** the
manual UI check). Command form:
`QT_QPA_PLATFORM=offscreen python -m pytest <file> -q -p no:cacheprovider`

| Suite | Result |
|-------|--------|
| `tests/test_alpha_release_gate.py` | **35 passed** |
| `tests/test_post_fix_regression_gate.py` | **20 passed** |
| `tests/test_pages_fullscreen_safe.py` (Pages fullscreen-safe dialogs) | **16 passed** |
| `tests/test_pages_alpha_fallback.py` (standalone Pages deferred) | **15 passed** |
| `tests/test_gn_manuscript_script_editor.py` (Manuscript comics script editor, Superscript-style blocks) | **56 passed** |
| `tests/test_gn_outline.py` (GN Outline Pages/Panels) | **38 passed** |
| `tests/test_gn_outline_integrity_gate.py` (GN Outline integrity gate) | **13 passed** |
| `tests/test_voice_mvp.py` (local voice-to-script MVP) | **35 passed** |
| `tests/test_voice_dictation_window.py` (floating Voice Dictation window) | **23 passed** |
| `tests/test_preferences_dialog.py` (scrollable General Preferences) | **11 passed** |
| `tests/test_voice_prefs_integrity_gate.py` (post-fix integrity gate) | **17 passed** |
| `tests/test_voice_commit_router.py` (Phase 2 mode-aware commit targets) | **41 passed** |
| `tests/test_voice_history.py` (Phase 3 history/edit/undo/retry/segments) | **37 passed** |
| `tests/test_voice_intents.py` (Phase 4 intent router, preview-first ops) | **37 passed** |
| `tests/test_voice_billy_bridge.py` (Phase 5 Billy Voice Bridge) | **35 passed** |
| `tests/test_voice_room.py` (Phase 6 Dexter's Room shell: state/queue/modes) | **26 passed** |
| `tests/test_voice_glossary.py` (Phase 7 project glossary + corrections) | **28 passed** |
| `tests/test_voice_setup.py` (Phase 8 setup/diagnostics/backend profiles) | **28 passed** |
| `tests/test_voice_alpha_gate.py` (Phase 9 end-to-end hardening gate) | **9 passed** |
| `tests/test_voice_lan.py` (backend modes + LAN Whisper server) | **43 passed** |
| `tests/test_voice_lan_server.py` (LAN companion server + client integration) | **22 passed** |
| `tests/test_gn_pages_manuscript_sync.py` (GN shared body) | **30 passed** |
| `tests/test_series_hierarchy.py` (Series hierarchy) | **70 passed** |
| `tests/test_series_navigator.py` (Navigator + deps) | **26 passed** |
| `tests/test_writing_mode_lock.py` (mode lock) | **22 passed** |
| `tests/test_export_safety.py` (export privacy) | **4 passed** |
| **Total** | **737 passed, 0 failed** |

> Environment note: PDF/DOCX export tests fail only where `reportlab` /
> `python-docx` are not installed (pre-existing, graceful-degradation behavior),
> not a code regression. Full certification was **not** run (out of scope here).

## Manual retest checklist

Legend — **Result:** `PASS` / `FAIL` / `PARTIAL` / `NOT TESTED` / `BLOCKED`
(all start `PENDING MANUAL RETEST`). **Auto:** `✓` = an automated test exercises
this behavior as supporting evidence (the manual UI check is still required).

### Core launch / project

| # | Item | Result | Auto |
|---|------|--------|------|
| 1 | Launch app | PENDING MANUAL RETEST | |
| 2 | Create new project | PENDING MANUAL RETEST | ✓ |
| 3 | Create Act → Chapter → Scene | PENDING MANUAL RETEST | ✓ |
| 4 | Save project | PENDING MANUAL RETEST | |
| 5 | Reopen project | PENDING MANUAL RETEST | ✓ |
| 6 | Data persists | PENDING MANUAL RETEST | ✓ |

### Writing-mode lock

| # | Item | Result | Auto |
|---|------|--------|------|
| 7 | Empty new project can change writing mode | PENDING MANUAL RETEST | ✓ |
| 8 | After meaningful content, selector disabled/blocked | PENDING MANUAL RETEST | ✓ |
| 9 | Blocked mode change shows clear warning | PENDING MANUAL RETEST | ✓ |
| 10 | Blocked mode change does not mutate body | PENDING MANUAL RETEST | ✓ |
| 11 | Blocked mode change does not mark dirty unnecessarily | PENDING MANUAL RETEST | |
| 12 | Novel body cannot switch to Screenplay | PENDING MANUAL RETEST | ✓ |
| 13 | Screenplay body cannot switch to Novel | PENDING MANUAL RETEST | ✓ |
| 14 | Graphic Novel cannot switch to another mode | PENDING MANUAL RETEST | ✓ |
| 15 | Stage Script cannot switch to another mode | PENDING MANUAL RETEST | ✓ |
| 16 | Series cannot switch to another mode | PENDING MANUAL RETEST | ✓ |

### Novel

| # | Item | Result | Auto |
|---|------|--------|------|
| 17 | Novel Manuscript opens prose editor | PENDING MANUAL RETEST | |
| 18 | Novel body saves / reloads correctly | PENDING MANUAL RETEST | ✓ |

### Screenplay

| # | Item | Result | Auto |
|---|------|--------|------|
| 19 | Screenplay Manuscript opens block editor | PENDING MANUAL RETEST | |
| 20 | Screenplay block body saves / reloads | PENDING MANUAL RETEST | ✓ |
| 21 | Fountain export works (if tested) | PENDING MANUAL RETEST | ✓ |

### Graphic Novel

| # | Item | Result | Auto |
|---|------|--------|------|
| 22 | Manuscript opens the **comics script editor** — PAGE headings (act-wide numbers) + one free-typing script block per panel (labeled Visual/Caption/Dialogue/SFX/Notes sections; no tree, no form fields) | PENDING MANUAL RETEST | ✓ |
| 23 | Outline shows the canonical `Act → Page → Scene → Panel` tree (page-first; chapters hidden); same Pages/Panels as the Manuscript | PENDING MANUAL RETEST | ✓ |
| 23b | Empty GN project: Manuscript + Outline show *"Create an Act to begin your Graphic Novel."* with **+ Act**; clicking it creates Act 1 and offers **+ Page** | PENDING MANUAL RETEST | ✓ |
| 23c | A scene spanning several pages shows `Scene … (continued)` on each following Outline page; pinning a scene's **start page** ("Scene starts on act page") makes one Page hold panels from two scenes; Auto returns it after the previous scene | PENDING MANUAL RETEST | ✓ |
| 24 | Editing in the Manuscript updates the Outline (shared body) | PENDING MANUAL RETEST | ✓ |
| 25 | Editing in the Outline updates the Manuscript (shared body) | PENDING MANUAL RETEST | ✓ |
| 26 | Add Page updates both surfaces | PENDING MANUAL RETEST | ✓ |
| 27 | Add Panel (per-page button) updates both surfaces | PENDING MANUAL RETEST | ✓ |
| 28 | Delete Panel / Page updates both (after confirm) | PENDING MANUAL RETEST | ✓ |
| 29 | Reorder Panel updates both | PENDING MANUAL RETEST | ✓ |
| 30 | Script editor stays readable/usable with many pages & panels (scrolling) | PENDING MANUAL RETEST | |
| 31 | Export uses shared Pages/Panels body | PENDING MANUAL RETEST | ✓ |
| 32 | No image-generation / ComfyUI fields appear | PENDING MANUAL RETEST | ✓ |

### Fullscreen window-management — Graphic Novel Outline + Manuscript Page/Panel editor

> The standalone **Pages** sidebar section is **disabled for Alpha** (it was
> fullscreen-hostile). The Graphic Novel structure lives in the **Outline** —
> the canonical page-first `Act → Page → Scene → Panel` tree (chapters hidden;
> scenes can span pages with `(continued)` labels; a pinned scene start page
> lets one Page hold panels from several scenes) — **and** the **Manuscript**,
> which derives from it (a **comics script editor**: inline PAGE blocks with
> act-wide numbers → panel script blocks — not a tree), both over the shared
> `Scene.content` body (child-widget-only; no separate route, no top-level
> window). Headless tests cover both surfaces + route safety
> (`tests/test_gn_outline.py`, `tests/test_gn_act_page_structure.py`,
> `tests/test_gn_manuscript_script_editor.py`,
> `tests/test_pages_alpha_fallback.py`, `tests/test_pages_fullscreen_safe.py`).
> **Confirm the fullscreen behavior manually** — especially that opening the GN
> Outline/Manuscript does not minimize the app:

| # | Item | Result | Auto |
|---|------|--------|------|
| F1 | Enter macOS **fullscreen**, open a Graphic Novel project | PENDING MANUAL RETEST | |
| F2 | The standalone **Pages** sidebar item is **not shown** (disabled) | PENDING MANUAL RETEST | ✓ |
| F3 | Click **Outline** — the GN Page/Panel Outline appears; app does **not** minimize/flicker | PENDING MANUAL RETEST | partial |
| F4 | Outline shows the canonical page-first `Act → Page → Scene → Panel` tree (chapters hidden; `(continued)` labels for spanning scenes) | PENDING MANUAL RETEST | ✓ |
| F5 | Add Act / Scene / Page / Panel in the Outline; rename a Scene and a Page; edit Visual / Caption / Dialogue / SFX / Notes; pin a scene's start page to share a Page between two scenes | PENDING MANUAL RETEST | ✓ |
| F6 | Open the **Manuscript** — the comics script editor shows the same structure with act-wide PAGE numbers (mirrored); app stays fullscreen | PENDING MANUAL RETEST | ✓ |
| F7 | Export Graphic Novel text / Markdown (`Act → Page → Scene → Panel`, explicit Panel → Scene / Panel → Page assignments, each panel once) | PENDING MANUAL RETEST | ✓ |

### Local voice-to-script (MVP) — OFF by default

> Local-first dictation; **no cloud, no audio upload**. Requires optional local
> backends (`faster-whisper`, `sounddevice`) + a local model path. The dictation
> surface is a **floating, modeless, resizable window** (one instance, toggled
> show/hide). Headless tests cover the logic + panel + window
> (`tests/test_voice_mvp.py`, `tests/test_voice_dictation_window.py`). Confirm
> with a real microphone manually:

| # | Item | Result | Auto |
|---|------|--------|------|
| V1 | App starts normally with voice off; no voice panel shown | PENDING MANUAL RETEST | ✓ |
| V2 | Enable `enable_voice_mode`; without backend/model the panel shows a non-blocking setup message (no crash) | PENDING MANUAL RETEST | ✓ |
| V3 | Configure local Whisper model path + install `faster-whisper`/`sounddevice` | PENDING MANUAL RETEST | |
| V4 | View → Voice Dictation (Ctrl/Cmd+Shift+V); Start; speak a short sentence; Stop | PENDING MANUAL RETEST | |
| V5 | Transcript appears in the preview | PENDING MANUAL RETEST | ✓ |
| V6 | Click in the editor, then Commit — text inserts at the cursor | PENDING MANUAL RETEST | ✓ |
| V7 | Clear removes the preview | PENDING MANUAL RETEST | ✓ |
| V8 | No crash when the microphone is unavailable / permission denied | PENDING MANUAL RETEST | ✓ |
| V9 | App does not freeze while transcribing; closing while recording stops safely | PENDING MANUAL RETEST | partial |
| V10 | No audio leaves the device (local-first) | PENDING MANUAL RETEST | ✓ |
| V11 | Save/reopen the project — committed dictation text persists | PENDING MANUAL RETEST | ✓ |
| V12 | Stop during Processing — no hang; status returns to off | PENDING MANUAL RETEST | ✓ |
| V13 | Switch project while recording — session stops; transcript is NOT committed into the other project | PENDING MANUAL RETEST | ✓ |
| V14 | Open the Voice Dictation window in macOS fullscreen — app does not minimize (modeless window parented to the main window) | PENDING MANUAL RETEST | partial |
| V15 | Voice Dictation opens as a **floating, resizable** window; toggle (menu/Ctrl+Shift+V) hides and reopens it repeatedly with **no duplicates** | PENDING MANUAL RETEST | ✓ |
| V16 | Hide/Close/Esc hide the window; transcript preview is still there on reopen (until Clear) | PENDING MANUAL RETEST | ✓ |
| V17 | Hiding/closing while recording stops the session safely and keeps the preview | PENDING MANUAL RETEST | ✓ |
| V18 | **Send to** dropdown lists mode-aware targets; unavailable ones are greyed out with a reason tooltip | PENDING MANUAL RETEST | ✓ |
| V19 | Commit to **New Note** / **PSYKE draft (type selector, default Other)** creates the entry only on Commit | PENDING MANUAL RETEST | ✓ |
| V20 | GN: focus a Panel script block → Panel field targets enable; commit appends to that panel; no panel selected → "Select a Panel first." | PENDING MANUAL RETEST | ✓ |
| V21 | Screenplay/Stage Dialogue target requires picking a character (never guessed from the transcript) | PENDING MANUAL RETEST | ✓ |
| V22 | Switch project with a pending transcript → commit is blocked ("Project changed since transcription…") | PENDING MANUAL RETEST | ✓ |
| V23 | History list shows each dictated segment with status; Edit → Apply Edit corrects a segment (original restorable) | PENDING MANUAL RETEST | ✓ |
| V24 | Check 2+ segments → Commit inserts them once, in order, with edited text; rows flip to committed → target | PENDING MANUAL RETEST | ✓ |
| V25 | **Undo last commit** reverts the insertion/created entry; disabled with a reason after unrelated edits | PENDING MANUAL RETEST | ✓ |
| V26 | **Retry** re-transcribes locally while segment audio is held; says "Audio segment no longer available." after | PENDING MANUAL RETEST | ✓ |
| V27 | Merge adjacent segments / Split at cursor behave; Discard + Clear uncommitted never touch the project | PENDING MANUAL RETEST | ✓ |
| V28 | Mode selector defaults to **Dictation**; switching to **Intent** shows intent controls (opt-in only) | PENDING MANUAL RETEST | ✓ |
| V29 | Intent **Preview** shows before/after (or Note/PSYKE preview); **Apply** is enabled only with a valid preview; **Cancel** mutates nothing | PENDING MANUAL RETEST | ✓ |
| V30 | Rule-based cleanup fixes spacing/punctuation without AI; AI intents disable with the configure-provider message when no provider is set | PENDING MANUAL RETEST | ✓ |
| V31 | AI rewrite replaces exactly the selected text after Apply; Undo restores it; stale selection blocks Apply with the regenerate message | PENDING MANUAL RETEST | ✓ |
| V32 | **Billy row**: with no AI provider configured, all Billy actions are disabled with the configure message | PENDING MANUAL RETEST | ✓ |
| V33 | Speak an instruction → select the segment → Generate Proposal → before/after preview appears; Apply mutates once; Cancel mutates nothing | PENDING MANUAL RETEST | ✓ |
| V34 | GN: with a Panel selected, Billy's Panel-field proposal applies to the chosen field and Outline/Manuscript mirror; Undo restores | PENDING MANUAL RETEST | ✓ |
| V35 | Dangerous spoken "commands" ("delete the project", "run this command", …) get the chat-only refusal — nothing executes | PENDING MANUAL RETEST | ✓ |
| V36 | **Dexter's Room header** shows the session state + context summary (project · mode · section · panel · selection) and updates as you work | PENDING MANUAL RETEST | ✓ |
| V37 | Four workflow modes (Dictation default / Intent / Ask Billy / Edit with Billy); Billy modes preset the operation; mode is never auto-detected | PENDING MANUAL RETEST | ✓ |
| V38 | Proposal queue lists every proposal with status; stale items refuse Apply; double-click re-activates a ready one; Pause keeps session/history/queue | PENDING MANUAL RETEST | ✓ |
| V39 | Glossary: add a term with a misrecognition → dictate it → segment shows "N suggestion(s)"; Apply fixes the transcript only; Reject leaves it | PENDING MANUAL RETEST | ✓ |
| V40 | Edit a segment, **Learn correction…** → confirmation lists the pair; confirmed pair appears in the Glossary and corrects future dictation | PENDING MANUAL RETEST | ✓ |
| V41 | **Glossary…** manager (parented window): add/delete/enable/search; **Import project terms** previews and asks before creating; PSYKE/Outline unchanged | PENDING MANUAL RETEST | ✓ |
| V42 | Spoken punctuation ("comma", "period", "new paragraph") suggested and applied correctly; project switch blocks applying old-project corrections | PENDING MANUAL RETEST | ✓ |
| V43 | **Voice Setup…** opens (parented); pick a backend → status chip shows ready/missing-dependency/missing-model; invalid paths never crash | PENDING MANUAL RETEST | ✓ |
| V44 | Configure faster-whisper (model dir) or whisper.cpp (executable + model) → Test backend reports ready; Test transcription on a short WAV shows text in the panel (not committed) | PENDING MANUAL RETEST | |
| V45 | Performance profile (Fast draft / Balanced / Accurate) updates silence/segment/beam; Custom exposes the fields; no GPU required | PENDING MANUAL RETEST | ✓ |
| V46 | With no valid backend, Dexter's Room Start is disabled with "Local Whisper is not configured. Open Voice Setup…"; Copy diagnostics has no secrets | PENDING MANUAL RETEST | ✓ |
| V47 | Full pipeline: speak → transcript → glossary correction → commit as dictation → Undo; then Send to Billy → Apply one proposal, Cancel another | PENDING MANUAL RETEST | ✓ |
| V48 | Close the app while recording — the session stops safely (reopen: app normal) | PENDING MANUAL RETEST | ✓ |
| V49 | Export the project — no transcript history, glossary internals, audio or voice temp data in the export | PENDING MANUAL RETEST | ✓ |
| L1 | Backend selector shows Disabled / Local PC / Local LAN Server / Mock; default Disabled | PENDING MANUAL RETEST | ✓ |
| L2 | Start a Whisper server on another LAN machine (`docs/LOCAL_LAN_WHISPER.md`) | PENDING MANUAL RETEST | |
| L3 | Select **Local LAN Server**; enter the private LAN URL (e.g. `http://192.168.x.x:8765`) | PENDING MANUAL RETEST | ✓ |
| L4 | **Check LAN server** reports reachable | PENDING MANUAL RETEST | ✓ |
| L5 | Start → speak → Stop: segment goes to the LAN server; transcript appears in preview | PENDING MANUAL RETEST | ✓ |
| L6 | Commit inserts the LAN transcript at the cursor | PENDING MANUAL RETEST | ✓ |
| L7 | Turn the LAN server off → unreachable warning, no crash | PENDING MANUAL RETEST | ✓ |
| L8 | Enter a public URL (e.g. `https://example.com`) → blocked with the local-address warning | PENDING MANUAL RETEST | ✓ |
| L9 | No audio leaves the device except to the configured private LAN server | PENDING MANUAL RETEST | ✓ |
| L10 | Enable `--auth-token` on the server: missing token rejected (401), correct token accepted | PENDING MANUAL RETEST | ✓ |

### Stage Script

| # | Item | Result | Auto |
|---|------|--------|------|
| 33 | Stage Script Manuscript opens stage block editor | PENDING MANUAL RETEST | |
| 34 | Stage blocks save / reload correctly | PENDING MANUAL RETEST | ✓ |

### Series

| # | Item | Result | Auto |
|---|------|--------|------|
| 35 | Series Navigator under Plan, Series mode only | PENDING MANUAL RETEST | ✓ |
| 36 | Navigator absent in Novel/Screenplay/GN/Stage | PENDING MANUAL RETEST | ✓ |
| 37 | Create Season | PENDING MANUAL RETEST | ✓ |
| 38 | Create Episode inside Season | PENDING MANUAL RETEST | ✓ |
| 39 | Create Act inside Episode | PENDING MANUAL RETEST | ✓ |
| 40 | Create Chapter inside Act | PENDING MANUAL RETEST | ✓ |
| 41 | Create Scene inside Chapter | PENDING MANUAL RETEST | ✓ |
| 42 | Rename Season | PENDING MANUAL RETEST | ✓ |
| 43 | Rename Episode | PENDING MANUAL RETEST | ✓ |
| 44 | Move Season (implemented) | PENDING MANUAL RETEST | ✓ |
| 45 | Move Episode within Season (implemented) | PENDING MANUAL RETEST | ✓ |
| 46 | Open Episode Outline (Navigator subtree) | PENDING MANUAL RETEST | |
| 47 | Episode Outline shows Act→Chapter→Scene (no Season/Episode confusion) | PENDING MANUAL RETEST | ✓ |
| 48 | Clicking Scene opens universal Manuscript | PENDING MANUAL RETEST | ✓ |
| 49 | Manuscript path shows full Series path — **deferred (Phase 1)**; path exists at data layer (`scene_series_path`), title-bar wiring deferred | PENDING MANUAL RETEST | |
| 50 | Moving Episode does not lose Scene body | PENDING MANUAL RETEST | ✓ |
| 51 | Series export traverses Season→Episode→Act→Chapter→Scene | PENDING MANUAL RETEST | ✓ |
| 52 | A/B/C Plots show from Episode data or clear empty state | PENDING MANUAL RETEST | ✓ |
| 53 | No old Act=Season / Chapter=Episode confusion (legacy adapter documented) | PENDING MANUAL RETEST | ✓ |

### Timeline

| # | Item | Result | Auto |
|---|------|--------|------|
| 54 | Timeline opens | PENDING MANUAL RETEST | |
| 55 | Timeline lanes independent from Outline / Series Seasons | PENDING MANUAL RETEST | ✓ |
| 56 | Timeline does not auto-create fake lanes from Seasons/Episodes | PENDING MANUAL RETEST | ✓ |
| 57 | Timeline links show correct path (if tested) | PENDING MANUAL RETEST | ✓ |

### Notes / PSYKE

| # | Item | Result | Auto |
|---|------|--------|------|
| 58 | Notes are project-bound | PENDING MANUAL RETEST | ✓ |
| 59 | PSYKE is project-bound | PENDING MANUAL RETEST | ✓ |
| 60 | Switching projects clears old Notes/PSYKE context | PENDING MANUAL RETEST | ✓ |

### Exports / dependencies

| # | Item | Result | Auto |
|---|------|--------|------|
| 61 | `requirements.txt` includes `reportlab` | PENDING MANUAL RETEST | ✓ |
| 62 | `requirements.txt` includes `python-docx` | PENDING MANUAL RETEST | ✓ |
| 63 | Markdown export works | PENDING MANUAL RETEST | ✓ |
| 64 | TXT export works (if tested) | PENDING MANUAL RETEST | ✓ |
| 65 | Fountain export works for Screenplay (if tested) | PENDING MANUAL RETEST | ✓ |
| 66 | JSON export works (if tested) | PENDING MANUAL RETEST | ✓ |
| 67 | PDF works if `reportlab` installed, else graceful message | PENDING MANUAL RETEST | ✓ |
| 68 | DOCX works if `python-docx` installed, else graceful message | PENDING MANUAL RETEST | ✓ |
| 69 | Exports contain no API keys / provider settings | PENDING MANUAL RETEST | ✓ |

### Project isolation

| # | Item | Result | Auto |
|---|------|--------|------|
| 70 | Create Project A with content | PENDING MANUAL RETEST | ✓ |
| 71 | Create Project B with different content | PENDING MANUAL RETEST | ✓ |
| 72 | Switch A → B: no A data visible | PENDING MANUAL RETEST | ✓ |
| 73 | Switch B → A: A data returns | PENDING MANUAL RETEST | ✓ |
| 74 | New Project C starts clean | PENDING MANUAL RETEST | ✓ |

### Dirty / save / close

| # | Item | Result | Auto |
|---|------|--------|------|
| 75 | Editing body marks project dirty | PENDING MANUAL RETEST | |
| 76 | Editing Outline marks project dirty | PENDING MANUAL RETEST | |
| 77 | Editing Timeline/Notes marks dirty if changed | PENDING MANUAL RETEST | |
| 78 | Preview-only actions do not mutate body | PENDING MANUAL RETEST | ✓ |
| 79 | Closing dirty project asks to save | PENDING MANUAL RETEST | |
| 80 | Closing clean project does not ask unnecessarily | PENDING MANUAL RETEST | |
| 81 | Save works | PENDING MANUAL RETEST | |
| 82 | Save As works | PENDING MANUAL RETEST | |
| 83 | Open works | PENDING MANUAL RETEST | |
| 84 | Refresh project list works | PENDING MANUAL RETEST | |

### General Preferences (scrollable, small-screen safe)

| # | Item | Result | Auto |
|---|------|--------|------|
| P1 | Open Preferences (Ctrl/Cmd+,) — window fits the screen (height clamped) | PENDING MANUAL RETEST | ✓ |
| P2 | Content scrolls vertically when taller than the window | PENDING MANUAL RETEST | ✓ |
| P3 | Close button row is sticky at the bottom and always reachable (outside the scroll area) | PENDING MANUAL RETEST | ✓ |
| P4 | Works on a small laptop screen / high UI scale — bottom controls still reachable | PENDING MANUAL RETEST | partial |
| P5 | Open Preferences in macOS fullscreen — app does not minimize | PENDING MANUAL RETEST | partial |
| P6 | Settings still persist on Close (theme, AI provider, Connector, storage folder) | PENDING MANUAL RETEST | ✓ |

### UI / scope

| # | Item | Result | Auto |
|---|------|--------|------|
| 85 | Logos dropdown is readable | PENDING MANUAL RETEST | |
| 86 | Assistant theme updates live after Appearance change | PENDING MANUAL RETEST | |
| 87 | No unwanted Navigator panel returns | PENDING MANUAL RETEST | |
| 88 | Canvas Plot remains hidden / deferred | PENDING MANUAL RETEST | ✓ |
| 89 | No ComfyUI / image-generation actions appear | PENDING MANUAL RETEST | ✓ |
| 90 | No production scheduling / writers-room automation appears | PENDING MANUAL RETEST | ✓ |

### Languages (multi-language infrastructure)

| # | Item | Result | Auto |
|---|------|--------|------|
| L1 | New Project dialog shows **Writing Language** (defaults to the global default); Project Settings shows and saves it with friendly names ("Italian (it)") | PENDING MANUAL RETEST | ✓ |
| L2 | Write Chinese / Japanese / Arabic / Hebrew / emoji text; save, close, reopen — text intact (editor + DB) | PENDING MANUAL RETEST | ✓ |
| L3 | Export Markdown/TXT/JSON/Fountain of that project — UTF-8 intact; PDF either renders or its glyph limitation matches the docs | PENDING MANUAL RETEST | partial |
| L4 | With a non-English project language, an AI reply stays in that language and does NOT translate user text unasked | PENDING MANUAL RETEST | partial |
| L5 | Dexter's Room Setup: language shows **Use project language** by default; explicit pick and Auto both work; invalid saved value repairs to Auto with the message | PENDING MANUAL RETEST | ✓ |
| L6 | Grammar is deferred: no underlines/popup appear while typing; Manuscript Review menu shows a **disabled** "Grammar Check — deferred after Alpha"; Project Settings shows the deferral note | PENDING MANUAL RETEST | ✓ |
| L7 | UI is English-only: Preferences → Language has **no UI-language selector** (only the default writing language + English-only note); all labels stay English regardless of project language | PENDING MANUAL RETEST | ✓ |
| L8 | CJK project shows **≈ N characters** word count; switch project A (it) → B (none) → A — no language leak anywhere | PENDING MANUAL RETEST | ✓ |

## Release blocker criteria

A **release blocker** if any of these FAIL: app cannot launch · project creation
broken · save/open broken · project isolation broken · Manuscript unusable ·
writing-mode lock broken after meaningful content · mode switching corrupts body ·
Graphic Novel Outline/Manuscript loses Panel data · Series cannot create/navigate
Season → Episode → Act → Chapter → Scene · dirty close-save prompt broken · data
loss · export leaks API/provider secrets · Unicode text corrupts on save/reload ·
project language leaks between projects · Dexter sends raw audio to cloud/AI ·
Dexter auto-applies changes without confirmation · Dexter cannot gracefully
handle a missing backend/microphone · the standalone-Pages fullscreen minimize
bug returns · export crashes instead of showing the graceful PDF/font
limitation.

**Non-blocking** (acceptable for Alpha): optional PDF/DOCX dependency absent but
graceful message works · minor UI spacing · dashboard refresh requires manual
refresh · A/B/C explicit assignment deferred if empty state is clear · Series
legacy migration not automatic but old data remains safe · panel undocking
deferred if collapsible layout works · **grammar checking deferred** (no active
checker; placeholder disabled) · **UI localization deferred** (English-only UI) ·
imperfect Whisper transcription quality (review-first by design) · incomplete
PDF glyph coverage when graceful/documented · RTL layout polish (storage/editing
safe; limitation documented).

## Blocker list

_None recorded — pending manual retest._

## Non-blocking issue list (known, pre-documented)

These are already documented in `docs/KNOWN_LIMITATIONS_ALPHA.md` and are
**non-blocking**; confirm during retest:

- Global Outline / Manuscript / Timeline stay episode-agnostic; the Series
  Navigator is the canonical Season/Episode surface (Phase-1 boundary).
- Manuscript title bar does not yet display the full Series path (data layer
  provides it; wiring deferred) — item 49.
- Move-Episode-across-Seasons and internal Act/Chapter reordering deferred
  (Scene reorder + move-scene-between-Episodes supported).
- PDF/DOCX require optional libs; degrade gracefully when absent.
- Dashboards refresh on open / manual button (no live recompute).
- ComfyUI is a disabled stub; the image-*prompt* text export is a legacy GN
  surface — no image generation runs.

## Decision

**PENDING MANUAL RETEST.** Automated focused suites are green (422 passed), but
the manual UI checklist above has not been executed. **Do not tag** the Alpha RC
until the manual checklist is completed and this decision is updated to one of:

- ✅ **Ready to tag** — all blocker-criteria items PASS; only documented
  non-blocking issues remain.
- ⚠️ **Retest required** — partial/blocked items need re-running.
- ⛔ **Not ready to tag** — one or more release blockers FAIL.
