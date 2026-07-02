# LogosForge Whiteboard — Design Restyle Brief

LogosForge Whiteboard is the Free-tier, deliberately-minimal writing application of the LogosForge suite: a distraction-light desktop app (Electron + React) built around a single full-bleed writing sheet where the writer composes prose or screenplay text. Its guiding principle is that **simplicity is a feature** — every editor aid (line numbers, folding, syntax highlighting, AI assistance, story-bible search) defaults to off or out-of-the-way, so the page stays a clean writing surface until the writer opts in. It supports five writing modes (`novel`, `screenplay`, `graphic_novel`, `stage`/`stage_script`, `series`) with a Fountain-aware screenplay engine, a lightweight outliner, a minimal story bible (PSYKE), and two purposely-small AI agents (Billy chat + Logos inline). It is the Free-tier reduction of the Pro graph/workspace tier — no graph, no Counterpart, no Quantum: just clean writing, with the whole look driven through a single themeable CSS-variable layer. This brief hands that visual layer to you, the designer (Claude Design), to restyle holistically while preserving every behavioral contract called out below.

---

## Information Architecture

The app is a conventional desktop frame composed of a title bar, a two-column work area, a bottom status bar, and a set of floating/transient overlays. Spatial map, outer to inner:

- **App shell** (`App.tsx`, root element `div.app` with conditional modifiers `is-top-hidden` / `is-focus`) — owns global view state (focus mode, panel visibility, theme), global keyboard/menu shortcuts, and delegates content to feature pages. Vertical stack:
  - **Title bar** (`header.titlebar`, 42px) — top strip. **Left:** outline toggle (`☰`). **Center:** app title `LogosForge Whiteboard` (`h1.app-title`). **Right cluster** (`div.titlebar-right`): Focus Mode (`◌`), Hide-top-panel (`▲`), `<ThemeSelector>` (the `Theme` trigger with a `.theme-dot` accent swatch, opening a `Popover` grid of 6 swatches + Custom), and the conditional `PSYKE` toggle pill.
  - **Work area** (`div.workarea`) — flex row filling the body:
    - **Left column — Outline panel** (`aside.outline-panel`, ~232px, conditional on `ui.outlineVisible`) — the lightweight story-structure tool, with two views behind one segmented toggle: a manual editable/persisted tree (acts/chapters/scenes/beats/notes with status, color, tags, zoom) and a read-only "From Document" navigator derived live from editor content. Clicking a derived item scrolls the editor.
    - **Main column — Whiteboard editor** (`main.whiteboard`, always mounted) — the primary writing surface. Top-to-bottom inside it: a slim **status line** (`div.wb-statusline`: File menu + Writing-Mode selector + screenplay element chip on the left; draft/file-state indicators + Editor-settings popover on the right), an optional **Screenplay toolbar** (`div.wb-toolbar`, screenplay mode only), and the **writing sheet** (`div.wb-surface` → `div.wb-content` → `div.wb-editor`, a centered measure-capped TipTap/ProseMirror column), with a side-by-side **Preview** (`div.wb-preview`) in screenplay Preview mode.
  - **Status bar** (`footer.statusbar`, 26px, conditional on `ui.statusBarVisible`) — backend connection dot + label on the left, `API v… · core …` version readout on the right.
- **Floating / transient overlays** (rendered above the work area, not in normal flow):
  - **PSYKE window** (`aside.psyke-window`, 320px, fixed to the right edge `top:42px; right:0; bottom:26px; z-index:20`) — the minimal story bible: search → results → detail, plus a create form. Seeded from the current editor selection on open. Floats above the workarea; never reflows the editor.
  - **Billy floating chat** (`div.billy-box.littleboy-box`, 340×420px, draggable, z-index 32) — the compact hovering "Small AI" chat, spawned top-right.
  - **Logos inline box** (`div.logos-box.littleboy-box`, 340px wide, z-index 30) — the inline contextual AI, auto-positioned at the caret/selection.
  - **Popovers** (`div.wb-popover` → `div.wb-popover-panel`, `role="dialog"`) — the shared floating-menu primitive: File, Editor Settings, Screenplay Settings/Format/Export, Outline filter/row-actions, Theme picker.
  - **Autocomplete popup** (`div.sp-autocomplete`, `position:fixed`) — screenplay character/scene-heading suggestions at the caret.
  - **Transient toasts/hints** — import/export `div.wb-toast`, the centered `div.focus-hint` ("Focus Mode — press Esc to exit"), the PSYKE "Added" toast.

Spatially: the title bar pins the top, the status bar pins the bottom, the outline and editor split the middle row, and everything AI/bible/menu-related floats above the editor anchored either to a trigger (popovers, autocomplete) or to a screen edge/caret (PSYKE right edge, Billy top-right, Logos at caret).

---

## Design Tokens & Current Theming

The entire visual skin is one global stylesheet (`styles/app.css`) plus a runtime theming engine (`styles/themes/`) that drives **every color through CSS custom properties**. The whole UI reads `--*` variables, so applying a theme is just setting variables on `<html>` — no per-component restyle is needed. **The restyle owns this layer**: the designer can rethink the look almost entirely from this one file plus the token map.

**Theming engine.** `ThemeProvider` (wraps `<App>` in `main.tsx`) holds `themeId` + `customFields`, resolves the active theme via `resolveTheme`, applies it in `useLayoutEffect`, and persists it. `useTheme()` exposes `{ theme, themeId, setThemeId, customFields, setCustomField }`. `ThemeSelector` (in the title bar, via `Popover`) is a 2-column `.theme-grid` of 6 predefined `.theme-option` swatches + a Custom option, with 6 `<input type="color">` rows shown only when Custom is active. `applyThemeVars()` (`themeTokens.ts`) is the **only** writer of theme vars and sets `data-theme="light|dark"` + `data-theme-id="<id>"` on `<html>`.

**Token map.**
- `WhiteboardTheme` — 17 fields: `id, name, mode, appBg, panelBg, editorBg, text, mutedText, editorText, editorMuted, border, accent, accentSoft, selectionBg, editorSelection, caret, shadow`.
- `CustomThemeFields` — 6 user-editable fields: `appBg, editorBg, text, mutedText, accent, border` (editor ink/muted are *derived* from `editorBg` luminance in `customToTheme`).
- CSS variables written by `applyThemeVars` and consumed across `app.css`: `--bg, --panel, --border, --text, --muted, --accent, --hover, --selection, --paper, --ink, --paper-muted, --paper-selection, --page-shadow, --caret, --error, --ok`, plus the `--lf-*` aliases.
- Variables set by features and read by CSS (names are a contract): `--measure` and `--wb-scale` (`WhiteboardPage.tsx`), `--wb-font-px` / `--wb-line-height` (`editorToolsSurface.ts`), `--syn-*` (`syntaxThemes.ts`).
- **Persistence:** `localStorage` keys `lf-theme-id`, `lf-theme-custom`; UI-visibility booleans `lf-vis-top|outline|status|psyke`.

**Current aesthetic.** A deliberately quiet, "Slugline-like" minimal writing app. Default theme is **Paper White** (warm parchment `#f3ead3` chrome, near-white page) — calm, low-chroma, thin 1px borders, small uppercase letter-spaced labels in muted gray. Six shipped themes range from light (Paper White) through dark (Ink Black, Klein Blue) to mixed dark-chrome/light-page (Ocher Gold, Red Room, Blue Bronze); each previews as a tiny swatch (app bg + page rect + accent stripe). Mixed themes are why `--text` (UI ink) and `--ink` (editor ink) are independent tokens — both must stay legible. Editor type is serif (Iowan Old Style) for prose, monospace (Courier Prime) for screenplay/stage. Accent is the only saturated element and is theme-defined.

---

## App Shell & Layout

### PURPOSE
The App Shell is the top-level frame of the Whiteboard app: it owns the window chrome (titlebar with global toggles), the two-column work area (Outline + editor), the floating PSYKE window, and the bottom status bar. It coordinates global view state (focus mode, panel visibility, theme) and global keyboard/menu shortcuts, then delegates all real content to feature pages. Files: `App.tsx` (shell + global key/menu wiring), `main.tsx` (React root + theme bootstrap), `components/StatusBar.tsx` (connection footer), `components/Popover.tsx` (shared floating-menu primitive used by feature toolbars).

### SURFACES / SCREENS
Rendered by `App()` in `App.tsx`, in DOM order:

1. **Titlebar** — `<header className="titlebar">`. Top bar. Left: outline toggle (`☰`). Center: app title `LogosForge Whiteboard` (`h1.app-title`). Right (`div.titlebar-right`): Focus Mode (`◌`), Hide-top-panel (`▲`), `<ThemeSelector />`, and a conditional `PSYKE` toggle button.
2. **Work area** — `<div className="workarea">`. The main two-column region below the titlebar. Left column: `<OutlinePanel>` (only when `ui.outlineVisible`). Right/main column: `<WhiteboardPage>` (always mounted).
3. **PSYKE window** — `<PsykeWindow>`. A floating/transient surface (not in normal flow), mounted only when `psykeOpen`. Seeded with the current text selection as its query.
4. **Status bar** — `<StatusBar>` rendered as `<footer className="statusbar">`. Bottom strip showing backend connection state + version, only when `ui.statusBarVisible`.
5. **Focus hint** — `<div className="focus-hint">`. A transient toast ("Focus Mode — press Esc to exit") shown for ~2.2s on entering focus mode.
6. **Popover** (`Popover.tsx`) — a reusable trigger-button + floating panel (`div.wb-popover` → `div.wb-popover-panel`). Not used directly by the shell; it is the shared primitive for feature toolbars (per its doc comment: Screenplay toolbar Settings / Format / Export).

### COMPONENTS
Hierarchy (containers vs leaf controls):

- `main.tsx`: `ReactDOM.createRoot(#root)` → `React.StrictMode` → `ThemeProvider` (container) → `App`.
- `App` (root container, class `app` + modifier flags):
  - `header.titlebar` (container)
    - outline toggle `button.icon-toggle` (leaf; `is-active` when outline visible)
    - `h1.app-title` (leaf)
    - `div.titlebar-right` (container)
      - Focus `button.icon-toggle` (leaf)
      - Hide-top `button.icon-toggle` (leaf)
      - `ThemeSelector` (leaf control, external)
      - PSYKE `button.psyke-toggle` (leaf; conditional on `ui.psykeButtonVisible`)
  - `div.workarea` (container)
    - `OutlinePanel` (container, conditional; external feature)
    - `WhiteboardPage` (container, always present; external feature)
  - `PsykeWindow` (container, conditional; external feature)
  - `StatusBar` (leaf, conditional)
  - `div.focus-hint` (leaf, conditional)
- `StatusBar`: `footer.statusbar` → `span.status` (with `span.dot`), `span.spacer`, `span.version`. All leaves.
- `Popover`: `div.wb-popover` (container) → `button.wb-tool` (trigger leaf) + `div.wb-popover-panel.wb-popover-{left|right}` (container, `role="dialog"`, render-prop children).

### USER INTERACTIONS
Titlebar clicks:
- `☰` → `ui.toggleOutline()` (show/hide left Outline column). `aria-pressed` mirrors `ui.outlineVisible`.
- `◌` → `toggleFocus()` (enter/exit focus mode; entering also closes PSYKE).
- `▲` → `ui.toggleTopPanel()` (hide the top panel; Esc restores).
- `ThemeSelector` → theme picking (external).
- `PSYKE` → toggles `psykeOpen`; opening calls `openPsyke()` which seeds `psykeQuery` from the current selection. `aria-pressed` mirrors `psykeOpen`.

Global keyboard shortcuts (`App.tsx`, window `keydown` listener; modifier = Meta or Ctrl, plus Shift, not Alt):
- `Ctrl/Cmd+Shift+O` → toggle Outline.
- `Ctrl/Cmd+Shift+P` → toggle PSYKE.
- `Ctrl/Cmd+Shift+T` → toggle top panel.
- `Ctrl/Cmd+Shift+D` → toggle Focus Mode.
- `Escape` → tiered handling (see STATES). Each handled shortcut calls `e.preventDefault()`.
- Note: `Cmd/Ctrl+K` is intentionally NOT bound here (reserved for Logos).

Native View-menu actions (`onMenuView` from `fileApi`, mouse-driven menu): actions `toggleTopPanel`, `toggleOutline`, `togglePsyke`, `focusMode`, `toggleTheme` map to the same handlers. Menu and keyboard share handlers via `actionsRef` (a ref kept in sync each render so listeners subscribe once).

Outline navigation: `OutlinePanel onNavigate={(item) => scrollToBlock(item.blockIndex)}` → `scrollToBlock` queries `.wb-editor`, indexes `children[index]`, and calls `scrollIntoView({behavior:'smooth', block:'center'})`.

PSYKE seeding: `currentSelectionText()` reads `window.getSelection().toString().trim()`.

Popover (`Popover.tsx`): trigger button toggles `open`; when open, an outside `mousedown` (target not within `ref`) closes it, and `Escape` closes it (calling `e.stopPropagation()` so it does not bubble to the global Esc handler). Children are a render-prop receiving a `close()` callback so menu items can self-dismiss.

### STATES & MODES
- **Backend connection state** (`status.state`): `connecting` | `connected` | `error`. `ready = status.state === 'connected'` is passed to `OutlinePanel` and `WhiteboardPage`. StatusBar maps state → color (`connecting #e0b341`, `connected #4ade80`, `error #f87171`, fallback `#888c99`) and label (`Connecting…`, `Connected`, `Unavailable`, fallback = raw state).
- **Focus mode** (`ui.focusModeActive`): adds `is-focus` to the root `app` class; entering closes PSYKE and shows the timed focus hint.
- **Top panel hidden** (`!ui.topPanelVisible`): adds `is-top-hidden` to the root class. Root class string built in `App.tsx`: `app${is-top-hidden}${is-focus}`.
- **Panel visibility toggles** from `useUiVisibility`: `outlineVisible`, `topPanelVisible`, `statusBarVisible`, `psykeButtonVisible`, `focusModeActive`. These gate conditional rendering of OutlinePanel, StatusBar, the PSYKE button, etc.
- **Writing mode** (`docMode`, default `'novel'`): one of `novel` | `screenplay` | `graphic_novel` | `stage` | `series`. Owned by the document/`WhiteboardPage`, lifted into App via `onModeChange={setDocMode}`, and passed down to `OutlinePanel mode={docMode}` so the manual outliner applies mode-aware defaults. The App shell itself does not branch visually on mode — mode-specific chrome lives in the feature pages.
- **PSYKE open** (`psykeOpen`): mounts/unmounts `PsykeWindow`.
- **Focus hint** (`focusHint`): true for ~2200ms after entering focus mode.
- **Escape tiering** (precedence): (1) if focus is inside `.wb-popover`, `.psyke-window`, `.littleboy-box`, or an `INPUT/SELECT/TEXTAREA`, the shell does nothing (lets the transient/input handle Esc; LittleBoy closes via its own capture-phase handler); (2) else if `psykeOpen`, close PSYKE; (3) else call `ui.handleEscape()` (restore hidden panels / exit focus) and preventDefault if it handled.

### DATA & API
- **Backend status**: `bridge` from `./api/backend` (type `BackendStatus`). `bridge.getBackendStatus()` (one-shot Promise) + `bridge.onBackendStatus(cb)` (subscription returning an unsubscribe fn). `BackendStatus` shape used here: `{ state: 'connecting'|'connected'|'error', baseUrl, managed, detail?, apiVersion?, version? }`. `baseUrl = status.baseUrl || DEFAULT_BASE_URL` (`DEFAULT_BASE_URL` from `features/whiteboard/whiteboardApi`).
- **UI visibility store**: `useUiVisibility()` from `./state/uiVisibilityStore` — exposes `outlineVisible`, `topPanelVisible`, `statusBarVisible`, `psykeButtonVisible`, `focusModeActive`, and actions `toggleOutline`, `toggleTopPanel`, `enterFocusMode`, `exitFocusMode`, `handleEscape`.
- **Theme**: `useTheme()` (`{themeId, setThemeId}`) + `PREDEFINED_THEMES` (cycled by `cycleTheme`), `ThemeSelector`, `ThemeProvider`, and `applyStoredTheme()` (called in `main.tsx` before render to avoid theme flash). From `./styles/themes/*`.
- **Menu bridge**: `onMenuView(cb)` from `./features/files/fileApi` (native View-menu events).
- **Feature pages (contract owners, not restyled here)**: `WhiteboardPage` props `{ baseUrl, ready, onOutlineChange, onModeChange }`; `OutlinePanel` props `{ derivedItems, onNavigate, baseUrl, ready, mode }`; `PsykeWindow` props `{ baseUrl, initialQuery, onClose }`. `OutlineItem` type from `features/outline/types` (renders via `item.blockIndex`).
- **Global stylesheet**: `./styles/app.css` imported in `main.tsx` — all shell class names below are styled there.

