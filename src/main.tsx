import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'sonner';
import { LocaleProvider } from '@/context/LocaleContext';
import { EngineAuthError } from '@/canvas/engine';
import App from './App';
import './index.css';
import '@/canvas/canvas.css';

const SESSION_KEY = ['timas-session'];

/** Oturum sayfa açıkken düşerse (çerez süresi doldu) oturum sorgusu 5 dk taze sayıldığı için giriş
 *  formu açılmıyor, her ekran kendi yoklamasında 401 almaya devam ediyordu. Herhangi bir sorgu 401
 *  aldığında oturum yeniden sorulur; o da 401 derse kapı giriş formunu açar. Oturum zaten hatadaysa
 *  tekrar sorulmaz, döngü olmaz. */
const queryClient: QueryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error, query) => {
      if (!(error instanceof EngineAuthError)) return;
      if (query.queryKey[0] === SESSION_KEY[0]) return;
      if (queryClient.getQueryState(SESSION_KEY)?.status === 'error') return;
      void queryClient.invalidateQueries({ queryKey: SESSION_KEY });
    },
  }),
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false },
  },
});

/** A browser extension's message port closing produces an unhandled rejection on this page even
 *  though nothing here uses the extension APIs. It is not ours to fix and not ours to show: a
 *  recurring line nobody can act on is how a console stops being read. Only this exact message is
 *  swallowed; everything else still surfaces. */
window.addEventListener('unhandledrejection', (e) => {
  if (String((e.reason as Error)?.message ?? e.reason ?? '').includes('message channel closed before a response was received')) {
    e.preventDefault();
  }
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <LocaleProvider>
        <App />
        <Toaster position="top-right" richColors closeButton />
      </LocaleProvider>
    </QueryClientProvider>
  </StrictMode>,
);
