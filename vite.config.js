import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { cpSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
const root = dirname(fileURLToPath(import.meta.url));
const publishedAssets = [
  'Parallax Brochure Design Assets/Parallax Design Utilities/logos/Parallax Logo.png',
  'Parallax Brochure Design Assets/Parallax Design Utilities/logos/NSSCE-Palakkad-Logo.webp',
  'Parallax Brochure Design Assets/Parallax Design Utilities/logos/ISTE LOGO NO  BG PNG.png',
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
// Set VITE_BASE_PATH=/ for user/organization sites or a custom domain.
export default defineConfig({
  plugins: [react(), copyBrandAssets],
  base: process.env.VITE_BASE_PATH || './',
});
