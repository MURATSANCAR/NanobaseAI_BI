import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Geliştirmede /api → semantic bridge (REST). Sunucuda köprü 127.0.0.1:8795'e bağlı;
// Mac'ten:  ssh -N -L 3000:127.0.0.1:3000 nanobase
const ENGINE_URL = process.env.ENGINE_URL ?? 'http://127.0.0.1:8795';

// Üretimde alt yol altında servis edilir (portal.nanobase.ai/timas/): VITE_BASE=/timas/ npm run build
const BASE = process.env.VITE_BASE ?? '/';

export default defineConfig({
  base: BASE,
  plugins: [react()],
  server: {
    port: 5180,
    proxy: {
      '/api': { target: ENGINE_URL, changeOrigin: true },
    },
  },
  build: { outDir: 'dist', sourcemap: false },
});
