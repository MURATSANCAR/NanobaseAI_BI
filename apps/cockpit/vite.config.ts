import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Geliştirmede /api → wren-ui (GraphQL + REST). Sunucuda wren-ui 127.0.0.1:3000'e bağlı;
// Mac'ten:  ssh -N -L 3000:127.0.0.1:3000 nanobase
const WREN_UI_URL = process.env.WREN_UI_URL ?? 'http://127.0.0.1:3000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5180,
    proxy: {
      '/api': { target: WREN_UI_URL, changeOrigin: true },
    },
  },
  build: { outDir: 'dist', sourcemap: false },
});
