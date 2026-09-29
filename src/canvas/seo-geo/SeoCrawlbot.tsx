import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, ExternalLink, Loader2, RefreshCw, Search } from 'lucide-react';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ENGINE_ENABLED } from '../engine';
import { useCan } from '../useAdmin';
import { call, dateTime, fmt, qs } from './api';
import SeoLayout, { Failed, Loading, SeoInfo } from './SeoLayout';
import { EmptyHint, Explain, ExplainLabel } from '../components/Explain';
import { Term, termText } from './terms';

const PAGE = 40;

type Tone = 'good' | 'mid' | 'bad' | 'violet';
type RunState = { running: boolean; startedAt: string | null; finishedAt: string | null; error: string | null; done?: number; failed?: number; queue?: number | null; stoppedBy?: string | null };
type Summary = {
  inspect: {
    configured: boolean;
    site: string | null;
    serviceAccount: string | null;
    permissionError: string | null;
    quota: { day: string; used: number; limit: number; remaining: number; stopped: string | null };
    run: RunState;
    lastInspectedAt: string | null;
    recentDays: number;
    staleDays: number;
    total: number;
    inspected: number;
    errors: number;
    byStatus: Array<{ status: string; label: string; tone: Tone; count: number }>;
    indexed: number;
    indexedShare: number | null;
    crawledNotIndexed: number;
    discoveredNotCrawled: number;
    canonicalMismatch: number;
    staleSellers: number;
    crawlAge: Array<{ label: string; count: number }>;
    crawledAs: Record<string, number>;
    richIssues: number;
    richIssuePages: number;
    productsInspected: number;
    productsActive: number;
  };
  bots: {
    configured: boolean;
    run: RunState;
    authError: string | null;
    planErrors: Record<string, string>;
    verified: boolean | null;
    partial: string[];
    lastFetch: string | null;
    requests14: number;
    byGroup: Record<string, number>;
    googlebot14: number;
  };
};
type Rich = { verdict: string | null; types: string[]; issues: Array<{ type: string; item: string | null; message: string; severity: string }> };
type UrlRow = {
  url: string;
  kind: string;
  productId: string | null;
  name: string | null;
  sales: number;
  status: string;
  statusLabel: string;
  tone: Tone;
  verdict: string | null;
  coverage: string | null;
  lastCrawl: string | null;
  daysSinceCrawl: number | null;
  googleCanonical: string | null;
  userCanonical: string | null;
  canonicalMismatch: boolean;
  crawledAs: string | null;
  rich: Rich | null;
  data: { referringUrls?: string[]; sitemap?: string[]; link?: string | null } | null;
  error: string | null;
  inspectedAt: string | null;
};
type BotRow = { bot: string; label: string; group: string; requests: number; verified: number | null; status: Record<string, number>; statusClass: Record<string, number>; topPaths: Array<{ path: string; count: number }> };
type Bots = {
  configured: boolean;
  verified: boolean | null;
  authError: string | null;
  planErrors: Record<string, string>;
  partial: string[];
  oldestAvailable: string | null;
  lastFetch: string | null;
  run: RunState;
  days: string[];
  series: Array<Record<string, number | string>>;
  bots: BotRow[];
  statusClass: Record<string, number>;
  topPaths: Array<{ path: string; count: number }>;
  topPathsLimit: number;
};
type Filter = 'all' | 'not_indexed' | 'canonical' | 'stale' | 'errors' | 'rich';

const api = {
  summary: () => call<Summary>('crawlbot'),
  urls: (p: { filter: Filter; start: number; limit: number; q?: string }) => call<{ total: number; start: number; items: UrlRow[] }>(`crawlbot/urls?${qs(p)}`),
  bots: (days: number) => call<Bots>(`crawlbot/bots?${qs({ days })}`),
  run: (part: 'inspect' | 'bots') => call<Record<string, string>>(`crawlbot/run?${qs({ part })}`, { method: 'POST' }),
};

