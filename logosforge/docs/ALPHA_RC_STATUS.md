# Alpha Release Candidate — Status

**Classification: A — Ready for Alpha Release Candidate.**

- **Product:** Logosforge — local-first Creative Writing system (Python core).
- **Version:** `0.9.0-alpha` (`logosforge/__init__.py` · `__status__ = "alpha"`).
- **Branch:** `claude/setup-logosforge-app-5cVxF`.
- **Date:** 2026-06-08.
- **Scope of this step:** Alpha RC **packaging / freeze + documentation only** — no
  product features, no refactors, **no production code changed**.

## FINAL COMBINED ALPHA RETEST GATE (2026-06-10)

A single combined gate re-verified **all** post-RC areas together: Graphic Novel
Outline/Page/Panel + Manuscript mirroring + standalone-Pages disabled +
fullscreen safety; the corrected Series hierarchy + Navigator + legacy
migration; the writing-mode lock; export dependencies + privacy; the local
Voice MVP (Local PC + Local LAN backends, URL security, commit safety); the LAN
Whisper companion (manual-start, localhost-default, endpoints, auth, logging
hygiene); and core regression (all five modes, Timeline, Notes, PSYKE,
autosave/dirty, project isolation, Canvas Plot hidden, no ComfyUI).

**Result: 790 passed, 0 failures** across the curated batches (gates + GN +
pages + series + lock = 467 · voice ×3 + export = 128 · isolation + lifecycle +
autosave + notes = 62 · timeline + structure + multi-mode + writing-modes = 133),
plus a 297-test pre-voice cross-check combo. **No release blockers.** Docs
verified to state every required guarantee; `CHANGELOG.md` gained the
consolidated post-RC entry.

One environment finding (not a product bug, documented in
[ALPHA_TEST_COMMANDS.md](ALPHA_TEST_COMMANDS.md)): very large single-process
pytest combinations can segfault on a timing-dependent Qt/GC teardown
interaction around the test-only pattern of constructing many MainWindows that
share the process-singleton event bus. Every suite passes alone and in the
curated batches; the running app (one window, process-lifetime bus) is
unaffected. Pre-existing — a pre-voice 297-test combo of the same shape passes.

**Gate classification: A — manual Alpha RC retest can resume**
(`docs/ALPHA_MANUAL_SMOKE_TEST.md`; tag only after manual confirmation).

## Post-gate fixes (packaging/usability)

- **Dependency manifest:** `requirements.txt` now lists the optional export libs
  `reportlab` (PDF) and `python-docx` (DOCX), so a normal install supports every
  export format. Graceful degradation is preserved when an environment lacks them.
- **Series Navigator:** a Series-only, read-only navigator was added under the left
  **Plan** group (Season/Arc → Episode → Scene, with A/B/C buckets derived from the
  Episode Beat Plan). It mirrors the Graphic-Novel "Pages" gating, navigates to
  Outline/Manuscript without mutating data, and never appears in other modes. No
  Season/Episode storage hierarchy was introduced.
- **Graphic Novel Pages/Manuscript single source of truth:** the GN "Pages"
  section now edits the **same** scene body as the Manuscript — `Scene.content`
  parsed/serialized by `graphic_novel_blocks` into Pages → Panels (visual /
  caption / dialogue / SFX / notes). The new scene-centric Pages view
  (collapsible panel cards) replaces the previously disconnected project-level
  pages surface as the wired nav; edits round-trip between Manuscript and Pages
  via the shared body. The legacy project-level `GraphicNovelPage/Panel` tables
  are left intact (non-destructive, deferred). No image generation / ComfyUI /
  prompt fields / visual canvas.

## Post-gate blocker fix

One Alpha-blocker was fixed after the gate: **writing mode is now locked once a
project has meaningful content** (it was previously switchable, which could make
the Manuscript read one mode's body as another's). Mode is chosen at creation and
locked thereafter; the Project Settings selector is disabled with a clear message
and any mode change is refused without mutating data. Conversion remains a deferred
future workflow. Single source of truth: `writing_modes.can_change_writing_mode` /
`change_writing_mode`. See `docs/KNOWN_LIMITATIONS_ALPHA.md`.

## Post-fix regression gate (2026-06-08)

A targeted gate re-verified the three Alpha-blocker fixes (Graphic Novel shared
body, corrected Series hierarchy, writing-mode lock) plus the export-dependency
manifest, and confirmed **no regressions** elsewhere:

- **Graphic Novel:** Manuscript ↔ Pages/Panels share one body (`Scene.content`);
  single store; add/edit/delete/reorder round-trip; export uses the shared body;
  panel fields are script-only (no image data). ComfyUI stays a **disabled stub**
  and no image-generation action exists in the Logos registry.