### RESTYLE SURFACE (safe to redesign freely)
- All spacing, color, typography, borders, shadows, radii, and motion for: `.titlebar`, `.app-title`, `.titlebar-right`, `.icon-toggle`, `.psyke-toggle`, `.workarea`, `.statusbar` (and `.status`, `.dot`, `.spacer`, `.version`), `.focus-hint`, `.wb-popover`, `.wb-tool`, `.wb-popover-panel`.
- The glyphs/iconography of the three icon buttons (`☰`, `◌`, `▲`) and the `PSYKE` label — swap for any icon set, as long as titles/`aria-label`s are preserved.
- Layout of the work-area columns (widths, order, collapse animation) and the placement/appearance of the floating PSYKE window and focus toast.
- StatusBar dot colors and labels are visual: the `COLORS`/`LABELS` maps in `StatusBar.tsx` can be re-skinned (keep the three keys connecting/connected/error and a sensible fallback).
- Popover panel alignment styling (`wb-popover-left` / `wb-popover-right`) and open/close transitions.

### LOGIC INVARIANTS (must preserve)
- **Root class contract** (`App.tsx`): the root element must keep base class `app` and the conditional modifiers `is-top-hidden` (when top panel hidden) and `is-focus` (when focus mode active). CSS and behavior key off these.
- **DOM hooks used by JS logic** (do NOT rename):
  - `.wb-editor` — `scrollToBlock()` queries it and indexes its direct `children` by block index; the editor's blocks must remain direct children in document order.
  - `.wb-popover`, `.psyke-window`, `.littleboy-box` — the global Esc handler (`App.tsx` keydown) tests `activeElement.closest(...)` against these exact classes to decide whether to defer Esc. Renaming breaks Esc tiering.
  - `.wb-popover` is also the boundary `Popover.tsx` uses (`ref.current.contains`) for outside-click close.
- **Keyboard contracts**: preserve `Ctrl/Cmd+Shift+O/P/T/D` and the modifier gate (`mod && shift && !alt`, matched via `e.code` = `KeyO/KeyP/KeyT/KeyD`). Do not bind `Cmd/Ctrl+K`. Esc precedence order must stay: focused transient/input → close PSYKE → `ui.handleEscape()`.
- **Esc-from-input rule**: focus inside `INPUT/SELECT/TEXTAREA` must continue to bypass the shell's Esc handling — keep native form controls (or replicate the tag check) so typing isn't hijacked.
- **Popover semantics**: keep `aria-haspopup="dialog"`, `aria-expanded`, panel `role="dialog"` + `aria-label={title}`, the outside-mousedown close, and the Esc `stopPropagation()` (so popover Esc does not also trigger the global Esc). Keep the render-prop `close()` so menu items can dismiss.
- **ARIA / accessibility affordances to keep**: `aria-pressed` on the outline toggle and PSYKE toggle; `aria-label` on the Focus and Hide-top buttons; `title` tooltips (they document the shortcuts and are the only place some shortcuts are surfaced). All interactive elements must remain real `<button type="button">` for keyboard focus.
- **Data flow / handler wiring**: `actionsRef` must keep being re-synced every render (menu + key listeners read latest handlers through it while subscribing once). `psykeOpenRef` likewise mirrors `psykeOpen` for the Esc handler. PSYKE open must seed `psykeQuery` from `currentSelectionText()` (selection-aware). `docMode` must stay lifted from `WhiteboardPage` (`onModeChange`) and forwarded to `OutlinePanel` (`mode`). `outlineItems` flows `WhiteboardPage` (`onOutlineChange`) → `OutlinePanel` (`derivedItems`); `onNavigate` must still call `scrollToBlock(item.blockIndex)`.
- **Conditional mounting**: OutlinePanel/StatusBar/PSYKE button/PsykeWindow visibility is driven by `useUiVisibility` flags + `psykeOpen` — keep these gates; `WhiteboardPage` must remain always-mounted (only one editor instance).
- **Theme bootstrap order** (`main.tsx`): `applyStoredTheme()` must run before React renders (prevents theme flash). Keep `ThemeProvider` wrapping `App`.
- **StatusBar state keys**: `status.state` values `connecting`/`connected`/`error` must keep mapping to a color and label; preserve the `title={status.detail}` tooltip and the `apiVersion` / `version` readout (`API v… · core …`).

### CURRENT LOOK
A conventional desktop-app frame. A thin titlebar runs across the top: a single `☰` hamburger glyph at the left, the centered plain-text title "LogosForge Whiteboard", and a right cluster of monochrome glyph buttons (`◌` focus, `▲` hide-top), the theme selector, and a text `PSYKE` pill that highlights (`is-active`) when open. Below sits a two-column work area — a collapsible left Outline column and the main editor — with no visible divider chrome defined at the shell level. A slim footer status bar spans the bottom showing a small colored dot (amber/green/red) + "Backend: …" on the left and a muted "API v… · core …" version on the right. Transient surfaces float above: the PSYKE window, a small centered "Focus Mode — press Esc to exit" toast, and feature popovers (small bordered dropdown panels anchored under a `wb-tool` trigger button). Active toggles are indicated by an `is-active` class rather than distinct iconography. Everything is theme-variable driven (colors come from the active theme via `ThemeProvider`/`app.css`).

---

## Whiteboard Editor (main writing surface)

### PURPOSE
The Whiteboard Editor is the Free-tier's single, distraction-light writing surface: a full-panel TipTap/ProseMirror sheet where the writer composes prose or screenplay text. It hosts the writing-mode selector, file/import/export menu, autosave + file-state indicators, the optional Screenplay toolbar, and (in Screenplay mode) a side-by-side formatted Preview. Everything lives in `features/whiteboard/WhiteboardPage.tsx`, with the editor itself in `WhiteboardEditor.tsx`.

### SURFACES / SCREENS
Top-to-bottom layout inside `<main className="whiteboard">` (`WhiteboardPage`):

1. **Status line** — `div.wb-statusline`, a thin top bar with two clusters:
   - `div.wb-statusline-left`: the **File menu** (a `Popover` labelled "File"), the **WritingModeSelector**, and—only in Screenplay mode—an inferred-element chip `span.sp-element` (e.g. "Scene", "Dialogue").
   - `div.wb-statusline-right`: the **Draft autosave indicator** `span.wb-draft.wb-draft-{status}`, the **file-state chip** `span.wb-filestate` (with `.is-dirty` modifier), and the **EditorSettingsPopover** (Nerd Mode aids).
2. **Screenplay toolbar** — `div.wb-toolbar[role=toolbar]` (`ScreenplayToolbar`), rendered only when `mode === 'screenplay'`. Sits directly below the status line. Holds: Preview/Editing toggle, ⚙ Settings popover, a view-scale group (− / %, / +), a Format ▾ popover, an Export ▾ popover, a spacer, and an "Approx. pages" readout.
3. **Writing surface** — `div.wb-surface` (gets `.is-preview` modifier when the preview is open). Contains the `WhiteboardEditor` (TipTap `EditorContent.wb-content` wrapping `div.wb-editor`) and, when previewing, the `PreviewView` rendered alongside. Empty/loading/error hints render here as `p.wb-hint`.
4. **File menu popover** — `div.wb-menu.wb-menu-scroll`: New, Open…, Save, Save As…, an Import section (`IMPORT_FORMATS`), an Export section (`EXPORT_FORMATS`), and a disabled "Export as PDF… (planned)" item. Separators are `div.wb-menu-sep[role=separator]`; section captions are `div.wb-menu-label`.
5. **Document Settings popover** — `div.wb-settings` (`DocumentSettingsPanel`): Screenplay-only form (scene-heading style, blank lines before scene, typeface, two checkboxes). Opened from the ⚙ Settings popover in the toolbar.
6. **Format / Export popovers** — `div.wb-menu` lists in the toolbar (capitalization cycle, center line; fountain/copy export targets).
7. **Autocomplete popup** — `AutocompletePopup` (Screenplay character/scene-heading suggestions), rendered as a floating box driven by `useScreenplayAutocomplete`.
8. **LittleBoy (Logos) provider** — `LittleBoyProvider`, mounted when an editor + doc exist; the in-editor AI assistant (Cmd/Ctrl+K is reserved for it).
9. **Import/Export toast** — `div.wb-toast.wb-toast-{kind}[role=status]`, click-to-dismiss, bottom overlay.

### COMPONENTS
Containers (compose/route state) vs leaf controls (render/emit):

- `WhiteboardPage` — top container; owns all surface state and wiring. **Container.**
  - `Popover` (File) — container; render-prop child receives `close`. **Container.**
    - `button.wb-menu-item` ×N — **leaf** (New/Open/Save/Save As/import items/export items).
  - `WritingModeSelector` — **leaf control** (mode `<select>`-like control), disabled when `!doc`.
  - `span.sp-element` — **leaf** display chip.
  - `span.wb-draft` — **leaf** display.
  - `span.wb-filestate` — **leaf** display.
  - `EditorSettingsPopover` — container (Nerd Mode toggles + Reset). **Container.**
  - `ScreenplayToolbar` (Screenplay only) — **Container.**
    - `button.wb-tool` (Preview/Editing) — **leaf**, `aria-pressed`.
    - `Popover` (⚙ Settings) → `DocumentSettingsPanel` — container → leaf form.
    - `span.wb-tool-group` → three `button.wb-tool` (−, `wb-scale-pct`, +) — **leaf** controls.
    - `Popover` (Format ▾) → `div.wb-menu` → two `button.wb-menu-item` — **leaf**.
    - `Popover` (Export ▾) → `div.wb-menu` → `button.wb-menu-item` per `EXPORT_TARGETS` — **leaf**.
    - `span.wb-spacer`, `span.wb-pages` — **leaf** layout/display.
  - `div.wb-surface` — container; click-to-focus host.
    - `WhiteboardEditor` — container wrapping TipTap. **Container.**
      - `EditorContent.wb-content` → `div.wb-editor` (the ProseMirror editable). **Leaf surface.**
      - `AutocompletePopup` — **leaf** floating control.
    - `PreviewView` (conditional) — **leaf** rendered output.
  - `LittleBoyProvider` — container (AI assistant). **Container.**
  - `div.wb-toast` (conditional) — **leaf**.
- `DocumentSettingsPanel` leaves: `label.wb-field` rows with `<select>`s; `label.wb-field.wb-field-check` rows with `<input type=checkbox>`.

### USER INTERACTIONS
**Mouse / clicks**
- Click anywhere on empty `div.wb-surface` (when not previewing and the click target is the surface itself) → focuses the editor at the end (`editor?.chain().focus('end').run()`). See `WhiteboardPage` `onMouseDown`.
- File menu items: New/Open…/Save/Save As… → `fileDoc.newDocument/openDocument/saveDocument/saveDocumentAs`; Import items → `importExport.runImport(id)`; Export items → `importExport.runExport(id)`. Each closes the popover.
- WritingModeSelector change → `setMode` (from `useWhiteboardDocument`).
- Toolbar Preview/Editing button → `onTogglePreview` (`setPreview(p => !p)`).
- Scale buttons −/%,/+ → `onScale('smaller'|'actual'|'bigger')` → `applyScale` (`useEditorScale`).
- Format ▾ → "Capitalization (cycle)" `cycleSelectionCase(editor)`, "Center line" `toggleCenterLine(editor)`; both disabled when `!editor || preview`.
- Export ▾ → `runExport(id)`: `fountain` downloads `screenplay.fountain`; `copy-fountain` / `copy-preview` write to clipboard. Unavailable targets are disabled with a `· note` suffix.
- Settings selects/checkboxes → `update(key, value)` (`DocumentSettingsApi`).
- Toast click → `importExport.clearFeedback`.

