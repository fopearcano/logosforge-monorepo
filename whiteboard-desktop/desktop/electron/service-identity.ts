/** Structural identity check for the local Whiteboard backend health payload. */
const BACKEND_LOOPBACK_HOST = '127.0.0.1';

/** Production backends are local-only; source development may opt into LAN binding. */
export function resolveBackendHost(
  requestedHost: string | undefined,
  production: boolean,
): string {
  const requested = requestedHost?.trim() || BACKEND_LOOPBACK_HOST;
  return production ? BACKEND_LOOPBACK_HOST : requested;
}

export function isExpectedBackendHealth(value: unknown, expectedNonce: string): boolean {
  if (!value || typeof value !== 'object') return false;
  const health = value as Record<string, unknown>;
  return health.status === 'ok'
    && health.service === 'logosforge-whiteboard-backend'
    && typeof health.api_version === 'string'
    && health.api_version.length > 0
    && health.instance_nonce === expectedNonce;
}
