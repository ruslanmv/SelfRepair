import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    strictPort: true,
    proxy: {
      // Forward /api requests to the FastAPI backend during dev so we can
      // call /v1/jobs, /v1/metrics/dashboard, /webhooks/github, etc. without
      // CORS gymnastics. Override with VITE_API_TARGET in .env.development.
      "/api": {
        target: process.env.VITE_API_TARGET || "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    // Drop console.* in prod bundles; logs that matter go through the API.
    minify: "esbuild",
    target: "es2022",
  },
  resolve: {
    alias: {
      "@": "/src",
    },
  },
});
