import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'sonner';
import { LocaleProvider } from '@/context/LocaleContext';
import { ENGINE_ENABLED, EngineAuthError, isAuthBlocked } from '@/canvas/engine';
import { startAuditTrail } from '@/canvas/auditTrail';
import { DATA_STALE_MS } from '@/canvas/DataRefresh';
import { msUntilNextRefresh } from '@/canvas/refreshSchedule';
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
  // Veri gösteren her ekran: alınan veri 5 dk taze sayılır ve ekrandan ayrılınca 30 dk bellekte kalır,
  // menüler arası geçişte yeniden beklenmez. Açık ekranın verisi her gün 07:00 ve 12:00'de (İstanbul) arka planda
  // yenilenir (kullanıcı kararı 2026-09-29; önce 5 dk'da birdi); sayfa yenilenmez, bileşen yeniden kurulmaz.
  // Kendi aralığını veren sorgu (iş ilerlemesi yoklaması) kendi değerini korur.
  // Üst şeritteki "Verileri yenile" düğmesi (DataRefresh) aynı sorguları istek anında tazeler.
  defaultOptions: {
    queries: {
      staleTime: DATA_STALE_MS,
      gcTime: 30 * 60_000,
      refetchInterval: () => (isAuthBlocked() ? false : msUntilNextRefresh()),
      refetchIntervalInBackground: true,
      retry: 1,
      refetchOnWindowFocus: false,
    },
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

/** Yeni sürüm kurulunca eski sürümün ekran parçaları sunucudan silinir; açık sekme bir ekrana geçerken o parçayı
 *  ister, 404 alır ve ekran «Hata» yazardı (Sayfa düzeni, Kapak). Parça yüklenemeyince sayfa yeni sürümle bir kez
 *  yenilenir; 60 sn içinde ikinci kez olursa yenilenmez (döngü olmaz), hata ekranı görünür. */
window.addEventListener('vite:preloadError', (e) => {
  const KEY = 'timas:chunk-reload';
  let last = 0;
  try { last = Number(sessionStorage.getItem(KEY)) || 0; } catch { /* depolama kapalı */ }
  if (Date.now() - last < 60_000) return;
  try { sessionStorage.setItem(KEY, String(Date.now())); } catch { /* depolama kapalı */ }
  e.preventDefault();
  window.location.reload();
});

// Denetim izi: açılan sayfa, basılan düğme, seçilen seçenek (Yönetim → Denetim kaydı).
if (ENGINE_ENABLED) startAuditTrail();

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
