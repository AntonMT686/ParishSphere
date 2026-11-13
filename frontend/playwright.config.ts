import { defineConfig, devices } from '@playwright/test';

/**
 * End-to-end suite: the MVP demo journey against a running stack with the demo parish
 * (`ps-admin seed-demo`). Start everything with `scripts/e2e.sh` (SQLite, throwaway data) or point
 * E2E_BASE_URL at another stack, e.g. the Docker dev stack (http://stmarys.parishsphere.localhost).
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  outputDir: 'test-results',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://stmarys.parishsphere.localhost:5173',
    trace: 'off',
    screenshot: 'only-on-failure',
    acceptDownloads: true,
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : undefined,
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } },
  ],
});
