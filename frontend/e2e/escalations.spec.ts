import { test, expect } from './fixtures';

test.describe('Escalations', () => {
  test('lists the unacknowledged escalation by default and filters by priority', async ({ page }) => {
    await page.goto('/escalations');
    await expect(page.getByTestId('escalation-row')).toHaveCount(1);
    await expect(page.getByText(/High-severity repeat billing dispute/)).toBeVisible();

    await page.getByRole('radio', { name: 'P2 High' }).click();
    await expect(page.getByTestId('empty-state')).toBeVisible();

    await page.getByRole('radio', { name: 'All priorities' }).click();
    await expect(page.getByTestId('escalation-row')).toHaveCount(1);
  });

  test('acknowledging from the drawer updates the row and clears the sidebar badge', async ({ page }) => {
    await page.goto('/escalations');
    await expect(page.getByTestId('nav-badge')).toHaveText('1');

    await page.getByTestId('escalation-row').click();
    const drawer = page.getByTestId('signal-drawer');
    await expect(drawer).toBeVisible();

    await drawer.getByRole('button', { name: 'Acknowledge' }).click();
    await expect(drawer.getByRole('button', { name: 'Acknowledged' })).toBeVisible();

    await drawer.getByLabel('Close').click();

    await expect(page.getByTestId('empty-state')).toBeVisible();
    await expect(page.getByTestId('nav-badge')).toHaveCount(0);
  });
});
