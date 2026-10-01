import { useState, type ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ExternalLink, Gauge, Loader2, RefreshCw } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { call, dateTime, fmt, qs, type Severity } from './api';
import SeoLayout, { Failed, Loading, SeoInfo } from './SeoLayout';
import { EmptyHint, Explain, ExplainLabel } from '../components/Explain';
import { Term } from './terms';
import SeoPager from './SeoPager';

/* ------------------------------------------------------------------ uç tipleri (/api/v1/seo-geo/tech*, /speed*) */
type RunState = { running: boolean; done?: number; failed?: number; queue?: number | null; startedAt: string | null; finishedAt: string | null; error: string | null };
type Kind = 'product' | 'category' | 'brand' | 'author' | 'home';
type TechCheck = { id: string; severity: Severity; title: string; why: string; count: number; group: 'page' | 'image' };
type Hop = { url: string; status: number; location: string | null; loop?: boolean; error?: string };
type TechItem = {
  url: string;
  kind: Kind;
  productId: string | null;
  name: string | null;
  status: number;
  chain: Hop[];
  issues: string[];
  checkedAt: string;
  sales: number;
  title: string | null;
  canonical: { href: string | null; kind: string; count: number; target?: { status: number; hops: number; final: string } } | null;
  robots: string | null;
  xRobotsTag: string | null;
  hreflang: number;
  trackingLinks: string[];
  images: { count: number; noAlt: string[]; emptyAlt: string[]; badName: string[]; noSize: string[] } | null;
  mainImage: { src: string; alt: string | null } | null;
  h1: number | null;
  finalUrl: string | null;
};
type TechReport = {
  checked: number;
  withIssues: number;
  byKind: Partial<Record<Kind, number>>;
  lastChecked: string | null;
  crawl: RunState;
  snapshots: RunState;
  checks: TechCheck[];
  total: number;
  items: TechItem[];
  kinds: Record<Kind, string>;
};
type SitemapInfo = { url: string; parent: string | null; status: number | null; kind: string | null; count: number; newest: string | null; oldest: string | null; withLastmod: number; stale: boolean; error: string | null; redirectedTo?: string };
type SitemapSnap = {
  site: string;
  declared: string[];
  fallback: boolean;
  sitemaps: SitemapInfo[];
  partial: boolean;
  totalUrls: number;
  staleDays: number;
  activeProducts: number;
  missingCount: number;
  missing: Array<{ id: string; name: string; url: string }>;
  missingStart: number;
  sample: { requested: number; checked: number; of: number; ok: number; redirect: number; error: number; items: Array<{ url: string; status: number; hops: number; final: string; issues: string[] }> };
  checkedAt: string;
  savedAt: string;
};
type BotRow = {
  agent: string;
  owner: string;
  purpose: 'search' | 'ai_search' | 'user' | 'training';
  purposeLabel: string;
  why: string;
  group: string;
  advice: string;
  blocked: boolean;
  results: Array<{ label: string; url: string; allowed: boolean; rule: string | null }>;
};
type RobotsSnap = { site: string; status: number | null; text: string; bots: BotRow[]; paths: Array<{ label: string; url: string }>; sitemaps: string[]; savedAt: string };
type Metric = 'lcp' | 'inp' | 'cls' | 'fcp' | 'ttfb';
type Cat = 'good' | 'ni' | 'poor' | null;
type CruxMetric = { p75: number | null; category: Cat; good?: number; ni?: number; poor?: number };
type Crux = { metrics: Partial<Record<Metric, CruxMetric>>; period?: { first: string | null; last: string | null }; noData?: boolean; error?: string; measuredAt: string };
type Psi = { score: number | null; lab: Partial<Record<'lcp' | 'cls' | 'fcp' | 'tbt' | 'si' | 'ttfb' | 'tti', number>>; labCategory: Partial<Record<string, Cat>>; field: Partial<Record<Metric, CruxMetric>>; fieldOrigin: boolean; error?: string; measuredAt: string };
type SpeedReport = {
  configured: boolean;
  state: RunState & { sample: { products: number; pages: number } | null };
  days: number;
  origin: Partial<Record<'phone' | 'desktop', Crux & { origin: string }>>;
  items: Array<{ url: string; kind: Kind; name: string | null; psi: Partial<Record<'mobile' | 'desktop', Psi>>; crux: Partial<Record<'phone' | 'desktop', Crux>> }>;
  trend: { origin: Array<{ date: string; formFactor: string } & Partial<Record<Metric, number | null>>>; psi: Array<{ date: string; strategy: string; score: number; pages: number }> };
  thresholds: Record<Metric, { good: number; poor: number }>;
};

const techApi = {
  report: (p: { issue?: string; kind?: string; group?: string; start?: number; limit?: number }) => call<TechReport>(`tech?${qs(p)}`),
  crawl: (budget = 3600) => call<{ started: boolean }>(`tech/crawl?budget=${budget}`, { method: 'POST' }),
  sitemaps: (start = 0, limit = 50) => call<{ snapshot: SitemapSnap | null; state: RunState }>(`tech/sitemaps?${qs({ start, limit })}`),
  refresh: (sample = 50) => call<{ started: boolean }>(`tech/sitemaps/refresh?sample=${sample}`, { method: 'POST' }),
  robots: () => call<{ snapshot: RobotsSnap; state: RunState }>('tech/robots'),
  speed: () => call<SpeedReport>('speed'),
  speedRun: (products = 10, pages = 5) => call<{ started: boolean }>(`speed/run?${qs({ products, pages })}`, { method: 'POST' }),
};

