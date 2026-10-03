/** Selection helpers for reopening the host-persisted last active Pro project. */

export const PROJECT_SESSION_VERSION = 1;

export interface ProjectIdRecord {
  readonly id: number;
}

export interface ProjectSessionState {
  readonly version: number;
  readonly lastActiveProjectId: number | null;
}

export function projectIdFromSessionState(value: unknown): number | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const candidate = value as Partial<ProjectSessionState>;
  if (candidate.version !== PROJECT_SESSION_VERSION) return null;
  const projectId = candidate.lastActiveProjectId;
  return Number.isSafeInteger(projectId) && Number(projectId) > 0
    ? Number(projectId)
    : null;
}

export function selectStartupProjectId(
  projects: readonly ProjectIdRecord[],
  persistedProjectId: number | null,
): number | null {
  if (persistedProjectId != null && projects.some((project) => project.id === persistedProjectId)) {
    return persistedProjectId;
  }
  return projects[0]?.id ?? null;
}
