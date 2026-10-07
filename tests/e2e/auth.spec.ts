import { expect, test } from '@playwright/test';
import { mockAPI, token, user } from './fixtures';

test('registration and login establish the two-token session', async ({ page }) => {
  await mockAPI(page);
  await page.route('**/api/register', route => route.fulfill({ status: 201, json: { message: 'Compte créé.' } }));
  await page.route('**/api/login', route => route.fulfill({ json: { token: token(), refresh_token: token(Math.floor(Date.now() / 1000) + 604_800) } }));
  await page.goto('/auth?mode=register');
  await page.getByPlaceholder('Prénom').fill('Luis');
  await page.getByPlaceholder('Nom de famille').fill('Fernandes');
  await page.getByPlaceholder('Nom d’utilisateur').fill('luis');
  await page.getByPlaceholder('vous@exemple.fr').fill(user.email);
  await page.getByPlaceholder('8 caractères minimum').fill('correct-password');
  await page.getByRole('button', { name: 'Créer mon compte' }).click();
  await expect(page.getByRole('status')).toContainText('Compte créé');
  await page.getByPlaceholder('E-mail ou nom d’utilisateur').fill(user.email);
  await page.getByPlaceholder('8 caractères minimum').fill('correct-password');
  await page.getByRole('button', { name: 'Se connecter' }).click();
  await expect(page).toHaveURL(url => url.pathname === '/dashboard');
  await expect(page.getByRole('heading', { name: 'Accueil' })).toBeVisible();
  const cookies = await page.context().cookies();
  expect(cookies.some(cookie => cookie.name === 'auth_token')).toBe(true);
  expect(cookies.some(cookie => cookie.name === 'refresh_token')).toBe(true);
});

test('expired access is renewed once before private data loads', async ({ page }) => {
  await mockAPI(page);
  let refreshes = 0;
  await page.route('**/api/refresh', route => { refreshes += 1; return route.fulfill({ json: { token: token() } }); });
  await page.context().addCookies([{ name: 'refresh_token', value: token(Math.floor(Date.now() / 1000) + 604_800), domain: '127.0.0.1', path: '/' }]);
  await page.goto('/dashboard');
  await expect(page.getByRole('heading', { name: 'Accueil' })).toBeVisible();
  await expect.poll(() => refreshes).toBe(1);
});
