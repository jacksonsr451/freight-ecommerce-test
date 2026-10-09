import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/layout',
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  use: {
    channel: process.env.PLAYWRIGHT_BROWSER_CHANNEL ?? 'msedge',
    headless: true,
    baseURL: 'http://127.0.0.1:15173',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'npm run dev -- --port 15173',
    url: 'http://127.0.0.1:15173',
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