const KIND_LABEL: Record<string, string> = { product: 'Kitap', author: 'Yazar', category: 'Kategori', brand: 'Yayınevi', home: 'Anasayfa' };
const GROUP_LABEL: Record<string, string> = { arama: 'Arama motoru', 'yapay zekâ araması': 'Yapay zekâ araması', 'yapay zekâ eğitimi': 'Yapay zekâ eğitimi' };
const PLAN_PART: Record<string, string> = { istekler: 'Bot istekleri', yollar: 'İstenen yollar', gecmis: 'Geçmiş günler', ag: 'Bağlantı' };
const STOP_LABEL: Record<string, string> = {
  quota: 'günlük kota doldu',
  permission: 'yetki yok',
  budget: 'süre bütçesi doldu; kalan sonraki tura',
  day: 'gün değişti',
  limit: 'bugünkü kota zaten kullanılmış',
  network: "Google'a ulaşılamadı",
};
const COLORS = ['#ff6b4a', '#7c5cff', '#10b981', '#f59e0b', '#0ea5e9', '#e5484d', '#8b5cf6', '#14b8a6', '#a16207', '#64748b', '#db2777', '#2563eb', '#65a30d'];
const TONE_COLOR: Record<Tone, string> = { good: '#10b981', mid: '#f59e0b', bad: '#e5484d', violet: '#7c5cff' };
const pct = (v: number | null | undefined) => (v == null ? '—' : `%${fmt(v * 100, 1)}`);
const ago = (d: number | null) => (d == null ? 'Hiç taranmamış' : d === 0 ? 'Bugün' : `${fmt(d)} gün önce`);
const shortUrl = (u: string) => u.replace(/^https?:\/\/[^/]+/, '') || '/';

function Pager({ start, total, onChange }: { start: number; total: number; onChange: (s: number) => void }) {
  if (total <= PAGE) return null;
  return (
    <div className="sg-pager" style={{ marginTop: 12 }}>
      <button className="sg-button" disabled={start === 0} onClick={() => onChange(Math.max(0, start - PAGE))} aria-label="Önceki sayfa">
        <ChevronLeft size={16} aria-hidden />
      </button>
      <span className="sg-mono">
        {fmt(start + 1)}–{fmt(Math.min(total, start + PAGE))} / {fmt(total)}
      </span>
      <button className="sg-button" disabled={start + PAGE >= total} onClick={() => onChange(start + PAGE)} aria-label="Sonraki sayfa">
        <ChevronRight size={16} aria-hidden />
      </button>
    </div>
  );
}

function Bars({ rows, total }: { rows: Array<{ key: string; label: string; count: number; tone?: Tone }>; total: number }) {
  return (
    <div className="sg-bars">
      {rows.map((r) => (
        <div key={r.key} className="sg-bar-row">
          <span style={{ display: 'flex', gap: 8, alignItems: 'center', minWidth: 0 }}>
            {r.tone && <i className="sg-dot" style={{ background: TONE_COLOR[r.tone] }} aria-hidden />}
            {r.label}
          </span>
          <span className="sg-mono">
            {fmt(r.count)} · %{Math.round((100 * r.count) / Math.max(1, total))}
          </span>
          <span className="sg-bar">
            <i style={{ width: `${(100 * r.count) / Math.max(1, total)}%` }} />
          </span>
        </div>
      ))}
    </div>
  );
}

/** Google taraması: Search Console URL Denetimi ile her kitap/sayfa için Google'ın son hâli ve site ağ geçidinin bot
 *  istatistiğiyle Googlebot'un ve yapay zekâ botlarının sitede ne yaptığı. Hiçbir yere yazılmaz. */
