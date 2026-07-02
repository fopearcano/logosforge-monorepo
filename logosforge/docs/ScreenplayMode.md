# Screenplay Mode (Phase 10A foundation)

When a project's writing mode is **Screenplay** (`Project.narrative_engine ==
"screenplay"`, exposed via `writing_modes`), Logosforge adapts the Manuscript,
Assistant, Logos, Strategy, and Export layers. Phase 10A is the *foundation* —
not a Final Draft clone.

## Project Writing Mode vs Manuscript Element Type

Two distinct concepts — never conflated:

- **Project Writing Mode** = *what kind of work this is* (Screenplay). One
  authoritative value per project (`narrative_engine`).
- **Manuscript Element Type** = *how the current text block is formatted*
  (Scene Heading / Action / Character / Dialogue / Parenthetical / Transition).
  Choosing an element type is local editor/text state; it never changes the
  project's writing mode.

## Element taxonomy (`logosforge/screenplay.py`)

The canonical, single-source taxonomy (no scattered strings):

| Key | Label | Uppercase | Dialogue | Structural |
|---|---|---|---|---|
| scene_heading | Scene Heading | ✓ | | ✓ |
| action | Action | | | |
| character | Character | ✓ | ✓ | |
| parenthetical | Parenthetical | | ✓ | |
| dialogue | Dialogue | | ✓ | |
| transition | Transition | ✓ | | ✓ |
| shot | Shot | ✓ | | |
| note | Note | | | |

Helpers: `is_uppercase_element`, `normalize_caps`, `dialogue_elements`,
`structural_elements`, `SCENE_HEADING_PREFIXES` (INT./EXT./…), and
`character_suggestions(db, pid)` (PSYKE character names, uppercased, read-only).

## Manuscript

The editor already renders the six core elements with screenplay styling
(margins, caps, alignment) and offers them in the element selector + Ctrl+1..6
when the project mode is Screenplay (`writing_formats.SCREENPLAY`). Novel editing
is unchanged. `normalize_caps` provides safe, opt-in uppercasing for
caps elements; no aggressive autoformatting changes user text.

## Assistant context

The controlled `[Project Mode]` block (via `assistant_context_policy` →
`writing_modes.mode_context_block`) gains one short screenplay guidance line in
Screenplay mode: *prefer visible action, scene economy, subtextual dialogue,
clear scene turns, setup/payoff; avoid novelistic interior exposition unless
requested.* Deterministic, capped, no LLM/DB during assembly.

## Logos actions

New screenplay-only actions (registered with `modes=("screenplay",)`, so they
**never appear in Novel** and surface + sort first in Screenplay):

- **Manuscript:** Convert Prose to Visual Action, Check Scene Turn, Reduce
  Novelistic Interior Exposition, Clarify Character Objective, Improve Scene
  Economy (plus existing Improve Dialogue / Improve Subtext / Compress).
- **Outline:** Check Sequence Logic, Strengthen Act Turn, Clarify Central
  Dramatic Question.
- **Plot:** Track Setup/Payoff, Check Causal Chain, Check Visual Turn.

All non-destructive and run through the normal Logos preview/confirm path.

## Strategy

`StrategyRouter` already activates the Screenplay medium profile automatically
when the project mode is Screenplay; a manual override still wins, and the
strategy explanation names the mode. Go McKee / Controlling Idea still layer in
when enabled; Quantum/Lambda does not override the medium unless selected.

## Health / Diagnostics

The engines **receive** the writing mode (`HealthEngine` / `DiagnosticsEngine`).
Screenplay-specific *detectors* (no-visible-turn, expositional dialogue, unclear
objective, novelistic action, setup/payoff tracking, weak scene economy) are
**deferred to Phase 10B** rather than faked — current data does not support them
without per-block element metadata.

## Export

`export_screenplay()` produces conservative screenplay-style text: uppercased
title, a `Writing Mode: Screenplay` header line, per-scene slug lines
(`INT. PLACE — TITLE`) and scene body. Fountain/FDX/PDF helpers exist but emit
body text as generic action. JSON/Markdown metadata include `writing_mode`.
Robust when a project has no scenes or an invalid mode (falls back to novel).

## Phase 10B — Screenplay block engine + export hardening

`logosforge/screenplay_blocks.py` adds a lightweight, **non-persisted** block
layer derived on demand from flat scene text (no DB schema change):

- **`ScreenplayBlock`** — `element_type / text / scene_id / order_index /
  metadata`; element type is validated centrally (invalid → `action`).
- **`parse_screenplay_text(text, scene_id=None)`** — conservative heuristics on
  blank-line-separated chunks: `INT./EXT./EST.` → scene_heading; uppercase lines
  ending `TO:` / `FADE …` → transition; an uppercase short cue leading a chunk →
  character, with following `( … )` → parenthetical and other lines → dialogue;
  everything uncertain → **action** (no false positives, no text loss).
- **`serialize_blocks(blocks, uppercase=True)`** — round-trip-safe text;
  uppercases caps elements, normalizes parentheticals.
- **`to_fountain(blocks)`** — Fountain-like output (forced `.` headings only when
  needed, `> ` transitions, `[[ ]]` notes).
- **`character_cues(blocks)`** — unique, uppercased cues present in a scene.

**Export hardening:** `export_screenplay` and `export_fountain` now render each
scene body through the parser/serializer, so character cues / transitions /
scene headings are uppercased and parentheticals normalized — while preserving
all text. Novel export is unaffected; both carry the `Writing Mode` metadata.

**Current element in context:** `WritingCoreView.current_element_type()` exposes
the cursor block's element; the host carries it into `LogosContext.active_block_type`
(only for screenplay element keys, so Novel stays `prose`). The Assistant gains a
concise `[Screenplay Scene]` line (heading + characters present, parsed from the
scene) when the project is a screenplay and a scene is active — data-driven, capped.

**Logos (hardened set):** added `Strengthen Setup/Payoff`, `Detect Overwritten
Action` (Manuscript) and `Improve Escalation` (Outline), all screenplay-only and
preview/confirm.

## Phase 10C — deterministic screenplay diagnostics + scene economy

`logosforge/screenplay_diagnostics.py` evaluates a scene **as a screenplay
scene** (built on the 10B block parser) — rule-based, no LLM, no DB writes,
confidence-aware.

- **`ScreenplaySceneReport`** / **`ScreenplayDiagnosticIssue`** (serializable):
  block/character counts, dominant block type, `economy_label`
  (dialogue-heavy / action-heavy / balanced / sparse), an approximate page/minute
  estimate (clearly rough), plus issues / strengths / warnings / summary.
- **Checks** (documented thresholds as module constants): scene economy ratios,
  missing scene heading, only-notes, internal-prose action, overwritten action,
  long dialogue, parenthetical overuse, single-voice scenes, transition/shot
  overuse, **scene-turn heuristic** (says *"Scene turn unclear"* with low
  confidence — never asserts absence), **character objective** (PSYKE-aware:
  missing data lowers confidence, never hard-fails), and cautious **setup/payoff
  candidates** ("Possible setup" — hooks for Phase 10D).

**Warning vs error:** every issue is a *warning/suggestion* with a severity
(`info` / `watch` / `weak` / `critical`) and confidence — never a hard error, and
nothing is auto-changed.

**Logos:** `Diagnose Scene Economy` (`sp_diagnose_scene_economy`) is a
**deterministic** action — it runs the engine with **no LLM call** (routed via
`logosforge/logos/deterministic.py`). Generative helpers (`Tighten Dialogue
Economy`, `Suggest Visual Beat`, `Suggest Action Interruption`, plus the 10A/10B
set) call the Assistant only when the user explicitly invokes them, always
through preview/confirm. All screenplay-only and hidden in Novel.

**Assistant:** a concise `[Screenplay Diagnostics]` block (economy summary + top
3 issues) is injected for screenplay projects with an active scene
(`include_screenplay_diagnostics_in_assistant_context`, default on) — capped,
deterministic, no LLM/DB during assembly.

**Narrative Health:** for screenplay projects the report appends mode-aware
categories — Visual Action, Scene Economy, Dialogue Economy, Scene Turn,
Character Objective, Setup/Payoff — computed from the deterministic engine.
Subtext Candidate and Cinematic Continuity are present but **deferred**
(`Not Enough Data`). No fake precision; no background LLM.

**Export:** `export_screenplay_diagnostics_json(db, project_id)` emits per-scene
reports + writing mode (additive; existing exports untouched).

## Phase 10D — setup/payoff + subtext tracking

Two deterministic, report-only engines (no LLM, no DB writes, no auto-mutation of
PSYKE/Graph/Plot) that help the writer *track* cinematic promises and dialogue
subtext across scenes — they do not judge art.

**Setup/Payoff** (`logosforge/screenplay_setup_payoff.py`) —
`SetupPayoffCandidate` / `SetupPayoffReport`. Detects promise/threat/secret/
plan/deadline markers, loaded objects, and PSYKE object/place/lore/theme name
mentions; cross-scene recurrence → **recurring motif** + **possible payoff**
(linked back to the planting scene as a graph-hook suggestion); single
occurrences → **unresolved setup candidate**. Character names are excluded from
motif tracking (they naturally recur). Cautious wording, confidence-scaled.

**Subtext** (`logosforge/screenplay_subtext.py`) — `SubtextSignal` /
`SubtextReport`. Flags on-the-nose / stated-emotion lines, exposition markers,
avoidance/indirect answers, parenthetical over-explanation, and objective gaps
(PSYKE-aware: missing data lowers confidence, never hard-fails). Wording is
suggestive ("may be too on-the-nose"), never a verdict.

**Persistence decision:** *report-only / in-memory* — no new DB schema. A
persistent `ScreenplayLink` table (confirmed setup→payoff / motif links, dismiss
state) and Graph-edge / PSYKE-entry creation actions are **deferred to Phase 10E**
(candidates surface as suggestions only; nothing is confirmed automatically).

**Logos:** deterministic (no LLM) — `Detect Setup/Payoff Candidates`,
`Track Unresolved Setups`, `Find Possible Payoffs`, `Check Dialogue Subtext`,
`Find Exposition in Dialogue`; generative rewrites (LLM on explicit invoke only) —
`Reduce On-the-Nose Dialogue`, `Strengthen Character Objective Gap`, `Add Action
Beat for Subtext`, `Convert Stated Emotion to Behavior`. Screenplay-only; hidden
in Novel; preview/confirm for any mutation.

**Assistant:** gated `[Screenplay Setup/Payoff]` (≤3 unresolved/payoffs/motifs)
and `[Screenplay Subtext]` (status + ≤3 signals) blocks via
`include_screenplay_tracking_in_assistant_context` (default on) — capped,
deterministic, no LLM/DB during assembly, no stale-project leak.

**Narrative Health:** Setup/Payoff, Motif Recurrence, Dialogue Subtext and
On-the-Nose categories are now populated from these engines; Cinematic Continuity
remains deferred (`Not Enough Data`).

**Export:** `export_setup_payoff_report_json` and `export_subtext_report_json`
(additive; existing exports untouched).

## Phase 10E — story-link graph + confirmed links

`logosforge/screenplay_graph.py` assembles a node/edge **story-link graph** from
the existing screenplay data plus user-confirmed links — references only, never
copies of scene/PSYKE text (the graph is **not** a source of truth). See
**docs/Graph.md** for node/edge types and the full surface.

- **Candidates** (setup→payoff, motif, character-in-scene, psyke→scene,
  subtext→character) are generated dynamically and never auto-persist.
- **Confirmed links** persist in the new `StoryLink` table (created idempotently;
  old DBs gain it empty). `confirm_candidate` / `dismiss_link` / `resolve_link`
  are explicit, user-invoked — analysis code never mutates them.
- **Logos** (deterministic, no LLM): `Show Story Link Graph`, `Explain This Link`.
- **Assistant**: capped `[Screenplay Story Links]` block
  (`include_screenplay_links_in_assistant_context`).
- **Health**: `Confirmed Setup/Payoff Coverage` (confirmed links weigh more) +
  `Unresolved Candidate Density` (cautious warning).
- **Export**: `export_screenplay_graph_json` + `export_story_links_json`
  (schema-versioned).

## Phase 10F — production polish + export preparation

- **Render model** (`screenplay_render.py`): serializable `ScreenplayRenderDocument`
  / `ScreenplayRenderBlock` built from the parsed blocks (style + `export_text`,
  title page, **approximate** page/minute estimate, warnings) + `render_to_html`
  / `render_to_plain_text`. Foundation for future PDF/FDX.
- **Title page metadata**: `title/credit/author/source/draft_date/contact/notes`
  stored in project settings (no schema change); falls back to the project title;
  exported at the top of Fountain.
- **Export preferences** (project settings, conservative defaults): note
  inclusion (off), casing, title page, export target, approximate estimate.
- **Fountain hardening**: title page emitted; notes honor the pref (excluded by
  default, `[[ ]]` when shown); the parser now recognizes `[[ ]]` notes and they
  round-trip; **duplicate scene headings fixed** (the metadata slug is skipped
  when the scene content already opens with a heading); no text loss.
- **Validation** (`screenplay_export_validation.py`): deterministic readiness
  report — blocking errors (empty / unsupported target) vs warnings (missing
  title/headings, orphan dialogue/parentheticals) vs suggestions. Blocks export
  only when truly unsafe.
- **Logos** (deterministic, no LLM): `Validate Screenplay Export`, `Generate
  Export Readiness Report`, `Preview Screenplay Render`, `Find Orphan Dialogue`,
  `Find Orphan Parentheticals`, `Check Production Polish`.
- **Assistant**: capped `[Screenplay Export Readiness]` block
  (`include_screenplay_export_in_assistant_context`).
- **Health**: format-health categories (Export Readiness, Title Page
  Completeness, Scene Heading Integrity, Dialogue Formatting Integrity) — **capped
  at *Needs Attention*** so a formatting issue never flips the narrative overall
  status. Format problems are kept distinct from craft problems.
- **Preview HTML** export (`export_screenplay_preview_html`) — conservative, not
  page-accurate.

See **docs/Export.md** for the full export surface, what is approximate vs
professional, and why PDF/FDX remain basic.

## Phase 10G — Fountain-first export + import pipeline

**Fountain** (not generic Markdown) is the canonical plain-text screenplay
interchange format. `logosforge/screenplay_fountain.py` is the dedicated
serializer / parser / validator.

- **Serializer** (`serialize_screenplay_to_fountain`): maps blocks → `.fountain`
  with conservative forcing — `.` forced scene headings, `@` mixed-case cues,
  `!` ambiguous ALL-CAPS action, `> ` non-standard transitions; dialogue groups
  stay together; title page on top; notes `[[ ]]` (option-gated). Returns
  `FountainExportResult` (text, `.fountain` filename, warnings, schema_version).
- **Parser** (`parse_fountain_to_screenplay_blocks`): real Fountain syntax —
  forced elements, title page, notes, **boneyard `/* */`** (stripped + warned),
  **sections `#`/`##`** and **synopses `=`** (preserved as notes + warned),
  centered/lyrics/page-break (degraded + warned); ambiguous → action; no text
  loss. Returns `FountainParseResult` (blocks, title_page, warnings, ambiguous).
