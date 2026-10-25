import { expect, test } from '@playwright/test';
import { authenticate, mockAPI } from './fixtures';

// Ad and tracking blockers (AdGuard was reported) cut requests whose name
// looks like statistics or telemetry: the pages must stay readable.
const lookAlikeTracking =
  /(metric|stat|telemetr|track|analytic|manifest|peers|beacon|[/_.-]ads?[/_.-]|banner|sponsor)/i;

test.beforeEach(async ({ page }) => {
  await mockAPI(page);
  await authenticate(page);
  await page.route(lookAlikeTracking, (route) => route.abort());
});

for (const path of ['/', '/download', '/dashboard', '/jobs', '/workloads']) {
  test(`${path} stays readable when a blocker cuts look-alike tracking requests`, async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(path);
    await expect(page.locator('h1').first()).toBeVisible();
    await expect(page.locator('h1').first()).not.toHaveText('');
    expect(errors).toEqual([]);
  });
}