export default function SeoCrawlbot() {
  const qc = useQueryClient();
  const canRun = useCan('seo.calistir');
  const [tab, setTab] = useState<'dizin' | 'botlar'>('dizin');
  const summary = useQuery({
    queryKey: ['seo-crawlbot'],
    queryFn: api.summary,
    enabled: ENGINE_ENABLED,
    retry: false,
    refetchInterval: (s) => (s.state.data?.inspect.run.running || s.state.data?.bots.run.running ? 5000 : false),
  });
  const run = useMutation({
    mutationFn: api.run,
    onSuccess: () => qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith('seo-crawlbot') }),
  });
  const d = summary.data;
  const ins = d?.inspect;
  const busy = !!ins?.run.running;
  const botsBusy = !!d?.bots.run.running;

  // Tur bitince listeler de tazelensin.
  const [wasBusy, setWasBusy] = useState(false);
  useEffect(() => {
    if (wasBusy && !busy && !botsBusy) qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith('seo-crawlbot-') });
    setWasBusy(busy || botsBusy);
  }, [busy, botsBusy, wasBusy, qc]);

  return (
    <SeoLayout k={summary.data?.kaynaklar}
      path="/seo-geo/google-taramasi"
      crumb="Google taraması"
      eyebrow="SEO & GEO · Google taraması"
      title="Google taraması"
      lead={<>Google’ın kitap sayfalarımızı ne zaman okuduğu ve aramada gösterip göstermeyeceğine dair kararı (Search Console’dan), ayrıca Google’ın ve yapay zekâ servislerinin botlarının siteye ne kadar geldiği (site ağ geçidinden). Yalnız okunur, hiçbir yere yazılmaz. <Term k="googlebot" /></>}
      actions={
        canRun && ins?.configured ? (
          <button className="sg-button primary" onClick={() => run.mutate('inspect')} disabled={run.isPending || busy || ins.quota.remaining <= 0}>
            {busy ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />}
            {busy ? `Denetleniyor ${fmt(ins.run.done ?? 0)}${ins.run.queue ? ` / ${fmt(ins.run.queue)}` : ''}` : ins.quota.remaining > 0 ? 'Şimdi denetle' : 'Bugünkü kota doldu'}
          </button>
        ) : undefined
      }
    >
      {summary.isLoading && <Loading text="Tarama durumu getiriliyor…" />}
      {summary.error && <Failed error={summary.error} />}
      {run.error && <Failed error={run.error} />}

      {d && ins && (
        <>
          {!ins.configured && (
            <section className="sg-card">
              <h2>Search Console bağlantısı eksik <SeoInfo k={summary.data?.kaynaklar} label="Search Console bağlantısı eksik" /></h2>
              <p className="sg-sub">URL Denetimi, Google'ın her sayfa için verdiği kararı okur; yalnız okuma yapılır.</p>
              <ol style={{ margin: 0, paddingLeft: 20, fontSize: 13, lineHeight: 1.7 }}>
                <li>
                  Google servis hesabı ve Search Console mülkü <Link to="/seo-geo/baglantilar">Bağlantılar</Link> ekranında tanımlı olmalı{ins.site ? '' : ' (mülk henüz girilmemiş)'}.
                </li>
                <li>Servis hesabı Search Console → Ayarlar → Kullanıcılar ve izinler bölümünde bu mülke <strong>sahip ya da tam yetkili</strong> olarak eklenmeli; kısıtlı kullanıcı denetim yapamaz.</li>
                <li>Günlük denetim sayısı Yönetim → SEO & GEO → günlük denetim kotası alanından ayarlanır (Google mülk başına günde 2.000 verir).</li>
              </ol>
            </section>
          )}
          {ins.permissionError && (
            <div className="sg-banner err" style={{ display: 'grid', gap: 4 }}>
              <strong>Servis hesabı Search Console'da sahip/tam yetkili olmalı.</strong>
              <span>{ins.permissionError}</span>
            </div>
          )}
          {ins.run.error && !ins.permissionError && <p className="sg-banner err">{ins.run.error}</p>}
          {run.data && (
            <p className="sg-banner ok">
              {Object.values(run.data).join(' · ')}
            </p>
          )}

          <section className="sg-kpis" aria-label="Özet">
            <div className="sg-kpi">
              <div className="sg-kpi-label">Dizinde oranı <SeoInfo k={summary.data?.kaynaklar} label="Dizinde oranı" /> <Explain label="Dizinde oranı">{`Denetlenen adreslerden yüzde kaçı Google’ın kayıtlı sayfa listesinde (dizinde). ${termText('index')} «Tarandı ama dizinde değil»: Google okudu ama göstermemeye karar verdi.`}</Explain></div>
              <div className="sg-kpi-value sg-mono">{pct(ins.indexedShare)}</div>
              <div className="sg-kpi-note">
                Denetlenen {fmt(ins.inspected)} adresten {fmt(ins.indexed)} · tarandı ama dizinde değil {fmt(ins.crawledNotIndexed)} · keşfedildi ama taranmadı {fmt(ins.discoveredNotCrawled)}
              </div>
            </div>
            <div className="sg-kpi">
              <div className="sg-kpi-label">{ins.staleDays}+ gündür taranmayan satan kitap <Explain label="Uzun süredir taranmayan kitap">Google bu sayfaları uzun süredir okumadığı için fiyat, stok ya da açıklama değişiklikleri aramaya geç yansır. Site içi bağlantı ve site haritası yardımcı olur.</Explain></div>
              <div className="sg-kpi-value sg-mono">{fmt(ins.staleSellers)}</div>
              <div className="sg-kpi-note">Satışı olan ve Google'ın {ins.staleDays} günden uzun süredir (ya da hiç) taramadığı kitap sayfaları</div>
            </div>
            <div className="sg-kpi">
              <div className="sg-kpi-label">Asıl adres uyuşmazlığı <SeoInfo k={summary.data?.kaynaklar} label="Asıl adres uyuşmazlığı" /> <Term k="canonical" label="Asıl adres uyuşmazlığı" /></div>
              <div className="sg-kpi-value sg-mono">{fmt(ins.canonicalMismatch)}</div>
              <div className="sg-kpi-note">Google'ın sitenin gösterdiğinden başka bir adresi asıl saydığı sayfa</div>
            </div>
            <div className="sg-kpi">
              <div className="sg-kpi-label">Bot istekleri (14 gün) <SeoInfo k={summary.data?.kaynaklar} label="Bot istekleri (14 gün)" /> <Explain label="Bot istekleri">Son 14 günde arama motoru ve yapay zekâ botlarının siteye yaptığı istek sayısı. Bot sayfayı okumazsa ne aramada ne yapay zekâ cevabında çıkar.</Explain></div>
              <div className="sg-kpi-value sg-mono">{d.bots.configured ? fmt(d.bots.requests14) : '—'}</div>
              <div className="sg-kpi-note">{d.bots.configured ? `Googlebot ${fmt(d.bots.googlebot14)} · yapay zekâ botları ${fmt((d.bots.byGroup['yapay zekâ araması'] ?? 0) + (d.bots.byGroup['yapay zekâ eğitimi'] ?? 0))}` : 'Site ağ geçidi bağlı değil'}</div>
            </div>
          </section>

          <p className="sg-sub" style={{ margin: 0, fontSize: 12, color: 'var(--sg-muted)' }}>
            Bugün {fmt(ins.quota.used)} / {fmt(ins.quota.limit)} denetim kullanıldı{ins.quota.stopped ? ' (Google kotası doldu, yarın sürer)' : ''} · etkin {fmt(ins.productsActive)} kitaptan {fmt(ins.productsInspected)} tanesi en az bir kez denetlendi · son denetim {dateTime(ins.lastInspectedAt)}
            {ins.run.stoppedBy && !busy ? ` · son tur: ${STOP_LABEL[ins.run.stoppedBy] ?? ins.run.stoppedBy}` : ''}. Her gece çok satan kitaplardan başlanır; son {ins.recentDays} günde bakılanlar sona kalır.
          </p>

          <div className="sg-filters" role="tablist" aria-label="Bölüm">
            <button role="tab" className="sg-filter" aria-pressed={tab === 'dizin'} aria-selected={tab === 'dizin'} onClick={() => setTab('dizin')}>
              Dizin durumu
            </button>
            <button role="tab" className="sg-filter" aria-pressed={tab === 'botlar'} aria-selected={tab === 'botlar'} onClick={() => setTab('botlar')}>
              Googlebot ve yapay zekâ botları
            </button>
          </div>

          {tab === 'dizin' && <IndexTab s={ins} />}
          {tab === 'botlar' && <BotsTab configured={d.bots.configured} canRun={canRun} onRun={() => run.mutate('bots')} running={botsBusy || run.isPending} />}
        </>
      )}
    </SeoLayout>
  );
}

