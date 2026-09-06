import { test, expect } from './fixtures';

test.describe('Send test signal', () => {
  test('filling an example and submitting shows a success callout with a link to the queue', async ({
    page,
  }) => {
    await page.goto('/ingest');

    await page.getByRole('button', { name: /Billing dispute \(likely escalates\)/ }).click();
    await expect(page.getByLabel('What they said')).toHaveValue(/Verizon overcharged me AGAIN/);

    await page.getByRole('button', { name: 'Send to the pipeline' }).click();

    const success = page.getByTestId('callout-success');
    await expect(success).toBeVisible();
    await expect(success).toContainText('Queued as');
    await expect(success.getByRole('link', { name: 'signal queue' })).toHaveAttribute('href', '/queue');
  });

  test('submit is disabled until content is filled', async ({ page }) => {
    await page.goto('/ingest');
    await expect(page.getByRole('button', { name: 'Send to the pipeline' })).toBeDisabled();

    await page.getByLabel('What they said').fill('Something is broken.');
    await expect(page.getByRole('button', { name: 'Send to the pipeline' })).toBeEnabled();
  });
});
