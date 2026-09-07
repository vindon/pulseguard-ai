import { test, expect } from './fixtures';

test.describe('Adapter status', () => {
  test('shows orchestrator stats, both adapters, and both circuit breakers', async ({ page }) => {
    await page.goto('/status');

    await expect(page.getByText('Running', { exact: true })).toBeVisible();
    await expect(page.getByText('escalations waiting')).toBeVisible();

    const adapterNames = ['X', 'Reddit'];
    for (const name of adapterNames) {
      await expect(page.getByTestId('status-card-name').filter({ hasText: name }).first()).toBeVisible();
    }

    await expect(page.getByTestId('status-card')).toHaveCount(4); // 2 adapters + 2 breakers
    await expect(page.locator('[data-testid="status-dot"][data-status="down"]')).toHaveCount(0);
  });
});