const FILTER_LABEL: Record<Filter, string> = {
  all: 'Tümü',
  not_indexed: 'Dizinde değil',
  canonical: 'Asıl adres uyuşmazlığı',
  stale: 'Uzun süredir taranmayan',
  errors: 'Hatalar ve engeller',
  rich: 'Zengin sonuç sorunları',
};

function IndexTab({ s }: { s: Summary['inspect'] }) {
  // İş listesinden gelen bağlantı filtreyi seçili açar (ör. ?filtre=rich).
  const [params] = useSearchParams();
  const initial = params.get('filtre') as Filter | null;
  const [filter, setFilter] = useState<Filter>(
    initial && ['all', 'not_indexed', 'canonical', 'stale', 'errors', 'rich'].includes(initial) ? initial : 'not_indexed',
  );
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [start, setStart] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => setQuery(q), 300);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => setStart(0), [filter, query]);
  const list = useQuery({
    queryKey: ['seo-crawlbot-urls', filter, query, start],
    queryFn: () => api.urls({ filter, start, limit: PAGE, q: query }),
    enabled: ENGINE_ENABLED && s.total > 0,
    retry: false,
    placeholderData: (p) => p,
  });
  const counts: Partial<Record<Filter, number>> = {
    all: s.total,
    not_indexed: s.inspected - s.indexed,
    canonical: s.canonicalMismatch,
    errors: s.byStatus.filter((b) => ['noindex', 'robots_blocked', 'not_found', 'soft_404', 'fetch_error', 'error'].includes(b.status)).reduce((a, b) => a + b.count, 0),
    rich: s.richIssuePages,
  };
  const mobile = s.crawledAs.MOBILE ?? 0;
  const desktop = s.crawledAs.DESKTOP ?? 0;

  if (s.total === 0) {
    return (
      <EmptyHint
        title="Henüz denetlenen adres yok"
        why={s.configured ? 'İlk denetim bu gece yapılır; hemen başlatmak için «Şimdi denetle»ye basın.' : 'Search Console bağlantısı kurulunca her gece çok satan kitaplardan başlayarak denetlenir.'}
      />
    );
  }
  return (
    <>
      <div className="sg-grid">
        <section className="sg-card sg-span-4">
          <h2>Google'ın kararı <SeoInfo k={list.data?.kaynaklar} label="Google'ın kararı" /></h2>
          <p className="sg-sub">Denetlenen {fmt(s.total)} adres, Google'ın son hâline göre.</p>
          <Bars rows={s.byStatus.map((b) => ({ key: b.status, label: b.label, count: b.count, tone: b.tone }))} total={s.total} />
        </section>
        <section className="sg-card sg-span-4">
          <h2>Son taramadan bu yana <SeoInfo k={list.data?.kaynaklar} label="Son taramadan bu yana" /></h2>
          <p className="sg-sub">Googlebot'un sayfayı en son ne zaman açtığı.</p>
          <Bars rows={s.crawlAge.map((a) => ({ key: a.label, label: a.label, count: a.count }))} total={s.inspected} />
        </section>
        <section className="sg-card sg-span-4">
          <h2>Hangi tarayıcıyla <SeoInfo k={list.data?.kaynaklar} label="Hangi tarayıcıyla" /></h2>
          <p className="sg-sub">Google siteyi çoğunlukla akıllı telefon tarayıcısıyla değerlendirir; masaüstü payı yüksekse mobil sürümde sorun olabilir.</p>
          <Bars
            rows={[
              { key: 'm', label: 'Akıllı telefon', count: mobile },
              { key: 'd', label: 'Masaüstü', count: desktop },
            ]}
            total={mobile + desktop}
          />
          {s.richIssues > 0 && (
            <p className="sg-banner" style={{ marginTop: 14 }}>
              {fmt(s.richIssuePages)} sayfada {fmt(s.richIssues)} zengin sonuç uyarısı var (ürün bilgisi, yorum, fiyat gibi alanlar).
            </p>
          )}
        </section>
      </div>

      <section className="sg-card">
        <h2>{FILTER_LABEL[filter]}</h2>
        <p className="sg-sub">
          {filter === 'stale'
            ? `Google'ın ${s.staleDays} günden uzun süredir ya da hiç taramadığı adresler, çok satandan aza.`
            : 'Anasayfa ve kitaplar önce (çok satandan aza), sonra yazar, kategori ve yayınevi sayfaları. Kitap adına tıklayınca ürün denetimi açılır.'}
        </p>
        <div className="sg-filters" role="group" aria-label="Süzgeç">
          {(Object.keys(FILTER_LABEL) as Filter[]).map((k) => (
            <button key={k} className="sg-filter" aria-pressed={filter === k} onClick={() => setFilter(k)}>
              {FILTER_LABEL[k]}
              {counts[k] != null && <span className="sg-mono">{fmt(counts[k])}</span>}
            </button>
          ))}
        </div>
        <label className="sg-search" style={{ margin: '12px 0' }}>
          <Search size={16} aria-hidden />
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Kitap adı ya da adres" aria-label="Ara" style={{ fontSize: 16 }} />
        </label>
        {list.error && <Failed error={list.error} />}
        {list.data && list.data.total === 0 && <EmptyHint title="Bu süzgeçte adres yok" why={query ? 'Aramayı kısaltın ya da temizleyin.' : 'Başka bir süzgeç seçin; bu durumda sayfa olmaması iyi haberdir.'} />}
        {list.data && list.data.total > 0 && (
          <div className="sg-table-wrap">
            <table className="sg-table">
              <thead>
                <tr>
                  <th>Sayfa</th>
                  <th>Google'ın kararı</th>
                  <th>Son tarama <SeoInfo k={list.data?.kaynaklar} label="Son tarama" /></th>
                  <th>Tarayıcı</th>
                  <th><ExplainLabel label="Asıl adres">{termText('canonical')} «Uyuşmuyor»: Google, sitenin gösterdiğinden başka bir adresi asıl saydı.</ExplainLabel></th>
                  <th><ExplainLabel label="Zengin sonuç">Google sonucunda fiyat, stok, yıldız gibi ek bilgilerin çıkması için sayfadaki yapısal veri. Uyarı varsa bu ek bilgiler çıkmayabilir.</ExplainLabel></th>
                  <th>Denetlendi</th>
                </tr>
              </thead>
              <tbody>
                {list.data.items.map((r) => (
                  <UrlLine key={r.url} r={r} staleDays={s.staleDays} />
                ))}
              </tbody>
            </table>
          </div>
        )}
        {list.data && <Pager start={start} total={list.data.total} onChange={setStart} />}
      </section>
    </>
  );
}

