# Changelog

All notable changes to Logosforge. This project uses semantic-ish versioning;
dates are release-readiness milestones, not packaged builds.

## [0.9.0-alpha] — pre-finalization refactor — 2026-06-11

### FINAL ALPHA RC RE-CERTIFICATION (post GN shared-renderer fix) — PASSED (2026-06-11)

Audit-only capstone at `4437cbe`: the GN renderer blocker is resolved
(shared WritingCoreView/PlanView mounts pinned; legacy unreachable);
full Alpha scope re-verified (modes, lock, Dexter, language/Unicode,
deferrals, exports, requirements, blocker policy, porting contract).
Evidence: 1527 + 638 + 740 = **2905 passed, 0 failures**. **No changes.
Classification: A — ready for manual release confirmation; no tag until
the manual checklist passes.**

### Phase 2 verification gate — PASSED (2026-06-11)

Audit-only: routing proof (shared mounts, legacy `not isinstance` pins),
old-UI absence (no Comics Script/page-manager chrome anywhere in code or
rendered UI), schema/mirroring/regression re-verified; new pin proves no
production module constructs the LEGACY renderers. **740** verification
matrix green + Phase-2 tree runs (incl. broad sweep 1527). No production
changes. **Classification: A.**

### Phase 2 — GN routes through SHARED editors (legacy renderers bypassed) (2026-06-11)

Graphic Novel Manuscript now mounts the **shared `WritingCoreView`** (same
family as Screenplay; GN block grammar already registered; chapter headers
hidden in GN) and Graphic Novel Outline mounts the **shared `PlanView`**
with a built-in GN mode schema (Act → Page → Scene → Panel cards,
`(continued)` spans, add-action bar, Panel double-click → Manuscript
cursor). New `graphic_novel_blocks.panel_at_offset/panel_offset` map the
editor cursor to (page, panel) — Outline deep-links and **Dexter's
"selected Panel"** now resolve from the shared editor's cursor (no widget
coupling; voice GN targets unchanged in behavior). The legacy
`GraphicNovel*View` modules are labelled **LEGACY — NOT ROUTED** and are
unreachable from navigation; standalone Pages stays inert (its route now
shows the shared editor). No data changes; same storage, mirroring and
exports. Tests: routing/marker pins flipped to the shared classes + 6 new
Phase-2 pins (mount families, no page-manager chrome, GN schema cards,
cursor deep-link, voice cursor resolver, cursor mapping round-trip).

### GN block-UX post-fix gate — PASSED (2026-06-11)

Audit-only: old-UI leak scan clean (no "Comics Script"/tree/dropdown in
sources or rendered widgets), shared-paradigm rendering pinned, Screenplay
views pinned untouched, CJK block-entry → Outline snippet pinned. Three
pins (suite → 84); no production changes. Gate matrix 537 green; fix-tree
broad sweep 1527. **Classification: A.**

### Graphic Novel UI bugfix — shared block-based UX for Manuscript + Outline (2026-06-11)

Release-blocking UI mismatch fixed: Graphic Novel now uses the same UX
paradigm as Screenplay/other modes. **Manuscript** = one full-document
block editor over the whole project (ACT section headers, SCENE headers
with inline rename + act-wide page-range chips, act-wide PAGE blocks,
free-typing panel script blocks, "Graphic Novel" mode label + live
word/character count) — the old standalone "Comics Script" single-scene
renderer and its scene dropdown are removed. **Outline** = the block/card
planner (full-width card canvas: Act cards → act-wide Page cards → Scene
groups with `(continued)` → Panel snippet cards; header action bar; click
selects/highlights, double-click deep-links to the Manuscript; inline page
title/notes, scene rename and start-page pin/Auto on the cards) — the old
thin tree + empty detail pane is removed. Canonical Act → Page → Scene →
Panel data, mirroring, voice panel targeting (`current_panel_ref`),
deep-link signatures, standalone-Pages inertness and exports are
unchanged; chapters stay hidden. Tests migrated to the new shape (GN
suites 228 green; voice GN routing keys updated); broad certification
sweep 1527 at baseline.

### FINAL ALPHA RC RE-CERTIFICATION — PASSED (2026-06-11)

The complete Desktop Alpha re-certified end-to-end after the GN refactor,
multi-language system and scope cleanup — **no blockers; zero production
or test changes** (clean run at `044f675`, version 0.9.0-alpha, no tags).
Certified: five modes (incl. GN Act → Page → Scene → Panel with derived
Manuscript and Series Season → Episode → Act → Chapter → Scene), Dexter's
Room as the local voice writing room (review-first, explicit Apply, no
grammar, no cloud/raw-audio), project Writing Language + Dexter language
+ Unicode/CJK/RTL writing and exports, mode lock, isolation, dirty
close-save, startup scope lock (Pages/Plot hidden, voice off, UI
English-only, grammar off, ComfyUI stub), clean requirements. Deferred
items documented and not exposed as complete. Evidence: 1527 + 569 + 359
+ 358 + 254 = **3067 passed, 0 failures**. **Classification: A — ready
for manual release confirmation** (microphone, macOS fullscreen,
language/Unicode UI and optional-export manual checks remain; do not tag
until the manual checklist passes).

