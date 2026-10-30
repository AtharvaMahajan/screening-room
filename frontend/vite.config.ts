import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Where `uv run uvicorn ...` listens (see README.md).
const API_TARGET = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // The browser only ever talks to the Vite origin. Vite forwards /api to
    // FastAPI, so the app is same-origin in development (no CORS), matching the
    // planned same-origin deployment (project-structure.md §8, ADR-0007).
    proxy: {
      "/api": { target: API_TARGET },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
