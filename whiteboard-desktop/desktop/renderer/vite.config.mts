import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// `.mts` keeps Vite's config unambiguously ESM while Electron's main package
// remains CommonJS. Root is this `renderer/` directory (`vite renderer`).
export default defineConfig({
  plugins: [react()],
  // Relative base so the built index.html loads assets over file:// in Electron.
  base: './',
  server: {
    port: 5173,
    strictPort: true,
    // Windows file-watch reliability. Native FS events (chokidar) can MISS edits to
    // existing files here — especially atomic writes (temp file + rename) — leaving
    // Vite serving a stale cached transform until the dev server is restarted. Polling
    // watches by mtime, so every save fires HMR without a restart; `awaitWriteFinish`
    // means a poll never reads a half-written file. node_modules/.git are ignored by
    // default, so this only polls source (cheap).
    watch: {
      usePolling: true,
      interval: 150,
      awaitWriteFinish: { stabilityThreshold: 120, pollInterval: 40 },
    },
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
