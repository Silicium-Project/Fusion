import { expect, test } from '@playwright/test';
import { mockAPI } from './fixtures';

test.beforeEach(async ({ page }) => mockAPI(page));

test('public product journey stays coherent across all pages', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Votre réseau.');
  await expect(page.locator('img[src="/brand/silicium-logo.png"]').first()).toBeVisible();
  for (const [name, path, heading] of [
    ['Produit', '/service', 'Du calcul soumis'],
    ['À propos', '/about', 'Relier les machines.'],
    ['Contact', '/contact', 'Une question ?'],
  ] as const) {
    await page.getByRole('navigation', { name: 'Navigation principale' }).getByRole('link', { name, exact: true }).click();
    await expect(page).toHaveURL(url => url.pathname === path);
    await expect(page.getByRole('heading', { level: 1 })).toContainText(heading);
  }
});

test('service reports live components and concrete downloads', async ({ page }) => {
  await page.goto('/service');
  await expect(page.getByText('3 nœuds actifs')).toBeVisible();
  await expect(page.getByText('Devnet', { exact: true }).first()).toBeVisible();
  await expect(page.getByRole('link', { name: /Node Windows/ }).first()).toHaveAttribute('href', /silicium-node-windows/);
  await page.getByRole('button', { name: 'Rafraîchir' }).click();
  await expect(page.getByText('API Silicium')).toBeVisible();
});

test('public mobile menu has no horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await page.getByRole('button', { name: 'Ouvrir le menu' }).click();
  await expect(page.getByRole('navigation', { name: 'Navigation mobile' }).getByRole('link', { name: 'Contact' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
