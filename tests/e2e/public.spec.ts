import { expect, test } from '@playwright/test';
import { mockAPI } from './fixtures';

test.beforeEach(async ({ page }) => mockAPI(page));

test('public product journey stays coherent across all pages', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Vos calculs.');
  await expect(page.locator('img[src="/brand/silicium-logo.png"]').first()).toBeVisible();
  for (const [name, path, heading] of [
    ['Produit', '/service', 'Votre projet avance'],
    ['Blockchain', '/blockchain', 'Du calcul au paiement'],
    ['À propos', '/about', 'Plusieurs machines'],
    ['Contact', '/contact', 'Une idée pour le réseau'],
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
  await expect(page.getByRole('link', { name: 'APT — Debian / Ubuntu' })).toHaveAttribute('href', '/download?platform=linux&manager=apt#installation');
  await expect(page.getByRole('link', { name: 'DNF — Fedora / RHEL' })).toHaveAttribute('href', '/download?platform=linux&manager=dnf#installation');
  await expect(page.locator('.downloads__platform--windows svg')).toHaveCount(2);
  await expect(page.locator('.downloads__platform--linux svg')).toHaveCount(3);
  const walkthrough = page.locator('.process-story');
  await expect(walkthrough.getByText('Vous envoyez, une seule fois.', { exact: true })).toBeVisible();
  await walkthrough.getByRole('button', { name: 'Répartir' }).click();
  await expect(walkthrough.getByText('Les bonnes machines se coordonnent.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Rafraîchir' }).click();
  await expect(page.getByText('Paiements', { exact: true })).toBeVisible();
});

test('legacy download pages lead to the matching installation guide', async ({ page }) => {
  for (const [route, system, channel] of [
    ['/service/downloads/windows', 'windows', 'prod'],
    ['/service/downloads/windows-dev', 'windows', 'dev'],
    ['/service/downloads/linux-dev', 'linux', 'dev'],
  ]) {
    await page.goto(route);
    await expect(page).toHaveURL(url => url.pathname === '/download' && url.searchParams.get('platform') === system && url.searchParams.get('channel') === channel);
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Installez une fois');
  }
});

test('public mobile menu has no horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await page.getByRole('button', { name: 'Ouvrir le menu' }).click();
  await expect(page.getByRole('navigation', { name: 'Navigation mobile' }).getByRole('link', { name: 'Contact' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('the network diagram lets visitors follow each stage without pretending to be live', async ({ page }) => {
  await page.goto('/');
  const diagram = page.locator('.network-blueprint');
  await expect(diagram.getByText('Schéma de fonctionnement')).toBeVisible();
  await diagram.getByRole('button', { name: '03 Vérifier' }).click();
  await expect(diagram).toHaveAttribute('data-stage', '2');
  await expect(diagram.locator('[aria-live]')).toContainText('Des contrôles adaptés');
  await expect(page.locator('.network-status-strip')).toContainText('3');
});
