/**
 * Data hooks — the bridge from panels to the injected `ApiClient`. `useResource`
 * is the generic fetch/loading/error/live-refetch primitive; the per-domain
 * hooks (useNotes, useScenes, …) bind a project's API call to its change-events.
 */
export * from "./useResource";
export * from "./resources";
