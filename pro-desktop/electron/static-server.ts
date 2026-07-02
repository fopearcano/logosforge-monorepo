/**
 * Minimal localhost static server for the PACKAGED renderer.
 *
 * Why not `loadFile()`? A `file://` page has a null origin, which the core's
 * CORS layer rejects — so every renderer→core fetch would fail in a packaged
 * build. Serving the built renderer from `http://127.0.0.1:<port>` instead
 * gives it a localhost origin, which the core's desktop-mode CORS regex
 * (`^https?://(localhost|127\.0\.0\.1)(:\d+)?$`) allows. Dev already runs on
 * localhost via Vite, so this is prod-only.
 *
 * Zero dependencies (Node http/fs) — keeps the Electron main free of a web
 * framework. Serves from a fixed root with path-traversal guarded and an SPA
 * fallback to index.html.
 */

import * as fs from 'node:fs';
import * as http from 'node:http';
import * as path from 'node:path';
import type { AddressInfo } from 'node:net';

const MIME: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.otf': 'font/otf',
  '.map': 'application/json',
  '.wasm': 'application/wasm',
};

export interface StaticServer {
  url: string;
  close: () => void;
}

/** Serve `rootDir` over a random localhost port; resolves with the base URL. */
export function serveStatic(rootDir: string, host = '127.0.0.1'): Promise<StaticServer> {
  const root = path.resolve(rootDir);
  const indexFile = path.join(root, 'index.html');

  const server = http.createServer((req, res) => {
    let filePath = indexFile;
    try {
      const urlPath = decodeURIComponent((req.url ?? '/').split('?')[0] ?? '/');
      const rel = urlPath === '/' ? 'index.html' : urlPath.replace(/^\/+/, '');
      const candidate = path.join(root, rel);
      // Path-traversal guard: never serve outside the root.
      if (candidate === root || candidate.startsWith(root + path.sep)) {
        if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) {
          filePath = candidate;
        }
      }
      const ext = path.extname(filePath).toLowerCase();
      res.writeHead(200, { 'Content-Type': MIME[ext] ?? 'application/octet-stream' });
      fs.createReadStream(filePath).pipe(res);
    } catch {
      res.writeHead(500);
      res.end('static server error');
    }
  });

  return new Promise((resolve, reject) => {
    server.on('error', reject);
    server.listen(0, host, () => {
      const { port } = server.address() as AddressInfo;
      resolve({ url: `http://${host}:${port}/`, close: () => server.close() });
    });
  });
}
