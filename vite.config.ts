import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// DB-GPT bridge (adapts /api/v1/bi/* → DB-GPT :5670). Override with VITE_API_BASE.
const runnerTarget = process.env.VITE_API_BASE || 'http://127.0.0.1:8787';
// Served under https://portal.nanobase.ai/bi/ — override with VITE_BASE=/ for rare root deploys.
const base = process.env.VITE_BASE || '/bi/';

export default defineConfig({
  base,
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') },
  },
  server: {
    port: 5174,
    proxy: {
      '/api': { target: runnerTarget, changeOrigin: true },
      '/health': { target: runnerTarget, changeOrigin: true },
    },
  },
  preview: {
    port: 4174,
    proxy: {
      '/api': { target: runnerTarget, changeOrigin: true },
      '/health': { target: runnerTarget, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (!id.includes('node_modules')) return undefined;
          // Charting stack (recharts + its d3/victory dependency tree).
          if (
            id.includes('/recharts/') ||
            id.includes('/recharts-scale/') ||
            id.includes('/victory-vendor/') ||
            id.includes('/d3-') ||
            id.includes('/internmap/') ||
            id.includes('/delaunator/') ||
            id.includes('/robust-predicates/')
          ) {
            return 'recharts';
          }
          // Schema graph stack.
          if (id.includes('/@xyflow/') || id.includes('/dagre/')) {
            return 'flow';
          }
          // Core framework vendor kept together and stable across releases.
          // clsx is pinned here too: it is imported by nearly every component,
          // and without an explicit assignment rollup hosts it inside the
          // recharts chunk — poisoning the entry with a 500 kB preload.
          if (
            id.includes('/react/') ||
            id.includes('/react-dom/') ||
            id.includes('/scheduler/') ||
            id.includes('/react-router/') ||
            id.includes('/react-router-dom/') ||
            id.includes('/@remix-run/') ||
            id.includes('/@tanstack/') ||
            id.includes('/clsx/')
          ) {
            return 'react-vendor';
          }
          return undefined;
        },
      },
    },
  },
});
