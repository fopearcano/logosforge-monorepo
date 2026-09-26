# PRO.md — start-here prompt for a Pro / Studio session

**Paste this into a fresh Pro-focused session.** It orients you to the current implementation state. You are working on the **Pro / Studio** product line only.

## Who owns what (read first)

- **Pro tier** = the power-user writing workstation. Code lives in:
  - `pro-shared-ui/` — the shared React UI (consumed by `pro-desktop` + `pro-web`). Platform-neutral; no Electron/Node/browser-host code, no Whiteboard imports. See `pro-shared-ui/CLAUDE.md`.
  - `pro-desktop/` — the Electron app shell.
  - `logosforge/` — the Python **core**; behaviour lives here and is reached only through its API. No React/UI/Electron in the core. See `logosforge/CLAUDE.md`.
  - `logosforge-ui-contracts/` — the shared type/event/command contracts. Cascade: `core → ui-contracts → pro-shared-ui → apps`.
- **Whiteboard tier** (`whiteboard-desktop/`) is a **separate product line — do NOT edit it.** Pro and Whiteboard never share UI.

## Whiteboard → Pro migration bridge (`.lfbundle`) status

Writers draft in Whiteboard (Free) and "graduate" a project into Pro via a one-click **`.lfbundle`** export → Pro's **⇩ IMPORT PROJECT** import (`pro-shared-ui/src/adapters/projectBundle.ts`). Status:

- **Phase 1 — DONE & shipped:** manuscript (blocks → scenes) + PSYKE bible + preservation of Whiteboard-only document settings in the new Pro project's settings store. See `PRO_IMPORT_BUNDLE_PROMPT.md`.
- **Phase 2 — DONE & shipped:** manual outline (topological recreate, writer summary preserved in description, metadata appended in a labelled line) + comments **deferred at that milestone** because Pro did not yet have an inline-comments subsystem. Partial/ambiguous rows are explicitly counted in the import report. See `PRO_IMPORT_BUNDLE_PHASE2_PROMPT.md`.
- **Phase 3 — DONE & shipped:** Whiteboard `link: { blockIndex, quote, blockId? }` anchors resolve through `scene_ids_by_block` and import as Pro outline `scene_id` hard links, with quote validation and explicit skipped-link counts. `blockId` is an additive Whiteboard stability hint; Pro remains compatible by resolving the required `blockIndex + quote`. `PRO_IMPORT_BUNDLE_PHASE3_PROMPT.md` is retained as the implementation record.
- **Phase 4 — DONE:** PSYKE relationships and progression beats import through source→destination entry ID remapping. Progression scene anchors are restored only on a unique scene-title match; unresolved anchors remain safely unlinked and are reported. Whiteboard added those collections without changing the additive bundle version `1.0` contract.
- **Phase 5A — DONE:** Whiteboard inline-comment threads import into a first-class Pro/core comments store. The core translates Whiteboard block spans to UTF-16 offsets in destination scene titles/content during the authoritative manuscript segmentation pass, preserves replies, resolution state, timestamps, source provenance, and cross-field/cross-scene ranges, and reports any thread whose anchor cannot be mapped safely.
- **Phase 5B — DONE:** selecting scene-title or prose text can create a native Pro comment; dragging a prose selection into another scene creates one ordered cross-scene range even though Chromium isolates its editable roots. Stored ranges render as persistent marks and open an anchored thread popover; the Comments panel adds replies, comment-body editing, reply/thread deletion, Resolve/Reopen, a remembered ALL/OPEN filter shared with manuscript marks, and Markdown export. `Alt+Up/Down` cycles open anchored threads and `Ctrl/Cmd+Shift+C` opens Comments. A reply containing `@assistant` or `@counterpart` requests a project-aware AI reply and stores it in the thread. The UTF-16 quote/context anchor engine relocates edits across fields/scenes only from settled live text, persists safe reanchors, and removes a thread only after its quote and context are genuinely gone.
- **Phase 5C — DONE:** the Pro MCP gateway now exposes comments within its 38 named tools. Agents can page/filter full threads with `logosforge_list_comments`, search comment text, inspect bounded comment summaries in project snapshots, and propose an `MCP assistant` reply or Resolve/Reopen transition. Comment apply is bound to the exact thread revision and rechecked atomically with the database mutation, so any intervening root/reply/resolution/anchor/delete change rejects stale work. Comment text is explicitly user-authored data, never tool instructions; anchored creation, anchor/root-body edits, and thread/reply deletion remain UI-only.
- **Phase 5D — DONE locally, pending remote CI:** the required packaged-Windows gate now builds both native Pro sidecars from a clean checkout, verifies the bundled MCP companion, and runs frozen plus installed-app MCP smokes. The installed smoke applies a revision-guarded `MCP assistant` reply, proves stale sibling proposals cannot mutate the thread, applies a fresh Resolve proposal, and rejects proposal replay. Its optional Codex subprocess remains read-only and does not invoke a LogosForge provider.

## Ground rules
- Stay in the Pro tier. Do NOT touch `whiteboard-desktop/`. The `.lfbundle` format is a fixed contract owned by the Whiteboard exporter — read it, don't redefine it, don't bump its `version`.
- Any core/data-shape need starts in `logosforge` + `logosforge-ui-contracts`, then cascades to `pro-shared-ui`. Prefer client-side orchestration over existing endpoints where possible.
- Verify against a **real** `.lfbundle` exported from the live Whiteboard app (File → Export → Export Project) that actually contains linked outline nodes.

## Reference docs in this repo
- `PRO_IMPORT_BUNDLE_PROMPT.md` — Phase 1 (bundle format + manuscript/PSYKE import).
- `PRO_IMPORT_BUNDLE_PHASE2_PROMPT.md` — Phase 2 (outline + comments decision).
- `PRO_IMPORT_BUNDLE_PHASE3_PROMPT.md` — Phase 3 implementation record (completed).
- `PRO_COMMENTS_IMPLEMENTATION_PROMPT.md` — the full Comments design and implementation record for Phases 5A–5B.
