import { Suspense, lazy, type ReactNode } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import ErrorBoundary from '@/components/ErrorBoundary';
import RequireTimasSession from '@/canvas/TimasSession';
import PageGate from '@/canvas/PageGate';
import { t } from '@/i18n';

const KampusPage = lazy(() => import('@/canvas/kampus/KampusPage'));
const BiCanvasPage = lazy(() => import('@/pages/BiCanvasPage'));
const BoardScreen = lazy(() => import('@/canvas/board/BoardScreen'));
const ReportsScreen = lazy(() => import('@/canvas/reports/ReportsScreen'));
const AdminScreen = lazy(() => import('@/canvas/admin/AdminScreen'));
const GlossaryScreen = lazy(() => import('@/canvas/dictionary/GlossaryScreen'));
const ApprovalsScreen = lazy(() => import('@/canvas/dictionary/ApprovalsScreen'));
const VocabularyScreen = lazy(() => import('@/canvas/dictionary/VocabularyScreen'));
const BoardSessionsScreen = lazy(() => import('@/canvas/editorial/applications/BoardSessionsScreen'));
const SessionScreen = lazy(() => import('@/canvas/editorial/applications/SessionScreen'));
const ApplicationsScreen = lazy(() => import('@/canvas/editorial/applications/ApplicationsScreen'));
const ApplicationScreen = lazy(() => import('@/canvas/editorial/applications/ApplicationScreen'));
const IntakeBoardScreen = lazy(() => import('@/canvas/editorial/intake/IntakeBoardScreen'));
const IntakeProjectScreen = lazy(() => import('@/canvas/editorial/intake/IntakeProjectScreen'));
const BookScreen = lazy(() => import('@/canvas/editorial/BookScreen'));
const EditorialHome = lazy(() => import('@/canvas/editorial/EditorialHome'));
const RedactionScreen = lazy(() => import('@/canvas/editorial/RedactionScreen'));
const ProofScreen = lazy(() => import('@/canvas/editorial/ProofScreen'));
const TranslationScreen = lazy(() => import('@/canvas/editorial/translation/TranslationScreen'));
const TranslationWorkbench = lazy(() => import('@/canvas/editorial/translation/Workbench'));
const TranslationQuality = lazy(() => import('@/canvas/editorial/translation/QualityReport'));
const StudioHome = lazy(() => import('@/canvas/editorial/studio/StudioHome'));
const StudioFlow = lazy(() => import('@/canvas/editorial/studio/StudioFlow'));
const StudioEditor = lazy(() => import('@/canvas/editorial/studio/StudioEditor'));
const PlanEditor = lazy(() => import('@/canvas/editorial/studio/PlanEditor'));
const CoverScreen = lazy(() => import('@/canvas/editorial/studio/collage/CoverScreen'));
const CoverLibraryScreen = lazy(() => import('@/canvas/editorial/studio/library/CoverLibraryScreen'));
const EditorsScreen = lazy(() => import('@/canvas/editorial/EditorsScreen'));
const MyTasksScreen = lazy(() => import('@/canvas/editorial/MyTasksScreen'));
const PeopleScreen = lazy(() => import('@/canvas/editorial/modules'));
const FreelanceScreen = lazy(() => import('@/canvas/editorial/freelance/FreelanceScreen'));
const PricingScreen = lazy(() => import('@/canvas/pricing/PricingScreen'));
const AuthorRelationsScreen = lazy(() => import('@/canvas/editorial/authors/AuthorRelationsScreen'));
const ProductionScreen = lazy(() => import('@/canvas/editorial/production/ProductionScreen'));
const CorporateScreen = lazy(() => import('@/canvas/corporate/CorporateScreen'));
const CorporateOpportunity = lazy(() => import('@/canvas/corporate/OpportunityPage'));
const MailboxHome = lazy(() => import('@/canvas/mailbox/MailboxHome'));
const MailMessage = lazy(() => import('@/canvas/mailbox/MessageDetail'));
const MailReport = lazy(() => import('@/canvas/mailbox/MailReport'));
const MailRules = lazy(() => import('@/canvas/mailbox/MailRules'));
const MailLabeling = lazy(() => import('@/canvas/mailbox/Labeling'));
const WebScreen = lazy(() => import('@/canvas/editorial/web/WebScreen'));
const ContractsScreen = lazy(() => import('@/canvas/editorial/ContractsScreen'));
const ContractDetail = lazy(() => import('@/canvas/editorial/contracts/ContractDetail'));
const NewContract = lazy(() => import('@/canvas/editorial/contracts/NewContract'));
const ContractPayments = lazy(() => import('@/canvas/editorial/contracts/PaymentsScreen'));
const ContractTemplates = lazy(() => import('@/canvas/editorial/contracts/TemplatesScreen'));
const FinancialAudit = lazy(() => import('@/canvas/financial-audit/FinancialAudit'));
const ManagementHome = lazy(() => import('@/canvas/management/ManagementHome'));
const BaskiOneri = lazy(() => import('@/canvas/management/BaskiOneri'));
const BudgetScreen = lazy(() => import('@/canvas/budget/BudgetScreen'));
const SystemStatusScreen = lazy(() => import('@/canvas/it-ops/SystemStatusScreen'));
const DistributionScreen = lazy(() => import('@/canvas/distribution/DistributionScreen'));
const DistributionPlan = lazy(() => import('@/canvas/distribution/PlanEditor'));
const TenderList = lazy(() => import('@/canvas/tenders/TenderList'));
const TenderDetail = lazy(() => import('@/canvas/tenders/TenderDetail'));
const CategoriesScreen = lazy(() => import('@/canvas/categories/CategoriesScreen'));
const CategoryBookProfile = lazy(() => import('@/canvas/categories/BookProfile'));
const FirstPrintScreen = lazy(() => import('@/canvas/first-print/FirstPrintScreen'));
const FieldScreen = lazy(() => import('@/canvas/field/FieldScreen'));
const CustomerBrief = lazy(() => import('@/canvas/field/CustomerBrief'));
const BookForecastPage = lazy(() => import('@/canvas/first-print/BookForecast'));
const FreeForecastPage = lazy(() => import('@/canvas/first-print/FreeForecast'));
const SchoolsScreen = lazy(() => import('@/canvas/schools/SchoolsScreen'));
const SchoolCard = lazy(() => import('@/canvas/schools/SchoolCard'));
const MarketingHome = lazy(() => import('@/canvas/marketing/MarketingHome'));
const MarketingPlan = lazy(() => import('@/canvas/marketing/PlanScreen'));
const SetsScreen = lazy(() => import('@/canvas/marketing/sets/SetsScreen'));
const SetEditor = lazy(() => import('@/canvas/marketing/sets/SetEditor'));
const GiftOfferEditor = lazy(() => import('@/canvas/marketing/sets/GiftOfferEditor'));
const CreativeHome = lazy(() => import('@/canvas/marketing/creative/CreativeHome'));
const CreativeRequest = lazy(() => import('@/canvas/marketing/creative/RequestScreen'));
const MarketingMonth = lazy(() => import('@/canvas/marketing/monthly/MonthScreen'));
const MarketingFoyList = lazy(() => import('@/canvas/marketing/monthly/FoyList'));
const MarketingFoy = lazy(() => import('@/canvas/marketing/monthly/FoyScreen'));
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
const SeoRights = lazy(() => import('@/canvas/seo-geo/SeoRights'));
const SeoOpportunities = lazy(() => import('@/canvas/seo-geo/SeoOpportunities'));
const SeoBing = lazy(() => import('@/canvas/seo-geo/SeoBing'));
const SeoTech = lazy(() => import('@/canvas/seo-geo/SeoTech'));
const SeoCompetitors = lazy(() => import('@/canvas/seo-geo/SeoCompetitors'));
const SeoEntity = lazy(() => import('@/canvas/seo-geo/SeoEntity'));
const SeoGuides = lazy(() => import('@/canvas/seo-geo/SeoGuides'));
const SeoWorklist = lazy(() => import('@/canvas/seo-geo/SeoWorklist'));
const SeoScorecard = lazy(() => import('@/canvas/seo-geo/SeoScorecard'));
const SeoBios = lazy(() => import('@/canvas/seo-geo/SeoBios'));
const SeoFaq = lazy(() => import('@/canvas/seo-geo/SeoFaq'));
const SeoSimilar = lazy(() => import('@/canvas/seo-geo/SeoSimilar'));
const SeoKeymap = lazy(() => import('@/canvas/seo-geo/SeoKeymap'));
const SeoQuestionSuggest = lazy(() => import('@/canvas/seo-geo/SeoQuestionSuggest'));
const SeoYoutube = lazy(() => import('@/canvas/seo-geo/SeoYoutube'));
const SeoShopping = lazy(() => import('@/canvas/seo-geo/SeoShopping'));
const SeoMonthly = lazy(() => import('@/canvas/seo-geo/SeoMonthly'));
const SeoWatch = lazy(() => import('@/canvas/seo-geo/SeoWatch'));
const SeoSources = lazy(() => import('@/canvas/seo-geo/SeoSources'));
const SeoCannibal = lazy(() => import('@/canvas/seo-geo/SeoCannibal'));
const SeoCrawlbot = lazy(() => import('@/canvas/seo-geo/SeoCrawlbot'));
const SeoBacklinks = lazy(() => import('@/canvas/seo-geo/SeoBacklinks'));
const SeoSeasons = lazy(() => import('@/canvas/seo-geo/SeoSeasons'));
const SeoLinks = lazy(() => import('@/canvas/seo-geo/SeoLinks'));
const SeoReviews = lazy(() => import('@/canvas/seo-geo/SeoReviews'));
const SeoVideo = lazy(() => import('@/canvas/seo-geo/SeoVideo'));
const SeoSunset = lazy(() => import('@/canvas/seo-geo/SeoSunset'));
const SeoAuthors = lazy(() => import('@/canvas/seo-geo/SeoAuthors'));

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
          {/* Rota kapısı: menüdeki karşılığı kişinin rolünde olmayan sayfa yüklenmez (canvas/PageGate). */}
          <Route element={<PageGate />}>
            {/* Kanvas kendi rayını ve dock'unu taşır; uygulama kabuğu (Layout)
                sarmalanırsa iki menü olur, o yüzden tam ekran açılır. */}
            {/* Girişten sonra ilk ekran Kampüs; modüllere oradan geçilir. */}
            <Route index element={<KampusPage />} />
            <Route path="genel-bakis" element={<BiCanvasPage />} />
            <Route path="finansal-denetim" element={<FinancialAudit />} />
            {/* Yönetim Raporları: diğer modüllerden ayrı, kendi rayı ve uçlarıyla (/api/v1/management). */}
            <Route path="yonetim-raporlari" element={<ManagementHome />} />
            <Route path="yonetim-raporlari/baski-oneri" element={<BaskiOneri />} />
            {/* M46 Bütçe planlama ve kontrolü (/api/v1/budget). */}
            <Route path="butce" element={<BudgetScreen />} />
            {/* M33 İhale takibi (Satış ve saha): ilanlar, takvim, belge arşivi, sonuçlar, kamu satışları (/api/v1/tenders). */}
            <Route path="ihale" element={<TenderList />} />
            <Route path="ihale/:id" element={<TenderDetail />} />
            {/* M48 IT altyapı ve sistem durumu: halkalar, olaylar, zamanlanmış işler, sürümler, kapasite (/api/v1/it-ops). */}
            <Route path="sistem-durumu" element={<SystemStatusScreen />} />
            {/* M10 İlk baskı ve satış tahmini: emsal kitaplardan senaryolar, ilk satış takibi, geçmiş sınama (/api/v1/management/first-print). */}
            <Route path="ilk-baski" element={<FirstPrintScreen />} />
            <Route path="ilk-baski/kitap/:code" element={<BookForecastPage />} />
            <Route path="ilk-baski/yeni" element={<FreeForecastPage />} />
            {/* M29 İlk dağılım (Satış ve saha): dağılım bekleyenler, plan, takip, Bölgem (/api/v1/distribution). */}
            <Route path="ilk-dagilim" element={<DistributionScreen />} />
            <Route path="ilk-dagilim/:stok" element={<DistributionPlan />} />
            {/* M30 Saha satış ve tahsilat (BMT): telefon önce; müşteri brifingi cari koduyla (/api/v1/field). */}
            <Route path="saha" element={<FieldScreen />} />
            <Route path="saha/musteri/:code" element={<CustomerBrief />} />
            {/* M31 Okul tanıtım ve ziyaret (/api/v1/schools): telefon öncelikli «Bu hafta», okul kartı, bayi kuyruğu, dönem raporu. */}
            <Route path="okul-tanitim" element={<SchoolsScreen />} />
            <Route path="okul-tanitim/:id" element={<SchoolCard />} />
            {/* Fiyatlama ve maliyet (M9): kitap maliyeti, başabaş, kapak fiyatı, onay; uçlar /api/v1/pricing. */}
            <Route path="fiyatlama" element={<PricingScreen />} />
            {/* Pazarlama › Planlama: M15 yeni kitap pazarlama planı (/api/v1/marketing). */}
            <Route path="pazarlama/yeni-kitap" element={<MarketingHome />} />
            <Route path="pazarlama/plan/:id" element={<MarketingPlan />} />
            {/* M18 aylık pazarlama planı ve satış föyleri (/api/v1/marketing/months, /foy). */}
            <Route path="pazarlama/aylik-plan" element={<MarketingMonth />} />
            <Route path="pazarlama/aylik-plan/:ay" element={<MarketingMonth />} />
            <Route path="pazarlama/foy" element={<MarketingFoyList />} />
            <Route path="pazarlama/foy/:stok" element={<MarketingFoy />} />
            {/* SEO & GEO: kendi rayı ve uçlarıyla (/api/v1/seo-geo); T-soft ürün denetimi, Search Console, AI görünürlük. */}
            {/* M53 Set, hediye ve promosyon (/api/v1/marketing/sets, /gift-offers, /promo-items). */}
            <Route path="pazarlama/set-hediye" element={<SetsScreen />} />
            <Route path="pazarlama/set-hediye/set/:id" element={<SetEditor />} />
            <Route path="pazarlama/set-hediye/teklif/:id" element={<GiftOfferEditor />} />
            <Route path="pazarlama/icerik" element={<CreativeHome />} />
            <Route path="pazarlama/icerik/:id" element={<CreativeRequest />} />
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
            <Route path="seo-geo/crm-haklar" element={<SeoRights />} />
            <Route path="seo-geo/firsatlar" element={<SeoOpportunities />} />
            <Route path="seo-geo/bing" element={<SeoBing />} />
            <Route path="seo-geo/teknik" element={<SeoTech />} />
            <Route path="seo-geo/rakipler" element={<SeoCompetitors />} />
            <Route path="seo-geo/kimlik" element={<SeoEntity />} />
            <Route path="seo-geo/rehberler" element={<SeoGuides />} />
            <Route path="seo-geo/is-listesi" element={<SeoWorklist />} />
            <Route path="seo-geo/kitap" element={<SeoScorecard />} />
            <Route path="seo-geo/yazar-biyografi" element={<SeoBios />} />
            <Route path="seo-geo/sss" element={<SeoFaq />} />
            <Route path="seo-geo/benzer-kitaplar" element={<SeoSimilar />} />
            <Route path="seo-geo/sorgu-sayfa" element={<SeoKeymap />} />
            <Route path="seo-geo/soru-onerileri" element={<SeoQuestionSuggest />} />
            <Route path="seo-geo/youtube" element={<SeoYoutube />} />
            <Route path="seo-geo/alisveris" element={<SeoShopping />} />
            <Route path="seo-geo/aylik-rapor" element={<SeoMonthly />} />
            <Route path="seo-geo/izleme" element={<SeoWatch />} />
            <Route path="seo-geo/kaynaklar" element={<SeoSources />} />
            <Route path="seo-geo/yarisan" element={<SeoCannibal />} />
            <Route path="seo-geo/google-taramasi" element={<SeoCrawlbot />} />
            <Route path="seo-geo/geri-baglantilar" element={<SeoBacklinks />} />
            <Route path="seo-geo/takvim" element={<SeoSeasons />} />
            <Route path="seo-geo/ic-baglantilar" element={<SeoLinks />} />
            <Route path="seo-geo/yorumlar" element={<SeoReviews />} />
            <Route path="seo-geo/video" element={<SeoVideo />} />
            <Route path="seo-geo/satistan-kalkan" element={<SeoSunset />} />
            <Route path="seo-geo/yazar-sayfalari" element={<SeoAuthors />} />
            <Route path="panolar" element={<BoardScreen />} />
            <Route path="veri-sozlugu" element={<GlossaryScreen />} />
            <Route path="onaylar" element={<ApprovalsScreen />} />
            <Route path="es-anlamlilar" element={<VocabularyScreen />} />
            <Route path="planli-raporlar" element={<ReportsScreen />} />
            <Route path="yonetim" element={<AdminScreen />} />
            <Route path="uyarilar" element={<BiCanvasPage />} />
            {/* Editoryal Süreç: Günlük (Masam, Başvurular, Yazar giriş süreci, Yayın kurulu) · Yayına hazırlık · Kayıtlar. */}
            <Route path="yazar-giris" element={<IntakeBoardScreen />} />
            <Route path="yazar-giris/:id" element={<IntakeProjectScreen />} />
            {/* M1: başvuru kuyruğu ve dosyası; yayın kurulu oturumları (CRM geçmişi ?gorunum=crm). */}
            <Route path="basvurular" element={<ApplicationsScreen />} />
            <Route path="basvurular/:id" element={<ApplicationScreen />} />
            <Route path="yayin-kurulu" element={<BoardSessionsScreen />} />
            <Route path="yayin-kurulu/oturum/:id" element={<SessionScreen />} />
            <Route path="editor-atama" element={<EditorsScreen />} />
            {/* H1 Kategori ağacı: tek onaylı ağaç, kitap profili (öneri → onay), tutarsızlıklar, CRM'e işlenecek fark (/api/v1/categories). */}
            <Route path="kategori-agaci" element={<CategoriesScreen />} />
            <Route path="kategori-agaci/kitap/:id" element={<CategoryBookProfile />} />
            <Route path="kategori-agaci/:section" element={<CategoriesScreen />} />
            <Route path="gorevlerim" element={<MyTasksScreen />} />
            <Route path="kisiler" element={<PeopleScreen />} />
            <Route path="serbest-calisanlar" element={<FreelanceScreen />} />
            <Route path="uretim" element={<ProductionScreen />} />
            {/* M32 Kurumsal satış ve B2B (/api/v1/corporate): fırsat, paket, teklif, hatırlatma, bayi paneli. */}
            <Route path="kurumsal-satis" element={<CorporateScreen />} />
            <Route path="kurumsal-satis/firsat/:id" element={<CorporateOpportunity />} />
            {/* H4 Kurumsal e-posta (/api/v1/mailbox): timas@ genel kutusu, atama, SLA, yanıt taslağı, rapor, kurallar. */}
            <Route path="kurumsal-eposta" element={<MailboxHome />} />
            <Route path="kurumsal-eposta/ileti/:id" element={<MailMessage />} />
            <Route path="kurumsal-eposta/rapor" element={<MailReport />} />
            <Route path="kurumsal-eposta/kurallar" element={<MailRules />} />
            <Route path="kurumsal-eposta/etiketleme" element={<MailLabeling />} />
            <Route path="yazar-iliskileri" element={<AuthorRelationsScreen />} />
            <Route path="basin-web" element={<WebScreen />} />
            {/* Eski adresler Kişiler ekranına ilgili seçimle gider; kaydedilmiş bağlantı kırılmaz. */}
            <Route path="yazarlar" element={<Navigate to="/kisiler?rol=yazar" replace />} />
            <Route path="cevirmenler" element={<Navigate to="/kisiler?rol=cevirmen" replace />} />
            <Route path="cizer-freelancer" element={<Navigate to="/kisiler?rol=cizer" replace />} />
            <Route path="kitap/:id" element={<BookScreen />} />
            <Route path="editoryal" element={<EditorialHome />} />
            <Route path="redaksiyon" element={<RedactionScreen />} />
            <Route path="son-okuma" element={<ProofScreen />} />
            <Route path="ceviri" element={<TranslationScreen />} />
            <Route path="ceviri/masam" element={<TranslationWorkbench />} />
            <Route path="ceviri/masam/:jobId" element={<TranslationWorkbench />} />
            <Route path="ceviri/:jobId/kalite" element={<TranslationQuality />} />
            <Route path="kitap-tasarim" element={<StudioHome />} />
            <Route path="kitap-tasarim/kapak-arsivi" element={<CoverLibraryScreen />} />
            <Route path="kitap-tasarim/:jobId" element={<StudioFlow />} />
            <Route path="kitap-tasarim/:jobId/studyo" element={<StudioEditor />} />
            <Route path="kitap-tasarim/:jobId/sayfalar" element={<PlanEditor />} />
            <Route path="kitap-tasarim/:jobId/kapak" element={<CoverScreen />} />
            <Route path="telif-sozlesme" element={<ContractsScreen />} />
            <Route path="telif-sozlesme/yeni" element={<NewContract />} />
            <Route path="telif-sozlesme/odemeler" element={<ContractPayments />} />
            <Route path="telif-sozlesme/sablonlar" element={<ContractTemplates />} />
            <Route path="telif-sozlesme/:key" element={<ContractDetail />} />
          </Route>
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </RoutedErrorBoundary>
      </Suspense>
    </BrowserRouter>
  );
}
