import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  // Electron loads the packaged renderer through file://, so assets must be relative.
  base: "./",
  plugins: [react()],
  server: { port: 5173, strictPort: true },
});
