import { expect, test } from '@playwright/test';
import { authenticate, mockAPI } from './fixtures';

type RouteCase = { path: string; heading: string; authenticated?: boolean; canonicalPath?: string };

const firstPartyRoutes: RouteCase[] = [
  { path: '/', heading: 'Vos calculs.' },
  { path: '/service', heading: 'Votre projet avance' },
  { path: '/blockchain', heading: 'Du calcul au paiement' },
  { path: '/service/downloads/windows', heading: 'Installez une fois' },
  { path: '/service/downloads/windows-dev', heading: 'Installez une fois' },
  { path: '/service/downloads/linux-dev', heading: 'Installez une fois' }, { path: '/download', heading: 'Installez une fois' },
  { path: '/about', heading: 'Plusieurs machines' },
  { path: '/contact', heading: 'Une idée pour le réseau' },
  { path: '/auth?mode=login', heading: 'Connectez-vous' },
  { path: '/dashboard', heading: 'Accueil', authenticated: true },
  { path: '/jobs', heading: 'Mes projets', authenticated: true },
  { path: '/jobs/new', heading: 'Lancer un calcul', authenticated: true },
  { path: '/jobs/1', heading: 'Rendu architecture', authenticated: true },
  { path: '/jobs/1/dashboard', heading: 'Rendu architecture', authenticated: true, canonicalPath: '/jobs/1' },
  { path: '/jobs/1/result', heading: 'Rendu architecture', authenticated: true, canonicalPath: '/jobs/1' },
  { path: '/network', heading: 'Santé du réseau', authenticated: true },
  { path: '/nodes', heading: 'Machines', authenticated: true },
  { path: '/workloads', heading: 'Types de calcul', authenticated: true },
  { path: '/profile', heading: 'Paramètres', authenticated: true },
];

const knownRoute = /^(?:\/|\/service|\/blockchain|\/service\/downloads\/(?:windows|windows-dev|linux-dev)|\/download|\/about|\/contact|\/auth|\/dashboard|\/jobs|\/jobs\/new|\/jobs\/\d+(?:\/dashboard|\/result)?|\/network|\/nodes|\/workloads|\/profile)$/;

// This test opens all 20 routes one after the other: about 16 s on a fast
// machine, more than the default 30 s on the shared CI runner.
test('every first-party route and internal link has a canonical destination', async ({ page }) => {
  test.setTimeout(120_000);
  await mockAPI(page);
  const hrefs: string[][] = [];
  const publicRoutes = firstPartyRoutes.filter(route => !route.authenticated);
  for (const route of publicRoutes) {
    await page.goto(route.path, { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: route.heading, exact: false }).first()).toBeVisible();
    hrefs.push(await page.locator('a[href]').evaluateAll(anchors => anchors.map(anchor => anchor.getAttribute('href')).filter((href): href is string => Boolean(href))));
  }

  const privatePage = await page.context().newPage();
  await mockAPI(privatePage);
  await authenticate(privatePage);
  for (const route of firstPartyRoutes.filter(item => item.authenticated)) {
    await privatePage.goto(route.path, { waitUntil: 'domcontentloaded' });
    await expect(privatePage.getByRole('heading', { name: route.heading, exact: false }).first()).toBeVisible();
    expect(new URL(privatePage.url()).pathname).toBe(route.canonicalPath || route.path.split('?')[0]);
    hrefs.push(await privatePage.locator('a[href]').evaluateAll(anchors => anchors.map(anchor => anchor.getAttribute('href')).filter((href): href is string => Boolean(href))));
  }

  const invalid = [...new Set(hrefs.flatMap(items => items).map(href => new URL(href, 'http://127.0.0.1:3001')).filter(url => url.origin === 'http://127.0.0.1:3001' && !url.pathname.startsWith('/downloads/') && !url.pathname.startsWith('/examples/') && !url.pathname.startsWith('/api/') && !knownRoute.test(url.pathname)).map(url => url.pathname))];
  expect(invalid).toEqual([]);
  await privatePage.close();
});

test('unknown routes render the product 404 state instead of a blank page', async ({ page }) => {
  await mockAPI(page);
  await page.goto('/route-that-does-not-exist', { waitUntil: 'domcontentloaded' });
  await expect(page.locator('.error-page__code')).toHaveText(/^404/);
  await expect(page.getByRole('heading', { name: 'Cette page n’existe pas.' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