### Graphic Novel post-refactor RE-certification — PASSED (2026-06-11)

Combined gate after the scope cleanup: canonical Act → Page → Scene → Panel
data model, Outline shape/editing, Manuscript derivation, mirroring,
standalone-Pages safety, export hygiene and compatibility re-verified —
now together with the language/Dexter dimensions. Eleven permanent pins
added (`tests/test_gn_act_page_structure.py` → 70): the full
CJK/RTL/Indic/Thai/mixed string set through every Panel field (reload +
canonical export), GN project-language coordination (AI context with
CJK/RTL notes, Dexter "Use project language", no Panel mutation,
English-only UI), and Dexter routing a CJK transcript into a Panel
Dialogue field (explicit, append-preserving). **No production code
changed.** Evidence: 376 + 355 + 298 + 1527 = **2556 passed, 0
failures**. **Classification: A** — Final Alpha RC re-certification can
resume.

### Dexter scope-cleanup certification gate — PASSED (2026-06-11)

Audit-only certification of the scope cleanup: Dexter capabilities and
forbidden-label scan, grammar deferral (forced-off load, disabled
placeholder, no startup dependency), English-only UI, writing/Dexter
language and Unicode support intact, blocker policy. Three permanent pins
added (suite → 69): Dexter works with the grammar module unimportable; the
required Writing Language help text; the blocker-policy doc pin. No scope
leaks; **no production code changed**. Evidence: 633 + 429 + 1527 =
**2589 passed, 0 failures**. **Classification: A.** GN post-refactor
re-certification can resume, then Final Alpha RC re-certification.

### Final pre-Alpha scope cleanup — Dexter = voice writing room; grammar & UI localization deferred (2026-06-11)

Scope decision before Alpha RC re-certification: **Dexter's Room is the
dynamic voice writing room** (capture, buffered transcription, transcript
review/manual editing, formatting, routing into Manuscript/Outline/Notes/
PSYKE/GN Panels, preview-first project-language-aware Billy proposals,
explicit Apply, undo) — **not a grammar-correction room**; it has and had
no grammar coupling (now test-pinned, incl. a wording scan). **Grammar
checking and deep text correction are deferred to a later Review/Correction
phase**: the editor's opt-in grammar pass is forced off on load (stored
opt-ins ignored), the Review-menu entry became a disabled *"Grammar Check —
deferred after Alpha"* placeholder, Project Settings shows the deferral
instead of per-language support claims, and grammar was removed from the
Alpha blocker list (backend kept dormant, stdlib-only). **The Alpha UI is
English-only**: the Preferences UI-language selector was removed, the
i18n scaffolding is dormant (`UI_LOCALIZATION_ENABLED = False`; `tr()`
pass-through; no partial Italian ships), and localization is documented as
future work. **Kept in full:** project Writing Language (label + new
required help text), full Whisper list, Dexter language modes, AI
preserve-language context, Unicode/CJK/RTL writing and exports. Blocker
list updated per the scope decision (grammar/UI-translation/transcription-
quality/PDF-glyph/RTL-polish are non-blocking when graceful+documented).
Tests: deferral/scope pins added; UI-language tests rewritten to pin
English-only (suite → 66).

### Multi-language regression gate — PASSED (2026-06-11)

Audit-only certification of the multi-language system: registry fields,
project-language safety (corrupt stored values degrade to auto), Dexter
override precedence, the gate's full CJK/RTL/Indic/Thai string matrix
across scene bodies / Notes / PSYKE / GN panels / Series / search /
exports, Italian Dexter setup labels, and the exports-carry-no-settings
property. Six permanent pins added (`tests/test_language_system.py` → 60);
**no production code changed**. Evidence: 482 language/voice + 423
GN/Series/isolation/export + 1527 broad sweep = **2432 passed, 0
failures**. **Classification: B** (documented grammar/UI/PDF/RTL
limitations stand). Graphic Novel post-refactor re-certification can
resume.

### Multi-language infrastructure (writing / Dexter / grammar / UI)

Four separated language concepts, all stored by stable Whisper codes over a
new central registry (`logosforge/languages.py`: scripts, RTL,
no-word-space metadata, grammar support levels, aliases — single source of
truth re-exported by the voice stack):

- **Project Writing Language** (per project; New Project + Project Settings;
  full 100-language list + Auto; settings-only — never rewrites text; no
  cross-project leaks; global default in Preferences).
- **AI coordination**: `chat_completion` now resolves explicit
  `response_language` → active project language → legacy text detection,
  so every AI surface (assistant, Logos, inline edits, rewrite tools,
  Billy voice bridge) preserves the project language by default with
  RTL/CJK-aware, never-auto-translate instructions.
- **Dexter's Room**: transcription language modes *Use project language*
  (default; follows project switches), *Auto detect*, *explicit code*
  (pre-existing explicit choices inferred and kept); segments record
  `project_language_code` + `dexter_language_mode` (+ existing
  selected/detected/source); invalid values always degrade to Auto;
  codes-only injection-proof pass-through.
