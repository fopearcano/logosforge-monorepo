# Alpha UI Stability Notes — Manuscript navigation + fullscreen

## Issue

1. **Manuscript reset/re-render on section switch.** Navigating Manuscript →
   (Outline / Notes / Assistant / PSYKE / Dashboard) → Manuscript visibly reset
   or re-rendered the editor and lost in-memory state (scroll position, focused
   block, selection, active scene, current screenplay element type).
2. **Fullscreen could lock / degrade.** There was no in-app way to exit full
   screen (only the native macOS control), so a user could feel trapped, and the
   editor could render poorly after a fullscreen transition.

## Root cause

- `MainWindow._show_manuscript()` built a **new** `WritingCoreView` on every
  visit and `_set_content()` **destroyed** the previous one (`deleteLater`). Only
  `ScenesView` was cached; the Manuscript editor was not — so all in-memory
  editor state was discarded on each navigation.
- There was **no application-level fullscreen toggle/exit** action; the app
  relied solely on the OS control.

## Fix (UI stabilization only — no schema/provider/feature changes)

- **Cache the Manuscript editor per project** (`_cached_manuscript_view`).
  `_show_manuscript()` reuses the cached `WritingCoreView` instead of rebuilding
  it; `_set_content()` **hides** (never destroys) the cached scenes + manuscript
  views. The cache is cleared on project switch (`_switch_project`).
- **Refresh only when needed.** Plain navigation does **not** refresh, reload
  from the DB, or run schema normalization — state is preserved exactly. When
  data changes elsewhere (`_on_data_changed` sets `_manuscript_needs_refresh`),
  the next return runs `WritingCoreView.refresh()` **once**, which is
  state-preserving (it flushes pending saves, then restores focus + scroll via
  `_restore_session_state`).
- **Renderer selection is unchanged and deterministic by mode** — Graphic Novel
  still uses the shared `WritingCoreView` (Act → Page → Scene → Panel); the
  legacy page-manager / standalone Pages routes remain disabled.
- **Always-reversible fullscreen.** Added a **View → Toggle Full Screen** (F11)
  and **Exit Full Screen** action plus `toggle_fullscreen()` / `enter_fullscreen()`
  / `exit_fullscreen()` on `MainWindow`. Exit always returns to normal and
  restores the prior window geometry; full screen is never forced at startup; no
  kiosk mode; no parentless windows; the standalone Pages route stays disabled.

## Automated tests

- `tests/test_manuscript_navigation_state.py` — caching/reuse, no-refresh on
  plain nav, single state-preserving refresh after external change, dirty
  survives nav, GN shared renderer, fresh-window clean state.
- `tests/test_fullscreen_window_behavior.py` — toggle/exit actions, never
  fullscreen at startup, exit always normalizes, repeated toggles don't lock,
  navigation reachable, no standalone Pages route.

## Manual checks still required (real desktop)

- Section switching preserves typed text + scroll/focus (Screenplay especially).
- Enter/exit full screen repeatedly (macOS green button **and** View menu / F11);
  app always exits; main navigation stays visible; Manuscript re-renders cleanly.
- Graphic Novel Manuscript/Outline in full screen keep the shared renderer; old
  page-manager UI never appears.
- Dexter opens after fullscreen; no raw-audio/memory side effects.
