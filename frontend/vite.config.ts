import { defineConfig } from "vite";
import preact from "@preact/preset-vite";

// `npm run dev` proxies /api (and the setup-ui pages) to a backend.
// WOT_BACKEND=http://walloftext.local to develop against the real Pi.
const backend = process.env.WOT_BACKEND || "http://localhost:8080";

export default defineConfig({
  plugins: [preact()],
  build: { outDir: "dist", emptyOutDir: true, sourcemap: false, target: "es2019", assetsInlineLimit: 0 },
  server: {
    host: true,
    proxy: Object.fromEntries(
      ["/api", "/ui", "/fonts", "/signin", "/setup", "/note", "/tokens.css"].map((p) => [p, { target: backend, changeOrigin: false }]),
    ),
  },
  test: { environment: "node" },
});
