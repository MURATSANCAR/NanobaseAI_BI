import en from './en.json';
import tr from './tr.json';
import ru from './ru.json';
import uz from './uz.json';
import helpEn from './help-en.json';
import helpTr from './help-tr.json';
import helpRu from './help-ru.json';
import helpUz from './help-uz.json';

/** All known locale codes (legacy ru/uz kept for stored prefs / old docs). */
export type Locale = 'en' | 'tr' | 'ru' | 'uz';
export type PortalLocale = Locale;
/** Locales offered in the UI and used for new generation. */
export type ActiveLocale = 'en' | 'tr';

const bundles: Record<Locale, Record<string, string>> = {
  en: { ...en, ...helpEn },
  tr: { ...tr, ...helpTr },
  ru: { ...ru, ...helpRu },
  uz: { ...uz, ...helpUz },
};

const listeners = new Set<(locale: ActiveLocale) => void>();

/** UI / new content — Russian and Uzbek temporarily disabled. */
export const SUPPORTED_LOCALES: ActiveLocale[] = ['tr', 'en'];

export const LOCALE_LABELS: Record<Locale, string> = {
  tr: '🇹🇷 TR',
  en: '🇬🇧 EN',
  ru: '🇷🇺 RU',
  uz: '🇺🇿 UZ',
};

/** Map ru/uz (and unknown) → active locale. */
export function normalizeActiveLocale(locale: string | null | undefined): ActiveLocale {
  const code = String(locale || '').trim().toLowerCase().slice(0, 2);
  if (code === 'tr' || code === 'en') return code;
  return 'en';
}

function readStoredLocale(): ActiveLocale | null {
  try {
    if (typeof localStorage === 'undefined') return null;
    const raw = localStorage.getItem('nanobase_qa_locale');
    if (!raw) return null;
    return normalizeActiveLocale(raw);
  } catch {
    return null;
  }
}

let current: ActiveLocale = readStoredLocale() || 'tr';

export function setLocale(locale: Locale | string): void {
  const next = normalizeActiveLocale(locale);
  current = next;
  try {
    localStorage?.setItem('nanobase_qa_locale', next);
  } catch {
    /* ignore — tests / private mode */
  }
  listeners.forEach((listener) => listener(next));
}

export function getLocale(): ActiveLocale {
  return current;
}

export function subscribeLocale(listener: (locale: ActiveLocale) => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function t(key: string, vars?: Record<string, string | number>): string {
  return tLocale(current, key, vars);
}

/** Translate a key in an explicit locale (e.g. public share). Inactive → English bundle. */
export function tLocale(locale: Locale | string, key: string, vars?: Record<string, string | number>): string {
  const requested = String(locale || '').trim().toLowerCase().slice(0, 2) as Locale;
  const loc: ActiveLocale =
    requested === 'tr' || requested === 'en' ? requested : normalizeActiveLocale(requested);
  let text = bundles[loc][key] ?? bundles.en[key] ?? key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      text = text.replace(`{${k}}`, String(v));
    }
  }
  return text;
}

/** Multi-line i18n value → array of non-empty lines */
export function tLines(key: string): string[] {
  const text = t(key);
  if (!text || text === key) return [];
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
}