- **Validator** (`validate_fountain_export`): blocking errors vs warnings;
  blocks only when truly unsafe.
- **Roundtrip**: blocks → `.fountain` → blocks preserves standard element types
  (scene heading / action / character / parenthetical / dialogue / transition /
  note) and the title page.
- **Export**: `export.export_screenplay_fountain[_result]` is canonical;
  `export_fountain` now routes screenplay projects through it (other modes
  unchanged); `export_fountain_validation_json`. Generic `export_markdown` stays
  **separate** — screenplay never relies on the Markdown serializer.
- **Logos** (deterministic, no LLM): Validate Fountain Export, Preview Fountain
  Output, Check Fountain Compatibility, Find Ambiguous Fountain Elements, Explain
  Fountain Warning, Prepare Screenplay for Fountain Export.
- **Assistant**: `[Fountain Export Readiness]` block (shown for the default
  `.fountain` target; the generic export block shows for other targets — exactly
  one appears).
- **Health**: Fountain Export Readiness + Unsupported Screenplay Elements
  (format health, capped at *Needs Attention*).

Editor architecture: the internal source of truth remains **structured
screenplay blocks** (derived from flat scene text); Fountain is an
interchange/export/import language. Raw-Fountain editing in Manuscript is not the
internal format and is deferred.