**Keyboard** (global `keydown` in `WhiteboardPage`; mod = Ctrl or Cmd):
- `mod + =`/`+` → scale bigger; `mod + -`/`_` → scale smaller; `mod + 0` → actual size. All `preventDefault`.
- `mod + Shift + E` (Screenplay only) → toggle Preview.
- `mod + Shift + F` → toggle folding; `mod + Shift + H` → toggle syntax highlight; `mod + L` → toggle line numbers (Nerd Mode; work in every mode).
- `Esc` while previewing → exit preview, **unless** focus is inside `.wb-popover` or an INPUT/SELECT/TEXTAREA.
- `Cmd/Ctrl+K` is **reserved for Logos/LittleBoy** — do not bind it.
- `Cmd/Ctrl+\` → center line (Screenplay; via `screenplayKeyboard`).
- In-editor Screenplay typing triggers Fountain inference/formatting and autocomplete (`ScreenplayEditing` + `useScreenplayAutocomplete`); selection/typing updates the inferred element via `currentFountainType(ed)`.

**Focus / selection / autocomplete**
- Editor autofocuses at end on mount (`autofocus: 'end'`).
- `onSelectionUpdate`/`onUpdate` report the current Fountain element to the status-line chip.
- Autocomplete is offered by `onAutocomplete` and surfaced through `AutocompletePopup`; accept/dismiss is handled inside the screenplay autocomplete hook.

### STATES & MODES
**Document load states** (rendered in `div.wb-surface`):
- `!ready` → `p.wb-hint` "Waiting for backend…"
- `loading` → `p.wb-hint` "Loading…"
- `loadError` → `p.wb-hint.wb-error` "Couldn't load document: {error}"
- `doc` present → editor (+ optional Preview).

**Autosave (Draft) status** — `saveStatus: SaveStatus` ∈ idle/saving/saved/error, labelled via `DRAFT_LABEL` ("", "Draft saving…", "Draft saved", "Draft error"); class `wb-draft-{status}`. This is the **backend session autosave**, deliberately distinct from file save.

**File state** — `fileDoc.status` (saving/error/idle), `fileDoc.dirty`, `fileDoc.fileName`, `fileDoc.filePath`. Rendered in `span.wb-filestate` (with `.is-dirty`); text via `fileStateLabel(...)`. Also drives `document.title` via `windowTitle(fileName, dirty)`.

**Writing modes** (`mode = doc?.mode ?? defaultMode`): `novel`, `screenplay`, `graphic_novel`, `stage`, `series` (from `useWritingModes`). Mode is reflected on the editor DOM as `data-writing-mode={mode}` and drives `--measure` (`modeBehavior(mode).measure`) on the surface.
- **Screenplay-specific UI:** the `ScreenplayToolbar`, the `sp-element` chip, the Preview toggle, Document Settings, and the Fountain engine all appear/activate only when `isScreenplay`. The surface gets `data-screenplay` + the settings `data-*` attributes. Leaving Screenplay mode forces `setPreview(false)`.
- **Preview mode** (`showPreview = isScreenplay && preview`): `div.wb-surface.is-preview`; `PreviewView` rendered beside the editor; Format actions disabled while previewing.

**Nerd Mode (Editor Tools)** — `editorTools: EditorToolsState` (line numbers / folding / syntax, all default off). Reflected via `editorToolsVars(...)` (CSS vars) and `editorToolsAttrs(...)` (data-attrs) on the surface, plus `folds: Set<number>`. Reset via `resetEditorView` (clears tools + folds).

**Scale** — `scale` number → CSS var `--wb-scale`; percentage shown via `scaleToPct(scale)`.

### DATA & API
- **`useWhiteboardDocument({ baseUrl, ready })`** → `{ doc, loading, loadError, saveStatus, onChangeBlocks, setMode }`. The document/backend autosave contract. `doc` shape: `{ id, title, mode, blocks }`; `blocks: WhiteboardBlock[]` (`./types`).
- **`WhiteboardBlock`** (the load-bearing backend contract): `{ id, type: 'heading'|'paragraph', text, level?, sp? }`. Mapped to/from ProseMirror by `blocksToDoc` / `docToBlocks` in `WhiteboardEditor.tsx` (heading carries `attrs.level`; paragraph carries `attrs.sp`).
- **`useWritingModes({ baseUrl, ready })`** → `{ modes, defaultMode }` for the selector.
- **`useDocumentSettings()`** → `DocumentSettingsApi` `{ settings, update, replace }`; `DocumentSettings` persisted to `localStorage` key `logosforge-doc-settings` (`documentSettings.ts`, `loadSettings`/`saveSettings`). `surfaceDataAttrs(settings)` emits `data-scene-style`, `data-scene-blank`, `data-typeface`, `data-invisibles`.
- **`useEditorScale()`** → `{ scale, apply }` (+ `scaleToPct`, `ScaleAction` from `editorScale`).
- **`useEditorTools()`** → `{ tools, toggle, reset }`; **`useFolding()`** → `{ folds, toggleFold, clearFolds }`.
- **`useFileActions({ getBlocks, loadBlocks, mode })`** → `fileDoc` (New/Open/Save/Save As, dirty/status/fileName/filePath, `markDirty`, `confirmProceedPastUnsavedChanges`).
- **`useImportExport({...})`** → `{ runImport, runExport, feedback, clearFeedback }`; formats from `IMPORT_FORMATS`/`EXPORT_FORMATS` (`files/importExportFormats`).
- **Screenplay engine:** `ScreenplayEditing`/`fountainKey`/`currentFountainType` (`screenplay/screenplayExtension`), `useScreenplayAutocomplete`, `toFountainBlocks`/`blocksToFountainText` (`screenplayExport`), `EXPORT_TARGETS`, `buildPreview`/`previewToPlainText` (`screenplayPreview`), `approxPageCount` (`screenplayPageCount`), `screenplayLabel` (`screenplayClassifier`), `cycleSelectionCase`/`toggleCenterLine` (`screenplayKeyboard`).
- **Outline:** `deriveOutline(blocks, mode)` (`outline/deriveOutline`) is recomputed on edit/load/mode-change and pushed up via `onOutlineChange`. `onModeChange` surfaces the mode to the shell.
- **AI:** `LittleBoyProvider` (`littleboy/LittleBoyProvider`) takes `editor`, `mode`, `baseUrl`, `documentTitle`, `screenplayElement`.

### RESTYLE SURFACE (safe to redesign freely)
- All spacing, padding, sizing, color, borders, shadows, radii, and background of: `.whiteboard`, `.wb-statusline`/`-left`/`-right`, `.wb-toolbar`, `.wb-surface`, `.wb-content`, `.wb-editor`, `.wb-menu`/`.wb-menu-item`/`.wb-menu-sep`/`.wb-menu-label`/`.wb-menu-soon`, `.wb-tool`/`.wb-tool-group`/`.wb-scale-pct`, `.wb-spacer`, `.wb-pages`, `.wb-draft*`, `.wb-filestate`, `.wb-hint`/`.wb-error`, `.wb-toast*`, `.sp-element`, `.wb-settings`/`.wb-settings-title`/`.wb-field`/`.wb-field-check`.
- Typography of the writing surface, including per-mode type via `[data-writing-mode]` and Screenplay typefaces via `[data-typeface]`/`[data-scene-style]`/`[data-scene-blank]`/`[data-invisibles]` — provided the attribute selectors and their value sets are preserved (see invariants).
- Iconography and labels of toolbar/menu controls (the ⚙, ▾, −/+, "Preview"/"Editing", "Format", "Export" are free to restyle/relabel).
- Motion: popover open/close, toast in/out, focus transitions, hover states.
- Layout of the status line and toolbar (reflow, regroup, reorder visually, move to a sidebar) as long as the controls and their handlers survive.
- Preview layout (side-by-side vs stacked) for `.wb-surface.is-preview`.

### LOGIC INVARIANTS (must preserve)
**DOM hooks / attributes consumed by logic & CSS:**
- `div.wb-surface` must remain the click-to-focus host and keep the `onMouseDown` target check intact — the focus-on-empty-click relies on `e.target === e.currentTarget`. Don't wrap the editor in extra full-bleed layers that intercept this.
- The surface must keep applying `--measure`, `--wb-scale`, `editorToolsVars`, and, in Screenplay, `data-screenplay` + `surfaceDataAttrs` values (`data-scene-style`, `data-scene-blank`, `data-typeface`, `data-invisibles`) and `editorToolsAttrs`. The Preview reads these same attributes to stay visually in sync (`documentSettings.ts` comment) — keep the attribute names and their enum values (`SceneHeadingStyle`, `Typeface`, `'on'|'off'`, `'1'|'2'`).
- `data-writing-mode={mode}` is set on `editor.view.dom` (`WhiteboardEditor` effect) and is the source for per-mode typography — preserve this attribute and its value set (`novel`/`screenplay`/`graphic_novel`/`stage`/`series`).
- `.wb-popover` is the class the `Esc`-to-exit-preview guard checks (`ae.closest('.wb-popover')`); the `Popover` component must keep emitting it, or Esc inside a popover will close Preview. Likewise the guard checks `INPUT/SELECT/TEXTAREA` tag names — keep settings controls as native form elements (or update the guard).
- Editor class names `wb-editor` (ProseMirror `attributes.class`) and `wb-content` (`EditorContent`) are referenced by editor-tools/folding/screenplay CSS and decorations — keep them.

**Keyboard contracts** (global handler in `WhiteboardPage`): preserve `mod +`/`-`/`0` (scale), `mod+Shift+E` (Preview, Screenplay), `mod+Shift+F`/`mod+Shift+H`/`mod+L` (Nerd Mode), and `Esc` (exit preview with the focus guard). **`Cmd/Ctrl+K` must stay unbound here** (reserved for Logos). `Cmd/Ctrl+\` (center line) is handled in the screenplay layer. A redesign must not add elements that swallow these or steal focus in a way that breaks them.

**Data flow / ordering:**
- The block↔ProseMirror mapping (`blocksToDoc`/`docToBlocks`) and the `WhiteboardBlock` shape are the backend contract — do not change field names (`type`, `text`, `level`, `sp`) or the heading/paragraph mapping.
- `<WhiteboardEditor key={doc.id} …>` remounts on document change — keep the `key={doc.id}` so loading a new doc resets the editor. `loadBlocks` uses `editor.commands.setContent(blocksToDoc(blocks), true)`.
- On every edit: `markFileDirty()` → `setLiveBlocks` → `onChangeBlocks` → `deriveOutline` (order in `handleBlocks`); outline + live snapshot + autosave depend on it.
- Mode switch keeps current content (re-derives outline from live blocks, not `doc.blocks`); only a different `doc.id` resets `liveBlocks` (see the load `useEffect`). Preserve this distinction.
- The two save indicators are semantically distinct: `.wb-draft` = backend autosave/session; `.wb-filestate` = file-on-disk. **Do not merge or relabel them into one "saved" indicator** — the code and the comments treat them as different sources of truth.
- Disabled states are meaningful: Format actions disabled when `!editor || preview`; Export targets disabled by `!t.available`; the planned PDF/export items are intentionally `disabled`. Keep disabled semantics (don't make planned items look clickable).

**Accessibility affordances to keep:** `div.wb-toolbar[role=toolbar][aria-label="Screenplay tools"]`; Preview button `aria-pressed={preview}`; scale group `aria-label="View scale"`; menu separators `role="separator"`; toast `role="status"`; titles/tooltips on tools and the file-state chip; `<label>`-wrapped form fields in `DocumentSettingsPanel`. Maintain a visible focus indicator and logical tab order across the restyle.

### CURRENT LOOK
A minimal, three-band stack on a near-full-bleed sheet. A thin top **status line** (File menu + mode selector on the left; small monochrome draft/file-state text and a settings gear on the right). When in Screenplay mode, a compact **toolbar row** appears below it with small bordered text buttons (Preview/Editing toggle that turns "active", a ⚙ Settings popover, a − % + scale cluster, Format ▾ and Export ▾ dropdowns, a flexible spacer, and a faint "Approx. pages: N" readout on the far right). The bulk of the screen is the **writing sheet** (`.wb-surface`/`.wb-content`/`.wb-editor`), a centered measure-constrained column that scales with `--wb-scale`; Screenplay applies a monospace/Courier-style typeface and Fountain formatting, and Preview splits the sheet to show a formatted screenplay beside the editor. Popovers (File, Settings, Format, Export) are simple vertical `.wb-menu`/`.wb-settings` lists/forms. Toasts appear as a small dismissible status pill. The aesthetic is deliberately spare and writing-first.

---

## Screenplay Editing (Fountain)

### PURPOSE
The Screenplay area turns the otherwise prose-first Whiteboard into a Fountain-aware screenwriting surface: as the writer types, an inference engine classifies each line into screenplay elements (scene headings, action, character, dialogue, etc.) and formats them live, with autocomplete, a readable Preview, an approximate page count, light export, and per-document typography settings. It is deliberately minimal (Free tier) — a clean foundation, not a production paginator.

### SURFACES / SCREENS
All screenplay surfaces live inside the single full-panel Whiteboard sheet (`WhiteboardPage.tsx`), stacked top-to-bottom:

1. **Status line** (`.wb-statusline`, top bar) — hosts the File menu, the `WritingModeSelector`, and, only in Screenplay mode, the **inferred-element chip** (`.sp-element`, text from `screenplayLabel(element)`). Right side holds draft/file-state indicators and the editor-tools popover (shared, not screenplay-specific).
2. **Screenplay toolbar** (`.wb-toolbar`, `ScreenplayToolbar.tsx`) — rendered only when `mode === 'screenplay'`. A compact horizontal toolbar: Preview/Editing toggle button, **Settings** popover, a view-scale group (− / percent / +), a **Format ▾** popover-menu, an **Export ▾** popover-menu, a spacer, and the **Approx. pages** readout (`.wb-pages`).
3. **Writing surface / sheet** (`.wb-surface`, with `data-screenplay` and typography data-attrs) — the full-panel scrolling paper. Inside it:
   - **Editor column** (`.wb-content` → `.wb-editor`, `WhiteboardEditor.tsx`) — the TipTap/ProseMirror editable, centered at a mode-specific `--measure` width (`63ch` for screenplay).
   - **Preview pane** (`.wb-preview`, `PreviewView.tsx`) — rendered alongside the editor when Preview is on; the surface gets `.is-preview` which hides the editor column visually.
4. **Autocomplete popup** (`.sp-autocomplete`, `AutocompletePopup.tsx`) — a floating box positioned at the caret (`left`/`top` from `editor.view.coordsAtPos`), containing a filter `<input>` over a scrollable suggestion `<ul>`. Rendered as a sibling of `EditorContent`.
5. **Document Settings panel** (`.wb-settings`, `DocumentSettingsPanel.tsx`) — a small form inside the Settings `Popover`.
6. **Format / Export menus** (`.wb-menu` inside `Popover`) — vertical button lists.

### COMPONENTS
Hierarchy (containers ▸ leaves):

- `WhiteboardPage` (container) — owns `preview`, `element`, `liveBlocks`, `editor`, `settingsApi`, `scale` state; mounts everything below.
  - `ScreenplayToolbar` (container) — leaves: Preview toggle `<button>`; `Popover` "⚙ Settings" ▸ `DocumentSettingsPanel` (leaf form of `<select>`/`<input type=checkbox>`); scale `<button>` group; `Popover` "Format ▾" ▸ `.wb-menu` buttons (Capitalization, Center line); `Popover` "Export ▾" ▸ `.wb-menu` buttons from `EXPORT_TARGETS`; `.wb-pages` span (leaf).
  - `WhiteboardEditor` (container) — `EditorContent` (the `.wb-editor`); `AutocompletePopup` (leaf-ish popup). Wires `ScreenplayEditing` TipTap extension + `useScreenplayAutocomplete`.
  - `PreviewView` (container, shown when `showPreview`) — `.sp-pv-titlepage` block + `.sp-pv-body` of `<p class="sp-{type}">`; inner `Inline` component (leaf) renders emphasis segments as `<strong>/<em>/<u>/<span>`.
- `Popover` (`components/Popover.tsx`) — generic container used by Settings/Format/Export; trigger `.wb-tool` button + `.wb-popover-panel` dialog.

Pure logic modules (no DOM) that the components depend on: `screenplayClassifier`, `screenplayAutocomplete`, `fountainParser`, `screenplayPreview`, `screenplayFormatting`, `screenplayKeyboard`, `screenplayPageCount`, `screenplayTitlePage`, `screenplaySections`, `screenplayBoneyard`, `screenplayCommands`, `screenplayExport`, `fountainTypes`.

### USER INTERACTIONS
- **Typing** — `onUpdate`/`onSelectionUpdate` re-run `currentFountainType(editor)` and the live classifier; each paragraph gets an `sp-{type}` decoration via `buildDecorations`. No Enter override — the next line is classified by context (`screenplayClassifier.classify`, `prev`-aware).
- **Tab** (`handleTab`): on a heading/Section → deepens it one level (`sectionTabLevel`, capped at 3); on a paragraph → opens the autocomplete popup pre-filled with the current line text; **always consumes Tab** so focus never leaves the editor.
- **Shift+Tab** (`handleShiftTab`): on a Section → shallows one level, or converts to paragraph at level 1 (`sectionShiftTabLevel` → 0); otherwise safe no-op.
- **Autocomplete popup**: opens focused; typing filters (`filterSuggestions`, prefix-then-substring); ArrowUp/ArrowDown move highlight; Enter or Tab choose; Escape or blur dismiss; mouse selection uses `onMouseDown` (fires before blur) so a click isn't cancelled. Choosing replaces the whole current line via `onSelect` → `insertContentAt({from,to})`.
- **Emphasis shortcuts**: `Cmd/Ctrl+B` → `**…**`, `Cmd/Ctrl+I` → `*…*`, `Cmd/Ctrl+U` → `_…_` (wrap selection or insert empty pair with caret between).
- **Note / Omit**: `Cmd/Ctrl+Alt+N` wraps `[[ … ]]`; `Cmd/Ctrl+Alt+O` wraps boneyard `/* … */`. (Cmd/Ctrl+Y intentionally NOT used — it is redo.)
- **Center line**: `Cmd/Ctrl+\` or Format ▸ "Center line" → `toggleCenterLine` (wraps/unwraps `> … <`).
- **Capitalization**: Format ▸ "Capitalization (cycle)" → `cycleSelectionCase` (lowercase → UPPER → Sentence case).
- **Preview toggle**: toolbar button or `Cmd/Ctrl+Shift+E`; **Escape** exits Preview (unless focus is in a popover/INPUT/SELECT/TEXTAREA).
- **View scale**: toolbar − / percent / + buttons, or `Cmd/Ctrl+ -/=/0`.
- **Export menu**: `fountain` downloads `screenplay.fountain`; `copy-fountain` and `copy-preview` write to clipboard; `pdf`/`fdx`/`print` are disabled (`available:false`, "Planned").
- **Settings form**: changing any `<select>`/checkbox calls `update(key,value)`, persisted to localStorage and reflected as `data-*` attrs on the surface.
- **Click on empty sheet**: focuses the editor at end (only when not in Preview, only when the target is the surface itself).

### STATES & MODES
- **Writing modes** (`modes.ts` registry): `screenplay` is the only Fountain mode (`fountain:true`, mono font, `outline:'fountain'`, `measure:'63ch'`). `stage_script` is mono but **not** Fountain. `novel`, `graphic_novel`, `series` are prose (`fountain:false`, serif, headings outline). The entire screenplay UI (toolbar, element chip, `data-screenplay`, Preview, page count) is gated on `isScreenplay = mode === 'screenplay'`. Leaving screenplay mode forces Preview off.
- **Engine on/off**: formatting decorations only apply when the `fountainKey` plugin state has `screenplay:true`, set by a meta transaction in `WhiteboardEditor` (not DOM timing). The surface also carries `data-writing-mode` for CSS gating.
- **Preview vs Editing**: `showPreview = isScreenplay && preview`; surface toggles `.is-preview`. Button label flips "Preview"/"Editing", `aria-pressed` tracks state.
- **Document loading states** (in the surface): "Waiting for backend…" (`!ready`), "Loading…", error "Couldn't load document: …" (`.wb-error`), else the editor.
- **Empty Preview**: `.sp-pv-empty` "Nothing to preview yet." when `preview.lines.length === 0`. Empty editor shows only the caret (no placeholder).
- **Autocomplete empty**: `.sp-ac-empty` "No matches".
- **Element chip**: always shows a label (defaults to "Action" for null/empty via `screenplayLabel`).
- **Per-setting variants**: `data-scene-style` (normal/bold/underline/bold-underline), `data-scene-blank` (1/2), `data-typeface` (courier-prime/courier/monospace), `data-invisibles` (on/off — toggles emphasis-marker visibility).

### DATA & API
This area is **client-only / pure** — no screenplay-specific backend endpoints. Data flows through the Whiteboard document contract:

- **Document store**: `useWhiteboardDocument` provides `doc` (`{id, mode, blocks, title}`), `saveStatus`, `onChangeBlocks`, `setMode`. `useWritingModes` provides the mode list/default. Backend autosave is the only network dependency, and it is generic (blocks), not screenplay-aware.
- **Settings store**: `useDocumentSettings` (→ `documentSettings.ts`) — `DocumentSettings` persisted in `localStorage` key `logosforge-doc-settings`. `surfaceDataAttrs(settings)` produces the `data-*` attrs.
- **Autocomplete hook**: `useScreenplayAutocomplete` (`onAutocomplete`, `setEditor`, `popup`) — popup state shape `PopupProps {open,left,top,query,suggestions,onSelect,onClose}`.
- **Core data shapes** (the restyle must preserve these):
  - `WhiteboardBlock` `{id, type:'paragraph'|'heading', text, level?, sp?}` → `FountainBlock` `{text, isHeading, level?}` via `toFountainBlocks`.
  - `FountainType` (12-member union) and `screenplayLabel` LABELS map.
  - `Preview` `{titlePage: Record<string,string>, lines: PreviewLine[]}`, `PreviewLine {type, text}`, `Segment {text, cls}`.
  - `TitlePage {fields, endIndex}`; `EmphasisRange {from,to,className}`; `EXPORT_TARGETS: ExportTarget[]`.
- Key functions consumed by UI: `classify`, `extractCharacters/SceneHeadings/Transitions`, `computeSuggestions`, `filterSuggestions`, `buildPreview`, `previewSegments`, `previewToPlainText`, `approxPageCount`, `buildDecorations`, `currentFountainType`, `blocksToFountainText`.

### RESTYLE SURFACE (safe to redesign freely)
- All colors, fills, borders, radii, shadows, spacing/margins, and motion for: the element chip (`.sp-element`), toolbar (`.wb-toolbar`, `.wb-tool`, `.wb-tool-group`, `.wb-scale-pct`, `.wb-pages`, `.wb-spacer`), popovers/menus (`.wb-popover`, `.wb-popover-panel`, `.wb-menu`, `.wb-menu-item`, `.wb-menu-sep`, `.wb-menu-label`, `.wb-menu-soon`), settings form (`.wb-settings`, `.wb-field`, `.wb-field-check`).
- Autocomplete popup chrome: `.sp-autocomplete`, `.sp-ac-input`, `.sp-ac-list`, `.sp-ac-item`, `.is-active`, `.sp-ac-empty`, scrollbar styling.
- Screenplay element typography/indents (within reason): `.sp-scene_heading`, `.sp-character`, `.sp-dialogue`, `.sp-parenthetical`, `.sp-transition`, `.sp-section`, `.sp-synopsis`, `.sp-note`, `.sp-centered`, `.sp-page_break`, `.sp-title-page`, `.sp-boneyard`, and emphasis classes `.sp-bold/.sp-italic/.sp-bold-italic/.sp-underline/.sp-emph-marker`.
- Preview look: `.wb-preview`, `.sp-pv-titlepage`, `.sp-pv-title`, `.sp-pv-credit`, `.sp-pv-author`, `.sp-pv-meta`, `.sp-pv-body`, `.sp-pv-empty`.
- Surface paper background, scale ramp visuals, iconography for the toolbar labels (currently text/glyphs like "⚙", "▾", "−/+").
- Button label text strings (Preview/Editing, menu items) are visual copy and may be restyled, but their `onClick` wiring must stay.

### LOGIC INVARIANTS (must preserve)
- **Class hooks driving live formatting**: ProseMirror decorations emit exact classes `sp-{FountainType}`, `sp-title-page`, `sp-boneyard`, and inline `sp-bold/sp-italic/sp-bold-italic/sp-underline/sp-emph-marker` (see `screenplayFormatting.buildDecorations` and `fountainParser.parseEmphasis`). Renaming any of these breaks visual formatting silently. Preview reuses the same `sp-{type}` and `sp-*` emphasis classes (`PreviewView.Inline`, `screenplayPreview.previewSegments`).
- **Mode/engine gating attributes**: `data-writing-mode` on `.wb-editor` (set in `WhiteboardEditor` effect; read by `screenplayKeyboard.isScreenplay`) and `data-screenplay` + `data-scene-style`/`data-scene-blank`/`data-typeface`/`data-invisibles` on `.wb-surface` (from `surfaceDataAttrs`) are behavioral contracts — `isScreenplay` reads `data-writing-mode === 'screenplay'` to decide whether Tab consumes/opens autocomplete. Do not drop or rename these.
- **`--measure` CSS var** must remain the editor column width source (`modes.measure`); `--wb-scale` drives font scale. Don't hardcode widths over them.
- **Keyboard contract** (unchangeable bindings): Tab/Shift+Tab (autocomplete + section depth), `Mod-b/i/u`, `Mod-Alt-n`, `Mod-Alt-o`, `Mod-\`, `Cmd/Ctrl+Shift+E` (Preview), `Cmd/Ctrl +/-/0` (scale), Escape (exit Preview). `Cmd/Ctrl+K` must stay unbound (reserved for Logos). Enter must NOT be bound.
- **Autocomplete a11y/behavioral**: popup `role="listbox"`, items `role="option"` with `aria-selected`, the filter input keeps `aria-label`; selection MUST use `onMouseDown` with `preventDefault` (click-after-blur would cancel selection). Keep the input auto-focused on open and re-seeded from `query`.
- **Escape-in-Preview guard**: keep the check that ignores Escape when focus is inside `.wb-popover` or an INPUT/SELECT/TEXTAREA (`WhiteboardPage` keydown). Popover relies on `.wb-popover` for outside-click and on the trigger `.wb-tool`.
- **Element ordering & labels**: `screenplayLabel` LABELS map and `FountainType` order must stay; the chip always shows a label (null→"Action").
- **Export semantics**: `EXPORT_TARGETS` `available` flags gate `disabled`; disabled targets must stay disabled. `runExport` ids (`fountain`/`copy-fountain`/`copy-preview`) are load-bearing strings.
- **Notes/boneyard are kept in the document but excluded** from Preview/export (`stripForExport`, `detectBoneyard`); preserve the dimmed-but-present rendering rather than deleting content.
- **Block contract**: heading nodes ↔ Fountain Sections (`#`), paragraphs carry the back-compat `sp` data attribute (`screenplayExtension.addGlobalAttributes`); `blocksToDoc`/`docToBlocks` round-trip must be preserved.

