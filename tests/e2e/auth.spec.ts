import { expect, test, type Page } from '@playwright/test';

const token = (exp: number, role = 'user') => `header.${Buffer.from(JSON.stringify({ exp, role })).toString('base64url')}.signature`;

async function mockPrivateAPI(page: Page) {
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/user') return route.fulfill({ json: { id: 1, username: 'test-user', email: 'test@example.test', role: 'admin' } });
    if (path === '/api/jobs') return route.fulfill({ json: [] });
    if (path.endsWith('/tasks')) return route.fulfill({ json: { workloads: [] } });
    if (path.endsWith('/peers')) return route.fulfill({ json: { peers: [] } });
    return route.fulfill({ json: { status: 'ok' } });
  });
}

async function fillRegistration(page: Page) {
  await page.getByPlaceholder('Prénom', { exact: true }).fill('Test');
  await page.getByPlaceholder('Nom de famille').fill('User');
  await page.getByPlaceholder("Nom d'utilisateur").fill('test-user');
  await page.getByPlaceholder('E-mail').fill('user@example.test');
  await page.getByPlaceholder('Mot de passe', { exact: true }).fill('correct-password');
}

test('signup opens registration and confirms account creation', async ({ page }) => {
  await mockPrivateAPI(page);
  await page.route('**/api/register', route => route.fulfill({ status: 201, json: { message: 'Compte créé.' } }));
  await page.goto('/');
  await page.getByRole('button', { name: "S'inscrire", exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Créer un compte' })).toBeVisible();
  await fillRegistration(page);
  await page.getByRole('button', { name: "S'inscrire", exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Compte créé');
  await expect(page.getByRole('button', { name: 'Connexion', exact: true })).toBeVisible();
});

test('invalid login and duplicate registration show errors', async ({ page }) => {
  await page.route('**/api/login', route => route.fulfill({ status: 401, json: { message: 'Mot de passe incorrect.' } }));
  await page.route('**/api/register', route => route.fulfill({ status: 409, json: { message: 'Adresse déjà utilisée.' } }));
  await page.goto('/auth');
  await page.getByPlaceholder('E-mail').fill('user@example.test');
  await page.getByPlaceholder('Mot de passe', { exact: true }).fill('wrong-password');
  await page.getByRole('button', { name: 'Connexion', exact: true }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'incorrect' })).toBeVisible();
  await page.getByRole('button', { name: /Besoin d'un compte/ }).click();
  await fillRegistration(page);
  await page.getByRole('button', { name: "S'inscrire", exact: true }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'déjà utilisée' })).toBeVisible();
  expect((await page.context().cookies()).some(cookie => cookie.name === 'auth_token')).toBe(false);
});

for (const account of [{ identifier: 'admin@example.test', role: 'admin' }, { identifier: 'test-user', role: 'user' }]) {
  test(`${account.role} signs in with ${account.identifier} and reaches the connected homepage`, async ({ page }) => {
    await mockPrivateAPI(page);
    const expires = Math.floor(Date.now() / 1000) + 900;
    await page.route('**/api/login', route => {
      expect(route.request().postDataJSON().identifier).toBe(account.identifier);
      return route.fulfill({ json: { token: token(expires, account.role) } });
    });
    await page.goto('/auth');
    await page.getByLabel('E-mail ou nom d’utilisateur').fill(account.identifier);
    await page.getByPlaceholder('Mot de passe', { exact: true }).fill('correct-password');
    await page.getByRole('button', { name: 'Connexion', exact: true }).click();
    await expect(page).toHaveURL(url => url.pathname === '/');
    const header = page.getByRole('banner');
    await expect(header.getByRole('link', { name: 'Dashboard', exact: true })).toBeVisible();
    await expect(header.getByRole('link', { name: 'test-user', exact: true })).toHaveAttribute('href', '/profile');
    await expect(header.getByRole('button', { name: 'Se connecter', exact: true })).toHaveCount(0);
    const cookie = (await page.context().cookies()).find(cookie => cookie.name === 'auth_token');
    expect(cookie).toBeDefined();
    expect(Math.abs(cookie!.expires - expires)).toBeLessThan(2);
    await page.reload();
    await expect(header.getByRole('link', { name: 'Dashboard', exact: true })).toBeVisible();
    await header.getByRole('link', { name: 'Dashboard', exact: true }).click();
    await expect(page).toHaveURL(url => url.pathname === '/dashboard');
  });
}

test('header switches back to sign-in when the session has disappeared', async ({ page, context }) => {
  await mockPrivateAPI(page);
  await context.addCookies([{ name: 'auth_token', value: token(Math.floor(Date.now() / 1000) + 900), domain: '127.0.0.1', path: '/' }]);
  await page.goto('/');
  const header = page.getByRole('banner');
  await expect(header.getByRole('link', { name: 'Dashboard', exact: true })).toBeVisible();
  await context.clearCookies();
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(header.getByRole('button', { name: 'Se connecter', exact: true })).toBeVisible();
  await expect(header.getByRole('link', { name: 'Dashboard', exact: true })).toHaveCount(0);
  await expect(header.getByRole('link', { name: 'test-user', exact: true })).toHaveCount(0);
});

test('header places Dashboard after the brand and links the username badge to the profile', async ({ page, context }) => {
  await mockPrivateAPI(page);
  await context.addCookies([{ name: 'auth_token', value: token(Math.floor(Date.now() / 1000) + 900), domain: '127.0.0.1', path: '/' }]);
  await page.goto('/');
  const header = page.getByRole('banner');
  const dashboard = header.getByRole('link', { name: 'Dashboard', exact: true });
  const profile = header.getByRole('link', { name: 'test-user', exact: true });
  await expect(profile).toBeVisible();
  await expect(profile.locator('[aria-hidden="true"]')).toHaveText('T');
  const brandBox = await header.getByText('Silicium', { exact: true }).boundingBox();
  const dashboardBox = await dashboard.boundingBox();
  const aboutBox = await header.getByRole('link', { name: 'À propos', exact: true }).boundingBox();
  const profileBox = await profile.boundingBox();
  expect(brandBox!.x + brandBox!.width).toBeLessThan(dashboardBox!.x);
  expect(dashboardBox!.x + dashboardBox!.width).toBeLessThan(aboutBox!.x);
  expect(profileBox!.x).toBeGreaterThan(aboutBox!.x + aboutBox!.width);
  await profile.click();
  await expect(page).toHaveURL(url => url.pathname === '/profile');
});

test('header uses the email when the account has no username', async ({ page, context }) => {
  await mockPrivateAPI(page);
  await page.route('**/api/user', route => route.fulfill({ json: { id: 1, email: 'fallback@example.test' } }));
  await context.addCookies([{ name: 'auth_token', value: token(Math.floor(Date.now() / 1000) + 900), domain: '127.0.0.1', path: '/' }]);
  await page.goto('/');
  const profile = page.getByRole('banner').getByRole('link', { name: 'fallback@example.test', exact: true });
  await expect(profile).toHaveAttribute('href', '/profile');
  await expect(profile.locator('[aria-hidden="true"]')).toHaveText('F');
});

test('logout returns to the homepage without an active session', async ({ page, context }) => {
  await mockPrivateAPI(page);
  await context.addCookies([{ name: 'auth_token', value: token(Math.floor(Date.now() / 1000) + 900), domain: '127.0.0.1', path: '/' }]);
  await page.goto('/profile');
  await page.getByRole('button', { name: 'Déconnexion', exact: true }).click();
  await expect(page).toHaveURL(url => url.pathname === '/');
  expect((await context.cookies()).some(cookie => cookie.name === 'auth_token')).toBe(false);
  const header = page.getByRole('banner');
  await expect(header.getByRole('button', { name: 'Se connecter', exact: true })).toBeVisible();
  await expect(header.getByRole('link', { name: 'Dashboard', exact: true })).toHaveCount(0);
  await expect(header.getByRole('link', { name: 'test-user', exact: true })).toHaveCount(0);
  await page.reload();
  await expect(page).toHaveURL(url => url.pathname === '/');
  await expect(header.getByRole('button', { name: 'Se connecter', exact: true })).toBeVisible();
});

test('an expired legacy cookie no longer redirects the landing page', async ({ page, context }) => {
  await mockPrivateAPI(page);
  await context.addCookies([{ name: 'auth_token', value: token(1), domain: '127.0.0.1', path: '/' }]);
  await page.goto('/');
  await expect.poll(async () => (await context.cookies()).some(cookie => cookie.name === 'auth_token')).toBe(false);
  await expect(page).toHaveURL(url => url.pathname === '/');
});

test('dashboard shares the header and returns home through the brand without signing out', async ({ page, context }, testInfo) => {
  await mockPrivateAPI(page);
  const session = token(Math.floor(Date.now() / 1000) + 900);
  await context.addCookies([{ name: 'auth_token', value: session, domain: '127.0.0.1', path: '/' }]);
  await page.goto('/dashboard');
  const header = page.getByRole('banner');
  await expect(header).toHaveCount(1);
  await expect(header.getByRole('link', { name: 'Dashboard', exact: true })).toHaveAttribute('href', '/dashboard');
  const profile = page.getByRole('link', { name: 'test-user', exact: true });
  await expect(profile).toHaveCount(1);
  await expect(header.getByRole('link', { name: 'test-user', exact: true })).toHaveAttribute('href', '/profile');
  await expect(page.getByRole('link', { name: 'Accueil', exact: true })).toHaveCount(0);
  const headerBox = await header.boundingBox();
  const titleBox = await page.getByRole('heading', { name: 'Tableau de bord', exact: true }).boundingBox();
  expect(titleBox!.y).toBeGreaterThan(headerBox!.y + headerBox!.height);
  await page.screenshot({ path: testInfo.outputPath('dashboard.png') });
  await page.getByRole('button', { name: 'Soumettre une tache', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Soumettre une tache', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '×', exact: true }).click();
  await header.getByRole('link', { name: 'Silicium', exact: true }).click();
  await expect(page).toHaveURL(url => url.pathname === '/');
  expect((await context.cookies()).find(cookie => cookie.name === 'auth_token')?.value).toBe(session);
  await page.reload();
  await expect(page).toHaveURL(url => url.pathname === '/');
});

for (const path of ['/auth', '/auth?mode=register']) {
  test(`${path} provides a working return-home link`, async ({ page }) => {
    await mockPrivateAPI(page);
    await page.goto(path);
    await page.getByRole('link', { name: 'Retour à l’accueil', exact: true }).click();
    await expect(page).toHaveURL(url => url.pathname === '/');
  });
}
