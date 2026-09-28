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
const SupportScreen = lazy(() => import('@/canvas/support/SupportScreen'));
const CorporateOpportunity = lazy(() => import('@/canvas/corporate/OpportunityPage'));
const MailboxHome = lazy(() => import('@/canvas/mailbox/MailboxHome'));
const MailMessage = lazy(() => import('@/canvas/mailbox/MessageDetail'));
const MailReport = lazy(() => import('@/canvas/mailbox/MailReport'));
const MailRules = lazy(() => import('@/canvas/mailbox/MailRules'));
const MailLabeling = lazy(() => import('@/canvas/mailbox/Labeling'));
const PaHome = lazy(() => import('@/canvas/public-affairs/PaHome'));
const PaPeople = lazy(() => import('@/canvas/public-affairs/PaPeople'));
const PaPersonCard = lazy(() => import('@/canvas/public-affairs/PaPersonCard'));
const PaOrgs = lazy(() => import('@/canvas/public-affairs/PaOrgs'));
const PaGifts = lazy(() => import('@/canvas/public-affairs/PaGifts'));
const PaProjects = lazy(() => import('@/canvas/public-affairs/PaProjects'));
const PaReport = lazy(() => import('@/canvas/public-affairs/PaReport'));
const WebScreen = lazy(() => import('@/canvas/editorial/web/WebScreen'));
const ContractsScreen = lazy(() => import('@/canvas/editorial/ContractsScreen'));
const ContractDetail = lazy(() => import('@/canvas/editorial/contracts/ContractDetail'));
const NewContract = lazy(() => import('@/canvas/editorial/contracts/NewContract'));
const ContractPayments = lazy(() => import('@/canvas/editorial/contracts/PaymentsScreen'));
const ContractTemplates = lazy(() => import('@/canvas/editorial/contracts/TemplatesScreen'));
const RoyaltyScreen = lazy(() => import('@/canvas/editorial/royalty/RoyaltyScreen'));
const RightsScreen = lazy(() => import('@/canvas/editorial/rights/RightsScreen'));
const FinancialAudit = lazy(() => import('@/canvas/financial-audit/FinancialAudit'));
const ManagementHome = lazy(() => import('@/canvas/management/ManagementHome'));
const BaskiOneri = lazy(() => import('@/canvas/management/BaskiOneri'));
const BudgetScreen = lazy(() => import('@/canvas/budget/BudgetScreen'));
const SystemStatusScreen = lazy(() => import('@/canvas/it-ops/SystemStatusScreen'));
const ModelQualityScreen = lazy(() => import('@/canvas/model-quality/ModelQualityScreen'));
const FinanceScreen = lazy(() => import('@/canvas/finance/FinanceScreen'));
const RiskScreen = lazy(() => import('@/canvas/risk/RiskScreen'));
const RiskCard = lazy(() => import('@/canvas/risk/RiskCard'));
const DistributionScreen = lazy(() => import('@/canvas/distribution/DistributionScreen'));
const DistributionPlan = lazy(() => import('@/canvas/distribution/PlanEditor'));
const StockHome = lazy(() => import('@/canvas/stock/StockHome'));
const StockItem = lazy(() => import('@/canvas/stock/StockItem'));
const StockRunningOut = lazy(() => import('@/canvas/stock/RunningOut'));
const StockExcess = lazy(() => import('@/canvas/stock/Excess'));
const StockDiff = lazy(() => import('@/canvas/stock/StockDiff'));
const StockTransfers = lazy(() => import('@/canvas/stock/TransferErrors'));
const StockPickLine = lazy(() => import('@/canvas/stock/PickLine'));
const StockThresholds = lazy(() => import('@/canvas/stock/Thresholds'));
const TenderList = lazy(() => import('@/canvas/tenders/TenderList'));
const TenderDetail = lazy(() => import('@/canvas/tenders/TenderDetail'));
const ShippingHome = lazy(() => import('@/canvas/shipping/ShippingHome'));
const ShippingShipment = lazy(() => import('@/canvas/shipping/Shipment'));
const ShippingErrors = lazy(() => import('@/canvas/shipping/Errors'));
const ShippingWaiting = lazy(() => import('@/canvas/shipping/Waiting'));
const ShippingCarriers = lazy(() => import('@/canvas/shipping/Carriers'));
const ShippingReconcile = lazy(() => import('@/canvas/shipping/Reconcile'));
const SupplyHome = lazy(() => import('@/canvas/supply/SupplyHome'));
const SupplyLoad = lazy(() => import('@/canvas/supply/Load'));
const SupplyPaper = lazy(() => import('@/canvas/supply/Paper'));
const SupplySuppliers = lazy(() => import('@/canvas/supply/Suppliers'));
const SupplySupplier = lazy(() => import('@/canvas/supply/Supplier'));
const SupplyCost = lazy(() => import('@/canvas/supply/CostTrend'));
const SupplyCapacity = lazy(() => import('@/canvas/supply/Capacity'));
const CategoriesScreen = lazy(() => import('@/canvas/categories/CategoriesScreen'));
const ReadersScreen = lazy(() => import('@/canvas/readers/ReadersScreen'));
const ReaderCard = lazy(() => import('@/canvas/readers/ReaderCard'));
const CommerceScreen = lazy(() => import('@/canvas/commerce/CommerceScreen'));
const CommerceCustomer = lazy(() => import('@/canvas/commerce/CustomerCard'));
const CategoryBookProfile = lazy(() => import('@/canvas/categories/BookProfile'));
const DataSecurityScreen = lazy(() => import('@/canvas/data-security/DataSecurityScreen'));
const PazarScreen = lazy(() => import('@/canvas/pazar/PazarScreen'));
const FirstPrintScreen = lazy(() => import('@/canvas/first-print/FirstPrintScreen'));
const FieldScreen = lazy(() => import('@/canvas/field/FieldScreen'));
const CustomerBrief = lazy(() => import('@/canvas/field/CustomerBrief'));
const DealersScreen = lazy(() => import('@/canvas/dealers/DealersScreen'));
const DealerCard = lazy(() => import('@/canvas/dealers/DealerCard'));
const MusteriHome = lazy(() => import('@/canvas/musteri/CustomersHome'));
const MusteriAccounts = lazy(() => import('@/canvas/musteri/AccountsScreen'));
const MusteriAccount = lazy(() => import('@/canvas/musteri/AccountDetail'));
const MusteriPortfolio = lazy(() => import('@/canvas/musteri/PortfolioPhone'));
const MusteriHealth = lazy(() => import('@/canvas/musteri/DataHealthScreen'));
const BookForecastPage = lazy(() => import('@/canvas/first-print/BookForecast'));
const FreeForecastPage = lazy(() => import('@/canvas/first-print/FreeForecast'));
const SchoolsScreen = lazy(() => import('@/canvas/schools/SchoolsScreen'));
const SchoolCard = lazy(() => import('@/canvas/schools/SchoolCard'));
const RecruitBoard = lazy(() => import('@/canvas/hr/recruit/RecruitBoard'));
const CandidateDrawer = lazy(() => import('@/canvas/hr/recruit/CandidateDrawer'));
const PositionEditor = lazy(() => import('@/canvas/hr/recruit/PositionEditor'));
const HrTemplatesScreen = lazy(() => import('@/canvas/hr/recruit/TemplatesScreen'));
const HrRecordsScreen = lazy(() => import('@/canvas/hr/records/HrRecordsScreen'));
const MyLearning = lazy(() => import('@/canvas/hr/learning/MyLearning'));
const LearningDashboard = lazy(() => import('@/canvas/hr/learning/LearningDashboard'));
const LearningCourses = lazy(() => import('@/canvas/hr/learning/CoursesScreen'));
const LearningSession = lazy(() => import('@/canvas/hr/learning/SessionScreen'));
const LearningNeeds = lazy(() => import('@/canvas/hr/learning/NeedsScreen'));
const LearningUsage = lazy(() => import('@/canvas/hr/learning/UsageMap'));
const LearningGuides = lazy(() => import('@/canvas/hr/learning/GuidesScreen'));
const MarketingHome = lazy(() => import('@/canvas/marketing/MarketingHome'));
const MarketingPlan = lazy(() => import('@/canvas/marketing/PlanScreen'));
const SetsScreen = lazy(() => import('@/canvas/marketing/sets/SetsScreen'));
const EticaretHome = lazy(() => import('@/canvas/eticaret/EticaretHome'));
const EticaretDiffs = lazy(() => import('@/canvas/eticaret/DiffsScreen'));
const EticaretFunnel = lazy(() => import('@/canvas/eticaret/FunnelScreen'));
const EticaretMarkets = lazy(() => import('@/canvas/eticaret/MarketplacesScreen'));
const SetEditor = lazy(() => import('@/canvas/marketing/sets/SetEditor'));
const GiftOfferEditor = lazy(() => import('@/canvas/marketing/sets/GiftOfferEditor'));
const DigitalCatalog = lazy(() => import('@/canvas/dijital/DigitalCatalog'));
const DigitalOpportunities = lazy(() => import('@/canvas/dijital/OpportunitiesScreen'));
const DigitalSales = lazy(() => import('@/canvas/dijital/DigitalSalesScreen'));
const CreativeHome = lazy(() => import('@/canvas/marketing/creative/CreativeHome'));
const CampaignsScreen = lazy(() => import('@/canvas/kampanya/CampaignsScreen'));
const CampaignDetail = lazy(() => import('@/canvas/kampanya/CampaignDetail'));
const CreativeRequest = lazy(() => import('@/canvas/marketing/creative/RequestScreen'));
const MarketingMonth = lazy(() => import('@/canvas/marketing/monthly/MonthScreen'));
const MarketingFoyList = lazy(() => import('@/canvas/marketing/monthly/FoyList'));
const MarketingFoy = lazy(() => import('@/canvas/marketing/monthly/FoyScreen'));
const OkurAudience = lazy(() => import('@/canvas/okur/AudienceScreen'));
const OkurSegments = lazy(() => import('@/canvas/okur/SegmentsScreen'));
const OkurPrograms = lazy(() => import('@/canvas/okur/ProgramsScreen'));
const OkurReviews = lazy(() => import('@/canvas/okur/ReviewsScreen'));
const LaunchHome = lazy(() => import('@/canvas/marketing/launch/LaunchHome'));
const LaunchScreen = lazy(() => import('@/canvas/marketing/launch/LaunchScreen'));
const BacklistScreen = lazy(() => import('@/canvas/marketing/backlist/BacklistScreen'));
const PrHome = lazy(() => import('@/canvas/pr/PrHome'));
const PrBook = lazy(() => import('@/canvas/pr/PrBook'));
const PrKit = lazy(() => import('@/canvas/pr/PrKit'));
const PrContacts = lazy(() => import('@/canvas/pr/PrContacts'));
const PrContact = lazy(() => import('@/canvas/pr/PrContact'));
const PrCoverage = lazy(() => import('@/canvas/pr/PrCoverage'));
const PrReport = lazy(() => import('@/canvas/pr/PrReport'));
const AdsOverview = lazy(() => import('@/canvas/ads/AdsOverview'));
const AdsCampaigns = lazy(() => import('@/canvas/ads/AdsCampaigns'));
const AdsImport = lazy(() => import('@/canvas/ads/AdsImport'));
const AdsBudget = lazy(() => import('@/canvas/ads/AdsBudget'));
const AdsBriefs = lazy(() => import('@/canvas/ads/AdsBriefs'));
const SocialCalendar = lazy(() => import('@/canvas/social/SocialCalendar'));
const SocialPost = lazy(() => import('@/canvas/social/SocialPost'));
const SocialOpportunities = lazy(() => import('@/canvas/social/SocialOpportunities'));
const SocialReport = lazy(() => import('@/canvas/social/SocialReport'));
const SocialAccounts = lazy(() => import('@/canvas/social/SocialAccounts'));
const CollabBoard = lazy(() => import('@/canvas/influencers/CollabBoard'));
const InfluencerPeople = lazy(() => import('@/canvas/influencers/PeopleList'));
const InfluencerPerson = lazy(() => import('@/canvas/influencers/PersonCard'));
const InfluencerCandidates = lazy(() => import('@/canvas/influencers/Candidates'));
const CollabReport = lazy(() => import('@/canvas/influencers/CollabReport'));
const InfluencerPayouts = lazy(() => import('@/canvas/influencers/Payouts'));
const CatalogNewsletterHome = lazy(() => import('@/canvas/catalog-newsletter/CatalogNewsletterHome'));
const CatalogEditor = lazy(() => import('@/canvas/catalog-newsletter/CatalogEditor'));
const NewsletterEditor = lazy(() => import('@/canvas/catalog-newsletter/NewsletterEditor'));
const EventsCalendar = lazy(() => import('@/canvas/events/EventsCalendar'));
const EventsFair = lazy(() => import('@/canvas/events/FairCard'));
const EventsResult = lazy(() => import('@/canvas/events/FairResult'));
const EventsCrm = lazy(() => import('@/canvas/events/CrmEvents'));
const EventsAwards = lazy(() => import('@/canvas/events/Awards'));
const EventsTypeMap = lazy(() => import('@/canvas/events/TypeMap'));
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
const ChannelsHome = lazy(() => import('@/canvas/channels/ChannelsHome'));
const ChannelDetail = lazy(() => import('@/canvas/channels/Channel'));
const ChannelsMatrix = lazy(() => import('@/canvas/channels/Matrix'));
const ChannelsD2C = lazy(() => import('@/canvas/channels/D2CGrowth'));
const ChannelsAccounts = lazy(() => import('@/canvas/channels/Accounts'));
const TrendyolHome = lazy(() => import('@/canvas/channels/trendyol/TrendyolHome'));
const TrendyolProducts = lazy(() => import('@/canvas/channels/trendyol/Products'));
const TrendyolOrders = lazy(() => import('@/canvas/channels/trendyol/Orders'));
const TrendyolQuestions = lazy(() => import('@/canvas/channels/trendyol/Questions'));
const TrendyolShowcase = lazy(() => import('@/canvas/channels/trendyol/Showcase'));
const TrendyolWeekly = lazy(() => import('@/canvas/channels/trendyol/Weekly'));
const TrendyolImports = lazy(() => import('@/canvas/channels/trendyol/Imports'));
const AmazonHome = lazy(() => import('@/canvas/channels/amazon/AmazonHome'));
const AmazonConsignment = lazy(() => import('@/canvas/channels/amazon/Consignment'));
const AmazonInternational = lazy(() => import('@/canvas/channels/amazon/International'));
const AmazonRights = lazy(() => import('@/canvas/channels/amazon/Rights'));
const AmazonDrafts = lazy(() => import('@/canvas/channels/amazon/Drafts'));
const AmazonMarketCards = lazy(() => import('@/canvas/channels/amazon/MarketCards'));

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
            {/* M50 Zeki AI kalitesi: karne, kalite koşuları (önce/sonra), hata sınıfları, geri bildirim, sürümler (/api/v1/model-quality). */}
            <Route path="zeki-kalite" element={<ModelQualityScreen />} />
            {/* M45 Finansal raporlar: gelir tablosu, bütçe–gerçekleşme, kârlılık, nakit, vergi takvimi (/api/v1/finance). */}
            <Route path="finansal-raporlar" element={<FinanceScreen />} />
            {/* M47 Risk yönetimi ve uyum (/api/v1/risk). */}
            <Route path="risk-uyum" element={<RiskScreen />} />
            <Route path="risk-uyum/risk/:id" element={<RiskCard />} />
            {/* M33 İhale takibi (Satış ve saha): ilanlar, takvim, belge arşivi, sonuçlar, kamu satışları (/api/v1/tenders). */}
            <Route path="ihale" element={<TenderList />} />
            <Route path="ihale/:id" element={<TenderDetail />} />
            {/* M48 IT altyapı ve sistem durumu: halkalar, olaylar, zamanlanmış işler, sürümler, kapasite (/api/v1/it-ops). */}
            <Route path="sistem-durumu" element={<SystemStatusScreen />} />
            {/* M49 Veri güvenliği (Altyapı ve destek): giriş/erişim kaydı, uyarılar, hijyen, envanter, saklama (/api/v1/data-security). */}
            <Route path="veri-guvenligi" element={<DataSecurityScreen />} />
            {/* M44 Lojistik ve kargo: günlük hat, gönderi kartı, hatalar, teslim bekleyen, firma karnesi, mutabakat (/api/v1/shipping). */}
            <Route path="kargo" element={<ShippingHome />} />
            <Route path="kargo/gonderi/:id" element={<ShippingShipment />} />
            <Route path="kargo/hatalar" element={<ShippingErrors />} />
            <Route path="kargo/bekleyen" element={<ShippingWaiting />} />
            <Route path="kargo/firmalar" element={<ShippingCarriers />} />
            <Route path="kargo/mutabakat" element={<ShippingReconcile />} />
            {/* M52 Tedarik ve baskı (Lojistik) */}
            <Route path="tedarik" element={<SupplyHome />} />
            <Route path="tedarik/yuk" element={<SupplyLoad />} />
            <Route path="tedarik/kapasite" element={<SupplyCapacity />} />
            <Route path="tedarik/kagit" element={<SupplyPaper />} />
            <Route path="tedarik/tedarikciler" element={<SupplySuppliers />} />
            <Route path="tedarik/tedarikci/:cari" element={<SupplySupplier />} />
            <Route path="tedarik/maliyet" element={<SupplyCost />} />
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
            {/* M59 Bayi riski (Satış ve saha): pano, bayiler, limit önerileri, aksiyonlar, kurallar; bayi kartı cari koduyla (/api/v1/dealers). */}
            <Route path="bayi-risk" element={<DealersScreen />} />
            <Route path="bayi-risk/:code" element={<DealerCard />} />
            {/* M38 Müşteri ilişkileri (Satış ve saha): özet, cariler, cari ayrıntısı, telefon portföyü, CRM veri sağlığı (/api/v1/musteri). */}
            <Route path="musteri-iliskileri" element={<MusteriHome />} />
            <Route path="musteri-iliskileri/cariler" element={<MusteriAccounts />} />
            <Route path="musteri-iliskileri/cari/:kod" element={<MusteriAccount />} />
            <Route path="musteri-iliskileri/portfoyum" element={<MusteriPortfolio />} />
            <Route path="musteri-iliskileri/veri-sagligi" element={<MusteriHealth />} />
            {/* M31 Okul tanıtım ve ziyaret (/api/v1/schools): telefon öncelikli «Bu hafta», okul kartı, bayi kuyruğu, dönem raporu. */}
            <Route path="okul-tanitim" element={<SchoolsScreen />} />
            <Route path="okul-tanitim/:id" element={<SchoolCard />} />
            {/* İnsan Kaynakları: M55 işe alım (/api/v1/hr/recruit) ve İK-0 çalışan/KVKK kayıtları (/api/v1/hr). */}
            <Route path="ik/ise-alim" element={<RecruitBoard />} />
            <Route path="ik/ise-alim/aday/:id" element={<CandidateDrawer />} />
            <Route path="ik/pozisyonlar" element={<PositionEditor />} />
            <Route path="ik/belgeler" element={<HrTemplatesScreen />} />
            <Route path="ik/kayitlar" element={<HrRecordsScreen />} />
            {/* M43 Depo ve stok (Lojistik): stok, kitap stok kartı, bitecekler, fazla stok, güvenlik stoku, Logo–CRM farkı,
                aktarım hataları, depo hattı (/api/v1/stock). */}
            <Route path="stok" element={<StockHome />} />
            <Route path="stok/bitecekler" element={<StockRunningOut />} />
            <Route path="stok/fazla" element={<StockExcess />} />
            <Route path="stok/esikler" element={<StockThresholds />} />
            <Route path="stok/fark" element={<StockDiff />} />
            <Route path="stok/aktarim" element={<StockTransfers />} />
            <Route path="stok/depo-hatti" element={<StockPickLine />} />
            <Route path="stok/:stokKodu" element={<StockItem />} />
            {/* M57 Eğitim ve gelişim (/api/v1/hr/learning): Eğitimlerim, pano, katalog/oturum, ihtiyaç, kullanım haritası, rehberler. */}
            <Route path="ik/egitimlerim" element={<MyLearning />} />
            <Route path="ik/egitim" element={<LearningDashboard />} />
            <Route path="ik/egitim/katalog" element={<LearningCourses />} />
            <Route path="ik/egitim/oturum/:id" element={<LearningSession />} />
            <Route path="ik/egitim/ihtiyaclar" element={<LearningNeeds />} />
            <Route path="ik/egitim/kullanim" element={<LearningUsage />} />
            <Route path="ik/egitim/rehberler" element={<LearningGuides />} />
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
            {/* Pazarlama › Okur ve müşteri: H2 okuyucu veri tabanı (/api/v1/readers). */}
            <Route path="okurlar" element={<ReadersScreen />} />
            <Route path="okurlar/kisi/:id" element={<ReaderCard />} />
            <Route path="okurlar/:section/*" element={<ReadersScreen />} />
            {/* H3 E-ticaret müşterileri (/api/v1/commerce): özet, RFM, tetikler, kampanya sonucu, huni, müşteri kartı. */}
            <Route path="eticaret-musteri" element={<CommerceScreen />} />
            <Route path="eticaret-musteri/musteri/:key" element={<CommerceCustomer />} />
            <Route path="eticaret-musteri/:section/*" element={<CommerceScreen />} />
            {/* Pazarlama › Okur ve müşteri: M37 okur topluluğu (/api/v1/okur); okur sayıları H2 çekirdeğinden, kişi adı yok. */}
            <Route path="okur-toplulugu" element={<OkurAudience />} />
            <Route path="okur-toplulugu/segmentler" element={<OkurSegments />} />
            <Route path="okur-toplulugu/programlar" element={<OkurPrograms />} />
            <Route path="okur-toplulugu/yorumlar" element={<OkurReviews />} />
            {/* Pazarlama › Planlama: M16 lansman (/api/v1/marketing/launches). */}
            <Route path="pazarlama/lansman" element={<LaunchHome />} />
            <Route path="pazarlama/lansman/:id" element={<LaunchScreen />} />
            {/* Pazarlama › Planlama: M17 backlist fırsatları ve aktivasyon planı (/api/v1/marketing/backlist). */}
            <Route path="pazarlama/backlist" element={<BacklistScreen />} />
            {/* Pazarlama › İletişim: M20 basın ilişkileri (/api/v1/pr). */}
            <Route path="basin-iliskileri" element={<PrHome />} />
            <Route path="basin-iliskileri/kitap/:bookId" element={<PrBook />} />
            <Route path="basin-iliskileri/dosya/:id" element={<PrKit />} />
            <Route path="basin-iliskileri/kisiler" element={<PrContacts />} />
            <Route path="basin-iliskileri/kisi/:key" element={<PrContact />} />
            <Route path="basin-iliskileri/yansimalar" element={<PrCoverage />} />
            <Route path="basin-iliskileri/rapor" element={<PrReport />} />
            {/* Pazarlama › Kampanya: M21 dijital pazarlama ve reklam (/api/v1/ads). */}
            <Route path="reklam" element={<AdsOverview />} />
            <Route path="reklam/kampanyalar" element={<AdsCampaigns />} />
            <Route path="reklam/yukle" element={<AdsImport />} />
            <Route path="reklam/butce" element={<AdsBudget />} />
            <Route path="reklam/brief" element={<AdsBriefs />} />
            {/* Pazarlama › İletişim: M22 sosyal medya takvimi, onay ve yayına hazır paket (/api/v1/social). */}
            <Route path="sosyal-medya" element={<SocialCalendar />} />
            <Route path="sosyal-medya/gonderi/:id" element={<SocialPost />} />
            <Route path="sosyal-medya/firsatlar" element={<SocialOpportunities />} />
            <Route path="sosyal-medya/rapor" element={<SocialReport />} />
            <Route path="sosyal-medya/hesaplar" element={<SocialAccounts />} />
            {/* Pazarlama › İletişim: M23 İşbirlikleri (/api/v1/influencers). */}
            <Route path="isbirlikleri" element={<CollabBoard />} />
            <Route path="isbirlikleri/kisiler" element={<InfluencerPeople />} />
            <Route path="isbirlikleri/kisi/:id" element={<InfluencerPerson />} />
            <Route path="isbirlikleri/aday" element={<InfluencerCandidates />} />
            <Route path="isbirlikleri/aday/:kitap" element={<InfluencerCandidates />} />
            <Route path="isbirlikleri/rapor" element={<CollabReport />} />
            <Route path="isbirlikleri/odemeler" element={<InfluencerPayouts />} />
            {/* Pazarlama › Kampanya: M24 katalog ve e-bülten (/api/v1/catalog-newsletter). */}
            <Route path="katalog-bulten" element={<CatalogNewsletterHome />} />
            <Route path="katalog-bulten/rapor" element={<CatalogNewsletterHome initial="rapor" />} />
            <Route path="katalog-bulten/katalog/:id" element={<CatalogEditor />} />
            <Route path="katalog-bulten/bulten/:id" element={<NewsletterEditor />} />
            {/* Pazarlama › Etkinlik: M27 fuar, etkinlik ve ödül (/api/v1/events). */}
            <Route path="etkinlikler" element={<EventsCalendar />} />
            <Route path="etkinlikler/fuar/:id" element={<EventsFair />} />
            <Route path="etkinlikler/fuar/:id/sonuc" element={<EventsResult />} />
            <Route path="etkinlikler/crm" element={<EventsCrm />} />
            <Route path="etkinlikler/oduller" element={<EventsAwards />} />
            <Route path="etkinlikler/tip-eslemesi" element={<EventsTypeMap />} />
            {/* Platform › Kanallar: M42 kanal karnesi, kitap × kanal, D2C, cari eşleme (/api/v1/channels). M40/M41 aynı alana eklenir. */}
            <Route path="kanallar" element={<ChannelsHome />} />
            <Route path="kanallar/matris" element={<ChannelsMatrix />} />
            <Route path="kanallar/d2c" element={<ChannelsD2C />} />
            <Route path="kanallar/eslesme" element={<ChannelsAccounts />} />
            <Route path="kanallar/:platform" element={<ChannelDetail />} />
            {/* Platform › Trendyol (M40) ve Amazon ve yurtdışı (M41): yalnız okuma + panel dosyası (/api/v1/channels/trendyol|amazon). */}
            <Route path="trendyol" element={<TrendyolHome />} />
            <Route path="trendyol/urunler" element={<TrendyolProducts />} />
            <Route path="trendyol/siparisler" element={<TrendyolOrders />} />
            <Route path="trendyol/sorular" element={<TrendyolQuestions />} />
            <Route path="trendyol/vitrin" element={<TrendyolShowcase />} />
            <Route path="trendyol/haftalik" element={<TrendyolWeekly />} />
            <Route path="trendyol/yukle" element={<TrendyolImports />} />
            <Route path="amazon" element={<AmazonHome />} />
            <Route path="amazon/konsinye" element={<AmazonConsignment />} />
            <Route path="amazon/yurtdisi" element={<AmazonInternational />} />
            <Route path="amazon/haklar" element={<AmazonRights />} />
            <Route path="amazon/pazarlar" element={<AmazonMarketCards />} />
            <Route path="amazon/taslaklar" element={<AmazonDrafts />} />
            {/* SEO & GEO: kendi rayı ve uçlarıyla (/api/v1/seo-geo); T-soft ürün denetimi, Search Console, AI görünürlük. */}
            {/* M53 Set, hediye ve promosyon (/api/v1/marketing/sets, /gift-offers, /promo-items). */}
            <Route path="pazarlama/set-hediye" element={<SetsScreen />} />
            <Route path="pazarlama/set-hediye/set/:id" element={<SetEditor />} />
            <Route path="pazarlama/set-hediye/teklif/:id" element={<GiftOfferEditor />} />
            {/* M34 E-ticaret ve platform (/api/v1/eticaret): platform durumu, farklar, huni, pazar yerleri. */}
            <Route path="e-ticaret" element={<EticaretHome />} />
            <Route path="e-ticaret/farklar" element={<EticaretDiffs />} />
            <Route path="e-ticaret/huni" element={<EticaretFunnel />} />
            <Route path="e-ticaret/pazar-yerleri" element={<EticaretMarkets />} />
            <Route path="pazarlama/icerik" element={<CreativeHome />} />
            <Route path="pazarlama/icerik/:id" element={<CreativeRequest />} />
            {/* M35 E-ticaret kampanyaları (/api/v1/kampanya): kayıt defteri, takvim, adaylar, kampanya ayrıntısı ve sonuç. */}
            <Route path="kampanyalar" element={<CampaignsScreen />} />
            <Route path="kampanyalar/takvim" element={<CampaignsScreen initial="takvim" />} />
            <Route path="kampanyalar/adaylar" element={<CampaignsScreen initial="adaylar" />} />
            <Route path="kampanyalar/:id" element={<CampaignDetail />} />
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
            {/* M39 Pazar ve rakip: özet, rakipler/emsal/eşleme, sektör raporları, aylık özet (/api/v1/pazar). */}
            <Route path="pazar-arastirma" element={<PazarScreen />} />
            <Route path="pazar-arastirma/:section" element={<PazarScreen />} />
            <Route path="pazar-arastirma/raporlar/:id" element={<PazarScreen />} />
            <Route path="pazar-arastirma/ozet/:donem" element={<PazarScreen />} />
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
            {/* M51 Müşteri hizmetleri: kuyruk, müşteri bağlamı, bayi görünümü, kalite, SSS açıkları (/api/v1/support). */}
            <Route path="musteri-destek" element={<SupportScreen />} />
            {/* M28 Kurumsal ilişkiler (/api/v1/public-affairs): kanaat önderi ve kurum kartı, hediye programı, kamu projeleri. */}
            <Route path="kurumsal-iliskiler" element={<PaHome />} />
            <Route path="kurumsal-iliskiler/kisiler" element={<PaPeople />} />
            <Route path="kurumsal-iliskiler/kisi/:id" element={<PaPersonCard />} />
            <Route path="kurumsal-iliskiler/kurumlar" element={<PaOrgs />} />
            <Route path="kurumsal-iliskiler/hediye" element={<PaGifts />} />
            <Route path="kurumsal-iliskiler/projeler" element={<PaProjects />} />
            <Route path="kurumsal-iliskiler/rapor" element={<PaReport />} />
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
            <Route path="dijital-yayin" element={<DigitalCatalog />} />
            <Route path="dijital-yayin/kitap/:id" element={<DigitalCatalog />} />
            <Route path="dijital-yayin/firsatlar" element={<DigitalOpportunities />} />
            <Route path="dijital-yayin/satis" element={<DigitalSales />} />
            <Route path="telif-sozlesme" element={<ContractsScreen />} />
            <Route path="telif-sozlesme/yeni" element={<NewContract />} />
            <Route path="telif-sozlesme/odemeler" element={<ContractPayments />} />
            <Route path="telif-sozlesme/sablonlar" element={<ContractTemplates />} />
            <Route path="telif-sozlesme/:key" element={<ContractDetail />} />
            <Route path="telif-donem" element={<RoyaltyScreen />} />
            <Route path="haklar" element={<RightsScreen />} />
          </Route>
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </RoutedErrorBoundary>
      </Suspense>
    </BrowserRouter>
  );
}
