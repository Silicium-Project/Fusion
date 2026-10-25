import { expect, test } from '@playwright/test';
import { authenticate, dashboard, job, mockAPI, user } from './fixtures';

// The longest values the site accepts, written without spaces: they must
// wrap or be cut, never widen the page (seen in acceptance tests: "a longer
// string takes the whole interface with it").
const longTitle = 'R'.repeat(120);
const longUser = {
  ...user,
  username: 'u'.repeat(30),
  firstName: 'F'.repeat(50),
  lastName: 'L'.repeat(50),
  email: `${'e'.repeat(60)}@example.test`,
};
const longJob = { ...job, title: longTitle, description: 'D'.repeat(1000) };

test.beforeEach(async ({ page }) => {
  await mockAPI(page);
  await page.route(/\/api\/user$/, (route) => route.fulfill({ json: longUser }));
  await page.route(/\/api\/jobs(\?.*)?$/, (route) =>
    route.request().method() === 'GET'
      ? route.fulfill({ headers: { 'x-total-count': '1' }, json: [longJob] })
      : route.fallback(),
  );
  await page.route(/\/api\/jobs\/1\/dashboard$/, (route) =>
    route.fulfill({ json: { ...dashboard, job: longJob } }),
  );
  await authenticate(page);
});

for (const width of [1280, 390]) {
  for (const path of ['/dashboard', '/jobs', '/jobs/1', '/profile']) {
    test(`${path} keeps its width with the longest names at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(path);
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(700);
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, `page wider than the window by ${overflow}px`).toBeLessThanOrEqual(1);
      // The page itself clips what overflows: each long text must also stay
      // inside its card (or the main column).
      const escaped = await page.evaluate(() => {
        const texts = document.querySelectorAll<HTMLElement>(
          '.job-head h1, .job-head p, .job-name strong, .profile-summary h2, .profile-summary > p, .metric-grid > *',
        );
        return [...texts]
          .filter((element) => {
            const box = element.getBoundingClientRect();
            const container = element
              .closest<HTMLElement>('.surface, .app-layout__main')
              ?.getBoundingClientRect();
            return (
              box.width > 0 &&
              (box.right > window.innerWidth + 1 ||
                (container !== undefined && box.right > container.right + 1))
            );
          })
          .map((element) => element.className || element.tagName);
      });
      expect(escaped, 'texts out of their card').toEqual([]);
    });
  }
}
