# @logosforge/pro-shared-ui — LogosForge **Studio** UI

The shared React UI for the **Pro / Studio** line — a dockable, cinematic
writing workstation over the `logosforge` core. Consumed by **pro-desktop**
(Electron, local AI) and **pro-web** (browser, remote AI). Platform-neutral:
host apps inject an `ApiClient` + `PlatformAdapter`.

> **This is a scaffold.** The structure, adapters, tokens, and per-panel stubs
> are in place; the actual panel UIs are designed in **Claude Design** (see
> `STUDIO_UI_DESIGN_BRIEF.md` + `design-tickets/`) and then recoded here in
> Claude Code, each wired to `@logosforge/ui-contracts` + the injected `ApiClient`.

## Layout

```
src/
  adapters/      ApiClient + PlatformAdapter interfaces, <StudioProvider>
  theme/         design tokens (dark-first, cinematic, per-mode bands)
  components/    one folder per panel area (stubs today)
  index.ts       public surface
STUDIO_UI_DESIGN_BRIEF.md   the full design brief (read this)
design-tickets/             one focused ticket per panel area
```

## Rules

- **Never** import `electron`, Node, or browser-host APIs — use the injected
  `PlatformAdapter`. Components must run unchanged in Electron and the browser.
- **Never** reimplement core logic — call the injected `ApiClient` (which wraps
  `logosforge.api`). Data shapes come from `@logosforge/ui-contracts`.
- **Never** import or resemble the Whiteboard (Free) UI — Studio is its own
  visual identity.

## Conventions (already wired into the scaffold)

- **`data-screen-label` on every panel root** — a stable screen id matching the
  design's Figma frame label, so design comments map to code. New panels must
  carry one; the `Placeholder` emits it from its required `screenLabel` prop.
- **`writingMode → --accent`** — the active writing mode scopes a single CSS
  custom property, `--accent`. Panels read it via `accent()` / `var(--accent)`
  and **never hardcode an accent color**. The provider scopes it for the whole
  tree; the shell re-asserts it locally. Re-skinning by mode = setting the mode
  once (`theme/accent.ts`).

## Usage (host app)

```tsx
import { StudioProvider } from "@logosforge/pro-shared-ui";
const services = { api: myApiClient, platform: myPlatformAdapter };
// writingMode (= the active project's narrative_engine) drives --accent:
<StudioProvider services={services} writingMode={project.narrative_engine}>
  {/* compose panels — each reads var(--accent) + carries a data-screen-label */}
</StudioProvider>
```