const PAGE = 40;
const TABS = [
  { id: 'sorunlar', label: 'Sayfa sorunları' },
  { id: 'sitemap', label: 'Site haritası' },
  { id: 'google-haritalar', label: 'Google’daki haritalar' },
  { id: 'botlar', label: 'Yapay zekâ botları' },
  { id: 'gorseller', label: 'Görseller' },
  { id: 'hiz', label: 'Hız' },
] as const;
type Tab = (typeof TABS)[number]['id'];
/** Sekmenin ne işe yaradığı; sekme şeridinin altında tek cümle. */
const TAB_HINT: Record<Tab, string> = {
  sorunlar: 'Canlı sayfalardaki teknik sorunlar: açılmayan ya da yönlenen sayfalar, yanlış asıl adres etiketi, aramadan gizlenen sayfalar. Bu listeyi site yöneticisine iletin.',
  sitemap: 'Sitenin Google’a verdiği sayfa listesi (site haritası) güncel mi, satıştaki her kitap listede var mı.',
  'google-haritalar': 'Search Console’a gönderilmiş site haritalarını Google’ın okuyup okumadığı ve bulduğu hatalar.',
  botlar: 'Arama motoru ve yapay zekâ botlarının sitenin hangi bölümlerine girebildiği (robots.txt izinleri).',
  gorseller: 'Kitap sayfalarındaki görsellerin yazılı tanımı (alt metin), dosya adı ve boyutu; Google Görseller bunlara bakar.',
  hiz: 'Sayfaların ne kadar hızlı açıldığı; Google, gerçek ziyaretçilerdeki hızı sıralamada kullanır.',
};
/** Hız ölçülerinin sade anlamı. */
const METRIC_WHY: Record<Metric, string> = {
  lcp: 'Sayfanın en büyük parçasının (çoğunlukla kapak görseli ya da başlık) ekranda görünme süresi. Ne kadar kısa, o kadar iyi.',
  inp: 'Ziyaretçi bir yere dokunduğunda ya da tıkladığında sayfanın tepki verme süresi.',
  cls: 'Sayfa yüklenirken içeriğin ne kadar kaydığı; kayma okuru yanlış yere tıklatır. 0’a yakın olması iyidir.',
  fcp: 'Sayfada ilk yazı ya da görselin görünme süresi.',
  ttfb: 'Sitenin ilk cevabı gönderme süresi.',
};
const KIND_LABEL: Record<Kind, string> = { product: 'Ürün', category: 'Kategori', brand: 'Yayınevi', author: 'Yazar', home: 'Anasayfa' };
const CAT_TONE: Record<'good' | 'ni' | 'poor', 'good' | 'mid' | 'bad'> = { good: 'good', ni: 'mid', poor: 'bad' };
const CAT_LABEL: Record<'good' | 'ni' | 'poor', string> = { good: 'İyi', ni: 'İyileştirilmeli', poor: 'Kötü' };
const METRIC_LABEL: Record<Metric, string> = {
  lcp: 'En büyük içerik (LCP)',
  inp: 'Etkileşim gecikmesi (INP)',
  cls: 'Düzen kayması (CLS)',
  fcp: 'İlk içerik (FCP)',
  ttfb: 'İlk bayt (TTFB)',
};

/** Değer biçimi: süre metrikleri ms'den (LCP/FCP/TTFB saniye, INP ms), CLS birimsiz. */
const metricText = (m: string, v: number | null | undefined) => {
  if (v == null) return '—';
  if (m === 'cls') return fmt(v, 2);
  if (m === 'inp' || m === 'tbt') return `${fmt(v)} ms`;
  return `${fmt(v / 1000, 1)} sn`;
};
const thresholdText = (m: Metric, t: { good: number; poor: number }) => `iyi ≤ ${metricText(m, t.good)} · kötü > ${metricText(m, t.poor)}`;

/** Teknik sağlık: canlı sayfaların teknik denetimi, sitemap, robots.txt'teki yapay zekâ botları, görseller ve hız.
 *  Site yalnız okunarak, saniyede en çok bir istekle taranır; T-soft'a hiçbir şey yazılmaz. */
