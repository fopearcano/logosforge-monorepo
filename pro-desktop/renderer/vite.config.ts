import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url)); // pro-desktop/renderer
const repo = resolve(here, '..', '..'); // the monorepo root

// The renderer consumes the shared package + contracts straight from source —
// no build/link step, HMR across the monorepo. The host apps would npm-link
// (file: deps) for a packaged build; aliasing to src keeps dev frictionless.
export default defineConfig({
  base: './', // packaged build loads assets relatively (file://)
  plugins: [react()],
  resolve: {
    alias: {
      '@logosforge/pro-shared-ui': resolve(repo, 'pro-shared-ui/src/index.ts'),
      '@logosforge/ui-contracts': resolve(repo, 'logosforge-ui-contracts/src/index.ts'),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    fs: { allow: [repo] },
  },
  build: { outDir: 'dist', emptyOutDir: true },
});
