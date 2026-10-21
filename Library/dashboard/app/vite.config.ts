import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// The dev server serves on 127.0.0.1 and hands /api to `dashboard serve
// --allow-origin http://127.0.0.1:5173`; the build is what the server serves.
export default defineConfig({
  plugins: [react()],
  base: './',
  server: { host: '127.0.0.1', port: 5173, strictPort: true, proxy: { '/api': { target: 'http://127.0.0.1:47900', changeOrigin: true } } },
  // theme.css is processed so a test can read its rules (?raw); vitest blanks every other stylesheet.
  // 30 s, not vitest's 5 s: under another build's load (example-terminal, 2026-10-14) whole App renders run five
  // times slower and passing tests hit the limit; nothing in them waits on a timer it never advances.
  test: { environment: 'jsdom', setupFiles: ['./src/test-setup.ts'], css: { include: [/theme\.css/] }, testTimeout: 30_000 },
});
