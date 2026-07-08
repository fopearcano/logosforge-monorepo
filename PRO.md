# PRO.md — start-here prompt for a Pro / Studio session

**Paste this into a fresh Pro-focused session.** It orients you and hands you the current pending task. You are working on the **Pro / Studio** product line only.

## Who owns what (read first)

- **Pro tier** = the power-user writing workstation. Code lives in:
  - `pro-shared-ui/` — the shared React UI (consumed by `pro-desktop` + `pro-web`). Platform-neutral; no Electron/Node/browser-host code, no Whiteboard imports. See `pro-shared-ui/CLAUDE.md`.
  - `pro-desktop/` — the Electron app shell.
  - `logosforge/` — the Python **core**; behaviour lives here and is reached only through its API. No React/UI/Electron in the core. See `logosforge/CLAUDE.md`.
  - `logosforge-ui-contracts/` — the shared type/event/command contracts. Cascade: `core → ui-contracts → pro-shared-ui → apps`.
- **Whiteboard tier** (`whiteboard-desktop/`) is a **separate product line — do NOT edit it.** Pro and Whiteboard never share UI.

## The task: finish the Whiteboard → Pro migration bridge (`.lfbundle`)

Writers draft in Whiteboard (Free) and "graduate" a project into Pro via a one-click **`.lfbundle`** export → Pro's **⇩ IMPORT PROJECT** import (`pro-shared-ui/src/adapters/projectBundle.ts`). Status:

- **Phase 1 — DONE & shipped:** manuscript (blocks → scenes) + PSYKE bible. See `PRO_IMPORT_BUNDLE_PROMPT.md`.
- **Phase 2 — DONE & shipped:** manual outline (topological recreate, metadata folded into description) + comments **deferred** (Pro has no inline-comments subsystem yet). See `PRO_IMPORT_BUNDLE_PHASE2_PROMPT.md`.
- **Phase 3 — PENDING (this is your task):** reconstruct the new **outline ↔ manuscript "hard link"** that Whiteboard now records. Each bundle outline node may carry `link: { blockIndex, quote }`; the bundle already ships it losslessly (no format bump). **Read `PRO_IMPORT_BUNDLE_PHASE3_PROMPT.md` and implement it** — it has the full source shape, the `block_index → scene` mapping (the one small sanctioned core change), three honest target options (full scene link / lossy description / defer), the import wiring, and acceptance criteria.

## Ground rules
- Stay in the Pro tier. Do NOT touch `whiteboard-desktop/`. The `.lfbundle` format is a fixed contract owned by the Whiteboard exporter — read it, don't redefine it, don't bump its `version`.
- Any core/data-shape need starts in `logosforge` + `logosforge-ui-contracts`, then cascades to `pro-shared-ui`. Prefer client-side orchestration over existing endpoints where possible.
- Verify against a **real** `.lfbundle` exported from the live Whiteboard app (File → Export → Export Project) that actually contains linked outline nodes.

## Reference docs in this repo
- `PRO_IMPORT_BUNDLE_PROMPT.md` — Phase 1 (bundle format + manuscript/PSYKE import).
- `PRO_IMPORT_BUNDLE_PHASE2_PROMPT.md` — Phase 2 (outline + comments decision).
- `PRO_IMPORT_BUNDLE_PHASE3_PROMPT.md` — **Phase 3 (your task).**
- `PRO_COMMENTS_IMPLEMENTATION_PROMPT.md` — the (separate) Pro inline-comments subsystem, if/when comments migration is revisited.
