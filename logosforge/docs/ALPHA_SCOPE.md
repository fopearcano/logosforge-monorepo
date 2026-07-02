# Logosforge — Alpha Scope

Version: **0.9.0-alpha** · Status: **alpha** (feature freeze).
Source of truth: `logosforge.__version__` / `logosforge.__status__` (also
surfaced as `QApplication.applicationVersion()` and recorded in per-project lock
metadata via `cloud_storage`).

This document is the authoritative
scope statement for the Alpha release. It is derived from the Step 1 scope audit
(5,885 tests collected clean; per-subsystem suites green). It defines what Alpha
includes, what it does not, what is stable vs experimental, and what is deferred
to Beta.

Companion document: **docs/ALPHA_FREEZE.md** (what may and may not change before
Alpha close).

---

## 1. What Logosforge Alpha includes

A local-first, single-user writing-intelligence desktop app (PySide6 + SQLite),
with one shared AI backend and a set of mode-aware authoring tools:

- **Projects** — create / open / switch / recent, per-project file locks,
  legacy-format compatibility, lifecycle cache clearing.
- **Writing Modes** — Novel / Screenplay / Graphic Novel / Stage Script / Series
  (single source of truth = `Project.narrative_engine`; every section adapts).
- **Manuscript** — scene editor with rich per-scene fields; basic grammar/spell.
- **Outline / Plot / Timeline** — act/chapter/scene structure, plot blocks
  (scene-derived), scene-order timeline.
- **Graph** — link graph + confirmed Story Links + focus graph view.
- **PSYKE** — characters/places/objects/lore/themes with relations,
  progressions, aliases, and command surface.
- **Notes**.
- **Assistant** — explicit right-panel chat/action assistant over the shared
  provider backend; capped, deterministic context injection.
- **Logos** — inline contextual assistant **layer** (left-panel ON/OFF toggle):
  toolbar + ambient suggestions + diagnostics/health drawers + strategy router,
  scoped to the current section. Preview/confirm only — never auto-applies.
- **Counterpart** — dialogic critic mode (in the Assistant panel).
- **Quantum Outliner** — plotting/outline exploration with lookahead scoring.
- **Connector** — local app-control bridge (read actions on; **write actions
  gated OFF by default**).
- **Go McKee** — optional craft-intelligence plugin (gated OFF by default).
- **Knowledge Graph** *(service)* — traceable semantic map across PSYKE/scenes/
  structure/notes/setup-payoff/revision (read-only; confidence + provenance).
- **Semantic Continuity** *(service)* — deterministic continuity issues +
  rewrite/apply change validation (preview-only).
- **Dashboard / Decision Radar** *(service + basic UI)* — read-only project
  intelligence and ranked decisions.
- **Guided Workflows** *(engine)* — resumable, mode-aware step paths.
- **Rewrite Sandbox / Controlled Apply / Revision Intelligence** — safe,
  confirm-gated change tooling.
- **Export / Import** — Fountain, DOCX, PDF, HTML preview, plain text, project
  data export/import (FDX experimental).
- **Autosave / Versioning** — atomic writes, locks, external-change detection.
- **API** *(desktop/localhost mode)* — thin FastAPI DTO layer over the core.
- **Plugins** — local plugin manager/registry/executor.

## 2. What Logosforge Alpha does NOT include

- No **Phase 10R**, **Director / Showrunner Control Room**, or any new major
  creative system.
- No new **AI agents** and no **autonomous mutation** (nothing rewrites content
  on its own).
- No **cloud collaboration / multi-user / real-time sync** (cloud paths are
  treated as ordinary local folders only).
- No **React / Electron rewrite** (the desktop UI is PySide6; the API exists but
  remote/LAN serving is not in Alpha).
- No **public/remote API serving** by default (desktop/localhost only).
- No second Assistant, second Logos system, or second provider backend.

## 3. Stable systems (Alpha-ready — "A")

Projects · Writing Modes · Manuscript · Outline · Graph · PSYKE · Notes ·
Assistant · Logos · Autosave/Versioning · Export (Fountain/DOCX/PDF/HTML/text).

These are frozen. Change only to fix a confirmed regression, with tests.

## 4. Experimental / limited systems (Usable with limitations — "B"/"C")

- **Plot / Timeline** — scene-derived models (no separate rich Plot/Timeline
  tables); adequate for Alpha. *(B)*