## Phase 10H — professional output layer

DOCX (stable), approximate PDF, HTML print preview, and **experimental** FDX
(gated) derived from the render model; per-element style profiles with safe font
fallback; output-readiness validation with compatibility levels; deterministic
Logos output actions; opt-in `[Professional Output Readiness]` Assistant block;
format-health categories (Professional Output Readiness, FDX Compatibility Risk).
Fountain remains canonical. See **docs/ProfessionalScreenplayOutput.md**.

## Phase 10K — revision intelligence

A deterministic change-impact layer: when a scene changes, a Change Impact
Map reports affected scenes, PSYKE entries, setup/payoff chains and continuity
risks with explicit confidence (confirmed/likely/possible/unknown). Saved
reports persist lightweight references only; deterministic Logos actions; a
capped `[Revision Impact]` Assistant block (from the last saved report); and
Revision Causality / Continuity Revision health categories. Assisted, never
autonomous — no auto-rewrite/mutation. See **docs/RevisionIntelligence.md**.

## Phase 10J — production draft layer

Optional, screenplay-only production drafts: persistent scene numbering,
omitted-scene tracking, dated/coloured revision sets, production-readiness
validation, and `export_production_fountain` (`#N#` numbers + OMITTED).
Page locking is approximate-awareness only (deferred). Deterministic Logos
status actions, `[Production Draft Status]` Assistant block (active-only), and
production health categories (capped). See **docs/ProductionDrafts.md**.

