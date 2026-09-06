import { test, expect } from './fixtures';

test.describe('Overview', () => {
  test('loads with stats and recent signals, no console errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (err) => errors.push(String(err)));
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text());
    });

    await page.goto('/');

    await expect(page.getByTestId('page-title')).toHaveText('Overview');
    await expect(page.getByTestId('stat-card')).toHaveCount(4);
    await expect(page.getByText('Recent signals')).toBeVisible();

    await expect(page.getByTestId('queue-row')).toHaveCount(2);
    await expect(page.getByText(/Verizon overcharged me AGAIN/)).toBeVisible();

    expect(errors).toEqual([]);
  });

  test('sidebar shows the unacknowledged escalation badge', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByTestId('nav-badge')).toHaveText('1');
  });
});
