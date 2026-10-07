// Translation of the site (French, English, German).
//
// The catalogs are in `locales/`. `translate('jobs.table.project')` returns
// the message in the current language, French when the key is missing, and
// the key itself when it does not exist at all. Placeholders are `{name}`;
// plurals are functions of `{ count }`.
//
// The current language is chosen by the user (language switcher, cookie
// `silicium_locale`); French by default. In the browser it is the reactive
// `activeLocale`, so templates and computed values update when it changes.
// During server rendering it is read from the request's Nuxt app (several
// requests can be rendered at once, each in its own language).
import { ref } from 'vue';
// Relative imports: the unit tests load this file outside of Nuxt.
import { de } from '../locales/de';
import { en } from '../locales/en';
import { fr } from '../locales/fr';
import type { MessageParams } from '../locales/types';

export type Locale = 'fr' | 'en' | 'de';
export type { MessageParams };

/** The languages offered, in the order of the switcher. */
export const LOCALES: readonly { code: Locale; label: string; short: string; intl: string }[] = [
  { code: 'fr', label: 'Français', short: 'FR', intl: 'fr-FR' },
  { code: 'en', label: 'English', short: 'EN', intl: 'en-GB' },
  { code: 'de', label: 'Deutsch', short: 'DE', intl: 'de-DE' },
];

export const DEFAULT_LOCALE: Locale = 'fr';
export const LOCALE_COOKIE = 'silicium_locale';

const catalogs: Record<Locale, unknown> = { fr, en, de };

/** The language of the page in the browser. */
export const activeLocale = ref<Locale>(DEFAULT_LOCALE);

/** A supported language from a cookie or a tag ("en-US" → en), else French. */
export function normalizeLocale(value: unknown): Locale {
  const tag = String(value || '').trim().toLowerCase().slice(0, 2);
  return LOCALES.some(locale => locale.code === tag) ? tag as Locale : DEFAULT_LOCALE;
}

let serverLocale: (() => Locale | undefined) | undefined;

/** Set by the i18n plugin: the language of the request being rendered. */
export function setServerLocaleResolver(resolver: () => Locale | undefined): void {
  serverLocale = resolver;
}

/** The language of the current render. */
export function currentLocale(): Locale {
  if (import.meta.server && serverLocale) {
    const locale = serverLocale();
    if (locale) return locale;
  }
  return activeLocale.value;
}

/** The `Intl` locale of a language, for dates and numbers. */
export function intlLocale(locale: Locale = currentLocale()): string {
  return LOCALES.find(item => item.code === locale)?.intl || 'fr-FR';
}

function lookup(catalog: unknown, key: string): unknown {
  return key.split('.').reduce<unknown>((node, part) => (node && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined), catalog);
}

function messageFor(key: string, locale: Locale): unknown {
  const value = lookup(catalogs[locale], key);
  return value === undefined ? lookup(catalogs[DEFAULT_LOCALE], key) : value;
}

/** The message `key` in the current language, with its placeholders filled. */
export function translate(key: string, params: MessageParams = {}, locale: Locale = currentLocale()): string {
  const value = messageFor(key, locale);
  if (typeof value === 'function') return (value as (params: MessageParams) => string)(params);
  if (typeof value !== 'string') return key;
  return value.replace(/\{(\w+)\}/g, (match, name: string) => (name in params ? String(params[name]) : match));
}

/** A list of the catalog (steps, cards…) in the current language. */
export function translateList<T = string>(key: string, locale: Locale = currentLocale()): T[] {
  const value = messageFor(key, locale);
  return Array.isArray(value) ? value as T[] : [];
}

/** A size in bytes, in the units of the current language (Ko / KB…). */
export function formatBytes(bytes: number): string {
  const number = (value: number) => new Intl.NumberFormat(intlLocale(), { maximumFractionDigits: 1, minimumFractionDigits: 1 }).format(value);
  if (bytes < 1024) return translate('units.bytes', { value: bytes });
  if (bytes < 1024 * 1024) return translate('units.kb', { value: number(Math.max(0.1, bytes / 1024)) });
  return translate('units.mb', { value: number(bytes / 1024 / 1024) });
}
