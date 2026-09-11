import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

// `.mts` keeps this config ESM without changing Electron's CommonJS main entry.
const here = dirname(fileURLToPath(import.meta.url)); // pro-desktop/renderer
const repo = resolve(here, '..', '..'); // the monorepo root

// The renderer consumes the shared package + contracts straight from source —
// no build/link step, HMR across the monorepo. The host apps would npm-link
// (file: deps) for a packaged build; aliasing to src keeps dev frictionless.
export default defineConfig({
  base: './', // packaged build loads assets relatively (file://)
  plugins: [react()],
  resolve: {
    // pro-shared-ui is aliased to source and bundled with the app, so React and
    // ProseMirror can be pulled from two node_modules trees — dedupe forces a
    // single copy of each (else: "invalid hook call" / duplicate prosemirror model).
    dedupe: [
      'react', 'react-dom',
      '@tiptap/core', '@tiptap/pm', '@tiptap/react', '@tiptap/starter-kit', '@tiptap/extensions',
      // every prosemirror-* @tiptap/pm re-exports — ProseMirror breaks on duplicate
      // module instances, so pin each to a single copy regardless of import path.
      'prosemirror-model', 'prosemirror-state', 'prosemirror-view', 'prosemirror-transform',
      'prosemirror-keymap', 'prosemirror-commands', 'prosemirror-history', 'prosemirror-inputrules',
      'prosemirror-gapcursor', 'prosemirror-dropcursor', 'prosemirror-schema-list', 'prosemirror-menu',
      'prosemirror-changeset', 'prosemirror-trailing-node',
    ],
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
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            {
              name: 'react-vendor',
              test: /node_modules[\\/](?:react|react-dom|scheduler)[\\/]/,
              priority: 30,
            },
            {
              name: 'editor-vendor',
              test: /node_modules[\\/](?:@tiptap|prosemirror-)/,
              priority: 20,
              includeDependenciesRecursively: true,
            },
            {
              name: 'studio-panels',
              test: /pro-shared-ui[\\/]src[\\/]components[\\/]/,
              priority: 15,
            },
            {
              name: 'vendor',
              test: /node_modules[\\/]/,
              priority: 10,
              minSize: 20_000,
            },
          ],
        },
      },
    },
  },
});