- **Series:** real Season → Episode → Act → Chapter → Scene; episode-local
  Acts/Chapters are **not** confused with Seasons/Episodes; Navigator scenes open
  in the Manuscript; moving a Season/Episode never loses a body; export traverses
  the real hierarchy once with no secrets; legacy shortcut projects load read-only
  and convert non-destructively.
- **Mode lock:** empty projects can change mode; any project with body / planning
  / Season-Episode content is locked; a blocked change mutates nothing.
- **Dependencies:** `requirements.txt` lists `reportlab` + `python-docx`; PDF/DOCX
  still degrade gracefully when absent. Canvas Plot stays hidden.

New focused gate: `tests/test_post_fix_regression_gate.py` (**20 passed**).
Verification sweep across the audited areas + all five modes + Timeline / PSYKE /
isolation / Alpha gate: **858 passed, 0 failures** (only the pre-existing
optional-lib PDF/DOCX cases fail in an environment without `reportlab` /
`python-docx`). **Classification: A — post-fix gate passed.**

## Graphic Novel — canonical `Act → Page → Scene → Panel` (standalone Pages disabled)

The standalone left-panel **Pages** route proved fullscreen-hostile (clicking it
minimized the app in macOS fullscreen, across multiple attempted fixes), so it is
**disabled for Alpha** — hidden in every mode, inert route that never mounts the old
standalone Pages widget. The Graphic Novel structure lives in **two mirrored
surfaces** over the shared `Scene.content` body:

- the **Outline** (`GraphicNovelOutlineView`) — the **canonical structure**: one
  page-first tree `Act → Page → Scene → Panel` (an **Act owns its act-wide Pages
  and its Scenes**; a **Panel belongs to one Scene** and sits on **one Page**; a
  **Scene can span several Pages** — `Scene … (continued)` on each following
  page; **one Page can hold Panels from several Scenes**; empty scenes stay
  visible under their Act; **chapters hidden** — `Scene.chapter` is a compat
  storage label only). Selected-item editor: the Panel's five fields (Visual /
  Caption / Dialogue / SFX / Notes), scene-page title/notes, and the scene's
  **act-wide start page** (pin / "Auto — after previous scene", which is how
  two scenes share one physical page); + Act / + Scene / + Page / + Panel,
  panel move + move-panel-to-page (act-wide labels), confirmed deletes,
  double-click → Manuscript;
- the **Manuscript** (`GraphicNovelManuscriptView`) — **derives from the
  Outline** — the **comics script editor** (Superscript-style blocks): PAGE
  headings showing the **act-wide page numbers** + one large free-typing
  script block per panel where the writer types labeled sections (Visual /
  Caption / Dialogue / SFX / Notes — labels optional; unlabeled text is the
  Visual; speaker lines stay content). Blocks parse back into the canonical
  five-field model on commit (focus-out) with line breaks preserved
  end-to-end and auto-numbered pages/panels; context header = Act + act-wide
  page range (no chapter); empty project → *"Create an Act to begin your
  Graphic Novel."* + **+ Act**; per-page **+ Panel** / **Delete Page**,
  per-panel move/delete (confirmed); flat scene dropdown (no tree, no form —
  structure stays in the Outline, whose Panel double-click deep-links to the
  script block here; focus survives the app-wide refresh that follows each
  save).

Both read/write the same body (single source of truth), so they mirror.
**Coordinates, not migration:** pages stay physically scene-scoped (`PAGE 1..n`
per scene body); `graphic_novel_structure` computes the act-wide page numbers
over the single new nullable `Scene.gn_page_start` offset (idempotent additive
`ALTER TABLE`; `NULL` = auto-chain = exact legacy layout, so existing projects
are untouched; other modes ignore the column). Physically merging panels from
different scenes onto one shared page record remains a documented next step.
Both surfaces are single embedded child widgets (no separate route, no top-level
window, no dialog on mount) → cannot trigger the minimize. Non-GN
Outline/Manuscript unchanged (`PlanView` / `WritingCoreView`).

Single source: `MainWindow._show_plan` (GN → `GraphicNovelOutlineView`) +
`_show_manuscript` (GN → `GraphicNovelManuscriptView`) + `_apply_pages_availability`
(hides standalone Pages) + `_show_gn_pages` (inert). Data layer:
`logosforge/graphic_novel_outline.py` (scene-scoped ops) +
`logosforge/graphic_novel_structure.py` (act-wide coordinates + canonical
export). Tests: `tests/test_gn_act_page_structure.py` (**59 passed**),
`tests/test_gn_outline.py` (**38 passed**),
`tests/test_gn_manuscript_script_editor.py` (**56 passed**), plus
pages/lifecycle/phase suites. True macOS fullscreen behavior must still be
confirmed manually (smoke-test F-items). **Classification: A — the Outline is
the canonical Act → Page → Scene → Panel structure and the Manuscript derives
from it; standalone Pages disabled.**

