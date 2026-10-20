import { expect, test } from '@playwright/test';
import path from 'node:path';
import { authenticate, mockAPI } from '../e2e/fixtures';

const publicPages = [
  ['home', '/'], ['service', '/service'], ['download', '/download'], ['blockchain', '/blockchain'], ['about', '/about'], ['contact', '/contact'], ['auth', '/auth'],
] as const;

const privatePages = [
  ['dashboard', '/dashboard'], ['jobs', '/jobs'], ['job-new', '/jobs/new'], ['job-detail', '/jobs/1'],
  ['network', '/network'], ['nodes', '/nodes'], ['profile', '/profile'],
] as const;

async function capture(page: Parameters<typeof mockAPI>[0], projectName: string, name: string, route: string, authenticated = false) {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await mockAPI(page);
  if (authenticated) await authenticate(page);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(route, { waitUntil: 'networkidle' });
  await page.waitForTimeout(250);
  await expect(page.locator('h1:visible, h2:visible').first()).toBeVisible();
  const layout = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, viewport: innerWidth, bodyFont: getComputedStyle(document.body).fontFamily }));
  expect(layout.width).toBeLessThanOrEqual(layout.viewport);
  expect(layout.bodyFont).toContain('Geist');
  expect(errors).toEqual([]);
  await page.screenshot({
    path: path.resolve('artifacts/design-audit/after', projectName, `${name}.png`),
    fullPage: true,
    animations: 'disabled',
  });
}

for (const [name, route] of publicPages) {
  test(`capture public ${name}`, async ({ page }, testInfo) => capture(page, testInfo.project.name, name, route));
}

for (const [name, route] of privatePages) {
  test(`capture private ${name}`, async ({ page }, testInfo) => capture(page, testInfo.project.name, name, route, true));
}

test('home distinguishes the diagram from observed network status', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'Checked once on desktop.');
  await mockAPI(page);
  await page.goto('/');
  await expect(page.locator('.network-blueprint')).toContainText('Schéma de fonctionnement');
  await expect(page.locator('.network-status-strip')).toContainText('Opérationnel');
});

test('live network telemetry displays the API snapshot', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'The live sample check runs once on the desktop project.');
  await mockAPI(page);
  await authenticate(page);
  await page.goto('/network', { waitUntil: 'networkidle' });
  const telemetry = page.locator('.live-network-map__telemetry');
  await expect(telemetry).toContainText('31.4 %');
  await expect(telemetry).toContainText('48.2 %');
  await expect(telemetry).toContainText('2');
});

test('scroll story keeps the 3D network visible and changes its stage', async ({ page }, testInfo) => {
  test.skip(!['desktop-wide', 'iphone-se'].includes(testInfo.project.name), 'The scroll story is checked on wide desktop and iPhone SE.');
  await mockAPI(page);
  await page.goto('/service', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  const story = page.locator('.process-story');
  const network = page.locator('.process-graph-3d');
  await expect(network).toBeVisible();
  await expect(network.locator('canvas')).toBeVisible();
  const snapshots: string[] = [];
  const targets: string[] = [];
  for (const [index, ratio] of [0, .25, .5, .75, 1].entries()) {
    await page.evaluate((value) => {
      const section = document.querySelector<HTMLElement>('.process-story');
      if (!section) return null;
      const scrollable = Math.max(1, section.offsetHeight - window.innerHeight);
      const top = window.scrollY + section.getBoundingClientRect().top + scrollable * value;
      document.documentElement.style.scrollBehavior = 'auto';
      window.scrollTo(0, top);
      document.documentElement.scrollTop = top;
      window.dispatchEvent(new Event('scroll'));
      return { target: top, scrollY: window.scrollY, rectTop: section.getBoundingClientRect().top, scrollable };
    }, ratio);
    await page.waitForTimeout(500);
    await expect(story).toBeVisible();
    await expect(network).toBeVisible();
    await expect(story.locator('.process-story__counter')).toContainText(`${String(Math.min(index + 1, 4)).padStart(2, '0')}`);
    targets.push((await network.getAttribute('data-camera-target')) || '');
    snapshots.push((await network.getAttribute('data-camera-position')) || '');
    await page.screenshot({ path: path.resolve('artifacts/design-audit/after', testInfo.project.name, `scroll-story-${index + 1}.png`), animations: 'disabled' });
  }
  expect(new Set(snapshots).size).toBeGreaterThan(3);
  expect(targets).toEqual(['source', 'relay-a', 'compute-a', 'result', 'result']);
  const cameraCoordinates = snapshots.map(snapshot => snapshot.split(',').map(Number));
  expect(new Set(cameraCoordinates.map(([x]) => x)).size).toBeGreaterThan(2);
  expect(new Set(cameraCoordinates.map(([, y]) => y)).size).toBeGreaterThan(2);
  expect(new Set(cameraCoordinates.map(([, , z]) => z)).size).toBeGreaterThan(2);

  // Selecting a distant stage updates the target immediately. The camera then
  // interpolates to that machine; no authored camera path is involved.
  await page.locator('.process-story__nav button').nth(0).click();
  await expect(network).toHaveAttribute('data-camera-target', 'source');
  await expect(network).toHaveAttribute('data-camera-moving', 'true');
  await page.waitForTimeout(350);
  await page.screenshot({ path: path.resolve('artifacts/design-audit/after', testInfo.project.name, 'scroll-story-camera-jump.png'), animations: 'disabled' });
});
