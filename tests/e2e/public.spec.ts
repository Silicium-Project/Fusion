import { expect, test } from '@playwright/test';
import { mockAPI } from './fixtures';

test.beforeEach(async ({ page }) => mockAPI(page));

test('public product journey stays coherent across all pages', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Du calcul distribué.');
  await expect(page.getByRole('link', { name: 'Silicium — Accueil' }).first().locator('img.brand-logo__mark')).toBeVisible();
  const primaryNavigation = page.getByRole('navigation', { name: 'Navigation principale' });
  await primaryNavigation.getByRole('link', { name: 'Produit' }).click();
  await expect(page).toHaveURL(url => url.pathname === '/service');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Votre projet avance');
  await page.getByRole('contentinfo').getByRole('link', { name: 'Blockchain' }).click();
  await expect(page).toHaveURL(url => url.pathname === '/blockchain');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Du calcul à la preuve');
  await primaryNavigation.getByRole('link', { name: 'À propos' }).click();
  await expect(page).toHaveURL(url => url.pathname === '/about');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Plusieurs machines');
  await primaryNavigation.getByRole('link', { name: 'Contact' }).click();
  await expect(page).toHaveURL(url => url.pathname === '/contact');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Une idée pour le réseau');
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
  const diagram = page.locator('.network-blueprint');
  await expect(diagram.getByRole('heading')).toBeVisible();
  const verification = diagram.getByRole('button').nth(2);
  await verification.click();
  await expect(verification).toHaveAttribute('aria-pressed', 'true');
  await expect(diagram.locator('[aria-live]')).not.toBeEmpty();
  await page.getByRole('button', { name: 'Rafraîchir' }).click();
  await expect(page.locator('.status-board article').nth(2)).toContainText('Traçabilité Solana');
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
  await page.goto('/service');
  const diagram = page.locator('.network-blueprint');
  await expect(diagram.getByText('Schéma de fonctionnement')).toBeVisible();
  const verifyStage = diagram.getByRole('button').nth(2);
  await verifyStage.click();
  await expect(verifyStage).toHaveAttribute('aria-pressed', 'true');
  await expect(diagram.locator('[aria-live]')).not.toBeEmpty();
});
