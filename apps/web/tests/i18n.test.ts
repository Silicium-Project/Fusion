import { afterEach, describe, expect, it } from 'vitest';
import { de } from '../locales/de';
import { en } from '../locales/en';
import { fr } from '../locales/fr';
import { activeLocale, formatBytes, normalizeLocale, translate, translateList } from '../utils/i18n';
import { statusLabel } from '../utils/format';
import { fragmentStateLabel } from '../utils/jobs';

/** Every key path of a catalog, with the kind of its value. */
function shape(node: unknown, prefix = ''): string[] {
  if (typeof node === 'function') return [`${prefix}:function`];
  if (typeof node === 'string') return [`${prefix}:string`];
  if (Array.isArray(node)) return node.flatMap((item, index) => shape(item, `${prefix}[${index}]`));
  return Object.entries(node as Record<string, unknown>).flatMap(([key, value]) => shape(value, prefix ? `${prefix}.${key}` : key));
}

describe('translation', () => {
  afterEach(() => { activeLocale.value = 'fr'; });

  it('has the same messages, lists and plurals in every language', () => {
    const reference = shape(fr).sort();
    expect(shape(en).sort()).toEqual(reference);
    expect(shape(de).sort()).toEqual(reference);
  });

  it('fills placeholders and plurals in the current language', () => {
    expect(translate('jobDetail.partsDone', { count: 3 })).toBe('3 terminées');
    expect(translate('documents.summary', { count: 1, passages: 40 })).toMatch(/^1 document lu, 40 passages\./);
    activeLocale.value = 'en';
    expect(translate('documents.summary', { count: 2, passages: 1 })).toMatch(/^2 documents read, 1 passage\./);
    expect(statusLabel('running')).toBe('Running');
    expect(fragmentStateLabel('verified')).toBe('Done');
    activeLocale.value = 'de';
    expect(translate('jobForm.documentsReady', { count: 1 })).toBe('1 Dokument bereit');
    expect(translateList('jobForm.steps')).toHaveLength(3);
  });

  it('falls back to French, then to the key', () => {
    activeLocale.value = 'de';
    expect(translate('does.not.exist')).toBe('does.not.exist');
    expect(normalizeLocale('en-US')).toBe('en');
    expect(normalizeLocale('es')).toBe('fr');
    expect(normalizeLocale(undefined)).toBe('fr');
  });

  it('writes sizes in the units of the language', () => {
    expect(formatBytes(512)).toBe('512 o');
    expect(formatBytes(2.5 * 1024 * 1024)).toBe('2,5 Mo');
    activeLocale.value = 'en';
    expect(formatBytes(2.5 * 1024 * 1024)).toBe('2.5 MB');
  });
});
