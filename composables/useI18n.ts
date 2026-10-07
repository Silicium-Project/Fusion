import { activeLocale, formatBytes, LOCALES, translate, translateList, type Locale } from '~/utils/i18n';

/**
 * Translation in components: `t('key', { count })`, `tl('key')` for the
 * lists of the catalog, and the language switcher's `setLocale`.
 */
export function useI18n() {
  const locale = computed(() => (import.meta.server ? (useNuxtApp().$locale as { value: Locale }).value : activeLocale.value));
  function setLocale(code: Locale) {
    activeLocale.value = code;
  }
  return { t: translate, tl: translateList, formatBytes, locale, setLocale, locales: LOCALES };
}