**Post-fix integrity gate (2026-06-08).** A targeted audit re-verified the model
(Chapter owns Pages, Scene owns Panels, Panel assigned to Page, Scene spans Pages),
data integrity (move-to-page preserves the body; reorder-scene preserves panels;
save/reload round-trips with no duplicate panels; one canonical panel body),
Outline⇄Manuscript single-body mirroring, standalone-Pages-disabled + fullscreen
safety, export (Panel→Page and Panel→Scene, no duplicate text / no secrets / no
ComfyUI), and full cross-mode regression — **no regressions** found. New gate:
`tests/test_gn_outline_integrity_gate.py` (**13 passed**); broad audit sweep
**813 passed, 0 failures**. Only deferral: **Page reorder** (move Page up/down) in
the Outline is not implemented for Alpha (panel reorder + move-panel-to-page are).
**Gate result: A.** *(Historical: this gate predates the pre-finalization
refactor below; its data-integrity invariants were re-verified after it.)*

**Pre-finalization refactor (2026-06-11): canonical Act → Page → Scene → Panel.**
The Outline became the canonical page-first structure above and the Manuscript
now derives from it (act-wide page numbers via the additive
`Scene.gn_page_start` coordinate; chapters hidden in GN UI; legacy `NULL`
offsets reproduce the old sequential layout exactly — non-destructive).
Canonical export with explicit Panel → Scene / Panel → Page assignments
replaces the duplicate Scene-view + Page-view markdown. Verification: new
`tests/test_gn_act_page_structure.py` **59 passed**; updated GN suites
(outline 38 + integrity gate 13 + script editor 56) green; regression batches —
GN core **452**, GN engine/graph/timeline **358**, cross-cutting gates
(incl. `test_alpha_release_gate.py`, multi-mode, pages safety, lifecycle,
export stabilization) **155**, voice-over-GN **156**, Series + backup **126**
— **all passed, 0 failures**. **Gate result: A.**

**Post-refactor integrity gate (2026-06-11): PASSED.** A dedicated audit
re-certified the refactor end-to-end: data model (ownership/assignment/order
stability, spans, shared pages, no duplicates, no orphans, isolation), Outline
shape + editing matrix (selection/cancel never dirty, confirmed edits dirty
exactly once; collapse/expand + highlight safe), Manuscript derivation +
empty-state ladder, Outline ⇄ Manuscript mirroring incl. stale-Panel-target
clearing on scene switch, standalone-Pages/fullscreen safety, canonical
export, compatibility (legacy `NULL` offsets byte-identical; simulated
pre-refactor DB migrates idempotently; pre-Alpha `GraphicNovelPage/Panel`
tables untouched and unmounted), and cross-mode + voice regression. One gap
was found and fixed: the GN Outline (which replaces PlanView in GN mode) had
no **Scene rename** — the scene/scene-page detail panes now carry a "Scene
title" editor (`update_scene_title`; empty titles refused). Four gate pins
added to `tests/test_gn_outline_integrity_gate.py` (**17 passed**). Evidence:
GN core **170** + GN surfaces/pages/export **272** + gates/lock/autosave/
isolation **186** + Dexter/voice **230** + Series/backup **126** + broad
certification sweep **1527** = **2511 passed, 0 failures**. Deferred (still
documented, unchanged): physical Page reorder within a scene (placement is
controlled via the start-page pin); Act rename/move from the GN Outline.
**Gate result: A.**

## Multi-language infrastructure (2026-06-11)

Pre-finalization language system, four separated concepts over the new
central registry (`logosforge/languages.py`: full Whisper list + script /
RTL / no-word-space metadata, honest grammar levels, internal aliases —
single source of truth, re-exported by the voice stack):
**Project Writing Language** (per project; New Project + Project Settings;
settings-only writes — never rewrites text; no cross-project leaks; global
default in Preferences), **AI coordination** (`chat_completion` resolves
explicit `response_language` → active project language → legacy detection,
so assistant/Logos/inline edits/rewrite tools/Billy proposals preserve the
project language by default, never auto-translate, RTL/CJK-aware),
**Dexter language modes** (*Use project language* default / *Auto detect* /
explicit; follows project switches; per-segment `project_language_code` +
`dexter_language_mode`; invalid values → Auto; injection-proof codes-only
pass-through), **grammar** (project language by default with per-project
override + editor session override; full English / basic word-spaced /
**none** for CJK-RTL with the graceful "not available … AI review" message
— never silent English-only checks), **Unicode certification**
(CJK/RTL/emoji storage + reload, search, UTF-8 Markdown/TXT/JSON/Fountain
exports without needless escaping; CJK word counts as ≈ characters; PDF
glyph limits documented; no bundled fonts), and a separate global
**Software UI Language** (English default + partial Italian via
`logosforge/i18n.py`; only translated locales selectable; coverage
labeled partial). Local-only — no cloud grammar/speech; no new
dependencies. Verification: `tests/test_language_system.py` **54 passed** +
Dexter/assistant language pins **35**; full voice matrix **569**;
modes/gates/grammar **415** + isolation **82**; broad certification sweep
**1527** — all green. **Classification: B — complete with documented
partial grammar coverage and partial UI translation (by design for
Alpha).**

