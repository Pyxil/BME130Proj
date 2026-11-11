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
      port: 5173,
      host: true,
      proxy: {
        "/api": {
          target: env.VITE_API_PROXY_TARGET || "http://localhost:8000",
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
