export default defineNuxtRouteMiddleware(async (to) => {
  const { ensureAccessToken } = useSession();
  const token = await ensureAccessToken();
  if (!token) return navigateTo({ path: '/auth', query: { mode: 'login', redirect: to.fullPath } });
});