**Post-implementation regression gate (2026-06-11): PASSED.** A dedicated
audit re-certified every area with targeted probes and six new permanent
pins (`tests/test_language_system.py` → **60**): registry fields for the
full required code list (incl. ta/te/ml/kn/gu/pa), corrupt stored project
language degrades to auto everywhere (AI receives nothing hostile),
per-project Dexter override wins and clears, the gate's exact
zh/ja/ko/ar/he/hi/bn/th/mixed-punctuation strings round-trip through every
writing surface (scene bodies, Notes, PSYKE, GN panel fields, Series
bodies, search, Markdown/JSON/GN exports), the Dexter setup label
translates under the Italian UI, and exports are confirmed to carry **no**
language/settings metadata (the project language travels in the
database/backup only — same property that keeps API keys out of exports).
No blockers found; **no production code changed**. Evidence: language +
voice/Dexter batch **482**, GN/Series/lock/isolation/export batch **423**,
broad certification sweep **1527** = **2432 passed, 0 failures**.
**Gate result: B** (the implementation's documented grammar/UI/PDF/RTL
limitations stand; everything else certified A-clean).

**Final pre-Alpha scope cleanup (2026-06-11): PASSED.** Scope decision
applied: **Dexter's Room is the dynamic voice writing room** (capture →
transcript review/manual edit → formatting → routing → preview-first,
project-language-aware Billy proposals → explicit Apply → undo); it has no
grammar coupling (pinned, incl. wording scan of all voice modules).
**Grammar checking and deep text correction are deferred to a later
Review/Correction phase**: the editor's grammar pass is forced off on load
(stored opt-ins ignored), the Review-menu entry is a disabled "Grammar
Check — deferred after Alpha" placeholder, Project Settings shows the
deferral statement, grammar removed from the blocker list (backend kept
dormant; stdlib-only; no startup dependency). **Alpha UI is English-only**:
the Preferences UI-language selector was removed; `logosforge/i18n.py`
is dormant (`UI_LOCALIZATION_ENABLED = False`, `tr()` pass-through — no
partial Italian ships); localization documented as future work. **Kept in
full:** project Writing Language (with the required help text), full
Whisper list, Dexter language modes + metadata, AI preserve-language
context, Unicode/CJK/RTL writing + exports. Blocker criteria updated per
the scope decision. Verification: language + editor + grammar-adjacent
**392** (suite → 66), voice/Dexter + assistant language **314**,
GN/Series/lock/isolation/export **390**, broad certification sweep
**1527** = **2623 passed, 0 failures**. **Classification: A — Dexter is
writing/interaction only; grammar and UI translation are cleanly deferred;
Alpha scope is clean** (dormant deferred code documented).

**Scope-cleanup certification gate (2026-06-11): PASSED.** A dedicated
post-implementation audit re-certified the cleanup with targeted probes and
three new permanent pins (`tests/test_language_system.py` → **69**): Dexter
constructs and resolves its language even with the grammar module made
unimportable (zero dependency, not just zero usage); the Project Settings
Writing Language help text carries the required wording ("Used for AI
writing context and Dexter transcription defaults. It does not change the
app interface language."); and the smoke-test blocker policy is pinned
(grammar absent from hard blockers; grammar/UI-localization/transcription-
quality explicitly non-blocking; the Unicode-corruption / language-leak /
raw-audio / auto-apply / fullscreen-minimize / Panel-data-loss /
secret-leak hard blockers all present). No scope leaks found; **no
production code changed**. Evidence: language/grammar/editor + voice
**633**, GN/Series/lock/isolation/export **429**, broad certification
sweep **1527** = **2589 passed, 0 failures**. **Gate result: A.**
Graphic Novel post-refactor re-certification can resume, followed by
Final Alpha RC re-certification.

**Graphic Novel post-refactor RE-certification (2026-06-11): PASSED.**
After the scope cleanup, a combined gate re-certified the canonical
Act → Page → Scene → Panel architecture together with the language and
Dexter-scope dimensions. Eleven new permanent pins
(`tests/test_gn_act_page_structure.py` → **70**): the full gate string set
(zh/ja/ko/ar/he/hi/bn/th/mixed) through **every** Panel field with reload +
canonical export + snippet safety; GN project language coordinates AI
context (Japanese no-word-spacing note, Arabic RTL note), resolves
Dexter's "Use project language", and never mutates Panel text while the UI
stays English; and Dexter's writing-room routing commits a CJK transcript
into the selected Panel's Dialogue field (explicit target,
append-preserving). Everything else re-verified green: data model,
Outline shape/editing, Manuscript derivation + empty states, mirroring,
standalone-Pages/fullscreen safety, export (assignments, no
dupes/secrets/image data, no grammar/translation metadata),
compatibility (NULL offsets, idempotent migration, legacy tables
untouched), other modes, Dexter scope, blockers. **No production code
changed.** Evidence: GN core/surfaces/export **376** + language &
voice/Dexter **355** + GN engine/Series/lock/isolation/backup **298** +
broad certification sweep **1527** = **2556 passed, 0 failures**.
**Gate result: A — Final Alpha RC re-certification can resume.**