## Phase 10I — export integrity

Audit/hardening pass: a no-text-loss harness across Fountain/DOCX/HTML/
FDX (PDF file-validated), a render-model **scene-heading injection fix**
(DOCX/PDF/preview/FDX no longer drop headings), verified Fountain↔Markdown
separation, writing-mode export visibility, and capped/leak-free Assistant
export context. See **docs/Export.md** (Export integrity).

## Intentionally deferred (future)

- Fountain **import UI** (parser + roundtrip exist as a service; project-import
  UI / destructive merge with preview-confirm is deferred).
- Export **menu / options dialog** wiring (functions + options + Logos exist).
- Section/synopsis **export** from outline (import handles them; export off by
  default).
- Rich-text emphasis (`*`/`_`) mapping (no rich-text source yet); page-accurate
  PDF + production FDX; Cinematic Continuity detector.

## (Earlier) Intentionally deferred to Phase 10G

- Page-accurate PDF pagination + production-grade FDX.
- Title-page / export-preferences **editor UI** (storage + service API exist).
- Fountain **import UI** (parser round-trip exists; project import UI deferred).
- Manuscript screenplay margin polish beyond the current approximation; Cinematic
  Continuity detector.

## (Earlier) Intentionally deferred to Phase 10F

- Interactive screenplay graph **widget** + filters + evidence panel.
- UI confirmation buttons + mutating Logos actions (Confirm/Dismiss/Resolve, Add
  to Graph, Create PSYKE from candidate) — persistence + service API exist; only
  the preview/confirm UI wiring is deferred.
