import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import './styles.css';

/** A browser extension's message port closing produces an unhandled rejection on this page even
 *  though nothing here uses the extension APIs. It is not ours to fix and not ours to show: the
 *  console is where a real fault has to be visible, and a recurring line nobody can act on is how a
 *  console stops being read. Only this exact message is swallowed; everything else still surfaces. */
const EXTENSION_NOISE = 'message channel closed before a response was received';

window.addEventListener('unhandledrejection', (e) => {
  if (String((e.reason as Error)?.message ?? e.reason ?? '').includes(EXTENSION_NOISE)) e.preventDefault();
});

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 5 * 60_000 } },
});

(window as any).__qc = queryClient;

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
