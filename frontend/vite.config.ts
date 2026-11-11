/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv } from "vite";

// One .env for the whole project: the repository root (only VITE_* values reach the browser bundle).
const ENV_DIR = fileURLToPath(new URL("..", import.meta.url));

// API requests go to /api and are proxied to the FastAPI backend in development.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ENV_DIR, "");
  return {
    envDir: ENV_DIR,
    plugins: [react(), tailwindcss()],
    server: {
      // Listens on localhost only: no firewall prompt and not reachable from the network.
      // (`npm run dev -- --host` exposes it on purpose.)
      port: 5173,
      proxy: {
        "/api": {
          // 127.0.0.1, not localhost: the backend binds IPv4 and localhost may resolve to ::1 first.
          target: env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000",
          changeOrigin: true,
        },
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      css: false,
    },
  };
});