- **Grammar**: `check_text(..., language=)` with honest levels — full
  English; basic generic rules for word-spaced scripts; **none** (graceful
  message, zero bogus issues) for CJK/RTL; project language by default,
  per-project override field, editor session override respected; Project
  Settings shows the support note. No external/cloud grammar engine.
- **Unicode/script safety** certified: CJK/RTL/emoji storage + reload,
  UTF-8 Markdown/TXT/JSON/Fountain exports (no needless escaping), search,
  GN structure export; CJK word count shown as ≈ characters; PDF glyph
  limits documented (no bundled fonts).
- **Software UI Language** (global, separate): lightweight catalog
  (`logosforge/i18n.py`), English default + partial Italian; only
  translated locales selectable; Preferences → Language section
  (UI language + default writing language).
- Tests: new `tests/test_language_system.py` (54) + updated Dexter
  language pins; voice matrix 569, modes/gates/grammar 415, broad
  certification sweep **1527** — all green. No new dependencies.

### Post-refactor integrity gate — PASSED (2026-06-11)

A dedicated audit re-certified the canonical Graphic Novel refactor: data
model, Outline shape + full editing matrix (selection/cancelled actions never
mark dirty; confirmed edits do exactly once), Manuscript derivation,
Outline ⇄ Manuscript mirroring (incl. stale Panel-target clearing on scene
switch), standalone-Pages/fullscreen safety, canonical export, compatibility
(legacy `NULL` offsets byte-identical; simulated pre-refactor DB migrates
idempotently) and cross-mode/voice regression. One gap fixed: the GN Outline
now offers **Scene rename** ("Scene title" in the scene/scene-page detail —
PlanView is not mounted in GN mode; empty titles refused). Four gate pins
added (`tests/test_gn_outline_integrity_gate.py` → 17). Evidence: **2511
passed, 0 failures** (GN core 170, GN surfaces/export 272, gates/lock/
autosave/isolation 186, Dexter/voice 230, Series/backup 126, broad sweep
1527). **Classification: A.**

### Graphic Novel — canonical `Act → Page → Scene → Panel` (Manuscript derives)

The Graphic Novel Outline's visible hierarchy is now the canonical
**Project → Act → Page → Scene → Panel** and the Manuscript derives from it:

- **Structure.** An **Act owns its act-wide Pages and its Scenes**; a **Panel
  belongs to exactly one Scene** and sits on **exactly one Page**; a **Scene
  can span several Pages** (its panels distributed across them); **one Page
  can hold Panels from several Scenes**. **Chapters are hidden** in Graphic
  Novel mode (`Scene.chapter` remains a hidden storage label so other modes
  and legacy data are untouched).
- **Smallest safe adapter, no storage migration.** Scene bodies keep the
  scene-local `PAGE n` / `PANEL n` script. The act-wide page numbers are a
  **computed coordinate** from the new module `graphic_novel_structure`
  over ONE new nullable column, `Scene.gn_page_start` (idempotent additive
  `ALTER TABLE`): `NULL` auto-chains the scene after the previous one —
  exactly the legacy layout, so existing projects read identically — and a
  pinned value places the scene's first page onto an earlier scene's page
  (page sharing). Other modes ignore the column entirely.
- **Outline rewritten** (`GraphicNovelOutlineView`): one page-first tree
  `Act → Page → Scene → Panel` with `Scene … (continued)` labels, empty
  scenes kept visible under their Act, toolbar **+ Act / + Scene / + Page /
  + Panel**, panel move/delete, move-panel-to-page with act-wide labels, a
  **"Scene starts on act page"** pin/Auto control, and the five-field Panel
  editor; double-click deep-links into the Manuscript (unchanged signature).
