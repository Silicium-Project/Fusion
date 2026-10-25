import { tokenExpiry } from '~/utils/auth';

export default defineNuxtRouteMiddleware(() => {
  const access = useCookie<string | null>('auth_token');
  if (tokenExpiry(access.value)) return navigateTo('/dashboard');
});