function UrlLine({ r, staleDays }: { r: UrlRow; staleDays: number }) {
  const issues = r.rich?.issues ?? [];
  return (
    <tr>
      <td style={{ minWidth: 200, maxWidth: 360 }}>
        <div style={{ display: 'grid', gap: 2 }}>
          {r.kind === 'product' && r.productId ? (
            <Link to={`/seo-geo/urun-denetimi?urun=${encodeURIComponent(r.productId)}`} style={{ fontWeight: 700 }}>
              {r.name || r.productId}
            </Link>
          ) : (
            <span style={{ fontWeight: 700 }}>{KIND_LABEL[r.kind] ?? r.kind}</span>
          )}
          <a href={r.url} target="_blank" rel="noreferrer" className="sg-mono" style={{ fontSize: 11, wordBreak: 'break-all', color: 'var(--sg-muted)' }}>
            {shortUrl(r.url)} <ExternalLink size={10} aria-hidden />
          </a>
          {r.kind === 'product' && r.sales > 0 && <span style={{ fontSize: 11, color: 'var(--sg-muted)' }}>{fmt(r.sales)} satış</span>}
        </div>
      </td>
      <td>
        <span className={`sg-chip ${r.tone}`} title={r.coverage ?? undefined}>
          {r.statusLabel}
        </span>
        {r.error && <div style={{ fontSize: 11, color: '#9b1c24', marginTop: 4, maxWidth: 260 }}>{r.error}</div>}
      </td>
      <td className="sg-mono" style={{ whiteSpace: 'nowrap', color: r.daysSinceCrawl == null || r.daysSinceCrawl > staleDays ? '#c2361b' : undefined }}>
        {ago(r.daysSinceCrawl)}
      </td>
      <td>{r.crawledAs === 'MOBILE' ? 'Akıllı telefon' : r.crawledAs === 'DESKTOP' ? 'Masaüstü' : '—'}</td>
      <td style={{ maxWidth: 260 }}>
        {r.canonicalMismatch ? (
          <div style={{ display: 'grid', gap: 2, fontSize: 11.5 }}>
            <span className="sg-chip mid">Uyuşmuyor</span>
            <span>
              Google: <span className="sg-mono" style={{ wordBreak: 'break-all' }}>{r.googleCanonical ? shortUrl(r.googleCanonical) : '—'}</span>
            </span>
            <span>
              Site: <span className="sg-mono" style={{ wordBreak: 'break-all' }}>{r.userCanonical ? shortUrl(r.userCanonical) : 'bildirmiyor'}</span>
            </span>
          </div>
        ) : r.googleCanonical ? (
          <span className="sg-chip good">Aynı</span>
        ) : (
          '—'
        )}
      </td>
      <td style={{ maxWidth: 260 }}>
        {issues.length > 0 ? (
          <details className="sg-more">
            <summary>{fmt(issues.length)} uyarı</summary>
            <ul className="sg-hints" style={{ marginTop: 6 }}>
              {issues.map((i, n) => (
                <li key={n}>
                  {i.type}: {i.message}
                </li>
              ))}
            </ul>
          </details>
        ) : r.rich?.types.length ? (
          <span className="sg-chip good">{r.rich.types.join(', ')}</span>
        ) : (
          '—'
        )}
      </td>
      <td className="sg-mono" style={{ whiteSpace: 'nowrap' }}>
        {dateTime(r.inspectedAt)}
      </td>
    </tr>
  );
}

