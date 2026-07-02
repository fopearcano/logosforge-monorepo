/**
 * @logosforge/pro-shared-ui — the LogosForge Studio shared React UI.
 *
 * Public surface: the injected adapters + provider, the design tokens + the
 * writingMode → --accent helpers, and the panel components. Host apps
 * (pro-desktop, pro-web) provide an `ApiClient` + `PlatformAdapter`, wrap their
 * tree in <StudioProvider> (passing the active `writingMode`), and compose the
 * panels into a dockable workspace.
 *
 * NOTE: components below are SCAFFOLD STUBS. They are filled in after the Studio
 * design is approved in Claude Design (see ../STUDIO_UI_DESIGN_BRIEF.md and
 * ../design-tickets/). Two conventions are already wired in: every panel carries
 * a `data-screen-label`, and accents come from `var(--accent)` (see theme/accent).
 */
export * from "./adapters/api";
export * from "./adapters/httpApiClient";
export * from "./adapters/platform";
export * from "./adapters/StudioProvider";
export * from "./hooks";
export * from "./theme/tokens";
export * from "./theme/accent";
export * from "./components";
