import { test, expect } from './fixtures';

test.describe('Escalations', () => {
  test('lists the unacknowledged escalation by default and filters by priority', async ({ page }) => {
    await page.goto('/escalations');
    await expect(page.locator('.esc-row')).toHaveCount(1);
    await expect(page.getByText(/High-severity repeat billing dispute/)).toBeVisible();

    await page.getByRole('button', { name: 'P2 High' }).click();
    await expect(page.locator('.empty-state')).toBeVisible();

    await page.getByRole('button', { name: 'All priorities' }).click();
    await expect(page.locator('.esc-row')).toHaveCount(1);
  });

  test('acknowledging from the drawer updates the row and clears the sidebar badge', async ({ page }) => {
    await page.goto('/escalations');
    await expect(page.locator('.nav-badge')).toHaveText('1');

    await page.locator('.esc-row').click();
    const drawer = page.locator('.drawer');
    await expect(drawer).toBeVisible();

    await drawer.getByRole('button', { name: 'Acknowledge' }).click();
    await expect(drawer.getByRole('button', { name: 'Acknowledged' })).toBeVisible();

    await drawer.getByLabel('Close').click();

    // "Unacknowledged only" is the default filter, so the now-acked
    // escalation should drop out immediately — the drawer's acknowledge
    // action broadcasts a refresh event precisely so this doesn't have to
    // wait out a poll interval (the sidebar badge alone polls every 20s).
    await expect(page.locator('.empty-state')).toBeVisible();
    await expect(page.locator('.nav-badge')).toHaveCount(0);
  });
});
