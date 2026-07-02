import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// Root is this `renderer/` directory (passed positionally: `vite renderer`).
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
  },
});
