# Follow-up: Dexter's Room over the core Voice API (desktop)

> Status: direction note. Records what the downstream desktop frontend should
> adapt to now that the core exposes a canonical voice API. No code here.

## What the core now provides

`logosforge/voice/service.py` (`VoiceRoomService`) + `logosforge/voice/serialization.py`
are the canonical, **headless, JSON-safe** API for Dexter's Room — the voice
equivalent of "the API layer frontends consume" (see `CLAUDE.md`). Pure Python,
no Qt; every method returns plain dicts.

Surface: `backend_status`, `transcribe` (stateless STT), `transcribe_segment`
(frontend-segmented) **and** `feed_chunk`/`flush` (core-segmented, reusing the
pure-Python `AudioBuffer`), session history (add/edit/merge/split/discard/
restore/retry/clear), glossary (suggest/apply), intents (list/preview/apply),
Billy (operations/generate/apply), commit (targets/commit), and
`can_undo`/`undo_last`. Constructor injects `db` + optional `ai_complete`, and
optionally a shared `history`/`transcriber`.

## What the desktop (`fopearcano/logosforge-desktop`) should do

1. **Wrap, do not reimplement.** Add Dexter as a `desktop/renderer/src/features/littleboy/dexter/`
   React feature backed by **thin FastAPI routes** in `backend/app/` that call
   `VoiceRoomService`. Do **not** re-derive segmentation/intent/Billy/commit
   logic in the backend — that is the drift `CLAUDE.md` warns against (the
   current `littleboy`/`logos` services reimplement core logic; Dexter must not
   repeat it). The backend should `import logosforge...` (or consume it via
   the core's API layer) so behaviour stays canonical.

2. **Audio.** The browser/renderer captures the mic (Web Audio / MediaRecorder).
   Choose one:
   - **Frontend segments** → POST finalized PCM to a route calling
     `transcribe_segment`; simplest, but duplicates VAD in JS.
   - **Core segments (preferred)** → stream chunks over a WebSocket to
     `feed_chunk`/`flush`; keeps the 900ms/silence-threshold behaviour
     canonical in the core.

3. **Commit + undo boundary.**
   - Cursor/editor targets return `inserted_text` — the React editor inserts it
     and owns **its own undo** (`can_undo` returns False for cursor by design).
   - DB targets (Note/PSYKE/GN field) commit server-side and are undoable via
     `undo_last`.

4. **Contracts.** When `logosforge-ui-contracts` exists, mirror the dict shapes
   from `logosforge/voice/serialization.py` there (TypeScript types) so the
   wire contract is shared rather than hand-copied.

## Not done here (by design)

- The FastAPI routes + the React Dexter UI live in the desktop repo, not here.
- The existing PySide6 voice panel was **not** refactored onto the facade: it is
  a different consumption layer (live audio + Qt widgets/signals + live-editor
  commit + undo-op) and forcing it through the dict/stateless API would regress
  undo or muddy the wire contract. The facade is validated instead by
  `tests/test_voice_service.py::test_full_loop_dictate_clean_commit_undo`, which
  mirrors how the React Dexter will consume it.
