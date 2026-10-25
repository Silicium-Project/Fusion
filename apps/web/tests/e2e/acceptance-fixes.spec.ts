import { expect, test } from '@playwright/test';
import { authenticate, mockAPI } from './fixtures';

// Problems reported by the acceptance tests of October 2026.

test('the login and register tabs work with the keyboard', async ({ page }) => {
  await mockAPI(page);
  await page.goto('/auth?mode=login');
  const login = page.getByRole('tab', { name: 'Connexion' });
  const register = page.getByRole('tab', { name: 'Inscription' });
  await expect(login).toHaveAttribute('aria-selected', 'true');
  await expect(register).toHaveAttribute('tabindex', '-1');
  await login.focus();
  await page.keyboard.press('Tab');
  await expect(page.getByPlaceholder('E-mail ou nom d’utilisateur')).toBeFocused();
  await login.focus();
  await page.keyboard.press('ArrowRight');
  await expect(register).toBeFocused();
  await expect(register).toHaveAttribute('aria-selected', 'true');
  await expect(page).toHaveURL(/mode=register/);
  await expect(page.getByRole('tabpanel')).toContainText('Nom d’utilisateur');
});

test('connecting Phantom without the extension explains what to do', async ({ page }) => {
  await mockAPI(page);
  await authenticate(page);
  await page.goto('/profile');
  await page.getByRole('button', { name: 'Connecter Phantom' }).click();
  await expect(page.locator('.notice--danger')).toContainText('Phantom n’est pas installé');
});
