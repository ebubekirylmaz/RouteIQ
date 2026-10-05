import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

// The API lives at the root of the FastAPI app, the dashboard under /dashboard/.
// In development the dev server forwards the API paths, so the browser sees one origin
// and no CORS setup is needed.
const API_PATHS = [
  "/config",
  "/requests",
  "/review",
  "/stats",
  "/route",
  "/deliveries",
  "/health",
  "/openapi.json",
];

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const target = env.ROUTEIQ_API_URL || "http://localhost:8000";

  return {
    base: "/dashboard/",
    plugins: [react()],
    server: {
      port: 5173,
      proxy: Object.fromEntries(
        API_PATHS.map((path) => [path, { target, changeOrigin: true }]),
      ),
    },
    // No source maps: they are served with the app, and they are 2 MB that nobody needs there.
    build: { outDir: "dist", sourcemap: false },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      restoreMocks: true,
    },
  };
});
