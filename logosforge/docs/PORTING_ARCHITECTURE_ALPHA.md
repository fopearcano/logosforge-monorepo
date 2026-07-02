# Porting Architecture — Alpha → Electron/React (Authoritative Contract)

**The Python/PySide6 Alpha is the behavioral and spec reference** for the
Electron Desktop and TypeScript Web ports. Port *behavior and data
contracts*, never legacy renderers.

## Target architecture (all ports, and the Python next phase)

```
SharedManuscriptEditor  ←  mode schema
SharedOutlineEditor     ←  mode schema
```

Writing-mode behavior is **schema-driven** over shared editor components:

| Mode          | Schema                                              |
|---------------|-----------------------------------------------------|
| Novel         | Act → Chapter → Scene                               |
| Screenplay    | Act → Chapter → Scene / screenplay blocks           |
| Graphic Novel | **Act → Page → Scene → Panel**                      |
| Stage Script  | Act → Chapter → Scene / stage blocks                |
| Series        | Season → Episode → Act → Chapter → Scene            |

## Current Python Alpha state (Phase 2 complete, 2026-06-11)

* **Routing is now schema-driven through the shared families.** Graphic
  Novel Manuscript mounts the SHARED `WritingCoreView` (the same editor as
  Screenplay; the registered `writing_formats.GRAPHIC_NOVEL` block grammar
  styles `PAGE n` / `PANEL n` / field lines; chapter headers are hidden in
  GN mode). Graphic Novel Outline mounts the SHARED `PlanView`, which
  renders the GN mode schema itself (Act cards → Page blocks → Scene
  groups with `(continued)` → Panel blocks; `+ Act/+ Page/+ Scene/+ Panel`
  action bar; Panel double-click deep-links to the Manuscript cursor).
* The cursor↔panel mapping (`graphic_novel_blocks.panel_at_offset` /
  `panel_offset`) gives Outline deep-links and Dexter's "selected Panel"
  resolution on the shared editor (no widget coupling).
* The legacy `GraphicNovelManuscriptView` / `GraphicNovelOutlineView`
  modules are **LEGACY — NOT ROUTED** (labelled; unreachable from Alpha
  navigation; kept only until safe deletion) — never port them.
* Data model unchanged and certified: `graphic_novel_structure` computes
  Act → Page → Scene → Panel over scene-local bodies (one storage for
  Outline/Manuscript/exports).

## Hard rules for every port and release

1. Graphic Novel **Manuscript = a writing/text/block editor** (the shared
   editor family + GN schema), never a page manager.
2. Graphic Novel **Outline = the shared block/card outline** + GN schema,
   never a tree-only or page-form manager.
3. Standalone **Pages** is disabled/deferred — hidden, inert, never mounted.
4. **Dexter's Room** is writing/formatting/interaction only (local
   buffered transcription, preview-first proposals, explicit Apply; no
   grammar, no cloud speech, no raw audio off-machine).
5. **Grammar / deep text correction: deferred** (future Review/Correction
   phase).
6. **UI translation/localization: deferred** (English-only UI; project
   Writing Language and Dexter language stay fully multilingual and
   separate from UI language).
7. **ComfyUI / image generation: deferred.** Panels are the future anchor
   for visual production integrations — no image fields exist.
8. **Canvas Plot: deferred.**
9. Qt-specific fullscreen/window glitches are **not** automatically ported,
   but the unsafe patterns that caused them must not be copied: no
   parentless windows/dialogs, no popups without a parent chain to the main
   window, no navigation that swaps the central surface through a separate
   top-level route (the original standalone-Pages minimize bug).
10. Writing-mode lock, project isolation, propose-then-confirm AI, and
    export privacy (no secrets/settings/audio in exports) are contract
    behavior in every port.

## DO NOT PORT

* The old **"Comics Script"** single-scene renderer (scene dropdown +
  bespoke chrome). Removed from Alpha UX; exists only in history.
* The old **GraphicNovelManuscript page/panel manager** as a Manuscript
  (PAGE containers with "+ Panel"/"Delete Page" as the primary writing UI).
* The old **tree-only GraphicNovelOutline** (thin tree + empty detail pane).
* The old **standalone Pages route/widget** (`GraphicNovelScenePagesView`
  and the `GraphicNovelPage/Panel` tables behind it — preserved, unmounted,
  never user-facing).
* Any **parentless, fullscreen-unsafe window/dialog pattern**.
* Any structure repair label ("Recovered Act") surfacing as a primary UI
  control.

## Acceptance criteria for the next Python implementation phase

PASS only if: GN Manuscript route mounts the shared Manuscript editor
family with the GN schema (Act → Page → Scene → Panel) and behaves as a
text/block editor; GN Outline route mounts the shared block/card Outline
family with the GN schema; legacy GN renderers are unreachable as primary
UI; standalone Pages stays inert; Screenplay/Novel/Stage/Series/Dexter
unchanged; fullscreen navigation never minimizes; tests prove the old UI
markers are unreachable. FAIL if PAGE-manager containers remain the primary
Manuscript UI, a legacy component is merely restyled and kept as primary,
Chapter surfaces as primary GN structure, Pages reactivates, Screenplay is
damaged, data is duplicated/lost, or the fullscreen bug returns.
