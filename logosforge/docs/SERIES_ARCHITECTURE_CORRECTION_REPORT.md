# Series Mode — Architecture Correction Report

Status: **architecture/report gate — no production code changed.**
Decision: **B — keep Series enabled for Alpha but mark it EXPERIMENTAL; the full
Season → Episode → Act → Chapter → Scene hierarchy is a post-Alpha structural
correction (Option B).**

This report answers the gate questions honestly. The current Series mode is useful
for *writing* but its Season/Episode model is the Alpha shortcut and is misleading
as a hierarchy. The correct model is achievable post-Alpha at moderate (not heroic)
cost, because the Season/Episode storage **already exists, dormant**.

---

## 1. Current state (audit)

### 1.1 Canonical structure — 3 levels, scene-derived labels
There are **no Act or Chapter tables**. A project's structure is derived from
`Scene` rows: `Scene.act` and `Scene.chapter` are **string labels** and
`Scene.sort_order` is the single global order (`story_structure.py`). `Scene` has
**no `episode_id` / `season_id`** (verified). So the canonical hierarchy is exactly
three levels:

```
Project → Act(label) → Chapter(label) → Scene(row)
```

Every section (Outline, Manuscript, Timeline, Notes, Export, Assistant, Logos)
reads order/numbering from `story_structure` (`canonical_scene_order`,
`compute_structural_numbers`). `test_structure_invariant.py` enforces "every Scene
under a Chapter, every Chapter under an Act."

### 1.2 Current Series mode = the Alpha shortcut (flat)
The universal-Manuscript Series system (Phases 1–8 + the new Series Navigator) maps:

| Series concept | Canonical node | Where |
|----------------|----------------|-------|
| **Season / Arc** | **Act** (label) | `series_navigator_view` ("Season / Arc {n} — {act}"), `series_pipeline.SEASON_KEY` keyed by **Act name** |
| **Episode** | **Chapter** (label) | `series_blocks.episode_label`, `series_navigator_view` ("Episode {n.m}"), `series_pipeline.EPISODE_KEY` keyed by **Chapter name** |
| **Scene** | **Scene** (row) | `series_blocks` body = `Scene.content` (teleplay Pages? no — teleplay blocks) |

So **"2 Acts in Outline → 2 Seasons in the Navigator"** is exactly this shortcut
leaking: an Act *is* a Season here. This is the reported defect — it is flat
(Season → Episode → Scene) and **cannot represent Episode-internal Acts →
Chapters**, and the Navigator is read-only with no Season/Episode management.

### 1.3 Series planning models (settings-backed, name-keyed)
- `series_pipeline.SeasonArcPlan` — stored in `settings["series_season_plans"]`,
  **keyed by Act name**. Fields: premise, arc_question, episode_progression,
  character_arcs, recurring_motifs, setup_payoff_notes, cliffhanger_reveal_notes.
- `series_pipeline.EpisodeBeatPlan` — `settings["series_episode_plans"]`, **keyed
  by Chapter name**. Fields: a_story / b_story / c_story, teaser_or_cold_open,
  act_breaks, climax, tag_or_button, etc.
- **A/B/C stories** exist only as those three text fields on the Episode Beat Plan.
  There is **no per-scene thread-assignment metadata** — the Navigator shows A/B/C
  as read-only buckets.

### 1.4 Manuscript / export
One `WritingCoreView`; a Series scene body *is* `Scene.content` (teleplay blocks via
`series_blocks`). `series_blocks.export_project_markdown` walks
`canonical_scene_order` (Act → Chapter → Scene). All Series tools
(`series_diagnostics/reflection/rewrite/continuity/dashboard`) operate on the
per-scene body + the name-keyed plans.

### 1.5 A dormant Season/Episode storage layer ALREADY EXISTS (key finding)
`models/models.py` defines real tables — **predating** the universal-Manuscript
Series work and **not used by it**:

- `Season(project_id, season_number, title, summary, season_arc, central_question,
  finale_payoff, status, order_index)`
- `Episode(season_id → Season, project_id, episode_number, title, logline, summary,
  episode_engine, teaser, act_breaks, cliffhanger, status,
  estimated_runtime_minutes, order_index)`
- `SeriesArc(...)` (arcs spanning episodes; links PSYKE entries)

…with full CRUD in `db/database.py` (`create_season`, `get_seasons`,
`create_episode`, `get_episodes_for_season`, `get_episodes`, `update_season/episode`,
`create_episode_plotline`, …). These belong to the **legacy series surface**
(`series_plot.py`, `series_review.py`, `psyke_series.py`). **Crucially:**
`Episode` has **no link to Scenes** (Scene has no `episode_id`), and the
universal-Manuscript Series modules never import these tables.

