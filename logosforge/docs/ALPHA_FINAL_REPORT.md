# Logosforge — Alpha Final Report (0.9.0-alpha)

Final closure assessment after stabilization Steps 1–22.

## Current classification

**B) Alpha Closed with documented limitations** — ready for **private writing
use**. Core authoring, AI, data-safety, export and lifecycle are stable and
tested; several intelligence systems ship as services without dedicated UI, and a
few formats are experimental (all documented).

## Implemented features

- **Projects & lifecycle** — create/open/switch/recent, per-project locks,
  additive migrations, full stale-state clearing on switch.
- **Writing Modes** — Novel / Screenplay / Graphic Novel / Stage Script / Series
  (single source of truth; every section + AI adapts).
- **Manuscript** — continuous scene editor, focus mode, format-aware blocks,
  font/size/grammar controls, debounced autosave.
- **Structure** — Outline (AI, confirmed), Multi-Plot, Timeline, act/beat/tag
  analysis, Story Grid, Structure view.
- **PSYKE** story bible — characters/places/objects/lore/themes, relations,
  progressions, console search.
- **Notes**, **Graph** (focus graph + confirmed links).
- **Assistant** — chat, critique, inline edit, Counterpart, Quantum outliner,
  capped context, propose-then-confirm actions, language-aware.
- **Logos** — inline contextual ON/OFF layer (toolbar, suggestions, diagnostics,
  health, strategy).
- **Connector** — local app-control bridge (writes off by default).
- **Intelligence services** — Project Intelligence / Decision Radar, Narrative
  Knowledge Graph, Semantic Continuity, Guided Workflows, Rewrite Sandbox,
  Controlled Apply, Revision Intelligence (services + Logos/Assistant surfaces).
- **Export/Import** — Markdown/TXT/Fountain/FDX/HTML/JSON/CSV + PDF/DOCX (optional
  libs); story-elements / PSYKE / full-project; non-destructive import.
- **Autosave / Versioning / Backup-Restore** — atomic writes, per-project
  snapshots, pre-restore safety snapshot.
- **HTTP API** — FastAPI DTO layer (desktop/localhost in alpha).

## Stable systems

Projects · Project switching · Writing Modes · Manuscript · Outline · Graph ·
PSYKE · Notes · Assistant · Logos · Autosave/Versioning · Backup/Restore ·
Export (text formats) · Provider settings · Timeout handling · Documentation.

## Experimental systems

PDF/DOCX export (optional deps) · FDX (menu = standard XML; advanced path
experimental) · HTML (preview-grade) · API LAN/remote modes · Go McKee plugin
(off by default) · Connector write actions (off by default).

## Risky systems (touch only for confirmed regressions, with tests)

Autosave · Versioning · Project switch/lock/lifecycle · DB models/migrations ·
shared provider backend (`build_active_provider`) · Assistant context policy.
These carry the highest blast radius; frozen for alpha.

## Known limitations

Plot/Timeline scene-derived; grammar rule-based; Knowledge-Graph/Continuity/
Decision-Radar/Workflow **UI deferred**; single-user local-only; restore creates
a new project; API keys plaintext in local settings (never exported). Full list:
[KNOWN_LIMITATIONS_ALPHA.md](KNOWN_LIMITATIONS_ALPHA.md).

## Tests run

- **Suite size:** ~6008 tests (Qt offscreen).
- **Full gate run:** `6005 passed, 2 failed, 1 skipped` (≈63 min). Of the two
  failures:
  - `test_outline_apply_scenes::test_confirm_dialog_is_resizable_with_pinned_buttons`
    — a **regression introduced during the UI-hardening step** (Outline-confirm
    dialog minimum raised too far). **Fixed** (reverted to a small minimum that
    fits a 13-inch screen); verified green.
  - `test_logos_integration::test_toolbar_run_action_renders_result_with_injected_chat`
    — **passes in isolation and in combined runs**; a pre-existing
    full-suite-ordering flake (a Qt signal `_wait` after ~6000 tests in one
    process). Not a regression; code unchanged.
- **Safety-critical subset verified green:** 214 passed, **0 skipped** —
  versioning/backup, autosave, project lifecycle + switch + state reset, writing-
  mode integrity, provider/language, export, UI layout, AI-UI, manuscript
  experience, refresh propagation, PSYKE console, version constant.
- **Post-fix expectation:** 6007 passed / 1 skipped, modulo the one known
  full-suite-ordering flake above (which is order-dependent, not a code defect).

## Tests skipped

- `test_api.py` — `pytest.importorskip("fastapi")` (skips only if FastAPI is not
  installed; it is in `requirements.txt`, so it runs).
- `test_graph_polish.py`, `test_story_gravity.py` — two **conditional**
  `pytest.skip` guards that trigger only when offscreen layout produces no
  visible graph nodes (environment-dependent, 0–1 tests). No `xfail` markers.

## Known flaky (full-suite ordering)

- `test_logos_integration::test_toolbar_run_action_renders_result_with_injected_chat`
  passes alone but can fail when run after the whole suite in one process
  (accumulated Qt state / signal-wait timing). Re-run it in isolation to confirm.

## Suggested version tag

**`v0.9.0-alpha.1`** (do **not** create the tag — declaration only).

## Next milestone recommendation

**Beta planning, not new alpha features.** First beta targets (in order):
1. UI panels for the deferred intelligence services (Knowledge Graph, Continuity,
   Decision Radar, Guided Workflows).
2. API LAN/remote hardening + auth; the shared React/Electron UI.
3. Richer Plot/Timeline models; opt-in semantic-continuity checks.

Keep the alpha freeze (docs/ALPHA_FREEZE.md) until a beta scope is agreed.
