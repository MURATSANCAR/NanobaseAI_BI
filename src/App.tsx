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
const MeetingScreen = lazy(() => import('@/canvas/editorial/intake/MeetingScreen'));
const IntakeBoardScreen = lazy(() => import('@/canvas/editorial/intake/IntakeBoardScreen'));
const IntakeProjectScreen = lazy(() => import('@/canvas/editorial/intake/IntakeProjectScreen'));
const BookScreen = lazy(() => import('@/canvas/editorial/BookScreen'));
const EditorialHome = lazy(() => import('@/canvas/editorial/EditorialHome'));
const RedactionScreen = lazy(() => import('@/canvas/editorial/RedactionScreen'));
const ProofScreen = lazy(() => import('@/canvas/editorial/ProofScreen'));
const StudioHome = lazy(() => import('@/canvas/editorial/studio/StudioHome'));
const StudioFlow = lazy(() => import('@/canvas/editorial/studio/StudioFlow'));
const StudioEditor = lazy(() => import('@/canvas/editorial/studio/StudioEditor'));
const EditorsScreen = lazy(() => import('@/canvas/editorial/EditorsScreen'));
const PeopleScreen = lazy(() => import('@/canvas/editorial/modules'));
const WebScreen = lazy(() => import('@/canvas/editorial/web/WebScreen'));
const ContractsScreen = lazy(() => import('@/canvas/editorial/ContractsScreen'));
const FinancialAudit = lazy(() => import('@/canvas/financial-audit/FinancialAudit'));
const ManagementHome = lazy(() => import('@/canvas/management/ManagementHome'));
const BaskiOneri = lazy(() => import('@/canvas/management/BaskiOneri'));
const SeoHome = lazy(() => import('@/canvas/seo-geo/SeoHome'));
const SeoAudit = lazy(() => import('@/canvas/seo-geo/SeoAudit'));
const SeoSearch = lazy(() => import('@/canvas/seo-geo/SeoSearch'));
const SeoVisibility = lazy(() => import('@/canvas/seo-geo/SeoVisibility'));
const SeoHistory = lazy(() => import('@/canvas/seo-geo/SeoHistory'));
const SeoConnections = lazy(() => import('@/canvas/seo-geo/SeoConnections'));
const SeoLlms = lazy(() => import('@/canvas/seo-geo/SeoLlms'));
const SeoRedirects = lazy(() => import('@/canvas/seo-geo/SeoRedirects'));
const SeoPages = lazy(() => import('@/canvas/seo-geo/SeoPages'));
const SeoSchema = lazy(() => import('@/canvas/seo-geo/SeoSchema'));

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
            <Route path="finansal-denetim" element={<FinancialAudit />} />
            {/* Yönetim Raporları: diğer modüllerden ayrı, kendi rayı ve uçlarıyla (/api/v1/management). */}
            <Route path="yonetim-raporlari" element={<ManagementHome />} />
            <Route path="yonetim-raporlari/baski-oneri" element={<BaskiOneri />} />
            {/* SEO & GEO: kendi rayı ve uçlarıyla (/api/v1/seo-geo); T-soft ürün denetimi, Search Console, AI görünürlük. */}
            <Route path="seo-geo" element={<SeoHome />} />
            <Route path="seo-geo/urun-denetimi" element={<SeoAudit />} />
            <Route path="seo-geo/anahtar-kelimeler" element={<SeoSearch />} />
            <Route path="seo-geo/ai-gorunurluk" element={<SeoVisibility />} />
            <Route path="seo-geo/gecmis" element={<SeoHistory />} />
            <Route path="seo-geo/baglantilar" element={<SeoConnections />} />
            <Route path="seo-geo/llms" element={<SeoLlms />} />
            <Route path="seo-geo/yonlendirmeler" element={<SeoRedirects />} />
            <Route path="seo-geo/sayfalar" element={<SeoPages />} />
            <Route path="seo-geo/sema" element={<SeoSchema />} />
            <Route path="panolar" element={<BoardScreen />} />
            <Route path="veri-sozlugu" element={<GlossaryScreen />} />
            <Route path="onaylar" element={<ApprovalsScreen />} />
            <Route path="es-anlamlilar" element={<VocabularyScreen />} />
            <Route path="planli-raporlar" element={<ReportsScreen />} />
            <Route path="yonetim" element={<AdminScreen />} />
            <Route path="uyarilar" element={<BiCanvasPage />} />
            {/* Editoryal Süreç: Günlük (Masam, Yazar giriş süreci, Yayın kurulu) · Yayına hazırlık · Kayıtlar. */}
            <Route path="yazar-giris" element={<IntakeBoardScreen />} />
            <Route path="yazar-giris/:id" element={<IntakeProjectScreen />} />
            <Route path="yayin-kurulu" element={<MeetingScreen />} />
            <Route path="editor-atama" element={<EditorsScreen />} />
            <Route path="kisiler" element={<PeopleScreen />} />
            <Route path="basin-web" element={<WebScreen />} />
            {/* Eski adresler Kişiler ekranına ilgili seçimle gider; kaydedilmiş bağlantı kırılmaz. */}
            <Route path="yazarlar" element={<Navigate to="/kisiler?rol=yazar" replace />} />
            <Route path="cevirmenler" element={<Navigate to="/kisiler?rol=cevirmen" replace />} />
            <Route path="cizer-freelancer" element={<Navigate to="/kisiler?rol=cizer" replace />} />
            <Route path="kitap/:id" element={<BookScreen />} />
            <Route path="editoryal" element={<EditorialHome />} />
            <Route path="redaksiyon" element={<RedactionScreen />} />
            <Route path="son-okuma" element={<ProofScreen />} />
            <Route path="kitap-tasarim" element={<StudioHome />} />
            <Route path="kitap-tasarim/:jobId" element={<StudioFlow />} />
            <Route path="kitap-tasarim/:jobId/studyo" element={<StudioEditor />} />
            <Route path="telif-sozlesme" element={<ContractsScreen />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </RoutedErrorBoundary>
      </Suspense>
    </BrowserRouter>
  );
}
