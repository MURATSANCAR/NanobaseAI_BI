import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  getLocale,
  normalizeActiveLocale,
  setLocale,
  subscribeLocale,
  type ActiveLocale,
} from '@/i18n';

type LocaleContextValue = {
  locale: ActiveLocale;
  setAppLocale: (locale: ActiveLocale | string) => void;
};

const LocaleContext = createContext<LocaleContextValue | null>(null);

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<ActiveLocale>(getLocale());

  useEffect(() => subscribeLocale(setLocaleState), []);

  const value = useMemo(
    () => ({
      locale,
      setAppLocale: (next: ActiveLocale | string) => {
        const active = normalizeActiveLocale(next);
        setLocale(active);
        setLocaleState(active);
      },
    }),
    [locale],
  );

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale() {
  const ctx = useContext(LocaleContext);
  if (!ctx) throw new Error('useLocale outside provider');
  return ctx;
}

/** Re-render children when locale changes */
export function useLocaleText() {
  const { locale } = useLocale();
  return locale;
}