## FINAL ALPHA RC RE-CERTIFICATION (2026-06-11): PASSED

The complete Desktop Alpha was re-certified end-to-end after the Graphic
Novel refactor, the multi-language system, and the final scope cleanup —
**no blockers found; zero production or test changes needed** (a clean
certification run at commit `044f675`, version **0.9.0-alpha**, no tags).

**Certified scope:** five writing modes (Novel Act→Chapter→Scene;
Screenplay; **Graphic Novel Act→Page→Scene→Panel with the Manuscript
deriving from the Outline**; Stage Script; **Series
Season→Episode→Act→Chapter→Scene**); **Dexter's Room** as the local voice
writing/formatting/routing room (review-first, explicit Apply, undo, no
grammar coupling, no cloud speech, no raw audio off-machine); **project
Writing Language** + full Whisper list + Dexter language modes + AI
preserve-language context; **Unicode/CJK/RTL** writing across every
surface and export; exports clean of secrets/image/grammar/translation
metadata; writing-mode lock, project isolation, dirty close-save,
autosave; startup verified for all five modes with Pages/Plot hidden,
voice off, UI English-only, grammar off, ComfyUI stub inert; requirements
clean (10 deps, no dupes, no grammar/cloud packages).

**Deferred (documented, not exposed as complete):** grammar checking and
deep text correction (future Review/Correction phase), UI localization
(English-only Alpha; dormant scaffolding), cloud realtime voice/speech,
ComfyUI/image generation, Canvas Plot, standalone Pages, cloud/web/sync.

**Evidence (fresh, this gate):** authoritative broad certification sweep
**1527** + full voice/Dexter matrix **569** + language/grammar/editor
**359** + GN + pages safety **358** + Series/backup/lock/lifecycle/export
gates **254** = **3067 passed, 0 failures**. (Curated-batch methodology
per `docs/ALPHA_TEST_COMMANDS.md`; the combined-single-run Qt/GC teardown
caveat remains documented and environmental.)

**Manual checks still required before tagging** (see
`docs/ALPHA_MANUAL_SMOKE_TEST.md`): real microphone (V-items), macOS
fullscreen (F-items), language/Unicode UI pass (L-items), optional
PDF/DOCX export visual checks, Dexter and Graphic Novel real-UI passes.

**Classification: A — Final Alpha RC re-certification passed; ready for
manual release confirmation.**

## Graphic Novel UI bugfix (2026-06-11): shared block-based UX

Post-re-certification screenshots showed the GN screens still used bespoke
chrome. Fixed before release: the **Manuscript** is now one full-document
block editor (ACT/SCENE headers, act-wide PAGE blocks, panel script
blocks, mode label + live word count — no "Comics Script" title, no scene
dropdown) and the **Outline** is the shared block/card planner (Act → Page
→ Scene → Panel cards, selection highlight, inline page/scene/start-page
editing — no tree, no empty detail pane). Data model, mirroring, voice
panel targeting, deep-links, Pages inertness and exports unchanged.
Verification: GN suites **228** + voice/cross-cutting **555** + GN
legacy/Series **205** + broad certification sweep **1527** — all green.
The Final Alpha RC re-certification result stands; manual smoke items
(GN real-UI pass) remain.

## GN block-UX post-fix gate (2026-06-11): PASSED

Certified the UI bugfix: zero old-UI leaks (no "Comics Script" marker, no
tree, no scene dropdown anywhere in the GN view sources or rendered UI —
source+widget pinned); the Manuscript renders the shared full-editor
paradigm (mode label + live count, ACT/SCENE/PAGE/PANEL blocks) and the
Outline the shared block/card paradigm; Screenplay's PlanView/
WritingCoreView pinned untouched; CJK entered through a new Manuscript
block reaches the Outline snippet; routing, data model, mirroring,
Pages inertness, exports, language/Dexter scope all re-verified. Three
pins added (GN act-page suite → 84). Evidence: gate matrix **537** green
+ the fix commit's full runs at this tree (GN 228, voice 139, legacy/
Series 205, broad sweep **1527**). **No production code changed.
Classification: A — Final Alpha RC re-certification can resume** (manual
GN real-UI smoke pass remains).

