import { expect, test } from '@playwright/test';
import { mockAPI } from './fixtures';

test.beforeEach(async ({ page }) => mockAPI(page));

test('Linux onboarding includes setup, installation and the correct channel', async ({
  page,
  context,
}) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await page.goto('/download?channel=prod');
  const installer = page.getByTestId('repository-installer');
  await expect(installer.getByTestId('dev-prerequisites')).toHaveCount(0);
  await expect(installer.locator('.repository-installer__step pre').first()).toContainText(
    '/etc/apt/keyrings/silicium-prod.gpg',
  );
  await expect(installer.locator('.repository-installer__step pre').first()).toContainText(
    '/etc/apt/sources.list.d/silicium-prod.sources',
  );
  await expect(installer.locator('.repository-installer__step pre').nth(1)).toContainText(
    'sudo apt install silicium-node',
  );
  const code = await installer.locator('.repository-installer__step pre').first().innerText();
  await installer.getByRole('button', { name: 'Copier — APT · Stable', exact: true }).click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(code);

  await installer.getByRole('button', { name: 'DNF Fedora / RHEL' }).click();
  await expect(installer.locator('.repository-installer__step pre').first()).toContainText(
    'https://vps-910c1dbc.vps.ovh.net/downloads/rpm/silicium-node.repo',
  );
  await page.getByRole('button', { name: 'Développement', exact: true }).click();
  await expect(installer.getByTestId('dev-prerequisites')).toContainText('WireGuard');
  await expect(installer.locator('.repository-installer__step pre').first()).toContainText(
    'https://10.77.0.1:8443',
  );
  await expect(installer.locator('.repository-installer__step pre').first()).toContainText(
    '/etc/yum.repos.d/silicium-dev.repo',
  );
  await installer.getByText('Installer le certificat sur ce système', { exact: true }).click();
  await expect(installer.getByTestId('dev-prerequisites').locator('pre')).toContainText(
    'update-ca-trust',
  );
  await expect(installer.getByTestId('dev-prerequisites').locator('pre')).not.toContainText('.ssh');
  await expect(page.locator('a[href$=".deb"], a[href$=".rpm"]')).toHaveCount(0);
});

test('distribution deep links and translated controls keep commands intact', async ({ page }) => {
  await page.goto('/download?channel=dev&manager=dnf');
  await expect(page.getByRole('button', { name: 'DNF Fedora / RHEL' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await page.getByRole('button', { name: 'English', exact: true }).first().click();
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Install once.');
  await expect(
    page.getByTestId('repository-installer').locator('.repository-installer__step pre').first(),
  ).toContainText('/etc/yum.repos.d/silicium-dev.repo');
  await page.getByRole('button', { name: 'Windows', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Download for Windows' })).toHaveAttribute(
    'href',
    'https://10.77.0.1:8443/downloads/silicium-node-windows-dev.exe',
  );
});

test('offline status stays unavailable and does not invent machine counts', async ({ page }) => {
  await page.route('**/api/status', (route) => route.fulfill({ status: 503, json: {} }));
  await page.goto('/');
  await expect(page.locator('.live-metrics-panel__metrics dd')).toHaveText(['—', '—', '—']);
  await page.goto('/service#status');
  await expect(
    page.locator('.status-board article').nth(1).locator('.status-board__main>strong'),
  ).toHaveText('—');
});

test('public home and installation fit small screens and the menu works with Escape', async ({
  page,
}) => {
  for (const width of [320, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    for (const path of ['/', '/download?channel=dev&manager=dnf']) {
      await page.goto(path);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
      for (const element of await page
        .locator('.repo-options, .command-snippet:visible, .repository-installer__prerequisite')
        .all()) {
        const box = await element.boundingBox();
        if (box) {
          expect(box.x).toBeGreaterThanOrEqual(0);
          expect(box.x + box.width).toBeLessThanOrEqual(width);
        }
      }
    }
  }
  await page.setViewportSize({ width: 390, height: 844 });
  const menu = page.getByRole('button', { name: 'Ouvrir le menu' });
  await menu.click();
  await expect(
    page.getByRole('navigation', { name: 'Navigation mobile', exact: true }),
  ).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(menu).toBeFocused();
  await expect(
    page.getByRole('navigation', { name: 'Navigation mobile', exact: true }),
  ).toHaveCount(0);
});
