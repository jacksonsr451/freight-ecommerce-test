import { defineConfig } from '@playwright/test';
import { fileURLToPath } from 'node:url';

const viteCli = fileURLToPath(new URL('./node_modules/vite/bin/vite.js', import.meta.url));
const quoteShellArgument = (value: string) => `"${value.replaceAll('"', '\\"')}"`;

export default defineConfig({
  testDir: './tests/layout',
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  use: {
    channel:
      process.env.PLAYWRIGHT_BROWSER_CHANNEL ??
      (process.platform === 'win32' ? 'msedge' : 'chromium'),
    headless: true,
    baseURL: 'http://127.0.0.1:15173',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `${quoteShellArgument(process.execPath)} ${quoteShellArgument(viteCli)} --host 127.0.0.1 --port 15173 --strictPort`,
    url: 'http://127.0.0.1:15173',
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