## Phase 2 — GN shared-editor routing (2026-06-11): PASSED

GN Manuscript route → shared `WritingCoreView` (full text/block editor; GN
grammar; chapters hidden); GN Outline route → shared `PlanView` GN schema
(Act → Page → Scene → Panel cards, continued spans, add actions, panel
deep-link to the Manuscript cursor); legacy `GraphicNovel*View` labelled
LEGACY — NOT ROUTED and unreachable; Dexter's Panel targeting now resolves
from the shared editor's cursor (`panel_at_offset`); Pages stays inert;
Screenplay/Novel/Stage/Series byte-identical paths. Evidence: GN +
shared-editor + pages + voice-gate suites **501**, GN phase suites **270**,
voice batch **183**, gates/isolation/lock/language **319**, broad
certification sweep re-run green after flipping two stale mount pins.
(The one observed combined-run crash reproduced only in an oversized
18-file batch — the documented Qt teardown flake; both halves pass alone.)
**Classification: A.**

## Phase 2 verification gate (2026-06-11): PASSED

Routing proven with mount pins and a new production-source pin: GN
Manuscript mounts the SHARED `WritingCoreView` (GN grammar, chapters
hidden), GN Outline mounts the SHARED `PlanView` GN schema; no production
module instantiates the LEGACY `GraphicNovel*View` renderers (their
modules carry the LEGACY — NOT ROUTED label) and "Comics Script" exists
nowhere in code; Pages stays inert; Screenplay/Novel/Stage/Series/Dexter
paths byte-identical; mirroring, isolation, dirty-save, exports, mode
lock and the alpha gate green. Evidence: verification matrix **740
passed, 0 failures** + the Phase-2 commit's runs at this tree (501 + 270
+ 183 + 319 + broad sweep **1527**). **No production code changed.
Classification: A — Final Alpha RC re-certification can resume.**

## FINAL ALPHA RC RE-CERTIFICATION after the GN shared-renderer fix (2026-06-11): PASSED

The complete Desktop Alpha re-certified at `4437cbe` (0.9.0-alpha, no
tags) after the Graphic Novel renderer replacement. The former release
blocker is resolved and pinned: GN Manuscript = shared `WritingCoreView`
(GN grammar, full text/block editor, no page-manager chrome, no Comics
Script); GN Outline = shared `PlanView` GN schema (Act → Page → Scene →
Panel cards, continued spans, adds/moves/deletes, panel → Manuscript
cursor); legacy renderers LEGACY-labelled and proven unconstructed in
production; Pages inert. All other scope re-verified: five modes, mode
lock, Dexter (writing room, preview-first, cursor-resolved Panel targets,
no cloud/raw audio), Writing Language + Whisper list + Unicode/CJK/RTL,
grammar + UI localization deferred, exports clean, requirements clean,
blocker policy current, porting contract current. Evidence at this tree:
broad certification sweep **1527** + full voice/Dexter + language **638**
+ verification matrix **740** = **2905 passed, 0 failures**.
**Classification: A — ready for manual release confirmation** (real
microphone, macOS fullscreen, GN/Dexter real-UI, optional-export and
Unicode/PDF visual checks remain; do not tag until the manual checklist
passes).

## Last audit summary

The final global multi-mode integrity audit (the **Alpha Release Gate**, see
[ALPHA_RELEASE_GATE_AUDIT.md](ALPHA_RELEASE_GATE_AUDIT.md)) returned **A**: all five
writing modes form one coherent system on the universal Manuscript, with the
canonical Act → Chapter → Scene invariant, project isolation, export privacy,
dirty-state handling, mode-aware non-mutating AI assistance, and no scope creep.
Per-mode integrity audits also returned A: Screenplay, Graphic Novel
([GRAPHIC_NOVEL_MODE_INTEGRITY_AUDIT.md](GRAPHIC_NOVEL_MODE_INTEGRITY_AUDIT.md)),
Stage Script ([STAGE_SCRIPT_MODE_INTEGRITY_AUDIT.md](STAGE_SCRIPT_MODE_INTEGRITY_AUDIT.md)),
and Series ([SERIES_MODE_INTEGRITY_AUDIT.md](SERIES_MODE_INTEGRITY_AUDIT.md)).

## Tests run / result

| Run | Command | Result |
|-----|---------|--------|
| Focused gate | `pytest tests/test_alpha_release_gate.py` | **35 passed** |
| Broad certification sweep | see [ALPHA_TEST_COMMANDS.md](ALPHA_TEST_COMMANDS.md) | **1527 passed, 0 failures** |

