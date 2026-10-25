import { jwtDecode } from 'jwt-decode';
import { translate } from './i18n';

// Only a UI expiry check. The API remains responsible for verifying the signature.
export function tokenExpiry(token: unknown, now = Date.now()): Date | undefined {
  if (typeof token !== 'string' || !token) return;
  try {
    const { exp } = jwtDecode<{ exp?: number }>(token);
    if (typeof exp !== 'number' || !Number.isFinite(exp)) return;
    const expires = new Date(exp * 1000);
    return Number.isFinite(expires.getTime()) && expires.getTime() > now ? expires : undefined;
  } catch {
    return;
  }
}

export function authErrorMessage(error: unknown): string {
  const failure = error as { data?: { message?: unknown }; status?: number; statusCode?: number };
  if (typeof failure?.data?.message === 'string') return failure.data.message;
  const status = failure?.statusCode ?? failure?.status;
  if (status === 401) return translate('auth.invalidCredentials');
  if (status === 409) return translate('auth.taken');
  if (status === 400) return translate('auth.checkForm');
  if (status === 429) return translate('auth.tooMany');
  return translate('auth.unavailable');
}

/** A redirect target that stays on this site (`/jobs/3`), else `fallback`. */
export function safeRedirect(value: unknown, fallback = '/dashboard'): string {
  if (
    typeof value !== 'string' ||
    !value.startsWith('/') ||
    value.startsWith('//') ||
    value.startsWith('/\\') ||
    /[\u0000-\u001f]/.test(value)
  )
    return fallback;
  return value;
}
