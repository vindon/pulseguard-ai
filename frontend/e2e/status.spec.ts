import { test, expect } from './fixtures';

test.describe('Adapter status', () => {
  test('shows orchestrator stats, all 6 adapters, and all 6 circuit breakers', async ({ page }) => {
    await page.goto('/status');

    await expect(page.getByText('Running', { exact: true })).toBeVisible();
    await expect(page.getByText('escalations waiting')).toBeVisible();

    const adapterNames = ['X', 'Reddit', 'Google Play', 'App Store', 'Trustpilot', 'Quora'];
    for (const name of adapterNames) {
      await expect(page.getByTestId('status-card-name').filter({ hasText: name }).first()).toBeVisible();
    }

    await expect(page.getByTestId('status-card')).toHaveCount(12); // 6 adapters + 6 breakers
    await expect(page.locator('[data-testid="status-dot"][data-status="down"]')).toHaveCount(0);
  });
});
