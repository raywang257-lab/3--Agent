import { resolve } from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  root: resolve(__dirname, "streamlit_web"),
  base: "./",
  plugins: [react()],
  build: {
    outDir: resolve(__dirname, "agent_backend/static_dashboard"),
    emptyOutDir: true,
  },
});
