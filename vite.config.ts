import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

const runnerTarget = process.env.VITE_API_BASE || 'http://127.0.0.1:8787';

export default defineConfig({
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
