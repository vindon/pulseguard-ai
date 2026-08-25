import { test, expect } from './fixtures';
import AxeBuilder from '@axe-core/playwright';

const PAGES = ['/', '/queue', '/escalations', '/status', '/ingest'];

test.describe('Accessibility', () => {
  for (const path of PAGES) {
    test(`${path || '/'} has no automatically-detectable accessibility violations`, async ({ page }) => {
      await page.goto(path);
      await page.waitForLoadState('networkidle');
      const results = await new AxeBuilder({ page }).analyze();
      expect(results.violations).toEqual([]);
    });
  }

  test('the signal detail drawer has no violations while open', async ({ page }) => {
    await page.goto('/queue');
    await page.locator('.queue-row').first().click();
    await expect(page.locator('.drawer')).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });
});
