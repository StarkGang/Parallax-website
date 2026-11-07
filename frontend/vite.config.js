import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { cpSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));
const publishedAssets = [
  'Parallax Brochure Design Assets/Parallax Design Utilities/logos/logo.webp',
  'Parallax Brochure Design Assets/Parallax Design Utilities/logos/logo.webp',
  'Parallax Brochure Design Assets/Parallax Design Utilities/logos/Parallax Vector.svg',
  'Parallax Brochure Design Assets/Parallax Design Utilities/logos/NSSCE-Palakkad-Logo.webp',
  'Parallax Brochure Design Assets/Parallax Design Utilities/logos/Iste_logo.png',
  'Parallax Brochure Design Assets/Parallax Design Utilities/modified assets/globe.svg',
];

const copyBrandAssets = {
  name: 'copy-selected-supplied-assets',
  closeBundle() {
    for (const source of publishedAssets) {
      const target = resolve(root, 'dist/images', source);
      mkdirSync(dirname(target), { recursive: true });
      cpSync(resolve(root, 'images', source), target);
    }
  },
};

// The FastAPI app owns /api and /health; the SPA is served from the same origin
// in production and proxied to :8000 in development.
export default defineConfig({
  plugins: [react(), copyBrandAssets],
  base: process.env.VITE_BASE_PATH || '/',
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/three')) return 'vendor-three';
          if (id.includes('node_modules/gsap')) return 'vendor-gsap';
          if (
            id.includes('node_modules/react') ||
            id.includes('node_modules/react-dom') ||
            id.includes('node_modules/react-router-dom')
          ) {
            return 'vendor-react';
          }
        },
      },
    },
    chunkSizeWarningLimit: 700,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_PROXY || 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
      '/health': {
        target: process.env.VITE_API_PROXY || 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
    },
  },
});
