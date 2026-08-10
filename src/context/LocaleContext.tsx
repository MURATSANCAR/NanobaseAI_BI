import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  getLocale,
  isLocaleLoaded,
  loadLocale,
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
  const [ready, setReady] = useState<boolean>(() => isLocaleLoaded(getLocale()));

  // Initial dictionary load — children stay unrendered until the active
  // locale bundle is available so t() never returns raw keys.
  useEffect(() => {
    let cancelled = false;
    void loadLocale(getLocale()).then((loaded) => {
      if (cancelled) return;
      setLocaleState(loaded);
      setReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // External setLocale() calls (e.g. AuthContext applying the profile
  // locale): load the dictionary first, then flip the rendered locale.
  useEffect(
    () =>
      subscribeLocale((next) => {
        void loadLocale(next).then((loaded) => {
          setLocaleState(loaded);
          setReady(true);
        });
      }),
    [],
  );

  const value = useMemo(
    () => ({
      locale,
      setAppLocale: (next: ActiveLocale | string) => {
        const active = normalizeActiveLocale(next);
        void loadLocale(active).then((loaded) => {
          setLocale(loaded);
          setLocaleState(loaded);
        });
      },
    }),
    [locale],
  );

  if (!ready) return null;

  return (
    <LocaleContext.Provider value={value}>
      {/* key remount re-evaluates every t() call site on locale switch */}
      <LocaleSubtree key={locale}>{children}</LocaleSubtree>
    </LocaleContext.Provider>
  );
}

function LocaleSubtree({ children }: { children: ReactNode }) {
  return <>{children}</>;
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
