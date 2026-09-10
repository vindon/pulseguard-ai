import { test, expect } from './fixtures';

test.describe('Draft review queue', () => {
  test('lists a pending draft and approves it', async ({ page }) => {
    await page.goto('/drafts');

    await expect(page.getByTestId('draft-card')).toHaveCount(1);
    await expect(page.getByText(/To activate your eSIM/)).toBeVisible();

    await page.getByRole('button', { name: 'Approve & Send' }).click();
    await expect(page.getByTestId('draft-card')).toHaveCount(0);
  });

  test('rejects a draft', async ({ page }) => {
    await page.goto('/drafts');
    await page.getByRole('button', { name: 'Reject' }).click();
    await expect(page.getByTestId('draft-card')).toHaveCount(0);
  });
});
