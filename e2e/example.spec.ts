import { test, expect } from '@playwright/test';

test('local dashboard loads', async ({ page }) => {
  await page.goto('/#m3-panel');
  await expect(page.locator('#m3-panel')).toBeVisible();
  await expect(page.locator('#detail-dialog')).not.toBeVisible();
});

test('packet cards expose relevance and application links', async ({ page }) => {
  await page.goto('/#m3-panel');
  const cards = page.locator('#application-queue .packet-card');
  // A fresh database can legitimately have no prepared packets.
  await expect(page.locator('#m3-status')).toContainText('prepared application texts');
  if (await cards.count() === 0) return;
  const first = cards.first();
  await expect(first.getByRole('heading', { name: 'Why this role fits' })).toBeVisible();
  await expect(first.getByRole('heading', { name: 'Gaps to review' })).toBeVisible();
  const link = first.getByRole('link', { name: 'Open application', exact: true });
  if (await link.count()) {
    await expect(link).toHaveAttribute('href', /^https?:\/\//);
    await expect(link).toHaveAttribute('target', '_blank');
  } else {
    await expect(first.getByText('Application link unavailable')).toBeVisible();
  }
  await expect(page.locator('#detail-dialog')).not.toBeVisible();
});
