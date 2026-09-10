import { expect, test } from '@playwright/test';
import { mockAPI } from './fixtures';

test.beforeEach(async ({ page }) => mockAPI(page));

test('public product journey stays coherent across all pages', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Ne soyez plus limité');
  await expect(page.locator('img[src="/brand/silicium-logo.png"]').first()).toBeVisible();
  for (const [name, path, heading] of [
    ['Produit', '/service', 'Votre projet avance'],
    ['Blockchain', '/blockchain', 'Du calcul au paiement'],
    ['À propos', '/about', 'Plusieurs machines'],
    ['Idées', '/contact', 'Une idée pour le réseau'],
  ] as const) {
    await page.getByRole('navigation', { name: 'Navigation principale' }).getByRole('link', { name: new RegExp(name) }).click();
    await expect(page).toHaveURL(url => url.pathname === path);
    await expect(page.getByRole('heading', { level: 1 })).toContainText(heading);
  }
});

test('service reports live components and concrete downloads', async ({ page }) => {
  await page.goto('/service');
  await expect(page.getByText('3 machines actives')).toBeVisible();
  await expect(page.getByText('Devnet', { exact: true }).first()).toBeVisible();
  await expect(page.getByRole('link', { name: 'Télécharger Silicium pour Windows, version stable' })).toHaveAttribute('href', '/downloads/silicium-node-windows.exe');
  await expect(page.getByRole('link', { name: 'Télécharger Silicium pour Windows, version test' })).toHaveAttribute('href', '/downloads/silicium-node-windows-dev.exe');
  await expect(page.getByRole('link', { name: 'Télécharger Silicium pour Linux, version test' })).toHaveAttribute('href', '/downloads/silicium-node-linux-dev.AppImage');
  await expect(page.getByRole('link', { name: 'Télécharger Silicium pour Linux, paquet Debian' })).toHaveAttribute('href', '/downloads/silicium-node-linux-dev.deb');
  await expect(page.getByRole('link', { name: 'Télécharger Silicium pour Linux, paquet RPM' })).toHaveAttribute('href', '/downloads/silicium-node-linux-dev.rpm');
  await expect(page.locator('.downloads__platform--windows svg')).toHaveCount(2);
  await expect(page.locator('.downloads__platform--linux svg')).toHaveCount(3);
  const walkthrough = page.locator('.process-story');
  await expect(walkthrough.getByText('Vous envoyez, une seule fois.', { exact: true })).toBeVisible();
  await walkthrough.getByRole('button', { name: 'Répartir' }).click();
  await expect(walkthrough.getByText('Les bonnes machines se coordonnent.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Rafraîchir' }).click();
  await expect(page.getByText('Paiements', { exact: true })).toBeVisible();
});

test('node download pages expose the published installer', async ({ page }) => {
  await page.goto('/service/downloads/windows');
  await expect(page.locator('.download-page__actions a').first()).toHaveAttribute('href', '/downloads/silicium-node-windows.exe');

  await page.goto('/service/downloads/windows-dev');
  await expect(page.locator('.download-page__actions a').first()).toHaveAttribute('href', '/downloads/silicium-node-windows-dev.exe');

  await page.goto('/service/downloads/linux-dev');
  await expect(page.locator('.download-page__actions a').first()).toHaveAttribute('href', '/downloads/silicium-node-linux-dev.AppImage');
  await expect(page.locator('.download-page__actions a').nth(1)).toHaveAttribute('href', '/downloads/silicium-node-linux-dev.deb');
  await expect(page.locator('.download-page__actions a').nth(2)).toHaveAttribute('href', '/downloads/silicium-node-linux-dev.rpm');
});

test('public mobile menu has no horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await page.getByRole('button', { name: 'Ouvrir le menu' }).click();
  await expect(page.getByRole('navigation', { name: 'Navigation mobile' }).getByRole('link', { name: 'Idées' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('glass surfaces follow the pointer with spatial depth', async ({ page }) => {
  await page.goto('/');
  const surface = page.locator('.network-panel');
  await expect(surface).toBeVisible();
  const box = await surface.boundingBox();
  expect(box).not.toBeNull();
  if (!box) return;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await expect.poll(() => surface.evaluate(element => ({ active: element.dataset.spatialActive, z: element.style.getPropertyValue('--spatial-z'), scale: element.style.getPropertyValue('--spatial-scale'), transform: getComputedStyle(element).transform }))).toMatchObject({ active: 'true' });
  const state = await surface.evaluate(element => ({
    z: element.style.getPropertyValue('--spatial-z'),
    scale: element.style.getPropertyValue('--spatial-scale'),
    transform: getComputedStyle(element).transform,
    backplate: getComputedStyle(element, '::after').transform,
    backplateContent: getComputedStyle(element, '::after').content,
  }));
  expect(Number.parseFloat(state.z)).toBeGreaterThan(0);
  expect(Number.parseFloat(state.scale)).toBeGreaterThan(1);
  expect(state.transform).not.toBe('none');
  expect(state.backplate).not.toBe('none');
  expect(state.backplateContent).not.toBe('none');
});
