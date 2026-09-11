import { Suspense, lazy, type ReactNode } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import ErrorBoundary from '@/components/ErrorBoundary';
import { RequirePortalSession } from '@/components/RequireAuth';
import { t } from '@/i18n';

const BiCanvasPage = lazy(() => import('@/pages/BiCanvasPage'));

function RouteFallback() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center text-slate-500">
      {t('common.loading')}
    </div>
  );
}

/** Page-crash containment; the key resets the boundary on navigation. */
function RoutedErrorBoundary({ children }: { children: ReactNode }) {
  const location = useLocation();
  return <ErrorBoundary key={location.pathname}>{children}</ErrorBoundary>;
}

export default function App() {
  // Uygulama hem /bi/ hem /timas/ altından sunuluyor. Yönlendirici tabanı
  // derleme tabanından okunur; yoksa /timas/ açıldığında hiçbir rota eşleşmez.
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, '')}>
      <Suspense fallback={<RouteFallback />}>
        <RoutedErrorBoundary>
        <Routes>
          {/* Kök doğrudan kanvas: /timas/ ve /bi/ adreslerinde araya ikinci bir
              yol parçası girmiyor. Kanvas ekranları kısa slug taşır. */}

          <Route element={<RequirePortalSession />}>
            {/* Kanvas kendi rayını ve dock'unu taşır; uygulama kabuğu (Layout)
                sarmalanırsa iki menü olur, o yüzden tam ekran açılır. */}
            <Route index element={<BiCanvasPage />} />
            <Route path="panolar" element={<BiCanvasPage />} />
            <Route path="veri-sozlugu" element={<BiCanvasPage />} />
            <Route path="onaylar" element={<BiCanvasPage />} />
            <Route path="planli-raporlar" element={<BiCanvasPage />} />
            <Route path="uyarilar" element={<BiCanvasPage />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </RoutedErrorBoundary>
      </Suspense>
    </BrowserRouter>
  );
}