### 1.6 Code that assumes the 3-level invariant
`story_structure` (whole module), `test_structure_invariant`, Outline (`plan_view`),
Manuscript (`writing_core_view`), Timeline canonical ordering, Notes
(`story_structure.note_link_label` with kinds act/chapter/scene), and every
mode's export all assume Act (top) → Chapter → Scene. Any deeper hierarchy must
**not** change this for Novel/Screenplay/Graphic Novel/Stage Script.

---

## 2. Target product model

```
Series Project
  └─ Season / Arc
       └─ Episode
            └─ Act
                 └─ Chapter
                      └─ Scene
```

- **Seasons contain Episodes**; **Episodes own their own Act → Chapter → Scene
  outline**; A/B/C plots are episode-level threads scenes can be assigned to.
- **Series Outline** (macro): Seasons + Episodes with season/episode summaries &
  plans. **Episode Outline** (micro): the selected Episode's Act → Chapter → Scene.
- The Series Navigator is the macro navigator + manager; the Outline section shows
  the **selected Episode's** Act → Chapter → Scene.

This is **5 levels**; the canonical model today is **3**. That gap is the whole
problem.

---

## 3. Architecture options

### Option A — Keep Act → Chapter → Scene only (today's shortcut)
Act = Season, Chapter = Episode, Scene = Scene; episode-internal acts/chapters
simulated in scene metadata or planning payloads.

| Dimension | Assessment |
|---|---|
| Implementation complexity | **Very low** (already shipped) |
| Data-migration risk | **None** |
| Impact on other modes | None |
| Timeline / Notes / PSYKE | Unchanged |
| Export | Unchanged |
| Tests | None new |
| Pre-Alpha suitability | Functional but **conceptually wrong**; misleading ("2 Acts = 2 Seasons"); no episode-internal Act→Chapter→Scene; no Season/Episode management |

**Verdict:** acceptable only as an honestly-labeled, *experimental* stopgap.

### Option B — Series wrapper entities (RECOMMENDED, post-Alpha)
Use the **already-existing** `Season`/`Episode`(/`SeriesArc`) tables; add the one
missing link so Episodes own scenes, and scope the existing Act → Chapter → Scene
**inside each Episode**:

- Add `Scene.episode_id` (nullable FK → `Episode`). **`NULL` = today's behavior**
  (non-Series and legacy Series unchanged → fully back-compatible).
- For a Series project, the canonical tree becomes **per-Episode**: an Episode's
  scenes (those with that `episode_id`) form their own Act → Chapter → Scene using
  the existing scene-derived `act`/`chapter` labels — i.e., `story_structure`
  gains an *episode-scoped* variant for Series. Other modes keep the project-wide
  tree untouched.
- Season → Episode already exists via `Episode.season_id`. A/B/C: optionally add a
  light `Scene.plot_thread` ("A"/"B"/"C"/"") for real per-scene assignment, or
  keep deriving from the Episode Beat Plan.
- Re-key the Series plans from Act/Chapter **name** to **Season/Episode id** (or
  keep name-keyed during transition).

```
Series → Season(table) → Episode(table) → [Scene.episode_id] → Act/Chapter(labels) → Scene
```

| Dimension | Assessment |
|---|---|
| Implementation complexity | **Moderate** (tables + CRUD exist; main work = `Scene.episode_id`, an episode-scoped `story_structure`, Series-mode Outline context + Navigator management, plan re-keying) |
| Data-migration risk | **Low–moderate, and opt-in**: `episode_id` NULL is safe by default; a one-time, **confirmed** converter maps existing shortcut Series (each Act→a Season, each Chapter→an Episode, scenes→`episode_id`). No auto-migration. |
| Impact on other modes | **None** if Series-gated (`episode_id` NULL elsewhere; `story_structure` per-episode path only for Series) |
| Timeline / Notes / PSYKE | Timeline/Notes still link to **Scene** ids (unchanged); add Season/Episode link *kinds* later. PSYKE unchanged (SeriesArc already links PSYKE). |
| Export | Series export gains a Season → Episode → (Act→Chapter→Scene) traversal; other modes unchanged |
| Tests | New: episode-scoped structure, Navigator CRUD, migration, isolation, export traversal; existing invariant tests stay valid (NULL `episode_id` path) |
| Pre-Alpha suitability | **No** (storage change) — correct **post-Alpha** target |

**Verdict:** the right model, made tractable by the dormant tables; **post-Alpha.**

### Option C — Generic hierarchical outline nodes
Replace fixed Act/Chapter/Scene with `OutlineNode(type ∈ {season, episode, act,
chapter, scene}, parent_id)`.