### CURRENT LOOK
Top-to-bottom: a thin status line with a pill-shaped element chip (`.sp-element` — rounded `999px`, 11px muted text, 1px border). Below it a single-row toolbar of small text buttons (`.wb-tool`) with `▾`/glyph affordances and an active state (`is-active`); the page-count readout sits flush-right after a flex spacer. The sheet (`.wb-surface`) is full-bleed "paper" (`--paper`) that scrolls; the editor column is centered at `63ch` in Courier Prime monospace (16px × scale, line-height 1.6). Screenplay elements are formatted by `ch`-based indents: scene headings bold/uppercase with top margin, character cues uppercase indented ~20ch, dialogue inset 10/12ch, parentheticals italic at 16ch, transitions right-aligned uppercase, sections accent-colored bold, synopses/notes/boneyard muted-italic, page breaks a dashed centered divider, emphasis markers dimmed to 0.35 opacity. The autocomplete popup is a small floating card: a focused filter input atop a scrolling list with a highlighted active row. Preview is a separate centered column with a subtle title-page block above readable, indented screenplay lines. Popovers (Settings/Format/Export) are simple floating panels of stacked buttons/form fields.

---

## Outline / Outliner

### PURPOSE
The left-side **Outline** panel is Whiteboard Free's lightweight story-structure tool. It offers two distinct views behind one toggle: a **manual, editable, persisted outliner** (a Dynalist-style tree of acts/chapters/scenes/beats/notes with status, color, tags, and zoom) and a **read-only "From Document" navigator** derived live from the current editor content (headings / scene-headings / synopses / notes) that scrolls the editor to the clicked spot.

### SURFACES / SCREENS
All surfaces live inside a single hideable left panel (`<aside class="outline-panel">`, `aria-label="Outline"` — `OutlinePanel.tsx`). Top to bottom:

- **Outline header** (`.outline-header`) — a title label ("Outline") plus a 2-button segmented **view toggle** (`.outline-view-toggle`, `role="group"`): "Outline" (manual) and "From Document" (derived). The chosen view is persisted to `localStorage` key `lf-outline-view`.
- **Manual view** (`ManualView`) shows, stacked:
  - **Toolbar** (`.outline-toolbar`): `+ Add`, `Collapse all`, `Expand all`, and a right-aligned **save status** chip (`.outline-save`, `aria-live="polite"`).
  - **Search bar** (`.outline-searchbar`): a `type="search"` input plus a **Filter popover** (a `Popover` triggered by a `⛃` glyph; align right) containing Type / Status / Color `<select>`s and a "Clear filters" button.
  - **Active-filter banner** (`.outline-filter-active`): shown only when a filter is active; displays "Filtered · #tag" and a "Clear" inline link.
  - **Body** (`.outline-body`): loading hint, error hint, or the `OutlineOutliner` tree.
  - Inside the outliner: an optional **zoom breadcrumb bar** (`<nav class="outline-breadcrumbs">`) when zoomed into an item, then the tree (`<ul class="outline-tree">`) of rows, or an empty-state hint.
- **Each row** (`OutlineRow`, `<li class="outline-node">`) is a multi-part main line plus two conditional sub-blocks:
  - **Tag line** (`.outline-tags`) when the node has tags.
  - **Details panel** (`.outline-details`) when this row's details are open — an inline editor with Type/Status/Color selects, a tag editor, a notes textarea, and Link/Done actions. Plus a per-row **actions popover** (`⋯`, `.outline-menu`).
- **Derived view** (`DerivedView`) shows an optional **kind-filter bar** (`.outline-filters`, buttons per present kind) and a flat `<ul class="outline-list">` of clickable navigation items.

### COMPONENTS
Hierarchy (containers → leaves):

- `OutlinePanel` (container; owns `view` state and the `useOutline` store)
  - `ManualView` (container)
    - toolbar buttons (leaf), save chip (leaf)
    - search input (leaf), `Popover` → filter menu with three `<select>` + clear button (leaf controls)
    - `OutlineOutliner` (container; computes visible rows, owns the keyboard handler and delete-confirm)
      - breadcrumb `nav` (leaf controls)
      - `OutlineRow` × N (container per node)
        - disclosure toggle, completed checkbox, color dot, type label, title (button when unselected / `<input>` when selected), status badge, row actions (`+` and `⋯` `Popover` → `.outline-menu`), tag chips, details panel (`<select>`s, tag editor input/chips, notes `<textarea>`, Link/Done)
  - `DerivedView` (container; owns local `hidden: Set<OutlineKind>` state)
    - kind-filter buttons (leaf)
    - `.outline-item` navigation buttons (leaf)
- Shared dependency: `Popover` (`../../components/Popover`) for both the filter menu and the per-row action menu.

### USER INTERACTIONS

**View toggle:** clicking "Outline" / "From Document" sets `view` and persists it (`selectView`).

**Manual view — toolbar / search / filter:**
- `+ Add` → adds a child of the current zoom root if zoomed, else a new top-level root (`ManualView.add`); the new node becomes selected and autofocuses.
- `Collapse all` / `Expand all` → `store.collapseAll` / `store.expandAll`.
- Search input → `store.setFilter({ query })`; live-filters the tree.
- Filter popover selects → `setFilter({ type | status | color })`; "Clear filters" / banner "Clear" → `store.clearFilter`.
- Tag chip on a row → `store.setFilter({ tag })` (filter by that tag).

**Manual view — mouse on a row (`OutlineRow`):**
- Disclosure ▸/▾ click → `store.toggleCollapse`; **Alt+click** → `store.collapseBranch` (recursive whole branch).
- Completed checkbox → `store.toggleCompleted` (adds `.is-completed` to the row).
- Type label **double-click** → `store.zoomInto(node.id)`.
- Title button (unselected) click → `store.setSelectedId(node.id)` (enters edit mode).
- Row actions `+` → `store.addChild`. `⋯` popover items: Add child, Rename, Edit details/note (toggle), Zoom into item, Mark done/not done, Duplicate, Delete (danger).
- Details panel: Type/Status/Color selects → `store.setType` / `setStatus` / `setColorLabel`; tag chips `#tag ×` → `removeTag`; tag input commits on Enter or blur (`commitTag` → `store.addTag`); notes textarea → `store.setNotes`; "Link to editor" is **disabled** ("coming soon"); "Done" → `setDetailsOpenId(null)`.

