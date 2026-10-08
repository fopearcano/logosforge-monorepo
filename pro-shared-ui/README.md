# @logosforge/pro-shared-ui — LogosForge **Studio** UI

The shared React UI for the **Pro / Studio** line — a dockable, cinematic
writing workstation over the `logosforge` core. Consumed by **pro-desktop**
(Electron, local AI) and **pro-web** (browser, remote AI). Platform-neutral:
host apps inject an `ApiClient` + `PlatformAdapter`.

> **Development stage: integrated alpha.** The shared panels are implemented and
> wired to `@logosforge/ui-contracts` through the injected `ApiClient`. The design
> brief and tickets remain historical design inputs, not descriptions of stubs.

## Layout

```
src/
  adapters/      ApiClient + PlatformAdapter interfaces, <StudioProvider>
  theme/         design tokens (dark-first, cinematic, per-mode bands)
  components/    implemented panel areas + shared recovery/accessibility controls
  index.ts       public surface
STUDIO_UI_DESIGN_BRIEF.md   the full design brief (read this)
design-tickets/             one focused ticket per panel area
```

## Workspace contract

The canonical catalog describes 36 shared panels; hosts add the permanent AI
Companions surface for a complete 37-panel Pro workspace. Every one of those
panels can be placed in any of the four docks or detached as a modeless floating
window, then moved, resized, minimized, restored, raised, and redocked without
reparenting or remounting its React content. Manuscript and AI Companions are
non-closable, but they follow the same placement and floating-window contract as
the other panels.

Each catalog entry owns one unique panel shortcut. `Primary` means `Cmd` on
macOS and `Ctrl` elsewhere; established direct bindings are retained, and the
remaining catalog entries use the reserved `Primary+Alt+Shift+letter/digit`
family. Hosts must route those shortcuts through their normal panel-navigation
and save-barrier path. The action opens a closed panel, activates a docked one,
or restores and raises its existing float; it must never create a second panel
instance or bypass pending project saves.

Layouts are versioned and persisted per project. Focus is only a visibility
projection of that state: it presents Manuscript alone while leaving dock order,
floating geometry, z-order, and minimization untouched for the return to
Cockpit. Host implementations must preserve that round trip and keep panel
identity stable across every placement change.

## Rules

- **Never** import `electron`, Node, or browser-host APIs — use the injected
  `PlatformAdapter`. Components must run unchanged in Electron and the browser.
- **Never** reimplement core logic — call the injected `ApiClient` (which wraps
  `logosforge.api`). Data shapes come from `@logosforge/ui-contracts`.
- **Never** import or resemble the Whiteboard (Free) UI — Studio is its own
  visual identity.

## HTTP transport guarantees

The reference HTTP adapter owns its requests and live transports. Replacing a
client aborts outstanding fetches and closes polling/SSE. Health checks, reads,
and explicitly long AI/voice/export operations have separate configurable
timeouts; mutations deliberately have no client abort by default because a
disconnect after commit has an ambiguous outcome.

Simultaneous identical GETs share one network request but not one mutable result:
each caller receives a cloned JSON value. The entry disappears immediately after
settlement, and every mutation invalidates pending coalescing before and after the
write. This is request coalescing, not a response cache.

The Manuscript uses viewport-aware editor activation. Scene state and save queues
remain mounted, while expensive ProseMirror instances are limited to visible,
active, recently used, or unsaved scenes. The browser preview includes a
`?large-manuscript-harness` fixture with 180 scenes for regression measurement.

## Conventions (already wired into the scaffold)

- **`data-screen-label` on every panel root** — a stable screen id matching the
  design's Figma frame label, so design comments map to code. New panels must
  carry one; the `Placeholder` emits it from its required `screenLabel` prop.
- **`writingMode → --accent`** — the active writing mode scopes a single CSS
  custom property, `--accent`. Panels read it via `accent()` / `var(--accent)`
  and **never hardcode an accent color**. The provider scopes it for the whole
  tree; the shell re-asserts it locally. Re-skinning by mode = setting the mode
  once (`theme/accent.ts`).
- **One identity, one shortcut, one placement** — panel IDs and shortcut
  assignments are durable catalog data. A host may add its own panel definition,
  but it must keep IDs and shortcuts unique and render each open panel exactly
  once across all docks and floating windows.

## Usage (host app)

```tsx
import { StudioProvider } from "@logosforge/pro-shared-ui";
const services = { api: myApiClient, platform: myPlatformAdapter };
// writingMode (= the active project's narrative_engine) drives --accent:
<StudioProvider services={services} writingMode={project.narrative_engine}>
  {/* compose panels — each reads var(--accent) + carries a data-screen-label */}
</StudioProvider>
```
