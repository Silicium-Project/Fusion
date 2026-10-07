// Language of the site: read from the cookie `silicium_locale` (French by
// default), kept in the Nuxt state so the browser starts in the language the
// server rendered, and written to `<html lang>`.
import { activeLocale, LOCALE_COOKIE, normalizeLocale, setServerLocaleResolver, type Locale } from '~/utils/i18n';

export default defineNuxtPlugin(() => {
  const cookie = useCookie<string | null>(LOCALE_COOKIE, { path: '/', sameSite: 'lax', maxAge: 365 * 24 * 60 * 60 });
  const locale = useState<Locale>('i18n:locale', () => normalizeLocale(cookie.value));

  if (import.meta.server) {
    setServerLocaleResolver(() => (tryUseNuxtApp() as { $locale?: { value: Locale } } | null)?.$locale?.value);
  } else {
    activeLocale.value = locale.value;
    watch(activeLocale, (value) => { locale.value = value; cookie.value = value; });
  }

  useHead({ htmlAttrs: { lang: () => (import.meta.server ? locale.value : activeLocale.value) } });
  return { provide: { locale } };
});