export default function SeoTech() {
  const [params, setParams] = useSearchParams();
  const tab = (TABS.some((t) => t.id === params.get('sekme')) ? params.get('sekme') : 'sorunlar') as Tab;
  const setTab = (t: Tab) => {
    const next = new URLSearchParams();
    if (t !== 'sorunlar') next.set('sekme', t);
    setParams(next, { replace: true });
  };

  return (
    <SeoLayout
      path="/seo-geo/teknik"
      crumb="Teknik sağlık"
      eyebrow="SEO & GEO · teknik tarama"
      title="Teknik sağlık"
      lead="Sitenin teknik sağlığı: sayfalar açılıyor mu, yönlendirmeler ve asıl adres ayarları doğru mu, site haritası güncel mi, botlara izin var mı, görseller ve hız nasıl. Site yalnız okunarak, saniyede en çok bir istekle taranır; hiçbir şey değiştirilmez."
    >
      <div className="sg-filters" role="tablist" aria-label="Bölüm">
        {TABS.map((t) => (
          <button key={t.id} role="tab" className="sg-filter" aria-pressed={tab === t.id} aria-selected={tab === t.id} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>
      <p style={{ margin: '-6px 0 0', fontSize: 12.5, color: 'var(--sg-muted)', lineHeight: 1.5 }}>{TAB_HINT[tab]}</p>
      {tab === 'sorunlar' && <IssuesTab group="page" />}
      {tab === 'gorseller' && <IssuesTab group="image" />}
      {tab === 'sitemap' && <SitemapTab />}
      {tab === 'google-haritalar' && <GscSitemapsTab />}
      {tab === 'botlar' && <BotsTab />}
      {tab === 'hiz' && <SpeedTab />}
    </SeoLayout>
  );
}

/* ------------------------------------------------------------------ sayfa sorunları / görseller */
function IssuesTab({ group }: { group: 'page' | 'image' }) {
  const qc = useQueryClient();
  const [issue, setIssue] = useState('');
  const [kind, setKind] = useState<Kind | ''>('');
  const [start, setStart] = useState(0);
  const r = useQuery({
    queryKey: ['seo-tech', group, issue, kind, start],
    queryFn: () => techApi.report({ issue, kind, group: issue ? '' : group === 'image' ? 'image' : '', start, limit: PAGE }),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
    refetchInterval: (q) => (q.state.data?.crawl.running ? 15000 : false),
  });
  const crawl = useMutation({ mutationFn: () => techApi.crawl(3600), onSuccess: () => qc.invalidateQueries({ queryKey: ['seo-tech'] }) });
  const d = r.data;
  const checks = (d?.checks ?? []).filter((c) => c.group === group);
  const title = (id: string) => d?.checks.find((c) => c.id === id)?.title ?? id;
  const sev = (id: string) => d?.checks.find((c) => c.id === id)?.severity ?? 'düşük';
  const shown = (it: TechItem) => it.issues.filter((i) => (group === 'image' ? d?.checks.find((c) => c.id === i)?.group === 'image' : true));
  const running = !!d?.crawl.running;
  const pick = (id: string) => {
    setIssue(issue === id ? '' : id);
    setStart(0);
  };

  return (
    <>
      <div className="sg-actions">
        <button className="sg-button" onClick={() => crawl.mutate()} disabled={crawl.isPending || running}>
          {running ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />}
          {running ? `Taranıyor ${fmt(d?.crawl.done)}${d?.crawl.queue ? ` / ${fmt(d.crawl.queue)}` : ''}` : 'Taramayı başlat (1 saat)'}
        </button>
      </div>
      {r.isLoading && <Loading text="Tarama sonuçları getiriliyor…" />}
      {r.error && <Failed error={r.error} />}
      {crawl.error && <Failed error={crawl.error} />}
      {d?.crawl.error && <p className="sg-banner err">Son tarama durdu: {d.crawl.error}</p>}
      {d && (
        <>
          <section className="sg-kpis" aria-label="Özet">
            <Kpi label="Taranan sayfa" value={fmt(d.checked)} note={`Son tarama ${dateTime(d.lastChecked)} · her gece kaldığı yerden sürer`} info={<SeoInfo k={r.data?.kaynaklar} label="Taranan sayfa" />}
              explain="Canlı sitede açılıp denetlenen sayfa sayısı: anasayfa, ürün sayfaları (çok satandan başlayarak) ve yazar, kategori, yayınevi sayfaları." />
            <Kpi label="Sorunlu sayfa" value={fmt(d.withIssues)} note="En az bir teknik sorunu olan" info={<SeoInfo k={r.data?.kaynaklar} label="Sorunlu sayfa" />}
              explain="Taranan sayfalardan en az bir teknik sorun bulunanların sayısı. Sorunun ne olduğu soldaki listede, hangi sayfada olduğu sağdaki tabloda." />
            {group === 'page' ? (
              <Kpi
                label="Açılmayan / yönlenen"
                value={fmt(['not_found', 'server_error', 'fetch_error', 'redirect_loop'].reduce((a, k) => a + (d.checks.find((c) => c.id === k)?.count ?? 0), 0))}
                note={`Yönlendirilen ${fmt((d.checks.find((c) => c.id === 'redirected')?.count ?? 0) + (d.checks.find((c) => c.id === 'redirect_chain')?.count ?? 0))}`} info={<SeoInfo k={r.data?.kaynaklar} label="Açılmayan / yönlenen" />}
                explain="Büyük sayı: bulunamayan (404), sunucu hatası veren, hiç açılamayan ya da yönlendirme döngüsüne giren sayfalar. Alttaki sayı başka adrese yönlenen sayfalar; bunlar açılır ama Google için fazladan adım demektir." />
            ) : (
              <Kpi label="Kapak alt metni sorunlu" value={fmt(d.checks.find((c) => c.id === 'main_img_alt')?.count)} note="Ana ürün görselinin alt metni kitap adını taşımıyor" info={<SeoInfo k={r.data?.kaynaklar} label="Kapak alt metni sorunlu" />}
                explain="Alt metin, görselin yazılı tanımıdır; Google Görseller ve ekran okuyucular bunu okur. Kapak görselinin alt metninde kitabın adı geçmeli." />
            )}
            <Kpi
              label="Türe göre"
              value={fmt(d.byKind.product)}
              note={(Object.keys(KIND_LABEL) as Kind[]).filter((k) => d.byKind[k]).map((k) => `${KIND_LABEL[k]} ${fmt(d.byKind[k])}`).join(' · ') || '—'} info={<SeoInfo k={r.data?.kaynaklar} label="Türe göre" />}
              explain="Büyük sayı taranan ürün sayfası sayısıdır; alt satırda taranan sayfaların türe göre dağılımı." />
          </section>

          {!d.checked && (
            <EmptyHint
              title="Henüz tarama yapılmadı"
              why="«Taramayı başlat»a basın ya da gece taramasını bekleyin. Anasayfa, ürün sayfaları (çok satandan) ve yazar, kategori, yayınevi sayfaları sırayla açılır."
            />
          )}

          {d.checked > 0 && (
            <div className="sg-grid">
              <section className="sg-card sg-span-5">
                <h2>{group === 'image' ? 'Görsel sorunları' : 'Sorunlar'}</h2>
                <p className="sg-sub">Her sorunun kaç sayfada olduğu. Bir soruna dokunun; neden önemli olduğu altta, o sayfalar sağda görünür.</p>
                <div className="sg-bars">
                  {checks
                    .filter((c) => c.count > 0)
                    .sort((a, b) => b.count - a.count)
                    .map((c) => (
                      <button
                        key={c.id}
                        className="sg-bar-row"
                        style={{ background: 'none', border: 0, textAlign: 'left', cursor: 'pointer', padding: 0, font: 'inherit', fontWeight: issue === c.id ? 800 : 500 }}
                        onClick={() => pick(c.id)}
                        aria-pressed={issue === c.id}
                        title={c.why}
                      >
                        <span style={{ display: 'flex', gap: 8, alignItems: 'center', minWidth: 0 }}>
                          <i className={`sg-dot ${c.severity}`} aria-hidden />
                          {c.title}
                        </span>
                        <span className="sg-mono">
                          {fmt(c.count)} · %{Math.round((100 * c.count) / Math.max(1, d.checked))}
                        </span>
                        <span className="sg-bar">
                          <i style={{ width: `${(100 * c.count) / Math.max(1, d.checked)}%` }} />
                        </span>
                      </button>
                    ))}
                  {!checks.some((c) => c.count > 0) && <p className="sg-banner ok">Taranan sayfalarda bu gruptan sorun bulunmadı.</p>}
                </div>
                {issue && <p className="sg-banner" style={{ marginTop: 14 }}>{d.checks.find((c) => c.id === issue)?.why}</p>}
              </section>

              <section className="sg-card sg-span-7">
                <h2>{issue ? title(issue) : group === 'image' ? 'Görsel sorunu olan sayfalar' : 'Sorunlu sayfalar'}</h2>
                <p className="sg-sub">Anasayfa önce, sonra çok satandan aza. Toplam {fmt(d.total)} sayfa.</p>
                <div className="sg-filters" role="toolbar" aria-label="Sayfa türü" style={{ marginBottom: 12 }}>
                  {(['', 'product', 'category', 'author', 'brand', 'home'] as const).map((k) => (
                    <button
                      key={k || 'all'}
                      className="sg-filter"
                      aria-pressed={kind === k}
                      onClick={() => {
                        setKind(k);
                        setStart(0);
                      }}
                    >
                      {k ? KIND_LABEL[k] : 'Tümü'}
                    </button>
                  ))}
                </div>
                {!d.items.length ? (
                  <EmptyHint title="Bu süzgece uyan sorunlu sayfa yok" why="Sayfa türünü «Tümü» yapın ya da soldan başka bir sorun seçin." />
                ) : (
                  <div className="sg-table-wrap">
                    <table className="sg-table">
                      <thead>
                        <tr>
                          <th>Sayfa</th>
                          <th>Tür</th>
                          <th>Sorunlar <SeoInfo k={r.data?.kaynaklar} label="Sorunlar" /></th>
                        </tr>
                      </thead>
                      <tbody>
                        {d.items.map((it) => (
                          <tr key={it.url}>
                            <td style={{ minWidth: 220 }}>
                              {it.productId ? (
                                <Link to={`/seo-geo/urun-denetimi?urun=${encodeURIComponent(it.productId)}`}>{it.name || it.productId}</Link>
                              ) : (
                                <span style={{ fontWeight: 700 }}>{it.title || KIND_LABEL[it.kind]}</span>
                              )}
                              <div className="sg-mono" style={{ fontSize: 11, wordBreak: 'break-all', marginTop: 2 }}>
                                <a href={it.url} target="_blank" rel="noreferrer">
                                  {it.url.replace(/^https?:\/\//, '')} <ExternalLink size={10} aria-hidden />
                                </a>
                              </div>
                              {it.chain.length > 1 && <Chain chain={it.chain} />}
                              {group === 'image' && it.images && <ImageDetail it={it} />}
                              {group === 'page' && <PageDetail it={it} />}
                            </td>
                            <td>
                              <span className="sg-chip">{KIND_LABEL[it.kind]}</span>
                            </td>
                            <td>
                              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                                {shown(it).map((i) => (
                                  <span key={i} className="sg-chip" title={d.checks.find((c) => c.id === i)?.why}>
                                    <i className={`sg-dot ${sev(i)}`} aria-hidden />
                                    {title(i)}
                                  </span>
                                ))}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <Pager start={start} total={d.total} setStart={setStart} />
              </section>
            </div>
          )}
        </>
      )}
    </>
  );
}

function Chain({ chain }: { chain: Hop[] }) {
  return (
    <details className="sg-more" style={{ marginTop: 6 }}>
      <summary className="sg-mono">
        {chain.map((h) => h.status || 'hata').join(' → ')}
        {chain[chain.length - 1]?.loop ? ' · döngü' : ''}
      </summary>
      <ol style={{ margin: '6px 0 0', paddingLeft: 18, fontSize: 11.5 }}>
        {chain.map((h, i) => (
          <li key={i} className="sg-mono" style={{ wordBreak: 'break-all' }}>
            {h.status || 'hata'} · {h.url}
            {h.error ? ` (${h.error})` : ''}
          </li>
        ))}
      </ol>
    </details>
  );
}

function PageDetail({ it }: { it: TechItem }) {
  const rows: Array<[string, ReactNode]> = [];
  if (it.canonical?.href && it.canonical.kind !== 'self') rows.push(['Asıl adres etiketi (canonical)', it.canonical.href + (it.canonical.target ? ` (${it.canonical.target.status}${it.canonical.target.hops ? `, ${it.canonical.target.hops} yönlendirme` : ''})` : '')]);
  if (it.robots && /noindex|nofollow|none/i.test(it.robots)) rows.push(['Aramadan gizleme ayarı (robots)', it.robots]);
  if (it.xRobotsTag) rows.push(['Sunucunun gizleme ayarı (X-Robots-Tag)', it.xRobotsTag]);
  if (it.title) rows.push(['Sayfa başlığı', `${it.title} (${it.title.length} karakter)`]);
  if (it.trackingLinks.length) rows.push([`İzleme parametreli bağlantı (${it.trackingLinks.length})`, it.trackingLinks.join('\n')]);
  if (!rows.length) return null;
  return (
    <details className="sg-more" style={{ marginTop: 6 }}>
      <summary>Ayrıntı</summary>
      <dl className="sg-facts">
        {rows.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd style={{ whiteSpace: 'pre-wrap' }}>{v}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

function ImageDetail({ it }: { it: TechItem }) {
  const im = it.images!;
  const groups: Array<[string, string[]]> = [
    ['Alt metni yok', im.noAlt],
    ['Boş alt metni', im.emptyAlt],
    ['Anlamsız dosya adı', im.badName],
    ['Boyut yok', im.noSize],
  ];
  return (
    <details className="sg-more" style={{ marginTop: 6 }}>
      <summary>
        {fmt(im.count)} görsel{it.mainImage ? ` · kapak alt metni: “${it.mainImage.alt ?? 'yok'}”` : ''}
      </summary>
      {groups
        .filter(([, l]) => l.length)
        .map(([k, l]) => (
          <div key={k} style={{ marginTop: 6 }}>
            <div className="sg-tag">
              {k.toUpperCase()} ({fmt(l.length)})
            </div>
            <div className="sg-mono" style={{ fontSize: 11, wordBreak: 'break-all', whiteSpace: 'pre-wrap' }}>{l.join('\n')}</div>
          </div>
        ))}
    </details>
  );
}

/* ------------------------------------------------------------------ Google'daki site haritaları */
type GscFlag = 'eski' | 'hata' | 'uyari' | 'okunmuyor' | 'bekliyor';
type GscSitemap = {
  path: string;
  parent: string | null;
  type: string | null;
  isIndex: boolean;
  isPending: boolean;
  lastSubmitted: string | null;
  lastDownloaded: string | null;
  errors: number;
  warnings: number;
  submitted: number | null;
  errorsDelta: number | null;
  warningsDelta: number | null;
  flags: GscFlag[];
};
type GscSnap = {
  site: string;
  link: string;
  summary: { sitemaps: number; errors: number; warnings: number; submitted: number; withErrors: number; withWarnings: number; notRead: number; obsolete: number };
  sitemaps: GscSitemap[];
  error: string | null;
  savedAt: string;
};
const gscApi = {
  get: () => call<{ configured: boolean; snapshot: GscSnap | null; state: RunState; refreshHours: number; staleDays: number }>('gsc-sitemaps'),
  refresh: () => call<{ started: boolean }>('gsc-sitemaps/refresh', { method: 'POST' }),
};
const FLAG_CHIP: Record<GscFlag, [string, 'bad' | 'mid']> = {
  eski: ['Eski kayıt — kaldırın', 'mid'],
  hata: ['Hata', 'bad'],
  uyari: ['Uyarı', 'mid'],
  okunmuyor: ['Google okumuyor', 'mid'],
  bekliyor: ['İşleniyor', 'mid'],
};
const delta = (d: number | null) => (d && d > 0 ? ` (+${fmt(d)})` : d && d < 0 ? ` (${fmt(d)})` : '');

/** Search Console'a gönderilmiş haritaların Google tarafındaki durumu; 6 saatte bir kendiliğinden okunur. */
function GscSitemapsTab() {
  const qc = useQueryClient();
  const r = useQuery({
    queryKey: ['seo-gsc-sitemaps'],
    queryFn: gscApi.get,
    enabled: ENGINE_ENABLED,
    retry: false,
    refetchInterval: (q) => (q.state.data?.state.running ? 5000 : false),
  });
  const refresh = useMutation({ mutationFn: gscApi.refresh, onSuccess: () => qc.invalidateQueries({ queryKey: ['seo-gsc-sitemaps'] }) });
  const d = r.data;
  const s = d?.snapshot;
  const running = !!d?.state.running;
  const sum = s?.summary;

  return (
    <>
      <div className="sg-actions">
        <button className="sg-button" onClick={() => refresh.mutate()} disabled={refresh.isPending || running || !d?.configured}>
          {running ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />}
          {running ? 'Search Console okunuyor…' : 'Şimdi oku'}
        </button>
        {s?.link && (
          <a className="sg-button" href={s.link} target="_blank" rel="noreferrer">
            <ExternalLink size={16} aria-hidden /> Search Console’da aç
          </a>
        )}
      </div>
      {r.isLoading && <Loading text="Site haritası durumu getiriliyor…" />}
      {r.error && <Failed error={r.error} />}
      {refresh.error && <Failed error={refresh.error} />}
      {d && !d.configured && <p className="sg-banner err">Search Console mülkü girilmemiş (Yönetim → SEO &amp; GEO).</p>}
      {(d?.state.error || s?.error) && <p className="sg-banner err">Son okuma başarısız: {d?.state.error || s?.error}</p>}
      {d?.configured && !s && !running && (
        <EmptyHint title="Henüz okunmadı" why={`«Şimdi oku»ya basın; sonra her ${d.refreshHours} saatte bir kendiliğinden okunur.`} />
      )}
      {s && sum && (
        <>
          <section className="sg-kpis" aria-label="Özet">
            <Kpi
              label="Gönderilmiş harita"
              value={fmt(sum.sitemaps)}
              note={`${sum.obsolete ? `${fmt(sum.obsolete)} tanesi eski siteden kalma · ` : ''}son okuma ${dateTime(s.savedAt)}`}
              tone={sum.obsolete ? 'mid' : undefined}
              explain="Search Console’a bildirilmiş site haritası dosyası sayısı. Bir yıldan uzun süredir okunmayanlar eski siteden kalmadır ve kaldırılmalıdır."
            />
            <Kpi label="Hata" value={fmt(sum.errors)} note={`${fmt(sum.withErrors)} haritada`} tone={sum.errors ? 'bad' : 'good'}
              explain="Google’ın haritaları okurken bulduğu hata sayısı. Hatalı haritadaki sayfalar Google’a geç ya da hiç ulaşmayabilir; ayrıntısı Search Console’dadır." />
            <Kpi label="Uyarı" value={fmt(sum.warnings)} note={`${fmt(sum.withWarnings)} haritada`} tone={sum.warnings ? 'bad' : 'good'}
              explain="Haritanın okunmasını durdurmayan ama düzeltilmesi gereken sorunlar." />
            <Kpi
              label="Google’ın okumadığı"
              value={fmt(sum.notRead)}
              note={`${d?.staleDays} günden uzun süredir okunmayan`}
              tone={sum.notRead ? 'bad' : 'good'}
              explain="Google’ın uzun süredir indirmediği haritalar; içlerindeki yeni kitaplar Google’a geç ulaşır."
            />
          </section>
          <section className="sg-card">
            <h2>Haritalar</h2>
            <p className="sg-sub">
              Google hata ve uyarının sayısını verir, metnini vermez; metin Search Console → Site haritaları’nda. Parantez içindeki sayı bir önceki okumaya göre farktır.
              Bir yıldan uzun süredir okunmayan harita eski siteden kalmadır: sayıları özete katılmaz, Search Console’dan kaldırılması iş listesine düşer.
            </p>
            <div className="sg-table-wrap">
              <table className="sg-table">
                <thead>
                  <tr>
                    <th>Harita</th>
                    <th><ExplainLabel label="Gönderilen adres">Haritada Google’a bildirilen sayfa adresi sayısı.</ExplainLabel></th>
                    <th>Hata</th>
                    <th>Uyarı</th>
                    <th>Google son okuma</th>
                    <th>Durum</th>
                  </tr>
                </thead>
                <tbody>
                  {s.sitemaps.map((m) => (
                    <tr key={m.path}>
                      <td className="url">
                        {m.parent ? '↳ ' : ''}
                        {m.path}
                        {m.isIndex ? ' (dizin)' : ''}
                      </td>
                      <td className="num">{m.submitted == null ? '—' : fmt(m.submitted)}</td>
                      <td className="num">{fmt(m.errors) + delta(m.errorsDelta)}</td>
                      <td className="num">{fmt(m.warnings) + delta(m.warningsDelta)}</td>
                      <td className="sg-mono" style={{ whiteSpace: 'nowrap' }}>{m.lastDownloaded ? dateTime(m.lastDownloaded) : 'hiç'}</td>
                      <td>
                        {m.flags.length ? (
                          m.flags.map((f) => (
                            <span key={f} className={`sg-chip ${FLAG_CHIP[f][1]}`} style={{ marginRight: 4 }}>
                              {FLAG_CHIP[f][0]}
                            </span>
                          ))
                        ) : (
                          <span className="sg-chip good">Sorunsuz</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </>
  );
}

/* ------------------------------------------------------------------ sitemap */
function SitemapTab() {
  const qc = useQueryClient();
  const [start, setStart] = useState(0);
  const r = useQuery({
    queryKey: ['seo-tech-sitemaps', start],
    queryFn: () => techApi.sitemaps(start, PAGE),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
    refetchInterval: (q) => (q.state.data?.state.running ? 10000 : false),
  });
  const refresh = useMutation({
    mutationFn: () => techApi.refresh(50),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['seo-tech-sitemaps'] });
      qc.invalidateQueries({ queryKey: ['seo-tech-robots'] });
    },
  });
  const s = r.data?.snapshot;
  const running = !!r.data?.state.running;

  return (
    <>
      <div className="sg-actions">
        <button className="sg-button" onClick={() => refresh.mutate()} disabled={refresh.isPending || running}>
          {running ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />}
          {running ? 'Site haritası okunuyor…' : 'Site haritasını ve robots.txt’i yeniden oku'}
        </button>
      </div>
      {r.isLoading && <Loading text="Sitemap sonuçları getiriliyor…" />}
      {r.error && <Failed error={r.error} />}
      {refresh.error && <Failed error={refresh.error} />}
      {r.data?.state.error && <p className="sg-banner err">Son okuma durdu: {r.data.state.error}</p>}
      {r.data && !s && (
        <EmptyHint
          title="Site haritası henüz okunmadı"
          why="«Yeniden oku»ya basın ya da gece işini bekleyin. robots.txt’te yazan harita adresleri okunur, içlerinden örnek adresler açılıp denetlenir."
        />
      )}
      {s && (
        <>
          <section className="sg-kpis" aria-label="Özet">
            <Kpi label="Site haritası dosyası" value={fmt(s.sitemaps.length)} note={s.fallback ? 'robots.txt’te harita satırı yok; /sitemap.xml denendi' : `robots.txt’te ${fmt(s.declared.length)} adres`} tone={s.fallback ? 'bad' : undefined} info={<SeoInfo k={r.data?.kaynaklar} label="Site haritası dosyası" />}
              explain="Okunan site haritası dosyası sayısı. Site haritası, sitedeki sayfaların Google’a verilen listesidir; adresi robots.txt’te yazmalı, yazmıyorsa arama motorları haritayı bulmakta zorlanır." />
            <Kpi label="Haritalardaki adres" value={fmt(s.totalUrls)} note={`Son okuma ${dateTime(s.checkedAt)}${s.partial ? ' · süre doldu, eksik okundu' : ''}`} info={<SeoInfo k={r.data?.kaynaklar} label="Haritalardaki adres" />}
              explain="Bütün site haritalarında listelenen toplam sayfa adresi." />
            <Kpi label="Haritada olmayan ürün" value={fmt(s.missingCount)} note={`Satıştaki ${fmt(s.activeProducts)} üründen`} tone={s.missingCount ? 'bad' : 'good'} info={<SeoInfo k={r.data?.kaynaklar} label="Haritada olmayan ürün" />}
              explain="Satıştaki ürünlerden adresi hiçbir site haritasında geçmeyenler. Google bunları ancak site içi bağlantılardan bulabilir." />
            <Kpi
              label="Örneklem denetimi"
              value={`${fmt(s.sample.ok)} / ${fmt(s.sample.checked)}`}
              note={`Rastgele ${fmt(s.sample.checked)} adres (toplam ${fmt(s.sample.of)}) · yönlenen ${fmt(s.sample.redirect)} · açılmayan ${fmt(s.sample.error)}`}
              tone={s.sample.checked && s.sample.ok < s.sample.checked ? 'bad' : undefined} info={<SeoInfo k={r.data?.kaynaklar} label="Örneklem denetimi" />}
              explain="Haritalardan rastgele seçilen adreslerin kaçının doğrudan açıldığı. Haritadaki adres yönlenmemeli ve hata vermemeli." />
          </section>

          <section className="sg-card">
            <h2>Site haritası dosyaları <SeoInfo k={r.data?.kaynaklar} label="Site haritası dosyaları" /></h2>
            <p className="sg-sub">Haritadaki en yeni güncelleme tarihi {fmt(s.staleDays)} günden eskiyse «Eski», dosya açılmıyorsa kırmızı işaretlenir: arama motoru yeni kitapları geç görür.</p>
            <div className="sg-table-wrap">
              <table className="sg-table">
                <thead>
                  <tr>
                    <th>Dosya</th>
                    <th>Tür</th>
                    <th>Adres sayısı</th>
                    <th>En yeni güncelleme</th>
                    <th>Durum</th>
                  </tr>
                </thead>
                <tbody>
                  {s.sitemaps.map((m) => (
                    <tr key={m.url}>
                      <td className="url">{m.url}</td>
                      <td>{m.kind === 'index' ? 'Dizin' : m.kind === 'urlset' ? 'Adres listesi' : '—'}</td>
                      <td className="num">{fmt(m.count)}</td>
                      <td className="sg-mono" style={{ whiteSpace: 'nowrap' }}>
                        {m.newest ? dateTime(m.newest) : m.count ? 'tarih yazılmamış' : '—'}
                      </td>
                      <td>
                        {m.error || (m.status && m.status !== 200) ? (
                          <span className="sg-chip bad">{m.error || m.status}</span>
                        ) : m.stale ? (
                          <span className="sg-chip mid">Eski</span>
                        ) : (
                          <span className="sg-chip good">Güncel</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <div className="sg-grid">
            <section className="sg-card sg-span-6">
              <h2>Örneklemde sorunlu adresler <SeoInfo k={r.data?.kaynaklar} label="Örneklemde sorunlu adresler" /></h2>
              <p className="sg-sub">Haritadaki adresler doğrudan açılmalı (200) ve başka adrese yönlenmemeli. Bu bir örneklemdir; bütün adresler denenmedi.</p>
              {!s.sample.items.length ? (
                <p className="sg-banner ok">Örneklemdeki bütün adresler doğrudan açıldı.</p>
              ) : (
                <div className="sg-table-wrap">
                  <table className="sg-table">
                    <thead>
                      <tr>
                        <th>Adres</th>
                        <th>Durum</th>
                      </tr>
                    </thead>
                    <tbody>
                      {s.sample.items.map((x) => (
                        <tr key={x.url}>
                          <td className="url">
                            {x.url}
                            {x.hops > 0 && <div style={{ color: 'var(--sg-muted)' }}>→ {x.final}</div>}
                          </td>
                          <td>
                            <span className={`sg-chip ${x.status === 200 || (x.status >= 300 && x.status < 400) ? 'mid' : 'bad'}`}>
                              {x.status || 'hata'}
                              {x.hops ? ` · ${x.hops} yönlendirme` : ''}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
            <section className="sg-card sg-span-6">
              <h2>Haritada olmayan ürünler <SeoInfo k={r.data?.kaynaklar} label="Haritada olmayan ürünler" /></h2>
              <p className="sg-sub">Satıştaki ürünün adresi hiçbir site haritasında yok. Çok satandan aza; listeyi site yöneticisine iletin.</p>
              {!s.missingCount ? (
                <p className="sg-banner ok">{s.totalUrls ? 'Satıştaki bütün ürünler site haritasında.' : 'Site haritası okunamadığı için karşılaştırma yapılmadı.'}</p>
              ) : (
                <>
                  <div className="sg-table-wrap">
                    <table className="sg-table">
                      <thead>
                        <tr>
                          <th>Kitap</th>
                        </tr>
                      </thead>
                      <tbody>
                        {s.missing.map((m) => (
                          <tr key={m.id}>
                            <td>
                              <Link to={`/seo-geo/urun-denetimi?urun=${encodeURIComponent(m.id)}`}>{m.name || m.id}</Link>{' '}
                              <a href={m.url} target="_blank" rel="noreferrer" aria-label="Sayfayı aç">
                                <ExternalLink size={11} aria-hidden />
                              </a>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <Pager start={start} total={s.missingCount} setStart={setStart} />
                </>
              )}
            </section>
          </div>
        </>
      )}
    </>
  );
}

/* ------------------------------------------------------------------ robots.txt ve yapay zekâ botları */
function BotsTab() {
  const r = useQuery({ queryKey: ['seo-tech-robots'], queryFn: techApi.robots, enabled: ENGINE_ENABLED, retry: false });
  const s = r.data?.snapshot;
  const order: Record<BotRow['purpose'], number> = { search: 0, ai_search: 1, user: 2, training: 3 };
  return (
    <>
      {r.isLoading && <Loading text="robots.txt okunuyor…" />}
      {r.error && <Failed error={r.error} />}
      {s && (
        <>
          <p className="sg-banner">
            Arama motorları ve yapay zekâ servislerinin arama botları, sayfayı ancak robots.txt izin veriyorsa gösterebilir ve kaynak verebilir. Yapay zekâ eğitimi için veri toplayan botları kapatmak görünürlüğü etkilemez; açık ya da kapalı tutmak işletmenin kararıdır. Son okuma {dateTime(s.savedAt)}
            {s.status !== 200 ? ` · robots.txt ${s.status ?? 'açılamadı'} döndü (dosya yoksa her şey açık sayılır)` : ''}. Yenilemek için Site haritası sekmesindeki düğme kullanılır. <Term k="robots" />
          </p>
          <section className="sg-card">
            <h2>Botların izin durumu <SeoInfo k={r.data?.kaynaklar} label="Botların izin durumu" /></h2>
            <p className="sg-sub">Her bot için örnek sayfalarda «Açık» (okuyabilir) ya da «Kapalı» (robots.txt engelliyor). Arama ve yapay zekâ araması botlarında «Kapalı» kırmızıdır, düzeltilmelidir. Kural robots.txt standardına göre okunur: botun kendi bölümü yoksa genel (*) bölüm uygulanır.</p>
            <div className="sg-table-wrap">
              <table className="sg-table">
                <thead>
                  <tr>
                    <th>Bot</th>
                    <th>Ne için</th>
                    {s.paths.map((p) => (
                      <th key={p.url} title={p.url}>
                        {p.label}
                      </th>
                    ))}
                    <th>Açıklama ve öneri</th>
                  </tr>
                </thead>
                <tbody>
                  {[...s.bots]
                    .sort((a, b) => order[a.purpose] - order[b.purpose])
                    .map((b) => (
                      <tr key={b.agent}>
                        <td style={{ whiteSpace: 'nowrap' }}>
                          <strong className="sg-mono">{b.agent}</strong>
                          <div style={{ fontSize: 11, color: 'var(--sg-muted)' }}>
                            {b.owner} · bölüm: {b.group}
                          </div>
                        </td>
                        <td>
                          <span className={`sg-chip ${b.purpose === 'training' ? '' : 'violet'}`}>{b.purposeLabel}</span>
                        </td>
                        {b.results.map((x) => (
                          <td key={x.url} title={x.rule ?? 'Eşleşen kural yok'}>
                            <span className={`sg-chip ${x.allowed ? 'good' : b.purpose === 'training' ? 'mid' : 'bad'}`}>{x.allowed ? 'Açık' : 'Kapalı'}</span>
                          </td>
                        ))}
                        <td style={{ minWidth: 260, fontSize: 12, lineHeight: 1.5 }}>
                          {b.why}
                          <div style={{ marginTop: 4, fontWeight: 700, color: b.blocked && b.purpose !== 'training' ? '#c2361b' : 'var(--sg-ink)' }}>{b.advice}</div>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </section>
          <details className="sg-more">
            <summary>robots.txt içeriği</summary>
            <pre className="sg-pre" style={{ marginTop: 8 }}>{s.text || '(boş ya da okunamadı)'}</pre>
          </details>
        </>
      )}
    </>
  );
}

/* ------------------------------------------------------------------ hız */
function SpeedTab() {
  const qc = useQueryClient();
  const r = useQuery({
    queryKey: ['seo-speed'],
    queryFn: techApi.speed,
    enabled: ENGINE_ENABLED,
    retry: false,
    refetchInterval: (q) => (q.state.data?.state.running ? 15000 : false),
  });
  const run = useMutation({ mutationFn: () => techApi.speedRun(10, 5), onSuccess: () => qc.invalidateQueries({ queryKey: ['seo-speed'] }) });
  const d = r.data;
  const running = !!d?.state.running;

  if (r.isLoading) return <Loading text="Hız ölçümleri getiriliyor…" />;
  if (r.error) return <Failed error={r.error} />;
  if (!d) return null;
  if (!d.configured)
    return (
      <div className="sg-empty">
        <Gauge size={22} aria-hidden />
        <h2>Google hız anahtarı girilmemiş <SeoInfo k={r.data?.kaynaklar} label="Google hız anahtarı girilmemiş" /></h2>
        <p>Sayfa hızı ve gerçek ziyaretçi ölçümleri Google’ın hız ölçüm servislerinden (PageSpeed ve CrUX) okunur. Yöneticiniz anahtarı Yönetim → SEO & GEO → Google API anahtarı alanına girmeli; anahtar yalnız bu iki servisle kısıtlı olmalı.</p>
      </div>
    );

  const phoneTrend = d.trend.origin.filter((t) => t.formFactor === 'phone');
  return (
    <>
      <div className="sg-actions">
        <button className="sg-button" onClick={() => run.mutate()} disabled={run.isPending || running}>
          {running ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <Gauge size={16} aria-hidden />}
          {running ? `Ölçülüyor ${fmt(d.state.done)}${d.state.queue ? ` / ${fmt(d.state.queue)}` : ''}` : 'Hızı şimdi ölç'}
        </button>
      </div>
      {run.error && <Failed error={run.error} />}
      {d.state.error && <p className="sg-banner err">Son ölçüm durdu: {d.state.error}</p>}

      <section className="sg-card">
        <h2>Gerçek ziyaretçilerde hız: bütün site (son 28 gün) <SeoInfo k={r.data?.kaynaklar} label="Gerçek ziyaretçilerde hız" /> <Term k="cwv" /></h2>
        <p className="sg-sub">Chrome kullanan ziyaretçilerin yaşadığı hız; Google sıralamada bunu kullanır. Gösterilen değer, ziyaretlerin %75’inin bundan iyi olduğu değerdir.</p>
        {!d.origin.phone && !d.origin.desktop ? (
          <p className="sg-banner">Henüz ölçüm yok. «Hızı şimdi ölç»e basın ya da gece işini bekleyin.</p>
        ) : (
          <div className="sg-grid">
            {(['phone', 'desktop'] as const).map((ff) => {
              const o = d.origin[ff];
              return (
                <div key={ff} className="sg-span-6" style={{ minWidth: 0 }}>
                  <div className="sg-tag">{ff === 'phone' ? 'TELEFON' : 'MASAÜSTÜ'}</div>
                  {!o ? (
                    <p className="sg-sub">Ölçüm yok.</p>
                  ) : o.noData ? (
                    <p className="sg-sub">Google bu cihazda ölçüm verecek kadar ziyaret görmemiş.</p>
                  ) : o.error ? (
                    <p className="sg-banner err">{o.error}</p>
                  ) : (
                    <div className="sg-kpis">
                      {(['lcp', 'inp', 'cls'] as const).map((m) => {
                        const v = o.metrics[m];
                        return <Kpi key={m} label={METRIC_LABEL[m]} value={metricText(m, v?.p75)} note={thresholdText(m, d.thresholds[m])} tone={v?.category ? CAT_TONE[v.category] : undefined} chip={v?.category ? CAT_LABEL[v.category] : undefined} info={<SeoInfo k={r.data?.kaynaklar} label={METRIC_LABEL[m]} />} explain={METRIC_WHY[m]} />;
                      })}
                    </div>
                  )}
                  {o?.period?.last && <p className="sg-sub" style={{ marginTop: 8 }}>Dönem {o.period.first} – {o.period.last} · okundu {dateTime(o.measuredAt)}</p>}
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section className="sg-card">
        <h2>Örnek sayfalar <SeoInfo k={r.data?.kaynaklar} label="Örnek sayfalar" /></h2>
        <p className="sg-sub">
          Anasayfa, en çok satan {fmt(d.state.sample?.products ?? 10)} ürün, en çok satan {fmt(d.state.sample?.pages ?? 5)} kategori ve yazar sayfası. Puan ve «test» sütunları Google’ın test ortamındaki ölçümüdür (0–100; 90 üstü iyi, 50 altı kötü); sağdaki üç değer o sayfanın gerçek ziyaretçi ölçümü (telefon), ziyaret azsa boş kalır.
        </p>
        {!d.items.length ? (
          <p className="sg-banner">Henüz sayfa ölçümü yok; «Hızı şimdi ölç»e basın ya da gece ölçümünü bekleyin.</p>
        ) : (
          <div className="sg-table-wrap">
            <table className="sg-table">
              <thead>
                <tr>
                  <th>Sayfa</th>
                  <th>Puan (telefon) <SeoInfo k={r.data?.kaynaklar} label="Puan (telefon)" /></th>
                  <th>Puan (masaüstü) <SeoInfo k={r.data?.kaynaklar} label="Puan (masaüstü)" /></th>
                  <th>LCP (test) <SeoInfo k={r.data?.kaynaklar} label="LCP (test)" /></th>
                  <th>CLS (test) <SeoInfo k={r.data?.kaynaklar} label="CLS (test)" /></th>
                  <th><ExplainLabel label="LCP">{METRIC_WHY.lcp}</ExplainLabel> <SeoInfo k={r.data?.kaynaklar} label="LCP" /></th>
                  <th><ExplainLabel label="INP">{METRIC_WHY.inp}</ExplainLabel> <SeoInfo k={r.data?.kaynaklar} label="INP" /></th>
                  <th><ExplainLabel label="CLS">{METRIC_WHY.cls}</ExplainLabel> <SeoInfo k={r.data?.kaynaklar} label="CLS" /></th>
                </tr>
              </thead>
              <tbody>
                {d.items.map((it) => {
                  const mob = it.psi.mobile;
                  const field = it.crux.phone?.metrics ?? {};
                  return (
                    <tr key={it.url}>
                      <td style={{ minWidth: 200 }}>
                        <span style={{ fontWeight: 700 }}>{it.name || it.url}</span> <span className="sg-chip">{KIND_LABEL[it.kind]}</span>
                        <div className="sg-mono" style={{ fontSize: 11, wordBreak: 'break-all' }}>
                          <a href={it.url} target="_blank" rel="noreferrer">
                            {it.url.replace(/^https?:\/\//, '')}
                          </a>
                        </div>
                        {mob?.error && <div style={{ fontSize: 11, color: '#c2361b' }}>{mob.error}</div>}
                      </td>
                      <td>
                        <Score v={mob?.score} />
                      </td>
                      <td>
                        <Score v={it.psi.desktop?.score} />
                      </td>
                      <td>
                        <Cell text={metricText('lcp', mob?.lab?.lcp)} cat={mob?.labCategory?.lcp} />
                      </td>
                      <td>
                        <Cell text={metricText('cls', mob?.lab?.cls)} cat={mob?.labCategory?.cls} />
                      </td>
                      {(['lcp', 'inp', 'cls'] as const).map((m) => (
                        <td key={m}>
                          <Cell text={metricText(m, field[m]?.p75)} cat={field[m]?.category} />
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <div className="sg-grid">
        <section className="sg-card sg-span-6">
          <h2>Eğilim: bütün site (telefon, p75) <SeoInfo k={r.data?.kaynaklar} label="Eğilim: bütün site (telefon, p75)" /></h2>
          <p className="sg-sub">Son {fmt(d.days)} günün her ölçümü.</p>
          {!phoneTrend.length ? (
            <p className="sg-sub">Henüz yeterli ölçüm yok.</p>
          ) : (
            <div className="sg-table-wrap" style={{ maxHeight: 320, overflowY: 'auto' }}>
              <table className="sg-table">
                <thead>
                  <tr>
                    <th>Tarih</th>
                    <th>LCP <SeoInfo k={r.data?.kaynaklar} label="LCP" /></th>
                    <th>INP <SeoInfo k={r.data?.kaynaklar} label="INP" /></th>
                    <th>CLS <SeoInfo k={r.data?.kaynaklar} label="CLS" /></th>
                  </tr>
                </thead>
                <tbody>
                  {[...phoneTrend].reverse().map((t, i) => (
                    <tr key={`${t.date}-${i}`}>
                      <td className="sg-mono">{t.date}</td>
                      <td className="num">{metricText('lcp', t.lcp)}</td>
                      <td className="num">{metricText('inp', t.inp)}</td>
                      <td className="num">{metricText('cls', t.cls)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
        <section className="sg-card sg-span-6">
          <h2>Eğilim: örnek sayfaların ortalama puanı <SeoInfo k={r.data?.kaynaklar} label="Eğilim: örnek sayfaların ortalama puanı" /></h2>
          <p className="sg-sub">Gün başına laboratuvar puanı ortalaması.</p>
          {!d.trend.psi.length ? (
            <p className="sg-sub">Henüz yeterli ölçüm yok.</p>
          ) : (
            <div className="sg-table-wrap" style={{ maxHeight: 320, overflowY: 'auto' }}>
              <table className="sg-table">
                <thead>
                  <tr>
                    <th>Tarih</th>
                    <th>Cihaz</th>
                    <th>Ortalama puan <SeoInfo k={r.data?.kaynaklar} label="Ortalama puan" /></th>
                    <th>Sayfa</th>
                  </tr>
                </thead>
                <tbody>
                  {[...d.trend.psi].reverse().map((t) => (
                    <tr key={`${t.date}-${t.strategy}`}>
                      <td className="sg-mono">{t.date}</td>
                      <td>{t.strategy === 'mobile' ? 'Telefon' : 'Masaüstü'}</td>
                      <td>
                        <Score v={t.score} />
                      </td>
                      <td className="num">{fmt(t.pages)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ küçük parçalar */
function Kpi({ label, value, note, tone, chip, info, explain }: { label: string; value: string; note?: string; tone?: 'good' | 'mid' | 'bad'; chip?: string; info?: ReactNode; explain?: ReactNode }) {
  return (
    <div className="sg-kpi">
      <div className="sg-kpi-label">{label}{info ? <> {info}</> : null}{explain ? <> <Explain label={label}>{explain}</Explain></> : null}</div>
      <div className="sg-kpi-value sg-mono" style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        {value}
        {tone && <span className={`sg-chip ${tone}`}>{chip ?? (tone === 'good' ? 'İyi' : tone === 'mid' ? 'Orta' : 'Dikkat')}</span>}
      </div>
      {note && <div className="sg-kpi-note">{note}</div>}
    </div>
  );
}

function Score({ v }: { v: number | null | undefined }) {
  if (v == null) return <span className="sg-mono">—</span>;
  return <span className={`sg-chip ${v >= 90 ? 'good' : v >= 50 ? 'mid' : 'bad'}`}>{fmt(v)}</span>;
}

function Cell({ text, cat }: { text: string; cat: Cat | undefined }) {
  if (!cat) return <span className="sg-mono">{text}</span>;
  return <span className={`sg-chip ${CAT_TONE[cat]}`}>{text}</span>;
}

function Pager({ start, total, setStart }: { start: number; total: number; setStart: (n: number) => void }) {
  return <SeoPager start={start} total={total} size={PAGE} onChange={setStart} />;
}
