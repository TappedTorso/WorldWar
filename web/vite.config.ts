import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  base: process.env.VITE_BASE_PATH || "./",
  test: { environment: "jsdom", setupFiles: "./test/setup.ts", restoreMocks: true, maxWorkers: 2, testTimeout: 30000 },
});