- **Counterpart** — works; thin automated coverage. *(B)*
- **Connector** — write actions gated OFF by default; only read actions are on
  the default path. *(B)*
- **Go McKee** — optional plugin, OFF by default. *(B)*
- **Quantum Outliner** — stable; cache-invalidation paths are the main risk. *(B)*
- **Knowledge Graph / Semantic Continuity / Decision Radar / Guided Workflows** —
  services and Logos/Assistant surfaces are complete; **dedicated UI panels are
  deferred to Beta**. *(B)*
- **FDX export** — experimental/gated. *(B)*
- **Grammar / spelling** — rule-based, no external engine; basic accuracy. *(B)*
- **API** — functional thin layer but **only desktop/localhost mode is in Alpha**;
  HTTP-layer test coverage is light. *(C)*

## 5. Known limitations

- Plot and Timeline are derived from scene fields, not standalone models.
- Continuity intentionally omits deep-NLP checks (voice drift, knowledge leak,
  object-destroyed-then-reused, lore-rule violation) to avoid hallucinated
  findings; it flags only evidence-backed, deterministic issues.
- Knowledge Graph centrality is plain degree (explainable, not PageRank);
  undefined-term detection is heuristic.
- Several intelligence services (Knowledge Graph, Continuity, Radar, Workflows)
  are surfaced via Logos/Assistant/services rather than dedicated UI panels.
- Grammar/spell is rule-based.
- Single-user, local-only; no collaboration or remote sync.

## 6. Deferred features (→ Beta)

- Dedicated **UI panels** for Knowledge Graph, Semantic Continuity, Decision
  Radar, and Guided Workflows.
- **API** `lan` / `remote` transport (with required auth) and the React/Electron
  shared UI.
- Richer **Plot** and **Timeline** models.
- **FDX** export hardening.
- Deeper **Counterpart**, **Connector** write-action breadth, **Go McKee**
  integration.
- Opt-in, user-confirmed **semantic continuity** checks.

## 7. Data-safety priorities

Highest priority, lowest tolerance for change:

- **Autosave / Versioning** — atomic temp-write + fsync + `os.replace`; never
  partially overwrite a project.
- **Project lifecycle** — switch/lock/recent must never leak or cross-write
  another project's data; per-project caches cleared on switch.
- **DB migrations** — additive/idempotent (`SQLModel.metadata.create_all`); old
  projects must open unchanged.
- **Export/Import round-trips** — no silent content loss.
- Rule: any change touching these requires tests and must **stop and report** if
  it risks project data.

## 8. UI / UX priorities

- Stable left-panel navigation: groups, labels, order, collapse/expand, and the
  consistent flat monochrome icon set (theme-colored: muted gray idle, accent
  when active) across Dark / Green / Warm.
- Logos is an **inline toggle**, not a central section; it never takes over the
  workspace and never steals the active-section highlight.
- Compact, 13-inch-friendly surfaces; no oversized modals; no focus stealing;
  no blank windows; project switch clears stale UI state.

## 9. AI / provider priorities

- **One shared provider backend** (`providers.build_active_provider` /
  `assistant.chat_completion`). No second backend, no duplicated provider
  settings.
- Assistant context is **gated, capped, deterministic**, current-project-only,
  with no LLM call during context assembly and no cross-project leak.
- All AI-driven mutations are **preview/confirm** via Controlled Apply / Rewrite
  Sandbox — never autonomous.

## 10. Export / import priorities

- Reliable, lossless: Fountain (screenplay), DOCX, PDF, HTML preview, plain text,
  and project data export/import.
- Roundtrip integrity (no duplicated/dropped headings or content).
- FDX remains experimental and clearly labeled.

## 11. Beta blockers (must be resolved before Beta scope expands)

1. Confirm a **full-suite green** baseline is recorded after the Alpha-close UI
   changes (Logos inline toggle + sidebar icons).
2. **API**: decide Alpha posture (ship desktop/localhost only) and add HTTP-layer
   coverage before exposing `lan`/`remote`; enforce auth for `remote`.
3. **Safety-gate tests**: prove Connector writes blocked when disabled, API
   desktop mode rejects non-localhost origins, Go McKee inert when disabled.
4. **Data-safety round-trip tests**: project create→edit→autosave→version→
   switch→reopen with no loss; export/import roundtrip.
5. UI panels for the deferred intelligence services (Beta feature work, not a
   blocker for Alpha *stability*).
