import type { AuthTokens, User } from '~/types/api';
import { clientCache } from '~/services/cache';
import { authErrorMessage, tokenExpiry } from '~/utils/auth';
import { currentLocale, translate } from '~/utils/i18n';

/** Headers of every API call: the API answers in the language of the site. */
export const languageHeaders = (): Record<string, string> => ({ 'Accept-Language': currentLocale() });

let refreshRequest: Promise<string | null> | null = null;

function requestStatus(error: unknown): number | undefined {
  const failure = error as { status?: number; statusCode?: number; response?: { status?: number } };
  return failure?.statusCode ?? failure?.status ?? failure?.response?.status;
}

export function useSession() {
  const config = useRuntimeConfig();
  const user = useState<User | null>('session:user', () => null);
  const ready = useState<boolean>('session:ready', () => false);
  const accessToken = useCookie<string | null>('auth_token', {
    path: '/', sameSite: 'lax', maxAge: 15 * 60,
    secure: import.meta.client ? window.location.protocol === 'https:' : false,
  });
  const refreshToken = useCookie<string | null>('refresh_token', {
    path: '/', sameSite: 'lax', maxAge: 7 * 24 * 60 * 60,
    secure: import.meta.client ? window.location.protocol === 'https:' : false,
  });

  const isAuthenticated = computed(() => Boolean(tokenExpiry(accessToken.value) || refreshToken.value));
  const displayName = computed(() => user.value?.username || user.value?.firstName || user.value?.email || translate('nav.myAccount'));
  const initials = computed(() => {
    const source = [user.value?.firstName, user.value?.lastName].filter(Boolean).join(' ') || displayName.value;
    return source.split(/\s+/).slice(0, 2).map(part => part.charAt(0)).join('').toUpperCase() || 'S';
  });

  function setTokens(tokens: AuthTokens): void {
    if (!tokenExpiry(tokens.token)) throw new Error(translate('errors.loginResponse'));
    accessToken.value = tokens.token;
    if (tokens.refresh_token) refreshToken.value = tokens.refresh_token;
  }

  function clearSession(): void {
    accessToken.value = null;
    refreshToken.value = null;
    user.value = null;
    ready.value = true;
    clientCache.invalidate();
  }

  async function renewAccessToken(): Promise<string | null> {
    if (!refreshToken.value) return null;
    if (import.meta.server) return refreshToken.value ? 'refresh-pending' : null;
    if (refreshRequest) return refreshRequest;

    refreshRequest = $fetch<AuthTokens>(`${config.public.apiBase}/refresh`, {
      method: 'POST', body: { refresh_token: refreshToken.value }, headers: languageHeaders(), retry: 0, timeout: 12_000,
    }).then((tokens) => {
      setTokens(tokens);
      return tokens.token;
    }).catch(() => {
      clearSession();
      return null;
    }).finally(() => { refreshRequest = null; });

    return refreshRequest;
  }

  async function ensureAccessToken(): Promise<string | null> {
    if (tokenExpiry(accessToken.value, Date.now() + 5_000)) return accessToken.value;
    accessToken.value = null;
    return renewAccessToken();
  }

  async function authorizedFetch<T>(path: string, options: Record<string, unknown> = {}, canRetry = true): Promise<T> {
    const token = await ensureAccessToken();
    if (!token || token === 'refresh-pending') throw Object.assign(new Error(translate('common.sessionExpired')), { statusCode: 401 });
    const headers = { ...languageHeaders(), ...(options.headers as Record<string, string> | undefined), Authorization: `Bearer ${token}` };
    try {
      return await $fetch<T>(`${config.public.apiBase}${path}`, { ...options, headers, retry: 0 } as never);
    } catch (error) {
      if (canRetry && requestStatus(error) === 401 && refreshToken.value) {
        accessToken.value = null;
        const renewed = await renewAccessToken();
        if (renewed) return authorizedFetch<T>(path, options, false);
      }
      if (requestStatus(error) === 401) clearSession();
      throw error;
    }
  }

  async function authorizedFetchRaw<T>(path: string, options: Record<string, unknown> = {}, canRetry = true): Promise<any> {
    const token = await ensureAccessToken();
    if (!token || token === 'refresh-pending') throw Object.assign(new Error(translate('common.sessionExpired')), { statusCode: 401 });
    const headers = { ...languageHeaders(), ...(options.headers as Record<string, string> | undefined), Authorization: `Bearer ${token}` };
    try {
      return await $fetch.raw<T>(`${config.public.apiBase}${path}`, { ...options, headers, retry: 0 } as never);
    } catch (error) {
      if (canRetry && requestStatus(error) === 401 && refreshToken.value) {
        accessToken.value = null;
        const renewed = await renewAccessToken();
        if (renewed) return authorizedFetchRaw<T>(path, options, false);
      }
      if (requestStatus(error) === 401) clearSession();
      throw error;
    }
  }

  async function loadUser(force = false): Promise<User | null> {
    if (import.meta.server) return user.value;
    if (ready.value && user.value && !force) return user.value;
    try {
      const profile = await clientCache.remember('session:user', () => authorizedFetch<User>('/user'), { ttl: 30_000, force });
      user.value = profile;
      return profile;
    } catch (error) {
      if (requestStatus(error) !== 401) throw error;
      return null;
    } finally {
      ready.value = true;
    }
  }

  async function login(identifier: string, password: string): Promise<User | null> {
    const tokens = await $fetch<AuthTokens>(`${config.public.apiBase}/login`, {
      method: 'POST', body: { identifier: identifier.trim(), password }, headers: languageHeaders(), retry: 0, timeout: 15_000,
    });
    setTokens(tokens);
    clientCache.invalidate();
    ready.value = false;
    return loadUser(true);
  }

  async function register(payload: { email: string; password: string; username?: string; first_name?: string; last_name?: string }): Promise<void> {
    await $fetch(`${config.public.apiBase}/register`, { method: 'POST', body: payload, headers: languageHeaders(), retry: 0, timeout: 15_000 });
  }

  async function saveProfile(payload: Record<string, string | undefined>): Promise<User> {
    const profile = await authorizedFetch<User>('/user', { method: 'PATCH', body: payload });
    user.value = profile;
    clientCache.invalidate('session:');
    return profile;
  }

  async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
    await authorizedFetch('/user/password', { method: 'PUT', body: { currentPassword, newPassword } });
  }

  return {
    user, ready, accessToken, refreshToken, isAuthenticated, displayName, initials,
    setTokens, clearSession, ensureAccessToken, authorizedFetch, authorizedFetchRaw,
    loadUser, login, register, saveProfile, changePassword,
    errorMessage: authErrorMessage,
  };
}
