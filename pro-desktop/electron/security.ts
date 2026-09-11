/** Validate renderer-controlled values before they cross an Electron boundary. */

export function normalizeExternalUrl(target: string): string {
  let url: URL;
  try {
    url = new URL(target);
  } catch {
    throw new Error('External link is not a valid URL.');
  }
  if (url.protocol !== 'https:' && url.protocol !== 'http:') {
    throw new Error(`External URL scheme is not allowed: ${url.protocol}`);
  }
  return url.toString();
}

export function requireProjectId(projectId: number): number {
  if (!Number.isSafeInteger(projectId) || projectId < 1) {
    throw new Error('projectId must be a positive integer.');
  }
  return projectId;
}

/** Structural identity check before attaching to a process already on :8765. */
export function isExpectedCoreHealth(value: unknown, expectedNonce: string): boolean {
  if (!value || typeof value !== 'object') return false;
  const health = value as Record<string, unknown>;
  return health.status === 'ok'
    && health.service === 'logosforge-api'
    && typeof health.api_version === 'string'
    && health.api_version.length > 0
    && health.instance_nonce === expectedNonce;
}