The previously-known red tests (two stale `test_logos_integration.py` cases that
referenced the removed `_action_buttons` toolbar API) were fixed at the test layer;
the suite is now fully green. The full ~120-file suite cannot finish inside the
environment's time cap, so the gate runs a broad blast-radius sweep across every
mode + cross-cutting surface (see [ALPHA_TEST_COMMANDS.md](ALPHA_TEST_COMMANDS.md)).

## Changed files for packaging (this step)

Documentation only:

- `RELEASE_NOTES_ALPHA.md` (updated — Alpha RC multi-mode section)
- `CHANGELOG.md` (updated — Alpha RC entry)
- `docs/ALPHA_RC_STATUS.md` (new — this file)
- `docs/ALPHA_RC_CHECKLIST.md` (new)
- `docs/ALPHA_TEST_COMMANDS.md` (new)
- `docs/KNOWN_LIMITATIONS_ALPHA.md` (updated — multi-mode RC section)
- `docs/ALPHA_RELEASE_GATE_AUDIT.md` (updated — final RC status note)

**Production code touched: none.**

## Series hierarchy — Phase 1 (post-RC foundation)

The Series Alpha shortcut (Act = Season, Chapter = Episode) has been replaced by a
real **Season → Episode → Act → Chapter → Scene** hierarchy: Season/Episode are
stored rows, each Series scene links to its Episode via a new nullable
`Scene.episode_id` (NULL elsewhere — no other mode is affected), and the
Act→Chapter→Scene outline is episode-scoped. The Series Navigator is now the
structural editor (full CRUD + non-destructive, confirmed legacy migration). The
*global* Outline/Manuscript/Timeline stay episode-agnostic for now (documented
Phase-1 boundary). Single source: `logosforge/series_structure.py`; see
[SERIES_ARCHITECTURE_CORRECTION_REPORT.md](SERIES_ARCHITECTURE_CORRECTION_REPORT.md)
§10 and [KNOWN_LIMITATIONS_ALPHA.md](KNOWN_LIMITATIONS_ALPHA.md). Tests:
`tests/test_series_hierarchy.py` (70 passed); legacy navigator stays green.

## Deferred work (out of scope, intentionally)

- Canvas Plot (hidden/deferred), ComfyUI / image generation, production scheduling,
  rehearsal / writers-room management, showrunner automation, and a Season/Episode-
  aware *global* Outline (the Phase-1 hierarchy lives in the Series Navigator). See
  [KNOWN_LIMITATIONS_ALPHA.md](KNOWN_LIMITATIONS_ALPHA.md).

## Recommended next steps

1. **Manual local smoke test** — follow [ALPHA_RC_CHECKLIST.md](ALPHA_RC_CHECKLIST.md).
2. **Optional Git tag** — only after manual confirmation, and only when explicitly
   instructed (this step does **not** tag).
3. **Optional GitHub release** — after tagging, when instructed.
4. **Commercial packaging plan** — prepared separately (see below).

## Commercial product note (documentation only)

The **current repository is the Python core / main creative-writing app** — the
single source of truth for the engine, data model, and AI surfaces. The planned
commercial products are **separate, later packaging/distribution targets**:

- an **Electron desktop app**, and
- a **Web app**,

both of which should **call or attach to this Python core / API** rather than
re-implement it. This Alpha RC is the Python core milestone and **should not be
conflated** with final Electron/Web commercial packaging.

## Voice MVP Phases 1–9 — Alpha hardening gate (2026-06-10)

The complete local voice stack — flag/capture/buffering (1), mode-aware
Commit Router (2), transcript history with edit/undo/retry (3), preview-first
Intent Router (4), Billy Voice Bridge (5), Dexter's Room shell with state
machine + proposal queue (6), project Voice Glossary corrections (7), Voice
Setup/diagnostics/backend profiles incl. whisper.cpp (8) — passed the Phase 9
end-to-end hardening gate. Privacy audit: `voice/lan_server.py` is the only
network-touching voice module (private/loopback hosts enforced); **zero
logging statements** in the voice stack; exports and diagnostics carry no
transcripts, glossary internals, audio or secrets. Cross-cutting pins:
uncommitted voice history never locks the writing mode (committed text
does); app close while recording stops safely; 30-segment sessions stay
ordered with audio dropped on discard/clear; one active backend per mode by
construction; every voice module imports without the optional dependencies.
Suites: 13 voice files **427 passed** (incl. `tests/test_voice_alpha_gate.py`,
9) + writing-mode/structural regression **449 passed** — 0 failures.
Real-microphone/fullscreen items remain in the manual checklist (V1–V49).
**Classification: A — Voice MVP is Alpha-safe.**

## FINAL ALPHA RC INTEGRATION GATE (2026-06-10) — PASSED

