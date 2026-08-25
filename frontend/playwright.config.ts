import { defineConfig, devices } from '@playwright/test';

const MOCK_BACKEND_PORT = 8001;
const APP_PORT = 3100;

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.spec.ts',
  // Not fullyParallel: every spec shares one mock-backend process (and its
  // mutable fixture state, e.g. the acknowledged flag) across the whole run,
  // so tests must not interleave — see mock-backend.mjs's /e2e/reset.
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: [['html', { open: 'never' }]],
  use: {
    baseURL: `http://localhost:${APP_PORT}`,
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      command: `node e2e/mock-backend.mjs`,
      url: `http://localhost:${MOCK_BACKEND_PORT}/health`,
      reuseExistingServer: !process.env.CI,
      env: { MOCK_BACKEND_PORT: String(MOCK_BACKEND_PORT) },
      timeout: 20_000,
    },
    {
      command: 'npm run start',
      url: `http://localhost:${APP_PORT}`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        PORT: String(APP_PORT),
        PULSEGUARD_API_URL: `http://localhost:${MOCK_BACKEND_PORT}`,
        PULSEGUARD_API_KEY: 'e2e-test-key',
      },
    },
  ],
});
