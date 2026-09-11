/** Structural identity check for the local Whiteboard backend health payload. */
export function isExpectedBackendHealth(value: unknown, expectedNonce: string): boolean {
  if (!value || typeof value !== 'object') return false;
  const health = value as Record<string, unknown>;
  return health.status === 'ok'
    && health.service === 'logosforge-whiteboard-backend'
    && typeof health.api_version === 'string'
    && health.api_version.length > 0
    && health.instance_nonce === expectedNonce;
}