- **Manuscript derives from the Outline**: PAGE headings show **act-wide**
  numbers (re-rendered when another scene's pages shift them), the context
  header shows Act + act-wide page range, the scene dropdown drops the
  chapter, and the empty-state ladder starts with *"Create an Act to begin
  your Graphic Novel."* + **+ Act**. Script-block editing, mirroring, voice
  panel targeting and deep-links keep their local-coordinate APIs.
- **Export** (`export_structure_markdown`; the old
  `gno.export_outline_markdown` delegates): `Act → Page → Scene → Panel` in
  physical page order with explicit Panel → Scene / Panel → Page assignments
  and `continued` markers — each panel's text exactly once, no image data,
  no settings/keys. Standalone Pages stays disabled; ComfyUI stays deferred;
  Panels remain the future anchor for visual production integrations.
- **Tests:** new `tests/test_gn_act_page_structure.py` (59) covering
  coordinates, UI shape, editing, derivation, mirroring, export, migration
  and cross-mode safety; `test_gn_outline.py` / `test_gn_outline_integrity_
  gate.py` / `test_gn_manuscript_script_editor.py` updated to the canonical
  shape. GN + cross-mode + voice regression batches all green.

## [0.9.0-alpha] — post-RC corrections & additions — 2026-06-10

Blocker fixes and structural corrections found by manual Alpha testing, plus a
feature-flagged local voice foundation. Verified by the **final combined Alpha
retest gate** (see `docs/ALPHA_RC_STATUS.md`).

### Final Alpha RC integration gate — PASSED (2026-06-10)

One audit-only integration gate across core, all five modes, the corrected
Graphic Novel + Series architectures, the complete Voice MVP (Phases 1–9),
exports/requirements and privacy. **No blockers found; no production code
changed.** Evidence: authoritative broad certification sweep **1527 passed**
(identical to its historical baseline, single process) + post-sweep voice/
preferences batch **392 passed** + GN/Series/lock/lifecycle/export batch
**392 passed** — **2311 passed, 0 failed**. Manual smoke test (V1–V49 +
P/F items) and maintainer sign-off remain before tagging.
**Classification: A — ready for manual release confirmation.**

### Structural corrections

- **Series — real hierarchy.** The Alpha shortcut (Act = Season, Chapter =
  Episode) is replaced by **Series → Season → Episode → Act → Chapter → Scene**:
  `Season`/`Episode` are stored rows, each Series scene links via a new nullable
  `Scene.episode_id` (NULL elsewhere — other modes unaffected), and the
  Act→Chapter→Scene outline is episode-scoped. The Series Navigator is the
  structural editor (full CRUD + non-destructive, confirmed legacy migration).
  The global Outline/Manuscript/Timeline stay episode-agnostic (documented
  Phase-1 boundary).
- **Graphic Novel — Pages/Panels in the Outline + Manuscript.** The standalone
  left-panel **Pages** route proved fullscreen-hostile (clicking it minimized
  the app in macOS fullscreen) and is **disabled for Alpha** (hidden; inert
  route). Page/Panel management lives in two mirrored surfaces over the shared
  `Scene.content` body: the **GN Outline** (Scenes tab `Act → Chapter → Scene →
  Page → Panel` + a chapter-level Pages cross-reference; full editing,
  assign-panel-to-page) and the **Manuscript**. Model: Chapter owns Pages,
  Scene owns Panels, Panel assigned to a Page, a Scene can span Pages.
- **Graphic Novel — Manuscript is a comics script editor, not an outliner.**
  The GN Manuscript initially shipped as a tree + selected-item detail editor
  (an outliner shape). It is now a true **comics script editor**: the selected
  scene's whole script renders inline as PAGE blocks containing Panel cards
  with all five fields (**Visual / Caption / Dialogue / SFX / Notes**) always
  visible and editable in place (commit on focus-out, focus preserved across
  the app-wide refresh that follows each save), per-page **+ Panel** / **Delete
  Page**, per-panel move/delete (confirmed via fullscreen-safe dialogs), an
  empty-state ladder (Create Scene → Add Page → Add Panel → script), and a flat
  scene dropdown. Structure stays in the GN Outline (double-click opens the
  scene in the Manuscript); both still mirror over the same `Scene.content`
  body. Suite: `tests/test_gn_manuscript_script_editor.py` (66 passed, replaces
  `test_gn_embedded_navigator.py`).
- **Graphic Novel — Manuscript upgraded to a Superscript-style script editor.**
  The per-field card layout still read as a form, so the writing surface is
  now true script blocks: PAGE headings + **one large free-typing block per
  panel** in which the writer types labeled sections (`Visual:` / `Caption:` /
  `Dialogue:` / `SFX:` / `Notes:` — labels optional, unlabeled text is the
  Visual, speaker lines like `NAME: …` stay content; blocks auto-grow so the
  scene scrolls as one document). Blocks parse back into the canonical
  five-field model on commit via `graphic_novel_blocks.parse_panel_text`;
  the body parser/serializer now **preserves line breaks inside fields**
  end-to-end (marker-looking lines are folded, never dropped, so structure
  cannot drift); pages/panels stay auto-numbered; the Outline's Panel
  double-click now **deep-links to the panel's script block**. Empty-state
  copy per spec ("No Graphic Novel scene yet." → "+ Create Scene", scene path
  + "Start the comics script for this scene." → "+ Add Page"). Same shared
  body, mirroring, fullscreen safety and export; no image-generation anything.
  Suite rewritten: 56 tests.
- **Writing-mode lock.** Mode is chosen at creation and **locks once a project
  has meaningful content** (body text, planning data, Timeline/Notes/PSYKE,
  user structure, Season/Episode rows); blocked changes mutate nothing.
  Conversion wizard deferred.

### Fixes / packaging

- **Voice Dictation is a floating window that actually toggles.** The voice
  surface was an embedded bottom strip that, with the feature flag off, could
  be shown but **never hidden again**; it was also too small to review
  transcripts. It is now a **floating, modeless, resizable** Voice Dictation
  window (`VoiceDictationWindow`) parented to the main window — one instance,
  toggled show↔hide from the menu / Ctrl+Shift+V; the Hide button, title-bar
  close and Esc all hide it with the transcript preview preserved; hiding
  while recording stops the session safely; never auto-shown, never
  auto-recording, commit stays manual (auto-commit off by default), no
  parentless top-level windows (the Pages-bug rules). Backends unchanged.
- **General Preferences scrolls on small screens.** The Preferences dialog
  put everything (including Close) in one fixed column, so tall content
  pushed the bottom controls off-screen. Settings content now lives in a
  vertical scroll area with a **sticky Close row outside it**, and the dialog
  clamps its height to ~85% of the available screen. Persistence and
  validation unchanged.

- `requirements.txt` lists the optional export libs (`reportlab`,
  `python-docx`); PDF/DOCX degrade gracefully when absent.
- Fullscreen-safe dialog helper (`ui/safe_dialogs.py`): window-modal,
  top-level-parented confirmations (macOS sheets) used by the GN surfaces.

### Added (feature-flagged, off by default)

- **Voice dependency / language / naming update (post-gate).** (1)
  `requirements.txt` now installs the voice modules the implementation
  actually uses — `faster-whisper` + `sounddevice` (loose-minimum style,
  matching the reportlab/python-docx precedent; PortAudio note for Linux;
  whisper.cpp documented as a local executable, never a pip package; the
  app still starts and degrades gracefully without models). (2) The
  user-facing voice workspace is renamed **Dexter's Room** (menu action
  "Dexter's Room" with "Enter Dexter's Room" tooltip, window title, shell
  header, privacy note "Dexter's Room uses local transcription. Audio is
  processed on this device. …"); **Billy stays Billy, Logos stays Logos**;
  internal `VoiceRoom*` module/class names are deliberately retained
  (low-risk policy) and documented as powering the Dexter's Room UI; no
  "Dester" typo exists. (3) The language selector now offers the **full
  OpenAI Whisper list** (Auto detect + 100 languages, alphabetical, shown
  as "English (en)", stored by code) with internal aliases
  (Mandarin→zh, Cantonese→yue, Castilian→es, Valencian→ca, Flemish→nl,
  Haitian→ht, Burmese→my, Moldovan→ro, Panjabi→pa, Pushto→ps,
  Sinhalese→si, …); invalid saved values fall back to Auto detect with a
  visible message; auto omits the language for faster-whisper (None) and
  whisper.cpp (no `-l`), chosen codes (incl. yue/haw/jw) pass through; and
  transcript segments now record `selected_language_code` /
  `detected_language_code` / `language_source`
  (auto | user_selected | backend_detected).
  `tests/test_voice_language_dexter.py` (15 passed).
- **Voice Phase 9 — end-to-end Alpha hardening gate (audit + certification;
  no production code changed).** The complete voice stack (Phases 1–8)
  passed the cross-cutting gate `tests/test_voice_alpha_gate.py` (9): a
  one-pass dictate→correct→commit→undo pipeline; **uncommitted voice
  history never locks the writing mode while committed voice text does**;
  app close while recording stops the session safely; 30-segment sessions
  stay ordered with audio dropped on discard/clear; mock-based latency
  guardrails (backend/mic checks and a short segment each < 1 s; real-model
  latency varies by hardware); exports and the diagnostics summary contain
  no transcript history, glossary internals, audio or secrets; every voice
  module imports cleanly without the optional dependencies; exactly one
  backend per resolved mode. Privacy audit: `lan_server.py` is the only
  network-touching voice module (private hosts enforced); zero logging
  statements in the voice stack. Full matrix: voice 427 + writing-mode/
  structural regression 449 — **0 failures**. Manual QA checklist extended
  to V49. **Classification: A — Voice MVP is Alpha-safe.**
- **Voice Phase 8 — local Whisper setup, diagnostics, backend profiles,
  guardrails.** A parented modeless **Voice Setup** panel
  (`ui/voice_setup_dialog.py`, opened from the voice panel) over a new
  diagnostics layer (`voice/setup.py`): enable Voice Mode; pick **one**
  local backend — faster-whisper / **whisper.cpp** (new local
  `WhisperCppTranscriber` shelling out to the user-set binary on a temp WAV
  that is always deleted) / Local LAN / Mock-test — with a validated status
  chip (`not_configured / ready / missing_dependency / missing_executable /
  missing_model / error / disabled`); model & executable paths with Browse;
  language; **performance profiles** (Fast draft / Balanced / Accurate /
  Custom → CPU-safe silence/segment/beam values, no model download, no GPU
  required); and safe **diagnostics** — microphone test, backend test (with
  a whisper.cpp `--help` probe), **file-based local test transcription**
  (shown in the panel only — never committed, never sent to Billy/AI, audio
  never retained) and a **copyable diagnostics summary** that excludes API
  keys, provider secrets, transcript history and raw paths. The **Voice Room
  gates Start** on a ready backend ("Local Whisper is not configured. Open
  Voice Setup to enable Voice Mode."); dictation still works with Whisper
  alone. Nothing is installed or downloaded; invalid paths degrade to clear
  messages, never crashes. New settings: `voice_performance_profile`,
  `voice_beam_size` (additive, safe defaults). `tests/test_voice_setup.py`
  (28 passed).
- **Voice Phase 7 — Project Voice Glossary + local correction layer.** A
  project-scoped `VoiceGlossaryTerm` table (additive schema; existing DBs
  gain it automatically) stores canonical spellings, spoken forms, known
  Whisper misrecognitions, category/source/enabled — no audio, no secrets,
  no cross-project leakage. A local correction engine
  (`logosforge/voice/glossary.py`) generates **review-first suggestions**
  after each final transcript (exact misrecognitions → spoken forms →
  canonical capitalization → spoken punctuation phrases → cautious fuzzy
  matches, off by default; whole-word matching, drift-guarded apply).
  Panel UI: per-segment checkable suggestion list with Apply (transcript
  text only; original kept; status `corrected`; commits still via the
  router) / Reject, **Learn correction…** (confirmed, project-scoped
  pairs), and a parented modeless **Glossary manager** with confirmed
  read-only **Import project terms** from PSYKE/characters/scene titles
  (sources never mutated, no duplicates). Corrected text is what Intent
  mode and Billy receive. Settings (review-first defaults):
  `enable_voice_glossary` on, `voice_spoken_punctuation` on, fuzzy and both
  auto-apply rules **off**, `voice_learn_corrections="ask"`. Project
  safety: corrections from another project are blocked with a clear
  message; the dialog follows project switches.
  `tests/test_voice_glossary.py` (28 passed).
- **Voice Phase 6 — Live Writer Room Alpha Shell (Voice Room).** One local,
  buffered, review-first session workflow unifying the whole voice stack:
  an explicit crash-proof **session state machine** (idle → checking
  backend → ready → listening → transcribing → transcript ready → choosing
  target / sending to Billy → proposal ready → applying → applied; error/
  stopped reachable from anywhere; invalid transitions refused), a **Voice
  Room header** with state + safe context summary (project, mode, section,
  selected Panel/field, selection — no keys, no audio, no other projects),
  a session-scoped **proposal queue** for Intent previews and Billy
  proposals (draft/ready/applied/cancelled/stale/failed; stale —
  project switch, deleted target, drifted selection — can never apply;
  double-click re-activates a ready item; applied items keep the operation
  id for the shared Undo), four **explicit workflow modes** (Dictation
  default / Intent / Ask Billy / Edit with Billy — never inferred from the
  transcript; Billy modes preset the bridge operation), and a **Pause**
  control that keeps session, history and queue. All inside the existing
  safe floating panel; dictation still works with Whisper alone; nothing
  mutates without confirmation. `logosforge/voice/room.py` +
  `tests/test_voice_room.py` (26 passed).
- **Voice Phase 5 — Billy Voice Bridge (voice → Billy proposal → confirmed
  apply).** Selected transcript segments can be sent to **Billy** (the
  Assistant chat agent) as a question or editing instruction. Billy receives
  **text only** — transcript + a minimal safe context (project title,
  writing mode, selection snippet, selected GN panel fields; never audio,
  never API keys/provider settings, never other-project data) — via the
  app's existing provider configuration (no provider ⇒ all Billy actions
  disabled with "Billy is not configured. Voice-to-Billy actions are
  unavailable."). Fixed operation allowlist: Ask (chat-only), Rewrite
  selected text, Continue from cursor, Summarize to Note, PSYKE draft
  (user-chosen type, default Other), GN Panel-field update (selected panel,
  chosen field, replace with diff; Outline/Manuscript mirror), Outline item
  still listed disabled. Every proposal is preview-first with explicit
  Apply (routed through the existing Intent/Commit routers → live
  re-validation + shared Undo) and Cancel (zero mutation); stale proposals
  block with regenerate messages; project switch invalidates them.
  Dangerous spoken "commands" ("delete the project", "run this command",
  "send to ComfyUI", …) never execute and never reach the provider —
  chat-only: "I can't perform that action from voice in Alpha." Transcript
  history tracks sent_to_billy / proposal id / applied-cancelled (no
  secrets, no audio). `logosforge/voice/billy_bridge.py` +
  `tests/test_voice_billy_bridge.py` (35 passed).
- **Voice Phase 4 — Voice Intent Router (preview-first confirmed text
  operations).** An explicit **Dictation / Intent** mode selector in the
  voice panel (Dictation stays the default; Intent is opt-in — command mode
  is never inferred). In Intent mode a transcript is an *instruction* from a
  fixed allowlist: rule-based cleanup (whitespace/capitalization/spoken
  punctuation; no AI, never fabricates; transcript-only apply), insert
  cleaned transcript via the chosen commit target, **AI rewrite of the
  editor selection** and **AI summarize-to-Note** (existing provider
  settings only — `build_active_provider` + the shared chat completion;
  text-only, audio never sent; disabled with "AI text operation unavailable.
  Configure an AI provider or use rule-based cleanup." when unconfigured),
  PSYKE draft entry (user-chosen type, default Other) and Graphic Novel
  Panel-field send (chosen field; Outline/Manuscript mirror). Every intent
  builds a before/after (+ diff) or entity preview and applies ONLY on
  explicit confirm; Cancel mutates nothing; apply re-validates project id,
  target existence and the expected before-text ("Target changed since
  preview. Regenerate preview before applying."); applied intents emit the
  Phase 3 operation records so Undo-last-commit covers them. No shell or
  system commands, no voice-command execution, no auto-apply.
  `logosforge/voice/intent_router.py` + `tests/test_voice_intents.py`
  (37 passed).
- **Voice Phase 3 — transcript history, correction, undo, retry.** A local,
  session-only history of dictated segments in the voice panel: edit before
  commit (original kept + restorable; empty segments never commit), select
  and commit multiple segments together (visible order, edited text, through
  the Commit Router only), merge adjacent / split at the cursor, retry
  transcription on the segment's locally-held audio (in-memory only, never
  on disk, dropped on discard/clear), discard / clear uncommitted, and a
  single-level **Undo last voice commit** that is target-scoped and refuses
  to touch anything else (editor document-revision guard; GN field previous
  value; created Note/PSYKE deleted only if unchanged; otherwise disabled
  with the reason). Per-segment project capture freezes history on project
  switch and blocks cross-project commits. Nothing persists across restarts;
  no telemetry; no cloud. `logosforge/voice/history.py` + undo layer in
  `commit_router.py`; `tests/test_voice_history.py` (37 passed).
- **Voice Phase 2 — mode-aware commit targets (Voice Commit Router).** After
  reviewing the transcript the user picks an explicit *Send to* target:
  cursor insert; **New Note**; **PSYKE draft entry** (type chosen by the
  user — Character/Place/Object/Lore/Theme/**Other** (default), never
  auto-classified); **Screenplay** Action / Dialogue and **Stage** Direction /
  Dialogue (character picked manually from existing characters — never
  guessed); **Graphic Novel** Panel → Visual/Caption/Dialogue/SFX/Notes for
  the selected Panel (appends; disabled with "Select a Panel first."
  otherwise). Listing/preview never mutates; commits re-validate the live
  target and are blocked if the project changed since transcription; the
  project is marked dirty only after a successful commit; transcript
  segments carry explicit-commit metadata (no audio stored). Deferred with
  visible reasons: Outline / Series-episode draft items and
  Append-to-Manuscript. `logosforge/voice/commit_router.py` +
  `tests/test_voice_commit_router.py` (41 passed).

- **Local voice-to-script MVP** (`enable_voice_mode`; backend mode defaults to
  *Disabled*): local mic capture, buffered silence-segmented dictation,
  transcript preview, **manual plain-text commit** at the editor cursor.
  Backends: **Local PC** (faster-whisper, optional/lazy, local model path, no
  auto-downloads) and **Local LAN Server** (segments go only to a Whisper
  server on the trusted LAN — private/loopback URLs enforced, public/ngrok/
  tunnel URLs blocked, redirects refused). No cloud speech, no OpenAI Realtime,
  no voice commands, no auto-classification.
- **LAN Whisper companion** (`scripts/local_whisper_server.py`): optional,
  manually-started stdlib server (faster-whisper; `/health`,
  `/v1/audio/transcriptions`, `/inference`); binds 127.0.0.1 by default, LAN
  bind is explicit with a warning; optional Bearer token (never logged).
  External whisper.cpp servers documented (`docs/LOCAL_LAN_WHISPER.md`).

## [0.9.0-alpha] — Alpha Release Candidate (multi-mode) — 2026-06-08

Release-candidate milestone for the five-mode writing system on the **universal
Manuscript**. **Feature-frozen**; this milestone focused on completing the
writing modes, then auditing and stabilizing the whole system. **No new product
features and no production-code changes were made during RC packaging.**

### Major additions (writing modes on the universal Manuscript)

- **Screenplay** (Phases 1–10), **Graphic Novel** (Phases 1–8), **Stage Script**
  (Phases 1–8), and **Series** (Phases 1–8), each adding — over a Scene's flat
  body — a typed block adapter, a planning pipeline (preview → confirmed apply),
  deterministic intelligence checks, Counterpart/Reflection, controlled rewrite
  (preview/diff/confirmed apply), cross-unit continuity, and a Review Dashboard.
- **Series** interprets the canonical Act → Chapter → Scene as Season/Arc →
  Episode → Scene (display only); plans are settings-backed (no Season/Episode
  storage hierarchy).
- All mode AI surfaces are **mode-gated** and **propose-then-confirm**; no silent
  overwrites; deterministic checks never call the provider.

### Stabilization / audits

- Per-mode integrity audits (Screenplay, Graphic Novel, Stage Script, Series) and
  a final **global multi-mode integrity audit / Alpha Release Gate** — all
  classification **A**. See `docs/ALPHA_RELEASE_GATE_AUDIT.md` and the per-mode
  `docs/*_MODE_INTEGRITY_AUDIT.md`.
- Fixed two stale `test_logos_integration.py` cases that referenced the removed
  `_action_buttons` toolbar API (test-harness only; the toolbar is the
  `_action_combo` dropdown) — the suite is now fully green.

### Tests

- Focused gate `tests/test_alpha_release_gate.py` — **35 passed**.
- Broad certification sweep — **1527 passed, 0 failures** (see
  `docs/ALPHA_TEST_COMMANDS.md`).

### Known non-blocking limitations

- Mode checks are conservative/rule-based (no NLP); dashboards refresh on open +
  manual button; persistent serialized-story relation links are reported but not
  yet persisted; optional DOCX/PDF export degrades gracefully when libs are
  absent. ComfyUI/image generation, Canvas Plot, production scheduling,
  writers-room/showrunner automation, and a real Season/Episode storage hierarchy
  remain **deferred**. See `docs/KNOWN_LIMITATIONS_ALPHA.md`.

## [0.9.0-alpha] — Private Alpha

First closed alpha: a local-first narrative operating system for structured
writing. **Feature-frozen**; this milestone focused on stability, data safety,
UI hardening, and documentation. Back up your work — see
`docs/BackupRestore.md`.

### Major implemented systems

- **Writing Modes** — Novel / Screenplay / Graphic Novel / Stage Script / Series
  as a single project-level source of truth that every section and the AI adapt
  to.
- **Manuscript** — continuous scene editor with focus mode, format-aware blocks,
  font/size/grammar controls, and debounced atomic autosave.
- **Structure** — Outline (AI-generated, confirmed), Multi-Plot, Timeline,
  Story Grid, act/beat/tag analysis.
- **PSYKE** story bible — characters/places/objects/lore/themes with relations,
  progressions and a fast console search.
- **AI Assistant** — engine-aware critique, inline editing, Counterpart mode,
  Quantum outliner, capped/toggleable context, language-aware responses, and
  safe propose-then-confirm actions.
- **Logos** — an inline contextual AI layer (left-panel ON/OFF toggle) with
  diagnostics, narrative health, proactive suggestions and a strategy router.
- **Intelligence services** — Project Intelligence + Decision Radar, Narrative
  Knowledge Graph, Semantic Continuity, Guided Workflows, Adaptive Rewrite
  Sandbox, Controlled Apply, Revision Intelligence (services + Logos/Assistant
  surfaces; dedicated UI deferred to beta).
- **Connector** — local app-control bridge (write actions off by default).
- **Export / Import** — Markdown, TXT, Fountain (screenplay), FDX, HTML, JSON,
  CSV, plus optional PDF/DOCX; story-elements / PSYKE / full-project exports;
  non-destructive import.
- **Autosave / Versioning / Backup-Restore** — atomic project writes, automatic
  + manual per-project snapshots, pre-restore safety snapshot.
- **HTTP API** — a FastAPI DTO layer over the core (desktop/localhost in alpha).

### Alpha stabilization (closing steps)

- **Project lifecycle** — writing-mode-dependent sidebar nav (Graphic-Novel
  Pages) now recomputes on project switch; no stale section state.
- **Refresh propagation** — section views that lacked a `refresh()` (Projects,
  Acts/Beats/Tags) now update in place; no recursion on `project_data_changed`.
- **Writing Modes** — Assistant mode strip re-points (and drops stale override)
  on project switch; mode read fresh everywhere.
- **Editor stability** — refresh flushes pending keystrokes and restores focus +
  cursor; no grey-out / lost typing on Assistant/Logos apply.
- **UI hardening** — removed Qt-unsupported QSS properties (no "Unknown property"
  warnings); raised the Outline-confirm modal minimum; 13-inch responsiveness
  verified (Assistant auto-hide, fitting dialogs).
- **AI provider** — single `build_active_provider` resolver; persisted settings;
  configurable local-aware timeouts with readable errors; Anthropic switch no
  longer flashes a stray window; custom model names allowed; **API keys never
  logged or exported**.
- **Export** — manuscript export now reports failures as readable dialogs
  (incl. a hint when `reportlab`/`python-docx` is missing).
- **Versioning/backup** — surfaced snapshot-load errors; verified per-project
  isolation and non-destructive restore.
- **Version constant** — `logosforge.__version__ = "0.9.0-alpha"`.

### Documentation

Added the Alpha doc set: README alpha note, User Guide, AI Setup,
Troubleshooting, Alpha Scope/Freeze, Known Limitations, Test Plan, Data Safety,
Backup & Restore, Autosave & Versioning, Export/Interchange (Export Matrix),
Release Checklist, Final Report, and a grouped `docs/index.md`.

### Known limitations

- PDF/DOCX export needs optional libraries; FDX/HTML and the API LAN/remote modes
  are experimental.
- Plot/Timeline are scene-derived; grammar is rule-based.
- Knowledge-Graph / Continuity / Decision-Radar / Workflow services have no UI
  panel yet.
- Single-user, local-only (no cloud sync/collaboration); restore creates a new
  project; API keys are stored in plaintext in the local settings file (never
  exported). See `docs/KNOWN_LIMITATIONS_ALPHA.md`.

### Tests

~6008 tests (Qt offscreen). Safety-critical subset verified green
(214 passed / 0 skipped). The final-gate full run was 6005 passed / 2 failed /
1 skipped; one failure was a UI-hardening regression (Outline-confirm dialog
minimum) now **fixed**, the other is a full-suite-ordering flake that passes in
isolation. See `docs/ALPHA_FINAL_REPORT.md`.
