import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));

// Dev-only harness for the pro-shared-ui panels. Aliases the contracts package
// straight to its source so no build/link step is needed.
export default defineConfig({
  root: here,
  plugins: [react()],
  resolve: {
    alias: {
      "@logosforge/ui-contracts": resolve(here, "../../logosforge-ui-contracts/src/index.ts"),
    },
  },
  server: {
    port: 5173,
    fs: { allow: [resolve(here, ".."), resolve(here, "../../logosforge-ui-contracts")] },
    // "Live core" mode hits these through here → no CORS. Start the core API on :8765.
    proxy: {
      "/api": { target: "http://localhost:8765", changeOrigin: true },
    },
  },
});
