import { expect, test } from '@playwright/test';
import { authenticate, dashboard, job, mockAPI } from './fixtures';

test.beforeEach(async ({ page }) => { await mockAPI(page); await authenticate(page); });

for (const pageCase of [
  { path: '/dashboard', heading: 'Accueil' }, { path: '/jobs', heading: 'Mes projets' },
  { path: '/jobs/new', heading: 'Lancer un calcul' }, { path: '/jobs/1', heading: 'Rendu architecture' },
  { path: '/network', heading: 'Santé du réseau' }, { path: '/nodes', heading: 'Machines' }, { path: '/profile', heading: 'Paramètres' },
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
  const continueButton = page.getByRole('button', { name: 'Continuer' });
  await expect(continueButton).toBeVisible();
  await page.getByPlaceholder('Ex. Rendu intérieur — version 4').fill('Rendu architecture');
  await page.locator('input[type=file]').setInputFiles({
    name: 'demo-scene.cfg',
    mimeType: 'text/plain',
    buffer: Buffer.from(`# Site raytracer fixture
camera :
{
  resolution = { width = 32 height = 20 }
  position = { x = 0 y = 0 z = 0 }
}
`),
  });
  await continueButton.click();
  await page.getByRole('button', { name: 'Continuer' }).click();
  const submit = page.getByRole('button', { name: 'Lancer le calcul' });
  await expect(submit).toBeEnabled();
  await submit.click();
  await expect(page).toHaveURL(url => url.pathname === '/jobs/1');
  await expect(page.getByRole('heading', { name: 'Rendu architecture' })).toBeVisible();
});

test('a failed job keeps the worker traceback visible', async ({ page }) => {
  await page.route('**/api/jobs/1/dashboard', route => route.fulfill({
    json: {
      ...dashboard,
      job: { ...job, status: 'failed', errorMessage: 'RuntimeError: worker failed\nTraceback (most recent call last):\n  worker.py:42\nValueError: bad scene' },
      summary: { ...dashboard.summary, success: false, stage: 'failed', failureDetail: 'RuntimeError: worker failed\nTraceback (most recent call last):\n  worker.py:42\nValueError: bad scene' },
    },
  }));
  await page.goto('/jobs/1');
  const notice = page.locator('.notice--danger');
  await expect(notice).toContainText('RuntimeError: worker failed');
  await expect(notice).toContainText('worker.py:42');
  await expect(notice).toContainText('ValueError: bad scene');
});

test('a SHA-256 job shows its chunks and its hash instead of an image', async ({ page }) => {
  const hashJob = { ...job, title: 'Empreinte archive', workload: 'calcul/integrity/sha256', fragmentCount: 2 };
  const fragments = [0, 1].map(fragment_index => ({ fragment_index, status: 'completed', handled_by: `worker-${fragment_index}` }));
  const report = {
    workload: 'calcul/integrity/sha256', algorithm: 'sha256', size_bytes: 10, chunk_count: 2, chunk_list_sha256: 'c'.repeat(64), input_hash: null,
    chunks: [{ index: 0, offset: 0, length: 5, sha256: 'a'.repeat(64) }, { index: 1, offset: 5, length: 5, sha256: 'b'.repeat(64) }],
  };
  await page.route('**/api/jobs/1/dashboard', route => route.fulfill({ json: { ...dashboard, job: hashJob, resultReady: true, summary: { success: true, fragmentCount: 2, fragments } } }));
  await page.route('**/api/jobs/1/result', route => route.fulfill({ json: report }));
  await page.goto('/jobs/1');
  await expect(page.getByText('Empreinte de la liste des morceaux')).toBeVisible();
  await expect(page.getByText('c'.repeat(64))).toBeVisible();
  await expect(page.getByText('b'.repeat(64))).toBeVisible();
  await expect(page.locator('.render-preview')).toHaveCount(0);
  await expect(page.getByText('2 terminés, 0 actifs, 0 en erreur.')).toBeVisible();
});

test('the project list exposes the submit path', async ({ page }) => {
  await page.goto('/jobs');
  const createLink = page.getByRole('main').getByRole('link', { name: 'Nouveau calcul' });
  await expect(createLink).toBeVisible();
  await createLink.click();
  await expect(page).toHaveURL(url => url.pathname === '/jobs/new');
});

test('connected mobile navigation remains usable and does not overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/dashboard');
  const navigation = page.getByRole('navigation', { name: 'Navigation mobile de l’application' });
  await expect(navigation.getByRole('link', { name: 'Mes projets' })).toBeVisible();
  await navigation.getByRole('link', { name: 'Nouveau calcul' }).click();
  await expect(page).toHaveURL(url => url.pathname === '/jobs/new');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('mobile navigation stays in flow instead of obscuring content', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/nodes');
  const layout = await page.evaluate(() => {
    const navigation = document.querySelector('.mobile-nav');
    const main = document.querySelector('.app-layout__main');
    if (!navigation || !main) return null;
    const navigationRect = navigation.getBoundingClientRect();
    const mainRect = main.getBoundingClientRect();
    return { position: getComputedStyle(navigation).position, navigationBottom: navigationRect.bottom, mainTop: mainRect.top };
  });
  expect(layout).not.toBeNull();
  expect(layout?.position).not.toBe('fixed');
  expect(layout?.navigationBottom).toBeLessThanOrEqual((layout?.mainTop || 0) + 1);
});

test('logout clears the session and returns to the public homepage', async ({ page }) => {
  await page.goto('/profile');
  await page.getByRole('button', { name: 'Déconnexion' }).click();
  await expect(page).toHaveURL(url => url.pathname === '/');
  const cookies = await page.context().cookies();
  expect(cookies.some(cookie => cookie.name === 'auth_token' || cookie.name === 'refresh_token')).toBe(false);
});
