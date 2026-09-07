import { test, expect } from './fixtures';

test.describe('Signal queue', () => {
  test('lists both fixture signals and filters by source', async ({ page }) => {
    await page.goto('/queue');
    await expect(page.getByTestId('queue-row')).toHaveCount(2);

    await page.getByRole('radio', { name: 'App Store' }).click();
    await expect(page.getByTestId('queue-row')).toHaveCount(1);
    await expect(page.getByText(/eSIM won't activate/)).toBeVisible();

    await page.getByRole('radio', { name: 'All feeds' }).click();
    await expect(page.getByTestId('queue-row')).toHaveCount(2);
  });

  test('opens the detail drawer with the full agent trail and closes it', async ({ page }) => {
    await page.goto('/queue');
    await page.getByTestId('queue-row').filter({ hasText: 'Verizon overcharged' }).click();

    const drawer = page.getByTestId('signal-drawer');
    await expect(drawer).toBeVisible();
    await expect(drawer.getByText('Billing dispute — verizon')).toBeVisible();
    await expect(drawer.getByTestId('timeline-agent').filter({ hasText: 'Sentinel' })).toBeVisible();
    await expect(drawer.getByTestId('timeline-agent').filter({ hasText: 'Triage' })).toBeVisible();
    await expect(drawer.getByTestId('timeline-agent').filter({ hasText: 'Escalation' })).toBeVisible();
    await expect(drawer.getByRole('button', { name: /Acknowledge/ })).toBeVisible();

    await drawer.getByLabel('Close').click();
    await expect(drawer).toBeHidden();
  });

  test('resolved signal shows a Resolved badge and no escalation section', async ({ page }) => {
    await page.goto('/queue');
    await page.getByTestId('queue-row').filter({ hasText: "eSIM won't activate" }).click();

    const drawer = page.getByTestId('signal-drawer');
    await expect(drawer.getByTestId('timeline-agent').filter({ hasText: 'Resolver' })).toBeVisible();
    await expect(drawer.getByTestId('timeline-agent').filter({ hasText: 'Escalation' })).toHaveCount(0);
    await expect(drawer.getByTestId('drawer-footer')).not.toBeVisible();
  });
});
