import { test as base, expect } from '@playwright/test';

const MOCK_BACKEND_URL = 'http://localhost:8001';

// All fixture state (e.g. the one escalation's acknowledged flag) lives in
// the single shared mock-backend process for the whole run, not per-test —
// reset it before every test, in every spec file, so no test's outcome can
// depend on what an earlier test (in this file or another) did to it.
export const test = base.extend<{ resetBackend: void }>({
  resetBackend: [
    async ({ request }, use) => {
      await request.post(`${MOCK_BACKEND_URL}/e2e/reset`);
      await use();
    },
    { auto: true },
  ],
});

export { expect };
