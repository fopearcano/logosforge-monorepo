import { createServer } from 'node:net';

function tryBind(host: string, port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const server = createServer();
    let settled = false;
    const finish = (available: boolean) => {
      if (settled) return;
      settled = true;
      resolve(available);
    };
    server.unref();
    server.once('error', () => finish(false));
    server.listen({ host, port, exclusive: true }, () => {
      server.close(() => finish(true));
    });
  });
}

function ephemeralPort(host: string): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.unref();
    server.once('error', reject);
    server.listen({ host, port: 0, exclusive: true }, () => {
      const address = server.address();
      if (!address || typeof address === 'string') {
        server.close();
        reject(new Error('Could not allocate a local TCP port.'));
        return;
      }
      const port = address.port;
      server.close((error) => (error ? reject(error) : resolve(port)));
    });
  });
}

/**
 * Keep an explicitly configured port strict; otherwise escape a stale or
 * unrelated process on the default port by choosing an ephemeral localhost
 * port. The actual backend still proves identity with its one-time nonce.
 */
export async function selectAvailablePort(
  host: string,
  preferredPort: number,
  allowFallback: boolean,
): Promise<number> {
  if (await tryBind(host, preferredPort)) return preferredPort;
  if (!allowFallback) {
    throw new Error(
      `Port ${preferredPort} is already in use. Stop that process or choose another LOGOSFORGE_PORT.`,
    );
  }
  return ephemeralPort(host);
}
