import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { loadEnv } from 'vite';
import { defineConfig } from 'vitest/config';

const root = fileURLToPath(new URL('..', import.meta.url));

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, root, 'VITE_');
  const target = process.env.VITE_PROXY_TARGET ?? env.VITE_PROXY_TARGET ?? 'http://127.0.0.1:8000';
  return {
    plugins: [react()],
    envDir: root,
    server: { proxy: { '/api': { target } } },
    preview: { proxy: { '/api': { target } } },
    test: {
      include: ['src/**/*.{test,spec}.{ts,tsx}'],
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      clearMocks: true,
      restoreMocks: true,
    },
  };
});
