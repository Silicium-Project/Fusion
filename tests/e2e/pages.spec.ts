import { expect, test } from '@playwright/test';

const dashboardPayload = {
  job: {
    id: 1,
    title: 'Functional raytracer',
    workload: 'raytracer',
    priority: 'normal',
    status: 'completed',
    siliciumJobId: 'job-functional-1',
    errorMessage: '',
  },
  resultReady: false,
  resultUrl: '/jobs/1/result',
  diagnostics: {},
  summary: {
    success: true,
    stage: 'completed',
    fragmentCount: 1,
    image: { width: 32, height: 32 },
    fragments: [{ fragment_index: 0, status: 'verified', x_start: 0, x_end: 32, y_start: 0, y_end: 32 }],
    nodeRuns: [],
  },
  devnet: {},
};

test.beforeEach(async ({ context, page }) => {
  await context.addCookies([{
    name: 'auth_token',
    value: 'functional-token',
    domain: '127.0.0.1',
    path: '/',
  }]);
  await page.route('**/jobs/1/dashboard', (route) => route.fulfill({ json: dashboardPayload }));
  await page.route('**/user', (route) => route.fulfill({
    json: { id: 1, username: 'functional-user', email: 'test@example.invalid' },
  }));
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/jobs/network/peers')) {
      return route.fulfill({ json: { peers: [] } });
    }
    if (path.endsWith('/jobs/1/dashboard')) {
      return route.fulfill({ json: dashboardPayload });
    }
    if (path.endsWith('/jobs')) {
      return route.fulfill({
        headers: { 'x-total-count': '1', 'access-control-expose-headers': 'x-total-count' },
        json: [dashboardPayload.job],
      });
    }
    if (path.endsWith('/user')) {
      return route.fulfill({ json: { id: 1, username: 'functional-user', email: 'test@example.invalid' } });
    }
    return route.fulfill({ status: 404, json: { error: 'not mocked' } });
  });
});

for (const pageCase of [
  { path: '/auth', text: /connexion|inscription/i },
  { path: '/dashboard', text: 'Mes taches' },
  { path: '/profile', text: 'Compte' },
  { path: '/jobs/1/dashboard', text: 'Functional raytracer' },
]) {
  test(`${pageCase.path} renders without a browser error`, async ({ page }) => {
    const browserErrors: string[] = [];
    page.on('pageerror', (error) => browserErrors.push(error.message));
    await page.goto(pageCase.path);
    await expect(page.getByText(pageCase.text).first()).toBeVisible();
    expect(browserErrors).toEqual([]);
  });
}
