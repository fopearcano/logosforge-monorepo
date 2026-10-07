# LogosForge — Alpha Scope

Core version: **0.9.0-alpha** · Pro desktop version: **0.1.0** · Status:
**alpha release candidate**.
The Core source of truth is `logosforge.__version__` /
`logosforge.__status__`; the packaged Pro version is recorded in
`pro-desktop/package.json` and its lockfile.

This document is the authoritative scope statement for the Alpha release. It
defines what Alpha includes, what it does not, what is stable vs experimental,
and what is deferred to Beta. Test totals are intentionally not frozen here;
the release workflows and their source-bound evidence are authoritative for a
given candidate.

Companion document: **docs/ALPHA_FREEZE.md** (what may and may not change before
Alpha close).

---

## 1. What Logosforge Alpha includes

A local-first, single-user writing-intelligence system with a SQLite/Python Core
and a packaged React/Electron Pro desktop. The historical PySide6 desktop remains
in the repository, but the native Pro release surface is the Electron shell over
the authenticated loopback API. Both use the same Core and mode-aware authoring
systems:

- **Projects** — create / open / switch / recent, per-project file locks,
  legacy-format compatibility, lifecycle cache clearing.
- **Writing Modes** — Novel / Screenplay / Graphic Novel / Stage Script / Series
  (single source of truth = `Project.narrative_engine`; every section adapts).
- **Manuscript** — scene editor with rich per-scene fields; basic grammar/spell.
- **Outline / Plot / Timeline** — act/chapter/scene structure, plot blocks
  (scene-derived), scene-order timeline.
- **Graph** — four bounded canonical projections, focus neighborhoods, Story
  Gravity/order overlays, and revision-bound Confirm/Hide/Restore review.
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
- **Knowledge Graph** — traceable semantic map across PSYKE/scenes/structure/
  notes/setup-payoff/revision with confidence, provenance, dedicated Pro UI, and
  transactional edge review.
- **Semantic Continuity** — deterministic continuity issues, a dedicated Pro
  panel, traceable Dashboard cards, transactional Defer/Dismiss/Resolve review,
  and a separate Billy → Controlled Apply repair handoff.
- **Dashboard / Decision Radar** — ranked Project Intelligence, Knowledge Graph,
  and Semantic Continuity cards with exact Graph/issue/scene deep links.
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
- No **web/PWA release**. The React/Electron Pro desktop is implemented, but
  remote/LAN serving remains outside the Alpha support boundary.
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
- **Knowledge Graph / Semantic Continuity / Decision Radar** — dedicated Pro
  panels and guarded review flows are implemented; cross-platform packaged
  acceptance for the current production-shell candidate is still incomplete.
  *(B)*
- **Guided Workflows** — the engine and Logos/Assistant surfaces exist; a
  dedicated workflow panel remains deferred. *(B)*
- **FDX export** — experimental/gated. *(B)*
- **Grammar / spelling** — rule-based, no external engine; basic accuracy. *(B)*
- **API** — the versioned HTTP contract and local MCP gateway have broad
  automated coverage, but **only authenticated desktop/localhost mode is in
  Alpha**; LAN/remote exposure is not a supported release mode. *(B)*

## 5. Known limitations

- Plot and Timeline are derived from scene fields, not standalone models.
- Continuity intentionally omits deep-NLP checks (voice drift, knowledge leak,
  object-destroyed-then-reused, lore-rule violation) to avoid hallucinated
  findings; it flags only evidence-backed, deterministic issues.
- Knowledge Graph centrality is plain degree (explainable, not PageRank);
  undefined-term detection is heuristic.
- Guided Workflows are surfaced through the engine and Logos/Assistant rather
  than a dedicated workflow panel.
- Grammar/spell is rule-based.
- Single-user, local-only; no collaboration or remote sync.

## 6. Deferred features (→ Beta)

- A dedicated **Guided Workflows** UI panel and persistent custom Radar filters/
  dismissal controls. Graph, Semantic Continuity, and Decision Radar panels are
  already part of the Pro Alpha.
- Supported **API** `lan` / `remote` transport with required authentication, and
  web/PWA distribution. The React/Electron shared UI itself is implemented.
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

1. Record a **full-suite-green, source-bound** baseline for the release
   candidate, including a Writer QA run with **0 BLOCKER** findings.
2. Run the unchanged production-shell packaged journey on hosted Linux/Xvfb and
   the Intel macOS 12 runner; the current candidate has passed on Windows only.
3. Complete hands-on acceptance of the installer/portable EXE, AppImage, and DMG
   on their supported operating systems before publishing.
4. Keep desktop/localhost as the Alpha API posture. Before any future LAN/remote
   exposure, add the required authentication and threat-model hardening.
5. Preserve the existing safety and data round-trip gates: disabled Connector
   writes and Go McKee stay inert, project lifecycle never cross-writes, and
   export/import and restart recovery lose no user data.
6. A dedicated Guided Workflows panel and richer Plot/Timeline models are Beta
   feature work, not blockers for Alpha stability.
