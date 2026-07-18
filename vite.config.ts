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
  },
});