function BotsTab({ configured, canRun, onRun, running }: { configured: boolean; canRun: boolean; onRun: () => void; running: boolean }) {
  const [days, setDays] = useState(14);
  const [picked, setPicked] = useState<string[] | null>(null);
  const [pathBot, setPathBot] = useState<string>('');
  const q = useQuery({ queryKey: ['seo-crawlbot-bots', days], queryFn: () => api.bots(days), enabled: ENGINE_ENABLED && configured, retry: false, placeholderData: (p) => p });
  const b = q.data;
  const shown = useMemo(() => picked ?? (b?.bots ?? []).slice(0, 5).map((x) => x.bot), [picked, b]);
  const color = (bot: string) => COLORS[Math.max(0, (b?.bots ?? []).findIndex((x) => x.bot === bot)) % COLORS.length];
  const label = (bot: string) => b?.bots.find((x) => x.bot === bot)?.label ?? bot;

  if (!configured) {
    return (
      <section className="sg-card">
        <h2>Site ağ geçidi (CDN) bağlı değil <SeoInfo k={q.data?.kaynaklar} label="Site ağ geçidi (CDN) bağlı değil" /></h2>
        <p className="sg-sub">Googlebot'un ve yapay zekâ botlarının siteye kaç istek attığı, hangi yanıtları aldığı ve en çok hangi sayfaları istediği sunucu günlüğü olmadan buradan okunur. Yalnız okuma izni kullanılır.</p>
        <ol style={{ margin: 0, paddingLeft: 20, fontSize: 13, lineHeight: 1.7 }}>
          <li>Site ağ geçidi (CDN) panelinde bir API belirteci oluşturun; yalnız bu site için “Analytics: Read” (analitik okuma) izni yeterlidir.</li>
          <li>Sitenin bölge (zone) kimliğini aynı panelin genel bakış sayfasından kopyalayın.</li>
          <li>İkisini Yönetim → SEO & GEO bölümündeki ilgili alanlara yapıştırın. Ertesi gece kendiliğinden okunur.</li>
        </ol>
      </section>
    );
  }
  if (q.isLoading) return <Loading text="Bot istatistiği getiriliyor…" />;
  if (q.error) return <Failed error={q.error} />;
  if (!b) return null;

  const planEntries = Object.entries(b.planErrors);
  const total = b.bots.reduce((a, x) => a + x.requests, 0);
  const pathList = pathBot ? b.bots.find((x) => x.bot === pathBot)?.topPaths ?? [] : b.topPaths;
  const classTotal = Object.values(b.statusClass).reduce((a, n) => a + n, 0);

  return (
    <>
      {b.authError && <p className="sg-banner err">{b.authError}</p>}
      {planEntries.length > 0 && (
        <div className="sg-banner" style={{ display: 'grid', gap: 4 }}>
          <strong>Planınız bu veriyi vermiyor{planEntries.length === 1 ? `: ${(PLAN_PART[planEntries[0][0]] ?? planEntries[0][0]).toLowerCase()}` : ''}.</strong>
          {b.oldestAvailable && <span>En eski okunabilen gün {b.oldestAvailable}.</span>}
          <details>
            <summary style={{ cursor: 'pointer' }}>Ayrıntı</summary>
            {planEntries.map(([k, m]) => (
              <div key={k} className="sg-mono" style={{ fontSize: 11, marginTop: 4 }}>
                {PLAN_PART[k] ?? k}: {m}
              </div>
            ))}
          </details>
        </div>
      )}
      {b.verified !== true && total > 0 && (
        <p className="sg-banner">Sayılar, kendini bu bot olarak tanıtan isteklerdir: kullanıcı ajanı taklit edilebilir, planınız doğrulanmış bot bilgisini vermiyor.</p>
      )}
      {b.partial.length > 0 && <p className="sg-banner">Şu günlerde istek çeşitliliği tek okumanın sınırını aştı, sayılar eksik olabilir: {b.partial.join(', ')}.</p>}

      <section className="sg-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <div>
            <h2>Günlük bot istekleri <SeoInfo k={q.data?.kaynaklar} label="Günlük bot istekleri" /></h2>
            <p className="sg-sub" style={{ margin: 0, fontSize: 12, color: 'var(--sg-muted)' }}>
              Gün (UTC) başına istek · son okuma {dateTime(b.lastFetch)}
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <div className="sg-filters" role="group" aria-label="Dönem">
              {[7, 14, 30].map((n) => (
                <button key={n} className="sg-filter" aria-pressed={days === n} onClick={() => setDays(n)}>
                  {n} gün
                </button>
              ))}
            </div>
            {canRun && (
              <button className="sg-button" onClick={onRun} disabled={running}>
                {running ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />}
                {running ? 'Okunuyor…' : 'Yeniden oku'}
              </button>
            )}
          </div>
        </div>
        {b.days.length === 0 ? (
          <p className="sg-sub" style={{ marginTop: 14 }}>Bu dönemde okunmuş veri yok; dönemi uzatın ya da ertesi gece okumasını bekleyin.</p>
        ) : (
          <>
            <div className="sg-filters" role="group" aria-label="Botlar" style={{ margin: '14px 0 8px' }}>
              {b.bots.map((x) => (
                <button
                  key={x.bot}
                  className="sg-filter"
                  aria-pressed={shown.includes(x.bot)}
                  onClick={() => setPicked(shown.includes(x.bot) ? shown.filter((k) => k !== x.bot) : [...shown, x.bot])}
                >
                  <span aria-hidden style={{ width: 8, height: 8, borderRadius: 999, background: color(x.bot) }} />
                  {x.label}
                  <span className="sg-mono">{fmt(x.requests)}</span>
                </button>
              ))}
            </div>
            <div className="sg-chart" style={{ height: 260 }}>
              <ResponsiveContainer>
                <LineChart data={b.series} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
                  <CartesianGrid stroke="#ebe6f0" vertical={false} />
                  <XAxis dataKey="day" tickFormatter={(v: string) => v.slice(5)} tick={{ fontSize: 10 }} tickLine={false} axisLine={false} minTickGap={16} />
                  <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={44} />
                  <Tooltip formatter={(v: number, k: string | number) => [fmt(v), label(String(k))]} />
                  <Legend formatter={(k: string) => label(k)} wrapperStyle={{ fontSize: 11 }} />
                  {shown.map((k) => (
                    <Line key={k} type="monotone" dataKey={k} stroke={color(k)} strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </>
        )}
      </section>

      {b.bots.length > 0 && (
        <div className="sg-grid">
          <section className="sg-card sg-span-8">
            <h2>Bot başına yanıtlar <SeoInfo k={q.data?.kaynaklar} label="Bot başına yanıtlar" /></h2>
            <p className="sg-sub">
              Son {days} gün. 4xx ve 5xx yanıtları botun boşa harcadığı taramadır; 3xx çoksa bağlantılar eski adresleri gösteriyor olabilir.{' '}
              <Explain label="Yanıt kodları" title="Yanıt kodları">2xx: sayfa açıldı. 3xx: başka adrese yönlendi. 4xx: bulunamadı ya da erişim yok. 5xx: sitenin sunucusunda hata. «Doğrulanmış»: gerçekten o bota ait olduğu doğrulanan istekler.</Explain>
            </p>
            <div className="sg-table-wrap">
              <table className="sg-table">
                <thead>
                  <tr>
                    <th>Bot</th>
                    <th>Tür</th>
                    <th>İstek <SeoInfo k={q.data?.kaynaklar} label="İstek" /></th>
                    <th>Doğrulanmış <SeoInfo k={q.data?.kaynaklar} label="Doğrulanmış" /></th>
                    <th>2xx <SeoInfo k={q.data?.kaynaklar} label="2xx" /></th>
                    <th>3xx <SeoInfo k={q.data?.kaynaklar} label="3xx" /></th>
                    <th>4xx <SeoInfo k={q.data?.kaynaklar} label="4xx" /></th>
                    <th>5xx <SeoInfo k={q.data?.kaynaklar} label="5xx" /></th>
                  </tr>
                </thead>
                <tbody>
                  {b.bots.map((x) => (
                    <tr key={x.bot}>
                      <td style={{ whiteSpace: 'nowrap', fontWeight: 700 }}>{x.label}</td>
                      <td>{GROUP_LABEL[x.group] ?? x.group}</td>
                      <td className="num">{fmt(x.requests)}</td>
                      <td className="num">{x.verified == null ? '—' : fmt(x.verified)}</td>
                      <td className="num">{fmt(x.statusClass['2xx'] ?? 0)}</td>
                      <td className="num">{fmt(x.statusClass['3xx'] ?? 0)}</td>
                      <td className="num" style={{ color: x.statusClass['4xx'] ? '#c2361b' : undefined }}>{fmt(x.statusClass['4xx'] ?? 0)}</td>
                      <td className="num" style={{ color: x.statusClass['5xx'] ? '#c2361b' : undefined }}>{fmt(x.statusClass['5xx'] ?? 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section className="sg-card sg-span-4">
            <h2>Yanıt kodu dağılımı <SeoInfo k={q.data?.kaynaklar} label="Yanıt kodu dağılımı" /></h2>
            <p className="sg-sub">Bütün botların istekleri, son {days} gün.</p>
            <Bars
              rows={Object.entries(b.statusClass)
                .sort(([a], [c]) => a.localeCompare(c))
                .map(([k, n]) => ({ key: k, label: k, count: n, tone: (k === '2xx' ? 'good' : k === '3xx' ? 'violet' : k === 'diğer' ? 'mid' : 'bad') as Tone }))}
              total={classTotal}
            />
          </section>
        </div>
      )}

      {b.bots.length > 0 && (
        <section className="sg-card">
          <h2>En çok istenen yollar <SeoInfo k={q.data?.kaynaklar} label="En çok istenen yollar" /></h2>
          <p className="sg-sub">Her bot için günde en çok istenen {fmt(b.topPathsLimit)} yol saklanır; burada seçilen dönemde toplanmış hâli, en çoktan aza.</p>
          <div className="sg-filters" role="group" aria-label="Bot" style={{ marginBottom: 12 }}>
            <button className="sg-filter" aria-pressed={pathBot === ''} onClick={() => setPathBot('')}>
              Bütün botlar
            </button>
            {b.bots.map((x) => (
              <button key={x.bot} className="sg-filter" aria-pressed={pathBot === x.bot} onClick={() => setPathBot(x.bot)}>
                {x.label}
              </button>
            ))}
          </div>
          {pathList.length === 0 ? (
            <p className="sg-sub">{b.planErrors.yollar ? 'Planınız istenen yolları vermiyor.' : 'Yol verisi yok.'}</p>
          ) : (
            <div className="sg-table-wrap">
              <table className="sg-table">
                <thead>
                  <tr>
                    <th>Yol</th>
                    <th>İstek <SeoInfo k={q.data?.kaynaklar} label="İstek" /></th>
                  </tr>
                </thead>
                <tbody>
                  {pathList.map((p) => (
                    <tr key={p.path}>
                      <td className="url">{p.path}</td>
                      <td className="num">{fmt(p.count)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </>
  );
}
