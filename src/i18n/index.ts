/** All known locale codes (legacy ru/uz kept for stored prefs / old docs). */
export type Locale = 'en' | 'tr' | 'ru' | 'uz';
export type PortalLocale = Locale;
/** Locales offered in the UI and used for new generation. */
export type ActiveLocale = 'en' | 'tr';

/**
 * Locale dictionaries are loaded on demand (dynamic import) so the entry
 * bundle no longer ships every translation. Only tr/en are ever loaded;
 * ru/uz stay on disk but out of the import graph.
 */
const bundles: Partial<Record<ActiveLocale, Record<string, string>>> = {};
const bundleLoads: Partial<Record<ActiveLocale, Promise<void>>> = {};

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

async function importBundle(locale: ActiveLocale): Promise<Record<string, string>> {
  if (locale === 'tr') {
    const [main, help] = await Promise.all([import('./tr.json'), import('./help-tr.json')]);
    return { ...(main.default as Record<string, string>), ...(help.default as Record<string, string>) };
  }
  const [main, help] = await Promise.all([import('./en.json'), import('./help-en.json')]);
  return { ...(main.default as Record<string, string>), ...(help.default as Record<string, string>) };
}

/**
 * Ensure the dictionary for `locale` is loaded (idempotent). Also kicks off a
 * non-blocking load of the English bundle, which acts as the fallback for
 * keys missing from the active locale.
 */
export function loadLocale(locale: Locale | string): Promise<ActiveLocale> {
  const next = normalizeActiveLocale(locale);
  let pending = bundleLoads[next];
  if (!pending) {
    pending = importBundle(next).then((dict) => {
      bundles[next] = dict;
    });
    bundleLoads[next] = pending;
    pending.catch(() => {
      // Allow a retry on transient chunk-load failures.
      if (!bundles[next]) delete bundleLoads[next];
    });
  }
  // Warm the English fallback dictionary in the background.
  if (next !== 'en' && !bundleLoads.en) {
    const enLoad = importBundle('en').then((dict) => {
      bundles.en = dict;
    });
    bundleLoads.en = enLoad;
    enLoad.catch(() => {
      if (!bundles.en) delete bundleLoads.en;
    });
  }
  return pending.then(() => next);
}

export function isLocaleLoaded(locale: ActiveLocale): boolean {
  return Boolean(bundles[locale]);
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
  // Keep the dictionary in sync for callers that set locale directly
  // (e.g. AuthContext applying the profile locale).
  void loadLocale(next);
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
  let text = bundles[loc]?.[key] ?? bundles.en?.[key] ?? key;
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
