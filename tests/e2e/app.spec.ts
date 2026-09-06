import { expect, test } from '@playwright/test';
import { authenticate, mockAPI } from './fixtures';

test.beforeEach(async ({ page }) => { await mockAPI(page); await authenticate(page); });

for (const pageCase of [
  { path: '/dashboard', heading: 'Vue d’ensemble' }, { path: '/jobs', heading: 'Tâches' },
  { path: '/jobs/new', heading: 'Configurer une tâche' }, { path: '/jobs/1', heading: 'Rendu architecture' },
  { path: '/network', heading: 'Réseau' }, { path: '/nodes', heading: 'Nœuds' }, { path: '/profile', heading: 'Paramètres' },
]) {
  test(`${pageCase.path} renders without browser errors`, async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(pageCase.path);
    await expect(page.getByRole('heading', { name: pageCase.heading, exact: true }).first()).toBeVisible();
    expect(errors).toEqual([]);
  });
}

test('a job can be submitted and opens its canonical detail route', async ({ page }) => {
  await page.goto('/jobs/new');
  await page.getByPlaceholder('Ex. Rendu intérieur — version 4').fill('Rendu architecture');
  await page.locator('input[type=file]').setInputFiles({ name: 'scene.cfg', mimeType: 'text/plain', buffer: Buffer.from('scene') });
  await page.getByRole('button', { name: 'Lancer la tâche' }).click();
  await expect(page).toHaveURL(url => url.pathname === '/jobs/1');
  await expect(page.getByRole('heading', { name: 'Rendu architecture' })).toBeVisible();
});

test('connected mobile navigation remains usable and does not overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/dashboard');
  const navigation = page.getByRole('navigation', { name: 'Navigation mobile de l’application' });
  await expect(navigation.getByRole('link', { name: 'Tâches' })).toBeVisible();
  await navigation.getByRole('link', { name: 'Réseau' }).click();
  await expect(page).toHaveURL(url => url.pathname === '/network');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('logout clears the session and returns to the public homepage', async ({ page }) => {
  await page.goto('/profile');
  await page.getByRole('button', { name: 'Déconnexion' }).click();
  await expect(page).toHaveURL(url => url.pathname === '/');
  const cookies = await page.context().cookies();
  expect(cookies.some(cookie => cookie.name === 'auth_token' || cookie.name === 'refresh_token')).toBe(false);
});