- Strategy-explanation enrichment from live graph state; Cinematic Continuity.

## (Earlier) Intentionally deferred to Phase 10E

- Persistent confirmed setup↔payoff / motif links (`ScreenplayLink` table) with
  confirmed/dismissed/resolved state + idempotent migration.
- User-approved Graph edges (setup→payoff, motif recurrence) and PSYKE entry
  creation/linking from candidates (preview/confirm operations).
- Strategy-explanation enrichment that cites live tracking state.
- Dedicated tracking drawer UI; Cinematic Continuity / contradiction /
  power-shift detectors (need semantics).

## (Earlier) Intentionally deferred to Phase 10D

- Cross-scene setup/payoff tracking engine (10C only flags candidates).
- Dedicated screenplay-diagnostics drawer + click-to-focus-block (today the
  diagnostic surfaces via the Logos toolbar action).
- Subtext / Cinematic Continuity detectors (need an LLM); precise runtime.

## (Earlier) Intentionally deferred to Phase 10C

- **Per-block element persistence** — block types are still in-memory while
  editing and re-derived (by the parser) for export/analysis; durable per-block
  storage needs a (safely migrated) schema and is **Phase 10C**.
- Shot/Note dedicated editor styling + selector entries.
- FDX export, PDF pagination, revision colors, locked pages, production drafts,
  dual dialogue, production scene numbering.
- Screenplay-specific Health/Diagnostics detectors and runtime estimation.
- Tab/Enter element cycling and character/scene-heading autocomplete UI
  (helpers exist in `screenplay.py` / `screenplay_blocks.py`; wiring deferred).

## Limitations

Block types are **derived from saved text**, not stored — so export/analysis
reconstruct structure heuristically and a hand-typed novelistic block may be
read as `action`. Durable per-block element storage is the primary 10C
prerequisite. Parsing is intentionally conservative (prefers `action`).
