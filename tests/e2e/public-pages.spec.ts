import { expect, test } from '@playwright/test';

test('public navigation reaches each page and returns home', async ({ page }) => {
  await page.route('**/api/health', route => route.fulfill({ json: { status: 'ok' } }));
  await page.route('**/downloads/update-manifest.json', route => route.fulfill({ json: { generated_utc: '2026-09-03T10:00:00Z', channels: {} } }));
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Un même calcul.');
  for (const [name, path, heading] of [
    ['À propos', '/about', 'Relier les machines.'],
    ['Service', '/service', 'Le site, les services VPS'],
    ['Contact', '/contact', 'Une question ?'],
  ]) {
    await page.getByRole('navigation', { name: 'Navigation principale' }).getByRole('link', { name, exact: true }).click();
    await expect(page).toHaveURL(url => url.pathname === path);
    await expect(page.getByRole('heading', { level: 1 })).toContainText(heading);
    await expect(page.getByRole('banner')).toHaveCount(1);
  }
  await page.getByRole('banner').getByRole('link', { name: 'Silicium', exact: true }).click();
  await expect(page).toHaveURL(url => url.pathname === '/');
});

test('status checks live on Service, with manual refresh and an offline state', async ({ page }) => {
  let checks = 0;
  await page.route('**/api/health', route => {
    checks += 1;
    return route.fulfill({ json: { status: 'ok', service: 'backend' } });
  });
  await page.route('**/downloads/update-manifest.json', route => route.fulfill({ json: { channels: {} } }));
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  expect(checks).toBe(0);
  await page.goto('/service');
  await expect.poll(() => checks).toBeGreaterThan(0);
  await expect(page.getByText('backend repond (ok).').first()).toBeVisible();
  await page.route('**/api/health', route => route.fulfill({ status: 503, json: {} }));
  await page.getByRole('button', { name: 'Rafraichir', exact: true }).click();
  await expect(page.getByText('Le backend ne repond pas pour le moment.').first()).toBeVisible();
  await expect(page.getByRole('link', { name: 'Telecharger le node Windows' })).toHaveAttribute('href', /silicium-node-windows/);
});

test('public navigation remains available on mobile', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  const navigation = page.getByRole('navigation', { name: 'Navigation principale' });
  await expect(navigation.getByRole('link', { name: 'À propos' })).toBeVisible();
  await navigation.getByRole('link', { name: 'Contact', exact: true }).click();
  await expect(page).toHaveURL(url => url.pathname === '/contact');
  await page.getByRole('button', { name: 'Se connecter', exact: true }).click();
  await expect(page).toHaveURL(/\/auth\?mode=login/);
});