**Manual view — keyboard (only while a row title `<input>` is focused; handler `OutlineOutliner.handleKey`, dispatched from `OutlineRow`'s `onKeyDown` which computes `atStart`/`atEnd` from caret position):**
- `Enter` → new sibling below (`addSibling`). `Shift+Enter` → toggle details/notes. `Ctrl/Cmd+Enter` → add child.
- `Tab` / `Shift+Tab` → `indent` / `outdent`.
- `Arrow Up`/`Down` → move selection; `Ctrl/Cmd+Arrow Up`/`Down` → move the item among siblings (`moveUp`/`moveDown`).
- `Arrow Left` (only at caret start) → collapse if expanded-with-children, else select parent. `Arrow Right` (only at caret end) → expand if collapsed, else select first child.
- `Ctrl/Cmd+]` → zoom into; `Ctrl/Cmd+[` → zoom out.
- `Backspace`/`Delete` when title is empty → delete (with `window.confirm` if it has children, via `confirmDelete`).
- `Escape` → deselect and blur.

**Zoom breadcrumbs:** "Outline" crumb → `setZoomRootId(null)`; intermediate crumb → `setZoomRootId(n.id)`; last crumb is `disabled`.

**Derived view:** kind-filter button → toggles that kind in `hidden`; navigation item click → `onNavigate?.(item)` (parent scrolls the editor to `item.blockIndex`).

### STATES & MODES
- **Loading** (`store.loading`): body shows `<p class="outline-hint">Loading…</p>`.
- **Error** (`store.error`): `<p class="outline-hint outline-error">Couldn't load outline: …</p>`.
- **Empty (manual):** distinct hints — no items → "No outline yet. Use **+ Add**…"; zoomed but empty → "Empty — add an item under this one."; filtering with no matches → "No matches. [Clear filter]".
- **Empty (derived):** "No structure in the document yet." (when `items.length === 0`) vs "All hidden." (all kinds toggled off).
- **Save state** (`store.saveState`: `idle | saving | saved | error`): chip text via `SAVE_LABEL` ("Saving…" / "Saved" / "Save failed"); class `outline-save-${saveState}`; `idle` renders empty.
- **Selection / details:** selected row gets `.is-selected` and swaps title button → input (autofocus, caret-at-end via the `useEffect` in `OutlineRow`); `detailsOpenId` controls the inline details panel.
- **Filter active:** `isFilterActive` drives the banner and changes empty-state copy; when filtering, `buildRows` ignores collapse and shows matches + ancestors.
- **Writing-mode variants (`mode` prop):** mode does **not** change layout but drives **default item types** via `rootType(mode)` and `childType(mode, parentType)` (e.g. screenplay → act › sequence › scene › beat › note; novel → chapter › scene › beat; series → part › chapter…; scene → scene › beat; notes → note). Derived view's parser also depends on mode: `deriveOutline` uses Fountain parsing when `modeBehavior(mode).outline === 'fountain'` (Sections/Scene-headings/Synopses/Notes), else Markdown headings.

### DATA & API
- **Store hook:** `useOutline({ baseUrl, ready, mode })` → `OutlineStore` (in `useOutline.ts`). Owns items, loading/error/saveState, selection, detailsOpenId, zoom, filter, and all mutations. Autosaves with a **600 ms debounce** (`SAVE_DEBOUNCE_MS`), flushes on unmount, and reloads on an out-of-band refresh event.
- **API module** `outlineApi.ts`:
  - `getOutlineItems(baseUrl, signal)` → `GET /api/outline/items` → `{ items }`.
  - `saveOutlineItems(baseUrl, items)` → `PUT /api/outline/items` with `{ items }`.
  - Defensive `normalize()` tolerates partial/legacy rows; unknown type/status/color fall back to `custom`/`none`/`none`.
  - `emitOutlineRefresh()` / `onOutlineRefresh(cb)` over the window event `lf:outline-refresh` (used by e.g. LogosForge import to trigger a reload).
- **Data shapes:** `OutlineNode` (manual model — `id`, `parentId`, `type`, `title`, `notes`, `order`, `collapsed`, `completed`, `status`, `tags`, `colorLabel`, `linkedLineId`, timestamps) defined in `outlineModel.ts`; the tree is **derived** from this flat list (`parentId` + `order`). `OutlineItem` (derived navigator — `id`, `label`, `kind`, `level`, `blockIndex`) in `./types`, produced by `deriveOutline(blocks, mode)` (`deriveOutline.ts`).
- **localStorage keys:** `lf-outline-view` (panel view), `lf-outline-zoom` (zoom root id).
- **Constant tables** (`outlineModel.ts`): `OUTLINE_TYPES`/`TYPE_LABELS`, `OUTLINE_STATUSES`/`STATUS_LABELS`/`STATUS_BADGE`, `OUTLINE_COLORS`/`COLOR_LABELS` — these define dropdown options and badge/label text.

### RESTYLE SURFACE (safe to redesign freely)
- All spacing, colors, typography, borders, radii, motion, and panel chrome for: `.outline-panel`, `.outline-header`, `.outline-title-label`, `.outline-view-toggle`/`.outline-view`, `.outline-toolbar`/`.outline-tool`, `.outline-save*`, `.outline-searchbar`/`.outline-search`, `.outline-filter-menu`/`.outline-field`, `.outline-filter-active`/`.outline-inline-link`, `.outline-breadcrumbs`/`.outline-crumb*`, `.outline-tree`/`.outline-node`/`.outline-row`, `.outline-disclosure`(+`-leaf`), `.outline-check`, `.outline-color-dot`/`.outline-color-*`, `.outline-type`, `.outline-title`/`.outline-title-input`/`.is-untitled`, `.outline-status`/`.outline-status-*`, `.outline-row-actions`/`.outline-act`/`.outline-menu`, `.outline-tags`/`.outline-tag-chip`/`.outline-tag-edit`/`.outline-tag-input`, `.outline-details*`/`.outline-notes`, `.outline-hint`/`.outline-error`, and derived `.outline-filters`/`.outline-filter`, `.outline-list`/`.outline-item`/`.outline-section|scene|synopsis|note`.
- The glyphs are decorative and replaceable with icons: disclosure `▸`/`▾`, leaf `•`, filter trigger `⛃`, breadcrumb separator `›`, add `+`, overflow `⋯`. Status badge **text** (`STATUS_BADGE`) and type/color/status **labels** are content you may rephrase, but keep them mapped to the same enum values.
- The segmented toggle, filter popover, breadcrumb bar, and per-row details/actions can be visually re-laid-out (e.g. icon buttons, different placement) as long as the controls and their handlers remain.

### LOGIC INVARIANTS (must preserve)
- **Keyboard ownership:** the row title `<input>` is the **only** keyboard-driven control; all other row controls must stay mouse-only so they never fight the editor. `OutlineRow`'s `onKeyDown` must keep computing `atStart`/`atEnd` from `selectionStart/End` and pass them to `OutlineOutliner.handleKey`; the Left/Right caret-edge gating depends on it. Preserve the full shortcut contract listed above and the `e.preventDefault()/stopPropagation()` behavior.
- **Selection → autofocus:** selecting a row must keep the title as a focusable `<input ref={inputRef}>`; the `useEffect` in `OutlineRow` focuses it and sets the caret to end. Don't replace the input with a non-focusable element when selected.
- **Disclosure semantics:** plain click toggles one level, **Alt+click** must remain the recursive branch toggle (`onDisclosureClick`). `onMouseDown={e => e.preventDefault()}` on disclosure / `+` / actions keeps focus on the title — preserve it. The checkbox uses `onMouseDown={e => e.stopPropagation()}` for the same reason.
- **Data flow / ordering:** rows are produced by `buildRows(items, zoomRootId, filter)` and rendered in that order; children sorted by `order` (`childrenOf`). All mutations go through the pure `outlineModel` functions via `store.mutate` (which updates state, the live `itemsRef`, and schedules a save). Do **not** mutate `OutlineNode`s in place or reorder outside these functions. New nodes must get a real id + timestamps and become the selection (existing behavior in `addRoot`/`addChild`/`addSibling`).
- **Persistence contract:** keep `GET/PUT /api/outline/items` with the `{ items: OutlineNode[] }` shape and the 600 ms debounced autosave + unmount flush; keep the `lf:outline-refresh` reload listener. Don't drop fields from `OutlineNode` (the backend stores it opaquely; `normalize` round-trips them). Keep `localStorage` keys `lf-outline-view` and `lf-outline-zoom` (or migrate deliberately).
- **Enum integrity:** Type/Status/Color `<select>`s must stay bound to `OUTLINE_TYPES`/`OUTLINE_STATUSES`/`OUTLINE_COLORS` values (the filter status/color selects intentionally exclude `'none'`). Status badge only renders when `status !== 'none'`; color dot only when `colorLabel !== 'none'` — keep these conditions.
- **Mode-aware typing:** new-item type selection must keep flowing through `rootType(mode)` / `childType(mode, parentType)` reading the live `modeRef`. The derived view must keep choosing Fountain vs heading parsing via `modeBehavior(mode).outline` in `deriveOutline`.
- **Derived navigation:** the derived items' `blockIndex` is the navigation target; keep passing the full `OutlineItem` to `onNavigate`. Kind ordering is `KIND_ORDER` (`section, scene, synopsis, note`) and the kind-filter bar only appears when more than one kind is present — preserve both.
- **Accessibility affordances to keep:** `aria-label="Outline"` on the aside; `role="group"` + `aria-pressed` on both toggle groups; `aria-expanded`/`aria-label` on the disclosure; `aria-label` on the checkbox; `aria-live="polite"` on the save chip; `aria-label` on breadcrumbs/filter groups. Maintain focus order and the visible focus target (the title input).
- **DOM hooks relied on by logic:** `.is-selected`, `.is-completed`, and the popover/menu structure (`.wb-menu`, `.wb-menu-item`, `.is-danger`) are referenced/shared; the `Popover` trigger label is the only required textual handle for its menus. Keep class names that other CSS/logic targets, or update all references together.

### CURRENT LOOK
A compact, monochrome, text-dense left rail in the Whiteboard Free style. The header sits at top with a tiny segmented toggle. The manual outliner is a tight indented tree (14 px indent step, 8 px base pad; `INDENT_STEP`/`BASE_PAD` in `OutlineRow.tsx`) of single-line rows, each reading: small disclosure triangle · checkbox · optional colored dot · a faint inline **type** label · the title · an optional tiny status badge · (on the selected row) a `+` and `⋯`. Tags appear as small `#chips` on a second line; opening details reveals an inline grid of three small selects, a chip-based tag editor, and a 3-row notes textarea. Toolbar buttons and the save chip are minimal text controls; the filter lives behind a single `⛃` glyph popover. The derived view is an even simpler flat list of indented, clickable navigation lines (sections indented by level, scenes/synopses/notes fixed-indented), with an optional row of small kind toggle buttons above it.

---

## LittleBoy Small AI — Billy (chat) + Logos (inline)

### PURPOSE
LittleBoy is the Whiteboard (Free-tier) "Small AI" system mounted over the document editor. It offers two deliberately lightweight, theme-aware AI agents: **Billy**, a compact draggable hovering chat box, and **Logos**, an inline contextual assistant that opens at the caret/selection to run quick transform actions and (on explicit confirmation) apply scoped edits. This is the Small system only — no Counterpart, no Quantum, no Pro workspace.

### SURFACES / SCREENS
Both surfaces are `position: fixed` overlays rendered by `LittleBoyProvider` (`LittleBoyProvider.tsx`), which is mounted once inside `WhiteboardPage.tsx` (line ~383) only when `editor && doc` exist. Neither is a docked panel; both float above the writing surface.

1. **Billy floating chat box** (`BillyFloatingChat.tsx`) — a 340×420px draggable dialog. Default spawn position is top-right of the viewport (`defaultBillyPos()`: `x = innerWidth − 360 − 24`, `y = 84`). It contains a drag header, a scrolling transcript, and an input row. Z-index 32.
2. **Logos inline box** (`LogosInlineBox.tsx`) — a 340px-wide (max-height 320–360px) dialog that auto-positions just below the caret/selection (`clampPosition` flips above the selection if it would overflow the bottom; clamps to a 12px viewport margin). Z-index 30. It contains a header, context preview, optional-instruction input, an action button grid, and a result region.

There is no toolbar button, menu item, or trigger affordance — **both surfaces are opened exclusively by keyboard shortcut** (see Interactions).

### COMPONENTS
Hierarchy (containers marked **C**, leaf controls marked **L**):

- **`LittleBoyProvider`** **C** — owns shortcuts, ESC handling, context capture, and the persistent Billy chat hook (`useBillyChat`). Renders nothing structural itself; conditionally renders the two boxes.
  - **`BillyFloatingChat`** **C** — `div.billy-box.littleboy-box[role=dialog][aria-label="Billy chat"]`
    - `div.billy-head` **C** (drag handle) → `div.billy-titles` (`span.billy-title` "Billy", `span.billy-subtitle` "LittleBoy Chat"), `div.billy-head-actions` → `button.billy-head-btn` "Clear" **L**, `button.billy-head-btn` "×" close **L**
    - **`BillyMessageList`** **C** — `div.billy-empty` (empty state) **or** `div.billy-messages` containing `div.billy-msg.billy-msg-{role}` bubbles **L** + a scroll-anchor `<div ref={endRef}>`
    - **`BillyChatInput`** **C** — `div.billy-input-row` → `textarea.billy-input` **L** + `button.billy-send` **L**
  - **`LogosInlineBox`** **C** — `div.logos-box.littleboy-box[role=dialog][aria-label="Logos inline assistant"]`
    - `div.logos-head` → `span.logos-title` ("Logos · {contextLabel}") + `button.logos-close` **L**
    - `div.logos-context` **L** (the captured selection/block preview)
    - `form.logos-prompt-row` → `input.logos-prompt` **L** (optional instruction; Enter submits `rewrite`)
    - **`LogosActionMenu`** **C** — `div.logos-actions` → one `button.logos-action` **L** per entry in `LOGOS_ACTIONS`
    - status: `div.logos-status` / `div.logos-status.logos-error` **L**
    - result: `div.logos-result` → `div.logos-output` (the text), optional `div.logos-note`, `div.logos-apply` → action buttons **L** (Apply/Insert, Copy, Close)

Pure (non-render) modules: `littleboyApi.ts` (fetch client), `useBillyChat.ts` / `useLogosInline.ts` (hooks), `collectEditorContext.ts`, `selectionContext.ts`, `writingModeContext.ts`, `logosTypes.ts` (action registry + helpers), and the `*Types.ts` files.

### USER INTERACTIONS
**Global shortcuts** (registered in `LittleBoyProvider`'s `useEffect`, in the **capture phase** on `window` — this is intentional so it beats the TipTap keymap and the app's global ESC handler):
- **Cmd/Ctrl+Shift+B** — toggle Billy open/closed.
- **Cmd/Ctrl+Shift+L** (official) or **Cmd/Ctrl+K** (legacy alias) — toggle Logos. Opening Logos snapshots editor context via `collectEditorContext` at that instant.
- **Escape** — closes the active AI box, **Logos first, then Billy** (only one ESC consumed per press; `e.preventDefault()` + `e.stopPropagation()` stop it from reaching the app's panel-restore ESC). Shortcuts are ignored when `altKey` is held.

**Billy:**
- Drag the box by its header (`onHeaderMouseDown`); dragging is suppressed when the mousedown originates on a `<button>` (`.closest('button')` check). Position is clamped to the viewport (min 8px; right edge `innerWidth − 340 − 8`; bottom `innerHeight − 80`).
- **Enter** in the textarea sends; **Shift+Enter** inserts a newline (`BillyChatInput.onKeyDown`). The send keydown calls `stopPropagation` so Enter doesn't leak to the editor.
- **Send** button — disabled while `sending` or when input is whitespace-only; trims and clears the field on submit.
- **Clear** button — wipes the transcript and resets `conversation_id`; disabled when there are no messages.
- **Close** (×) — hides the box; the conversation thread survives (hook lives in the provider), so reopening restores it.
- Transcript auto-scrolls to the newest message (`BillyMessageList` `endRef.scrollIntoView`).

**Logos:**
- The optional-instruction `input` autofocuses on open (`instructionRef.current?.focus()`).
- Submitting the prompt form (Enter) runs the **`rewrite`** action with the typed instruction.
- Clicking any action button in `LogosActionMenu` runs that action with the captured context + current instruction text. All actions are disabled while `status === 'loading'`.
- Result actions: **Apply (replace selection)** appears only in `apply` mode and replaces the captured `{from,to}` range via `editor.chain().focus().insertContentAt(...)`; **Insert below** appears otherwise and inserts after the captured block; **Copy** writes the result to the clipboard; **Close** dismisses. Apply/Insert close the box afterward. Multi-line output is split to paragraphs by `toParagraphs` (the schema has no hardBreak).

### STATES & MODES
**Billy message states** (`BillyMessage`): normal user (`billy-msg-user`, right-aligned), normal assistant (`billy-msg-assistant`, left-aligned), **pending** (`is-pending`, placeholder content "…" while awaiting reply), **error** (`is-error`, shows "Billy couldn't respond (…)"). Empty state: `billy-empty` ("Ask Billy about your draft. Your selection and nearby text are included as context."). The send/clear buttons reflect `sending` and `messages.length`.

**Logos status** (`LogosStatus` from `useLogosInline`): `idle` (no result region), `loading` ("Thinking…"), `error` ("Logos error: {error}"), `done` (shows output + apply row). The `done`/apply affordance has two **modes** computed by `applyModeFor` (`logosTypes.ts`): **`apply`** only when the backend returned a non-null `suggested_replacement` **and** there is a live selection; otherwise **`insert`**.

**Writing modes** drive only labels, not layout. `writingModeContext.ts` maps mode → label (`novel`→Novel, `screenplay`→Screenplay, `graphic_novel`→Graphic Novel, `stage_script`→Stage Script, `series`→Series, plus notes/scene; unknown modes are capitalized). In **screenplay** mode only, the active element (`scene_heading`, `action`, `character`, `dialogue`, `parenthetical`, `transition`, etc.) is appended as `Mode · Element` in the Logos header via `contextLabel`. The mode/element is captured from `doc.mode` and `screenplayElement` passed from `WhiteboardPage`. Mode is sent to the backend (`writing_mode`) for both agents but does not change which Logos actions appear.

The Logos action set is fixed (`LOGOS_ACTIONS`), in display order: Rewrite, Expand, Compress, Make visual, Improve dialogue, Improve action, Explain, Summarize, Connect to PSYKE. `LOGOS_TRANSFORM_ACTIONS` (rewrite/expand/compress/improve_dialogue/improve_action/make_more_visual) are the ones eligible for Apply.

### DATA & API
- **API client:** `littleboyApi.ts` — `billyChat(baseUrl, req, signal)` → `POST /api/littleboy/billy/chat`; `logosInline(baseUrl, req, signal)` → `POST /api/littleboy/logos/inline`. Default base URL `http://127.0.0.1:8777`; actual `baseUrl` is threaded from `WhiteboardPage`. Non-2xx throws `Request failed (HTTP {status})`.
- **Hooks:** `useBillyChat({ baseUrl })` → `{ messages, sending, send, clear }`; keeps `conversation_id` and sends the last 10 non-pending/non-error turns (`HISTORY_TURNS`) as `history`. `useLogosInline({ baseUrl })` → `{ status, response, error, run, reset }`; aborts any in-flight request via `AbortController` before starting a new one.
- **Context capture:** `collectEditorContext` reads `editor.state.selection` for `selection`/`block`/`from`/`to`, `nearby` text within `NEARBY_RADIUS = 800` PM positions each side (bounded to `NEARBY_LIMIT = 1500` chars by `boundedContext`), and caret viewport `coords` via `editor.view.coordsAtPos`. `contextPreview` clamps the header preview to `PREVIEW_LIMIT = 160` chars.
- **Wire shapes** (`littleboyTypes.ts`, mirroring `backend/app/schemas/littleboy.py`): `BillyChatRequest` {message, selected_text?, nearby_context?, writing_mode?, document_title?, conversation_id?, history?} → `BillyChatResponse` {ok, conversation_id, message:{role,content}, provider, note?}. `LogosInlineRequest` {action, selected_text?, nearby_context?, writing_mode?, instruction?, document_title?} → `LogosInlineResponse` {ok, action, result, suggested_replacement?, provider, note?}.

### RESTYLE SURFACE (safe to redesign freely)
All visual properties of the `.billy-*` and `.logos-*` rules in `styles/app.css` (lines ~2050–2424): colors, the box backgrounds/borders/shadows/radii, padding/gaps, typography (sizes, weight, letter-spacing, uppercase), the message-bubble look and `max-width`, scrollbar styling, hover/disabled visual states, the "×" glyph, button labels'/titles' presentation, and box dimensions/`BOX_WIDTH`/`BOX_HEIGHT`/`BOX_MAX_HEIGHT` constants (within reason). The agents are theme-aware via CSS custom properties (`--panel`, `--border`, `--text`, `--muted`, `--accent`, `--bg`, `--hover`, `--selection`, `--error`) defined in `:root` light + `[data-theme]` dark — restyle by editing these tokens or the component rules. Motion/animation may be added freely (none exists today). The default spawn position, drag affordance styling, and Logos placement math may be re-tuned visually as long as positioning stays viewport-clamped.

### LOGIC INVARIANTS (must preserve)
- **Capture-phase keyboard handler** in `LittleBoyProvider` must keep `addEventListener('keydown', …, true)`, must keep the **Logos-before-Billy ESC ordering**, and must keep `preventDefault`/`stopPropagation` so ESC and the shortcuts don't fall through to the editor/global handlers. The shortcut set (Cmd/Ctrl+Shift+B, Cmd/Ctrl+Shift+L, Cmd/Ctrl+K legacy) and the alt-key guard are a behavioral contract.
- **Billy drag** depends on the header being the drag handle and on the `(e.target).closest('button')` guard — header action buttons must remain real `<button>` elements (do not swap to non-button clickable divs) or dragging will start on them. Viewport clamping in the `mousemove` handler must persist.
- **Billy input keymap:** Enter-sends / Shift+Enter-newline, plus `stopPropagation` on the send keydown, must be preserved so the editor doesn't receive the keystroke. The Send/Clear `disabled` conditions (`sending`, empty input, `messages.length === 0`) are functional.
- **Transcript order & autoscroll:** messages render in array order; the trailing `endRef` div and `scrollIntoView` must remain for newest-message visibility. Message identity is by `m.id` (`key`); `is-pending`/`is-error` class hooks drive functional styling.
- **Logos lifecycle:** `useLogosInline` aborts in-flight requests on a new `run` — keep the `AbortController` flow. The instruction `input` autofocus on mount, and Enter-on-form → `rewrite`, are contracts.
- **Logos apply contract:** `applyModeFor` (`logosTypes.ts`) decides Apply vs Insert — Apply must remain gated on `suggested_replacement && hasSelection`, and it must replace the **captured** `{context.from, context.to}` range (not the live selection), routing through `toParagraphs` for multi-line. Do not remove the Copy/Insert fallbacks.
- **Context bounds:** the `NEARBY_RADIUS`/`NEARBY_LIMIT`/`PREVIEW_LIMIT` caps and `boundedContext` cleanup keep AI context bounded (never send the whole doc) — a restyle must not bypass these or change request field names.
- **API contract:** endpoint paths, request/response field names, the 10-turn history slice, and `conversation_id` persistence across close/reopen must be untouched; the chat hook must stay mounted in `LittleBoyProvider` (not in `BillyFloatingChat`) so the thread survives closing.
- **Accessibility / DOM hooks:** keep `role="dialog"` + `aria-label` on both boxes and the close buttons' `aria-label="Close"` / `title="Close (Esc)"`. The class names `billy-box`/`logos-box`/`littleboy-box` and the `billy-msg-{role}`, `is-pending`, `is-error` modifiers are referenced by CSS and message styling logic — rename only if you update both sites.

### CURRENT LOOK
Minimal, neutral, flat panels matching the editor theme (light `#f3f1ec` panel / dark `#1e1f23`), 1px `--border` outlines, soft drop shadows, 8–10px radii, 13px base text. **Billy** reads as a small chat: bold "Billy" title with an uppercase "LITTLEBOY CHAT" subtitle, ghost Clear/× buttons, right-aligned user bubbles tinted with `--selection`, left-aligned bordered assistant bubbles, a 2-row textarea + Send button footer, thin custom scrollbars. **Logos** reads as a compact command popover: a small uppercase tracking-wide "LOGOS · {context}" title, an italic muted one-line selection preview, a full-width instruction input, a wrapping grid of pill-like action buttons, a "Thinking…"/error status line, and a result block with a `pre-wrap` output, optional muted note, and a wrapping row of Apply/Insert · Copy · Close buttons. Nothing is animated; all interactivity is hover-tint + opacity-dim-on-disabled.

---

## PSYKE (minimal story bible)

### PURPOSE
PSYKE is the Whiteboard's deliberately-minimal "story bible": a compact, hideable right-side panel where the writer searches a flat index of story elements (characters, places, objects, lore, themes) and adds new ones. It is the Free-tier reduction of the Pro graph/workspace — no graph, no relationships, no canvas: just **search → results → simple detail**, plus **+ Add**.

### SURFACES / SCREENS
All PSYKE UI lives inside one floating panel; there is no separate page or route.

- **Toggle button (`.psyke-toggle`)** — lives in the app titlebar's right cluster (`App.tsx`, rendered only when `ui.psykeButtonVisible`). Opens/closes the panel; reflects open state via `is-active` class and `aria-pressed`.
- **PSYKE panel (`<aside className="psyke-window">`)** — fixed overlay pinned to the right edge of the window (`position: fixed; top: 42px; right: 0; bottom: 26px; width: 320px; z-index: 20`). It floats over the workarea between the titlebar and status bar; it does not reflow the editor. Rendered conditionally in `App.tsx` (`{psykeOpen && <PsykeWindow … />}`). Inside it, exactly one of two **views** is shown at a time (`view: 'search' | 'create'`):
  - **Header (`.psyke-header`)** — always visible: the "PSYKE" wordmark (`.psyke-title`), and in the right cluster (`.psyke-header-actions`) the **+ Add** button (`.psyke-add`, search view only) and the **× close** button (`.psyke-close`).
  - **Search view** — search input bar (`.psyke-search`), an optional transient "Added" toast (`.psyke-added`), and the scrollable body (`.psyke-body`) which renders one of: hint, loading, error, empty-with-add, results list, or the selected-entry detail.
  - **Create view** — the `New PSYKE element` form (`.psyke-create`), replacing the search bar + body entirely.
  - **Detail (`.psyke-detail`)** — an in-body sub-surface of the search view shown when a result is `selected`; it replaces the results list (it is not a separate popover).

### COMPONENTS
Hierarchy (containers vs leaf controls):

- **`PsykeWindow`** (`PsykeWindow.tsx`) — top-level container; owns view/selection/toast state and the Esc handler. Props: `{ baseUrl, initialQuery, onClose }`.
  - **Header** (inline JSX) — container; leaf controls: **+ Add** button, **× close** button.
  - **`PsykeCreateForm`** (`PsykeCreateForm.tsx`) — container (when `view === 'create'`). Leaf controls: Type `<select>`, Name `<input>` (autofocused), Description `<textarea>`, Notes `<textarea>`, **Cancel** + **Save** buttons. Props: `{ baseUrl, seed, onCreated, onCancel }`.
  - **`PsykeSearch`** (`PsykeSearch.tsx`) — leaf control wrapper; a single `<input type="search">` that autofocuses + selects on mount. Props: `{ query, onChange }`.
  - **Body** (inline JSX) — container that branches across states (see below). Leaf controls inside: result buttons (`.psyke-result`), inline add button (`.psyke-add-inline`), back button (`.psyke-back`).
- **`usePsykeSearch`** (`usePsykeSearch.ts`) — hook (not a component) owning `query`, `results`, `loading`, `error` and the debounce.
- **`psykeApi`** (`psykeApi.ts`) — fetch client (`searchPsyke`, `createPsykeElement`).

### USER INTERACTIONS
- **Open PSYKE** — titlebar **PSYKE** button or **Ctrl/Cmd+Shift+P**, or the native View menu (`togglePsyke`). On open, `App.openPsyke()` seeds `psykeQuery` with `currentSelectionText()` (the editor's current text selection) and passes it as `initialQuery`. The search input then autofocuses and selects its content (`PsykeSearch`).
- **Type in search** — `onChange` updates `query` (and clears `selected`). `usePsykeSearch` debounces **250ms** (`DEBOUNCE_MS`), trims the query, aborts the prior request (`AbortController`), and calls `GET /api/psyke/search`. Empty/whitespace query short-circuits to no results, no loading, no error.
- **Click a result (`.psyke-result`)** — sets `selected` to that `PsykeEntry`; body switches to the detail sub-surface.
- **Back to results (`.psyke-back`)** — clears `selected`, returns to the list (query/results are preserved).
- **+ Add (header) / + Add "{query}" (inline empty-state)** — switches `view` to `'create'`; clears `selected`. The form is seeded from the trimmed query.
- **Create-form seed rule** (`PsykeCreateForm`): if `seed` is 1–60 chars it prefills **Name**; if longer it prefills **Description** (the "add-from-selection" path). Default Type is `character`.
- **Save** — submit (button click or form submit/Enter in fields). Disabled unless `name.trim()` is non-empty and not already saving. On success calls `onCreated`, which returns to search, clears selection, sets `query` to the new element's name (so it re-appears in results), and shows the **"Added "{name}.""** toast (auto-dismisses after **2600ms**).
- **Cancel** — returns to search view, no save.
- **Escape key (layered):**
  - In **create** view: `PsykeWindow`'s handler calls `e.stopPropagation()` and returns to **search** view (does not close the panel).
  - In **search** view: calls `onClose()` → panel closes.
  - This cooperates with `App.tsx`'s global Esc handler, which **bails out early** if focus is inside `.psyke-window` (or an INPUT/SELECT/TEXTAREA), letting PSYKE handle Esc first; only when focus is elsewhere does App close the panel via `psykeOpenRef`.
- **× close button** — calls `onClose()` directly.

### STATES & MODES
The body (`.psyke-body`) renders exactly one branch, in this precedence order:
1. **Detail** — a result is `selected`.
2. **Idle/hint** — query is empty/whitespace: "Type to search the story bible, or + Add a new element."
3. **Loading** — "Searching…".
4. **Error** — `error` set: the message in `.psyke-error`.
5. **Empty** — query present, zero results: "No entries match "{query}"." + an inline **+ Add "{query}"** button.
6. **Results** — `<ul className="psyke-results">` of result buttons, each showing name + a type badge.

Other states: **Added toast** (transient, search view only), **Saving** (Save button label → "Saving…", inputs effectively locked via disabled save), **create-form error** (`Could not save the element.` or thrown message).

**Writing-mode variants (novel/screenplay/graphic_novel/stage/series):** PSYKE is **mode-agnostic** in this UI. None of these files branch on writing mode — the element type vocabulary (`character/place/object/lore/theme/other`) and the search/detail rendering are identical across all modes. (Mode lives in the editor/outline, not here.) A restyle does **not** need per-mode variants for PSYKE.

### DATA & API
- **Hook:** `usePsykeSearch({ baseUrl, initialQuery })` → `{ query, setQuery, results, loading, error }`.
- **API module:** `psykeApi.ts`
  - `searchPsyke(baseUrl, query, signal)` → `GET {baseUrl}/api/psyke/search?q=<encoded>` → `PsykeSearchResponse`.
  - `createPsykeElement(baseUrl, payload, signal)` → `POST {baseUrl}/api/psyke/elements` (JSON body) → `PsykeCreateResponse`.
  - `DEFAULT_BASE_URL = 'http://127.0.0.1:8777'` (the in-process core backend; the real `baseUrl` comes from `status.baseUrl` in `App.tsx`).
- **Data shapes** (`types.ts`, mirror backend DTOs — **the restyle must keep rendering these fields**):
  - `PsykeEntry`: `{ id, name, entry_type, aliases: string[], description?, notes?, created_at?, updated_at? }`. Note `entry_type` (display string, used in the result badge and detail) is distinct from the create payload's `type`.
  - `PsykeSearchResponse`: `{ query, results: PsykeEntry[] }`.
  - `PsykeCreatePayload`: `{ type: PsykeElementType, name, description, notes }` where `PsykeElementType = 'character'|'place'|'object'|'lore'|'theme'|'other'`.
  - `PsykeCreateResponse`: `{ ok: boolean, element: PsykeEntry }`.
- **Detail renders** (conditionally): `name`, `entry_type`, `description` (only if present), `notes` (only if present, labeled "Notes"), `aliases` (only if non-empty, joined by ", ").

### RESTYLE SURFACE (safe to redesign freely)
- All colors via the theme CSS variables (`--panel`, `--bg`, `--border`, `--text`, `--muted`, `--accent`, `--hover`, `--error`, `--ok`) — recolor, retheme, dark/light all fine.
- Panel chrome: width (`320px`), the `top/right/bottom` insets, `box-shadow`, `border-left`, header height/padding.
- Typography: all font sizes, `letter-spacing`, `text-transform` on `.psyke-title`, `.psyke-detail-label`, `.psyke-create-title`.
- The type **badge** styling (`.psyke-badge` pill), result row layout/hover, the dashed inline-add button look, button styling (`.psyke-btn`, `.psyke-btn-primary`, `.psyke-add`).
- Iconography/labels: the `+ Add`, `×`, `← Back to results` glyphs and copy strings; toast styling and presentation; the hint/empty copy wording.
- Motion: add transitions/animations for panel open/close, toast appearance, view switching (none exist today).
- Layout of the create form (currently a vertical stack with one inline `Type` row) — free to rearrange.
- Whether detail is a sub-view, a slide-over, or a card — free to change, as long as the same fields render.

### LOGIC INVARIANTS (must preserve)
- **DOM hook for Esc layering:** the root element **must keep `class="psyke-window"`**. `App.tsx` (`onKey` Escape handler, line ~138) calls `ae.closest('.psyke-window')` to decide whether to let PSYKE handle Esc. Renaming/removing this class breaks Escape behavior app-wide.
- **`aria-label="PSYKE"`** on the `<aside>` and **`aria-label="Search PSYKE"`** on the search input — keep these accessibility affordances (and `role`/landmark of `<aside>`).
- **Search input semantics:** keep an actual focusable text input that autofocuses and `select()`s on mount (`PsykeSearch`). Focusing inside an INPUT/SELECT/TEXTAREA is also what makes App's global Esc defer — preserve native focusable form controls (don't replace with non-focusable divs).
- **Esc contract:** create-view Esc must return to search (and `stopPropagation`), search-view Esc must close. Don't reorder this.
- **Debounce + abort:** keep the 250ms debounce and `AbortController` cancellation in `usePsykeSearch` (prevents request storms / out-of-order results). Empty-query short-circuit must remain (no request on blank).
- **Branch precedence** in the body (detail → hint → loading → error → empty → results) and the empty-state inline **Add** must stay — these are the only entry points to certain flows.
- **Save gating:** Save stays disabled unless trimmed name is non-empty; payload sends **trimmed** `name/description/notes` and the selected `type`. `onCreated` must keep re-running the search via `setQuery(element.name)` so the new entry is visible.
- **Field rendering guards:** `description`, `notes`, and `aliases` are optional — keep the conditional rendering (don't assume they exist) and keep `aliases.join(', ')`.
- **Type vocabulary:** the six `PsykeElementType` options and their order are the create contract; the `entry_type` string from the server is display-only (don't hardcode/normalize it in the badge).
- **`white-space: pre-wrap`** on `.psyke-detail-text` preserves authored line breaks in descriptions — keep equivalent behavior.
- **Mounting contract:** `PsykeWindow` is a controlled overlay driven by `psykeOpen`/`onClose`/`initialQuery` in `App.tsx`; it must remain a self-contained fixed overlay that does not push/reflow the editor layout (the workarea assumes PSYKE floats above it).

### CURRENT LOOK
A narrow (320px) dark floating panel hugging the right edge, separated by a hairline `border-left` and a leftward drop shadow. Top: a 32px header with a small uppercase letter-spaced "PSYKE" label, a bordered pill-ish **+ Add** button, and a ghost **×**. Below it a single search field on a subtle inset background. The body is a quiet vertical list: borderless full-width result rows (name truncated with ellipsis on the left, a small rounded "pill" type badge in muted text on the right) with a hover wash. Detail view is a simple stacked text block — back link, large name, muted type line, body text, and uppercase mini-labels ("Notes"/"Aliases") over their values. The create form is a tight vertical stack of labeled fields (one inline Type select, then column-layout Name/Description/Notes) with right-aligned Cancel/Save buttons, Save accented by border + accent-colored text. Empty state shows a dashed-outline accent-colored inline add button. All chrome is minimal, monochrome-plus-one-accent, flat (no elevation except the panel's own shadow), with no animation.

---

## Files, Import/Export, Editor Tools, Writing Modes

### PURPOSE
This area covers everything around getting a document *in and out of the Whiteboard* and *configuring the editing surface*: native disk file management (New / Open / Save / Save As), multi-format Import/Export, the optional "Nerd Mode" editor view aids (line numbers, current-line highlight, folding, syntax highlighting, typography overrides), and the Writing Mode selector that switches the document's structural model (novel / screenplay / graphic_novel / stage / series / notes). It is deliberately minimal — every editor aid defaults to off so the page stays a clean writing surface until the writer opts in.

---

### SURFACES / SCREENS
All surfaces live on the single `wb-statusline` bar at the top of `WhiteboardPage.tsx` (the slim toolbar above the writing surface). There is no separate page or route.

1. **File menu (popover)** — `wb-statusline-left`, leftmost. Trigger button labeled "File" opens a `wb-menu` dropdown containing: New, Open…, Save, Save As…, a separator, an **Import** label + one item per import format, a separator, an **Export** label + one item per export format, and a disabled "Export as PDF… (planned)" item. Rendered via the shared `Popover` (render-prop gives each item a `close` callback).
2. **Writing Mode selector** — `wb-statusline-left`, right of the File menu. `WritingModeSelector` renders a `mode-selector` group: a `Mode` label, a native `<select>` (`mode-select`), and a `mode-vocab` chip showing the active mode's structural vocabulary (e.g. "Act / Scene / Beat") with `medium_constraints` as its tooltip.
3. **Inferred screenplay element chip** (`sp-element`) — `wb-statusline-left`, only in screenplay mode. Read-only, not part of this area's owned logic but adjacent.
4. **Draft / autosave indicator** (`wb-draft`) — `wb-statusline-right`. The *backend session* save state, deliberately distinct from file state. Not owned here but must not be conflated with #5.
5. **File state label** (`wb-filestate`) — `wb-statusline-right`. The source of truth for "saved to disk": shows "Untitled", "name.fountain — Saved to file", "… — Modified", "… — Saving…", or "… — Save failed". Tooltip shows the absolute path (or "Not saved to a file yet").
6. **Editor Settings popover** — `wb-statusline-right`, rightmost (`align="right"`). Trigger labeled "Editor" opens the `wb-settings` panel: an "Editor View" heading, four checkboxes (line numbers, current-line highlight, folding, syntax), three dropdowns (syntax theme, font size, line height, typeface), and a "Reset editor view" button.
7. **Import/Export feedback toast** (`wb-toast`) — floating, bottom of `<main className="whiteboard">`. Transient success/error message, click-to-dismiss, auto-clears after 3.6 s.
8. **Inline editor decorations** — rendered *inside* the TipTap writing surface, not the toolbar: the line-number gutter, current-line band, fold toggle carets (`▸`/`▾`), and syntax token coloring. These are ProseMirror decorations, not React DOM.
9. **Native OS dialogs** — Open/Save file pickers, the unsaved-changes prompt (Save / Don't Save / Cancel), and the import-mode prompt (Replace / Append / Cancel) are all native Electron dialogs driven over IPC; they are not styleable in the renderer.

---

### COMPONENTS
- **Containers / hooks (no DOM of their own):** `useFileActions` (file path + dirty + status + New/Open/Save/SaveAs), `useImportExport` (import/export orchestration + feedback), `useEditorTools` (tool state, localStorage-persisted), `useFolding` (collapsed-head index set), `useWritingModes` (loads modes from backend).
- **React components (leaf/visual):** `WritingModeSelector` (label + `<select>` + vocab chip), `EditorSettingsPopover` (uses shared `Popover`), `SyntaxThemeSelector` (a single `<select className="wb-syntax-theme">`).
- **Shared container:** `Popover` (`components/Popover.tsx`) — trigger `wb-tool` button + `wb-popover-panel` dialog. Used by both the File menu and Editor Settings.
- **Non-React surface module:** `EditorTools` TipTap `Extension` (`editorToolsExtension.ts`) — builds all in-editor decorations. `foldToggleDOM()` builds the clickable `wb-fold-toggle` caret as a raw DOM widget.
- **Pure logic modules (no UI):** `fileSerialize.ts`, `fileState.ts`, `importExportFormats.ts`, `editorToolsSurface.ts`, `folding/foldingModel.ts`, `lineNumbers/lineNumbers.ts`, `syntax/syntaxClassifier.ts`, `syntax/syntaxThemes.ts`.

---

### USER INTERACTIONS
**File menu**
- New → `fileDoc.newDocument()` (runs unsaved-changes guard, then blanks the document) + closes menu.
- Open… → `openDocument()` (guard → native open dialog → parse text → load).
- Save → `saveDocument()` (writes to current path, or falls back to Save As if untitled).
- Save As… → `saveDocumentAs()` (native save dialog; sets the active path).
- Each Import item → `importExport.runImport(f.id)`; each Export item → `runExport(f.id)`.
- "Export as PDF…" is `disabled` (planned).

**Native File menu / accelerators** (`onMenuFile`) drive the *same* pathway: `'new' | 'open' | 'save' | 'save-as'`, and `import:<id>` / `export:<id>` strings. The in-app dropdown and the OS menu are one code path — never fork them.

**Window close / quit** — main process calls `onSaveBeforeClose`; the renderer runs `doSave()` and replies via `sendCloseResult(ok)`.

**Import flow** — pick file → `parseImport` → native **Replace/Append/Cancel** prompt (`importConfirmMode`) → on Replace, if dirty, the unsaved-changes guard runs → apply. Replace swaps blocks, may force mode (`forcesMode` / parsed `mode`), applies settings, and restores embedded outline + PSYKE; Append concatenates after a blank separator block and keeps the current document. Either way the document is marked dirty; the active file path is **never** changed by import.

**Export flow** — build format string → native save dialog → write. Export **never** clears dirty state and **never** changes the active file path (it is a copy).

**Writing Mode** — selecting an option calls `onChange` → `setMode`. Disabled when no document is loaded or `modes` is empty.

**Editor Settings** — checkboxes call `toggle('lineNumbers' | 'currentLineHighlight' | 'folding' | 'syntax')`; dropdowns call `update(key, value)` (font size / line height accept "Default" = `null`; typeface/syntax theme are enums). "Reset editor view" → `onReset` (`resetEditorView` = `reset()` tool state + `clearFolds()`).

**Keyboard shortcuts** (registered in `WhiteboardPage.tsx` keydown handler; work in every mode):
- `Ctrl/Cmd+L` → toggle line numbers.
- `Ctrl/Cmd+Shift+F` → toggle folding.
- `Ctrl/Cmd+Shift+H` → toggle syntax.
- (Adjacent, not owned here: `Ctrl/Cmd +/-/0` zoom, `Ctrl/Cmd+Shift+E` screenplay preview, `Esc` exits preview unless focus is in a popover/input.)

**In-editor folding** — clicking a `wb-fold-toggle` caret calls `onToggleFold(headIndex)` → `toggleFold` flips that head in the collapsed set; the extension hides body blocks via the `wb-folded-hidden` class. The caret's `mousedown` is `preventDefault`-ed so the editor never steals focus / moves the caret.

**Popover dismissal** — outside `mousedown` or `Escape` closes (`Escape` is `stopPropagation`-ed so it doesn't also exit preview).

**Toast** — click anywhere on it to dismiss; otherwise auto-dismisses after `FEEDBACK_MS` (3600 ms).

---

### STATES & MODES
- **File status** (`FileStatus`): `'saved' | 'unsaved' | 'saving' | 'error'`. Drives the `wb-filestate` label text and its `is-dirty` modifier. `'saving'` → "Saving…"; `'error'` → "Save failed".
- **Dirty flag** — set on any edit via `markDirty`; suppressed during a programmatic load (`suppressDirty` ref). Cleared only by explicit Save/Open/New. Mirrored to main via `fileApi.setDirty`.
- **No-bridge / browser fallback** — when not running in Electron, `filesAvailable()` / `importExportAvailable()` are false and every bridge call resolves to a safe error result (`NO_BRIDGE`) or a no-op; guard prompts default to `'dont-save'`, import mode to `'cancel'`.
- **Writing modes loading** — `useWritingModes` exposes `loading` / `error`; until loaded, the selector shows a single fallback `<option>` of the current value and the default mode is `'novel'`.
- **Editor tools toggles** — each of the four boolean aids is independently on/off; the extension renders nothing (`return null`) when all four are off. Typography overrides (`fontSize`, `lineHeight`) are `null` = "use mode default"; `typeface` `'default'` = per-mode typeface.
- **Writing-mode variants** affect behavior here:
  - *Folding:* headings fold in **all** modes; **screenplay** additionally folds multi-block Notes (`[[ … ]]`) and boneyard (`/* … */`).
  - *Syntax:* **screenplay** uses the Fountain classifier (scene_heading/character/dialogue/etc. + title-page + boneyard tokens); **prose modes** classify Markdown-ish chapter/heading/subheading/bullet/checkbox. Inline tokens (emphasis, note, todo, tag, link, checkbox, psyke) are shared, except checkbox/tag are skipped in screenplay.
  - *Default file extension* (`defaultExtForMode`): screenplay → `.fountain`; novel/notes/scene/series/graphic_novel → `.md`; else `.txt`.
  - *Import mode-forcing:* importing Fountain or Final Draft forces `mode: 'screenplay'`.
  - *Export HTML* uses a monospace font for screenplay/stage_script, serif otherwise.
- **Toast states** — `feedback.kind` is `'ok' | 'error'`, mapped to `wb-toast-ok` / `wb-toast-error`.

---

### DATA & API
**Electron IPC bridges** (resolved lazily off `window.logosforge`, flat function names):
- `fileApi` (`fileApi.ts`) → `open`, `saveAs`, `saveToPath`, `confirmSaveChanges`, `setDirty`, `onSaveBeforeClose`, `sendCloseResult`; plus `onMenuFile` / `onMenuView` menu subscriptions. Shapes: `OpenResult`, `SaveResult`, `SaveChoice` (`fileTypes.ts`).
- import/export bridge (`importExportApi.ts`) → `importOpen(filters)`, `importConfirmMode()` (`ImportMode = 'replace'|'append'|'cancel'`), `exportSave(content, suggestedName, filters)`.

**Backend HTTP**
- `getWritingModes(baseUrl, signal)` → `GET /api/writing-modes` (`writingModesApi.ts`), returning `WritingModesResponse { modes: WritingMode[]; default_mode }`. `WritingMode` = `{ id, label, structural_units, default_writing_format, medium_constraints }`. Default base URL `http://127.0.0.1:8777`.
- Import/export also touch **outline** (`getOutlineItems` / `saveOutlineItems` / `emitOutlineRefresh` from `outline/outlineApi`) and **PSYKE** (`createPsykeElement` from `psyke/psykeApi`) — only on a LogosForge full-replace import / `.logosforge` export. These restores are best-effort and never abort the import.

**Persistence (localStorage, no backend):**
- `useEditorTools` → key `logosforge-editor-tools` (the full `EditorToolsState`).
- `useFolding` → key `logosforge-folds` (array of collapsed head indices).

**Serialization / formats (pure):**
- `blocksToText` / `textToBlocks` (`fileSerialize.ts`) — block ⇄ Fountain/Markdown text round-trip; `#`/`##`/`###` lines ⇄ heading blocks (levels 1–3).
- `IMPORT_FORMATS` (`txt`, `md`, `fountain`, `logosforge`, `fdx`) and `EXPORT_FORMATS` (`txt`, `md`, `fountain`, `logosforge`, `json`, `html`) with their `DialogFilter[]` and menu `action` ids — drive the File-menu item lists.
- `WhiteboardBlock` `{ id, type: 'paragraph'|'heading', text, level? }` is the document model rendered throughout.

---

### RESTYLE SURFACE (safe to redesign freely)
- All toolbar layout, spacing, color, typography, and iconography of `wb-statusline`, `wb-statusline-left/right`, `wb-tool` triggers, `wb-popover` / `wb-popover-panel` (and `wb-popover-left/right` alignment look), `wb-menu` / `wb-menu-item` / `wb-menu-label` / `wb-menu-sep` / `wb-menu-scroll`.
- The Editor Settings panel internals: `wb-settings`, `wb-settings-title`, `wb-field`, `wb-field-check`, `wb-reset`, the `<kbd>` shortcut hints, and the native `<select>` styling.
- The mode selector look: `mode-selector`, `mode-label`, `mode-select`, `mode-vocab` chip.
- The file-state and draft indicators' look: `wb-filestate` (and `is-dirty`), `wb-draft` / `wb-draft-*` — text content is generated by `fileStateLabel` but the chrome is free.
- The toast look/motion: `wb-toast`, `wb-toast-ok`, `wb-toast-error`.
- The **syntax theme palettes** in `syntaxThemes.ts` (`minimal`, `paper`, `writer-dark`, `sublime-dark`) and the `--syn-*` color values — these are pure color and may be retuned, themes added/relabeled.
- The fold caret glyphs/animation, current-line band styling, and gutter appearance — purely decorative.
- The HTML export's embedded `<style>` block in `buildHtml` is independent of app chrome and may be restyled (it ships inside exported files).

---

### LOGIC INVARIANTS (must preserve)
**DOM hooks the editor-decoration logic and CSS gating depend on** — renaming any of these silently breaks a feature:
- Decoration classes emitted by `editorToolsExtension.ts:build()`: `wb-ln` (+ `data-ln` attribute = line number), `wb-current-line`, `wb-folded-hidden`, `wb-fold-head`, `wb-fold-collapsed`, and `wb-syn-<token>` (block + inline). The `data-ln` attribute is the line-number value; the CSS gutter renders it via `::before`.
- The fold-toggle widget (`foldToggleDOM`): class `wb-fold-toggle`, glyphs `▸`/`▾`, `role="button"`, `aria-label` "Expand block"/"Collapse block", `contenteditable="false"`, and its `mousedown`→`preventDefault` behavior. Do not remove the mousedown guard or the click handler.
- Surface gating attributes from `editorToolsSurface.ts:editorToolsAttrs`: `data-linenumbers`, `data-folding`, `data-syntax`, `data-currentline`, `data-editor-font`, `data-editor-lh`, `data-editor-typeface`. CSS keys off these to show/hide each tool, so the styling must stay attribute-gated.
- CSS custom properties from `editorToolsVars` / `themeCssVars`: `--wb-font-px`, `--wb-line-height`, and `--syn-*`. Also `--measure` and `--wb-scale` set alongside them on the surface.

**Data-flow / behavioral contracts:**
- New/Open/Save/Save As have exactly **one** pathway shared by the in-app File menu and the native menu (`useFileActions` + `onMenuFile`). Do not duplicate it in the UI.
- The unsaved-changes guard (`confirmProceedPastUnsavedChanges`) must run before *every* destructive action: New, Open, and import-Replace. Resolving `false` aborts.
- Import **never** changes the active file path; Export **never** clears dirty or changes the path (`useImportExport.doExport` comment). Preserve this separation between Save (owns the document) and Export (a copy).
- `markDirty` must fire on user edits and be suppressed during programmatic loads (`suppressDirty` ref / `loadInto`). Folding/syntax/line-number rendering must remain **visual only** — `editorToolsExtension`'s decorations never mutate the document, so hidden/folded text is always saved (`foldingModel.ts` docstring). Never make a redesign that edits doc text to fold.
- Menu **action id strings** are part of the IPC contract: `'new' | 'open' | 'save' | 'save-as'`, `import:<ImportFormatId>`, `export:<ExportFormatId>`. The format ids (`txt/md/fountain/logosforge/fdx`, `txt/md/fountain/logosforge/json/html`) and their `DialogFilter` extensions are the file-association contract — don't drop or rename without matching the main process.
- The `.logosforge` envelope shape (`format: 'logosforge-whiteboard'`, `version`, `document.{title,mode,content,settings}`, `outline`, `psyke`, `metadata`) is the round-trip contract for `buildLogosforgeEnvelope` ↔ `parseLogosforge`. No machine paths are ever written into exports.

**Keyboard / accessibility affordances to keep:**
- `Ctrl/Cmd+L`, `Ctrl/Cmd+Shift+F`, `Ctrl/Cmd+Shift+H` must keep toggling line numbers / folding / syntax (and stay clear of `Ctrl/Cmd+K`, reserved for Logos).
- `Popover` contract: `aria-haspopup="dialog"`, `aria-expanded`, panel `role="dialog"` + `aria-label`, outside-click and `Escape` close. The `Escape`-in-popover check in the page keydown handler relies on focus being inside `.wb-popover`.
- `WritingModeSelector`: keep it a real `<label htmlFor="writing-mode">` + `<select id="writing-mode">`; keep the `disabled` behavior when no doc/modes. `SyntaxThemeSelector` keeps `aria-label="Syntax theme"`.
- Toast keeps `role="status"`.

---

### CURRENT LOOK
A single slim status bar (`wb-statusline`) spans the top of the writing area, split left/right. Left: a text-trigger "File" popover button, the "Mode" labeled dropdown with a small slash-joined vocabulary chip, and (in screenplay) an inferred-element chip. Right: a muted backend "Draft/autosave" pill, a "name — Saved/Modified" file-state pill (asterisk-free; dirtiness shown as " — Modified" text + `is-dirty` class), and an "Editor" popover button. The File popover is a plain vertical list of text buttons with two labeled sections (Import / Export) separated by thin rules, scrollable, ending in a greyed-out "Export as PDF… (planned)". The Editor Settings popover is a compact form: a small title, stacked checkbox rows with inline `<kbd>` shortcut hints, four native `<select>` dropdowns, and a "Reset editor view" text button. Inside the editor, enabled aids appear as a numbered left gutter, a faint current-line band, small triangle fold carets at heading/note/boneyard heads, and low-saturation token coloring driven by the selected palette. Feedback from import/export appears as a small floating toast near the bottom.

---

## Global Logic Invariants (do NOT break)

A consolidated, deduplicated checklist of behaviors, contracts, and DOM hooks the restyle must preserve. Grouped by concern; every item is load-bearing.

### Root & shell structure
- Root element keeps base class `app` plus conditional modifiers `is-top-hidden` (top panel hidden) and `is-focus` (focus mode). CSS and behavior key off these.
- `WhiteboardPage` (the editor) stays **always-mounted** — only one editor instance. OutlinePanel / StatusBar / PSYKE button / PsykeWindow remain conditionally mounted via `useUiVisibility` flags + `psykeOpen`.
- `ThemeProvider` must wrap `<App>`; `applyStoredTheme()` must run in `main.tsx` **before** React renders (no-flash startup). Reapply happens in `ThemeProvider`'s `useLayoutEffect`.

### Theming variable contract
- `applyThemeVars` (`themeTokens.ts`) is the **single** writer of theme vars: `--bg, --panel, --border, --text, --muted, --accent, --hover, --selection, --paper, --ink, --paper-muted, --paper-selection, --page-shadow, --caret, --error, --ok`, the `--lf-*` aliases, and the `data-theme` / `data-theme-id` attributes. Rename a consumed var in `app.css` ⇒ rename it here too.
- Keep emitting `data-theme="light|dark"` on `<html>` (the dark-override block and `--hover` selection depend on it).
- Feature-set vars whose **names** are a contract (do not drop): `--measure`, `--wb-scale` (`WhiteboardPage`), `--wb-font-px`, `--wb-line-height` (`editorToolsSurface`), `--syn-*` (`syntaxThemes`), `--caret`.
- Custom theme: editing any custom field must keep auto-activating `themeId='custom'`; `customToTheme` must keep **deriving** editor ink/muted from `editorBg` luminance; `CUSTOM_ROWS` keys stay a subset of `CustomThemeFields`. `PREDEFINED_THEMES` array order = cycle order = `.theme-grid` render order — keep aligned.

### DOM-class hooks consumed by JS logic (do NOT rename without updating both sites)
- `.wb-editor` — `App.scrollToBlock()` does `document.querySelector('.wb-editor').children[index]`; editor blocks must stay **direct children in document order**. Also referenced by editor-tools/folding/screenplay CSS/decorations. `.wb-content` likewise.
- `.wb-popover`, `.psyke-window`, `.littleboy-box` — the global Esc handler (`App.tsx` keydown) tests `activeElement.closest(...)` on these exact classes to defer Esc. `.littleboy-box` is a behavioral hook applied to **both** Billy (`billy-box littleboy-box`) and Logos (`logos-box littleboy-box`) — keep it on both. `.wb-popover` is also the outside-click boundary in `Popover.tsx`.
- `.wb-surface` — click-to-focus host; its `onMouseDown` relies on `e.target === e.currentTarget`. Do not wrap the editor in extra full-bleed layers that intercept this.
- State-class hooks toggled in JSX (keep the names; only appearance is free): `.is-active`, `.is-selected`, `.is-completed`, `.is-dirty`, `.is-pending`, `.is-error`, `.is-untitled`, `.is-danger`.

### Editor surface attributes & decoration classes (set by feature code; restyle the rules, never rename the attribute/value names or classes)
- On `.wb-editor`: `data-writing-mode` ∈ `novel/screenplay/graphic_novel/stage/series` — source of per-mode typography and `isScreenplay` gating.
- On `.wb-surface`: `data-screenplay`; document-settings attrs `data-scene-style` (normal/bold/underline/bold-underline), `data-scene-blank` (1/2), `data-typeface` (courier-prime/courier/monospace), `data-invisibles` (on/off); editor-tools attrs `data-linenumbers`, `data-folding`, `data-syntax`, `data-currentline`, `data-editor-font`, `data-editor-lh`, `data-editor-typeface`; the `.is-preview` modifier. CSS must stay attribute-gated. Preview reads the same attrs to stay in sync.
- `--measure` is the editor column width source (per-mode, e.g. `63ch` screenplay); `--wb-scale` drives font scale — don't hardcode widths over them.
- Screenplay element classes emitted by ProseMirror decorations / Preview (renaming silently breaks formatting): `sp-{FountainType}` (`sp-scene_heading`, `sp-character`, `sp-dialogue`, `sp-parenthetical`, `sp-transition`, `sp-section`, `sp-synopsis`, `sp-note`, `sp-centered`, `sp-page_break`), `sp-title-page`, `sp-boneyard`, and inline `sp-bold/sp-italic/sp-bold-italic/sp-underline/sp-emph-marker`. Preview reuses these same classes.
- Editor-tools decoration classes: `wb-ln` (+ `data-ln` = line number, rendered via `::before`), `wb-current-line`, `wb-folded-hidden`, `wb-fold-head`, `wb-fold-collapsed`, `wb-syn-<token>` (block + inline). Fold-toggle widget: class `wb-fold-toggle`, glyphs `▸`/`▾`, `role="button"`, `aria-label` Expand/Collapse block, `contenteditable="false"`, `mousedown`→`preventDefault` (keep the guard + click handler).

### Keyboard contracts (global + per-area)
- **`Cmd/Ctrl+K` must stay unbound everywhere except Logos** (legacy alias to toggle Logos). Reserved app-wide.
- Shell (`App.tsx`, gate `mod && shift && !alt`, matched via `e.code`): `Ctrl/Cmd+Shift+O/P/T/D` = Outline / PSYKE / top panel / Focus Mode. Esc precedence: focused transient/input → close PSYKE → `ui.handleEscape()`.
- Whiteboard/Editor (`WhiteboardPage`): `mod +`/`-`/`0` scale; `mod+Shift+E` Preview (screenplay); `mod+Shift+F` folding; `mod+Shift+H` syntax; `mod+L` line numbers; `Esc` exits Preview **unless** focus is in `.wb-popover` or INPUT/SELECT/TEXTAREA.
- Screenplay layer: Tab / Shift+Tab (autocomplete + section depth, **Tab always consumed**), `Mod-b/i/u`, `Mod-Alt-n`, `Mod-Alt-o`, `Mod-\` (center line). **Enter must NOT be bound** (context classifies the next line).
- LittleBoy (`LittleBoyProvider`, **capture-phase** `keydown` on `window`, ignored when `altKey` held): `Cmd/Ctrl+Shift+B` toggle Billy; `Cmd/Ctrl+Shift+L` (and legacy `Cmd/Ctrl+K`) toggle Logos; **Esc closes Logos before Billy** (one Esc per press, with `preventDefault`+`stopPropagation`). This handler must beat the TipTap keymap and the app Esc.
- Outline (only while a row title `<input>` is focused, `atStart`/`atEnd` computed from `selectionStart/End`): Enter = sibling, Shift+Enter = details, Ctrl/Cmd+Enter = child, Tab/Shift+Tab = indent/outdent, Arrows = move/select (Ctrl/Cmd+Arrow = reorder siblings), Left/Right caret-edge collapse/expand, Ctrl/Cmd+]/[ = zoom in/out, Backspace/Delete on empty = delete, Esc = deselect/blur. All other row controls stay **mouse-only**.
- The `Esc`-in-popover / Esc-from-input bypass: focus inside `.wb-popover` or `INPUT/SELECT/TEXTAREA` must keep deferring the various Esc handlers; keep native focusable form controls (or replicate the tag check).

### Popover semantics (shared `Popover.tsx`)
- Keep `aria-haspopup="dialog"`, `aria-expanded`, panel `role="dialog"` + `aria-label={title}`, outside-`mousedown` close, and Esc `stopPropagation()` (so popover Esc does not bubble to the global/preview Esc). Keep the render-prop `close()` so menu items self-dismiss. Trigger is `button.wb-tool`.

### Data-flow / behavioral contracts
- **Two distinct save indicators** — `.wb-draft` (backend autosave/session) and `.wb-filestate` (file-on-disk) are different sources of truth. **Do not merge or relabel** into one "saved" indicator.
- `WhiteboardBlock` shape `{ id, type:'heading'|'paragraph', text, level?, sp? }` is the backend contract; `blocksToDoc`/`docToBlocks` round-trip (heading↔level, paragraph↔`sp`; heading↔Fountain Section `#`) must be preserved. `<WhiteboardEditor key={doc.id}>` must keep remounting on doc change.
- Edit ordering in `handleBlocks`: `markFileDirty()` → `setLiveBlocks` → `onChangeBlocks` → `deriveOutline`. Mode switch keeps current content (re-derives outline from live blocks); only a different `doc.id` resets `liveBlocks`.
- Outline data flow: `WhiteboardPage` (`onOutlineChange`) → `OutlinePanel` (`derivedItems`); `onNavigate` calls `scrollToBlock(item.blockIndex)` (the derived `blockIndex` is the nav target). `docMode` lifted via `onModeChange` and forwarded to `OutlinePanel` (`mode`). `actionsRef`/`psykeOpenRef` re-synced every render (one subscription, latest handlers). PSYKE open seeds query from `currentSelectionText()`.
- Outline persistence: `GET/PUT /api/outline/items` with `{ items: OutlineNode[] }`, 600 ms debounced autosave + unmount flush, `lf:outline-refresh` reload listener. Don't drop `OutlineNode` fields (stored opaquely; `normalize` round-trips). All mutations go through pure `outlineModel` functions via `store.mutate` — never mutate nodes in place or reorder outside them; new nodes get a real id + timestamps and become the selection. Rows come from `buildRows(items, zoomRootId, filter)` (children sorted by `order`). Enum integrity: Type/Status/Color selects bound to `OUTLINE_TYPES`/`OUTLINE_STATUSES`/`OUTLINE_COLORS`; status badge only when `status !== 'none'`, color dot only when `colorLabel !== 'none'`. Mode-aware typing via `rootType(mode)`/`childType(mode,parentType)`; derived parsing via `modeBehavior(mode).outline`. Kind order `KIND_ORDER` = `section, scene, synopsis, note`; kind-filter bar only when >1 kind present.
- Files / Import / Export: New/Open/Save/Save As have **one** pathway shared by in-app File menu and native menu (`useFileActions` + `onMenuFile`) — never fork. The unsaved-changes guard runs before New, Open, and import-Replace. **Import never changes the active file path; Export never clears dirty or changes path** (Export is a copy). `markDirty` fires on user edits, suppressed during programmatic loads. Editor-tools decorations are **visual only** — never mutate doc text to fold; folded/hidden text is always saved. Menu action-id strings (`'new'|'open'|'save'|'save-as'`, `import:<id>`, `export:<id>`) and the format ids (`txt/md/fountain/logosforge/fdx` import; `txt/md/fountain/logosforge/json/html` export) + their `DialogFilter` extensions are the IPC/file-association contract. The `.logosforge` envelope shape is the round-trip contract; no machine paths in exports.
- Screenplay export semantics: `EXPORT_TARGETS.available` gates `disabled` (disabled stay disabled); `runExport` ids `fountain`/`copy-fountain`/`copy-preview` are load-bearing. Notes/boneyard stay in the document but are excluded from Preview/export (dimmed-but-present, never deleted). `screenplayLabel` LABELS map + `FountainType` order fixed; element chip always shows a label (null→"Action").
- Disabled states are meaningful — Format actions disabled when `!editor || preview`; planned items (PDF export, "Link to editor", `pdf`/`fdx`/`print` screenplay export) stay visibly non-clickable.
- LittleBoy: capture-phase handler with Logos-before-Billy Esc; Billy drag via header with `(e.target).closest('button')` guard (header actions stay real `<button>`s) + viewport clamping; Billy Enter-sends / Shift+Enter-newline + `stopPropagation`; transcript renders in array order with trailing `endRef` `scrollIntoView`; `useLogosInline` aborts in-flight on new `run`; Logos instruction input autofocus + Enter→`rewrite`; **Apply gated on `suggested_replacement && hasSelection`**, replaces the **captured** `{from,to}` range via `toParagraphs` (keep Copy/Insert fallbacks). Context caps `NEARBY_RADIUS`/`NEARBY_LIMIT`/`PREVIEW_LIMIT` + `boundedContext` (never send whole doc). API: endpoint paths, request/response field names, 10-turn history slice, `conversation_id` persistence across close/reopen; chat hook stays in `LittleBoyProvider` (not `BillyFloatingChat`) so the thread survives closing.
- PSYKE: `usePsykeSearch` 250 ms debounce + `AbortController` cancellation + empty-query short-circuit (no request on blank). Body branch precedence **detail → hint → loading → error → empty → results** + the empty-state inline Add. Save gated on non-empty trimmed name; sends trimmed `name/description/notes` + selected `type`; `onCreated` re-runs search via `setQuery(element.name)`. Create-form seed rule: 1–60 chars → Name, longer → Description. Field-render guards on optional `description`/`notes`/`aliases` (`aliases.join(', ')`). Type vocabulary (`character/place/object/lore/theme/other`, fixed order) is the create contract; server `entry_type` is display-only. `white-space: pre-wrap` on detail text. PsykeWindow is a controlled fixed overlay that never reflows the editor.

### Accessibility affordances to keep across every surface
- `aria-pressed` on title-bar toggles (outline, PSYKE) and the Preview button; `aria-label` on Focus/Hide-top buttons, both boxes' close buttons (`aria-label="Close"` / `title="Close (Esc)"`), color inputs, the disclosure, the checkbox, breadcrumb/filter groups, search inputs (`aria-label="Search PSYKE"`), `SyntaxThemeSelector` (`aria-label="Syntax theme"`).
- Landmarks/roles: `aria-label="Outline"` and `aria-label="PSYKE"` on their `<aside>`s; `div.wb-toolbar[role="toolbar"][aria-label="Screenplay tools"]`; scale group `aria-label="View scale"`; `role="group"` + `aria-pressed` on segmented toggles; `role="dialog"` + `aria-label` on both AI boxes; menu separators `role="separator"`; toast `role="status"`; save chip `aria-live="polite"`; autocomplete `role="listbox"` / items `role="option"` + `aria-selected`.
- `WritingModeSelector` stays a real `<label htmlFor="writing-mode">` + `<select id="writing-mode">`. All interactive elements remain real `<button type="button">` / native form controls for keyboard focus and tab order. Maintain a visible focus indicator (`:focus { border-color: var(--accent) }` or a visible replacement) and logical tab order. Autocomplete selection MUST use `onMouseDown` + `preventDefault` (click-after-blur would cancel selection).

---

## Restyle Freedom (safe to change)

Everything visual is in scope. Consolidated list of what the designer may freely redesign, provided the invariants above survive.

- **The entire token layer.** All raw color values in the 6 predefined palettes and the `:root` / `[data-theme='dark']` blocks — hues, contrast, the chrome/page split. Add / replace / rename *palettes* freely (keep the `WhiteboardTheme` shape and at least one default). Retune the `--syn-*` syntax palettes (`minimal`, `paper`, `writer-dark`, `sublime-dark`) and add/relabel themes. The whole point of the architecture is that re-skinning is mostly editing tokens.
- **All spacing, radii, borders, shadows** (`--page-shadow`, per-box box-shadows), panel sizing (the 232px outline width, 320px PSYKE, 340px AI boxes, 42px titlebar / 26px status bar heights, `BOX_WIDTH/HEIGHT/MAX_HEIGHT`), and the `clamp()` writing-surface padding.
- **Typography.** Font stacks (serif `Iowan Old Style`, mono `Courier Prime`, system sans), sizes, weights, line-heights, letter-spacing, `text-transform`; per-mode editor type via `[data-writing-mode]`; screenplay typefaces via `[data-typeface]`/`[data-scene-style]`/`[data-scene-blank]`/`[data-invisibles]`; per-mode `--measure` widths. (Preserve the attribute selectors + their value sets; restyle what they map to.)
- **Iconography & glyphs** — all decorative glyphs are swappable for any icon set as long as titles/`aria-label`s persist: titlebar `☰ ◌ ▲`, the `PSYKE` label, overflow `⋯`, disclosure `▸`/`▾`, leaf `•`, filter `⛃`, breadcrumb `›`, add `+`, the `⚙`/`▾`/`−`/`+` toolbar affordances, fold carets `▸`/`▾`, the `×` close glyph, swatch/dot shapes, chip/pill styling. Button **label text** (Preview/Editing, Format, Export, menu items, hint/empty copy, Status-badge text, type/color/status labels) is content you may rephrase — keep the wiring and the enum-value mappings.
- **Layout within every surface** — reflow/regroup/reorder toolbar groups, the status line, menu internals, the swatch grid columns, the create form; move controls to a sidebar; change the work-area column widths/order/collapse animation; change Preview from side-by-side to stacked (`.wb-surface.is-preview`); change whether PSYKE detail is a sub-view, slide-over, or card — as long as the controls, handlers, and the same rendered fields survive.
- **Floating-surface placement & chrome** — the PSYKE dock position/insets, Billy default spawn + drag-affordance look, Logos placement math (keep viewport-clamped), popover panel alignment (`wb-popover-left`/`-right`), autocomplete popup chrome, toast/focus-hint look.
- **Motion** — none exists today; add transitions/animations freely: panel open/close, popover/menu in-out, toast in/out, focus transitions, view switching, the `focus-hint` fade (`@keyframes focus-hint-fade`), fold-toggle and hover transitions, drag feedback.
- **StatusBar dot colors and labels** — the `COLORS`/`LABELS` maps (keep keys connecting/connected/error + a fallback). The screenplay element-formatting look (scene-heading/character/dialogue indents, transition alignment, emphasis-marker dimming) is restylable within reason. The HTML-export embedded `<style>` block (ships inside exported files) is independent of app chrome.

---

## Claude Design Prompt

> **Restyle the LogosForge Whiteboard — a Free-tier, minimal, writing-first desktop app.**
>
> You are restyling an existing, fully-working Electron + React writing application. **This brief (above) is your spec** — read all of it. Your job is purely the visual layer: the global stylesheet (`styles/app.css`), the theme token map (`styles/themes/`), and any motion. **Do not touch component logic, data flow, DOM structure, class/attribute names, keyboard bindings, or ARIA — those are fixed contracts** enumerated in "Global Logic Invariants (do NOT break)." Everything you *may* change is in "Restyle Freedom (safe to change)."
>
> **Aesthetic goals are open.** The current look is a deliberately quiet, "Slugline-like" parchment-and-ink minimalism (default theme *Paper White*), but you are not bound to it — propose a fresh, cohesive visual direction. The one fixed principle is the product's: **simplicity is a feature.** This is the Free tier; the page should stay a calm, distraction-light writing surface, with every aid (outline, PSYKE, AI, Nerd-Mode editor tools) quiet until summoned. Don't add visual noise the architecture is specifically designed to avoid.
>
> **Deliver a cohesive visual system across all surfaces**, not a per-screen patchwork:
> - A **token system** expressed through the existing CSS-variable contract. `applyThemeVars` (`themeTokens.ts`) is the only writer of theme vars — work within the 17-field `WhiteboardTheme` shape and the `--bg/--panel/--border/--text/--muted/--accent/--hover/--selection/--paper/--ink/--paper-muted/--paper-selection/--page-shadow/--caret/--error/--ok` (+ `--lf-*`) variable set. Keep `--text` (UI ink) and `--ink` (editor ink) independently legible so mixed light-page/dark-chrome themes work. Honor the no-flash startup (`applyStoredTheme` before render).
> - **At least one polished default theme** plus a refreshed set of light / dark / mixed palettes (you may add, replace, or relabel the six), each renderable as a small `.theme-grid` swatch, in the `PREDEFINED_THEMES` cycle order. Retune the `--syn-*` syntax-highlight palettes to match.
> - A consistent treatment of the recurring primitives so they read as one family: the **title bar**, the **two-column work area** (outline rail + full-bleed writing sheet), the **status bar**, the shared **Popover** menus (File / Editor / Screenplay Settings / Format / Export / Outline filter / Theme), **pills/chips/badges** (mode vocab, screenplay element, file-state, draft, status, PSYKE type), **segmented toggles**, the floating **PSYKE** dock, the two **LittleBoy** AI boxes (**Billy** chat + **Logos** inline), **toasts**, the **focus-hint**, and the **autocomplete** popup.
> - The **writing sheet** is the hero. Treat per-mode typography deliberately — serif-feeling prose vs. the monospace, indent-driven Fountain screenplay formatting (scene heading / character / dialogue / parenthetical / transition / sections / synopsis / notes / boneyard, plus emphasis markers and the Preview pane) — driven entirely through the preserved `[data-writing-mode]` / `data-screenplay` / `data-*` attribute selectors and `--measure` / `--wb-scale`.
> - **Motion**: there is none today. Add tasteful, restrained transitions (popover/menu, toast, view-switch, focus-mode entry, drag/hover, the `focus-hint` fade) that reinforce calm, never distract.
> - Cover every **state**: loading / empty / error hints, dirty vs. saved, pending / error AI messages, disabled (planned/unavailable) controls, active/selected/completed toggles, focus & selection rings — using the preserved state-class hooks (`.is-active/.is-selected/.is-completed/.is-dirty/.is-pending/.is-error/.is-untitled/.is-danger`).
>
> Deliver the restyled `app.css` + theme token definitions (and any keyframes), keeping every class name, attribute selector, CSS-variable name, and ARIA hook intact. Show the system across the key surfaces (shell + writing sheet in prose and screenplay modes, outline, PSYKE, both AI boxes, popovers, a couple of themes). When in doubt about whether something is safe to change, the two consolidated lists above are authoritative: if it's a name/contract/binding, preserve it; if it's a pixel, color, font, glyph, or motion, it's yours.