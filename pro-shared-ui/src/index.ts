/**
 * @logosforge/pro-shared-ui — the LogosForge Studio shared React UI.
 *
 * Public surface: the injected adapters + provider, the design tokens + the
 * writingMode → --accent helpers, and the panel components. Host apps
 * (pro-desktop, pro-web) provide an `ApiClient` + `PlatformAdapter`, wrap their
 * tree in <StudioProvider> (passing the active `writingMode`), and compose the
 * panels into a dockable workspace.
 *
 * The integrated-alpha panels below are backed by the injected API and platform
 * adapters. Every panel carries a `data-screen-label`, and accents come from
 * `var(--accent)` (see theme/accent).
 */
export * from "./adapters/api";
export * from "./adapters/httpApiClient";
export * from "./adapters/platform";
export * from "./adapters/projectSaveCoordinator";
export * from "./adapters/clientLifetime";
export * from "./adapters/StudioProvider";
export * from "./hooks";
export * from "./theme/tokens";
export * from "./theme/accent";
export * from "./components";
