import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base "./" keeps asset and data URLs relative, so the site works at
// https://<user>.github.io/terrasentinel/ as well as locally.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    chunkSizeWarningLimit: 900,
    rollupOptions: { output: { manualChunks: { maplibre: ["maplibre-gl"] } } },   // cached separately from app code
  },
});
