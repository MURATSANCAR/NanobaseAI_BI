import { Suspense, lazy, type ReactNode } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import ErrorBoundary from '@/components/ErrorBoundary';
import RequireTimasSession from '@/canvas/TimasSession';
import { t } from '@/i18n';

const KampusPage = lazy(() => import('@/canvas/kampus/KampusPage'));
const BiCanvasPage = lazy(() => import('@/pages/BiCanvasPage'));
const BoardScreen = lazy(() => import('@/canvas/board/BoardScreen'));
const ReportsScreen = lazy(() => import('@/canvas/reports/ReportsScreen'));
const AdminScreen = lazy(() => import('@/canvas/admin/AdminScreen'));
const GlossaryScreen = lazy(() => import('@/canvas/dictionary/GlossaryScreen'));
const ApprovalsScreen = lazy(() => import('@/canvas/dictionary/ApprovalsScreen'));
const VocabularyScreen = lazy(() => import('@/canvas/dictionary/VocabularyScreen'));
const EditorialBoardScreen = lazy(() => import('@/canvas/editorial/BoardScreen'));
const RedactionScreen = lazy(() => import('@/canvas/editorial/RedactionScreen'));
const ProofScreen = lazy(() => import('@/canvas/editorial/ProofScreen'));
const EditorsScreen = lazy(() => import('@/canvas/editorial/EditorsScreen'));
const AuthorsScreen = lazy(() => import('@/canvas/editorial/modules').then((m) => ({ default: m.AuthorsScreen })));
const TranslatorsScreen = lazy(() => import('@/canvas/editorial/modules').then((m) => ({ default: m.TranslatorsScreen })));
const FreelancersScreen = lazy(() => import('@/canvas/editorial/modules').then((m) => ({ default: m.FreelancersScreen })));
const ContractsScreen = lazy(() => import('@/canvas/editorial/ContractsScreen'));

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

          <Route element={<RequireTimasSession />}>
            {/* Kanvas kendi rayını ve dock'unu taşır; uygulama kabuğu (Layout)
                sarmalanırsa iki menü olur, o yüzden tam ekran açılır. */}
            {/* Girişten sonra ilk ekran Kampüs; modüllere oradan geçilir. */}
            <Route index element={<KampusPage />} />
            <Route path="genel-bakis" element={<BiCanvasPage />} />
            <Route path="panolar" element={<BoardScreen />} />
            <Route path="veri-sozlugu" element={<GlossaryScreen />} />
            <Route path="onaylar" element={<ApprovalsScreen />} />
            <Route path="es-anlamlilar" element={<VocabularyScreen />} />
            <Route path="planli-raporlar" element={<ReportsScreen />} />
            <Route path="yonetim" element={<AdminScreen />} />
            <Route path="uyarilar" element={<BiCanvasPage />} />
            {/* Editoryal Süreç (M1–M8); ekranı hazır olan modül buraya girer. */}
            <Route path="yayin-kurulu" element={<EditorialBoardScreen />} />
            <Route path="editor-atama" element={<EditorsScreen />} />
            <Route path="cevirmenler" element={<TranslatorsScreen />} />
            <Route path="yazarlar" element={<AuthorsScreen />} />
            <Route path="cizer-freelancer" element={<FreelancersScreen />} />
            <Route path="redaksiyon" element={<RedactionScreen />} />
            <Route path="son-okuma" element={<ProofScreen />} />
            <Route path="telif-sozlesme" element={<ContractsScreen />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </RoutedErrorBoundary>
      </Suspense>
    </BrowserRouter>
  );
}
