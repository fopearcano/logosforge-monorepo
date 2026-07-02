# Implement the full Comments system in LogosForge **Pro**

You are working in the local monorepo `C:\Users\charlemagne\Desktop\Logosforge Alphatest\`.
Your job: build the **Comments / inline-annotation system** into **LogosForge Pro**, matching the
complete feature set already shipped in the **Whiteboard** product — but adapted to Pro's
architecture and the Pro "Studio" UI. The Whiteboard implementation is your reference spec;
**do not blindly copy it** — Pro's editor, storage, and AI are different (see Part 3).

Touch **only the Pro tree** (`pro-shared-ui/`, `pro-desktop/`) and the **core**
(`logosforge/`) where comment storage + AI context must live. Do **not** modify the
Whiteboard tree — read it for reference only.

---

## Part 0 — Settled architectural decision: **separate Comments store in the core, NOT merged into Notes**

The question "Pro already has Notes — shouldn't comments just be Notes?" was investigated against the
actual code (a 5-reader fan-out + a 3-lens adversarial review). **Verdict: build Comments as a
*separate* subsystem in the core. Do NOT merge them into Notes, and do NOT make them a "typed Note"
variant.**

Why (decisive, evidence-backed):
- The core `Note` model is 6 fields — `id, project_id, title, content, tags(CSV), pinned, created_at`
  (`logosforge/logosforge/models/models.py:56-66`) — and links to **entities** (PSYKE entries,
  Scenes, Acts/Chapters) by ID via junction tables (`:68-94`). A Note is *about an entity / the
  project*. A comment is *about a place in the prose*. **Zero column overlap**: Notes have no anchor,
  no offsets, no replies, no resolved status, no author, no updated_at.
- Merging means bolting ~9 comment-only nullable columns onto `Note` — a type discriminator in
  disguise (the "Hybrid" option), which pays the cost of separation *and* a shared table. Worst of both.
- The AI already consumes the two differently and incompatibly: Notes by **relevance ranking**
  (`gather_notes_context`, `context_builder.py:848-918`); comments by **open-vs-resolved status** as
  live editorial directives (`littleboy.py:125-162`). One selector can't serve both.

**"Separate store" ≠ "confusing double system."** The instinct to avoid two overlapping features is
right — but the fix is *naming/UX discipline*, not a merged table. Enforce one noun per concept
everywhere (labels, placeholders, empty-states):
- **Notes** = durable project research (characters, continuity, ideas); entity/scene-linked; `NotesPanel`.
- **Comments** = transient margin reactions on a specific passage; anchored, threaded, **resolvable**
  (they get resolved and disappear — a different *lifecycle* from a Note).
- Overlap case (a thought triggered by a passage but worth keeping): if it's durable research → a
  scene-linked **Note**; if it's a reaction to fix/resolve → a **Comment**. Document this so the two
  surfaces have non-overlapping jobs.
- ⚠️ Do **not** port the Whiteboard copy verbatim — its UI calls a comment body a "note"
  (`CommentsWindow.tsx` "empty note"; `local_state.py:225` "the note itself"). Rename so the word
  "Note" belongs exclusively to the research feature.

Four refinements the adversarial pass surfaced (detailed inline in Part 3):
1. **Anchoring is not a "mechanical port"** — define an explicit anchor-scope contract (3.2).
2. **Re-anchoring stays frontend-side** — it's not inherited by moving storage to the core (3.2).
3. **Do NOT move @mention→AI-reply into the core** — it hard-codes Whiteboard persona labels (3.4).
4. **AI-context wiring must be symmetric + token-budgeted** (3.4).

---

## Part 1 — The feature set to deliver

Replicate every capability below (all already live in Whiteboard). Each line is an acceptance item.

1. **Inline comments.** Select text in the manuscript → a "Comment" affordance appears →
   create a comment → the selected text gets a persistent highlight (a "mark") → click the mark
   to open a floating popover → all comments also list in a side panel. Add a toolbar/dock entry
   and a keyboard shortcut (Whiteboard uses **Ctrl+Shift+C**).
2. **Robust anchoring (W3C TextQuoteSelector).** A comment stores
   `{ quote, prefix, suffix, <location hints> }` and **re-locates itself** when the underlying
   text changes: an exact-quote pass (context match via prefix/suffix + word-boundary scoring +
   proximity to the old position) with a **bracket/landmark fallback**. It must survive edits
   *inside* and *around* the span and **disambiguate duplicate quotes** by choosing the occurrence
   nearest the original location.
3. **Orphan cleanup.** If the text a comment is anchored to is **deleted**, the comment is deleted
   too. Edits that move text **re-anchor** rather than orphan.
4. **Hide / filter resolved.** A toggle (panel + manuscript) to hide resolved comments + their
   marks; the preference is **persisted**.
5. **Export.** A portable **Markdown report** of all comments (quote + thread + resolved status).
6. **AI context.** The Pro assistant sees **open *and* resolved** comments (clearly labeled) and
   their **reply threads**, folded into its context so it can reason about them.
7. **Keyboard navigation.** Jump to next/prev **unresolved** comment (Whiteboard: **Alt+↓ / Alt+↑**).
8. **Polish.** Popover repositions on scroll/resize; errors surface to the user (toast); relative
   timestamps ("2m ago"); full ARIA/keyboard a11y.
9. **Threads / replies.** A comment is a thread: `CommentReply { id, body, author, created_at }`,
   with reply create/delete and thread UI in the popover + panel.
10. **Multi-paragraph selections.** A comment can span multiple paragraphs/scenes
    (store an end-anchor; anchor each edge independently; paint a mark per spanned block).
11. **@AI-mention.** Typing **@<assistant>** in a comment or reply triggers the AI to **reply in the
    thread**. (Whiteboard detects `@billy` / `@logos`; in Pro this becomes the Pro assistant —
    see Part 3.4.)

---

## Part 2 — Reference implementation (Whiteboard) — read these first

Frontend — `whiteboard-desktop/desktop/renderer/src/features/comments/`:
- `commentsApi.ts` — REST client + the shared types: `Comment`, `CommentReply`, `CommentAnchor`
  (`block_index`, `from_offset`, `to_offset`, `end_block_index?`, `prefix`, `suffix`, `quote`).
- `commentsAnchor.ts` — **the heart of it** (pure functions, no React/PM imports in the core logic):
  `locateSpan()` (exact-quote + context + word-boundary + proximity), `bracketBetween()`
  (landmark-pair enumeration fallback), `commentSpans()` (single- + multi-block resolution),
  `reconcileMarks()`, `findOrphanIds()`, `selectionToDraft()`. Constants: `CONTEXT=32`,
  `MIN_CONTEXT_MATCH=4`, `MIN_ONE_SIDED=8`, `MAX_GAP_SLACK=40`. **Port this nearly verbatim** —
  only the "what is a block / how do I read block text" adapter changes (Part 3.2).
- `commentsAnchorTests.ts` — 40 tests. Port + re-point them at Pro's block model.
- `useComments.ts` — the hook: load, CRUD, optimistic updates (incl. an "{Assistant} is thinking…"
  placeholder on @mention), reply add/remove, error channel.
- `CommentsLayer.tsx` — editor overlay: the selection→FAB, popover host, keyboard nav, mark
  reflow on scroll/resize.
- `CommentPopover.tsx` — floating popover: body, thread, reply composer, resolve/delete, `timeAgo`.
- `CommentsWindow.tsx` — side panel: list, hide-resolved, reply counts.
- `commentsPanelStore.ts` — panel open + `hideResolved` (persisted).
- The TipTap **decoration extension** that paints the highlight marks (in the editor's extensions).

Backend — `whiteboard-desktop/backend/app/`:
- `local_state.py` — `CommentsStore` + models `Comment` / `CommentReply` / `CommentAnchor`; CRUD;
  `add_reply` / `delete_reply`. **Note the invariant:** `update()` must carry `replies` through or
  editing wipes the thread.
- `routers/comments.py` — REST: CRUD + `POST/DELETE /api/comments/{id}/replies`.
- `routers/littleboy.py` — the AI glue: `_comments_context` (open + resolved notes + threads),
  `_detect_mention`, `ai_reply_to_comment`, `maybe_ai_reply`.

---

## Part 3 — Why this is NOT a copy: Pro's architecture + the per-layer adaptation

**Investigate and confirm each of these in the Pro tree before building** — they are the reason a
straight copy will not work.

### 3.1 The editor is a read-only scene render, not ProseMirror
`pro-shared-ui/src/components/manuscript/ManuscriptEditor.tsx` renders `SceneDTO`s
(`useScenes()`) as `SceneBlock`s (slugline + prose paragraphs from `scene.content`). There is **no
TipTap/ProseMirror** dependency in `pro-shared-ui`. Consequences:
- **No PM decorations.** Highlights must be painted by wrapping matched text ranges in `<mark>`
  (or `<span>`) in React, during the scene render — i.e. split each paragraph's text at the
  resolved comment offsets and render the pieces.
- **Anchor unit = scene, not a flat block-doc.** First confirm whether Pro writing actually happens
  here or whether this view is read-only/preview (memory: "Manuscript Editor unwired"). Where does
  the writer edit prose in Pro? Anchor comments to **`sceneId` + paragraph index + offset + quote**
  (plus prefix/suffix), so they survive content changes regardless of where the edit happens.

### 3.2 Adapt the anchoring, don't rewrite it
`commentsAnchor.ts` is written against an array of block texts (`texts: string[]`). Keep the
algorithm; replace only the **block adapter**: produce `texts` from the manuscript
(e.g. flatten scenes→paragraphs into an ordered `texts[]`, mapping each index back to
`{ sceneId, paraIndex }`). `block_index` becomes a position in that flattened list (or switch the
anchor to `{ sceneId, paraIndex }` directly — your call, but keep the locate/bracket logic intact).
Port `commentsAnchorTests.ts` against the new adapter.

> **Anchor-scope contract (do this first — it is NOT a mechanical port).** Whiteboard's flat
> `block_index` works only because Whiteboard collapses *one ProseMirror doc == one project*
> (`local_state.py:6-8`); the core has **no block-doc table** to validate a `block_index` against
> (`local_state.py:8`). Pro decomposes a project into many scenes, so a bare `block_index` is
> ambiguous. **Before writing the schema, define which document/scene the offsets count within** and
> carry a stable scope key on every anchor (e.g. `scene_id` + paragraph-relative offsets). Accept that
> the DB cannot FK-validate the position (no block-doc target exists) — so the anchor is advisory and
> the frontend reconciles it. Because anchoring units differ, a comment authored in Whiteboard's
> whole-doc model will **not** auto-resolve in Pro's scene model — they do not transparently converge.
>
> **Re-anchoring stays in the frontend.** The prefix/suffix reconciliation lives in `commentsAnchor.ts`
> (the renderer), not the backend. Moving storage to the core does **not** let tiers "inherit" anchor
> maintenance — each editor still runs its own `commentSpans()`/`findOrphanIds()` pass against its own
> document model. The core only stores+serves the anchor data.

### 3.3 Storage lives in the **core**, not a wrapper backend
`pro-desktop` has **no backend** — it talks straight to the core API via
`pro-shared-ui/src/adapters/httpApiClient.ts` (`createHttpApiClient`). So:
- Add a **core comments router + store** mirroring `logosforge/logosforge/api/routes/notes.py`, with
  **new tables** `Comment` + `CommentReply` (SQLModel, next to `Note` at `models.py:56`) — **not new
  columns on `Note`**. Reuse the Whiteboard `Comment`/`CommentReply`/`CommentAnchor` field shapes
  (`local_state.py:205-229`). Publish a `comments_changed` event mirroring `notes_changed`.
- Extend `httpApiClient.ts` with comment methods (list/create/update/resolve/delete + replies),
  following the existing `ROUTES` + `get/post/patch` pattern (see `listNotes`/`createNote`).
- This makes comments persist with the project and be reachable by **both** pro-desktop and pro-web,
  and by the assistant server-side.
- **Migrate, don't drop.** Whiteboard's shipped comments live in `~/.logosforge/comments/{doc_id}.json`
  (`local_state.py:253-273`). If/when Whiteboard repoints at the core, write a **one-time import** of
  those JSON files into the new core tables *before* deleting the local store — otherwise already-authored
  comments are silently lost. (Alternative: keep the local JSON store as an offline cache that syncs.)
- **Note:** the core has no migration framework (idempotent `create_all` + hand-rolled additive
  `ALTER ... ADD COLUMN`, `database.py:138-173`). Brand-new tables via `create_all` are low-risk, but any
  *later* change to the `Comment` schema inherits this brittle pattern — design the columns you need up front.

### 3.4 The AI is **Counterpart / AssistantDock**, not Billy/Logos
Pro's assistant routes are `assistantChat` / `assistantAction` / `runCounterpart`
(`pro-shared-ui/src/components/aipanels/{AssistantDock,CounterpartPanel}.tsx`). Adapt the
Whiteboard AI glue:
- **AI context (feature 6):** inject the open+resolved comments + threads into the **core's**
  assistant/counterpart prompt builder (find where the assistant context is assembled server-side),
  the way `littleboy.py::_comments_context` does.
- **@mention (feature 11):** replace `@billy`/`@logos` detection with Pro's assistant handle(s)
  (e.g. `@counterpart` / `@assistant` — confirm the canonical name). On mention, call the Pro
  assistant and post its answer as a reply in the thread.

> **Two cautions the review flagged:**
> 1. **Keep @mention detection + persona out of the core.** The Whiteboard regex hard-codes
>    `@billy|@logos` and the reply persona "Billy"/"Logos" (`littleboy.py:167`, `:228-232`) — explicit
>    Whiteboard product labels the **core CLAUDE.md forbids**. Do the mention detection + persona
>    labeling **frontend-side** (or behind a generic mention contract in `logosforge-ui-contracts`);
>    the core just exposes the assistant call.
> 2. **Wire AI-context symmetrically and within budget.** The core's `build_chat_context`
>    (`chat_context.py:20-69`) currently injects **neither** notes nor comments. Do **not** inject
>    comments there while leaving notes uninjected (that creates an asymmetric, drift-prone context
>    surface vs. the desktop UI assistant which *does* see notes). Pick one rule — inject both (with an
>    explicit ordering + `CONTEXT_MAX_CHARS=6000` tail-truncation budget so neither silently evicts the
>    other, `chat_context.py:67-68`) or inject neither and keep comment-context frontend-side — and
>    state it. Keep the comment selector (open-vs-resolved) as its **own** function, separate from
>    `gather_notes_context` (relevance-ranked); they are not interchangeable.

### 3.5 UI must be re-styled to the Studio identity
The Whiteboard comment UI is the light "Manuscript" theme. Pro is dark/cinematic: CSS vars
`--line`, `--line2`, `--txt2/3`, `--accent`; `'Chakra Petch'` headers; radial-gradient HUD panels;
`PanelShell` + `Corners` from `pro-shared-ui/src/components/shell/`. Rebuild the popover, side
panel, FAB, and marks as **Studio-styled** components (use `PanelShell` for the side panel; match
the AssistantDock/Counterpart visual language). Comments side panel should dock like the other
Pro panels (`components/shell`), not float like the Whiteboard window.

---

## Part 4 — Recommended build order

1. **Core:** comments router + store + persistence + tests (mirror `notes.py`). Verify via the core's
   OpenAPI + a couple of REST calls.
2. **Core AI:** fold comments into the assistant context builder; add @mention → assistant-reply.
3. **pro-shared-ui data layer:** `httpApiClient` comment methods; port `commentsAnchor.ts` + tests
   behind a Pro block adapter; a `useComments` hook.
4. **pro-shared-ui UI:** Studio-styled marks (DOM `<mark>` in the scene render), FAB, popover,
   docked side panel, threads, hide-resolved, keyboard nav, export. Wire the toolbar entry +
   Ctrl+Shift+C.
5. **Multi-paragraph + @mention + polish** last (build on the working single-span path).

---

## Part 5 — Decide / confirm before coding
- **Anchor scope key (blocking).** Does Pro map one document per project, per scene, or a free-form
  doc id? The core has no block-doc table, so the `Comment` row must carry a stable scope key the
  offsets count within (likely `scene_id`). Resolve this before writing the schema (see 3.2).
- **Where does the Pro writer actually edit prose?** Is `ManuscriptEditor` the edit surface or a
  read-only preview? (Memory: "Manuscript Editor unwired.") This determines selection capture and
  where the frontend re-anchoring pass runs.
- **Migration of existing comments** — import `~/.logosforge/comments/{doc_id}.json` into the new core
  tables, or keep the local store as an offline cache (see 3.3). Don't drop them silently.
- **Author/identity model.** Replies carry an author string (`'you'` / assistant name). Pro is
  single-user today — is writer-vs-assistant enough for the alpha, or is real multi-user identity needed?
- **Repo ownership.** Per the core CLAUDE.md the core has no React — the `CommentsPanel` + in-editor
  margin layer go in `pro-shared-ui`, the wire types in `logosforge-ui-contracts`. Confirm those repo
  sessions are in scope for this item or track them as follow-ups.
- `SceneDTO` shape — the id field and how scenes map to the rendered paragraphs.

## Part 6 — Verification (must pass before you call it done)
- Core: comments tests green; OpenAPI shows the new routes; manual CRUD + reply + @mention round-trip.
- pro-shared-ui / pro-desktop: `typecheck` clean; the ported anchor tests green; build succeeds.
- **Live**: run pro-desktop (`cd pro-desktop && npm run dev`, with the core API up) and verify
  end-to-end: select → comment → mark renders in Studio style → popover → resolve/delete → side
  panel → reply → @mention gets an assistant reply → hide-resolved → export → keyboard nav →
  re-anchor after a content edit → orphan-delete after the text is removed.

## Part 7 — Constraints
- Pro tree + core only; never edit the Whiteboard tree.
- Match the Studio UI; do not import Whiteboard CSS/themes.
- Don't regress existing Pro panels or the core test suite.
- Keep `commentsAnchor` pure/testable; keep the model shapes compatible with Whiteboard's so the two
  products can converge later.