| Dimension | Assessment |
|---|---|
| Implementation complexity | **Very high** (re-platform the whole structure model) |
| Data-migration risk | **High** (every project migrates) |
| Impact on other modes | **All modes** rewritten |
| Timeline / Notes / PSYKE / Export | All re-pointed to node ids |
| Tests | Massive |
| Pre-Alpha suitability | **No** (and high risk even post-Alpha) |

**Verdict:** elegant long-term north star, but **out of scope** for the Alpha and
the immediate correction. Option B does not preclude evolving toward C later.

---

## 4. Recommended approach

**Post-Alpha: implement Option B.** Keep Act → Chapter → Scene for all other modes;
give Series real `Season`/`Episode` entities (reuse the existing tables) with each
Episode owning its own Act → Chapter → Scene via a nullable `Scene.episode_id` and
an episode-scoped `story_structure`. Convert existing shortcut Series projects only
via an explicit, confirmed one-time wizard (NULL `episode_id` keeps them working
until then).

**Alpha-safe (now, separate small follow-up — not this gate):**
1. **Mark Series mode EXPERIMENTAL** in the mode picker / docs.
2. **Correct the Navigator's misleading framing** so it does not present Outline
   Acts as "Seasons" as if Season/Episode management exists — either label honestly
   as the current Act → Chapter → Scene (with a "full Season/Episode hierarchy
   coming" note) or clearly badge the Season/Episode labels as a provisional view.
   Do **not** silently keep implying "2 Acts = 2 Seasons" is real season modeling.
3. **Document** the limitation (done in this report; mirror into
   `KNOWN_LIMITATIONS_ALPHA.md`).

This is honest: the Series *writing* tools (teleplay body, plans, checks,
reflection, controlled rewrite, continuity, dashboard, navigation) genuinely work
and add value; only the Season/Episode *hierarchy* is provisional.

---

## 5. Series Navigator — target behavior (any storage option)

- **Season:** create / rename / delete (confirm) / move up-down / open overview /
  generate-edit Season-Arc Plan.
- **Episode:** create inside Season / rename / delete (confirm) / move within
  Season / move to another Season (safe) / open Episode Outline / generate-edit
  Episode Beat Plan.
- **Episode Outline:** create Act / Chapter / Scene inside the Episode; move
  Act/Chapter/Scene; open Scene in Manuscript; open linked Timeline event.
- **A/B/C Plots:** view threads from the Episode Beat Plan; assign a Scene to a
  thread **only if** explicit metadata exists/is added safely; filter by thread;
  show unassigned scenes; never invent links silently.

Today's Navigator is **read-only** and lacks all create/rename/delete/move actions
— another reason the current state is "experimental," and these actions are only
fully meaningful once Option B provides real Season/Episode entities.

---

## 6. Outline integration — target & answers

- **Series Outline (macro):** Seasons + Episodes with season/episode summaries and
  plans — surfaced through the **Series Navigator**.
- **Episode Outline (micro):** the existing **Outline** section shows the
  **selected Episode's** Act → Chapter → Scene.
- *Does Outline switch context per selected Episode?* — **Yes (target):** Series
  Navigator selects an Episode → Outline renders that Episode's Act→Chapter→Scene.
- *Navigator vs Outline?* — Navigator = macro (Season/Episode) manager; Outline =
  micro (Act/Chapter/Scene) editor for the selected Episode.
- *Timeline links?* — keep linking to **Scene ids** (stable across the change);
  Season/Episode link *kinds* can be added later.
- *Notes links?* — Scene/Act/Chapter links continue via `story_structure`; add
  Season/Episode link kinds in Option B.
- *Exports?* — Series export traverses Season → Episode → (Act → Chapter → Scene);
  other modes unchanged.

---

## 7. Storage changes & migration risks

**Option B storage (post-Alpha):**
- Reuse `Season`/`Episode`/`SeriesArc` tables (exist). Add **`Scene.episode_id`**
  (nullable FK). Optional `Scene.plot_thread` for real A/B/C assignment.
- Episode-scoped `story_structure` for Series; project-wide for other modes.
- Re-key `series_season_plans`/`series_episode_plans` from name → id.

**Risks & mitigations:**
- *Breaking the 3-level invariant for other modes* → gate every change on Series;
  `episode_id NULL` ⇒ identical behavior; existing invariant tests must stay green.
- *Existing shortcut Series projects* → never auto-migrate; ship a confirmed
  converter; until run, they render via the legacy/NULL path.
- *Plan re-keying data loss* → migrate name→id with a name fallback; keep a backup
  export.
- *Timeline/Notes drift* → keep Scene-id links canonical; add Season/Episode kinds
  additively.

---

## 8. Tests needed (for Option B, post-Alpha)
- Episode-scoped structure: each Episode has its own Act → Chapter → Scene; moving
  within an Episode doesn't affect siblings.
- Other modes unaffected (NULL `episode_id` ⇒ project-wide tree unchanged); the
  `test_structure_invariant` suite stays green.
- Navigator CRUD: create/rename/delete/move Season & Episode; create Act/Chapter/
  Scene in an Episode; no mutation on navigation.
- A/B/C assignment (if added): assign/filter/unassigned; no silent links.
- Migration: shortcut Series → wrapper entities is confirmed, reversible-by-backup,
  lossless; un-migrated projects keep working.
- Export traversal Season→Episode→Act→Chapter→Scene; isolation; privacy.

---

## 9. Decision classification

**Final: B — Architecture is clear; mark Series EXPERIMENTAL for Alpha.**

- §7 Alpha decision: keep Series **enabled but experimental** (≈ A/B blend) — its
  writing tools work; the Season/Episode hierarchy is provisional and must be
  labeled honestly. The **full** Season → Episode → Act → Chapter → Scene
  correction is **post-Alpha** (Option B), which is also true in the sense of §7-C.
- It is **not** D (hide): the Series writing system is substantial and tested;
  hiding it discards real value. Experimental-labeling + honest Navigator framing
  is proportionate and honest.

**Should Series, for Alpha:** *remain enabled but marked experimental* — with the
Navigator's Season/Episode framing corrected so it does not overpromise, and the
limitation documented. Implement Option B post-Alpha.

### Next implementation prompt (recommended)
A small, **Alpha-safe, non-storage** follow-up: (1) mark Series mode experimental
in the picker/docs; (2) relabel the Series Navigator so it stops presenting Outline
Acts as managed "Seasons" (honest framing + "full hierarchy coming"); (3) mirror
this limitation into `KNOWN_LIMITATIONS_ALPHA.md` / `ALPHA_RC_STATUS.md`. Then, as a
separate **post-Alpha** track, implement **Option B** behind a Series gate
(`Scene.episode_id` + episode-scoped `story_structure` + Navigator CRUD + confirmed
migration), reusing the existing `Season`/`Episode` tables.

## 10. Phase 1 — IMPLEMENTED (Option B foundation)

Option B is now landed as the **Series hierarchy foundation** (Series-only,
additive, back-compatible). What shipped:

- **`Scene.episode_id`** — a nullable FK column (`models.py` +
  `db/database.py::_migrate` ALTER-TABLE-ADD-COLUMN). `NULL` everywhere preserves
  prior behaviour (all non-Series modes and pre-migration Series), so the change
  is purely additive. `create_scene` accepts `episode_id`; new helpers
  `set_scene_episode` / `get_scenes_for_episode` / `get_unassigned_series_scenes`.
- **Season/Episode are now used as real storage.** Added the missing CRUD:
  `delete_season` / `delete_episode` (cascade episodes; **unlink** scenes to NULL
  rather than delete them — bodies are never destroyed), `reorder_seasons` /
  `reorder_episodes`.
- **`logosforge/series_structure.py`** — the episode-scoped data layer:
  detection (`is_series_project` / `has_series_hierarchy` / `is_legacy_series`),
  Season/Episode CRUD wrappers + move, scene↔episode linking, episode-scoped
  Act→Chapter→Scene tree (reuses the canonical grouping, filtered by
  `episode_id`), `build_series_tree`, readable `scene_series_path`,
  `series_stats`, a **confirmed, non-destructive** `migrate_legacy_series`
  (old Act→Season title, old Chapter→Episode title, link scenes; bodies/labels/
  order untouched), and `export_series_markdown` (structure + bodies only — never
  settings/API keys).
- **Rebuilt `ui/series_navigator_view.py`** — renders **two ways**: *hierarchy
  mode* (real Season→Episode→Act→Chapter→Scene with full CRUD: create/rename/
  delete/move Seasons, Episodes, internal Acts/Chapters, Scenes; move a scene
  between Episodes; A/B/C buckets per episode; an "Unassigned Scenes" bucket) and
  *legacy mode* (the original read-only view + a one-click confirmed **Convert to
  Season/Episode**). A trivial single Act/Chapter (e.g. a migration echo) is
  collapsed for readability.
- **Mode lock** now counts Season/Episode rows as meaningful content.

**Deliberately deferred to a later phase (documented):** the **global** Outline /
Manuscript / Timeline remain episode-agnostic (they still read the canonical flat
`story_structure`); the **Series Navigator is the canonical Season/Episode
structural surface**. Season/Episode-aware global Outline context-switching,
durable relation links, and per-scene A/B/C thread assignment are future work.

**Verification:** `tests/test_series_hierarchy.py` (**70 passed**); the legacy
`tests/test_series_navigator.py` stays green (**26 passed**); broad cross-mode +
gate sweep clean (only pre-existing optional-lib PDF/DOCX skips fail in CI
without `reportlab`/`python-docx`).
