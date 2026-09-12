import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LocaleProvider } from '@/context/LocaleContext';
import App from './App';
import './index.css';
import '@/canvas/canvas.css';

const queryClient = new QueryClient({
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
      </LocaleProvider>
    </QueryClientProvider>
  </StrictMode>,
);