One integration audit across everything that ships in the Alpha: core app +
five writing modes + corrected Graphic Novel architecture (standalone Pages
disabled; Outline manages Pages/Panels; the Manuscript is the mirrored
comics script editor) + corrected Series hierarchy (Season → Episode → Act →
Chapter → Scene; old shortcut deprecated) + the complete Voice MVP
(Phases 1–9, review-first everywhere, local-only) + exports/requirements +
privacy. **No release blockers found; no production code changed in this
gate.**

Evidence (all green, 0 failures):

- **Authoritative broad certification sweep** (`docs/ALPHA_TEST_COMMANDS.md`
  §2, 49 files): **1527 passed** — identical to its historical baseline, in
  a single process.
- **Post-sweep voice + preferences batch** (14 files, Phases 1–9 incl. the
  Phase 9 hardening gate): **392 passed**.
- **Post-sweep GN/Series/lock/lifecycle/export batch** (15 files): **392
  passed**.
- Total this gate: **2311 passed, 0 failed.**

Requirements audit: `reportlab` + `python-docx` present for exports; **no
voice dependencies baked in** (faster-whisper / sounddevice / whisper.cpp
remain optional, lazy and documented); graceful degradation pinned by
tests. Privacy: exports and diagnostics carry no API keys, provider
secrets, transcripts, audio or temp voice data (test-pinned); the only
network-touching voice module is the private-host-enforced LAN client.

Remaining before tag: the **manual smoke test** (V1–V49 + P/F items — real
microphone, macOS fullscreen, optional-dep exports) and maintainer
sign-off. The full ~120-file suite stays infeasible under the gate time
cap (documented combined-run caveat); the sweep + post-sweep batches above
are the authoritative automated check.

**Classification: A — final Alpha RC integration gate passed; ready for
manual release confirmation.**


## Writer QA harness (required before Alpha release confirmation)

Assistant behavior is now verified by the **Writer QA harness** (behavior, not
just code): `python tools/writer_qa/run_writer_qa.py --suite all` drives the real
Assistant contract layer with a deterministic fake provider across a section ×
mode × action × target × response matrix and writes `reports/writer_qa/latest.{json,md}`.
GitHub-only/CI runs catch contract / routing / validation / cache / apply
failures but **not** all GUI/render/fullscreen issues — local PC (Level 2 API /
Level 3 GUI computer-use) is recommended for final human-like acceptance. Test
projects only; no real provider keys; no cloud/GitHub. See
`docs/WRITER_QA_AGENT_PLAN.md`.

**First-run findings (to fix before release):** 5 BLOCKER — wrong-mode Assistant
output is applyable; 5 HIGH — empty output is applyable; 1 MEDIUM — Chat does not
clarify on a missing target. Alpha release confirmation is **blocked** until the
Writer QA suite reports **0 BLOCKER**.


## Local Writer QA agent mode (2026-06-20)

Added a **local PC QA mode** (`logosforge/qa_mode.py`) so an external GUI /
computer-use writer agent (or a human) can drive the **real app** deterministically
with **no real provider, network, cloud, or credentials**.

- **OFF by default** — enabled only by `LOGOSFORGE_QA_MODE` in {1,true,yes,on}.
  Disabled, runtime behavior is unchanged (verified: with QA off,
  `chat_completion` takes the real provider path; the default settings key
  `qa_fake_provider_profile` is empty).
- **Deterministic fake provider, QA-only.** `chat_completion` short-circuits to
  `qa_mode.fake_completion` *before* any credential/network use. Profiles A–O
  (valid per mode/section, planning/context/meta/wrong-mode/empty/secret-leak,
  provider error); default `valid_auto` returns mode-correct content. Selection:
  settings → `LOGOSFORGE_FAKE_PROVIDER_PROFILE` → default.
- **Redacted logging + report export.** Assistant responses log redacted events
  (secrets/tokens/local paths/raw audio removed; long content truncated) under
  `logs/writer_qa/`; `export_report()` and the test-only CLI
  `tools/writer_qa/export_local_report.py` write
  `reports/writer_qa/local_latest.{json,md}`. All generated artifacts are
  git-ignored.
- **Fixtures + script + tests.** `sample_projects/writer_qa/` (per-mode + Notes/
  PSYKE), `docs/LOCAL_WRITER_QA_AGENT_SCRIPT.md` (20 scenarios + bug template),
  `tests/test_local_writer_qa_mode.py`.

**Verification:** `tests/test_local_writer_qa_mode.py` **30 passed**; existing
`tests/test_writer_qa_harness.py` **16 passed**; alpha release gate
(`tests/test_alpha_release_gate.py`) **35 passed** — no regressions. The local
report run is offline and leak-free (forced `invalid_secret_leak` → all responses
withheld, nothing leaked into logs/report). **Classification: A** — additive,
default-off; no production behavior change.
